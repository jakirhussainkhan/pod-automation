"""Post schema validation: URL scheme + reserved statuses."""


def test_non_http_image_url_rejected(client):
    resp = client.post(
        "/api/posts", json={"caption": "img", "image_url": "ftp://evil/x.png"}
    )
    assert resp.status_code == 422


def test_http_image_url_accepted(client):
    resp = client.post(
        "/api/posts",
        json={"caption": "img", "image_url": "https://example.com/a.png"},
    )
    assert resp.status_code == 201
    assert resp.json()["image_url"] == "https://example.com/a.png"


def test_forged_published_status_on_create_is_ignored(client):
    resp = client.post("/api/posts", json={"caption": "forge", "status": "published"})
    assert resp.status_code == 201
    assert resp.json()["status"] == "draft"


def test_patch_to_published_status_rejected(client):
    pid = client.post("/api/posts", json={"caption": "patch"}).json()["id"]
    resp = client.patch(f"/api/posts/{pid}", json={"status": "published"})
    assert resp.status_code == 422


def test_unknown_tone_rejected(client):
    resp = client.post("/api/ai/generate", json={"product_id": 1, "tone": "bogus"})
    assert resp.status_code == 422
