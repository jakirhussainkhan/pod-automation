"""High-level AI content generation for products and posts."""

from typing import Optional

from sqlalchemy.orm import Session

from app.models.post import Post
from app.models.product import Product
from app.services import log_service
from app.services.ai.client import run_validated
from app.services.ai.exceptions import AIResponseParseError, AIServiceError
from app.services.ai.parser import (
    extract_json,
    normalize_hashtags,
    validate_post_payload,
)
from app.services.ai.prompts import (
    build_caption_prompts,
    build_group_post_prompts,
    build_hashtag_prompts,
    build_post_prompts,
    build_variations_prompts,
    normalize_group_niche,
    normalize_group_subculture,
    normalize_group_template,
    normalize_group_trigger,
    normalize_tone,
)
from app.services.group_shield import shield_group_post


def _with_result_meta(payload: dict, provider: str, model: str) -> dict:
    """Attach provider and model names to a validated payload."""
    payload["provider"] = provider
    payload["model"] = model
    return payload


def _parse_post_payload(result) -> dict:
    """Extract + validate a post payload, raising AIResponseParseError."""
    return validate_post_payload(extract_json(result.text))


def _parse_hashtags(result) -> list[str]:
    """Extract + validate a hashtag list."""
    data = extract_json(result.text)
    tags = data.get("hashtags")
    if not isinstance(tags, list):
        raise AIResponseParseError("Hashtag payload needs a 'hashtags' list.")
    return normalize_hashtags(tags)


def _make_variations_parser(count: int):
    """Build a parser that requires at least ``count`` variations."""

    def _parse(result) -> list[dict]:
        data = extract_json(result.text)
        variations = data.get("variations")
        if not isinstance(variations, list) or not variations:
            raise AIResponseParseError("Variations payload needs a 'variations' list.")
        if len(variations) < count:
            raise AIResponseParseError(
                f"Expected {count} variations, got {len(variations)}."
            )
        return variations[:count]

    return _parse


def _get_product_or_raise(db: Session, product_id: int) -> Product:
    """Load a product or raise AIServiceError when missing."""
    product = db.get(Product, product_id)
    if product is None:
        raise AIServiceError(f"Product {product_id} not found.")
    return product


def generate_post_content(
    db: Session, product_id: int, tone: str = "friendly"
) -> dict:
    """Generate caption, hashtags, CTA and image idea for a product."""
    product = _get_product_or_raise(db, product_id)
    tone = normalize_tone(tone)
    system, user = build_post_prompts(product, tone)
    result, payload = run_validated(
        db, system, user, _parse_post_payload,
        json_mode=True, product_id=product.id, call_type="caption",
    )
    return _with_result_meta(payload, result.provider, result.model)


def regenerate_caption(db: Session, post_id: int, tone: str) -> dict:
    """Generate a fresh caption and hashtags for an existing post."""
    post = db.get(Post, post_id)
    if post is None:
        raise AIServiceError(f"Post {post_id} not found.")
    tone = normalize_tone(tone)
    product: Optional[Product] = None
    if post.product_id is not None:
        product = db.get(Product, post.product_id)
    system, user = build_caption_prompts(product, tone, current_caption=post.caption)
    result, payload = run_validated(
        db, system, user, _parse_post_payload,
        json_mode=True, product_id=post.product_id, call_type="caption",
    )
    return _with_result_meta(payload, result.provider, result.model)


def generate_hashtags(db: Session, product_id: int) -> list[str]:
    """Generate a normalized hashtag list for a product."""
    product = _get_product_or_raise(db, product_id)
    system, user = build_hashtag_prompts(product)
    _result, tags = run_validated(
        db, system, user, _parse_hashtags,
        json_mode=True, product_id=product.id, call_type="hashtag",
    )
    return tags


def generate_post_variations(
    db: Session, product_id: int, count: int = 3
) -> list[dict]:
    """Generate several validated post variations in a single AI call."""
    count = max(2, min(5, int(count)))
    product = _get_product_or_raise(db, product_id)
    system, user = build_variations_prompts(product, count)
    result, variations = run_validated(
        db, system, user, _make_variations_parser(count),
        json_mode=True, product_id=product.id, call_type="variation",
    )
    checked: list[dict] = []
    for item in variations:
        payload = validate_post_payload(item)
        checked.append(_with_result_meta(payload, result.provider, result.model))
    return checked


def create_draft_post_from_ai(
    db: Session, product_id: int, tone: str = "friendly"
) -> Post:
    """Generate AI content and persist it as a draft post."""
    content = generate_post_content(db, product_id, tone)
    post = Post(
        product_id=product_id,
        caption=content["caption"],
        hashtags=content["hashtags"],
        status="draft",
        ai_provider=content["provider"],
        ai_model=content["model"],
    )
    db.add(post)
    db.commit()
    db.refresh(post)
    log_service.add_log(
        db,
        "ai_generated",
        f"AI generated draft post {post.id} for product {product_id} "
        f"via {content['provider']}.",
        post_id=post.id,
    )
    return post


def generate_group_post_content(
    db: Session,
    niche: str = "car",
    template: str = "show_your_ride",
    subculture: str = "auto",
    trigger: str = "auto",
) -> dict:
    """Generate a psychology-driven, LINK-FREE viral group post.

    The AI prompt carries the identity/controversy framework; afterwards the
    reach-down shield applies synonym variation and enforces zero-link so no
    product URL can ever leak into a main post.
    """
    niche = normalize_group_niche(niche)
    template = normalize_group_template(template)
    subculture = normalize_group_subculture(subculture)
    trigger = normalize_group_trigger(trigger)
    system, user = build_group_post_prompts(niche, template, subculture=subculture, trigger=trigger)
    result, payload = run_validated(
        db, system, user, _parse_post_payload,
        json_mode=True, product_id=None, call_type="other",
    )
    payload = shield_group_post(payload)
    return _with_result_meta(payload, result.provider, result.model)
