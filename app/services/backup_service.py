"""SQLite backup service: atomic snapshots + retention pruning."""

import logging
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional

from sqlalchemy.orm import Session

from app.config import BASE_DIR, get_settings
from app.models.system import DbBackup

logger = logging.getLogger("pod-automation")

_RESTORE_CONFIRM_TEXT = "RESTORE BACKUP"
"""Exact confirmation string required for backup restores."""


def _source_db_path() -> Path:
    """Resolve the live SQLite file from DATABASE_URL."""
    url = get_settings().DATABASE_URL
    path = url[len("sqlite:///"):] if url.startswith("sqlite:///") else url
    candidate = Path(path)
    if not candidate.is_absolute():
        candidate = BASE_DIR / candidate
    return candidate


def _backup_dir() -> Path:
    """Return the backups directory, creating it on demand."""
    target = BASE_DIR / "data" / "backups"
    target.mkdir(parents=True, exist_ok=True)
    return target


def _backup_settings(db: Session) -> tuple[bool, int]:
    """Read (enabled, keep_last) with safe fallbacks."""
    from app.services import settings_service

    try:
        enabled = str(settings_service.get_setting(db, "backup_enabled", "true")).strip().lower() != "false"
    except Exception:
        enabled = True
    try:
        keep = int(str(settings_service.get_setting(db, "backup_keep_last", "7")).strip())
        keep = max(1, min(30, keep))
    except (TypeError, ValueError, AttributeError):
        keep = 7
    return enabled, keep


def run_backup(db: Session, trigger: str = "manual") -> dict:
    """Snapshot the live DB atomically and prune beyond retention.

    Writes to ``.tmp`` then renames so no partial file ever survives.
    Uses the sqlite3 backup API, safe against a live writer.
    """
    mode = (trigger or "manual").strip().lower()
    if mode not in ("scheduled", "manual", "pre-restore"):
        mode = "manual"
    source = _source_db_path()
    if not source.exists():
        raise ValueError(f"Live database not found at {source}.")
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    # Unique filename: same-second runs (manual + scheduled) must never
    # collide — Windows rename refuses to overwrite, so loop until free.
    counter = 0
    while True:
        suffix = f"_{counter}" if counter else ""
        filename = f"automation_{stamp}{suffix}.db"
        final_path = _backup_dir() / filename
        if not final_path.exists():
            break
        counter += 1
    tmp_path = final_path.with_suffix(final_path.suffix + ".tmp")
    try:
        if tmp_path.exists():
            tmp_path.unlink()
    except Exception:
        pass
    try:
        src = sqlite3.connect(str(source))
        try:
            dst = sqlite3.connect(str(tmp_path))
            try:
                src.backup(dst)
            finally:
                dst.close()
        finally:
            src.close()
        # replace() overwrites atomically; final_path is guaranteed fresh
        # by the loop above, so no good backup is ever clobbered.
        tmp_path.replace(final_path)
        size_bytes = final_path.stat().st_size
    except Exception:
        try:
            if tmp_path.exists():
                tmp_path.unlink()
        except Exception:
            pass
        logger.exception("DB backup failed.")
        try:
            failed = DbBackup(
                filename=filename, file_path=str(final_path),
                size_bytes=0, trigger=mode, status="failed",
                error_message="Backup file write failed; see server logs.",
            )
            db.add(failed)
            db.commit()
        except Exception:
            db.rollback()
        raise
    try:
        record = DbBackup(
            filename=filename, file_path=str(final_path),
            size_bytes=size_bytes, trigger=mode, status="ok",
        )
        db.add(record)
        db.commit()
        db.refresh(record)
    except Exception:
        db.rollback()
        logger.exception("Backup row insert failed; removing orphan file.")
        try:
            if final_path.exists():
                final_path.unlink()
        except Exception:
            pass
        raise
    pruned = prune_backups(db)
    kept = db.query(DbBackup).filter(DbBackup.status == "ok").count()
    return {
        "id": record.id,
        "filename": filename,
        "size_bytes": size_bytes,
        "kept_count": kept,
        "pruned_count": pruned,
    }


def prune_backups(db: Session) -> int:
    """Delete backup files + rows beyond the keep-last window."""
    _, keep = _backup_settings(db)
    try:
        stale = (
            db.query(DbBackup)
            .filter(DbBackup.status == "ok")
            .order_by(DbBackup.id.desc())
            .offset(keep)
            .all()
        )
        removed = 0
        for row in stale:
            try:
                candidate = Path(row.file_path)
                if candidate.exists():
                    candidate.unlink()
            except Exception:
                logger.exception("Failed to delete stale backup file %s.", row.file_path)
                continue
            db.delete(row)
            removed += 1
        db.commit()
        return removed
    except Exception:
        db.rollback()
        logger.exception("Backup pruning failed.")
        raise


def list_backups(db: Session, limit: int = 50) -> list[dict]:
    """List recent backups newest-first."""
    rows = (
        db.query(DbBackup)
        .order_by(DbBackup.id.desc())
        .limit(max(1, min(200, int(limit))))
        .all()
    )
    return [
        {
            "id": row.id,
            "filename": row.filename,
            "size_bytes": int(row.size_bytes or 0),
            "trigger": row.trigger,
            "status": row.status,
            "error_message": row.error_message,
            "created_at": row.created_at.isoformat() if row.created_at else None,
            "exists": Path(row.file_path).exists(),
        }
        for row in rows
    ]


def delete_backup(db: Session, backup_id: int) -> None:
    """Remove a backup file + its row. Rollback if the file delete fails."""
    row = db.get(DbBackup, backup_id)
    if row is None:
        raise ValueError(f"Backup {backup_id} not found.")
    try:
        candidate = Path(row.file_path)
        if candidate.exists():
            candidate.unlink()
        db.delete(row)
        db.commit()
    except Exception:
        db.rollback()
        logger.exception("Backup delete failed for %s.", backup_id)
        raise


def restore_backup(backup_id: int, db: Session) -> dict:
    """Restore a backup into the live DB. Never auto-restarts the app.

    A pre-restore snapshot MUST succeed first; otherwise the restore
    aborts. Uses the sqlite3 backup API (target-side) so the restore
    works while the app holds the live file open — no file replace,
    no lock fights. The caller must restart the process afterwards.
    """
    row = db.get(DbBackup, backup_id)
    if row is None:
        raise ValueError(f"Backup {backup_id} not found.")
    source = Path(row.file_path)
    if not source.exists():
        raise ValueError(f"Backup file for {backup_id} is missing from disk.")
    try:
        pre = run_backup(db, trigger="pre-restore")
    except Exception as exc:
        raise ValueError(f"Pre-restore backup failed, aborting: {exc}")
    live = _source_db_path()
    try:
        src = sqlite3.connect(str(source))
        try:
            dst = sqlite3.connect(str(live), timeout=30.0)
            try:
                src.backup(dst)
            finally:
                dst.close()
        finally:
            src.close()
        # Force pooled connections onto the restored content.
        try:
            from app.database.session import engine

            engine.dispose()
        except Exception:
            pass
    except Exception:
        logger.exception("Backup restore failed.")
        raise ValueError(
            "Restore failed while copying into the live database. "
            "Stop the app and copy the backup file manually."
        )
    logger.warning("Database restored from %s; restart required.", row.filename)
    return {
        "pre_restore_backup": pre["filename"],
        "restored_from": row.filename,
        "restart_required": True,
    }


def last_backup_at(db: Session) -> Optional[datetime]:
    """Return the newest successful backup time, or None."""
    row = (
        db.query(DbBackup)
        .filter(DbBackup.status == "ok")
        .order_by(DbBackup.id.desc())
        .first()
    )
    if row is None or row.created_at is None:
        return None
    stamp = row.created_at
    if stamp.tzinfo is None:
        stamp = stamp.replace(tzinfo=timezone.utc)
    return stamp


def scheduled_backup_if_due(db: Session) -> Optional[dict]:
    """Run the daily backup when the UTC hour matches and none is fresh."""
    from app.services import settings_service

    try:
        enabled, _ = _backup_settings(db)
        if not enabled:
            return None
        try:
            hour = int(str(settings_service.get_setting(db, "backup_hour_utc", "3")).strip())
        except (TypeError, ValueError, AttributeError):
            hour = 3
        if datetime.now(timezone.utc).hour != hour:
            return None
        latest = last_backup_at(db)
        if latest is not None and datetime.now(timezone.utc) - latest < timedelta(hours=23):
            return None
        return run_backup(db, trigger="scheduled")
    except Exception:
        logger.exception("Scheduled backup check failed.")
        return None
