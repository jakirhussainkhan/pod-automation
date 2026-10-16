"""Publisher idempotency: a post can only be claimed/published once."""

from app.models import PostStatus
from app.models.post import Post


def test_publish_then_double_publish_is_rejected(client):
    created = client.post("/api/posts", json={"caption": "pytest publish"}).json()
    pid = created["id"]
    assert created["status"] == "draft"

    first = client.post(f"/api/posts/{pid}/publish")
    assert first.status_code == 200
    assert first.json()["status"] == "published"

    second = client.post(f"/api/posts/{pid}/publish")
    assert second.status_code == 400


def test_publishing_claim_blocks_reclaim(client, db):
    created = client.post("/api/posts", json={"caption": "in flight"}).json()
    pid = created["id"]

    # Simulate an in-flight claim (as the publisher writes before the network).
    post = db.get(Post, pid)
    post.status = PostStatus.publishing.value
    db.commit()

    resp = client.post(f"/api/posts/{pid}/publish")
    assert resp.status_code == 400


def test_publish_attempts_increment_on_claim(client, db):
    created = client.post("/api/posts", json={"caption": "attempts"}).json()
    pid = created["id"]
    client.post(f"/api/posts/{pid}/publish")
    db.expire_all()
    post = db.get(Post, pid)
    assert post.publish_attempts == 1


def test_empty_post_publish_does_not_burn_attempt(client, db):
    # Caption is required by the schema, so force an empty caption via ORM to
    # exercise the publisher's pre-claim validation.
    created = client.post("/api/posts", json={"caption": "placeholder"}).json()
    pid = created["id"]
    post = db.get(Post, pid)
    post.caption = "   "
    post.hashtags = []
    db.commit()

    resp = client.post(f"/api/posts/{pid}/publish")
    assert resp.status_code == 400
    db.expire_all()
    assert db.get(Post, pid).publish_attempts == 0
