"""Shared FastAPI dependencies for destructive-endpoint hardening."""

from fastapi import Header, HTTPException


def require_destructive_confirmation(
    x_confirm_delete: str | None = Header(default=None, alias="X-Confirm-Delete"),
) -> None:
    """Require the custom ``X-Confirm-Delete`` header on destructive calls.

    The UI sends ``X-Confirm-Delete: true`` after an explicit user
    confirmation dialog. Missing/invalid headers are rejected so stray
    crawlers, prefetches, or CSRF probes cannot trigger wipes.
    """
    if x_confirm_delete is None or x_confirm_delete.strip().lower() not in {
        "1",
        "true",
        "yes",
        "confirm",
    }:
        raise HTTPException(
            status_code=403,
            detail="Destructive action requires X-Confirm-Delete header.",
        )
