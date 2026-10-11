"""Background Automation loop that publishes due scheduled posts."""

import asyncio
import logging
from datetime import datetime, timedelta, timezone
from typing import Optional

from sqlalchemy.orm import Session

from app.config import get_settings
from app.database.session import SessionLocal
from app.models.post import Post
from app.services import log_service, post_service, settings_service
from app.services.facebook.exceptions import FacebookError
from app.services.facebook.publisher import publish_post

logger = logging.getLogger("pod-automation")


def _utcnow() -> datetime:
    """Return the current timezone-aware UTC datetime."""
    return datetime.now(timezone.utc)


class Automation:
    """Single-task scheduler that publishes due posts sequentially."""

    def __init__(self) -> None:
        """Initialize scheduler state without starting any task."""
        self._task: Optional[asyncio.Task] = None
        self._lock = asyncio.Lock()
        self._in_flight: set[int] = set()
        self._stopping = False
        self.last_run_at: Optional[datetime] = None
        self.last_run_result: dict = {}
        self._interval_seconds = 30

    @property
    def running(self) -> bool:
        """Return True while the background task is alive."""
        return self._task is not None and not self._task.done()

    @property
    def tick_running(self) -> bool:
        """Return True while a tick currently holds the run lock."""
        return self._lock.locked()

    def start(self) -> None:
        """Start the background loop task (idempotent)."""
        if self.running:
            return
        self._stopping = False
        self._interval_seconds = max(10, get_settings().SCHEDULER_INTERVAL_SECONDS)
        self._task = asyncio.create_task(self._loop(), name="automation")
        logger.info(
            "Automation started with interval %s seconds.", self._interval_seconds
        )

    async def stop(self) -> None:
        """Stop the background loop gracefully."""
        self._stopping = True
        task, self._task = self._task, None
        if task is None:
            return
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass
        logger.info("Automation stopped.")

    def status(self) -> dict:
        """Return scheduler status as JSON-serializable data."""
        settings = get_settings()
        next_run: Optional[str] = None
        if self.running and self.last_run_at is not None:
            next_run = (self.last_run_at + timedelta(seconds=self._interval_seconds)).isoformat()
        return {
            "running": self.running,
            "enabled": settings.SCHEDULER_ENABLED,
            "interval_seconds": self._interval_seconds,
            "last_run_at": self.last_run_at.isoformat() if self.last_run_at else None,
            "last_run_result": dict(self.last_run_result),
            "next_run_at": next_run,
        }

    async def _loop(self) -> None:
        """Run ticks forever until stopped; never let errors escape."""
        while not self._stopping:
            try:
                await self._tick()
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.exception("Automation tick failed; continuing.")
            interval = max(10, get_settings().SCHEDULER_INTERVAL_SECONDS)
            self._interval_seconds = interval
            for _ in range(interval):
                if self._stopping:
                    break
                await asyncio.sleep(1)

    async def _tick(self) -> dict:
        """Perform one publishing tick under the run lock."""
        async with self._lock:
            settings = get_settings()
            db = SessionLocal()
            try:
                posting = settings_service.get_setting(db, "posting_enabled", "false")
                if str(posting).lower() != "true":
                    result: dict = {
                        "published": 0,
                        "failed": 0,
                        "skipped": 0,
                        "skipped_reason": "posting_disabled",
                    }
                    self._record_run(result)
                    return result
                if settings_service.is_kill_switch_active(db):
                    # Layer 1: scheduler refuses to start work while stopped.
                    # Layer 2 (publisher.publish_post) blocks direct publishes too.
                    log_service.add_log(
                        db,
                        "kill_switch_blocked",
                        "Automation tick blocked: emergency stop is active.",
                        level="WARNING",
                    )
                    result = {
                        "published": 0,
                        "failed": 0,
                        "skipped": 0,
                        "skipped_reason": "kill_switch_active",
                    }
                    self._record_run(result)
                    return result
                self._run_maintenance(db)
                batch = max(1, settings.SCHEDULER_BATCH_SIZE)
                max_attempts = max(1, settings.PUBLISH_MAX_ATTEMPTS)
                due = post_service.get_due_scheduled_posts(db, _utcnow())[:batch]
                published = 0
                failed = 0
                skipped = 0
                for index, post in enumerate(due):
                    if post.id in self._in_flight:
                        skipped += 1
                        continue
                    if post.status == "failed" and (post.publish_attempts or 0) >= max_attempts:
                        skipped += 1
                        continue
                    self._in_flight.add(post.id)
                    try:
                        await publish_post(db, post.id)
                        published += 1
                    except (FacebookError, ValueError) as exc:
                        failed += 1
                        logger.warning(
                            "Automation publish of post %s failed: %s.", post.id, exc
                        )
                    except Exception:
                        failed += 1
                        logger.exception(
                            "Automation publish of post %s crashed.", post.id
                        )
                    finally:
                        self._in_flight.discard(post.id)
                    if index < len(due) - 1:
                        await asyncio.sleep(2)
                result = {
                    "published": published,
                    "failed": failed,
                    "skipped": skipped,
                }
                self._record_run(result)
                return result
            finally:
                db.close()

    def _run_maintenance(self, db: Session) -> None:
        """Hourly backup check + daily log prune. Best-effort, never fatal."""
        from app.services import backup_service

        try:
            backup_service.scheduled_backup_if_due(db)
        except Exception:
            logger.exception("Scheduled backup failed; continuing tick.")
        try:
            today = _utcnow().date().isoformat()
            if getattr(self, "_last_prune_day", None) != today:
                retention_raw = settings_service.get_setting(db, "log_retention_days", "30")
                try:
                    retention = max(1, min(365, int(str(retention_raw))))
                except (TypeError, ValueError):
                    retention = 30
                pruned = log_service.prune_old_logs(db, retention)
                if pruned:
                    logger.info("Pruned %s old activity logs.", pruned)
                self._last_prune_day = today
        except Exception:
            logger.exception("Log prune failed; continuing tick.")

    def _record_run(self, result: dict) -> None:
        """Store the outcome and timestamp of a tick."""
        self.last_run_at = _utcnow()
        self.last_run_result = dict(result)
        logger.info("Automation tick finished: %s.", result)

    async def run_once(self) -> dict:
        """Perform one tick on demand and return its result."""
        return await self._tick()

    def fill_queue(self, db: Session) -> dict:
        """Auto-schedule oldest drafts into posting-hour slots for 7 days."""
        per_day_raw = settings_service.get_setting(db, "posts_per_day", "1")
        try:
            per_day = max(1, int(str(per_day_raw)))
        except (TypeError, ValueError):
            per_day = 1
        hours_raw = settings_service.get_setting(db, "posting_hours", "09:00,18:00")
        hours: list[tuple[int, int]] = []
        for part in str(hours_raw or "").split(","):
            piece = part.strip()
            if len(piece) == 5 and piece[2] == ":" and piece[:2].isdigit() and piece[3:].isdigit():
                hour, minute = int(piece[:2]), int(piece[3:])
                if 0 <= hour <= 23 and 0 <= minute <= 59:
                    hours.append((hour, minute))
        hours = sorted(set(hours))
        if not hours:
            hours = [(9, 0)]
        now = _utcnow()
        drafts = (
            db.query(Post)
            .filter(Post.status == "draft")
            .order_by(Post.created_at.asc(), Post.id.asc())
            .all()
        )
        scheduled_rows = (
            db.query(Post)
            .filter(Post.status == "scheduled")
            .filter(Post.scheduled_at.is_not(None))
            .all()
        )
        per_day_count: dict = {}
        for row in scheduled_rows:
            day = row.scheduled_at.date()
            per_day_count[day] = per_day_count.get(day, 0) + 1
        scheduled_total = 0
        slots_considered = 0
        queue = list(drafts)
        for day_offset in range(7):
            if not queue:
                break
            day = (now + timedelta(days=day_offset)).date()
            remaining = per_day - per_day_count.get(day, 0)
            if remaining <= 0:
                continue
            for hour, minute in hours:
                if not queue or remaining <= 0:
                    break
                slot = datetime(day.year, day.month, day.day, hour, minute, tzinfo=timezone.utc)
                if slot <= now:
                    continue
                slots_considered += 1
                draft = queue.pop(0)
                post_service.schedule_post(db, draft.id, slot)
                scheduled_total += 1
                remaining -= 1
        drafts_remaining = len(queue)
        log_service.add_log(
            db,
            "queue_filled",
            f"Automation filled queue: {scheduled_total} posts scheduled, "
            f"{drafts_remaining} drafts remaining.",
        )
        return {
            "scheduled": scheduled_total,
            "slots_considered": slots_considered,
            "drafts_remaining": drafts_remaining,
        }


automation = Automation()
"""Process-wide Automation singleton."""
