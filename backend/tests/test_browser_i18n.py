"""Real browser coverage, opt-in locally and required in CI; never uses operator SMTP/data."""

import os
import shutil
import socket
import subprocess
import threading
import time
from datetime import UTC, datetime, timedelta
from pathlib import Path
from urllib.request import urlopen

import pytest
import uvicorn
from app.auth.security import hash_password, hash_token
from app.config import get_settings
from app.database import SessionLocal
from app.main import app
from app.models import EmailVerification, Invitation, PasswordReset, User
from app.routes import auth, password_recovery
from app.services.onboarding import add_onboarding_data
from sqlalchemy import select


@pytest.mark.skipif(
    os.environ.get("NEXT_TASK_BROWSER_TESTS") != "1", reason="Opt-in Chrome integration"
)
def test_i18n_in_chrome(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    chrome = (
        os.environ.get("CHROME_BIN") or shutil.which("google-chrome") or shutil.which("chromium")
    )
    if not chrome and os.name == "nt":
        chrome = r"C:\Program Files\Google\Chrome\Application\chrome.exe"
    assert chrome and Path(chrome).is_file(), "Set CHROME_BIN to a Chrome/Chromium executable"
    root = Path(__file__).resolve().parents[2]
    # Production assets must be built before this opt-in integration check.
    monkeypatch.setattr(get_settings(), "frontend_dir", root / "frontend/dist")
    monkeypatch.setattr(get_settings(), "cookie_secure", False)
    monkeypatch.setattr(auth, "send_email", lambda *_args: None)
    monkeypatch.setattr(password_recovery, "send_email", lambda *_args: None)
    with SessionLocal() as db:
        for language in ("en", "pt-BR"):
            user = User(
                email=f"{language}@example.com",
                display_name="Browser User",
                language=language,
                password_hash=hash_password("correct horse"),
            )
            db.add(user)
            add_onboarding_data(db, user)
            expiry = datetime.now(UTC) + timedelta(hours=24)
            db.add(
                Invitation(
                    email=f"guest-{language}@example.com",
                    language=language,
                    token_hash=hash_token(f"invite-{language}-" + "x" * 32),
                    expires_at=expiry,
                )
            )
            db.add(
                EmailVerification(
                    user_id=user.id,
                    email=user.email,
                    token_hash=hash_token(f"verify-{language}-" + "x" * 32),
                    expires_at=expiry,
                )
            )
            recovery_user = User(
                email=f"recovery-{language}@example.com",
                display_name="Recovery",
                language=language,
                password_hash=hash_password("correct horse"),
                email_verified_at=datetime.now(UTC),
            )
            db.add(recovery_user)
            db.flush()
            db.refresh(recovery_user)
            db.add(
                PasswordReset(
                    user_id=recovery_user.id,
                    email=recovery_user.email,
                    credential_hash=password_recovery.credential_hash(recovery_user),
                    token_hash=hash_token(f"reset-{language}-" + "x" * 32),
                    expires_at=expiry,
                )
            )
        db.commit()
    with socket.socket() as port_socket:
        port_socket.bind(("127.0.0.1", 0))
        port = port_socket.getsockname()[1]
    server = uvicorn.Server(
        uvicorn.Config(app, host="127.0.0.1", port=port, log_level="warning", access_log=False)
    )
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    address = f"http://127.0.0.1:{port}"
    try:
        for _ in range(100):
            if server.started:
                break
            time.sleep(0.05)
        assert server.started
        with urlopen(address + "/api/health") as response:
            assert response.status == 200
        result = subprocess.run(
            ["node", str(root / "frontend/tests/browser-i18n.mjs")],
            cwd=root,
            env={
                **os.environ,
                "CHROME_BIN": chrome,
                "NEXT_TASK_TEST_URL": address,
                "NEXT_TASK_BROWSER_PROFILE": str(tmp_path / "chrome"),
            },
            check=False,
            capture_output=True,
            text=True,
            timeout=90,
        )
        assert result.returncode == 0, result.stdout + result.stderr
        with SessionLocal() as db:
            assert db.scalar(select(User).where(User.email == "en@example.com")).language == "pt-BR"
    finally:
        server.should_exit = True
        thread.join(timeout=5)
