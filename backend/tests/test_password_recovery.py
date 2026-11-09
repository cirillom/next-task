import re
from argparse import Namespace
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta

import pytest
from app import cli
from app.auth.security import hash_password, hash_token
from app.database import SessionLocal
from app.main import app
from app.models import EmailVerification, PasswordReset, User, UserSession
from app.routes import auth
from app.routes import password_recovery as recovery
from app.services.mail import MailConfigurationError, MailDeliveryError
from fastapi.testclient import TestClient
from sqlalchemy import func, select

EMAIL = "owner@example.com"
NEW_PASSWORD = "a new secure password"


@pytest.fixture
def messages(monkeypatch: pytest.MonkeyPatch) -> list[tuple[str, str, str]]:
    sent: list[tuple[str, str, str]] = []
    for module in (recovery, auth):
        monkeypatch.setattr(module, "public_app_url", lambda: "https://tasks.example.com")
        monkeypatch.setattr(module, "send_email", lambda *args: sent.append(args))
    return sent


@pytest.fixture
def owner(logged_in_client: Callable[[str], TestClient]) -> TestClient:
    client = logged_in_client(EMAIL)
    with SessionLocal() as db:
        user = db.scalar(select(User).where(User.email == EMAIL))
        user.email_verified_at = datetime.now(UTC)
        db.commit()
    return client


def request_link(client: TestClient, email: str = EMAIL):
    return client.post("/api/auth/forgot-password", json={"email": email})


def token_from(messages: list[tuple[str, str, str]]) -> str:
    match = re.search(r"token=([A-Za-z0-9_-]+)", messages[-1][2])
    assert match is not None
    return match.group(1)


def reset(client: TestClient, token: str, password: str = NEW_PASSWORD):
    return client.post("/api/auth/reset-password", json={"token": token, "new_password": password})


def test_request_is_generic_and_only_verified_accounts_receive_links(
    owner: TestClient,
    create_user: Callable[[str], User],
    messages: list[tuple[str, str, str]],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    create_user("unverified@example.com")
    create_user("legacy-user")
    responses = [
        request_link(owner, email)
        for email in (EMAIL.upper(), "missing@example.com", "unverified@example.com", "legacy-user")
    ]
    assert all(response.status_code == 202 for response in responses)
    assert all(response.json() == {"message": recovery.RESET_REQUESTED} for response in responses)
    assert len(messages) == 1
    assert messages[0][0] == EMAIL
    assert "https://tasks.example.com/#/reset-password?token=" in messages[0][2]
    assert "30 minutes" in messages[0][2]
    assert owner.get("/api/auth/me").status_code == 200

    def fail(*_args: object) -> None:
        raise MailConfigurationError("unconfigured SMTP")

    monkeypatch.setattr(recovery, "send_email", fail)
    assert request_link(owner).json() == responses[0].json()
    assert owner.get("/api/auth/me").status_code == 200


def test_reset_revokes_sessions_and_tokens_without_signing_in(
    owner: TestClient, messages: list[tuple[str, str, str]]
) -> None:
    task = owner.post("/api/tasks", json={"title": "Keep this task"}).json()
    second = TestClient(app)
    assert (
        second.post(
            "/api/auth/login", json={"email": EMAIL, "password": "correct horse"}
        ).status_code
        == 200
    )
    assert request_link(owner).status_code == 202
    token = token_from(messages)
    with SessionLocal() as db:
        pending = db.scalar(select(PasswordReset))
        assert pending.token_hash == hash_token(token)
        assert token not in pending.token_hash
        assert pending.email == EMAIL
        db.add(
            EmailVerification(
                user_id=pending.user_id,
                email="attacker@example.com",
                token_hash=hash_token("x" * 32),
                expires_at=datetime.now(UTC) + timedelta(hours=1),
            )
        )
        db.commit()

    public = TestClient(app)
    for _ in range(5):
        assert public.post(
            "/api/auth/login", json={"email": EMAIL, "password": "wrong password"}
        ).status_code == 401
    response = reset(public, token)
    assert response.status_code == 200
    assert public.get("/api/auth/me").status_code == 401
    assert owner.get("/api/auth/me").status_code == 401
    assert second.get("/api/auth/me").status_code == 401
    with SessionLocal() as db:
        assert db.scalar(select(func.count()).select_from(UserSession)) == 0
        assert db.scalar(select(PasswordReset)) is None
        assert db.scalar(select(EmailVerification)) is None
    assert reset(public, token).status_code == 400
    assert "password was changed" in messages[-1][1]
    assert NEW_PASSWORD not in messages[-1][2]
    assert (
        public.post(
            "/api/auth/login", json={"email": EMAIL, "password": "correct horse"}
        ).status_code
        == 401
    )
    assert (
        public.post("/api/auth/login", json={"email": EMAIL, "password": NEW_PASSWORD}).status_code
        == 200
    )
    assert public.get(f"/api/tasks/{task['id']}").json()["title"] == "Keep this task"


def test_resend_supersedes_old_link_but_failed_delivery_preserves_it(
    owner: TestClient, messages: list[tuple[str, str, str]], monkeypatch: pytest.MonkeyPatch
) -> None:
    request_link(owner)
    old = token_from(messages)
    original_sender = recovery.send_email

    def fail(*_args: object) -> None:
        raise MailDeliveryError("failed")

    monkeypatch.setattr(recovery, "send_email", fail)
    assert request_link(owner).status_code == 202
    with SessionLocal() as db:
        assert db.scalar(select(PasswordReset)).token_hash == hash_token(old)
    monkeypatch.setattr(recovery, "send_email", original_sender)
    request_link(owner)
    new = token_from(messages)
    assert new != old
    assert reset(owner, old).status_code == 400
    with SessionLocal() as db:
        db.scalar(select(PasswordReset)).expires_at = datetime.now(UTC) - timedelta(seconds=1)
        db.commit()
    assert reset(owner, new).status_code == 400
    assert owner.get("/api/auth/me").status_code == 200


def test_smtp_starts_after_the_generic_response_is_sent(
    owner: TestClient, messages: list[tuple[str, str, str]], monkeypatch: pytest.MonkeyPatch
) -> None:
    events: list[str] = []
    monkeypatch.setattr(recovery, "send_email", lambda *_args: events.append("smtp"))

    async def traced_app(scope, receive, send):
        async def traced_send(message):
            if message["type"] == "http.response.body" and not message.get("more_body", False):
                events.append("response")
            await send(message)

        await app(scope, receive, traced_send)

    with TestClient(traced_app) as client:
        assert request_link(client).status_code == 202
    assert events == ["response", "smtp"]


def test_request_limits_persist_and_do_not_lock_sign_in(
    owner: TestClient, messages: list[tuple[str, str, str]], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(recovery, "RESET_EMAIL_LIMIT", 1)
    monkeypatch.setattr(recovery, "RESET_IP_LIMIT", 3)
    first = request_link(owner)
    assert request_link(owner).json() == first.json()
    assert len(messages) == 1
    assert request_link(owner, "unknown@example.com").json() == first.json()
    assert request_link(TestClient(app), "another@example.com").status_code == 429
    other_ip = TestClient(app, client=("203.0.113.99", 50000))
    assert request_link(other_ip).json() == first.json()
    assert len(messages) == 1
    assert (
        other_ip.post(
            "/api/auth/login", json={"email": EMAIL, "password": "correct horse"}
        ).status_code
        == 200
    )


def test_token_attempts_are_limited_without_disabling_the_link(
    owner: TestClient, messages: list[tuple[str, str, str]], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(recovery, "RESET_TOKEN_LIMIT", 2)
    request_link(owner)
    token = token_from(messages)
    assert reset(owner, "x" * 43).status_code == 400
    assert reset(owner, "y" * 43).status_code == 400
    assert reset(owner, token).status_code == 429
    other_ip = TestClient(app, client=("203.0.113.99", 50000))
    assert reset(other_ip, token).status_code == 200


@pytest.mark.parametrize("action", ["password", "operator", "email"])
def test_credential_changes_invalidate_reset_links(
    action: str,
    owner: TestClient,
    messages: list[tuple[str, str, str]],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    request_link(owner)
    token = token_from(messages)
    if action == "password":
        assert (
            owner.post(
                "/api/auth/change-password",
                json={
                    "current_password": "correct horse",
                    "new_password": NEW_PASSWORD,
                },
            ).status_code
            == 200
        )
    elif action == "operator":
        monkeypatch.setattr(cli, "read_password", lambda *_args: NEW_PASSWORD)
        cli.reset_password(Namespace(email=EMAIL, password_stdin=True))
    else:
        assert (
            owner.post(
                "/api/auth/email",
                json={
                    "email": "new@example.com",
                    "current_password": "correct horse",
                },
            ).status_code
            == 200
        )
        assert (
            owner.post("/api/auth/email/verify", json={"token": token_from(messages)}).status_code
            == 200
        )
    assert reset(TestClient(app), token).status_code == 400


def test_password_change_during_delivery_cannot_issue_a_working_old_link(
    owner: TestClient, messages: list[tuple[str, str, str]], monkeypatch: pytest.MonkeyPatch
) -> None:
    def send_and_change_password(*args: str) -> None:
        messages.append(args)
        with SessionLocal() as db:
            user = db.scalar(select(User).where(User.email == EMAIL))
            user.password_hash = hash_password("changed while SMTP was in flight")
            db.commit()

    monkeypatch.setattr(recovery, "send_email", send_and_change_password)
    assert request_link(owner).status_code == 202
    assert reset(owner, token_from(messages)).status_code == 400


def test_concurrent_redemption_succeeds_only_once(
    owner: TestClient, messages: list[tuple[str, str, str]]
) -> None:
    request_link(owner)
    token = token_from(messages)
    with ThreadPoolExecutor(max_workers=2) as pool:
        outcomes = list(pool.map(lambda _: reset(TestClient(app), token).status_code, range(2)))
    assert sorted(outcomes) == [200, 400]


def test_password_policy_and_notification_failure(
    owner: TestClient, messages: list[tuple[str, str, str]], monkeypatch: pytest.MonkeyPatch
) -> None:
    request_link(owner)
    token = token_from(messages)
    assert reset(owner, token, "short").status_code == 422

    def fail(*_args: object) -> None:
        raise MailDeliveryError("failed")

    monkeypatch.setattr(recovery, "send_email", fail)
    assert reset(owner, token).status_code == 200
    assert (
        owner.post("/api/auth/login", json={"email": EMAIL, "password": NEW_PASSWORD}).status_code
        == 200
    )
