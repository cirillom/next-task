"""Browser coverage for login continuation and explicit MCP consent."""

import os
import shutil
import socket
import subprocess
import threading
import time
from pathlib import Path

import httpx
import pytest
import uvicorn
from app.config import get_settings
from app.database import SessionLocal
from app.main import app
from app.models import MCPGrant, User
from app.routes import mcp_oauth
from authlib.oauth2.rfc7636.challenge import create_s256_code_challenge
from sqlalchemy import func, select


@pytest.mark.skipif(
    os.environ.get("NEXT_TASK_BROWSER_TESTS") != "1", reason="Opt-in Chrome integration"
)
@pytest.mark.parametrize("language,allow", [("en", True), ("pt-BR", False)])
def test_mcp_consent_after_login(tmp_path: Path, monkeypatch, create_user, language, allow):
    chrome = (
        os.environ.get("CHROME_BIN") or shutil.which("google-chrome") or shutil.which("chromium")
    )
    if not chrome and os.name == "nt":
        chrome = r"C:\Program Files\Google\Chrome\Application\chrome.exe"
    assert chrome and Path(chrome).is_file()
    root = Path(__file__).resolve().parents[2]
    user = create_user("mcp-browser@example.com")
    with SessionLocal() as db:
        db.get(User, user.id).language = language
        db.commit()
    monkeypatch.setattr(get_settings(), "frontend_dir", root / "frontend/dist")
    monkeypatch.setattr(get_settings(), "cookie_secure", False)

    async def metadata(client_id):
        return {
            "client_id": client_id,
            "client_name": "Browser fixture",
            "redirect_uris": ["https://localhost:1/callback"],
            "token_endpoint_auth_method": "none",
        }

    monkeypatch.setattr(mcp_oauth.resolver, "resolve", metadata)
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
    address = f"http://127.0.0.1:{port}"
    monkeypatch.setattr(mcp_oauth, "issuer", lambda: address)
    server = uvicorn.Server(
        uvicorn.Config(app, host="127.0.0.1", port=port, log_level="warning", access_log=False)
    )
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    try:
        for _ in range(100):
            if server.started:
                break
            time.sleep(0.05)
        assert server.started
        response = httpx.get(
            address + "/oauth/authorize",
            follow_redirects=False,
            params={
                "client_id": "https://client.example/metadata",
                "redirect_uri": "https://localhost:1/callback",
                "response_type": "code",
                "resource": address + "/mcp",
                "code_challenge_method": "S256",
                "code_challenge": create_s256_code_challenge("a" * 43),
            },
        )
        assert response.status_code == 303
        result = subprocess.run(
            ["node", str(root / "frontend/tests/browser-mcp.mjs")],
            cwd=root,
            env={
                **os.environ,
                "CHROME_BIN": chrome,
                "NEXT_TASK_TEST_URL": address + response.headers["location"] + "&lang=" + language,
                "NEXT_TASK_MCP_LANGUAGE": language,
                "NEXT_TASK_MCP_ALLOW": str(allow),
                "NEXT_TASK_BROWSER_PROFILE": str(tmp_path / "chrome"),
            },
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=60,
        )
        assert result.returncode == 0, result.stdout + result.stderr
        with SessionLocal() as db:
            assert db.scalar(select(func.count(MCPGrant.id))) == int(allow)
    finally:
        server.should_exit = True
        thread.join(timeout=5)
