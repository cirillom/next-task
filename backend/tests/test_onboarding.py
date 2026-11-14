import re
from collections.abc import Callable
from datetime import UTC, datetime, timedelta

import pytest
from app import cli
from app.database import SessionLocal
from app.main import app
from app.models import Invitation, Tag, Task, TaskBlock, User
from app.routes import invitations as invitation_routes
from app.services import invitations, scoring
from app.services.onboarding import add_onboarding_data
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError

TITLES = [
    "Conheça sua próxima tarefa",
    "Experimente as tags e seus valores",
    "Experimente uma tarefa com prazo",
    "Adicione algo que você não quer esquecer",
]


@pytest.fixture
def invite_link(monkeypatch: pytest.MonkeyPatch) -> Callable[[str], str]:
    messages: list[str] = []
    monkeypatch.setattr(invitations, "public_app_url", lambda: "https://tasks.example.com")
    monkeypatch.setattr(
        invitations, "send_email", lambda _to, _subject, body: messages.append(body)
    )

    def factory(email: str) -> str:
        invitations.send_invitation(email)
        match = re.search(r"token=([A-Za-z0-9_-]+)", messages[-1])
        assert match is not None
        return match.group(1)

    return factory


@pytest.fixture
def register(invite_link: Callable[[str], str]) -> Callable[[str], TestClient]:
    def factory(email: str = "new@example.com") -> TestClient:
        client = TestClient(app)
        response = client.post(
            "/api/auth/invitations/accept",
            json={
                "token": invite_link(email),
                "display_name": "New User",
                "password": "correct horse",
            },
        )
        assert response.status_code == 201, response.text
        assert (
            client.post(
                "/api/auth/login", json={"email": email, "password": "correct horse"}
            ).status_code
            == 200
        )
        return client

    return factory


def next_tasks(client: TestClient) -> list[dict]:
    response = client.get(
        "/api/tasks", params={"finished": False, "blocked": False, "actionable": True}
    )
    assert response.status_code == 200, response.text
    return response.json()


def test_new_account_gets_hierarchical_tags_urgent_and_relative_dates(
    register: Callable[[str], TestClient],
) -> None:
    client = register("new@example.com")
    tags = {tag["name"]: tag for tag in client.get("/api/tags").json()}
    assert set(tags) == {
        "Pessoal",
        "Trabalho",
        "Urgente",
        "Rotina",
        "Aprendizado",
        "Projetos",
        "Administrativo",
    }
    assert {name for name, tag in tags.items() if not tag["parents"]} == {
        "Pessoal",
        "Trabalho",
        "Urgente",
    }
    assert tags["Urgente"]["color"] == "#D64545"
    assert tags["Urgente"]["score_value"] == 5
    for child, parent in (
        ("Rotina", "Pessoal"),
        ("Aprendizado", "Pessoal"),
        ("Projetos", "Trabalho"),
        ("Administrativo", "Trabalho"),
    ):
        assert [tag["id"] for tag in tags[child]["parents"]] == [tags[parent]["id"]]
        assert tags[child]["color"] == tags[parent]["color"]
    assert all(tag["description"] for tag in tags.values())
    tasks = {task["title"]: task for task in client.get("/api/tasks").json()}
    assert set(tasks) == set(TITLES)
    created_at = datetime.fromisoformat(client.get("/api/auth/me").json()["created_at"])
    for task in tasks.values():
        assert datetime.fromisoformat(task["created_at"]) == created_at
        assert task["last_worked_at"] is None
        assert task["description"]
        assert task["finished_at"] is None and task["abandoned_at"] is None
    assert (
        tasks[TITLES[2]]["due_date"]
        == (created_at.astimezone().date() + timedelta(days=7)).isoformat()
    )
    assert all(tasks[title]["due_date"] is None for title in (TITLES[0], TITLES[1], TITLES[3]))
    first = next_tasks(client)[0]
    assert first["title"] == TITLES[0]
    assert scoring.DEFAULT_SCORING_FORMULA in first["description"]
    assert "Urgente" in first["description"] and "100 pontos" in first["description"]
    assert {tag["name"] for tag in first["inherited_tags"]} == {"Pessoal"}
    updated = client.patch(
        f"/api/tasks/{first['id']}",
        json={"tag_ids": [tags["Aprendizado"]["id"], tags["Urgente"]["id"]]},
    ).json()
    assert updated["score"] - first["score"] == pytest.approx(100, abs=0.02)


@pytest.mark.parametrize("days_later", [0, 365])
@pytest.mark.parametrize("action", ["finish", "abandon"])
def test_next_presents_all_four_steps_in_order_even_when_deadline_is_overdue(
    register: Callable[[str], TestClient],
    monkeypatch: pytest.MonkeyPatch,
    days_later: int,
    action: str,
) -> None:
    client = register("new@example.com")
    future = datetime.now(UTC) + timedelta(days=days_later)

    class Clock:
        @staticmethod
        def now(_tz: object) -> datetime:
            return future

    monkeypatch.setattr(scoring, "datetime", Clock)
    for title in TITLES:
        eligible = next_tasks(client)
        assert [task["title"] for task in eligible] == [title]
        assert client.post(f"/api/tasks/{eligible[0]['id']}/{action}").status_code == 200
    assert next_tasks(client) == []
    with SessionLocal() as db:
        assert db.scalar(select(func.count(Task.id))) == 4
        blocks = db.scalars(select(TaskBlock)).all()
        assert len(blocks) == 3
        assert all(block.unblocked_at is not None for block in blocks)


def test_sign_in_never_reseeds_and_existing_and_other_accounts_stay_isolated(
    register: Callable[[str], TestClient],
    logged_in_client: Callable[[str], TestClient],
) -> None:
    existing = logged_in_client("existing@example.com")
    task = existing.post("/api/tasks", json={"title": "Existing real work"}).json()
    first = register("first@example.com")
    second = register("second@example.com")
    first_tags = {tag["id"] for tag in first.get("/api/tags").json()}
    second_tags = {tag["id"] for tag in second.get("/api/tags").json()}
    assert first_tags.isdisjoint(second_tags)
    first_task = next_tasks(first)[0]
    assert first.delete(f"/api/tasks/{first_task['id']}").status_code == 204
    first.post("/api/auth/logout")
    assert (
        first.post(
            "/api/auth/login", json={"email": "first@example.com", "password": "correct horse"}
        ).status_code
        == 200
    )
    assert len(first.get("/api/tasks").json()) == 3
    assert len(first.get("/api/tags").json()) == 7
    assert len(second.get("/api/tasks").json()) == 4
    assert [item["id"] for item in existing.get("/api/tasks").json()] == [task["id"]]
    assert existing.get("/api/tags").json() == []


def test_failed_seeding_rolls_back_account_examples_and_invite_consumption(
    client: TestClient,
    invite_link: Callable[[str], str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    token = invite_link("new@example.com")

    def fail(db, user):
        add_onboarding_data(db, user)
        db.flush()
        raise IntegrityError("simulated seed failure", None, None)

    payload = {"token": token, "display_name": "New User", "password": "correct horse"}
    with monkeypatch.context() as patch:
        patch.setattr(invitation_routes, "add_onboarding_data", fail)
        assert client.post("/api/auth/invitations/accept", json=payload).status_code == 400
    with SessionLocal() as db:
        for model in (User, Task, Tag, TaskBlock):
            assert db.scalar(select(func.count()).select_from(model)) == 0
        assert db.scalar(select(func.count()).select_from(Invitation)) == 1
    assert client.post("/api/auth/invitations/accept", json=payload).status_code == 201
    assert client.post("/api/auth/invitations/accept", json=payload).status_code == 400
    with SessionLocal() as db:
        assert db.scalar(select(func.count()).select_from(User)) == 1
        assert db.scalar(select(func.count()).select_from(Task)) == 4
        assert db.scalar(select(func.count()).select_from(Tag)) == 7


def test_operator_created_accounts_get_the_same_examples(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(cli, "read_password", lambda *_args: "correct horse")
    args = cli.build_parser().parse_args(
        [
            "create-user",
            "--email",
            "cli@example.com",
            "--display-name",
            "CLI User",
        ]
    )
    args.handler(args)
    assert (
        client.post(
            "/api/auth/login", json={"email": "cli@example.com", "password": "correct horse"}
        ).status_code
        == 200
    )
    assert len(client.get("/api/tags").json()) == 7
    assert len(client.get("/api/tasks").json()) == 4
    assert next_tasks(client)[0]["title"] == TITLES[0]
    assert client.get("/api/auth/email").json()["verified"] is False
    with pytest.raises(SystemExit, match="already exists"):
        args.handler(args)
    assert len(client.get("/api/tasks").json()) == 4


@pytest.mark.parametrize(
    "created_at", [datetime(2024, 2, 25, 12, tzinfo=UTC), datetime(2025, 12, 28, 12, tzinfo=UTC)]
)
def test_example_deadline_uses_account_date_across_calendar_boundaries(
    created_at: datetime,
) -> None:
    with SessionLocal() as db:
        user = User(
            email="calendar@example.com",
            display_name="Calendar",
            password_hash="unused",
            created_at=created_at,
        )
        db.add(user)
        add_onboarding_data(db, user)
        db.commit()
        tasks = db.scalars(select(Task)).all()
        assert {task.due_date for task in tasks if task.due_date} == {
            created_at.astimezone().date() + timedelta(days=7)
        }
