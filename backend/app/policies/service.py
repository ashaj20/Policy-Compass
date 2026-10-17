"""Policy upload (US-006)."""

import hashlib
from dataclasses import dataclass
from datetime import UTC, date, datetime

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, selectinload

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


@dataclass
class PolicyFilters:
    audience: Audience | None = None
    status: VersionStatus | None = None
    category: str | None = None
    search: str | None = None


def latest_version(policy: Policy) -> PolicyVersion:
    return policy.versions[-1]


def display_status(policy: Policy) -> str:
    """The status shown for a policy: its newest version's status (refined by versioning)."""
    return latest_version(policy).status


def list_policies(
    db: Session, organisation: Organisation, filters: PolicyFilters, staff_view: bool
) -> list[Policy]:
    """Policies in one organisation, newest version status included.

    Staff only see policies that are ready to use; drafts, processing and failed uploads are
    not approved knowledge yet and stay visible to administrators only.
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

    wanted = VersionStatus.READY if staff_view else filters.status
    if wanted:
        policies = [p for p in policies if display_status(p) == wanted]
    return policies
