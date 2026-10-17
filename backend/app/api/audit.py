"""Activity history (US-005A). Read-only and for administrators only: there are deliberately no
endpoints to change or delete audit events."""

import uuid
from datetime import datetime

from fastapi import APIRouter, Query
from pydantic import BaseModel
from sqlalchemy import select

from app.deps import AdminOf, DbSession
from app.models import AuditEvent

router = APIRouter(tags=["audit"])


class AuditEventOut(BaseModel):
    id: str
    timestamp: datetime
    actor: str | None
    action: str
    object_type: str
    object_id: str | None
    object_label: str | None
    previous: dict | None
    new: dict | None


class AuditPageOut(BaseModel):
    events: list[AuditEventOut]
    # Pass as `before` to fetch the next (older) page; null when there are no more.
    next_before: str | None


@router.get("/organisations/{organisation_id}/audit-events")
def list_audit_events(
    admin: AdminOf,
    db: DbSession,
    limit: int = Query(50, ge=1, le=100),
    before: uuid.UUID | None = None,
) -> AuditPageOut:
    query = select(AuditEvent).where(AuditEvent.organisation_id == admin.organisation_id)
    if before is not None:
        cursor = db.get(AuditEvent, before)
        # Cursors from another organisation are ignored rather than leaking anything.
        if cursor is not None and cursor.organisation_id == admin.organisation_id:
            query = query.where(AuditEvent.seq < cursor.seq)

    rows = list(db.scalars(query.order_by(AuditEvent.seq.desc()).limit(limit + 1)))
    has_more = len(rows) > limit
    rows = rows[:limit]
    return AuditPageOut(
        events=[
            AuditEventOut(
                id=str(e.id),
                timestamp=e.created_at,
                actor=e.actor_email,
                action=e.action,
                object_type=e.object_type,
                object_id=e.object_id,
                object_label=e.object_label,
                previous=e.previous,
                new=e.new,
            )
            for e in rows
        ],
        next_before=str(rows[-1].id) if has_more else None,
    )
