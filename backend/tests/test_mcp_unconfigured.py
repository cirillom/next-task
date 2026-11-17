import os
import subprocess
import sys
from pathlib import Path


def test_unconfigured_origin_keeps_app_available_but_rejects_mcp(tmp_path: Path):
    code = """
from fastapi.testclient import TestClient
from app.main import app
with TestClient(app) as client:
    assert client.get('/api/health').json() == {'status': 'ok'}
    assert client.post('/mcp', json={}).status_code == 503
    assert client.get('/.well-known/oauth-protected-resource/mcp').status_code == 503
    assert client.get('/.well-known/oauth-authorization-server').status_code == 503
    assert client.get('/oauth/authorize').status_code == 503
    assert client.post('/oauth/token', data={}).status_code == 503
"""
    env = {
        **os.environ,
        "NEXT_TASK_PUBLIC_APP_URL": "",
        "NEXT_TASK_DATABASE_URL": f"sqlite:///{(tmp_path / 'empty.sqlite3').as_posix()}",
    }
    subprocess.run(
        [sys.executable, "-c", code],
        cwd=Path(__file__).resolve().parents[2],
        env=env,
        check=True,
        capture_output=True,
    )
