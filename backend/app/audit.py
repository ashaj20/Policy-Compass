"""Audit trail service (US-005A, Spec §15, AC-08).

Call `record()` inside the same transaction as the change it describes, before committing, so
a change can never be saved without its audit event (and vice versa).
"""

from enum import StrEnum

from sqlalchemy.orm import Session

from app.models import User
from app.models.audit import AuditEvent


class AuditAction(StrEnum):
    # Organisation
    ORGANISATION_CREATED = "ORGANISATION_CREATED"
    ORGANISATION_SETTINGS_CHANGED = "ORGANISATION_SETTINGS_CHANGED"
    PUBLIC_URL_CHANGED = "PUBLIC_URL_CHANGED"
    LOGO_UPDATED = "LOGO_UPDATED"
    LOGO_REMOVED = "LOGO_REMOVED"
    # Members
    MEMBER_INVITED = "MEMBER_INVITED"
    INVITATION_RESENT = "INVITATION_RESENT"
    INVITATION_CANCELLED = "INVITATION_CANCELLED"
    MEMBER_JOINED = "MEMBER_JOINED"
    MEMBER_ROLE_CHANGED = "MEMBER_ROLE_CHANGED"
    MEMBER_REMOVED = "MEMBER_REMOVED"
    # Policies
    POLICY_UPLOADED = "POLICY_UPLOADED"
    POLICY_EDITED = "POLICY_EDITED"
    POLICY_ARCHIVED = "POLICY_ARCHIVED"
    POLICY_RESTORED = "POLICY_RESTORED"
    POLICY_VERSION_CREATED = "POLICY_VERSION_CREATED"
    POLICY_VERSION_REPLACED = "POLICY_VERSION_REPLACED"
    POLICY_VERSION_SUBMITTED = "POLICY_VERSION_SUBMITTED"
    POLICY_VERSION_WITHDRAWN = "POLICY_VERSION_WITHDRAWN"
    POLICY_VERSION_REJECTED = "POLICY_VERSION_REJECTED"
    POLICY_ACTIVATED = "POLICY_ACTIVATED"
    POLICY_SUPERSEDED = "POLICY_SUPERSEDED"
    POLICY_PROCESSING_RETRIED = "POLICY_PROCESSING_RETRIED"
    POLICY_OWNER_CHANGED = "POLICY_OWNER_CHANGED"
    PUBLIC_HELP_ROUTE_CHANGED = "PUBLIC_HELP_ROUTE_CHANGED"
    # Contacts
    CONTACT_CREATED = "CONTACT_CREATED"
    CONTACT_UPDATED = "CONTACT_UPDATED"
    CONTACT_DELETED = "CONTACT_DELETED"
    HELP_ROUTE_CREATED = "HELP_ROUTE_CREATED"
    HELP_ROUTE_UPDATED = "HELP_ROUTE_UPDATED"
    HELP_ROUTE_DELETED = "HELP_ROUTE_DELETED"
    DEFAULT_HELP_ROUTE_CHANGED = "DEFAULT_HELP_ROUTE_CHANGED"


def record(
    db: Session,
    *,
    organisation_id,
    actor: User | None,
    action: AuditAction,
    object_type: str,
    object_id=None,
    object_label: str | None = None,
    previous: dict | None = None,
    new: dict | None = None,
) -> AuditEvent:
    event = AuditEvent(
        organisation_id=organisation_id,
        actor_user_id=actor.id if actor else None,
        actor_email=actor.email if actor else None,
        action=action,
        object_type=object_type,
        object_id=str(object_id) if object_id is not None else None,
        object_label=object_label,
        previous=previous,
        new=new,
    )
    db.add(event)
    return event


def changed_fields(before: dict, after: dict) -> tuple[dict, dict]:
    """Only the fields whose values actually differ, as (previous, new)."""
    keys = [k for k in after if before.get(k) != after.get(k)]
    return {k: before.get(k) for k in keys}, {k: after.get(k) for k in keys}
