"""Policy endpoints (US-006). Uploading is for administrators only."""

from datetime import date, datetime
from typing import Annotated

from fastapi import APIRouter, Form, UploadFile, status
from fastapi.exceptions import RequestValidationError
from pydantic import BaseModel, ValidationError, field_validator

from app.deps import AdminOf, AppSettings, DbSession, FileStorage
from app.errors import AppError
from app.models import Audience, Policy, PolicyVersion
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


class PolicyOut(BaseModel):
    id: str
    name: str
    category: str
    audience: Audience
    source: str | None
    created_at: datetime
    updated_at: datetime
    latest_version: VersionOut


def version_out(v: PolicyVersion) -> VersionOut:
    return VersionOut(
        id=str(v.id),
        version=v.version_label,
        effective_date=v.effective_date,
        status=v.status,
        original_filename=v.original_filename,
        file_size=v.file_size,
        uploaded_at=v.uploaded_at,
        uploaded_by=v.uploaded_by.email if v.uploaded_by else None,
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


@router.post("", status_code=status.HTTP_201_CREATED)
def upload_policy(
    admin: AdminOf,
    db: DbSession,
    settings: AppSettings,
    storage: FileStorage,
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
    return policy_out(policy)


@router.get("/categories")
def list_categories(admin: AdminOf, db: DbSession) -> list[str]:
    """Categories already in use, to suggest when uploading."""
    return service.categories(db, admin.organisation)
