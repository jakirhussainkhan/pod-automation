"""Shared pytest fixtures.

Environment is configured *before* importing the app so an isolated temp
SQLite database, mock AI provider and dry-run publishing are used. No test ever
talks to Groq/OpenAI/Facebook or touches the real ``data/automation.db``.
"""

import os
import tempfile
from pathlib import Path

_TMP = Path(tempfile.mkdtemp(prefix="pod-tests-"))
os.environ["DATABASE_URL"] = f"sqlite:///{_TMP / 'test.db'}"
os.environ["SCHEDULER_ENABLED"] = "false"
os.environ["AI_MOCK_MODE"] = "true"
os.environ["FACEBOOK_DRY_RUN"] = "true"
os.environ["APP_ENV"] = "development"
os.environ["FACEBOOK_PAGE_ACCESS_TOKEN"] = "FAKE_TOKEN_ABC123"
os.environ["LOG_LEVEL"] = "WARNING"

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402


@pytest.fixture(scope="session")
def client():
    """A TestClient with the app lifespan (init_db + seed) active."""
    from app.main import app

    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture()
def db():
    """A short-lived SQLAlchemy session against the temp database."""
    from app.database.session import SessionLocal

    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()
