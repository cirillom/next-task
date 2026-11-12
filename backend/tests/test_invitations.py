import re
from argparse import Namespace
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta

import pytest
from app import cli
from app.auth.security import hash_token
from app.database import SessionLocal
from app.main import app
from app.models import Invitation, User, UserSession
from app.schemas import ensure_utc
from app.services import invitations
from app.services.mail import MailConfigurationError, MailDeliveryError
from fastapi.testclient import TestClient
from sqlalchemy import func, select

EMAIL = "guest@example.com"
PASSWORD = "a secure password"


@pytest.fixture
def messages(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    sent: list[str] = []
    monkeypatch.setattr(invitations, "public_app_url", lambda: "https://tasks.example.com")
    monkeypatch.setattr(invitations, "send_email", lambda _to, _subject, body: sent.append(body))
    return sent


def invite(messages: list[str]) -> str:
    cli.invite_user(Namespace(email=f"  {EMAIL.upper()}  "))
    match = re.search(r"token=([A-Za-z0-9_-]+)", messages[-1])
    assert match is not None
    return match.group(1)


def accept(client: TestClient, token: str, **changes: str):
    return client.post(
        "/api/auth/invitations/accept",
        json={"token": token, "display_name": "  Guest User  ", "password": PASSWORD, **changes},
    )


def test_invite_creates_verified_account_only_on_redemption(
    client: TestClient, messages: list[str], capsys: pytest.CaptureFixture[str]
) -> None:
    before = datetime.now(UTC)
    token = invite(messages)
    assert "https://tasks.example.com/#/accept-invite?token=" in messages[-1]
    assert "24 hours" in messages[-1]
    assert token not in capsys.readouterr().out
    with SessionLocal() as db:
        pending = db.get(Invitation, EMAIL)
        assert pending.token_hash == hash_token(token)
        assert token not in pending.token_hash
        assert before + timedelta(hours=24) <= ensure_utc(pending.expires_at)
        assert db.scalar(select(func.count(User.id))) == 0
    response = accept(client, token, email="different@example.com")
    assert response.status_code == 201, response.text
    assert "set-cookie" not in response.headers
    assert client.get("/api/auth/me").status_code == 401
    with SessionLocal() as db:
        user = db.scalar(select(User))
        assert user.email == EMAIL  # The token, never client input, chooses the address.
        assert user.display_name == "Guest User"
        assert user.email_verified_at is not None
        assert user.password_hash.startswith("$argon2id$")
        assert db.get(Invitation, EMAIL) is None
        assert db.scalar(select(func.count(UserSession.token_hash))) == 0
    assert accept(client, token).status_code == 400
    assert (
        client.post("/api/auth/login", json={"email": EMAIL, "password": PASSWORD}).status_code
        == 200
    )
    assert client.get("/api/auth/email").json()["verified"] is True


def test_public_signup_and_invite_issuance_are_not_available(client: TestClient) -> None:
    for path in ("/api/auth/signup", "/api/auth/invitations"):
        assert client.post(path, json={"email": EMAIL, "password": PASSWORD}).status_code in (
            404,
            405,
        )
    assert accept(client, "x" * 43).status_code == 400
    with SessionLocal() as db:
        assert db.scalar(select(func.count(User.id))) == 0


@pytest.mark.parametrize("state", ["expired", "revoked", "replaced"])
def test_expired_revoked_and_replaced_links_cannot_create_accounts(
    client: TestClient, messages: list[str], state: str
) -> None:
    token = invite(messages)
    if state == "expired":
        with SessionLocal() as db:
            db.get(Invitation, EMAIL).expires_at = datetime.now(UTC) - timedelta(seconds=1)
            db.commit()
    elif state == "revoked":
        cli.revoke_invite(Namespace(email=EMAIL.upper()))
        cli.revoke_invite(Namespace(email=EMAIL))  # Idempotent.
    else:
        replacement = invite(messages)
        assert replacement != token
    assert accept(client, token).status_code == 400
    with SessionLocal() as db:
        assert db.scalar(select(func.count(User.id))) == 0
    if state == "replaced":
        assert accept(client, replacement).status_code == 201


@pytest.mark.parametrize(
    "changes", [{"password": "short"}, {"display_name": "  "}, {"display_name": "x" * 161}]
)
def test_invalid_form_does_not_consume_invitation(
    client: TestClient, messages: list[str], changes: dict[str, str]
) -> None:
    token = invite(messages)
    assert accept(client, token, **changes).status_code == 422
    assert accept(client, token).status_code == 201


def test_concurrent_redemption_creates_exactly_one_account(messages: list[str]) -> None:
    token = invite(messages)

    def redeem():
        with TestClient(app) as client:
            return accept(client, token).status_code

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _: redeem(), range(2)))
    assert sorted(results) == [201, 400]
    with SessionLocal() as db:
        assert db.scalar(select(func.count(User.id))) == 1


def test_existing_accounts_cannot_be_overwritten(
    client: TestClient, messages: list[str], create_user: Callable[[str], User]
) -> None:
    token = invite(messages)
    existing = create_user(EMAIL)
    assert accept(client, token).status_code == 400
    with pytest.raises(SystemExit, match="already exists"):
        cli.invite_user(Namespace(email=EMAIL))
    assert len(messages) == 1
    with SessionLocal() as db:
        assert db.scalar(select(func.count(User.id))) == 1
        assert db.get(User, existing.id).password_hash == existing.password_hash
        assert db.get(User, existing.id).email_verified_at is None


@pytest.mark.parametrize(
    "error", [MailConfigurationError("unconfigured SMTP"), MailDeliveryError("delivery failed")]
)
def test_delivery_failure_is_reported_and_retry_works(
    client: TestClient, messages: list[str], monkeypatch: pytest.MonkeyPatch, error: Exception
) -> None:
    old_token = invite(messages)

    def fail(*_args: object) -> None:
        raise error

    with monkeypatch.context() as patch:
        patch.setattr(invitations, "send_email", fail)
        with pytest.raises(SystemExit, match=str(error)):
            cli.invite_user(Namespace(email=EMAIL))
    with SessionLocal() as db:
        assert db.get(Invitation, EMAIL) is None
        assert db.scalar(select(func.count(User.id))) == 0
    assert accept(client, old_token).status_code == 400
    assert accept(client, invite(messages)).status_code == 201


def test_smtp_does_not_hold_database_lock_or_resurrect_revoked_invite(
    client: TestClient, messages: list[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    def revoke_during_send(_to: str, _subject: str, body: str) -> None:
        messages.append(body)
        # A separate writer can revoke while delivery is in flight.
        cli.revoke_invite(Namespace(email=EMAIL))

    monkeypatch.setattr(invitations, "send_email", revoke_during_send)
    token = invite(messages)
    assert accept(client, token).status_code == 400


def test_redemption_rate_limit_does_not_lock_login(
    client: TestClient, messages: list[str], create_user: Callable[[str], User]
) -> None:
    create_user("legacy-user")
    for _ in range(10):
        assert accept(client, "x" * 43).status_code == 400
    token = invite(messages)
    assert accept(client, token).status_code == 429
    assert (
        client.post(
            "/api/auth/login", json={"email": "legacy-user", "password": "correct horse"}
        ).status_code
        == 200
    )
    with TestClient(app, client=("another-ip", 1234)) as other:
        assert accept(other, token).status_code == 201


def test_failed_older_delivery_does_not_revoke_newer_invitation(
    client: TestClient, messages: list[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    def replace_during_send(_to: str, _subject: str, body: str) -> None:
        messages.append(body)
        with monkeypatch.context() as patch:
            patch.setattr(
                invitations, "send_email", lambda _to, _subject, body: messages.append(body)
            )
            invite(messages)
        raise MailDeliveryError("older delivery failed")

    monkeypatch.setattr(invitations, "send_email", replace_during_send)
    with pytest.raises(SystemExit, match="older delivery failed"):
        invite(messages)
    match = re.search(r"token=([A-Za-z0-9_-]+)", messages[-1])
    assert match is not None
    assert accept(client, match.group(1)).status_code == 201


def test_operator_commands_and_invalid_email(messages: list[str]) -> None:
    parser = cli.build_parser()
    args = parser.parse_args(["invite-user", "invalid"])
    with pytest.raises(SystemExit, match="valid email"):
        args.handler(args)
    args = parser.parse_args(["revoke-invite", "invalid"])
    with pytest.raises(SystemExit, match="valid email"):
        args.handler(args)
    assert not messages
