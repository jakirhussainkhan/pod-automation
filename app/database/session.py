"""SQLAlchemy engine and session factory."""

from pathlib import Path
from typing import Generator

from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session, sessionmaker

from app.config import BASE_DIR, get_settings


def _ensure_data_dir() -> None:
    """Ensure the data directory exists before engine creation."""
    data_dir: Path = BASE_DIR / "data"
    data_dir.mkdir(parents=True, exist_ok=True)


_ensure_data_dir()

_settings = get_settings()

_engine_kwargs: dict = {"pool_pre_ping": True}
# check_same_thread/timeout are SQLite-only; don't pass them for Postgres/etc.
if _settings.DATABASE_URL.startswith("sqlite"):
    _engine_kwargs["connect_args"] = {
        "check_same_thread": False,
        # Python sqlite3-level busy wait (seconds) as a first line of defense.
        "timeout": 30.0,
    }

engine = create_engine(_settings.DATABASE_URL, **_engine_kwargs)
"""SQLAlchemy engine configured from settings."""


@event.listens_for(engine, "connect")
def _set_sqlite_pragmas(dbapi_connection, connection_record) -> None:
    """Apply SQLite pragmas on each new DBAPI connection."""
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.execute("PRAGMA journal_mode=WAL")
    cursor.execute("PRAGMA synchronous=NORMAL")
    # Wait up to 5s on locked pages so background scheduler ticks don't
    # raise "database is locked" while a request holds a write transaction.
    cursor.execute("PRAGMA busy_timeout = 5000")
    cursor.close()


SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
"""Session factory for request-scoped sessions."""


def get_db() -> Generator[Session, None, None]:
    """Yield a request-scoped session; rollback on error, always close."""
    db: Session = SessionLocal()
    try:
        yield db
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()
