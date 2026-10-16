"""Group Growth & Intent DM Engine API router."""

import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

logger = logging.getLogger("pod-automation")

# Bucket views compute urgency in Python, so they scan a bounded slice of leads
# rather than the whole table (guard against unbounded memory/CPU).
_BUCKET_SCAN_LIMIT = 2000

from app.database.session import get_db
from app.routers.ai import _map_ai_error
from app.schemas.ai import GeneratedContent
from app.schemas.group_lead import (
    BulkMarkReplyRequest,
    CadenceResponse,
    ClassifyCommentRequest,
    ClassifyCommentResponse,
    GroupLeadCreate,
    GroupLeadRead,
    GroupLeadUpdate,
    GroupPostRequest,
    MarkReplyRequest,
)
from app.schemas.group_queue import (
    BulkParseRequest,
    BulkParseResponse,
    BulkParseSkipped,
    QueueBatchRequest,
    QueueItemRead,
    QueueUpdate,
    RevenueStats,
)
from app.services import group_service
from app.services.ai.content_generator import generate_group_post_content
from app.services.ai.exceptions import AIServiceError
from app.services.ai.prompts import GROUP_SUBCULTURES, GROUP_TEMPLATES, GROUP_TRIGGERS

router: APIRouter = APIRouter(prefix="/api/groups", tags=["groups"])

leads_router: APIRouter = APIRouter(prefix="/api/group-leads", tags=["group-leads"])

safety_router: APIRouter = APIRouter(prefix="/api/dm-safety", tags=["dm-safety"])


@router.get("/templates")
def group_templates() -> dict:
    """List psychology-driven Group Engagement templates + framework metadata."""
    return {
        "niches": ["car", "bike"],
        "subcultures": list(GROUP_SUBCULTURES),
        "triggers": list(GROUP_TRIGGERS),
        "policy": {
            "direct_selling": "BANNED in group posts",
            "zero_link": "No URLs, prices, stores, or purchase CTAs in main posts — links live only in the 2-step DM funnel",
            "variation": "Every post is synonym-spun + hashtag-rotated so Meta never sees repetitive spam",
        },
        "templates": [
            {
                "key": key,
                "label": value["label"],
                "angle": value["angle"],
                "subculture": value.get("subculture"),
                "triggers": value.get("triggers", []),
                "indirect_selling": bool(value.get("indirect_selling", False)),
            }
            for key, value in GROUP_TEMPLATES.items()
        ],
    }


@router.post("/posts", response_model=GeneratedContent)
def generate_group_post(data: GroupPostRequest, db: Session = Depends(get_db)) -> GeneratedContent:
    """Generate a psychology-driven, LINK-FREE group post with spam shield."""
    try:
        content = generate_group_post_content(db, data.niche, data.template, data.subculture, data.trigger)
    except AIServiceError as exc:
        raise _map_ai_error(exc)
    return GeneratedContent(**content)


@router.get("/cadence", response_model=CadenceResponse)
def cadence_delay() -> CadenceResponse:
    """Roll a randomized 3-5 minute anti-spam safety delay."""
    return CadenceResponse(**group_service.roll_cadence_delay())


@router.post("/classify", response_model=ClassifyCommentResponse)
def classify_comment(data: ClassifyCommentRequest, db: Session = Depends(get_db)) -> ClassifyCommentResponse:
    """Classify a raw group comment and preview DMs for high intent."""
    scored = group_service.classify_intent(data.comment_text)
    message1 = ""
    message2 = ""
    if scored["intent"] == "high":
        messages = group_service.build_dm_messages(db, data.comment_text, data.username, None)
        message1 = messages["message1"]
        message2 = messages["message2"]
    return ClassifyCommentResponse(
        intent=scored["intent"],
        confidence=scored["confidence"],
        signals=scored["signals"],
        message1=message1,
        message2=message2,
    )


@router.get("/funnel/stats")
def funnel_stats(db: Session = Depends(get_db)) -> dict:
    """Return per-status funnel counts for the workbench header."""
    return group_service.lead_funnel_stats(db)


@router.get("/revenue", response_model=RevenueStats)
def revenue_totals(db: Session = Depends(get_db)) -> RevenueStats:
    """Return total/average revenue logged on converted DM leads."""
    return RevenueStats(**group_service.revenue_stats(db))


@router.post("/leads/bulk-parse", response_model=BulkParseResponse)
def bulk_parse_leads(data: BulkParseRequest, db: Session = Depends(get_db)) -> BulkParseResponse:
    """Parse 10+ pasted comments; extract usernames, classify, save high-intent."""
    result = group_service.bulk_import_leads(db, data.text, data.group_name, data.product_id)
    return BulkParseResponse(
        total_parsed=result["total_parsed"],
        saved_high=result["saved_high"],
        skipped=[BulkParseSkipped(**item) for item in result["skipped"]],
        lead_ids=[lead.id for lead in result["leads"]],
    )


@router.post("/queue/generate-batch", response_model=list[QueueItemRead])
def generate_queue_batch(data: QueueBatchRequest, db: Session = Depends(get_db)) -> list[QueueItemRead]:
    """Auto-generate a batch of distinct psychology-driven posts into the queue."""
    items: list[QueueItemRead] = []
    try:
        plan = group_service.pick_batch_plan(data.niche, data.count)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    for step in plan:
        try:
            content = generate_group_post_content(db, step["niche"], step["template"])
            saved = group_service.save_queued_post(db, step["niche"], step["template"], content)
            items.append(QueueItemRead.model_validate(saved))
        except AIServiceError as exc:
            # Rows saved so far are already committed; only surface an error when
            # the batch produced nothing at all (otherwise return the partial
            # result instead of a 5xx that hides the committed rows).
            if not items:
                raise _map_ai_error(exc)
            logger.warning(
                "Queue batch partial failure after %d item(s): %s", len(items), exc
            )
            break
    return items


@router.get("/queue", response_model=dict)
def list_queue(
    status: str | None = Query(None, pattern="^(queued|posted)$"),
    db: Session = Depends(get_db),
) -> dict:
    """List the Group Post Queue newest-first."""
    items = group_service.list_queue(db, status=status)
    return {
        "items": [QueueItemRead.model_validate(item).model_dump() for item in items],
        "total": group_service.count_queue(db),
        "queued": group_service.count_queue(db, status="queued"),
        "posted": group_service.count_queue(db, status="posted"),
    }


@router.post("/queue/{item_id}/copy", summary="Track queue copy", description="Stamp copied_at when the user copies a queued post's text into Facebook.")
def track_copy(item_id: int, db: Session = Depends(get_db)) -> QueueItemRead:
    """Record that a queued post's text was copied."""
    item = group_service.track_queue_copy(db, item_id)
    if item is None:
        raise HTTPException(status_code=404, detail=f"Queue item {item_id} not found.")
    return QueueItemRead.model_validate(item)


@router.post("/queue/{item_id}/mark-posted", summary="Track queue posted", description="Stamp posted_at and flip status to posted when a queued post goes live on Facebook.")
def track_posted(item_id: int, db: Session = Depends(get_db)) -> QueueItemRead:
    """Record that a queued post was published."""
    item = group_service.track_queue_posted(db, item_id)
    if item is None:
        raise HTTPException(status_code=404, detail=f"Queue item {item_id} not found.")
    return QueueItemRead.model_validate(item)


@router.patch("/queue/{item_id}", response_model=QueueItemRead)
def update_queue_item(item_id: int, data: QueueUpdate, db: Session = Depends(get_db)) -> QueueItemRead:
    """Edit a queued caption or flip its queued/posted status."""
    item = group_service.update_queued_post(db, item_id, caption=data.caption, status=data.status)
    if item is None:
        raise HTTPException(status_code=404, detail=f"Queue item {item_id} not found.")
    return QueueItemRead.model_validate(item)


@router.delete("/queue/{item_id}", status_code=204)
def delete_queue_item(item_id: int, db: Session = Depends(get_db)) -> None:
    """Delete a queued post."""
    if not group_service.delete_queued_post(db, item_id):
        raise HTTPException(status_code=404, detail=f"Queue item {item_id} not found.")
    return None


@leads_router.post("", response_model=GroupLeadRead, status_code=201)
def create_group_lead(data: GroupLeadCreate, db: Session = Depends(get_db)) -> GroupLeadRead:
    """Classify a comment, auto-build the 2-step DM, and store the lead."""
    try:
        lead = group_service.create_lead(
            db,
            comment_text=data.comment_text,
            username=data.username,
            group_name=data.group_name,
            product_id=data.product_id,
            user_profile_link=data.user_profile_link,
            conversion_value=data.conversion_value,
            source_template=data.source_template,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    logger.info("Group lead created for user %s.", data.username)
    return GroupLeadRead.model_validate(lead)


@leads_router.get("", response_model=dict)
def list_group_leads(
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    status: str | None = Query(None, pattern="^(unsent|step1_sent|step2_sent|replied|converted|follow_up_sent)$"),
    bucket: str | None = Query(None, pattern="^(attention|reply_check|overdue|cold|m2_waiting|unassigned)$"),
    offset: int | None = Query(None, ge=0),
    db: Session = Depends(get_db),
) -> dict:
    """List stored group leads newest-first with pagination.

    ``bucket`` filters server-side by lifecycle urgency (reply_check,
    overdue, cold, m2_waiting, unassigned, or the union: attention).
    ``offset`` is an alias for ``skip`` kept for API symmetry; when both
    are given, ``offset`` wins.
    """
    from app.services import lead_lifecycle as lifecycle

    effective_skip = offset if offset is not None else skip
    if not bucket:
        items = group_service.list_leads(db, skip=effective_skip, limit=limit, status=status)
        total = group_service.count_leads(db, status=status)
        cfg = lifecycle._lifecycle_cfg(db)
        payload = []
        for item in items:
            row = GroupLeadRead.model_validate(item).model_dump()
            row["urgency"] = lifecycle.compute_lead_urgency(item, cfg=cfg)
            payload.append(row)
        return {"items": payload, "total": total, "skip": effective_skip, "limit": limit}
    # Bucket filtering: one status-scoped query, urgency computed in Python
    # (pure, no extra queries), filtered + paginated server-side. The scan is
    # hard-capped so a pathological dataset can't load unbounded ORM rows.
    all_items = group_service.list_leads(db, skip=0, limit=_BUCKET_SCAN_LIMIT, status=status)
    if len(all_items) >= _BUCKET_SCAN_LIMIT:
        logger.warning(
            "Bucket scan reached the %s-lead cap; some leads may be omitted.",
            _BUCKET_SCAN_LIMIT,
        )
    cfg = lifecycle._lifecycle_cfg(db)
    wanted = set()
    if bucket == "attention":
        wanted = {"reply_check", "overdue", "cold", "m2_waiting", "unassigned"}
    else:
        wanted = {bucket}
    filtered = []
    for item in all_items:
        urgency = lifecycle.compute_lead_urgency(item, cfg=cfg)
        in_bucket = (
            ("reply_check" in wanted and urgency["needs_reply_check"] and not urgency["is_overdue"])
            or ("overdue" in wanted and urgency["is_overdue"])
            or ("cold" in wanted and urgency["is_cold"])
            or ("m2_waiting" in wanted and urgency["m2_waiting"])
            or ("unassigned" in wanted and getattr(item, "assigned_account_id", None) is None)
        )
        if in_bucket:
            row = GroupLeadRead.model_validate(item).model_dump()
            row["urgency"] = urgency
            filtered.append(row)
    total = len(filtered)
    return {
        "items": filtered[effective_skip:effective_skip + limit],
        "total": total,
        "skip": effective_skip,
        "limit": limit,
    }


@leads_router.get("/attention", summary="Bucketed lead attention counts", description="Reply-check, overdue, cold follow-up, M2-waiting and unassigned lead ids. Powers the Attention Board + dashboard widget.")
def leads_attention(db: Session = Depends(get_db)) -> dict:
    """Return bucketed ids of leads needing action (plus unassigned)."""
    from app.models.group_lead import GroupLead
    from app.services import lead_lifecycle as lifecycle

    result = lifecycle.get_leads_needing_attention(db)
    try:
        unassigned = [
            row.id for row in
            db.query(GroupLead.id).filter(GroupLead.assigned_account_id.is_(None))
            .order_by(GroupLead.id.asc()).all()
        ]
    except Exception:
        logger.exception("Unassigned bucket query failed.")
        unassigned = []
    result["unassigned"] = unassigned
    counts = result.get("counts", {})
    counts["unassigned"] = len(unassigned)
    result["counts"] = counts
    return result


@leads_router.post("/bulk-mark-reply", summary="Bulk mark reply state", description="Set reply_state on up to 100 leads in one atomic call (select rows then mark).")
def bulk_mark_reply(data: BulkMarkReplyRequest, db: Session = Depends(get_db)) -> dict:
    """Mark up to 100 leads with the same manual reply-check outcome."""
    from app.services import lead_lifecycle as lifecycle

    updated: list[int] = []
    skipped: list[dict] = []
    try:
        for lead_id in dict.fromkeys(data.ids):
            lead = group_service.get_lead(db, lead_id)
            if lead is None:
                skipped.append({"id": lead_id, "reason": "not found"})
                continue
            try:
                lifecycle.mark_reply_checked(lead_id, data.reply_state, db)
                updated.append(lead_id)
            except ValueError as exc:
                db.rollback()
                skipped.append({"id": lead_id, "reason": str(exc)})
        return {"updated": updated, "skipped": skipped, "reply_state": data.reply_state}
    except Exception:
        db.rollback()
        logger.exception("Bulk mark-reply failed.")
        raise


@leads_router.get("/{lead_id}", response_model=GroupLeadRead)
def get_group_lead(lead_id: int, db: Session = Depends(get_db)) -> GroupLeadRead:
    """Fetch a single group lead, including its computed lifecycle urgency."""
    from app.services import lead_lifecycle as lifecycle

    lead = group_service.get_lead(db, lead_id)
    if lead is None:
        raise HTTPException(status_code=404, detail=f"GroupLead {lead_id} not found.")
    row = GroupLeadRead.model_validate(lead)
    row.urgency = lifecycle.compute_lead_urgency(lead, db=db)
    return row


def _resolve_send_account(db: Session, lead, preferred_id: Optional[int] = None) -> int:
    """Resolve a sendable account id for a lead (rotation-aware).

    A preferred account is honored only when currently usable;
    otherwise rotation picks the best eligible account. Raises 409
    when no account can serve this lead's group.
    """
    from app.models.fb_account import FbAccount
    from app.services import dm_safety

    if preferred_id is not None:
        preferred = db.get(FbAccount, preferred_id)
        if preferred is not None:
            usable, _ = dm_safety.is_account_usable_for_lead(preferred, lead, db)
            if usable:
                return preferred.id
    pick = dm_safety.get_next_available_account(db, lead)
    if pick is None:
        raise HTTPException(status_code=409, detail="No available account for this group")
    if preferred_id is not None:
        # Preferred was unusable — the rotation fallback serves instead.
        logger.info("Send-account fallback: preferred %s unusable, using %s.",
                    preferred_id, pick.id)
    return pick.id

@leads_router.patch("/{lead_id}", response_model=GroupLeadRead)
def update_group_lead(lead_id: int, data: GroupLeadUpdate, db: Session = Depends(get_db)) -> GroupLeadRead:
    """Update a lead's funnel status, profile link, group tag, or revenue value.

    DM Safety guards: ``step1_sent`` stamps M1 + bumps quota; ``step2_sent``
    enforces kill-switch (409), the M1->M2 gap (409) and the per-account
    quota (429) first. NULL-assigned leads auto-pick a rotation account.
    """
    from app.services import dm_safety

    lead = group_service.get_lead(db, lead_id)
    if lead is None:
        raise HTTPException(status_code=404, detail=f"GroupLead {lead_id} not found.")
    requested_status = data.status
    if requested_status in ("step1_sent", "step2_sent"):
        if requested_status == "step2_sent":
            from app.services import settings_service

            if settings_service.is_kill_switch_active(db):
                raise HTTPException(status_code=409, detail="Kill switch active — DMs blocked.")
        account_id = _resolve_send_account(
            db, lead, data.assigned_account_id or getattr(lead, "assigned_account_id", None)
        )
        try:
            if requested_status == "step1_sent":
                dm_safety.record_dm_sent(account_id, 1, db, lead_id)
            else:
                gap = dm_safety.get_min_gap_seconds(db)
                allowed, reason = dm_safety.can_send_step2(lead, gap_seconds=gap, db=db)
                if not allowed:
                    raise HTTPException(status_code=409, detail=reason)
                rate_ok, rate_reason = dm_safety.check_rate_limit(account_id, db)
                if not rate_ok:
                    raise HTTPException(status_code=429, detail=rate_reason)
                dm_safety.record_dm_sent(account_id, 2, db, lead_id)
        except HTTPException:
            raise
        except ValueError as exc:
            db.rollback()
            raise HTTPException(status_code=422, detail=str(exc))
        except Exception:
            db.rollback()
            logger.exception("DM safety update failed for lead %s.", lead_id)
            raise
        # Apply any accompanying non-status fields on the freshly stamped row.
        try:
            updated = group_service.update_lead(
                db,
                lead_id,
                user_profile_link=data.user_profile_link,
                conversion_value=data.conversion_value,
                group_name=data.group_name,
                assigned_account_id=data.assigned_account_id,
            )
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc))
        if updated is None:
            raise HTTPException(status_code=404, detail=f"GroupLead {lead_id} not found.")
        return GroupLeadRead.model_validate(updated)
    try:
        lead = group_service.update_lead(
            db,
            lead_id,
            status=data.status,
            user_profile_link=data.user_profile_link,
            conversion_value=data.conversion_value,
            group_name=data.group_name,
            assigned_account_id=data.assigned_account_id,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    if lead is None:
        raise HTTPException(status_code=404, detail=f"GroupLead {lead_id} not found.")
    return GroupLeadRead.model_validate(lead)


@leads_router.get("/{lead_id}/send-status", summary="M2 send readiness", description="Live M1→M2 gap + quota check for the DM modal. No state change.")
def lead_send_status(lead_id: int, db: Session = Depends(get_db)) -> dict:
    """Live M2 readiness for the DM modal (no state change)."""
    from app.services import dm_safety

    lead = group_service.get_lead(db, lead_id)
    if lead is None:
        raise HTTPException(status_code=404, detail=f"GroupLead {lead_id} not found.")
    gap = dm_safety.get_min_gap_seconds(db)
    allowed, reason = dm_safety.can_send_step2(lead, gap_seconds=gap, db=db)
    seconds_left = dm_safety.seconds_until_m2(lead, gap_seconds=gap, db=db)
    account_id = (
        getattr(lead, "assigned_account_id", None)
        or dm_safety.resolve_account(db, None).id
    )
    try:
        rate_ok, rate_reason = dm_safety.check_rate_limit(account_id, db)
    except Exception:
        logger.exception("Rate-limit check failed for lead %s.", lead_id)
        rate_ok, rate_reason = False, "Rate-limit check unavailable"
    return {
        "can_send_m2": bool(allowed and rate_ok),
        "reason": reason if not allowed else rate_reason,
        "seconds_until_m2": int(seconds_left) if not allowed else 0,
        "rate_limit_ok": bool(rate_ok),
        "rate_limit_reason": rate_reason,
        "account_id": account_id,
    }


@safety_router.get("/status", summary="DM quota status", description="Current per-account hourly/daily DM counters, limits, and next reset time.")
def dm_safety_status(db: Session = Depends(get_db)) -> dict:
    """Current DM quota counters for the Groups header widget."""
    from app.services import dm_safety

    return dm_safety.quota_snapshot(db)


@leads_router.post("/{lead_id}/mark-reply", response_model=GroupLeadRead, summary="Mark reply state after manual check", description="Record the outcome of a manual DM-thread reply check (replied / no_reply / bounced). M1 must already be sent; status stays step1_sent so M2 unlocks via the Phase 1 gap logic.")
def mark_lead_reply(lead_id: int, data: MarkReplyRequest, db: Session = Depends(get_db)) -> GroupLeadRead:
    """Stamp a manual reply check on a lead."""
    from app.services import lead_lifecycle as lifecycle
    from app.services import settings_service

    lead = group_service.get_lead(db, lead_id)
    if lead is None:
        raise HTTPException(status_code=404, detail=f"GroupLead {lead_id} not found.")
    if settings_service.is_kill_switch_active(db):
        raise HTTPException(status_code=409, detail="Kill switch active — DMs blocked.")
    # Auto-pick a rotation account for NULL-assigned leads (persisted below).
    pick_id = _resolve_send_account(
        db, lead, getattr(lead, "assigned_account_id", None)
    )
    try:
        updated = lifecycle.mark_reply_checked(lead_id, data.reply_state, db)
    except ValueError as exc:
        message = str(exc)
        if "M1 not sent" in message:
            raise HTTPException(status_code=400, detail=message)
        raise HTTPException(status_code=422, detail=message)
    if getattr(updated, "assigned_account_id", None) is None:
        try:
            updated = group_service.update_lead(db, lead_id, assigned_account_id=pick_id)
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc))
    row = GroupLeadRead.model_validate(updated)
    row.urgency = lifecycle.compute_lead_urgency(updated, db=db)
    return row


@leads_router.post("/{lead_id}/follow-up", summary="Send cold-lead follow-up", description="Send the M3 re-engagement message to a cold lead. Requires follow-ups enabled, remaining quota of max_follow_ups, a cold lead, and Phase 1 rate-limit headroom. Consumes quota via record_dm_sent(step=3).")
def send_lead_follow_up(lead_id: int, db: Session = Depends(get_db)) -> dict:
    """Send the M3 follow-up to a cold lead, consuming DM quota."""
    from app.services import dm_safety
    from app.services import lead_lifecycle as lifecycle

    lead = group_service.get_lead(db, lead_id)
    if lead is None:
        raise HTTPException(status_code=404, detail=f"GroupLead {lead_id} not found.")
    if getattr(lead, "step1_sent_at", None) is None:
        raise HTTPException(status_code=400, detail="M1 not sent yet.")
    from app.services import settings_service

    if settings_service.is_kill_switch_active(db):
        raise HTTPException(status_code=409, detail="Kill switch active — DMs blocked.")
    allowed, reason = dm_safety.can_send_followup(lead, db=db)
    if not allowed:
        raise HTTPException(status_code=409, detail=reason)
    account_id = _resolve_send_account(
        db, lead, getattr(lead, "assigned_account_id", None)
    )
    rate_ok, rate_reason = dm_safety.check_rate_limit(account_id, db)
    if not rate_ok:
        raise HTTPException(status_code=429, detail=rate_reason)
    try:
        updated = lifecycle.record_follow_up_sent(lead_id, db)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    quota = dm_safety.quota_snapshot(db, account_id)
    row = GroupLeadRead.model_validate(updated).model_dump()
    row["urgency"] = lifecycle.compute_lead_urgency(updated, db=db)
    return {"lead": row, "quota": quota}


@leads_router.delete("/{lead_id}", status_code=204)
def delete_group_lead(lead_id: int, db: Session = Depends(get_db)) -> None:
    """Delete a group lead."""
    if not group_service.delete_lead(db, lead_id):
        raise HTTPException(status_code=404, detail=f"GroupLead {lead_id} not found.")
    return None
