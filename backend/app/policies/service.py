"""Policies: upload, listing, details, archiving, versions and the approval workflow."""

import hashlib
from dataclasses import dataclass
from datetime import UTC, date, datetime

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, selectinload

from app.audit import AuditAction, changed_fields, record
from app.errors import AppError, NotFound, PermissionDenied
from app.models import Audience, Organisation, Policy, PolicyVersion, User, VersionStatus
from app.policies.validation import FileRejected, detect_policy_file, display_filename
from app.storage import Storage

NAME_TAKEN = (
    "A policy with this name already exists. To update it, upload a new version from the "
    "policy's page."
)


@dataclass
class PolicyUpload:
    name: str
    version_label: str
    effective_date: date
    audience: Audience
    category: str
    source: str | None


def touch(policy: Policy, when: datetime | None = None) -> datetime:
    """Mark the policy as changed (US-008 "last updated"). Call on every policy/version change."""
    policy.updated_at = when or datetime.now(UTC)
    return policy.updated_at


def _store_version(
    db: Session,
    policy: Policy,
    actor: User,
    version_label: str,
    effective_date: date,
    filename: str,
    data: bytes,
    max_bytes: int,
    storage: Storage,
) -> PolicyVersion:
    """Validate and store an uploaded file as a new PROCESSING version (caller commits)."""
    try:
        detected = detect_policy_file(filename, data, max_bytes)
    except FileRejected as exc:
        raise AppError(422, "invalid_file", str(exc), {"file": str(exc)}) from None
    key = storage.save(f"policies/{policy.organisation_id}/{policy.id}", data, detected.extension)
    version = PolicyVersion(
        policy=policy,
        organisation_id=policy.organisation_id,
        version_label=version_label,
        effective_date=effective_date,
        status=VersionStatus.PROCESSING,
        storage_key=key,
        original_filename=display_filename(filename),
        content_type=detected.content_type,
        file_size=len(data),
        sha256=hashlib.sha256(data).hexdigest(),
        uploaded_by_id=actor.id,
        uploaded_at=touch(policy),
    )
    db.add(version)
    db.flush()
    return version


def upload_policy(
    db: Session,
    organisation: Organisation,
    actor: User,
    meta: PolicyUpload,
    filename: str,
    data: bytes,
    max_bytes: int,
    storage: Storage,
) -> Policy:
    # Check the file before creating anything.
    try:
        detect_policy_file(filename, data, max_bytes)
    except FileRejected as exc:
        raise AppError(422, "invalid_file", str(exc), {"file": str(exc)}) from None

    if db.scalar(
        select(Policy.id).where(
            Policy.organisation_id == organisation.id, func.lower(Policy.name) == meta.name.lower()
        )
    ):
        raise AppError(409, "policy_exists", NAME_TAKEN, {"name": NAME_TAKEN})

    policy = Policy(
        organisation_id=organisation.id,
        name=meta.name,
        category=meta.category,
        audience=meta.audience,
        source=meta.source,
        created_by_id=actor.id,
    )
    db.add(policy)
    db.flush()

    version = _store_version(
        db,
        policy,
        actor,
        meta.version_label,
        meta.effective_date,
        filename,
        data,
        max_bytes,
        storage,
    )
    key = version.storage_key
    record(
        db,
        organisation_id=organisation.id,
        actor=actor,
        action=AuditAction.POLICY_UPLOADED,
        object_type="policy",
        object_id=policy.id,
        object_label=policy.name,
        new={
            "version": meta.version_label,
            "effective_date": meta.effective_date.isoformat(),
            "audience": str(meta.audience),
            "category": meta.category,
            "file": version.original_filename,
        },
    )
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        storage.delete(key)
        raise AppError(409, "policy_exists", NAME_TAKEN, {"name": NAME_TAKEN}) from None
    return policy


def categories(db: Session, organisation: Organisation) -> list[str]:
    return list(
        db.scalars(
            select(Policy.category)
            .where(Policy.organisation_id == organisation.id)
            .distinct()
            .order_by(Policy.category)
        )
    )


@dataclass
class PolicyFilters:
    audience: Audience | None = None
    status: VersionStatus | None = None
    category: str | None = None
    search: str | None = None


IN_PROGRESS = (VersionStatus.PROCESSING, VersionStatus.DRAFT, VersionStatus.READY)
AWAITING_REVIEW = (VersionStatus.DRAFT, VersionStatus.READY)


def latest_version(policy: Policy) -> PolicyVersion:
    return policy.versions[-1]


def active_version(policy: Policy) -> PolicyVersion | None:
    return next((v for v in policy.versions if v.status == VersionStatus.ACTIVE), None)


def pending_version(policy: Policy) -> PolicyVersion | None:
    """The newest version that hasn't gone live yet, if it is still in progress or failed."""
    latest = latest_version(policy)
    if latest.status in (*IN_PROGRESS, VersionStatus.FAILED):
        return latest
    return None


def display_version(policy: Policy) -> PolicyVersion:
    """The version a policy is known by: the active one, or else the newest."""
    return active_version(policy) or latest_version(policy)


def display_status(policy: Policy) -> str:
    """Archived if archived; Active if a version is live; otherwise the newest version's status."""
    if policy.is_archived:
        return VersionStatus.ARCHIVED
    return display_version(policy).status


def visible_to_staff(policy: Policy) -> bool:
    """Staff see live policies, plus versions waiting for review so they can review them."""
    if policy.is_archived:
        return False
    return active_version(policy) is not None or latest_version(policy).status in AWAITING_REVIEW


def staff_can_read_version(version: PolicyVersion) -> bool:
    return version.status in (VersionStatus.ACTIVE, *AWAITING_REVIEW)


def list_policies(
    db: Session, organisation: Organisation, filters: PolicyFilters, staff_view: bool
) -> list[Policy]:
    """Policies in one organisation, newest version status included.

    Staff see live policies and versions awaiting review; processing-only, failed-only and
    archived policies stay visible to administrators only.
    """
    query = (
        select(Policy)
        .where(Policy.organisation_id == organisation.id)
        .options(selectinload(Policy.versions))
        .order_by(func.lower(Policy.name))
    )
    if filters.audience:
        query = query.where(Policy.audience == filters.audience)
    if filters.category:
        query = query.where(func.lower(Policy.category) == filters.category.lower())
    if filters.search:
        term = f"%{filters.search.strip().lower()}%"
        query = query.where(
            func.lower(Policy.name).like(term) | func.lower(Policy.category).like(term)
        )
    policies = list(db.scalars(query.limit(1000)))

    if staff_view:
        return [p for p in policies if visible_to_staff(p)]
    if filters.status:
        policies = [p for p in policies if display_status(p) == filters.status]
    return policies


def get_policy(db: Session, organisation: Organisation, policy_id, staff_view: bool) -> Policy:
    """One policy in this organisation, or 404. Staff only open policies visible to staff."""
    policy = db.scalar(
        select(Policy)
        .where(Policy.id == policy_id, Policy.organisation_id == organisation.id)
        .options(selectinload(Policy.versions))
    )
    if policy is None or (staff_view and not visible_to_staff(policy)):
        raise NotFound("This policy is no longer available.")
    return policy


EDITABLE_POLICY_FIELDS = ("name", "category", "audience", "source")


def edit_policy(db: Session, policy: Policy, actor: User, changes: dict) -> None:
    """Edit policy-level details (US-023). Only fields that actually change are audited."""
    if "name" in changes and changes["name"].lower() != policy.name.lower():
        clash = db.scalar(
            select(Policy.id).where(
                Policy.organisation_id == policy.organisation_id,
                func.lower(Policy.name) == changes["name"].lower(),
                Policy.id != policy.id,
            )
        )
        if clash:
            msg = "Another policy already has this name"
            raise AppError(409, "policy_exists", msg, {"name": msg})

    before = {
        f: str(getattr(policy, f)) if getattr(policy, f) else None for f in EDITABLE_POLICY_FIELDS
    }
    for field, value in changes.items():
        if field in EDITABLE_POLICY_FIELDS:
            setattr(policy, field, value)
    after = {
        f: str(getattr(policy, f)) if getattr(policy, f) else None for f in EDITABLE_POLICY_FIELDS
    }
    previous, new = changed_fields(before, after)
    if not new:
        return
    touch(policy)
    record(
        db,
        organisation_id=policy.organisation_id,
        actor=actor,
        action=AuditAction.POLICY_EDITED,
        object_type="policy",
        object_id=policy.id,
        object_label=policy.name,
        previous=previous,
        new=new,
    )
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        msg = "Another policy already has this name"
        raise AppError(409, "policy_exists", msg, {"name": msg}) from None


def get_version(policy: Policy, version_id) -> PolicyVersion:
    for v in policy.versions:
        if str(v.id) == str(version_id):
            return v
    raise NotFound("This document is no longer available.")


def _audit_policy(db: Session, policy: Policy, actor: User, action: AuditAction, **kw) -> None:
    record(
        db,
        organisation_id=policy.organisation_id,
        actor=actor,
        action=action,
        object_type="policy",
        object_id=policy.id,
        object_label=policy.name,
        **kw,
    )


def archive_policy(db: Session, policy: Policy, actor: User) -> None:
    """Stop using a policy for answers without deleting anything (US-009)."""
    if policy.is_archived:
        raise AppError(409, "already_archived", "This policy is already archived.")
    previous_status = display_status(policy)
    policy.archived_at = touch(policy)
    policy.archived_by_id = actor.id
    _audit_policy(
        db,
        policy,
        actor,
        AuditAction.POLICY_ARCHIVED,
        previous={"status": str(previous_status)},
        new={"status": str(VersionStatus.ARCHIVED)},
    )
    db.commit()


def restore_policy(db: Session, policy: Policy, actor: User) -> None:
    """Bring an archived policy back exactly as it was before archiving."""
    if not policy.is_archived:
        raise AppError(409, "not_archived", "This policy isn't archived.")
    policy.archived_at = None
    policy.archived_by_id = None
    touch(policy)
    _audit_policy(
        db,
        policy,
        actor,
        AuditAction.POLICY_RESTORED,
        previous={"status": str(VersionStatus.ARCHIVED)},
        new={"status": str(display_status(policy))},
    )
    db.commit()


# --- Versions and approval (US-010A, REVIEW F-decisions) ---


def _version_label(version: PolicyVersion) -> dict:
    return {"version": version.version_label}


def _require_not_archived(policy: Policy) -> None:
    if policy.is_archived:
        raise AppError(409, "policy_archived", "Restore this policy before changing its versions.")


def _lock(db: Session, policy: Policy) -> None:
    """Serialise workflow changes on one policy so two people can't approve at once."""
    db.scalar(select(Policy.id).where(Policy.id == policy.id).with_for_update())


def upload_new_version(
    db: Session,
    policy: Policy,
    actor: User,
    version_label: str,
    effective_date: date,
    filename: str,
    data: bytes,
    max_bytes: int,
    storage: Storage,
) -> PolicyVersion:
    """Add a new version alongside the active one. The active version stays live meanwhile."""
    _require_not_archived(policy)
    _lock(db, policy)
    if any(v.version_label.lower() == version_label.lower() for v in policy.versions):
        msg = "This version number has already been used for this policy"
        raise AppError(409, "version_exists", msg, {"version": msg})

    # Only one version is ever in progress: an older one that never went live is replaced.
    now = datetime.now(UTC)
    for old in policy.versions:
        if old.status in IN_PROGRESS:
            old.status = VersionStatus.SUPERSEDED
            old.superseded_at = now
            old.superseded_by_id = actor.id
            _audit_policy(
                db,
                policy,
                actor,
                AuditAction.POLICY_VERSION_REPLACED,
                previous=_version_label(old),
                new={"version": version_label},
            )

    version = _store_version(
        db, policy, actor, version_label, effective_date, filename, data, max_bytes, storage
    )
    _audit_policy(
        db,
        policy,
        actor,
        AuditAction.POLICY_VERSION_CREATED,
        new={
            "version": version_label,
            "effective_date": effective_date.isoformat(),
            "file": version.original_filename,
        },
    )
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        storage.delete(version.storage_key)
        msg = "This version number has already been used for this policy"
        raise AppError(409, "version_exists", msg, {"version": msg}) from None
    return version


def mark_ready(db: Session, policy: Policy, version: PolicyVersion, actor: User) -> None:
    """Any member confirms a processed draft is ready for an administrator's approval."""
    _require_not_archived(policy)
    _lock(db, policy)
    if version.status != VersionStatus.DRAFT:
        raise AppError(
            409,
            "not_draft",
            "Only a draft version that has finished processing can be marked ready.",
        )
    version.status = VersionStatus.READY
    version.submitted_by_id = actor.id
    version.submitted_at = touch(policy)
    _audit_policy(
        db, policy, actor, AuditAction.POLICY_VERSION_SUBMITTED, new=_version_label(version)
    )
    db.commit()


def withdraw(
    db: Session, policy: Policy, version: PolicyVersion, actor: User, is_admin: bool
) -> None:
    """The person who marked a version ready (or an administrator) takes it back to Draft."""
    _lock(db, policy)
    if version.status != VersionStatus.READY:
        raise AppError(409, "not_ready", "Only a version awaiting approval can be withdrawn.")
    if not is_admin and version.submitted_by_id != actor.id:
        raise PermissionDenied("Only the person who marked this version ready can withdraw it.")
    version.status = VersionStatus.DRAFT
    version.submitted_by_id = None
    version.submitted_at = None
    touch(policy)
    _audit_policy(
        db, policy, actor, AuditAction.POLICY_VERSION_WITHDRAWN, previous=_version_label(version)
    )
    db.commit()


def reject(db: Session, policy: Policy, version: PolicyVersion, actor: User, reason: str) -> None:
    """An administrator sends a version back to Draft, saying why."""
    _lock(db, policy)
    if version.status != VersionStatus.READY:
        raise AppError(409, "not_ready", "Only a version awaiting approval can be sent back.")
    version.status = VersionStatus.DRAFT
    version.submitted_by_id = None
    version.submitted_at = None
    version.rejected_by_id = actor.id
    version.rejected_at = touch(policy)
    version.rejection_reason = reason
    _audit_policy(
        db,
        policy,
        actor,
        AuditAction.POLICY_VERSION_REJECTED,
        previous=_version_label(version),
        new={"reason": reason},
    )
    db.commit()


def activate(db: Session, policy: Policy, version: PolicyVersion, actor: User) -> None:
    """An administrator approves a Ready version: it goes live and the previous one is superseded.

    Only a READY version can be activated, and READY is only reachable after processing has
    succeeded, so a failed or unfinished update can never replace the active version (AC-04).
    Who and when are recorded on both versions and in the audit trail, in one transaction.
    """
    _require_not_archived(policy)
    _lock(db, policy)
    db.refresh(version)
    if version.status != VersionStatus.READY:
        raise AppError(
            409, "not_ready", "Only a version marked ready for approval can be approved."
        )
    now = touch(policy)
    previous = active_version(policy)
    if previous is not None:
        previous.status = VersionStatus.SUPERSEDED
        previous.superseded_at = now
        previous.superseded_by_id = actor.id
        db.flush()  # free the single active slot before filling it
        _audit_policy(
            db,
            policy,
            actor,
            AuditAction.POLICY_SUPERSEDED,
            previous={"version": previous.version_label, "status": str(VersionStatus.ACTIVE)},
            new={"version": previous.version_label, "status": str(VersionStatus.SUPERSEDED)},
        )
    version.status = VersionStatus.ACTIVE
    version.activated_at = now
    version.activated_by_id = actor.id
    _audit_policy(
        db,
        policy,
        actor,
        AuditAction.POLICY_ACTIVATED,
        previous={"active_version": previous.version_label if previous else None},
        new={"active_version": version.version_label},
    )
    db.commit()
