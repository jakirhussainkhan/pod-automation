"""Development server entrypoint for POD Facebook Automation Dashboard."""

import uvicorn

from app.config import get_settings


def main() -> None:
    """Start Uvicorn using host, port and reload flag from settings."""
    from app.config import LOCAL_HOSTS

    settings = get_settings()
    # Defense in depth: never bind beyond loopback even if settings drift.
    host = settings.HOST if settings.HOST in LOCAL_HOSTS else "127.0.0.1"
    uvicorn.run(
        "app.main:app",
        host=host,
        port=settings.PORT,
        reload=settings.DEBUG,
    )


if __name__ == "__main__":
    main()
