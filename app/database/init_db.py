"""Database initialization helpers."""

import logging

from sqlalchemy import text

logger = logging.getLogger("pod-automation")


_ALLOWED_TABLES = {
    "products",
    "posts",
    "group_leads",
    "group_post_queue",
    "activity_logs",
    "ai_generations",
    "app_settings",
    "fb_accounts",
    "group_stats",
    "db_backups",
    "ai_usage",
    "account_groups_blocked",
}


def _quote_ident(name: str) -> str:
    """Quote a SQLite identifier, escaping embedded double quotes."""
    return '"' + str(name).replace('"', '""') + '"'


def _utcnow_iso() -> str:
    """Return the current UTC time as an ISO string for seed inserts."""
    from datetime import datetime, timezone

    return datetime.now(timezone.utc).isoformat()


def _ensure_table_columns(connection, dialect, table_name: str, model) -> None:
    """Add any missing model columns to an existing SQLite table idempotently."""
    from sqlalchemy import inspect

    if table_name not in _ALLOWED_TABLES:
        raise ValueError(f"Refusing to migrate unexpected table: {table_name!r}")
    existing = {column["name"] for column in inspect(connection).get_columns(table_name)}
    pending: list[str] = []
    for column in model.__table__.columns:
        if column.name in existing or column.primary_key:
            continue
        column_type = str(column.type.compile(dialect=dialect))
        clause = (
            f"ALTER TABLE {_quote_ident(table_name)} ADD COLUMN "
            f"{_quote_ident(column.name)} {column_type}"
        )
        if not column.nullable:
            from sqlalchemy import Date, DateTime, Time

            default = None
            if column.default is not None and not callable(
                getattr(column.default, "arg", None)
            ):
                default = column.default.arg
            elif column.server_default is not None:
                default = str(column.server_default.arg)
            if default is None:
                # A Python-callable default (e.g. datetime.now) can't be inlined
                # into DDL; a timestamp column must fall back to SQLite's
                # CURRENT_TIMESTAMP instead of the literal 0.
                default = (
                    "CURRENT_TIMESTAMP"
                    if isinstance(column.type, (DateTime, Date, Time))
                    else 0
                )
            if str(default).strip().upper() == "CURRENT_TIMESTAMP":
                pending.append(clause + " NOT NULL DEFAULT CURRENT_TIMESTAMP")
                continue
            try:
                default_num = float(default)
                default_sql = (
                    str(default_num) if "." in str(default) else str(int(default_num))
                )
            except (TypeError, ValueError):
                escaped = str(default).replace("'", "''")
                default_sql = f"'{escaped}'"
            clause += f" NOT NULL DEFAULT {default_sql}"
        pending.append(clause)
    if not pending:
        return
    try:
        for clause in pending:
            connection.execute(text(clause))
        connection.commit()
    except Exception:
        connection.rollback()
        logger.exception("Schema migration failed for %s.", table_name)
        raise
    for clause in pending:
        logger.info("Executed schema migration: %s.", clause)


def ensure_schema() -> None:
    """Migrate existing SQLite databases idempotently (incl. is_demo flags)."""
    from sqlalchemy import inspect as sa_inspect

    from app.database.base import Base
    from app.database.session import engine
    from app.models.fb_account import FbAccount
    from app.models.group_lead import GroupLead
    from app.models.group_post_queue import GroupPostQueue
    from app.models.group_stats import GroupStats
    from app.models.post import Post
    from app.models.product import Product
    from app.models.system import AiUsage, DbBackup

    # Create group-engine tables when opening a database made before them.
    Base.metadata.tables["group_leads"].create(bind=engine, checkfirst=True)
    Base.metadata.tables["group_post_queue"].create(bind=engine, checkfirst=True)
    # Soft-delete support: create activity_logs on very old DBs, then add
    # snapshot/entity/restored columns to existing tables.
    Base.metadata.tables["activity_logs"].create(bind=engine, checkfirst=True)
    # DM Safety layer: per-account quota counters.
    Base.metadata.tables["fb_accounts"].create(bind=engine, checkfirst=True)
    # Health dashboard: one snapshot row per calendar day.
    Base.metadata.tables["group_stats"].create(bind=engine, checkfirst=True)
    # Production hardening: backup log + AI usage ledger.
    Base.metadata.tables["db_backups"].create(bind=engine, checkfirst=True)
    Base.metadata.tables["ai_usage"].create(bind=engine, checkfirst=True)
    # Multi-account collision prevention.
    Base.metadata.tables["account_groups_blocked"].create(bind=engine, checkfirst=True)

    with engine.connect() as connection:
        tables = set(sa_inspect(connection).get_table_names())
        if "products" in tables:
            _ensure_table_columns(connection, engine.dialect, "products", Product)
        if "posts" in tables:
            _ensure_table_columns(connection, engine.dialect, "posts", Post)
        if "group_leads" in tables:
            _ensure_table_columns(connection, engine.dialect, "group_leads", GroupLead)
        if "group_post_queue" in tables:
            _ensure_table_columns(connection, engine.dialect, "group_post_queue", GroupPostQueue)
        if "activity_logs" in tables:
            from app.models.activity_log import ActivityLog

            _ensure_table_columns(
                connection, engine.dialect, "activity_logs", ActivityLog
            )
        if "fb_accounts" in tables:
            _ensure_table_columns(connection, engine.dialect, "fb_accounts", FbAccount)
        if "group_stats" in tables:
            _ensure_table_columns(connection, engine.dialect, "group_stats", GroupStats)
        if "db_backups" in tables:
            _ensure_table_columns(connection, engine.dialect, "db_backups", DbBackup)
        if "ai_usage" in tables:
            _ensure_table_columns(connection, engine.dialect, "ai_usage", AiUsage)
        if "account_groups_blocked" in tables:
            from app.models.fb_account import AccountGroupBlocked

            _ensure_table_columns(
                connection, engine.dialect, "account_groups_blocked", AccountGroupBlocked
            )
        # Seed ONE default account when the table is empty (idempotent).
        try:
            count = connection.execute(
                text(f"SELECT COUNT(*) FROM {_quote_ident('fb_accounts')}")
            ).scalar() or 0
            if int(count) == 0:
                connection.execute(
                    text(
                        f"INSERT INTO {_quote_ident('fb_accounts')} "
                        f"({_quote_ident('name')}, {_quote_ident('profile_url')}, "
                        f"{_quote_ident('daily_dm_count')}, {_quote_ident('hourly_dm_count')}, "
                        f"{_quote_ident('last_hourly_reset_at')}, {_quote_ident('last_daily_reset_at')}, "
                        f"{_quote_ident('daily_limit')}, {_quote_ident('hourly_limit')}, "
                        f"{_quote_ident('is_active')}, {_quote_ident('created_at')}, "
                        f"{_quote_ident('updated_at')}) "
                        "VALUES (:name, NULL, 0, 0, :now_hourly, :now_daily, 20, 10, 1, :now_created, :now_updated)"
                    ),
                    {
                        "name": "Default Account",
                        "now_hourly": _utcnow_iso(),
                        "now_daily": _utcnow_iso(),
                        "now_created": _utcnow_iso(),
                        "now_updated": _utcnow_iso(),
                    },
                )
                logger.info("Seeded default fb_accounts row.")
            # Health backfill: label legacy queued posts + seed today's
            # snapshot when leads exist but no stats were ever logged.
            connection.execute(
                text(
                    f"UPDATE {_quote_ident('group_post_queue')} "
                    f"SET {_quote_ident('template_name')} = {_quote_ident('template')} "
                    f"WHERE {_quote_ident('template_name')} IS NULL"
                )
            )
            stats_count = connection.execute(
                text(f"SELECT COUNT(*) FROM {_quote_ident('group_stats')}")
            ).scalar() or 0
            leads_count = connection.execute(
                text(f"SELECT COUNT(*) FROM {_quote_ident('group_leads')}")
            ).scalar() or 0
            if int(stats_count) == 0 and int(leads_count) > 0:
                from datetime import date as _date

                connection.execute(
                    text(
                        f"INSERT INTO {_quote_ident('group_stats')} "
                        f"({_quote_ident('stat_date')}, {_quote_ident('member_count')}, "
                        f"{_quote_ident('new_members')}, {_quote_ident('posts_published')}, "
                        f"{_quote_ident('comments_received')}, {_quote_ident('leads_captured')}, "
                        f"{_quote_ident('m1_sent')}, {_quote_ident('m2_sent')}, "
                        f"{_quote_ident('converted')}, {_quote_ident('revenue')}, "
                        f"{_quote_ident('created_at')}, {_quote_ident('updated_at')}) "
                        "VALUES (:stat_date, 0, 0, "
                        "(SELECT COUNT(*) FROM "
                        f"{_quote_ident('group_post_queue')} "
                        f"WHERE date({_quote_ident('posted_at')}) = :stat_date), "
                        "0, "
                        "(SELECT COUNT(*) FROM "
                        f"{_quote_ident('group_leads')} "
                        f"WHERE date({_quote_ident('created_at')}) = :stat_date), "
                        "(SELECT COUNT(*) FROM "
                        f"{_quote_ident('group_leads')} "
                        f"WHERE date({_quote_ident('step1_sent_at')}) = :stat_date), "
                        "(SELECT COUNT(*) FROM "
                        f"{_quote_ident('group_leads')} "
                        f"WHERE date({_quote_ident('step2_sent_at')}) = :stat_date), "
                        "(SELECT COUNT(*) FROM "
                        f"{_quote_ident('group_leads')} "
                        f"WHERE {_quote_ident('status')} = 'converted' "
                        f"AND date({_quote_ident('updated_at')}) = :stat_date), "
                        "(SELECT COALESCE(SUM("
                        f"{_quote_ident('conversion_value')}), 0.0) FROM "
                        f"{_quote_ident('group_leads')} "
                        f"WHERE {_quote_ident('status')} = 'converted' "
                        f"AND date({_quote_ident('updated_at')}) = :stat_date), "
                        ":now, :now)"
                    ),
                    {"stat_date": _date.today().isoformat(), "now": _utcnow_iso()},
                )
                logger.info("Backfilled today's group_stats snapshot.")
            # Phase 5: single-row persona backfill + orphan lead assignment.
            fb_count = connection.execute(
                text(f"SELECT COUNT(*) FROM {_quote_ident('fb_accounts')}")
            ).scalar() or 0
            if int(fb_count) == 1:
                connection.execute(
                    text(
                        f"UPDATE {_quote_ident('fb_accounts')} "
                        f"SET {_quote_ident('persona_name')} = COALESCE({_quote_ident('persona_name')}, {_quote_ident('name')}), "
                        f"{_quote_ident('persona_tone')} = COALESCE({_quote_ident('persona_tone')}, 'enthusiast'), "
                        f"{_quote_ident('niche_focus')} = COALESCE({_quote_ident('niche_focus')}, 'mixed'), "
                        f"{_quote_ident('health_status')} = COALESCE({_quote_ident('health_status')}, 'healthy'), "
                        f"{_quote_ident('priority')} = COALESCE({_quote_ident('priority')}, 100)"
                    )
                )
                logger.info("Backfilled default account persona fields.")
            default_id = connection.execute(
                text(
                    f"SELECT {_quote_ident('id')} FROM {_quote_ident('fb_accounts')} "
                    f"ORDER BY {_quote_ident('id')} ASC LIMIT 1"
                )
            ).scalar()
            if default_id is not None:
                connection.execute(
                    text(
                        f"UPDATE {_quote_ident('group_leads')} "
                        f"SET {_quote_ident('assigned_account_id')} = :aid "
                        f"WHERE {_quote_ident('assigned_account_id')} IS NULL"
                    ),
                    {"aid": int(default_id)},
                )
            # Partial unique index: handle unique only when set (SQLite
            # forbids UNIQUE inside ALTER TABLE ADD COLUMN, hence separate).
            connection.execute(
                text(
                    "CREATE UNIQUE INDEX IF NOT EXISTS "
                    f"{_quote_ident('uq_fb_accounts_handle')} ON {_quote_ident('fb_accounts')} "
                    f"({_quote_ident('handle')}) WHERE {_quote_ident('handle')} IS NOT NULL"
                )
            )
            connection.execute(
                text(
                    "CREATE INDEX IF NOT EXISTS "
                    f"{_quote_ident('ix_blocked_account_group')} ON {_quote_ident('account_groups_blocked')} "
                    f"({_quote_ident('account_id')}, {_quote_ident('group_name')})"
                )
            )
            # Retro-fix (Phase 3 gap): stat_date must be unique even on DBs
            # migrated before the constraint. De-dupe defensively first.
            dupes = connection.execute(
                text(
                    f"SELECT {_quote_ident('stat_date')} FROM {_quote_ident('group_stats')} "
                    f"GROUP BY {_quote_ident('stat_date')} HAVING COUNT(*) > 1"
                )
            ).fetchall()
            for (dup_date,) in dupes:
                keep = connection.execute(
                    text(
                        f"SELECT MIN({_quote_ident('id')}) FROM {_quote_ident('group_stats')} "
                        f"WHERE {_quote_ident('stat_date')} = :d"
                    ),
                    {"d": dup_date},
                ).scalar()
                connection.execute(
                    text(
                        f"DELETE FROM {_quote_ident('group_stats')} "
                        f"WHERE {_quote_ident('stat_date')} = :d AND {_quote_ident('id')} != :keep"
                    ),
                    {"d": dup_date, "keep": keep},
                )
                logger.warning("Removed duplicate group_stats row for %s.", dup_date)
            connection.execute(
                text(
                    "CREATE UNIQUE INDEX IF NOT EXISTS "
                    f"{_quote_ident('uq_group_stats_stat_date')} ON {_quote_ident('group_stats')} "
                    f"({_quote_ident('stat_date')})"
                )
            )
            connection.commit()
        except Exception:
            connection.rollback()
            logger.exception("fb_accounts/group_stats seed migration failed.")
            raise


def init_db() -> None:
    """Create all database tables from model metadata."""
    import app.models  # noqa: F401  -- ensure all models are registered
    from app.database.base import Base
    from app.database.session import engine

    Base.metadata.create_all(bind=engine)
    ensure_schema()
    logger.info("Database tables created.")
