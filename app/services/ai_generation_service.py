"""Service for AI generation records."""

from typing import Optional

from sqlalchemy.orm import Session

from app.models.ai_generation import AIGeneration


def record_generation(
    db: Session,
    product_id: Optional[int],
    prompt: str,
    response: str,
    provider: str,
    model: str,
    tokens_used: Optional[int] = None,
    success: bool = True,
) -> AIGeneration:
    """Record an AI generation and commit it."""
    record = AIGeneration(
        product_id=product_id,
        prompt=prompt,
        response=response,
        provider=provider,
        model=model,
        tokens_used=tokens_used,
        success=success,
    )
    db.add(record)
    db.commit()
    db.refresh(record)
    return record


def list_generations(
    db: Session, skip: int = 0, limit: int = 50
) -> list[AIGeneration]:
    """List AI generation records newest first."""
    return (
        db.query(AIGeneration)
        .order_by(AIGeneration.id.desc())
        .offset(skip)
        .limit(limit)
        .all()
    )


def count_generations(db: Session) -> int:
    """Return the total number of AI generation records."""
    from sqlalchemy import func

    return db.query(func.count(AIGeneration.id)).scalar() or 0


def clear_generations(db: Session) -> int:
    """Delete all AI generation records and return the removed count."""
    deleted = db.query(AIGeneration).delete(synchronize_session=False)
    db.commit()
    return deleted or 0
