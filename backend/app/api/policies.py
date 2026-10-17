"""Policy endpoints (US-006). Uploading is for administrators only."""

import uuid
from datetime import date, datetime
from typing import Annotated

from fastapi import APIRouter, Form, Response, UploadFile, status
from fastapi.exceptions import RequestValidationError
from pydantic import BaseModel, ValidationError, field_validator

from app.deps import AdminOf, AppSettings, DbSession, FileStorage, MemberOf, Runner
from app.errors import AppError, NotFound
from app.models import Audience, Policy, PolicyVersion, Role, VersionStatus
from app.policies import service
from app.policies.validation import (
    check_category,
    check_effective_date,
    check_policy_name,
    check_source,
    check_version_label,
)

router = APIRouter(prefix="/organisations/{organisation_id}/policies", tags=["policies"])


class PolicyUploadForm(BaseModel):
    name: str
    version: str
    effective_date: date
    audience: Audience
    category: str
    source: str | None = None

    _name = field_validator("name")(check_policy_name)
    _version = field_validator("version")(check_version_label)
    _effective = field_validator("effective_date")(check_effective_date)
    _category = field_validator("category")(check_category)
    _source = field_validator("source")(check_source)


class VersionOut(BaseModel):
    id: str
    version: str
    effective_date: date
    status: str
    original_filename: str
    file_size: int
    uploaded_at: datetime
    uploaded_by: str | None
    submitted_at: datetime | None = None
    submitted_by: str | None = None
    activated_at: datetime | None = None
    activated_by: str | None = None
    superseded_at: datetime | None = None
    superseded_by: str | None = None
    rejected_at: datetime | None = None
    rejected_by: str | None = None
    rejection_reason: str | None = None
    processing_stage: str | None = None
    processed_at: datetime | None = None
    chunk_count: int | None = None
    failure_reason: str | None = None
    error_id: str | None = None


class PolicyOut(BaseModel):
    id: str
    name: str
    category: str
    audience: Audience
    source: str | None
    created_at: datetime
    updated_at: datetime
    latest_version: VersionOut


def _email(user) -> str | None:
    return user.email if user else None


def version_out(v: PolicyVersion) -> VersionOut:
    return VersionOut(
        id=str(v.id),
        version=v.version_label,
        effective_date=v.effective_date,
        status=v.status,
        original_filename=v.original_filename,
        file_size=v.file_size,
        uploaded_at=v.uploaded_at,
        uploaded_by=_email(v.uploaded_by),
        submitted_at=v.submitted_at,
        submitted_by=_email(v.submitted_by),
        activated_at=v.activated_at,
        activated_by=_email(v.activated_by),
        superseded_at=v.superseded_at,
        superseded_by=_email(v.superseded_by),
        rejected_at=v.rejected_at if v.status == VersionStatus.DRAFT else None,
        rejected_by=_email(v.rejected_by) if v.status == VersionStatus.DRAFT else None,
        rejection_reason=v.rejection_reason if v.status == VersionStatus.DRAFT else None,
        processing_stage=v.processing_stage,
        processed_at=v.processed_at,
        chunk_count=v.chunk_count,
        failure_reason=v.failure_reason,
        error_id=v.error_id,
    )


def policy_out(p: Policy) -> PolicyOut:
    return PolicyOut(
        id=str(p.id),
        name=p.name,
        category=p.category,
        audience=p.audience,
        source=p.source,
        created_at=p.created_at,
        updated_at=p.updated_at,
        latest_version=version_out(p.versions[-1]),
    )


class PolicyListItem(BaseModel):
    id: str
    name: str
    category: str
    audience: Audience
    status: str
    version: str
    effective_date: date
    updated_at: datetime
    # The newest version that isn't live yet (e.g. awaiting approval), if any.
    pending_version: str | None = None
    pending_status: str | None = None
    # Policy owners are configured in US-024.
    owner: str | None = None


class PolicyListOut(BaseModel):
    policies: list[PolicyListItem]
    categories: list[str]


@router.get("")
def list_policies(
    membership: MemberOf,
    db: DbSession,
    audience: Audience | None = None,
    status: VersionStatus | None = None,
    category: str | None = None,
    q: str | None = None,
) -> PolicyListOut:
    staff_view = membership.role != Role.ADMIN
    policies = service.list_policies(
        db,
        membership.organisation,
        service.PolicyFilters(audience=audience, status=status, category=category, search=q),
        staff_view=staff_view,
    )
    items = []
    for p in policies:
        v = service.display_version(p)
        pending = service.pending_version(p)
        show_pending = pending is not None and pending.id != v.id and not p.is_archived
        if staff_view and show_pending and not service.staff_can_read_version(pending):
            show_pending = False
        items.append(
            PolicyListItem(
                id=str(p.id),
                name=p.name,
                category=p.category,
                audience=p.audience,
                status=service.display_status(p),
                version=v.version_label,
                effective_date=v.effective_date,
                updated_at=p.updated_at,
                pending_version=pending.version_label if show_pending else None,
                pending_status=pending.status if show_pending else None,
            )
        )
    categories = (
        sorted({i.category for i in items})
        if staff_view
        else service.categories(db, membership.organisation)
    )
    return PolicyListOut(policies=items, categories=categories)


@router.post("", status_code=status.HTTP_201_CREATED)
def upload_policy(
    admin: AdminOf,
    db: DbSession,
    settings: AppSettings,
    storage: FileStorage,
    runner: Runner,
    name: Annotated[str, Form()] = "",
    version: Annotated[str, Form()] = "",
    effective_date: Annotated[str, Form()] = "",
    audience: Annotated[str, Form()] = "",
    category: Annotated[str, Form()] = "",
    source: Annotated[str, Form()] = "",
    file: UploadFile | None = None,
) -> PolicyOut:
    # Validate the form fields with the same rules and per-field messages as JSON bodies.
    try:
        form = PolicyUploadForm.model_validate(
            {
                "name": name,
                "version": version,
                "effective_date": effective_date or None,
                "audience": audience or None,
                "category": category,
                "source": source,
            }
        )
    except ValidationError as exc:
        raise RequestValidationError(exc.errors()) from None

    if file is None or not file.filename:
        msg = "Choose a PDF or Word document to upload"
        raise AppError(
            422, "validation_error", "Please check the highlighted fields.", {"file": msg}
        )
    # Read one byte past the limit so oversized files are caught without reading them fully.
    data = file.file.read(settings.policy_max_bytes + 1)
    policy = service.upload_policy(
        db,
        admin.organisation,
        admin.user,
        service.PolicyUpload(
            name=form.name,
            version_label=form.version,
            effective_date=form.effective_date,
            audience=form.audience,
            category=form.category,
            source=form.source,
        ),
        file.filename,
        data,
        settings.policy_max_bytes,
        storage,
    )
    db.refresh(policy)
    runner.submit(policy.versions[-1].id)
    db.refresh(policy)
    return policy_out(policy)


@router.get("/categories")
def list_categories(admin: AdminOf, db: DbSession) -> list[str]:
    """Categories already in use, to suggest when uploading."""
    return service.categories(db, admin.organisation)


class PolicyEditIn(BaseModel):
    """Only the fields sent are changed. Send source as "" or null to clear it."""

    name: str | None = None
    category: str | None = None
    audience: Audience | None = None
    source: str | None = None

    @field_validator("name")
    @classmethod
    def valid_name(cls, v: str | None) -> str:
        return check_policy_name(v or "")

    @field_validator("category")
    @classmethod
    def valid_category(cls, v: str | None) -> str:
        return check_category(v or "")

    _source = field_validator("source")(check_source)


class PolicyDetailOut(PolicyOut):
    status: str
    version_count: int
    # The version the policy is known by (the active one, else the newest).
    current_version: VersionOut
    active_version_id: str | None
    # Newest first. Staff only see versions they may read (active and awaiting review).
    versions: list[VersionOut]
    archived_at: datetime | None = None
    archived_by: str | None = None
    # Configured in US-024.
    owner: str | None = None
    help_route: str | None = None


def policy_detail_out(p: Policy, staff_view: bool = False) -> PolicyDetailOut:
    active = service.active_version(p)
    versions = [
        v for v in reversed(p.versions) if not staff_view or service.staff_can_read_version(v)
    ]
    return PolicyDetailOut(
        **policy_out(p).model_dump(),
        status=service.display_status(p),
        version_count=len(p.versions),
        current_version=version_out(service.display_version(p)),
        active_version_id=str(active.id) if active else None,
        versions=[version_out(v) for v in versions],
        archived_at=p.archived_at,
        archived_by=p.archived_by.email if p.archived_by else None,
    )


@router.get("/{policy_id}")
def get_policy(policy_id: uuid.UUID, membership: MemberOf, db: DbSession) -> PolicyDetailOut:
    staff_view = membership.role != Role.ADMIN
    policy = service.get_policy(db, membership.organisation, policy_id, staff_view=staff_view)
    return policy_detail_out(policy, staff_view)


@router.patch("/{policy_id}")
def edit_policy(
    policy_id: uuid.UUID, body: PolicyEditIn, admin: AdminOf, db: DbSession
) -> PolicyDetailOut:
    policy = service.get_policy(db, admin.organisation, policy_id, staff_view=False)
    if "audience" in body.model_fields_set and body.audience is None:
        raise AppError(
            422,
            "validation_error",
            "Please check the highlighted fields.",
            {"audience": "Choose who this policy is for"},
        )
    changes = {field: getattr(body, field) for field in body.model_fields_set}
    service.edit_policy(db, policy, admin.user, changes)
    db.refresh(policy)
    return policy_detail_out(policy)


@router.get("/{policy_id}/versions/{version_id}/file")
def download_version(
    policy_id: uuid.UUID,
    version_id: uuid.UUID,
    membership: MemberOf,
    db: DbSession,
    storage: FileStorage,
) -> Response:
    policy = service.get_policy(
        db, membership.organisation, policy_id, staff_view=membership.role != Role.ADMIN
    )
    version = service.get_version(policy, version_id)
    if membership.role != Role.ADMIN and not service.staff_can_read_version(version):
        raise NotFound("This document is no longer available.")
    # The display name is already cleaned; quote it and offer an ASCII fallback.
    safe = version.original_filename.replace('"', "").encode("ascii", "replace").decode()
    return Response(
        storage.read(version.storage_key),
        media_type=version.content_type,
        headers={
            "Content-Disposition": f'attachment; filename="{safe}"',
            "X-Content-Type-Options": "nosniff",
            "Cache-Control": "private, no-store",
        },
    )


@router.post("/{policy_id}/archive")
def archive_policy(policy_id: uuid.UUID, admin: AdminOf, db: DbSession) -> PolicyDetailOut:
    policy = service.get_policy(db, admin.organisation, policy_id, staff_view=False)
    service.archive_policy(db, policy, admin.user)
    db.refresh(policy)
    return policy_detail_out(policy)


@router.post("/{policy_id}/restore")
def restore_policy(policy_id: uuid.UUID, admin: AdminOf, db: DbSession) -> PolicyDetailOut:
    policy = service.get_policy(db, admin.organisation, policy_id, staff_view=False)
    service.restore_policy(db, policy, admin.user)
    db.refresh(policy)
    return policy_detail_out(policy)


# --- Versions and approval (US-010A) ---


class RejectIn(BaseModel):
    reason: str

    @field_validator("reason")
    @classmethod
    def valid_reason(cls, v: str) -> str:
        v = " ".join((v or "").split())
        if not v:
            raise ValueError("Say why this version is being sent back")
        if len(v) > 500:
            raise ValueError("Use no more than 500 characters")
        return v


class NewVersionForm(BaseModel):
    version: str
    effective_date: date

    _version = field_validator("version")(check_version_label)
    _effective = field_validator("effective_date")(check_effective_date)


def _member_policy(membership, db, policy_id) -> Policy:
    return service.get_policy(
        db, membership.organisation, policy_id, staff_view=membership.role != Role.ADMIN
    )


def _detail(db, policy: Policy, membership) -> PolicyDetailOut:
    db.refresh(policy)
    return policy_detail_out(policy, staff_view=membership.role != Role.ADMIN)


@router.post("/{policy_id}/versions", status_code=status.HTTP_201_CREATED)
def upload_new_version(
    policy_id: uuid.UUID,
    admin: AdminOf,
    db: DbSession,
    settings: AppSettings,
    storage: FileStorage,
    runner: Runner,
    version: Annotated[str, Form()] = "",
    effective_date: Annotated[str, Form()] = "",
    file: UploadFile | None = None,
) -> PolicyDetailOut:
    try:
        form = NewVersionForm.model_validate(
            {"version": version, "effective_date": effective_date or None}
        )
    except ValidationError as exc:
        raise RequestValidationError(exc.errors()) from None
    if file is None or not file.filename:
        msg = "Choose a PDF or Word document to upload"
        raise AppError(
            422, "validation_error", "Please check the highlighted fields.", {"file": msg}
        )
    policy = service.get_policy(db, admin.organisation, policy_id, staff_view=False)
    data = file.file.read(settings.policy_max_bytes + 1)
    new_version = service.upload_new_version(
        db,
        policy,
        admin.user,
        form.version,
        form.effective_date,
        file.filename,
        data,
        settings.policy_max_bytes,
        storage,
    )
    runner.submit(new_version.id)
    return _detail(db, policy, admin)


@router.post("/{policy_id}/versions/{version_id}/mark-ready")
def mark_ready(
    policy_id: uuid.UUID, version_id: uuid.UUID, membership: MemberOf, db: DbSession
) -> PolicyDetailOut:
    policy = _member_policy(membership, db, policy_id)
    service.mark_ready(db, policy, service.get_version(policy, version_id), membership.user)
    return _detail(db, policy, membership)


@router.post("/{policy_id}/versions/{version_id}/withdraw")
def withdraw(
    policy_id: uuid.UUID, version_id: uuid.UUID, membership: MemberOf, db: DbSession
) -> PolicyDetailOut:
    policy = _member_policy(membership, db, policy_id)
    service.withdraw(
        db,
        policy,
        service.get_version(policy, version_id),
        membership.user,
        is_admin=membership.role == Role.ADMIN,
    )
    return _detail(db, policy, membership)


@router.post("/{policy_id}/versions/{version_id}/reject")
def reject(
    policy_id: uuid.UUID, version_id: uuid.UUID, body: RejectIn, admin: AdminOf, db: DbSession
) -> PolicyDetailOut:
    policy = service.get_policy(db, admin.organisation, policy_id, staff_view=False)
    service.reject(db, policy, service.get_version(policy, version_id), admin.user, body.reason)
    return _detail(db, policy, admin)


@router.post("/{policy_id}/versions/{version_id}/activate")
def activate(
    policy_id: uuid.UUID, version_id: uuid.UUID, admin: AdminOf, db: DbSession
) -> PolicyDetailOut:
    policy = service.get_policy(db, admin.organisation, policy_id, staff_view=False)
    service.activate(db, policy, service.get_version(policy, version_id), admin.user)
    return _detail(db, policy, admin)
