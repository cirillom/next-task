import re
import smtplib
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from threading import Event

import pytest
from app.cli import build_parser
from app.config import Settings
from app.database import SessionLocal
from app.main import app
from app.models import AuthLoginAttempt, EmailVerification, User
from app.routes import auth as auth_routes
from app.services import mail
from fastapi.testclient import TestClient
from pydantic import SecretStr
from sqlalchemy import select, update


def sent_token(messages: list[str], index: int = -1) -> str:
    match = re.search(r"token=([A-Za-z0-9_-]+)", messages[index])
    assert match is not None
    return match.group(1)


def request_email(client: TestClient, email: str, password: str = "correct horse"):
    return client.post(
        "/api/auth/contact-email",
        json={"email": email, "current_password": password},
    )


def age_mail_attempts() -> None:
    with SessionLocal() as db:
        db.execute(
            update(AuthLoginAttempt)
            .where(AuthLoginAttempt.key.like("contact-email-send:%"))
            .values(created_at=datetime.now(UTC) - timedelta(minutes=2))
        )
        db.commit()


def test_legacy_login_and_one_use_verification(
    logged_in_client: Callable[[str], TestClient], monkeypatch: pytest.MonkeyPatch
) -> None:
    client = logged_in_client("legacy-user")
    messages: list[str] = []
    monkeypatch.setattr(auth_routes, "public_app_url", lambda: "https://tasks.example.com")
    monkeypatch.setattr(
        auth_routes, "send_email", lambda _to, _subject, body: messages.append(body)
    )

    assert client.get("/api/auth/contact-email").json()["verified_email"] is None
    assert request_email(client, "Person@Example.com", "wrong password").status_code == 400
    assert not messages
    response = request_email(client, " Person@Example.com ")
    assert response.status_code == 200, response.text
    assert response.json()["pending_email"] == "person@example.com"
    assert response.json()["verified_email"] is None
    token = sent_token(messages)
    with SessionLocal() as db:
        pending = db.scalar(select(EmailVerification))
        assert pending is not None
        assert token not in pending.token_hash
        assert db.scalar(select(User).where(User.email == "legacy-user")).contact_email is None

    verified = client.post("/api/auth/contact-email/verify", json={"token": token})
    assert verified.status_code == 200
    assert client.get("/api/auth/contact-email").json()["verified_email"] == "person@example.com"
    assert client.post("/api/auth/contact-email/verify", json={"token": token}).status_code == 400
    client.post("/api/auth/logout")
    assert (
        client.post(
            "/api/auth/login", json={"email": "LEGACY-USER", "password": "correct horse"}
        ).status_code
        == 200
    )
    assert (
        client.post(
            "/api/auth/login", json={"email": "person@example.com", "password": "correct horse"}
        ).status_code
        == 401
    )


def test_resend_expiry_and_failed_delivery_preserve_verified_address(
    logged_in_client: Callable[[str], TestClient], monkeypatch: pytest.MonkeyPatch
) -> None:
    client = logged_in_client("owner@example.com")
    messages: list[str] = []
    monkeypatch.setattr(auth_routes, "public_app_url", lambda: "https://tasks.example.com")
    monkeypatch.setattr(
        auth_routes, "send_email", lambda _to, _subject, body: messages.append(body)
    )
    assert request_email(client, "old@example.com").status_code == 200
    assert (
        client.post(
            "/api/auth/contact-email/verify", json={"token": sent_token(messages)}
        ).status_code
        == 200
    )

    age_mail_attempts()
    assert request_email(client, "new@example.com").status_code == 200
    first_new_token = sent_token(messages)
    assert client.get("/api/auth/contact-email").json()["verified_email"] == "old@example.com"
    assert request_email(client, "new@example.com").status_code == 429
    age_mail_attempts()

    def fail_delivery(_to: str, _subject: str, _body: str) -> None:
        raise mail.MailDeliveryError("Email could not be sent. Try again later.")

    monkeypatch.setattr(auth_routes, "send_email", fail_delivery)
    assert request_email(client, "new@example.com").status_code == 503
    assert client.get("/api/auth/contact-email").json()["verified_email"] == "old@example.com"

    monkeypatch.setattr(
        auth_routes, "send_email", lambda _to, _subject, body: messages.append(body)
    )
    assert request_email(client, "new@example.com").status_code == 200
    second_new_token = sent_token(messages)
    assert second_new_token != first_new_token
    assert (
        client.post("/api/auth/contact-email/verify", json={"token": first_new_token}).status_code
        == 400
    )
    with SessionLocal() as db:
        pending = db.scalar(select(EmailVerification))
        pending.expires_at = datetime.now(UTC) - timedelta(seconds=1)
        db.commit()
    assert (
        client.post("/api/auth/contact-email/verify", json={"token": second_new_token}).status_code
        == 400
    )
    assert client.get("/api/auth/contact-email").json()["verified_email"] == "old@example.com"
    age_mail_attempts()
    assert request_email(client, "new@example.com").status_code == 200
    assert (
        client.post(
            "/api/auth/contact-email/verify", json={"token": sent_token(messages)}
        ).status_code
        == 200
    )
    assert client.get("/api/auth/contact-email").json()["verified_email"] == "new@example.com"


def test_mail_outage_does_not_hold_database_write_lock(
    logged_in_client: Callable[[str], TestClient],
    create_user: Callable[[str, str, str], User],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = logged_in_client("owner")
    create_user("other")
    entered = Event()
    release = Event()
    monkeypatch.setattr(auth_routes, "public_app_url", lambda: "https://tasks.example.com")

    def slow_failure(_to: str, _subject: str, _body: str) -> None:
        entered.set()
        assert release.wait(10)
        raise mail.MailDeliveryError("Email could not be sent. Try again later.")

    monkeypatch.setattr(auth_routes, "send_email", slow_failure)
    with ThreadPoolExecutor(max_workers=1) as executor:
        future = executor.submit(request_email, client, "new@example.com")
        assert entered.wait(5)
        try:
            with TestClient(app) as another:
                response = another.post(
                    "/api/auth/login", json={"email": "other", "password": "correct horse"}
                )
            assert response.status_code == 200
        finally:
            release.set()
        assert future.result().status_code == 503


def test_contact_email_collision_and_signup_protection(
    logged_in_client: Callable[[str], TestClient],
    create_user: Callable[[str, str, str], User],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = logged_in_client("first")
    create_user("claimed@example.com")
    messages: list[str] = []
    monkeypatch.setattr(auth_routes, "public_app_url", lambda: "https://tasks.example.com")
    monkeypatch.setattr(
        auth_routes, "send_email", lambda _to, _subject, body: messages.append(body)
    )
    assert request_email(client, "claimed@example.com").status_code == 409
    assert not messages

    assert request_email(client, "shared@example.com").status_code == 200
    first_token = sent_token(messages)
    second = logged_in_client("second")
    assert request_email(second, "shared@example.com").status_code == 200
    second_token = sent_token(messages)
    assert (
        second.post("/api/auth/contact-email/verify", json={"token": second_token}).status_code
        == 200
    )
    assert (
        client.post("/api/auth/contact-email/verify", json={"token": first_token}).status_code
        == 409
    )
    assert client.get("/api/auth/contact-email").json()["verified_email"] is None
    assert (
        client.post(
            "/api/auth/signup",
            json={"identifier": "shared@example.com", "password": "a secure password"},
        ).status_code
        == 409
    )


def test_mail_service_uses_starttls_and_reports_delivery_errors(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    events: list[object] = []
    settings = Settings(
        smtp_host="smtp.example.com",
        smtp_port=587,
        smtp_security="starttls",
        smtp_username="account",
        smtp_password=SecretStr("app-secret"),
        smtp_from_email="tasks@example.com",
        public_app_url="https://tasks.example.com",
    )
    monkeypatch.setattr(mail, "get_settings", lambda: settings)

    class FakeSMTP:
        def __init__(self, host: str, port: int, timeout: int) -> None:
            events.append((host, port, timeout))

        def __enter__(self):
            return self

        def __exit__(self, *_args: object) -> None:
            pass

        def starttls(self, *, context: object) -> None:
            events.append("starttls")

        def login(self, username: str, password: str) -> None:
            events.append((username, password))

        def send_message(self, message: object) -> None:
            events.append(message)

    monkeypatch.setattr(mail.smtplib, "SMTP", FakeSMTP)
    mail.send_email("person@example.com", "Test", "Body")
    assert events[:3] == [("smtp.example.com", 587, 15), "starttls", ("account", "app-secret")]
    assert events[3]["To"] == "person@example.com"
    assert mail.public_app_url() == "https://tasks.example.com"
    settings.public_app_url = "http://tasks.example.com"
    with pytest.raises(mail.MailConfigurationError):
        mail.public_app_url()
    settings.public_app_url = "https://tasks.example.com:99999"
    with pytest.raises(mail.MailConfigurationError):
        mail.public_app_url()

    class FakeSSL(FakeSMTP):
        def __init__(self, host: str, port: int, timeout: int, context: object) -> None:
            events.append((host, port, timeout, "ssl"))

    settings.smtp_security = "ssl"
    settings.smtp_port = 465
    events.clear()
    monkeypatch.setattr(mail.smtplib, "SMTP_SSL", FakeSSL)
    mail.send_email("person@example.com", "Test", "Body")
    assert events[0] == ("smtp.example.com", 465, 15, "ssl")
    assert "starttls" not in events

    def refuse(_message: object) -> None:
        raise smtplib.SMTPException("refused")

    monkeypatch.setattr(FakeSMTP, "send_message", lambda self, message: refuse(message))
    with pytest.raises(mail.MailDeliveryError):
        mail.send_email("person@example.com", "Test", "Body")


def test_operator_test_email_command_uses_mail_service(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    from app import cli

    sent: list[tuple[str, str]] = []
    monkeypatch.setattr(cli, "send_email", lambda to, subject, _body: sent.append((to, subject)))
    args = build_parser().parse_args(["test-email", "Person@Example.com"])
    args.handler(args)
    assert sent == [("person@example.com", "Next Task SMTP test")]
    assert "SMTP server accepted" in capsys.readouterr().out
