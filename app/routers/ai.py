"""AI generation API router."""

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.config import get_settings
from app.database.session import get_db
from app.models.post import Post
from app.schemas.ai import (
    AIStatusResponse,
    GeneratedContent,
    GeneratePostRequest,
    RegenerateCaptionRequest,
    VariationsRequest,
)
from app.schemas.ai_generation import AIGenerationRead
from app.schemas.common import Page
from app.schemas.post import PostRead, PostUpdate
from app.services import ai_generation_service, log_service, post_service
from app.services.ai.content_generator import (
    create_draft_post_from_ai,
    generate_hashtags,
    generate_post_content,
    generate_post_variations,
    regenerate_caption,
)
from app.services.ai.exceptions import (
    AIConfigurationError,
    AIProviderError,
    AIResponseParseError,
    AIServiceError,
)
from app.services.ai.status import get_ai_status

router: APIRouter = APIRouter(prefix="/api/ai", tags=["ai"])


def _safe_detail(message: str) -> str:
    """Redact configured secret values from an error message."""
    settings = get_settings()
    safe = str(message)
    for secret in (
        settings.GROQ_API_KEY,
        settings.OPENAI_API_KEY,
        settings.FACEBOOK_PAGE_ACCESS_TOKEN,
    ):
        if secret:
            safe = safe.replace(secret, "[redacted]")
    return safe


def _map_ai_error(exc: AIServiceError) -> HTTPException:
    """Map AI service errors to HTTP errors without leaking secrets."""
    from app.services.ai.exceptions import AIAuthError, AIRateLimitError

    detail = _safe_detail(exc)
    if isinstance(exc, AIConfigurationError):
        return HTTPException(status_code=503, detail=detail)
    if isinstance(exc, AIAuthError):
        return HTTPException(status_code=502, detail=detail)
    if isinstance(exc, AIRateLimitError):
        return HTTPException(status_code=429, detail=detail)
    if isinstance(exc, (AIProviderError, AIResponseParseError)):
        return HTTPException(status_code=502, detail=detail)
    lowered = str(exc).lower()
    # Only map missing DB records to 404; provider "model not found"
    # messages must stay 502 to avoid misleading clients.
    if "not found" in lowered and ("product" in lowered or "post" in lowered):
        return HTTPException(status_code=404, detail=detail)
    return HTTPException(status_code=400, detail=detail)


@router.get("/status", response_model=AIStatusResponse)
def ai_status_endpoint() -> AIStatusResponse:
    """Return AI provider configuration status."""
    return get_ai_status()


@router.post("/generate", response_model=PostRead, status_code=201)
def ai_generate_endpoint(
    data: GeneratePostRequest, db: Session = Depends(get_db)
) -> Post:
    """Generate AI content and save it as a draft post."""
    try:
        return create_draft_post_from_ai(db, data.product_id, data.tone)
    except AIServiceError as exc:
        raise _map_ai_error(exc)


@router.post("/preview", response_model=GeneratedContent)
def ai_preview_endpoint(
    data: GeneratePostRequest, db: Session = Depends(get_db)
) -> GeneratedContent:
    """Generate AI content without saving a post."""
    try:
        content = generate_post_content(db, data.product_id, data.tone)
    except AIServiceError as exc:
        raise _map_ai_error(exc)
    return GeneratedContent(**content)


@router.post("/posts/{post_id}/regenerate-caption", response_model=PostRead)
def ai_regenerate_caption_endpoint(
    post_id: int, data: RegenerateCaptionRequest, db: Session = Depends(get_db)
) -> Post:
    """Regenerate a post caption in place and log the event."""
    post = post_service.get_post(db, post_id)
    if post is None:
        raise HTTPException(status_code=404, detail=f"Post {post_id} not found.")
    if post.status == "published":
        raise HTTPException(status_code=400, detail="Published posts cannot be modified.")
    try:
        content = regenerate_caption(db, post_id, data.tone)
    except AIServiceError as exc:
        raise _map_ai_error(exc)
    updated = post_service.update_post(
        db, post_id, PostUpdate(caption=content["caption"], hashtags=content["hashtags"])
    )
    log_service.add_log(
        db, "ai_regenerated", f"Post {post_id} caption regenerated.", post_id=post_id
    )
    return updated


@router.post("/products/{product_id}/hashtags", response_model=dict[str, list[str]])
def ai_hashtags_endpoint(
    product_id: int, db: Session = Depends(get_db)
) -> dict[str, list[str]]:
    """Generate hashtags for a product without saving anything."""
    try:
        tags = generate_hashtags(db, product_id)
    except AIServiceError as exc:
        raise _map_ai_error(exc)
    return {"hashtags": tags}


@router.post(
    "/products/{product_id}/variations", response_model=list[GeneratedContent]
)
def ai_variations_endpoint(
    product_id: int, data: VariationsRequest, db: Session = Depends(get_db)
) -> list[GeneratedContent]:
    """Generate several post variations for a product."""
    try:
        variations = generate_post_variations(db, product_id, data.count)
    except AIServiceError as exc:
        raise _map_ai_error(exc)
    return [GeneratedContent(**item) for item in variations]


@router.get("/generations", response_model=Page[AIGenerationRead])
def ai_generations_endpoint(
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
) -> dict:
    """List recorded AI generation attempts with pagination."""
    items = ai_generation_service.list_generations(db, skip=skip, limit=limit)
    total = ai_generation_service.count_generations(db)
    return {"items": items, "total": total, "skip": skip, "limit": limit}
