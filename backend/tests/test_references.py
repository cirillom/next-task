def test_references_are_bounded_owner_scoped_and_include_drafts_and_tag_paths(logged_in_client):
    owner = logged_in_client("references-owner@example.com")
    other = logged_in_client("references-other@example.com")
    task = owner.post("/api/tasks", json={"title": "Task target", "description": "Private"}).json()
    draft = owner.post("/api/drafts", json={"title": "Draft target"}).json()
    parent = owner.post("/api/tags", json={"name": "Parent"}).json()
    second = owner.post("/api/tags", json={"name": "Second"}).json()
    tag = owner.post("/api/tags", json={"name": "Shared", "parent_tag_id": parent["id"]}).json()
    assert (
        owner.post(
            f"/api/tags/{tag['id']}/parents", json={"parent_tag_id": second["id"]}
        ).status_code
        == 201
    )
    foreign = other.post("/api/tasks", json={"title": "Secret target"}).json()

    results = owner.get("/api/references", params={"query": "target"}).json()
    assert {item["id"] for item in results} == {task["id"], draft["id"]}
    assert all("description" not in item for item in results)
    result = owner.get("/api/references", params={"query": "Shared"}).json()[0]
    assert result["paths"] == ["Parent › Shared", "Second › Shared"]
    assert owner.get("/api/references", params={"query": "9" * 120}).status_code == 200
    assert owner.get("/api/references", params={"limit": 51}).status_code == 422
    assert owner.get("/api/references", params={"query": "x" * 121}).status_code == 422

    keys = [
        {"kind": "task", "id": task["id"]},
        {"kind": "task", "id": foreign["id"]},
        {"kind": "task", "id": 999999},
        {"kind": "tag", "id": tag["id"]},
    ]
    resolved = owner.post("/api/references/resolve", json={"items": keys + keys[:1]}).json()
    assert len(resolved) == 4
    assert resolved[0]["label"] == "Task target"
    assert resolved[1]["label"] is None and resolved[2]["label"] is None
    assert resolved[3]["paths"] == ["Parent › Shared", "Second › Shared"]
    assert owner.post("/api/references/resolve", json={"items": keys * 26}).status_code == 422
