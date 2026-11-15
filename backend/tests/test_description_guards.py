from concurrent.futures import ThreadPoolExecutor
from threading import Barrier

import pytest


@pytest.mark.parametrize("kind", ["tasks", "tags"])
def test_guarded_description_updates_are_atomic_and_owner_scoped(logged_in_client, kind):
    owner = logged_in_client(f"{kind}@example.com")
    other = logged_in_client(f"other-{kind}@example.com")
    name_field = "title" if kind == "tasks" else "name"
    created = owner.post(f"/api/{kind}", json={name_field: "Original"})
    assert created.status_code == 201
    item_id = created.json()["id"]
    url = f"/api/{kind}/{item_id}"

    first = owner.patch(url, json={"description": "First", "expected_description": None})
    assert first.status_code == 200
    stale = owner.patch(
        url,
        json={"description": "Stale", "expected_description": None, name_field: "Changed"},
    )
    assert stale.status_code == 409
    current = owner.get(url).json() if kind == "tasks" else owner.get("/api/tags").json()[0]
    assert current["description"] == "First"
    assert current[name_field] == "Original"
    foreign = other.patch(url, json={"description": "Foreign", "expected_description": "First"})
    assert foreign.status_code == 404

    renamed = owner.patch(url, json={name_field: "Renamed", "expected_description": "Unrelated"})
    assert renamed.status_code == 200
    second = owner.patch(url, json={"description": "Second", "expected_description": "First"})
    assert second.status_code == 200
    assert second.json()["description"] == "Second"
    assert owner.patch(url, json={"description": "Legacy"}).json()["description"] == "Legacy"


def test_task_conflict_does_not_change_tags_and_draft_creation_excludes_guard(logged_in_client):
    client = logged_in_client("draft@example.com")
    tag = client.post("/api/tags", json={"name": "New tag"}).json()
    draft = client.post(
        "/api/drafts",
        json={"title": "Draft", "description": "Notes", "expected_description": None},
    )
    assert draft.status_code == 201
    assert draft.json()["priority"] == 0
    url = f"/api/tasks/{draft.json()['id']}"
    conflict = client.patch(
        url, json={"description": "Lost", "expected_description": None, "tag_ids": [tag["id"]]}
    )
    assert conflict.status_code == 409
    current = client.get(url).json()
    assert current["description"] == "Notes"
    assert current["direct_tags"] == []
    assert current["priority"] == 0


@pytest.mark.parametrize("kind", ["tasks", "tags"])
def test_two_simultaneous_description_writes_have_one_winner(logged_in_client, kind):
    client = logged_in_client(f"concurrent-{kind}@example.com")
    name_field = "title" if kind == "tasks" else "name"
    item = client.post(f"/api/{kind}", json={name_field: "Item", "description": "Base"}).json()
    barrier = Barrier(2)

    def change(description):
        barrier.wait(timeout=10)
        return client.patch(
            f"/api/{kind}/{item['id']}",
            json={"description": description, "expected_description": "Base"},
        ).status_code

    with ThreadPoolExecutor(max_workers=2) as executor:
        statuses = list(executor.map(change, ["First", "Second"]))
    assert sorted(statuses) == [200, 409]
