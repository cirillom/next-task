import subprocess
import sys
from argparse import Namespace
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from app.auth.rate_limit import (
    IP_BURST_WINDOW,
    LOCKOUT,
    account_key,
    ip_key,
    password_change_key,
    record_attempt,
    reserve_window_attempt,
)
from app.cli import reset_password
from app.database import SessionLocal
from app.main import app
from app.models import AuthLoginAttempt, AuthRateLimit, User
from app.routes import auth as auth_routes
from fastapi.testclient import TestClient
from sqlalchemy import select
from uvicorn.middleware.proxy_headers import ProxyHeadersMiddleware


class Clock:
    current = datetime(2026, 10, 19, 12, tzinfo=UTC)

    @classmethod
    def now(cls, _timezone: object) -> datetime:
        return cls.current


@pytest.fixture
def frozen_auth_clock(monkeypatch: pytest.MonkeyPatch) -> type[Clock]:
    Clock.current = datetime(2026, 10, 19, 12, tzinfo=UTC)
    monkeypatch.setattr(auth_routes, "datetime", Clock)
    return Clock


def login(client: TestClient, email: str, password: str, **kwargs: object):
    return client.post("/api/auth/login", json={"email": email, "password": password}, **kwargs)


def test_password_is_hashed_and_login_sets_http_only_cookie(
    client: TestClient, create_user: Callable[[str, str, str], User]
) -> None:
    created = create_user("person@example.com")
    assert created.password_hash.startswith("$argon2id$")
    assert "correct horse" not in created.password_hash

    denied = client.post(
        "/api/auth/login", json={"email": "Person@Example.com", "password": "wrong password"}
    )
    assert denied.status_code == 401

    response = client.post(
        "/api/auth/login",
        json={"email": "person@example.com", "password": "correct horse"},
    )
    assert response.status_code == 200
    assert "HttpOnly" in response.headers["set-cookie"]
    assert response.json()["email"] == "person@example.com"
    assert client.get("/api/auth/me").status_code == 200


def test_signup_accepts_username_and_logs_user_in(client: TestClient) -> None:
    response = client.post(
        "/api/auth/signup",
        json={"identifier": "  NewUser  ", "password": "a secure password"},
    )
    assert response.status_code == 201
    assert "HttpOnly" in response.headers["set-cookie"]
    assert response.json()["email"] == "newuser"
    assert response.json()["display_name"] == "newuser"
    assert client.get("/api/auth/me").status_code == 200

    with SessionLocal() as db:
        user = db.scalar(select(User).where(User.email == "newuser"))
        assert user is not None
        assert user.password_hash.startswith("$argon2id$")
        assert "a secure password" not in user.password_hash

    client.post("/api/auth/logout")
    login = client.post(
        "/api/auth/login",
        json={"email": "NEWUSER", "password": "a secure password"},
    )
    assert login.status_code == 200


def test_signup_accepts_email_and_rejects_duplicates_and_short_passwords(
    client: TestClient,
) -> None:
    created = client.post(
        "/api/auth/signup",
        json={"identifier": "Person@Example.com", "password": "a secure password"},
    )
    assert created.status_code == 201
    assert created.json()["email"] == "person@example.com"
    assert created.json()["display_name"] == "person"

    duplicate = client.post(
        "/api/auth/signup",
        json={"identifier": "person@example.com", "password": "another secure password"},
    )
    assert duplicate.status_code == 409
    assert duplicate.json()["detail"] == "That username or email is already in use"

    short = client.post(
        "/api/auth/signup",
        json={"identifier": "another-user", "password": "short"},
    )
    assert short.status_code == 422


def test_password_change_revokes_other_sessions(
    create_user: Callable[[str, str, str], User],
) -> None:
    create_user("person@example.com")
    first = TestClient(app)
    second = TestClient(app)
    for test_client in (first, second):
        assert (
            test_client.post(
                "/api/auth/login",
                json={"email": "person@example.com", "password": "correct horse"},
            ).status_code
            == 200
        )

    changed = first.post(
        "/api/auth/change-password",
        json={"current_password": "correct horse", "new_password": "a new secure password"},
    )
    assert changed.status_code == 200
    assert first.get("/api/auth/me").status_code == 200
    assert second.get("/api/auth/me").status_code == 401


def test_five_failures_lock_account_temporarily_and_success_resets_it(
    client: TestClient,
    create_user: Callable[[str, str, str], User],
    frozen_auth_clock: type[Clock],
) -> None:
    user = create_user("person@example.com")
    for _ in range(5):
        denied = login(client, user.email, "wrong password")
        assert denied.status_code == 401
        assert denied.json()["detail"] == "Invalid username/email or password"
    assert login(client, user.email, "correct horse").status_code == 401

    with SessionLocal() as db:
        record = db.get(AuthRateLimit, account_key(user.id))
        assert record is not None
        assert record.locked_until is not None
        assert (
            len(
                db.scalars(
                    select(AuthLoginAttempt).where(AuthLoginAttempt.key == account_key(user.id))
                ).all()
            )
            == 5
        )

    frozen_auth_clock.current += timedelta(minutes=15, seconds=1)
    assert login(client, user.email, "correct horse").status_code == 200
    with SessionLocal() as db:
        assert db.get(AuthRateLimit, account_key(user.id)) is None
    client.post("/api/auth/logout")
    assert login(client, user.email, "wrong password").status_code == 401
    assert login(client, user.email, "correct horse").status_code == 200


def test_lockout_survives_new_app_client_and_is_shared_across_ips(
    client: TestClient,
    create_user: Callable[[str, str, str], User],
) -> None:
    create_user("person@example.com")
    for _ in range(5):
        assert login(client, "person@example.com", "wrong password").status_code == 401

    with TestClient(app, client=("203.0.113.50", 50000)) as restarted_client:
        assert login(restarted_client, "person@example.com", "correct horse").status_code == 401

    fresh_process = subprocess.run(
        [
            sys.executable,
            "-c",
            "import sys; sys.path.insert(0, 'backend'); "
            "from fastapi.testclient import TestClient; from app.main import app; "
            "print(TestClient(app).post('/api/auth/login', "
            "json={'email':'person@example.com','password':'correct horse'}).status_code)",
        ],
        cwd=Path(__file__).resolve().parents[2],
        capture_output=True,
        text=True,
        check=True,
    )
    assert fresh_process.stdout.strip() == "401"


def test_admin_password_reset_clears_sliding_account_lock(
    client: TestClient,
    create_user: Callable[[str, str, str], User],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    create_user("person@example.com")
    for _ in range(5):
        assert login(client, "person@example.com", "wrong password").status_code == 401
    monkeypatch.setattr("app.cli.read_password", lambda *_args: "replacement password")
    reset_password(Namespace(email="person@example.com", password_stdin=True))
    assert login(client, "person@example.com", "replacement password").status_code == 200


def test_account_failure_observation_window_resets(
    client: TestClient,
    create_user: Callable[[str, str, str], User],
    frozen_auth_clock: type[Clock],
) -> None:
    create_user("person@example.com")
    for _ in range(4):
        assert login(client, "person@example.com", "wrong password").status_code == 401
    frozen_auth_clock.current += timedelta(minutes=15, seconds=1)
    assert login(client, "person@example.com", "wrong password").status_code == 401
    assert login(client, "person@example.com", "correct horse").status_code == 200


def test_account_failure_window_slides_across_first_attempt_boundary(
    client: TestClient,
    create_user: Callable[[str, str, str], User],
    frozen_auth_clock: type[Clock],
) -> None:
    create_user("person@example.com")
    assert login(client, "person@example.com", "wrong password").status_code == 401
    frozen_auth_clock.current += timedelta(minutes=10)
    for _ in range(3):
        assert login(client, "person@example.com", "wrong password").status_code == 401
    frozen_auth_clock.current += timedelta(minutes=5, seconds=1)
    assert login(client, "person@example.com", "wrong password").status_code == 401
    assert login(client, "person@example.com", "wrong password").status_code == 401
    assert login(client, "person@example.com", "correct horse").status_code == 401


def test_correct_fifth_attempt_succeeds_and_clears_account_limit(
    client: TestClient,
    create_user: Callable[[str, str, str], User],
) -> None:
    user = create_user("person@example.com")
    for _ in range(4):
        assert login(client, user.email, "wrong password").status_code == 401
    assert login(client, user.email, "correct horse").status_code == 200
    with SessionLocal() as db:
        assert db.get(AuthRateLimit, account_key(user.id)) is None


def test_ip_limit_applies_before_expensive_unknown_account_check(
    client: TestClient,
    create_user: Callable[[str, str, str], User],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(auth_routes, "IP_FAILURE_LIMIT", 2)
    create_user("person@example.com")
    assert login(client, "missing@example.com", "wrong password").status_code == 401
    assert login(client, "another@example.com", "wrong password").status_code == 401
    assert login(client, "person@example.com", "correct horse").status_code == 429
    with SessionLocal() as db:
        records = db.scalars(
            select(AuthLoginAttempt).where(AuthLoginAttempt.key == ip_key("testclient"))
        ).all()
        assert len(records) == 2

    with TestClient(app) as restarted_client:
        assert login(restarted_client, "person@example.com", "correct horse").status_code == 429

    with TestClient(app, client=("203.0.113.51", 50000)) as other_ip:
        assert login(other_ip, "person@example.com", "correct horse").status_code == 200


def test_ip_limit_expires_at_end_of_window(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    frozen_auth_clock: type[Clock],
) -> None:
    monkeypatch.setattr(auth_routes, "IP_FAILURE_LIMIT", 1)
    assert login(client, "missing@example.com", "wrong password").status_code == 401
    assert login(client, "missing@example.com", "wrong password").status_code == 429
    frozen_auth_clock.current += timedelta(minutes=15, seconds=1)
    assert login(client, "missing@example.com", "wrong password").status_code == 401


def test_successful_logins_do_not_consume_shared_ip_failure_limit(
    client: TestClient,
    create_user: Callable[[str, str, str], User],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(auth_routes, "IP_FAILURE_LIMIT", 2)
    monkeypatch.setattr(auth_routes, "IP_BURST_LIMIT", 20)
    create_user("first@example.com")
    create_user("second@example.com")
    for _ in range(5):
        assert login(client, "first@example.com", "correct horse").status_code == 200
        assert login(client, "second@example.com", "correct horse").status_code == 200
    with SessionLocal() as db:
        assert (
            db.scalars(
                select(AuthLoginAttempt).where(AuthLoginAttempt.key == ip_key("testclient"))
            ).all()
            == []
        )
    assert login(client, "missing@example.com", "wrong password").status_code == 401
    assert login(client, "another@example.com", "wrong password").status_code == 401
    assert login(client, "first@example.com", "correct horse").status_code == 429


def test_raw_login_burst_stops_before_password_check_and_refills(
    client: TestClient,
    create_user: Callable[[str, str, str], User],
    monkeypatch: pytest.MonkeyPatch,
    frozen_auth_clock: type[Clock],
) -> None:
    monkeypatch.setattr(auth_routes, "IP_BURST_LIMIT", 2)
    create_user("person@example.com")
    assert login(client, "person@example.com", "correct horse").status_code == 200
    assert login(client, "person@example.com", "correct horse").status_code == 200
    assert login(client, "person@example.com", "correct horse").status_code == 429
    frozen_auth_clock.current += IP_BURST_WINDOW + timedelta(seconds=1)
    assert login(client, "person@example.com", "correct horse").status_code == 200


def test_ip_failure_window_slides_with_each_failure(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    frozen_auth_clock: type[Clock],
) -> None:
    monkeypatch.setattr(auth_routes, "IP_FAILURE_LIMIT", 2)
    assert login(client, "missing@example.com", "wrong password").status_code == 401
    frozen_auth_clock.current += timedelta(minutes=10)
    assert login(client, "other@example.com", "wrong password").status_code == 401
    frozen_auth_clock.current += timedelta(minutes=5, seconds=1)
    assert login(client, "third@example.com", "wrong password").status_code == 401
    assert login(client, "fourth@example.com", "wrong password").status_code == 429


def test_unknown_account_uses_dummy_hash_and_untrusted_header_cannot_change_ip(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    checked_hashes: list[str] = []

    def record_hash(password_hash: str, _password: str) -> bool:
        checked_hashes.append(password_hash)
        return False

    monkeypatch.setattr(auth_routes, "verify_password", record_hash)
    monkeypatch.setattr(auth_routes, "IP_FAILURE_LIMIT", 1)
    assert (
        login(
            client, "missing@example.com", "guess", headers={"X-Forwarded-For": "198.51.100.1"}
        ).status_code
        == 401
    )
    assert checked_hashes == [auth_routes.DUMMY_PASSWORD_HASH]
    assert (
        login(
            client, "other@example.com", "guess", headers={"X-Forwarded-For": "198.51.100.2"}
        ).status_code
        == 429
    )
    assert checked_hashes == [auth_routes.DUMMY_PASSWORD_HASH]


def test_concurrent_window_reservations_do_not_exceed_limit() -> None:
    now = datetime.now(UTC)
    key = ip_key("198.51.100.20")

    def reserve() -> int | None:
        with SessionLocal() as db:
            return reserve_window_attempt(db, key, now, window=timedelta(minutes=15), limit=5)

    with ThreadPoolExecutor(max_workers=8) as workers:
        reservations = list(workers.map(lambda _: reserve(), range(8)))
    assert len([reservation for reservation in reservations if reservation is not None]) == 5
    with SessionLocal() as db:
        assert (
            len(db.scalars(select(AuthLoginAttempt).where(AuthLoginAttempt.key == key)).all()) == 5
        )


def test_trusted_proxy_uses_forwarded_client_ip_for_login_limit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(auth_routes, "IP_FAILURE_LIMIT", 1)
    behind_proxy = ProxyHeadersMiddleware(app, trusted_hosts=["10.0.0.2"])
    with TestClient(behind_proxy, client=("10.0.0.2", 50000)) as proxied:
        assert (
            login(
                proxied, "missing@example.com", "guess", headers={"X-Forwarded-For": "198.51.100.1"}
            ).status_code
            == 401
        )
        assert (
            login(
                proxied, "missing@example.com", "guess", headers={"X-Forwarded-For": "198.51.100.2"}
            ).status_code
            == 401
        )
        assert (
            login(
                proxied, "missing@example.com", "guess", headers={"X-Forwarded-For": "198.51.100.1"}
            ).status_code
            == 429
        )

    with TestClient(behind_proxy, client=("203.0.113.99", 50000)) as untrusted:
        assert (
            login(
                untrusted, "missing@example.com", "guess", headers={"X-Forwarded-For": "192.0.2.1"}
            ).status_code
            == 401
        )
        assert (
            login(
                untrusted, "missing@example.com", "guess", headers={"X-Forwarded-For": "192.0.2.2"}
            ).status_code
            == 429
        )


def test_password_change_failures_lock_temporarily(
    logged_in_client: Callable[[str], TestClient],
    frozen_auth_clock: type[Clock],
) -> None:
    client = logged_in_client("person@example.com")
    for _ in range(5):
        denied = client.post(
            "/api/auth/change-password",
            json={"current_password": "wrong password", "new_password": "a new secure password"},
        )
        assert denied.status_code == 400
        assert denied.json()["detail"] == "Could not change password"
    correct = {"current_password": "correct horse", "new_password": "a new secure password"}
    assert client.post("/api/auth/change-password", json=correct).status_code == 400
    with SessionLocal() as db:
        user = db.scalar(select(User).where(User.email == "person@example.com"))
        assert user is not None
        assert db.get(AuthRateLimit, password_change_key(user.id)) is not None

    frozen_auth_clock.current += timedelta(minutes=15, seconds=1)
    assert client.post("/api/auth/change-password", json=correct).status_code == 200


def test_parallel_attempts_share_one_database_counter() -> None:
    now = datetime.now(UTC)
    key = account_key(999)

    def attempt() -> int:
        with SessionLocal() as db:
            return record_attempt(db, key, now, limit=5, lockout=LOCKOUT)

    with ThreadPoolExecutor(max_workers=8) as workers:
        counts = list(workers.map(lambda _: attempt(), range(8)))
    assert sorted(counts) == list(range(1, 9))
