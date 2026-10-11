"""Service for key-value app settings."""

import re
from typing import Optional

from sqlalchemy.orm import Session

from app.config import get_settings
from app.models.app_setting import AppSetting

EDITABLE_SETTING_KEYS: set[str] = {
    "default_tone",
    "brand_voice",
    "post_language",
    "default_hashtags",
    "posting_enabled",
    "posts_per_day",
    "posting_hours",
    "dm_min_gap_seconds",
    "dm_hourly_cap",
    "dm_daily_cap",
    "reply_check_delay_hours",
    "reply_check_second_hours",
    "cold_lead_days",
    "follow_up_enabled",
    "max_follow_ups",
    "stats_auto_compute",
    "digest_week_start",
    "chart_days",
    "token_added_at",
    "token_expires_at",
    "backup_enabled",
    "backup_hour_utc",
    "backup_keep_last",
    "log_retention_days",
    "ai_cost_groq_per_1k_in",
    "ai_cost_groq_per_1k_out",
    "ai_cost_openai_per_1k_in",
    "ai_cost_openai_per_1k_out",
    "kill_switch_active",
    "multi_account_enabled",
    "account_rotation_mode",
    "account_collision_window_days",
    "account_warning_pause_hours",
    "account_ban_recovery_days",
    "account_health_check_enabled",
}
"""Whitelisted keys editable through the public settings API."""


def get_setting(db: Session, key: str, default: Optional[str] = None) -> Optional[str]:
    """Return a setting value, or default when the key is missing."""
    row = db.query(AppSetting).filter(AppSetting.key == key).first()
    if row is None:
        return default
    return row.value


def set_setting(db: Session, key: str, value: Optional[str]) -> AppSetting:
    """Upsert a setting value and commit it."""
    row = db.query(AppSetting).filter(AppSetting.key == key).first()
    if row is None:
        row = AppSetting(key=key, value=value)
        db.add(row)
    else:
        row.value = value
    db.commit()
    db.refresh(row)
    return row


def get_all_settings(db: Session) -> dict[str, Optional[str]]:
    """Return all settings as a key-value dict."""
    rows = db.query(AppSetting).all()
    return {row.key: row.value for row in rows}


def set_setting_checked(db: Session, key: str, value: Optional[str]) -> AppSetting:
    """Upsert a whitelisted setting, rejecting unknown keys."""
    if key not in EDITABLE_SETTING_KEYS:
        raise ValueError(
            f"Setting '{key}' is not editable. "
            f"Allowed keys: {', '.join(sorted(EDITABLE_SETTING_KEYS))}."
        )
    return set_setting(db, key, value)


def validate_setting_value(key: str, value: str) -> str:
    """Validate and normalize a whitelisted setting value."""
    text = str(value).strip()
    if key == "posts_per_day":
        try:
            number = int(text)
        except (TypeError, ValueError):
            raise ValueError("posts_per_day must be an integer between 1 and 10.")
        if not 1 <= number <= 10:
            raise ValueError("posts_per_day must be an integer between 1 and 10.")
        return str(number)
    if key == "posting_enabled":
        lowered = text.lower()
        if lowered not in ("true", "false"):
            raise ValueError('posting_enabled must be "true" or "false".')
        return lowered
    if key == "default_tone":
        from app.services.ai.prompts import ALLOWED_TONES

        lowered = text.lower()
        if lowered not in ALLOWED_TONES:
            raise ValueError(
                f"default_tone must be one of: {', '.join(ALLOWED_TONES)}."
            )
        return lowered
    if key == "posting_hours":
        parts = [part.strip() for part in text.split(",") if part.strip()]
        if not parts:
            raise ValueError("posting_hours must be comma-separated HH:MM values.")
        for part in parts:
            if not re.fullmatch(r"([01]\d|2[0-3]):[0-5]\d", part):
                raise ValueError(
                    "posting_hours must be comma-separated HH:MM values."
                )
        return ",".join(parts)
    if key == "dm_min_gap_seconds":
        try:
            number = int(text)
        except (TypeError, ValueError):
            raise ValueError("dm_min_gap_seconds must be an integer >= 60.")
        if number < 60:
            raise ValueError("dm_min_gap_seconds must be an integer >= 60.")
        return str(number)
    if key == "dm_hourly_cap":
        try:
            number = int(text)
        except (TypeError, ValueError):
            raise ValueError("dm_hourly_cap must be an integer between 1 and 50.")
        if not 1 <= number <= 50:
            raise ValueError("dm_hourly_cap must be an integer between 1 and 50.")
        return str(number)
    if key == "dm_daily_cap":
        try:
            number = int(text)
        except (TypeError, ValueError):
            raise ValueError("dm_daily_cap must be an integer between 1 and 200.")
        if not 1 <= number <= 200:
            raise ValueError("dm_daily_cap must be an integer between 1 and 200.")
        return str(number)
    if key in ("reply_check_delay_hours", "reply_check_second_hours"):
        try:
            number = int(text)
        except (TypeError, ValueError):
            raise ValueError(f"{key} must be an integer between 1 and 168.")
        if not 1 <= number <= 168:
            raise ValueError(f"{key} must be an integer between 1 and 168.")
        return str(number)
    if key == "cold_lead_days":
        try:
            number = int(text)
        except (TypeError, ValueError):
            raise ValueError("cold_lead_days must be an integer between 1 and 30.")
        if not 1 <= number <= 30:
            raise ValueError("cold_lead_days must be an integer between 1 and 30.")
        return str(number)
    if key == "follow_up_enabled":
        lowered = text.lower()
        if lowered not in ("true", "false"):
            raise ValueError('follow_up_enabled must be "true" or "false".')
        return lowered
    if key == "max_follow_ups":
        try:
            number = int(text)
        except (TypeError, ValueError):
            raise ValueError("max_follow_ups must be an integer between 1 and 5.")
        if not 1 <= number <= 5:
            raise ValueError("max_follow_ups must be an integer between 1 and 5.")
        return str(number)
    if key == "stats_auto_compute":
        lowered = text.lower()
        if lowered not in ("true", "false"):
            raise ValueError('stats_auto_compute must be "true" or "false".')
        return lowered
    if key == "digest_week_start":
        lowered = text.lower()
        if lowered not in ("monday", "sunday"):
            raise ValueError('digest_week_start must be "monday" or "sunday".')
        return lowered
    if key == "chart_days":
        try:
            number = int(text)
        except (TypeError, ValueError):
            raise ValueError("chart_days must be an integer between 7 and 90.")
        if not 7 <= number <= 90:
            raise ValueError("chart_days must be an integer between 7 and 90.")
        return str(number)
    if key in ("token_added_at", "token_expires_at"):
        if not text:
            return ""
        try:
            stamp = text[:-1] + "+00:00" if text.endswith("Z") else text
            from datetime import datetime

            datetime.fromisoformat(stamp)
        except (TypeError, ValueError):
            raise ValueError(f"{key} must be a valid ISO datetime string.")
        return text
    if key == "backup_hour_utc":
        try:
            number = int(text)
        except (TypeError, ValueError):
            raise ValueError("backup_hour_utc must be an integer between 0 and 23.")
        if not 0 <= number <= 23:
            raise ValueError("backup_hour_utc must be an integer between 0 and 23.")
        return str(number)
    if key == "backup_keep_last":
        try:
            number = int(text)
        except (TypeError, ValueError):
            raise ValueError("backup_keep_last must be an integer between 1 and 30.")
        if not 1 <= number <= 30:
            raise ValueError("backup_keep_last must be an integer between 1 and 30.")
        return str(number)
    if key == "log_retention_days":
        try:
            number = int(text)
        except (TypeError, ValueError):
            raise ValueError("log_retention_days must be an integer between 1 and 365.")
        if not 1 <= number <= 365:
            raise ValueError("log_retention_days must be an integer between 1 and 365.")
        return str(number)
    if key in ("backup_enabled", "kill_switch_active",
               "multi_account_enabled", "account_health_check_enabled"):
        lowered = text.lower()
        if lowered not in ("true", "false"):
            raise ValueError(f'{key} must be "true" or "false".')
        return lowered
    if key in ("ai_cost_groq_per_1k_in", "ai_cost_groq_per_1k_out",
               "ai_cost_openai_per_1k_in", "ai_cost_openai_per_1k_out"):
        try:
            rate = float(text)
        except (TypeError, ValueError):
            raise ValueError(f"{key} must be a number >= 0.")
        if rate < 0:
            raise ValueError(f"{key} must be a number >= 0.")
        return str(rate)
    if key == "account_rotation_mode":
        lowered = text.lower()
        if lowered not in ("priority", "round_robin", "niche_match"):
            raise ValueError('account_rotation_mode must be "priority", "round_robin" or "niche_match".')
        return lowered
    if key == "account_collision_window_days":
        try:
            number = int(text)
        except (TypeError, ValueError):
            raise ValueError("account_collision_window_days must be an integer between 1 and 90.")
        if not 1 <= number <= 90:
            raise ValueError("account_collision_window_days must be an integer between 1 and 90.")
        return str(number)
    if key == "account_warning_pause_hours":
        try:
            number = int(text)
        except (TypeError, ValueError):
            raise ValueError("account_warning_pause_hours must be an integer between 0 and 720.")
        if not 0 <= number <= 720:
            raise ValueError("account_warning_pause_hours must be an integer between 0 and 720.")
        return str(number)
    if key == "account_ban_recovery_days":
        try:
            number = int(text)
        except (TypeError, ValueError):
            raise ValueError("account_ban_recovery_days must be an integer between 1 and 365.")
        if not 1 <= number <= 365:
            raise ValueError("account_ban_recovery_days must be an integer between 1 and 365.")
        return str(number)
    return text


def is_kill_switch_active(db: Session) -> bool:
    """Return True when the emergency stop is engaged."""
    try:
        return str(get_setting(db, "kill_switch_active", "false")).strip().lower() == "true"
    except Exception:
        return False


def set_kill_switch(db: Session, active: bool) -> None:
    """Engage or release the emergency stop, logging the event."""
    from app.services import log_service

    set_setting(db, "kill_switch_active", "true" if active else "false")
    try:
        log_service.add_log(
            db,
            "kill_switch_on" if active else "kill_switch_off",
            "Emergency stop ENGAGED — all publishing blocked."
            if active else "Emergency stop released — publishing resumed.",
            level="WARNING" if active else "INFO",
        )
    except Exception:
        pass


def get_public_settings(db: Session) -> dict[str, str]:
    """Return whitelisted settings with defaults for missing keys."""
    settings = get_settings()
    defaults: dict[str, str] = {
        "default_tone": "friendly",
        "brand_voice": settings.DEFAULT_BRAND_VOICE,
        "post_language": settings.DEFAULT_POST_LANGUAGE,
        "default_hashtags": "",
        "posting_enabled": "false",
        "posts_per_day": "1",
        "posting_hours": "09:00,18:00",
        "dm_min_gap_seconds": "300",
        "dm_hourly_cap": "10",
        "dm_daily_cap": "20",
        "reply_check_delay_hours": "6",
        "reply_check_second_hours": "24",
        "cold_lead_days": "3",
        "follow_up_enabled": "true",
        "max_follow_ups": "1",
        "stats_auto_compute": "true",
        "digest_week_start": "monday",
        "chart_days": "30",
        "token_added_at": "",
        "token_expires_at": "",
        "backup_enabled": "true",
        "backup_hour_utc": "3",
        "backup_keep_last": "7",
        "log_retention_days": "30",
        "ai_cost_groq_per_1k_in": "0.0",
        "ai_cost_groq_per_1k_out": "0.0",
        "ai_cost_openai_per_1k_in": "0.005",
        "ai_cost_openai_per_1k_out": "0.015",
        "kill_switch_active": "false",
        "multi_account_enabled": "false",
        "account_rotation_mode": "priority",
        "account_collision_window_days": "7",
        "account_warning_pause_hours": "48",
        "account_ban_recovery_days": "30",
        "account_health_check_enabled": "true",
    }
    stored = get_all_settings(db)
    result: dict[str, str] = {}
    for key in sorted(defaults):
        value = stored.get(key)
        result[key] = value if value is not None else defaults[key]
    return result
