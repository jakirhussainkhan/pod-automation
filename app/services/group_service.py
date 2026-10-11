"""Group growth services: intent classification, DM funnel, cadence, leads CRUD."""

import random
import re
from typing import Optional

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.group_lead import GroupLead
from app.models.group_post_queue import GroupPostQueue
from app.models.product import Product
from app.services.group_shield import enforce_zero_link

LEAD_STATUSES: tuple[str, ...] = ("unsent", "step1_sent", "step2_sent", "replied", "converted", "follow_up_sent")

_HIGH_SIGNALS: tuple[str, ...] = (
    "where to buy", "where can i buy", "link", "price", "how much", "cost",
    "want to buy", "need this", "take my money", "how do i order", "how to order",
    "is this available", "still available", "dm me", "send me", "i want one",
    "need one", "buy one", "order one", "in stock", "ship", "discount", "sale",
)

_MEDIUM_SIGNALS: tuple[str, ...] = (
    "love", "awesome", "cool", "nice", "want", "need", "beautiful", "amazing",
    "great", "sick", "clean", "dope", "fire", "dream", "wish", "my first",
    "my ride", "my bike", "my car", "looks good", "looks great",
)

_LOW_NOISE: tuple[str, ...] = ("http://", "https://", "free crypto", "earn money", "whatsapp me")


def _normalize(text: str) -> str:
    """Lowercase and collapse whitespace for matching."""
    return re.sub(r"\s+", " ", (text or "").strip().lower())


def classify_intent(comment_text: str) -> dict:
    """Classify a raw group comment as high / medium / low intent.

    Rule-based and deterministic so it works fully offline. High intent
    signals are purchase-oriented questions; medium signals are enthusiasm
    or ownership stories; everything else is low.
    """
    cleaned = _normalize(comment_text)
    if not cleaned:
        return {"intent": "low", "confidence": 0.3, "signals": []}
    if any(noise in cleaned for noise in _LOW_NOISE):
        return {"intent": "low", "confidence": 0.75, "signals": ["possible-spam-link"]}
    high_hits = [sig for sig in _HIGH_SIGNALS if sig in cleaned]
    if high_hits:
        confidence = min(0.99, 0.82 + 0.05 * (len(high_hits) - 1))
        return {"intent": "high", "confidence": round(confidence, 2), "signals": high_hits[:5]}
    medium_hits = [sig for sig in _MEDIUM_SIGNALS if sig in cleaned]
    if medium_hits:
        # A medium comment with a question mark leans closer to high.
        confidence = 0.68 if "?" in cleaned else 0.6
        return {"intent": "medium", "confidence": confidence, "signals": medium_hits[:5]}
    if "?" in cleaned:
        return {"intent": "medium", "confidence": 0.55, "signals": ["question-asked"]}
    # Longer enthusiastic comments (>= 8 words with !) count as medium.
    if "!" in cleaned and len(cleaned.split()) >= 5:
        return {"intent": "medium", "confidence": 0.52, "signals": ["enthusiasm"]}
    return {"intent": "low", "confidence": 0.6, "signals": []}


def _first_name(username: str) -> str:
    """Derive a friendly first name from a username handle."""
    cleaned = (username or "").strip().lstrip("@")
    if not cleaned or cleaned.lower() in {"group_member", "member"}:
        return "friend"
    part = re.split(r"[\s_.\-]+", cleaned)[0]
    return part[:20] if part else "friend"


def _product_label(db: Session, product_id: Optional[int]) -> tuple[str, str]:
    """Return (product title, store URL) for DM personalization."""
    if product_id is None:
        return "that design you liked", ""
    product = db.get(Product, product_id)
    if product is None:
        return "that design you liked", ""
    title = product.title or "that design you liked"
    return title, (product.store_url or "")


def build_dm_messages(
    db: Session,
    comment_text: str,
    username: str = "group_member",
    product_id: Optional[int] = None,
) -> dict[str, str]:
    """Build the 2-step DM funnel for a high-intent commenter.

    Message 1 is a personalized inquiry with ZERO external links (safe for
    first contact). Message 2 shares the product link only after a reply.
    """
    name = _first_name(username)
    title, store_url = _product_label(db, product_id)
    snippet = (comment_text or "").strip()
    if len(snippet) > 120:
        snippet = snippet[:117].rstrip() + "..."
    message1 = (
        f"Hey {name}! 👋 Saw your comment (\"{snippet}\") in the group and "
        f"could tell you're really into {title}. Quick question — are you looking "
        f"for one for yourself or as a gift? I can point you to the exact version "
        f"other riders/drivers grabbed. No pressure at all, just happy to help! 🙂"
    )
    link_bit = f" Here it is: {store_url}" if store_url else (
        " I can share the exact link here if you'd like — just say the word!"
    )
    message2 = (
        f"Awesome, thanks for getting back to me {name}! 🙌 Since you asked, "
        f"this is the {title} everyone's been talking about.{link_bit} "
        f"If the size/color you want is out of stock, tell me and I'll find the "
        f"closest match. Want me to hold the details for you?"
    )
    return {"message1": message1, "message2": message2}


def roll_cadence_delay(rng: Optional[random.Random] = None) -> dict:
    """Roll a randomized 3-5 minute (180-300s) anti-spam safety delay."""
    source = rng or random
    delay = source.randint(180, 300)
    minutes, seconds = divmod(delay, 60)
    return {
        "delay_seconds": delay,
        "delay_label": f"{minutes}m {seconds:02d}s",
        "min_seconds": 180,
        "max_seconds": 300,
    }


def create_lead(
    db: Session,
    comment_text: str,
    username: str = "group_member",
    group_name: Optional[str] = None,
    product_id: Optional[int] = None,
    user_profile_link: Optional[str] = None,
    conversion_value: float = 0.0,
    source_template: Optional[str] = None,
) -> GroupLead:
    """Classify a comment, build DMs for high intent, and persist the lead."""
    scored = classify_intent(comment_text)
    messages = {"message1": "", "message2": ""}
    if scored["intent"] == "high":
        messages = build_dm_messages(db, comment_text, username, product_id)
    lead = GroupLead(
        username=(username or "group_member").strip()[:120] or "group_member",
        comment_text=comment_text.strip(),
        group_name=(group_name or None),
        intent=scored["intent"],
        product_id=product_id,
        message1=messages["message1"],
        message2=messages["message2"],
        status="unsent",
        user_profile_link=(user_profile_link or None),
        conversion_value=max(0.0, float(conversion_value or 0.0)),
        source_template=(source_template or None),
    )
    db.add(lead)
    db.commit()
    db.refresh(lead)
    return lead


def list_leads(
    db: Session, skip: int = 0, limit: int = 50, status: Optional[str] = None
) -> list[GroupLead]:
    """List leads newest-first, optionally filtered by funnel status."""
    query = db.query(GroupLead)
    if status:
        query = query.filter(GroupLead.status == status)
    return query.order_by(GroupLead.id.desc()).offset(skip).limit(limit).all()


def count_leads(db: Session, status: Optional[str] = None) -> int:
    """Count leads, optionally filtered by funnel status."""
    query = db.query(func.count(GroupLead.id))
    if status:
        query = query.filter(GroupLead.status == status)
    return int(query.scalar() or 0)


def get_lead(db: Session, lead_id: int) -> Optional[GroupLead]:
    """Load a single lead by id."""
    return db.get(GroupLead, lead_id)


def update_lead_status(db: Session, lead_id: int, status: str) -> Optional[GroupLead]:
    """Advance a lead's funnel status (validated by caller schema)."""
    return update_lead(db, lead_id, status=status)


def update_lead(
    db: Session,
    lead_id: int,
    status: Optional[str] = None,
    user_profile_link: Optional[str] = None,
    conversion_value: Optional[float] = None,
    group_name: Optional[str] = None,
    assigned_account_id: Optional[int] = None,
) -> Optional[GroupLead]:
    """Update a lead's status, profile link, revenue value, or group tag."""
    lead = db.get(GroupLead, lead_id)
    if lead is None:
        return None
    was_converted = (getattr(lead, "status", "") or "") == "converted"
    if status is not None:
        if status not in LEAD_STATUSES:
            raise ValueError(
                f"Invalid status {status!r}. Allowed: {', '.join(LEAD_STATUSES)}."
            )
        lead.status = status
    if user_profile_link is not None:
        lead.user_profile_link = user_profile_link or None
    if conversion_value is not None:
        lead.conversion_value = max(0.0, float(conversion_value))
    if group_name is not None:
        lead.group_name = group_name or None
    if assigned_account_id is not None:
        lead.assigned_account_id = assigned_account_id
    db.commit()
    db.refresh(lead)
    # Lifetime attribution: first transition INTO converted credits the
    # assigned account (count + revenue). Later value edits on an
    # already-converted lead do not double-count.
    if not was_converted and (lead.status or "") == "converted":
        try:
            from app.models.fb_account import FbAccount

            account_id = getattr(lead, "assigned_account_id", None)
            account = db.get(FbAccount, account_id) if account_id else None
            if account is not None:
                account.total_converted = int(account.total_converted or 0) + 1
                account.total_revenue = round(
                    float(account.total_revenue or 0.0) + float(lead.conversion_value or 0.0), 2
                )
                db.commit()
                db.refresh(lead)
        except Exception:
            db.rollback()
    return lead


def delete_lead(db: Session, lead_id: int) -> bool:
    """Delete a lead; return True when it existed."""
    lead = db.get(GroupLead, lead_id)
    if lead is None:
        return False
    db.delete(lead)
    db.commit()
    return True


def lead_funnel_stats(db: Session) -> dict:
    """Return per-status counts for the funnel dashboard cards."""
    stats = {"total": count_leads(db)}
    for status in LEAD_STATUSES:
        stats[status] = count_leads(db, status=status)
    return stats


def revenue_stats(db: Session) -> dict:
    """Return total/average revenue logged on converted DM leads."""
    total = db.query(func.coalesce(func.sum(GroupLead.conversion_value), 0.0)).filter(
        GroupLead.status == "converted"
    ).scalar() or 0.0
    count = count_leads(db, status="converted")
    total = round(float(total), 2)
    return {
        "total_revenue": total,
        "converted_count": count,
        "average_value": round(total / count, 2) if count else 0.0,
    }


_FB_URL_RE = re.compile(r"https?://(?:www\.)?facebook\.com/\S+", re.IGNORECASE)


def parse_bulk_comments(text: str) -> list[dict]:
    """Parse pasted multi-line comments into username/comment/profile entries.

    Supported per-line formats (first match wins):
    ``Name: comment`` | ``Name - comment`` | ``Name | comment`` |
    ``@name comment`` | bare ``comment`` (username defaults to group_member).
    A facebook.com URL anywhere in the line is captured as user_profile_link.
    """
    entries: list[dict] = []
    for raw_line in (text or "").splitlines():
        line = raw_line.strip()
        if not line:
            continue
        profile: Optional[str] = None
        match = _FB_URL_RE.search(line)
        if match:
            profile = match.group(0).rstrip(".,)")
            line = _FB_URL_RE.sub("", line)
            line = re.sub(r"\s{2,}", " ", line).strip(" -:|\t")
        username, comment = "group_member", line
        colon = re.match(r"^(.{1,40}?):\s+(.+)$", line)
        if colon and len(colon.group(1).split()) <= 4:
            username, comment = colon.group(1).strip().lstrip("@"), colon.group(2).strip()
        else:
            dashed = re.match(r"^(.{1,40}?)\s+[|\-–—]\s+(.+)$", line)
            if dashed and len(dashed.group(1).split()) <= 4:
                username, comment = dashed.group(1).strip().lstrip("@"), dashed.group(2).strip()
            else:
                tagged = re.match(r"^@(\S+)\s+(.+)$", line)
                if tagged:
                    username, comment = tagged.group(1), tagged.group(2).strip()
        if not comment:
            continue
        entries.append(
            {
                "username": (username.strip()[:120] or "group_member"),
                "comment_text": comment,
                "user_profile_link": profile,
            }
        )
    return entries


def bulk_import_leads(
    db: Session,
    text: str,
    group_name: Optional[str] = None,
    product_id: Optional[int] = None,
) -> dict:
    """Classify every parsed comment; instantly save high-intent leads only."""
    saved: list[GroupLead] = []
    skipped: list[dict] = []
    for entry in parse_bulk_comments(text):
        scored = classify_intent(entry["comment_text"])
        if scored["intent"] == "high":
            saved.append(
                create_lead(
                    db,
                    comment_text=entry["comment_text"],
                    username=entry["username"],
                    group_name=group_name,
                    product_id=product_id,
                    user_profile_link=entry["user_profile_link"],
                )
            )
        else:
            skipped.append(
                {
                    "username": entry["username"],
                    "comment_text": entry["comment_text"],
                    "intent": scored["intent"],
                    "confidence": scored["confidence"],
                }
            )
    return {
        "total_parsed": len(saved) + len(skipped),
        "saved_high": len(saved),
        "skipped": skipped,
        "leads": saved,
    }


def pick_batch_plan(niche: str, count: int, rng: Optional[random.Random] = None) -> list[dict]:
    """Plan a batch of distinct template/niche pairs for the daily queue."""
    from app.services.ai.prompts import GROUP_TEMPLATES

    source = rng or random
    cleaned = (niche or "mixed").strip().lower()
    if cleaned not in ("car", "bike", "mixed"):
        cleaned = "mixed"
    count = max(1, min(5, int(count)))
    templates = list(GROUP_TEMPLATES.keys())
    source.shuffle(templates)
    plan: list[dict] = []
    start_car = source.random() < 0.5
    for index in range(count):
        if cleaned == "mixed":
            item_niche = "car" if (index % 2 == 0) == start_car else "bike"
        else:
            item_niche = cleaned
        plan.append({"niche": item_niche, "template": templates[index % len(templates)]})
    return plan


def save_queued_post(
    db: Session,
    niche: str,
    template: str,
    content: dict,
    subculture: str = "auto",
    trigger: str = "auto",
) -> GroupPostQueue:
    """Persist one generated post into the Group Post Queue."""
    item = GroupPostQueue(
        niche=niche,
        subculture=subculture,
        template=template,
        trigger=trigger,
        caption=content.get("caption", ""),
        hashtags=list(content.get("hashtags", [])),
        call_to_action=content.get("call_to_action", ""),
        image_idea=content.get("image_idea", ""),
        status="queued",
        template_name=template,
    )
    db.add(item)
    db.commit()
    db.refresh(item)
    return item


def list_queue(db: Session, status: Optional[str] = None) -> list[GroupPostQueue]:
    """List queued posts newest-first, optionally filtered by status."""
    query = db.query(GroupPostQueue)
    if status:
        query = query.filter(GroupPostQueue.status == status)
    return query.order_by(GroupPostQueue.id.desc()).all()


def count_queue(db: Session, status: Optional[str] = None) -> int:
    """Count queued posts, optionally filtered by status."""
    query = db.query(func.count(GroupPostQueue.id))
    if status:
        query = query.filter(GroupPostQueue.status == status)
    return int(query.scalar() or 0)


def get_queued_post(db: Session, item_id: int) -> Optional[GroupPostQueue]:
    """Load a single queued post by id."""
    return db.get(GroupPostQueue, item_id)


def update_queued_post(
    db: Session,
    item_id: int,
    caption: Optional[str] = None,
    status: Optional[str] = None,
) -> Optional[GroupPostQueue]:
    """Edit a queued caption (re-shielded) or flip its queued/posted status."""
    item = db.get(GroupPostQueue, item_id)
    if item is None:
        return None
    if caption is not None:
        cleaned, _ = enforce_zero_link(caption.strip(), item.call_to_action or "")
        item.caption = cleaned
    if status is not None:
        item.status = status
    db.commit()
    db.refresh(item)
    return item


def delete_queued_post(db: Session, item_id: int) -> bool:
    """Delete a queued post; return True when it existed."""
    item = db.get(GroupPostQueue, item_id)
    if item is None:
        return False
    db.delete(item)
    db.commit()
    return True


def track_queue_copy(db: Session, item_id: int) -> Optional[GroupPostQueue]:
    """Stamp copied_at on a queued post when the user copies its text."""
    from datetime import datetime, timezone

    item = db.get(GroupPostQueue, item_id)
    if item is None:
        return None
    try:
        item.copied_at = datetime.now(timezone.utc)
        db.commit()
        db.refresh(item)
        return item
    except Exception:
        db.rollback()
        raise


def track_queue_posted(db: Session, item_id: int) -> Optional[GroupPostQueue]:
    """Stamp posted_at (and flip status) when a queued post goes live."""
    from datetime import datetime, timezone

    item = db.get(GroupPostQueue, item_id)
    if item is None:
        return None
    try:
        item.posted_at = datetime.now(timezone.utc)
        item.status = "posted"
        db.commit()
        db.refresh(item)
        return item
    except Exception:
        db.rollback()
        raise
