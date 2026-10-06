import json
from collections.abc import Callable

import httpx
import pytest
from app.database import SessionLocal
from app.gemini_schemas import GeminiModelRead, GeneratedTask
from app.models import User
from app.routes import gemini as gemini_routes
from app.services.gemini import GeminiServiceError, generate_task_draft, list_gemini_models
from fastapi.testclient import TestClient
from sqlalchemy import select


def save_key(client: TestClient, key: str = "AIza-test-key-with-enough-characters") -> dict:
    response = client.put("/api/integrations/gemini", json={"api_key": key})
    assert response.status_code == 200, response.text
    return response.json()


def make_workspace(client: TestClient) -> dict:
    workspace = client.post("/api/workspaces", json={"name": "Product"}).json()
    return workspace


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


def test_google_models_are_filtered_across_pages() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers["x-goog-api-key"] == "secret-key"
        if request.url.params.get("pageToken") == "second":
            return httpx.Response(
                200,
                json={
                    "models": [
                        {
                            "name": "models/gemini-2.5-pro",
                            "displayName": "Gemini 2.5 Pro",
                            "supportedGenerationMethods": ["generateContent"],
                        },
                        {
                            "name": "models/gemini-tts",
                            "supportedGenerationMethods": ["generateContent"],
                        },
                    ]
                },
            )
        return httpx.Response(
            200,
            json={
                "models": [
                    {
                        "name": "models/gemini-3.8-flash",
                        "displayName": "Gemini 3.8 Flash",
                        "supportedGenerationMethods": ["generateContent"],
                    },
                    {
                        "name": "models/text-embedding-004",
                        "supportedGenerationMethods": ["embedContent"],
                    },
                    {
                        "name": "models/gemini-3-pro-image",
                        "supportedGenerationMethods": ["generateContent"],
                    },
                ],
                "nextPageToken": "second",
            },
        )

    with httpx.Client(transport=httpx.MockTransport(handler)) as http_client:
        models = list_gemini_models("secret-key", http_client)
    assert [(model.id, model.name) for model in models] == [
        ("gemini-2.5-pro", "Gemini 2.5 Pro"),
        ("gemini-3.8-flash", "Gemini 3.8 Flash"),
    ]


def test_selected_model_is_private_and_used_for_drafts(
    logged_in_client: Callable[[str], TestClient], monkeypatch
) -> None:
    owner = logged_in_client("owner@example.com")
    other = logged_in_client("other@example.com")
    workspace = make_workspace(owner)
    assert owner.get("/api/integrations/gemini/models").status_code == 409
    assert (
        owner.put("/api/integrations/gemini/model", json={"model": "gemini-2.5-pro"}).status_code
        == 409
    )
    save_key(owner)
    save_key(other)
    monkeypatch.setattr(
        gemini_routes,
        "list_gemini_models",
        lambda _key: [
            GeminiModelRead(id="gemini-2.5-pro", name="Gemini 2.5 Pro"),
            GeminiModelRead(id="gemini-3.8-flash", name="Gemini 3.8 Flash"),
        ],
    )
    assert len(owner.get("/api/integrations/gemini/models").json()) == 2
    assert (
        owner.put("/api/integrations/gemini/model", json={"model": "gemini-unknown"}).status_code
        == 422
    )
    selected = owner.put("/api/integrations/gemini/model", json={"model": "gemini-2.5-pro"})
    assert selected.status_code == 200
    assert selected.json()["model"] == "gemini-2.5-pro"
    assert owner.get("/api/integrations/gemini").json()["model"] == "gemini-2.5-pro"
    assert other.get("/api/integrations/gemini").json()["model"] == "gemini-3.8-flash"

    captured: dict = {}

    def fake_generate(_key: str, _context: dict, _text: str, *, model: str) -> GeneratedTask:
        captured["model"] = model
        return GeneratedTask(
            title="Draft",
            description=None,
            priority=1,
            due_date=None,
            assignee_emails=[],
            tag_names=[],
        )

    monkeypatch.setattr(gemini_routes, "generate_task_draft", fake_generate)
    draft = owner.post(
        f"/api/workspaces/{workspace['id']}/task-drafts/from-text", json={"text": "Draft something"}
    )
    assert draft.status_code == 200, draft.text
    assert draft.json()["model"] == captured["model"] == "gemini-2.5-pro"

    assert owner.delete("/api/integrations/gemini").json()["model"] == "gemini-3.8-flash"


def test_text_to_task_maps_only_valid_workspace_values(
    logged_in_client: Callable[[str], TestClient],
    create_user: Callable[[str, str, str], User],
    monkeypatch,
) -> None:
    client = logged_in_client("owner@example.com")
    teammate = create_user("teammate@example.com", name="Team Mate")
    workspace = make_workspace(client)
    client.post(
        f"/api/workspaces/{workspace['id']}/members",
        json={"email": teammate.email, "role": "editor"},
    )
    existing = client.post(
        f"/api/workspaces/{workspace['id']}/tags", json={"name": "backend"}
    ).json()
    save_key(client)
    captured: dict = {}

    def fake_generate(api_key: str, context: dict, text: str, *, model: str) -> GeneratedTask:
        captured.update(api_key=api_key, context=context, text=text, model=model)
        return GeneratedTask(
            title="Ship task drafting",
            description="Add a reviewed **AI draft**.",
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
    workspace = make_workspace(owner)

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
        "members": [{"name": "Owner", "email": "owner@example.com"}],
        "existing_tags": [],
    }


def test_gemini_interactions_request_uses_structured_output() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers["x-goog-api-key"] == "secret-key"
        body = json.loads(request.content)
        assert body["model"] == "gemini-2.5-pro"
        assert "max_output_tokens" not in body
        assert body["generation_config"] == {"max_output_tokens": 2_048}
        assert body["response_format"]["mime_type"] == "application/json"
        assert "status_name" not in body["response_format"]["schema"]["properties"]
        generated = {
            "title": "Buy groceries",
            "description": None,
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
        draft = generate_task_draft(
            "secret-key", gemini_context(), "Buy groceries", client, model="gemini-2.5-pro"
        )
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

    with (
        httpx.Client(transport=httpx.MockTransport(handler)) as client,
        pytest.raises(GeminiServiceError) as caught,
    ):
        generate_task_draft(api_key, gemini_context(), "Buy groceries", client)

    assert caught.value.status_code == 400
    assert "unknown field" in str(caught.value)
    assert api_key not in str(caught.value)
    assert "[redacted]" in str(caught.value)
