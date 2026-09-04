import json
from collections.abc import Callable

import httpx
import pytest
from app.database import SessionLocal
from app.gemini_schemas import GeneratedTask
from app.models import User
from app.routes import gemini as gemini_routes
from app.services.gemini import GeminiServiceError, generate_task_draft
from fastapi.testclient import TestClient
from sqlalchemy import select


def save_key(client: TestClient, key: str = "AIza-test-key-with-enough-characters") -> dict:
    response = client.put("/api/integrations/gemini", json={"api_key": key})
    assert response.status_code == 200, response.text
    return response.json()


def make_workspace(client: TestClient) -> tuple[dict, list[dict]]:
    workspace = client.post("/api/workspaces", json={"name": "Product"}).json()
    statuses = client.get(f"/api/workspaces/{workspace['id']}/statuses").json()
    return workspace, statuses


def test_gemini_key_is_encrypted_and_never_returned(
    logged_in_client: Callable[[str], TestClient],
) -> None:
    client = logged_in_client("owner@example.com")
    key = "AIza-test-key-with-enough-characters"

    invalid = client.put("/api/integrations/gemini", json={"api_key": " " * 20})
    assert invalid.status_code == 422

    assert client.get("/api/integrations/gemini").json()["configured"] is False
    status = save_key(client, key)
    assert status == {
        "configured": True,
        "masked_key": "••••••••••••",
        "model": "gemini-3.8-flash",
    }
    assert key not in json.dumps(status)

    with SessionLocal() as db:
        user = db.scalar(select(User).where(User.email == "owner@example.com"))
        assert user is not None
        assert user.gemini_api_key_encrypted
        assert key not in user.gemini_api_key_encrypted

    removed = client.delete("/api/integrations/gemini")
    assert removed.status_code == 200
    assert removed.json()["configured"] is False


def test_text_to_task_maps_only_valid_workspace_values(
    logged_in_client: Callable[[str], TestClient],
    create_user: Callable[[str, str, str], User],
    monkeypatch,
) -> None:
    client = logged_in_client("owner@example.com")
    teammate = create_user("teammate@example.com", name="Team Mate")
    workspace, statuses = make_workspace(client)
    client.post(
        f"/api/workspaces/{workspace['id']}/members",
        json={"email": teammate.email, "role": "editor"},
    )
    existing = client.post(
        f"/api/workspaces/{workspace['id']}/tags", json={"name": "backend"}
    ).json()
    save_key(client)
    captured: dict = {}

    def fake_generate(api_key: str, context: dict, text: str) -> GeneratedTask:
        captured.update(api_key=api_key, context=context, text=text)
        return GeneratedTask(
            title="Ship task drafting",
            description="Add a reviewed **AI draft**.",
            status_name="doing",
            priority=3,
            due_date="2026-09-08",
            assignee_emails=["teammate@example.com", "outside@example.com"],
            tag_names=["#Backend", "ai", "AI", ""],
        )

    monkeypatch.setattr(gemini_routes, "generate_task_draft", fake_generate)
    response = client.post(
        f"/api/workspaces/{workspace['id']}/task-drafts/from-text",
        json={"text": "Have Team Mate ship AI task drafting by Tuesday"},
    )

    assert response.status_code == 200, response.text
    assert response.json() == {
        "title": "Ship task drafting",
        "description": "Add a reviewed **AI draft**.",
        "status_id": statuses[1]["id"],
        "priority": 3,
        "due_date": "2026-09-08",
        "assignee_ids": [teammate.id],
        "existing_tag_ids": [existing["id"]],
        "new_tag_names": ["ai"],
        "model": "gemini-3.8-flash",
    }
    assert captured["api_key"] == "AIza-test-key-with-enough-characters"
    assert captured["text"].startswith("Have Team Mate")
    assert captured["context"]["existing_tags"] == ["backend"]
    assert {item["name"] for item in captured["context"]["members"]} == {
        "Test User",
        "Team Mate",
    }


def test_text_to_task_requires_own_key_and_editor_access(
    logged_in_client: Callable[[str], TestClient],
    create_user: Callable[[str, str, str], User],
) -> None:
    owner = logged_in_client("owner@example.com")
    viewer = create_user("viewer@example.com")
    workspace, _statuses = make_workspace(owner)

    missing = owner.post(
        f"/api/workspaces/{workspace['id']}/task-drafts/from-text",
        json={"text": "Create something"},
    )
    assert missing.status_code == 409

    owner.post(
        f"/api/workspaces/{workspace['id']}/members",
        json={"email": viewer.email, "role": "viewer"},
    )
    viewer_client = TestClient(owner.app)
    viewer_client.post(
        "/api/auth/login",
        json={"email": viewer.email, "password": "correct horse"},
    )
    save_key(viewer_client)
    denied = viewer_client.post(
        f"/api/workspaces/{workspace['id']}/task-drafts/from-text",
        json={"text": "Create something"},
    )
    assert denied.status_code == 403


def gemini_context() -> dict:
    return {
        "name": "Personal",
        "today": "2026-09-03",
        "statuses": [{"name": "todo"}],
        "members": [{"name": "Owner", "email": "owner@example.com"}],
        "existing_tags": [],
    }


def test_gemini_interactions_request_uses_structured_output() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers["x-goog-api-key"] == "secret-key"
        body = json.loads(request.content)
        assert body["model"] == "gemini-3.8-flash"
        assert "max_output_tokens" not in body
        assert body["generation_config"] == {"max_output_tokens": 2_048}
        assert body["response_format"]["mime_type"] == "application/json"
        assert body["response_format"]["schema"]["properties"]["status_name"]["enum"] == [
            "todo"
        ]
        generated = {
            "title": "Buy groceries",
            "description": None,
            "status_name": "todo",
            "priority": 1,
            "due_date": None,
            "assignee_emails": [],
            "tag_names": ["errands"],
        }
        return httpx.Response(
            200,
            json={
                "status": "completed",
                "steps": [
                    {
                        "type": "model_output",
                        "content": [{"type": "text", "text": json.dumps(generated)}],
                    }
                ],
            },
        )

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        draft = generate_task_draft("secret-key", gemini_context(), "Buy groceries", client)
    assert draft.title == "Buy groceries"
    assert draft.tag_names == ["errands"]


def test_gemini_request_error_keeps_useful_detail_and_redacts_key() -> None:
    api_key = "secret-key"

    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            400,
            json={
                "error": {
                    "code": 400,
                    "status": "INVALID_ARGUMENT",
                    "message": f'Invalid JSON payload for {api_key}: unknown field "bad_field".',
                }
            },
        )

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(GeminiServiceError) as caught:
            generate_task_draft(api_key, gemini_context(), "Buy groceries", client)

    assert caught.value.status_code == 400
    assert "unknown field" in str(caught.value)
    assert api_key not in str(caught.value)
    assert "[redacted]" in str(caught.value)
