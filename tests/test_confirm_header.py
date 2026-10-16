"""Destructive endpoints require the X-Confirm-Delete header."""


def test_single_post_delete_requires_header(client):
    pid = client.post("/api/posts", json={"caption": "delete me"}).json()["id"]

    denied = client.delete(f"/api/posts/{pid}")
    assert denied.status_code == 403

    ok = client.delete(f"/api/posts/{pid}", headers={"X-Confirm-Delete": "true"})
    assert ok.status_code == 204


def test_single_product_delete_requires_header(client):
    product = client.post(
        "/api/products", json={"title": "pytest product", "niche": "test"}
    ).json()
    pid = product["id"]

    denied = client.delete(f"/api/products/{pid}")
    assert denied.status_code == 403

    ok = client.delete(
        f"/api/products/{pid}", headers={"X-Confirm-Delete": "yes"}
    )
    assert ok.status_code == 204


def test_bulk_delete_requires_header(client):
    denied = client.post("/api/posts/bulk-delete", json={"ids": [1]})
    assert denied.status_code == 403
