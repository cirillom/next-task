from collections.abc import Callable

from fastapi.testclient import TestClient


def create_tag(client: TestClient, name: str, parent_id: int | None = None) -> dict:
    response = client.post(
        "/api/tags", json={"name": name, "parent_tag_id": parent_id}
    )
    assert response.status_code == 201, response.text
    return response.json()


def test_names_are_unique_per_direct_parent_and_display_with_context(
    logged_in_client: Callable[[str], TestClient],
) -> None:
    client = logged_in_client("owner@example.com")
    work = create_tag(client, "Work")
    personal = create_tag(client, "Personal")
    root = create_tag(client, "Review")
    work_review = create_tag(client, "Review", work["id"])
    personal_review = create_tag(client, "review", personal["id"])

    assert client.post("/api/tags", json={"name": "REVIEW"}).status_code == 409
    assert (
        client.post("/api/tags", json={"name": "REVIEW", "parent_tag_id": work["id"]})
        .status_code
        == 409
    )

    by_id = {tag["id"]: tag for tag in client.get("/api/tags").json()}
    assert by_id[root["id"]]["display_name"] == "Review"
    assert by_id[work_review["id"]]["display_name"] == "Review (Work)"
    assert by_id[personal_review["id"]]["display_name"] == "review (Personal)"

    task = client.post(
        "/api/tasks",
        json={"title": "Check", "tag_ids": [work_review["id"], personal_review["id"]]},
    )
    assert task.status_code == 201, task.text
    assert {tag["display_name"] for tag in task.json()["direct_tags"]} == {
        "Review (Work)",
        "review (Personal)",
    }


def test_renames_and_parent_changes_keep_sibling_names_unique(
    logged_in_client: Callable[[str], TestClient],
) -> None:
    client = logged_in_client("owner@example.com")
    work = create_tag(client, "Work")
    personal = create_tag(client, "Personal")
    create_tag(client, "Review")
    create_tag(client, "Review", work["id"])
    work_check = create_tag(client, "Check", work["id"])
    personal_check = create_tag(client, "Check", personal["id"])

    assert (
        client.patch(f"/api/tags/{work_check['id']}", json={"name": "REVIEW"}).status_code
        == 409
    )
    assert (
        client.patch(f"/api/tags/{personal_check['id']}", json={"name": "review"})
        .status_code
        == 200
    )
    assert (
        client.post(
            f"/api/tags/{personal_check['id']}/parents",
            json={"parent_tag_id": work["id"]},
        ).status_code
        == 409
    )
    assert (
        client.delete(f"/api/tags/{personal_check['id']}/parents/{personal['id']}")
        .status_code
        == 409
    )
    assert client.delete(f"/api/tags/{personal['id']}").status_code == 409
    assert client.get(
        f"/api/tags/{work['id']}/merge-preview",
        params={"destination_tag_id": personal["id"]},
    ).status_code == 422


def test_duplicate_parent_names_use_full_path(
    logged_in_client: Callable[[str], TestClient],
) -> None:
    client = logged_in_client("owner@example.com")
    work = create_tag(client, "Work")
    personal = create_tag(client, "Personal")
    work_phase = create_tag(client, "Phase", work["id"])
    personal_phase = create_tag(client, "Phase", personal["id"])
    work_review = create_tag(client, "Review", work_phase["id"])
    personal_review = create_tag(client, "Review", personal_phase["id"])

    tags = {tag["id"]: tag for tag in client.get("/api/tags").json()}
    assert tags[work_review["id"]]["display_name"] == "Review (Work › Phase)"
    assert tags[personal_review["id"]]["display_name"] == "Review (Personal › Phase)"


def test_display_names_stay_distinct_when_a_base_name_mimics_a_suffix(
    logged_in_client: Callable[[str], TestClient],
) -> None:
    client = logged_in_client("owner@example.com")
    work = create_tag(client, "Work")
    create_tag(client, "Review")
    nested = create_tag(client, "Review", work["id"])
    literal = create_tag(client, "Review (Work)")

    tags = {tag["id"]: tag for tag in client.get("/api/tags").json()}
    assert tags[nested["id"]]["display_name"] != tags[literal["id"]]["display_name"]
