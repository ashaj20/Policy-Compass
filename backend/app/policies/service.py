"""Policy upload (US-006)."""

import hashlib
from dataclasses import dataclass
from datetime import UTC, date, datetime

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.audit import AuditAction, record
from app.errors import AppError
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


def start_processing(version: PolicyVersion) -> None:
    """Hand a new version to document processing.

    Extraction, indexing and validation are built in US-011; until then new versions stay in
    PROCESSING and are never retrievable (only READY, active versions ever will be).
    """


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
    try:
        detected = detect_policy_file(filename, data, max_bytes)
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

    key = storage.save(f"policies/{organisation.id}/{policy.id}", data, detected.extension)
    version = PolicyVersion(
        policy=policy,
        organisation_id=organisation.id,
        version_label=meta.version_label,
        effective_date=meta.effective_date,
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
    start_processing(version)
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
