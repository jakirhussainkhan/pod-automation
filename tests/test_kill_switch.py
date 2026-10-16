"""Kill switch blocks publishing at the publisher layer."""


def test_kill_switch_blocks_publish(client):
    pid = client.post("/api/posts", json={"caption": "blocked by kill"}).json()["id"]

    engage = client.post(
        "/api/system/kill-switch",
        json={"active": True},
        headers={"X-Confirm-Delete": "true"},
    )
    assert engage.status_code == 200
    assert engage.json()["kill_switch_active"] is True

    try:
        blocked = client.post(f"/api/posts/{pid}/publish")
        assert blocked.status_code == 400
    finally:
        release = client.post("/api/system/kill-switch", json={"active": False})
        assert release.status_code == 200

    # Once released, publishing works again.
    ok = client.post(f"/api/posts/{pid}/publish")
    assert ok.status_code == 200


def test_engaging_kill_switch_requires_header(client):
    resp = client.post("/api/system/kill-switch", json={"active": True})
    assert resp.status_code == 403
    # Ensure it is not left engaged.
    client.post("/api/system/kill-switch", json={"active": False})
