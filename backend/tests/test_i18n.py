import re
from collections.abc import Callable

import pytest
from app import cli
from app.database import SessionLocal
from app.i18n import LANGUAGES, catalog, translate
from app.models import Invitation, Task, User
from app.routes import auth, password_recovery
from app.services import invitations
from fastapi.testclient import TestClient
from sqlalchemy import select


def test_language_preference_requires_authentication_and_preserves_user_content(
    client: TestClient,
    logged_in_client: Callable[[str], TestClient],
) -> None:
    assert client.put("/api/auth/language", json={"language": "pt-BR"}).status_code == 401
    owner = logged_in_client("owner@example.com")
    task = owner.post(
        "/api/tasks", json={"title": "My unchanged task", "description": "Notas pessoais"}
    ).json()
    assert owner.get("/api/auth/me").json()["language"] == "en"
    assert owner.put("/api/auth/language", json={"language": "pt-BR"}).json()["language"] == "pt-BR"
    other_device = TestClient(client.app)
    assert (
        other_device.post(
            "/api/auth/login", json={"email": "owner@example.com", "password": "correct horse"}
        ).json()["language"]
        == "pt-BR"
    )
    assert owner.get(f"/api/tasks/{task['id']}").json()["description"] == "Notas pessoais"
    for unsupported in ("pt", "pt-PT", "fr", "../en", None):
        response = owner.put("/api/auth/language", json={"language": unsupported})
        assert response.status_code == 422
        assert response.json()["detail"][0]["code"] == "validation.invalidChoice"
    assert owner.get("/api/auth/me").json()["language"] == "pt-BR"
    assert len(owner.get("/api/tasks").json()) == 1


@pytest.mark.parametrize("language", LANGUAGES)
@pytest.mark.parametrize("override", [False, True])
def test_invitation_language_and_onboarding_are_atomic_and_keep_next_order(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    language: str,
    override: bool,
) -> None:
    sent = []
    monkeypatch.setattr(invitations, "public_app_url", lambda: "https://tasks.example.com")
    monkeypatch.setattr(invitations, "send_email", lambda *args: sent.append(args))
    invitations.send_invitation("new@example.com", language)
    assert sent[0][1] == translate("mail.inviteSubject", language)
    assert f"&lang={language}" in sent[0][2]
    with SessionLocal() as db:
        assert db.get(Invitation, "new@example.com").language == language
    token = re.search(r"token=([A-Za-z0-9_-]+)", sent[0][2])[1]
    selected = ("pt-BR" if language == "en" else "en") if override else language
    payload = {"token": token, "display_name": "New User", "password": "correct horse"}
    if override:
        payload["language"] = selected
    assert client.post("/api/auth/invitations/accept", json=payload).status_code == 201
    assert (
        client.post(
            "/api/auth/login", json={"email": "new@example.com", "password": "correct horse"}
        ).json()["language"]
        == selected
    )
    tags = client.get("/api/tags").json()
    urgent = next(
        tag for tag in tags if tag["name"] == translate("onboarding.tag.urgent.name", selected)
    )
    assert urgent["score_value"] == 5 and urgent["color"] == "#D64545"
    for step in range(1, 5):
        tasks = client.get(
            "/api/tasks", params={"finished": False, "blocked": False, "actionable": True}
        ).json()
        assert len(tasks) == 1
        task = tasks[0]
        assert task["title"] == translate(f"onboarding.task.{step}.title", selected)
        assert client.post(f"/api/tasks/{task['id']}/finish").status_code == 200
    before = client.get("/api/tags").json()
    assert (
        client.put(
            "/api/auth/language", json={"language": "pt-BR" if selected == "en" else "en"}
        ).status_code
        == 200
    )
    assert client.get("/api/tags").json() == before
    assert len(client.get("/api/tasks", params={"finished": True}).json()) == 4


@pytest.mark.parametrize("language", LANGUAGES)
def test_account_emails_use_recipient_preference_and_reset_responses_remain_generic(
    client: TestClient,
    logged_in_client: Callable[[str], TestClient],
    monkeypatch: pytest.MonkeyPatch,
    language: str,
) -> None:
    owner = logged_in_client("owner@example.com")
    assert owner.put("/api/auth/language", json={"language": language}).status_code == 200
    sent = []
    for module in (auth, password_recovery):
        monkeypatch.setattr(module, "public_app_url", lambda: "https://tasks.example.com")
        monkeypatch.setattr(module, "send_email", lambda *args: sent.append(args))
    response = owner.post(
        "/api/auth/email", json={"email": "owner@example.com", "current_password": "correct horse"}
    )
    assert response.status_code == 200
    assert sent[-1][1] == translate("mail.verifySubject", language)
    token = re.search(r"token=([A-Za-z0-9_-]+)", sent[-1][2])[1]
    assert client.post("/api/auth/email/verify", json={"token": token}).status_code == 200
    known = client.post("/api/auth/forgot-password", json={"email": "owner@example.com"})
    unknown = client.post("/api/auth/forgot-password", json={"email": "unknown@example.com"})
    assert known.status_code == unknown.status_code == 202
    assert known.json() == unknown.json()
    assert sent[-1][1] == translate("mail.resetSubject", language)
    assert f"&lang={language}" in sent[-1][2]
    token = re.search(r"token=([A-Za-z0-9_-]+)", sent[-1][2])[1]
    response = client.post(
        "/api/auth/reset-password", json={"token": token, "new_password": "new secure password"}
    )
    assert response.status_code == 200
    assert sent[-1][1:] == (
        translate("mail.changedSubject", language),
        translate("mail.changedBody", language),
    )
    assert (
        client.post(
            "/api/auth/reset-password", json={"token": token, "new_password": "another password"}
        ).status_code
        == 400
    )


def test_validation_and_scoring_errors_have_stable_codes_without_echoing_secrets(
    client: TestClient,
    logged_in_client: Callable[[str], TestClient],
) -> None:
    response = client.post("/api/auth/login", json={"email": "someone"})
    assert response.status_code == 422
    assert all("input" not in error and "ctx" not in error for error in response.json()["detail"])
    response = client.post(
        "/api/auth/login", json={"email": "missing@example.com", "password": "secret value"}
    )
    assert response.status_code == 401
    assert response.json()["code"] == "api.invalidEmailOrPassword"
    assert "secret value" not in response.text
    owner = logged_in_client("owner@example.com")
    owner.post("/api/tasks", json={"title": "Task"})
    with SessionLocal() as db:
        db.scalar(select(User).where(User.email == "owner@example.com")).scoring_formula = "1 / 0"
        db.commit()
    task = owner.get("/api/tasks").json()[0]
    assert task["scoring_warning_code"] == "api.scoringFallback"
    assert task["scoring_warning_params"]["reason"]["key"] == "api.formulaArithmeticFailed"


def test_backend_fallback_and_catalog_coverage() -> None:
    assert catalog("unsupported") == catalog("en")
    assert set(catalog("en")) == set(catalog("pt-BR"))
    assert translate("api.invalidEmailOrPassword", "pt-BR") == "E-mail ou senha inválidos"


@pytest.mark.parametrize("language", LANGUAGES)
def test_operator_language_controls_examples_and_test_email(
    monkeypatch: pytest.MonkeyPatch,
    language: str,
) -> None:
    monkeypatch.setattr(cli, "read_password", lambda *_args: "correct horse")
    args = cli.build_parser().parse_args(
        [
            "create-user",
            "--email",
            "operator@example.com",
            "--display-name",
            "Operator",
            "--language",
            language,
        ]
    )
    args.handler(args)
    with SessionLocal() as db:
        user = db.scalar(select(User).where(User.email == "operator@example.com"))
        assert user.language == language
        assert db.scalar(
            select(Task.title).where(Task.user_id == user.id).order_by(Task.id)
        ) == translate("onboarding.task.1.title", language)
    sent = []
    monkeypatch.setattr(cli, "send_email", lambda *args: sent.append(args))
    args = cli.build_parser().parse_args(
        ["test-email", "operator@example.com", "--language", language]
    )
    args.handler(args)
    assert sent[0][1:] == (
        translate("mail.testSubject", language),
        translate("mail.testBody", language),
    )
