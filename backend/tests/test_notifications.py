import base64
import json
import socket
import struct
from collections.abc import Callable
from datetime import UTC, date, datetime, timedelta

import httpx
import pytest
from app import cli
from app.config import get_settings
from app.database import SessionLocal
from app.i18n import translate
from app.models import PushSubscription, Task, TaskBlock, User
from app.routes import notifications as notifications_route
from app.services import notifications as notifications_service
from app.services import webpush
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives.asymmetric.utils import encode_dss_signature
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.hkdf import HKDF
from fastapi.testclient import TestClient
from sqlalchemy import select


def _b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def _b64url_decode(value: str) -> bytes:
    return base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))


def _make_ua_subscription() -> tuple[ec.EllipticCurvePrivateKey, str, str]:
    ua_private = ec.generate_private_key(ec.SECP256R1())
    ua_pub = ua_private.public_key().public_bytes(
        serialization.Encoding.X962, serialization.PublicFormat.UncompressedPoint
    )
    auth = b"0123456789abcdef"
    return ua_private, _b64url(ua_pub), _b64url(auth)


def _decrypt_aes128gcm(
    body: bytes, ua_private: ec.EllipticCurvePrivateKey, auth_b64: str
) -> bytes:
    salt = body[:16]
    record_size, id_len = struct.unpack("!IB", body[16:21])
    assert record_size == 4096
    assert id_len == 65
    as_pub_bytes = body[21 : 21 + id_len]
    ciphertext = body[21 + id_len :]
    ua_pub_bytes = ua_private.public_key().public_bytes(
        serialization.Encoding.X962, serialization.PublicFormat.UncompressedPoint
    )
    as_pub = ec.EllipticCurvePublicKey.from_encoded_point(ec.SECP256R1(), as_pub_bytes)
    ecdh_secret = ua_private.exchange(ec.ECDH(), as_pub)
    auth_secret = _b64url_decode(auth_b64)
    ikm = HKDF(
        algorithm=hashes.SHA256(),
        length=32,
        salt=auth_secret,
        info=b"WebPush: info\x00" + ua_pub_bytes + as_pub_bytes,
    ).derive(ecdh_secret)
    cek = HKDF(
        algorithm=hashes.SHA256(),
        length=16,
        salt=salt,
        info=b"Content-Encoding: aes128gcm\x00",
    ).derive(ikm)
    nonce = HKDF(
        algorithm=hashes.SHA256(),
        length=12,
        salt=salt,
        info=b"Content-Encoding: nonce\x00",
    ).derive(ikm)
    padded = AESGCM(cek).decrypt(nonce, ciphertext, None)
    assert padded.endswith(b"\x02")
    return padded[:-1]


def _mock_public_dns(monkeypatch: pytest.MonkeyPatch, ip: str = "93.184.216.34") -> None:
    family = socket.AF_INET6 if ":" in ip else socket.AF_INET
    addr = (ip, 443, 0, 0) if family == socket.AF_INET6 else (ip, 443)
    monkeypatch.setattr(
        webpush.socket,
        "getaddrinfo",
        lambda *_args, **_kwargs: [(family, socket.SOCK_STREAM, 6, "", addr)],
    )


def _configure_vapid(monkeypatch: pytest.MonkeyPatch) -> tuple[str, str]:
    priv, pub = webpush.generate_vapid_keypair()
    settings = get_settings()
    monkeypatch.setattr(settings, "vapid_private_key", type(settings.vapid_private_key)(priv))
    monkeypatch.setattr(settings, "vapid_subject", "mailto:ops@example.com")
    return priv, pub


def test_webpush_encryption_vapid_signature_and_cli_keypair(
    capsys: pytest.CaptureFixture[str],
) -> None:
    _priv, pub = webpush.generate_vapid_keypair()
    args = cli.build_parser().parse_args(["generate-vapid-keys"])
    args.handler(args)
    output = capsys.readouterr().out
    assert "NEXT_TASK_VAPID_PRIVATE_KEY=" in output
    generated_priv = output.splitlines()[0].split("=", 1)[1].strip()
    loaded = webpush.load_vapid_private_key(generated_priv)
    derived_pub = webpush.vapid_public_key_b64(loaded)
    assert len(_b64url_decode(derived_pub)) == 65
    assert derived_pub != pub

    ua_priv, p256dh, auth = _make_ua_subscription()
    plaintext = b'{"title":"Due","body":"Pay taxes"}'
    encrypted = webpush.encrypt_webpush_payload(plaintext, p256dh, auth)
    assert _decrypt_aes128gcm(encrypted, ua_priv, auth) == plaintext

    header = webpush.build_vapid_header(
        "https://fcm.googleapis.com/fcm/send/abc",
        loaded,
        derived_pub,
        "mailto:ops@example.com",
        now=datetime(2026, 11, 19, 12, 0, tzinfo=UTC),
    )
    assert header.startswith("vapid t=")
    token_part, key_part = header.removeprefix("vapid ").split(", ")
    jwt_token = token_part.removeprefix("t=")
    assert key_part == f"k={derived_pub}"
    h_b64, p_b64, s_b64 = jwt_token.split(".")
    claims = json.loads(_b64url_decode(p_b64))
    assert claims["aud"] == "https://fcm.googleapis.com"
    assert claims["sub"] == "mailto:ops@example.com"
    raw_sig = _b64url_decode(s_b64)
    assert len(raw_sig) == 64
    r = int.from_bytes(raw_sig[:32], "big")
    s = int.from_bytes(raw_sig[32:], "big")
    loaded.public_key().verify(
        encode_dss_signature(r, s),
        f"{h_b64}.{p_b64}".encode("ascii"),
        ec.ECDSA(hashes.SHA256()),
    )


def test_ssrf_endpoint_validation_blocks_internal_targets(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _mock_public_dns(monkeypatch)
    assert (
        webpush.validate_push_endpoint("https://fcm.googleapis.com/fcm/send/token")
        == "https://fcm.googleapis.com/fcm/send/token"
    )

    for bad_url in (
        "",
        "http://fcm.googleapis.com/fcm/send/token",
        "https://localhost/sub",
        "https://push.localhost/sub",
        "https://printer.local/sub",
        "https://metadata.internal/sub",
        "https://127.0.0.1/sub",
        "https://10.0.0.1/sub",
        "https://[::1]/sub",
        "https://user:pass@fcm.googleapis.com/sub",
        "https://fcm.googleapis.com:8443/sub",
        "https://fcm.googleapis.com/sub#frag",
    ):
        with pytest.raises(ValueError):
            webpush.validate_push_endpoint(bad_url)

    for bad_ip in (
        "127.0.0.1",
        "10.0.0.5",
        "172.16.0.1",
        "192.168.1.1",
        "169.254.169.254",
        "::1",
    ):
        _mock_public_dns(monkeypatch, bad_ip)
        with pytest.raises(ValueError):
            webpush.validate_push_endpoint("https://push.example.com/sub")

    monkeypatch.setattr(
        webpush.socket,
        "getaddrinfo",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(OSError("DNS failed")),
    )
    with pytest.raises(ValueError):
        webpush.validate_push_endpoint("https://push.example.com/sub")

    # Even if a bad endpoint exists in DB, send_web_push re-validates DNS before touching httpx.
    _configure_vapid(monkeypatch)
    called = []
    monkeypatch.setattr(webpush.httpx, "post", lambda *a, **kw: called.append((a, kw)))
    _ua_priv, p256dh, auth = _make_ua_subscription()
    outcome = webpush.send_web_push(
        "https://push.example.com/sub", p256dh, auth, {"title": "x"}
    )
    assert outcome == "failed"
    assert called == []


def test_notification_endpoints_auth_isolation_logout_and_account_switch(
    client: TestClient,
    logged_in_client: Callable[[str], TestClient],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    for method, path in (
        ("GET", "/api/notifications/settings"),
        ("PUT", "/api/notifications/settings"),
        ("POST", "/api/notifications/subscriptions"),
        ("POST", "/api/notifications/unsubscribe"),
        ("POST", "/api/notifications/test"),
        ("GET", "/api/notifications"),
        ("POST", "/api/notifications/read"),
    ):
        assert client.request(method, path, json={}).status_code == 401

    owner = logged_in_client("owner@example.com")
    other = logged_in_client("other@example.com")

    # VAPID not configured -> 503 for subscription and test
    settings = get_settings()
    monkeypatch.setattr(settings, "vapid_private_key", type(settings.vapid_private_key)(""))
    _mock_public_dns(monkeypatch)
    _ua_priv, p256dh, auth = _make_ua_subscription()
    assert (
        owner.post(
            "/api/notifications/subscriptions",
            json={
                "endpoint": "https://push.example.com/dev1",
                "p256dh": p256dh,
                "auth": auth,
                "timezone": "America/Sao_Paulo",
            },
        ).status_code
        == 503
    )
    assert owner.post("/api/notifications/test", json={}).status_code == 503

    _priv, pub = _configure_vapid(monkeypatch)
    settings_resp = owner.get("/api/notifications/settings")
    assert settings_resp.status_code == 200
    assert settings_resp.json()["push_configured"] is True
    assert settings_resp.json()["vapid_public_key"] == pub

    # Invalid timezone -> 422
    bad_tz = owner.put("/api/notifications/settings", json={"timezone": "Mars/Olympus"})
    assert bad_tz.status_code == 422
    assert bad_tz.json()["detail"][0]["code"] == "api.invalidTimeZone"

    # Subscribe two devices for owner and one for other
    for idx in (1, 2):
        resp = owner.post(
            "/api/notifications/subscriptions",
            json={
                "endpoint": f"https://push.example.com/dev{idx}",
                "p256dh": p256dh,
                "auth": auth,
                "timezone": "America/Sao_Paulo",
            },
        )
        assert resp.status_code == 201
        assert resp.json()["subscription_count"] == idx

    other_resp = other.post(
        "/api/notifications/subscriptions",
        json={
            "endpoint": "https://push.example.com/other1",
            "p256dh": p256dh,
            "auth": auth,
            "timezone": "UTC",
        },
    )
    assert other_resp.status_code == 201

    # Owner cannot unsubscribe other's device
    owner.post("/api/notifications/unsubscribe", json={"endpoint": "https://push.example.com/other1"})
    assert other.get("/api/notifications/settings").json()["subscription_count"] == 1

    # Two devices receive one push each for one due task; other user receives none
    task = owner.post(
        "/api/tasks", json={"title": "Submit report", "due_date": "2026-11-19"}
    ).json()
    sent_endpoints: list[str] = []
    monkeypatch.setattr(
        notifications_service,
        "send_web_push",
        lambda endpoint, *_args, **_kwargs: sent_endpoints.append(endpoint) or "sent",
    )
    with SessionLocal() as db:
        owner_user = db.scalar(select(User).where(User.email == "owner@example.com"))
        for sub in db.scalars(select(PushSubscription)).all():
            sub.created_at = datetime(2026, 11, 19, 10, 0, tzinfo=UTC)
        db.commit()
        assert (
            notifications_service.run_notifier_once(
                db, now=datetime(2026, 11, 19, 12, 0, tzinfo=UTC)  # 09:00 America/Sao_Paulo
            )
            == 1
        )
        assert owner_user is not None

    assert sorted(sent_endpoints) == [
        "https://push.example.com/dev1",
        "https://push.example.com/dev2",
    ]
    assert owner.get("/api/notifications").json()["unread_count"] == 1
    assert owner.get("/api/notifications").json()["items"][0]["task_id"] == task["id"]
    assert other.get("/api/notifications").json()["unread_count"] == 0

    # Logout removes only the logged-out device's subscription
    assert (
        owner.post(
            "/api/auth/logout", json={"push_endpoint": "https://push.example.com/dev1"}
        ).status_code
        == 200
    )
    with SessionLocal() as db:
        owner_user = db.scalar(select(User).where(User.email == "owner@example.com"))
        remaining = list(
            db.scalars(
                select(PushSubscription.endpoint).where(PushSubscription.user_id == owner_user.id)
            ).all()
        )
        assert remaining == ["https://push.example.com/dev2"]

    # Account switching reassigns endpoint to new user with fresh created_at
    assert (
        other.post(
            "/api/notifications/subscriptions",
            json={
                "endpoint": "https://push.example.com/dev2",
                "p256dh": p256dh,
                "auth": auth,
                "timezone": "UTC",
            },
        ).status_code
        == 201
    )
    with SessionLocal() as db:
        owner_user = db.scalar(select(User).where(User.email == "owner@example.com"))
        other_user = db.scalar(select(User).where(User.email == "other@example.com"))
        sub = db.scalar(
            select(PushSubscription).where(
                PushSubscription.endpoint == "https://push.example.com/dev2"
            )
        )
        assert sub is not None and sub.user_id == other_user.id
        assert (
            db.scalar(
                select(PushSubscription).where(PushSubscription.user_id == owner_user.id)
            )
            is None
        )


def test_due_date_0900_timezone_dst_blocking_and_reschedule_rules(
    logged_in_client: Callable[[str], TestClient],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _configure_vapid(monkeypatch)
    _mock_public_dns(monkeypatch)
    _ua_priv, p256dh, auth = _make_ua_subscription()

    ny = logged_in_client("ny@example.com")
    tokyo = logged_in_client("tokyo@example.com")

    assert (
        ny.post(
            "/api/notifications/subscriptions",
            json={
                "endpoint": "https://push.example.com/ny",
                "p256dh": p256dh,
                "auth": auth,
                "timezone": "America/New_York",
            },
        ).status_code
        == 201
    )
    assert (
        tokyo.post(
            "/api/notifications/subscriptions",
            json={
                "endpoint": "https://push.example.com/tokyo",
                "p256dh": p256dh,
                "auth": auth,
                "timezone": "Asia/Tokyo",
            },
        ).status_code
        == 201
    )

    sent: list[tuple[str, dict]] = []
    monkeypatch.setattr(
        notifications_service,
        "send_web_push",
        lambda endpoint, _p256dh, _auth, payload: sent.append((endpoint, payload)) or "sent",
    )

    # Set subscriptions early in 2026 so they are eligible across all DST checks
    with SessionLocal() as db:
        for sub in db.scalars(select(PushSubscription)).all():
            sub.created_at = datetime(2026, 1, 1, 0, 0, tzinfo=UTC)
        db.commit()

    # 1. Spring-forward DST in America/New_York: 2026-03-08 is EDT (UTC-4), 09:00 == 13:00 UTC
    ny.post("/api/tasks", json={"title": "Spring DST task", "due_date": "2026-03-08"})
    with SessionLocal() as db:
        assert (
            notifications_service.run_notifier_once(
                db, now=datetime(2026, 3, 8, 12, 59, tzinfo=UTC)
            )
            == 0
        )
        assert (
            notifications_service.run_notifier_once(
                db, now=datetime(2026, 3, 8, 13, 0, tzinfo=UTC)
            )
            == 1
        )
        # Repeated run causes no duplicate
        assert (
            notifications_service.run_notifier_once(
                db, now=datetime(2026, 3, 8, 13, 5, tzinfo=UTC)
            )
            == 0
        )
    assert len(sent) == 1 and sent[-1][0] == "https://push.example.com/ny"

    # 2. Fall-back DST in America/New_York: 2026-11-01 is EST (UTC-5), 09:00 == 14:00 UTC
    ny.post("/api/tasks", json={"title": "Fall DST task", "due_date": "2026-11-01"})
    with SessionLocal() as db:
        assert (
            notifications_service.run_notifier_once(
                db, now=datetime(2026, 11, 1, 13, 59, tzinfo=UTC)
            )
            == 0
        )
        assert (
            notifications_service.run_notifier_once(
                db, now=datetime(2026, 11, 1, 14, 0, tzinfo=UTC)
            )
            == 1
        )

    # 3. Cross-midnight timezone difference: 00:30 UTC is Nov 20 09:30 Tokyo, Nov 19 19:30 NY
    ny_task = ny.post("/api/tasks", json={"title": "NY Nov 20", "due_date": "2026-11-20"}).json()
    tokyo.post("/api/tasks", json={"title": "Tokyo Nov 20", "due_date": "2026-11-20"})
    sent.clear()
    with SessionLocal() as db:
        notifications_service.run_notifier_once(
            db, now=datetime(2026, 11, 20, 0, 30, tzinfo=UTC)
        )
    assert [endpoint for endpoint, _ in sent] == ["https://push.example.com/tokyo"]
    assert ny.get(f"/api/tasks/{ny_task['id']}").json()["due_date"] == "2026-11-20"

    # 4. Eligibility: draft, finished, abandoned, parent with unfinished child, blocked skipped
    ny.post("/api/drafts", json={"title": "Draft due", "due_date": "2026-11-21"})
    fin = ny.post("/api/tasks", json={"title": "Finished due", "due_date": "2026-11-21"}).json()
    ny.post(f"/api/tasks/{fin['id']}/finish")
    aban = ny.post("/api/tasks", json={"title": "Abandoned due", "due_date": "2026-11-21"}).json()
    ny.post(f"/api/tasks/{aban['id']}/abandon")
    parent = ny.post("/api/tasks", json={"title": "Parent due", "due_date": "2026-11-21"}).json()
    ny.post("/api/tasks", json={"title": "Child", "parent_task_id": parent["id"]})
    blocked = ny.post("/api/tasks", json={"title": "Blocked due", "due_date": "2026-11-21"}).json()
    ny.post(f"/api/tasks/{blocked['id']}/block", json={"reason": "Waiting"})
    with SessionLocal() as db:
        block_row = db.scalar(select(TaskBlock).where(TaskBlock.task_id == blocked["id"]))
        block_row.blocked_at = datetime(2026, 11, 21, 13, 0, tzinfo=UTC)
        db.commit()
    resched = ny.post("/api/tasks", json={"title": "Resched due", "due_date": "2026-11-21"}).json()
    ny.patch(f"/api/tasks/{resched['id']}", json={"due_date": "2026-11-22"})

    sent.clear()
    with SessionLocal() as db:
        assert (
            notifications_service.run_notifier_once(
                db, now=datetime(2026, 11, 21, 14, 5, tzinfo=UTC)
            )
            == 0
        )

    # Manually unblocking after 09:00 must NOT cause a delayed 09:00 push
    ny.post(f"/api/tasks/{blocked['id']}/unblock")
    with SessionLocal() as db:
        block_row = db.scalar(select(TaskBlock).where(TaskBlock.task_id == blocked["id"]))
        block_row.unblocked_at = datetime(2026, 11, 21, 14, 30, tzinfo=UTC)
        db.commit()
    with SessionLocal() as db:
        assert (
            notifications_service.run_notifier_once(
                db, now=datetime(2026, 11, 21, 15, 0, tzinfo=UTC)
            )
            == 0
        )

    # Rescheduled task fires on its new due date (2026-11-22)
    with SessionLocal() as db:
        assert (
            notifications_service.run_notifier_once(
                db, now=datetime(2026, 11, 22, 14, 5, tzinfo=UTC)
            )
            == 1
        )
    assert sent[0][1]["body"] == "Due today: Resched due"

    # 5. No retroactive burst when subscribing AFTER 09:00 on that day
    late_user = logged_in_client("late@example.com")
    late_user.post("/api/tasks", json={"title": "Late task", "due_date": "2026-11-25"})
    sent.clear()
    with SessionLocal() as db:
        user_obj = db.scalar(select(User).where(User.email == "late@example.com"))
        user_obj.notification_timezone = "UTC"
        db.add(
            PushSubscription(
                user_id=user_obj.id,
                endpoint="https://push.example.com/late",
                p256dh=p256dh,
                auth=auth,
                created_at=datetime(2026, 11, 25, 10, 0, tzinfo=UTC),
            )
        )
        db.commit()
        assert (
            notifications_service.run_notifier_once(
                db, now=datetime(2026, 11, 25, 10, 5, tzinfo=UTC)
            )
            == 1
        )
    # In-app notification recorded as fallback, but zero Web Pushes sent retroactively!
    assert sent == []
    assert late_user.get("/api/notifications").json()["unread_count"] == 1


def test_timed_blocks_multi_blocker_reblock_cancellation_and_due_status(
    logged_in_client: Callable[[str], TestClient],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _configure_vapid(monkeypatch)
    _mock_public_dns(monkeypatch)
    _ua_priv, p256dh, auth = _make_ua_subscription()
    owner = logged_in_client("timed@example.com")
    assert (
        owner.post(
            "/api/notifications/subscriptions",
            json={
                "endpoint": "https://push.example.com/timed",
                "p256dh": p256dh,
                "auth": auth,
                "timezone": "UTC",
            },
        ).status_code
        == 201
    )

    with SessionLocal() as db:
        for sub in db.scalars(select(PushSubscription)).all():
            sub.created_at = datetime(2026, 1, 1, 0, 0, tzinfo=UTC)
        db.commit()

    sent: list[dict] = []
    monkeypatch.setattr(
        notifications_service,
        "send_web_push",
        lambda _ep, _p, _a, payload: sent.append(payload) or "sent",
    )

    base = datetime.now(UTC)
    t_multi = owner.post("/api/tasks", json={"title": "Multi timed"}).json()
    t1 = base + timedelta(hours=1)
    t2 = base + timedelta(hours=2)
    owner.post(
        f"/api/tasks/{t_multi['id']}/block",
        json={"reason": "B1", "unblocked_at": t1.isoformat()},
    )
    owner.post(
        f"/api/tasks/{t_multi['id']}/block",
        json={"reason": "B2", "unblocked_at": t2.isoformat()},
    )

    # First blocker expires while second is still active -> nothing
    with SessionLocal() as db:
        assert notifications_service.run_notifier_once(db, now=t1 + timedelta(minutes=1)) == 0
    # Second blocker expires -> alerts ONCE without any API request
    with SessionLocal() as db:
        assert notifications_service.run_notifier_once(db, now=t2 + timedelta(minutes=1)) == 1
        assert notifications_service.run_notifier_once(db, now=t2 + timedelta(minutes=2)) == 0
    assert len(sent) == 1
    assert sent[0]["body"] == "Ready to work on: Multi timed"

    # Reblocking with a new timed unblock sends a new alert on the next expiry
    with SessionLocal() as db:
        for row in db.scalars(select(TaskBlock).where(TaskBlock.task_id == t_multi["id"])).all():
            row.unblocked_at = base - timedelta(minutes=10)
        db.commit()
    t3 = t2 + timedelta(hours=3)
    assert (
        owner.post(
            f"/api/tasks/{t_multi['id']}/reblock", json={"unblocked_at": t3.isoformat()}
        ).status_code
        == 200
    )
    with SessionLocal() as db:
        assert notifications_service.run_notifier_once(db, now=t3 + timedelta(minutes=1)) == 1
    assert len(sent) == 2

    # Timed block expires while a manual block is active, then manual unblock runs -> nothing
    t_manual = owner.post("/api/tasks", json={"title": "Manual beats timed"}).json()
    t_exp = base + timedelta(hours=1)
    owner.post(
        f"/api/tasks/{t_manual['id']}/block",
        json={"reason": "Timed", "unblocked_at": t_exp.isoformat()},
    )
    manual_block = owner.post(
        f"/api/tasks/{t_manual['id']}/block", json={"reason": "Manual"}
    ).json()["current_block"]
    # unblock_one checks wall-clock datetime.now(UTC), so backdate expiry before manual unblock.
    with SessionLocal() as db:
        timed_row = db.scalar(
            select(TaskBlock).where(
                TaskBlock.task_id == t_manual["id"], TaskBlock.auto_unblock.is_(True)
            )
        )
        timed_row.unblocked_at = base - timedelta(minutes=10)
        db.commit()
    assert (
        owner.post(f"/api/tasks/{t_manual['id']}/blocks/{manual_block['id']}/unblock").status_code
        == 200
    )
    with SessionLocal() as db:
        assert (
            notifications_service.run_notifier_once(
                db, now=datetime.now(UTC) + timedelta(minutes=1)
            )
            == 0
        )

    # Finishing, abandoning, or deleting before timed expiry cancels stale alerts
    for action in ("finish", "abandon", "delete"):
        t_cancel = owner.post("/api/tasks", json={"title": f"Cancel {action}"}).json()
        t_future = base + timedelta(hours=4)
        owner.post(
            f"/api/tasks/{t_cancel['id']}/block",
            json={"reason": "Wait", "unblocked_at": t_future.isoformat()},
        )
        if action == "delete":
            owner.delete(f"/api/tasks/{t_cancel['id']}")
        else:
            owner.post(f"/api/tasks/{t_cancel['id']}/{action}")
        with SessionLocal() as db:
            assert (
                notifications_service.run_notifier_once(db, now=t_future + timedelta(minutes=1))
                == 0
            )

    # Due task blocked past 09:00 gets unblocked_due / unblocked_overdue when timed block expires
    today = date(2026, 12, 10)
    t_due = owner.post(
        "/api/tasks", json={"title": "Blocked due today", "due_date": today.isoformat()}
    ).json()
    t_over = owner.post(
        "/api/tasks",
        json={"title": "Blocked overdue", "due_date": (today - timedelta(days=1)).isoformat()},
    ).json()
    with SessionLocal() as db:
        db.add_all(
            [
                TaskBlock(
                    task_id=t_due["id"],
                    reason="Wait",
                    blocked_at=datetime(2026, 12, 10, 8, 0, tzinfo=UTC),
                    unblocked_at=datetime(2026, 12, 10, 11, 0, tzinfo=UTC),
                    auto_unblock=True,
                ),
                TaskBlock(
                    task_id=t_over["id"],
                    reason="Wait",
                    blocked_at=datetime(2026, 12, 9, 8, 0, tzinfo=UTC),
                    unblocked_at=datetime(2026, 12, 10, 11, 0, tzinfo=UTC),
                    auto_unblock=True,
                ),
            ]
        )
        db.commit()
    sent.clear()
    with SessionLocal() as db:
        # At 09:05 both are blocked, so no due push fires
        assert (
            notifications_service.run_notifier_once(
                db, now=datetime(2026, 12, 10, 9, 5, tzinfo=UTC)
            )
            == 0
        )
        # At 11:05 both auto-unblock with due/overdue context
        assert (
            notifications_service.run_notifier_once(
                db, now=datetime(2026, 12, 10, 11, 5, tzinfo=UTC)
            )
            == 2
        )
    assert {item["body"] for item in sent} == {
        "Ready and due today: Blocked due today",
        "Ready and overdue: Blocked overdue",
    }

    # Parent with unfinished child at timed b_end -> child finished manually later -> no timed push
    t_parent = owner.post("/api/tasks", json={"title": "Parent timed"}).json()
    t_child = owner.post(
        "/api/tasks", json={"title": "Child", "parent_task_id": t_parent["id"]}
    ).json()
    with SessionLocal() as db:
        child_row = db.get(Task, t_child["id"])
        child_row.created_at = datetime(2026, 12, 11, 9, 0, tzinfo=UTC)
        db.add(
            TaskBlock(
                task_id=t_parent["id"],
                reason="Wait",
                blocked_at=datetime(2026, 12, 11, 9, 0, tzinfo=UTC),
                unblocked_at=datetime(2026, 12, 11, 10, 0, tzinfo=UTC),
                auto_unblock=True,
            )
        )
        db.commit()
    owner.post(f"/api/tasks/{t_child['id']}/finish")
    with SessionLocal() as db:
        child_row = db.get(Task, t_child["id"])
        child_row.finished_at = datetime(2026, 12, 11, 10, 30, tzinfo=UTC)
        db.commit()
    sent.clear()
    with SessionLocal() as db:
        assert (
            notifications_service.run_notifier_once(
                db, now=datetime(2026, 12, 11, 11, 0, tzinfo=UTC)
            )
            == 0
        )


def test_dependency_unblock_records_grouped_in_app_notifications_without_push(
    logged_in_client: Callable[[str], TestClient],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _configure_vapid(monkeypatch)
    _mock_public_dns(monkeypatch)
    _ua_priv, p256dh, auth = _make_ua_subscription()
    owner = logged_in_client("deps@example.com")
    owner.post(
        "/api/notifications/subscriptions",
        json={
            "endpoint": "https://push.example.com/deps",
            "p256dh": p256dh,
            "auth": auth,
            "timezone": "UTC",
        },
    )

    pushes: list[str] = []
    monkeypatch.setattr(
        webpush, "send_web_push", lambda ep, *_a, **_kw: pushes.append(ep) or "sent"
    )
    monkeypatch.setattr(
        notifications_service, "send_web_push", lambda ep, *_a, **_kw: pushes.append(ep) or "sent"
    )

    for action in ("finish", "abandon", "delete"):
        blocker = owner.post("/api/tasks", json={"title": f"Blocker {action}"}).json()
        other_blocker = owner.post("/api/tasks", json={"title": f"Other {action}"}).json()
        d1 = owner.post("/api/tasks", json={"title": f"Ready A {action}"}).json()
        d2 = owner.post("/api/tasks", json={"title": f"Ready B {action}"}).json()
        d3_still_blocked = owner.post(
            "/api/tasks", json={"title": f"Still blocked {action}"}
        ).json()
        for dep_id in (d1["id"], d2["id"], d3_still_blocked["id"]):
            owner.post(f"/api/tasks/{dep_id}/block", json={"blocking_task_id": blocker["id"]})
        owner.post(
            f"/api/tasks/{d3_still_blocked['id']}/block",
            json={"blocking_task_id": other_blocker["id"]},
        )

        if action == "delete":
            assert owner.delete(f"/api/tasks/{blocker['id']}").status_code == 204
        else:
            assert owner.post(f"/api/tasks/{blocker['id']}/{action}").status_code == 200

        feed = owner.get("/api/notifications").json()
        latest = feed["items"][0]
        assert latest["task_id"] == d1["id"]
        assert latest["task_title"] == f"Ready A {action}"
        assert latest["extra_count"] == 1
        assert pushes == []

    # Manual unblock creates neither push nor in-app notification
    before_count = owner.get("/api/notifications").json()["unread_count"]
    manual_task = owner.post("/api/tasks", json={"title": "Manual task"}).json()
    owner.post(f"/api/tasks/{manual_task['id']}/block", json={"reason": "Hold"})
    owner.post(f"/api/tasks/{manual_task['id']}/unblock")
    assert owner.get("/api/notifications").json()["unread_count"] == before_count

    # Mark single and mark all read
    first_id = owner.get("/api/notifications").json()["items"][0]["id"]
    unread_after_one = owner.post(
        "/api/notifications/read", json={"ids": [first_id]}
    ).json()["unread_count"]
    assert unread_after_one == before_count - 1
    assert owner.post("/api/notifications/read", json={}).json()["unread_count"] == 0


def test_expired_subscription_cleanup_failure_resilience_and_language(
    logged_in_client: Callable[[str], TestClient],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _configure_vapid(monkeypatch)
    _mock_public_dns(monkeypatch)
    _ua_priv, p256dh, auth = _make_ua_subscription()
    owner = logged_in_client("pt@example.com")
    assert owner.put("/api/auth/language", json={"language": "pt-BR"}).status_code == 200

    for name in ("expired", "healthy"):
        assert (
            owner.post(
                "/api/notifications/subscriptions",
                json={
                    "endpoint": f"https://push.example.com/{name}",
                    "p256dh": p256dh,
                    "auth": auth,
                    "timezone": "America/Sao_Paulo",
                },
            ).status_code
            == 201
        )

    # Mock httpx.post to return 410 for expired and 201 for healthy, plus verify pt-BR payload
    def fake_post(url: str, *, content: bytes, headers: dict, **_kwargs):
        status_code = 410 if url.endswith("/expired") else 201
        return httpx.Response(status_code, request=httpx.Request("POST", url, content=content))

    monkeypatch.setattr(webpush.httpx, "post", fake_post)
    test_resp = owner.post("/api/notifications/test", json={})
    assert test_resp.status_code == 200
    assert owner.get("/api/notifications/settings").json()["subscription_count"] == 1

    # Payload language check via build_push_payload
    pt_payload = notifications_service.build_push_payload("due", 7, "Revisar plano", "pt-BR", "k")
    assert pt_payload["title"] == translate("notification.dueTitle", "pt-BR")
    assert pt_payload["body"] == translate("notification.dueBody", "pt-BR", title="Revisar plano")
    assert pt_payload["url"] == "/#/tasks?task=7"

    # Push failure (500) returns 502 on /test without crashing app, and notifier keeps in-app row
    monkeypatch.setattr(
        webpush.httpx,
        "post",
        lambda url, **_kw: httpx.Response(500, request=httpx.Request("POST", url)),
    )
    assert owner.post("/api/notifications/test", json={}).status_code == 502

    owner.post("/api/tasks", json={"title": "Keep in-app", "due_date": "2026-12-15"})
    with SessionLocal() as db:
        for sub in db.scalars(select(PushSubscription)).all():
            sub.created_at = datetime(2026, 12, 15, 10, 0, tzinfo=UTC)
        db.commit()
        assert (
            notifications_service.run_notifier_once(
                db, now=datetime(2026, 12, 15, 12, 5, tzinfo=UTC)
            )
            == 1
        )
    assert owner.get("/api/notifications").json()["unread_count"] == 1
    assert notifications_route is not None
