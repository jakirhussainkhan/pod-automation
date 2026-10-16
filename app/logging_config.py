"""Central logging configuration for console and rotating file output."""

import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path

from app.config import BASE_DIR, get_settings


def setup_logging() -> logging.Logger:
    """Configure root logging with console and rotating file handlers."""
    settings = get_settings()
    level_name = (settings.LOG_LEVEL or "").strip().upper()
    log_level = getattr(logging, level_name, None)
    if not isinstance(log_level, int):
        raise ValueError(
            f"Invalid LOG_LEVEL {settings.LOG_LEVEL!r}; expected one of "
            "DEBUG, INFO, WARNING, ERROR, CRITICAL."
        )

    logs_dir: Path = BASE_DIR / "logs"
    logs_dir.mkdir(parents=True, exist_ok=True)
    log_file: Path = logs_dir / "app.log"

    formatter = logging.Formatter(
        fmt="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    root_logger = logging.getLogger()
    root_logger.setLevel(log_level)

    # Remove stale handlers so repeated startup calls do not duplicate output.
    for handler in list(root_logger.handlers):
        root_logger.removeHandler(handler)

    console_handler = logging.StreamHandler()
    console_handler.setLevel(log_level)
    console_handler.setFormatter(formatter)
    root_logger.addHandler(console_handler)

    file_handler = RotatingFileHandler(
        filename=str(log_file),
        maxBytes=5 * 1024 * 1024,
        backupCount=3,
        encoding="utf-8",
    )
    file_handler.setLevel(log_level)
    file_handler.setFormatter(formatter)
    root_logger.addHandler(file_handler)

    logger = logging.getLogger("pod-automation")
    logger.debug("Logging initialized at level %s.", settings.LOG_LEVEL.upper())
    return logger
