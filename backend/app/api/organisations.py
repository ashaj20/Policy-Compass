"""Organisation endpoints for signed-in users (US-002)."""

from fastapi import APIRouter, UploadFile, status
from pydantic import BaseModel, field_validator

from app.deps import AdminOf, AppSettings, CurrentUser, DbSession, FileStorage, MemberOf
from app.models import Membership, Organisation
from app.organisations import service
from app.organisations.validation import (
    check_colour,
    check_name,
    check_slug,
    check_website,
    meets_contrast,
    text_colour_for,
)

router = APIRouter(prefix="/organisations", tags=["organisations"])


class OrganisationIn(BaseModel):
    name: str
    slug: str
    website: str | None = None

    _name = field_validator("name")(check_name)
    _slug = field_validator("slug")(check_slug)
    _website = field_validator("website")(check_website)


class OrganisationUpdateIn(BaseModel):
    """Only the fields sent are changed. Send website as "" or null to clear it."""

    name: str | None = None
    website: str | None = None
    primary_colour: str | None = None

    @field_validator("name")
    @classmethod
    def valid_name(cls, v: str | None) -> str:
        return check_name(v or "")

    @field_validator("primary_colour")
    @classmethod
    def valid_colour(cls, v: str | None) -> str:
        return check_colour(v or "")

    _website = field_validator("website")(check_website)


class SlugIn(BaseModel):
    slug: str

    _slug = field_validator("slug")(check_slug)


class OrganisationOut(BaseModel):
    id: str
    name: str
    slug: str
    website: str | None
    logo_url: str | None
    primary_colour: str
    # Text colour that reads best on the primary colour, and whether it meets WCAG AA.
    brand_text_colour: str
    colour_meets_contrast: bool
    role: str


class SlugCheckOut(BaseModel):
    available: bool
    message: str | None


def logo_url(organisation: Organisation) -> str | None:
    if not organisation.logo_key:
        return None
    # The version changes whenever a new logo is uploaded, so browsers don't show a stale one.
    version = organisation.logo_key.rsplit("/", 1)[-1].split(".")[0][:12]
    return f"/api/public/organisations/{organisation.slug}/logo?v={version}"


def organisation_out(membership: Membership) -> OrganisationOut:
    org = membership.organisation
    return OrganisationOut(
        id=str(org.id),
        name=org.name,
        slug=org.slug,
        website=org.website,
        logo_url=logo_url(org),
        primary_colour=org.primary_colour,
        brand_text_colour=text_colour_for(org.primary_colour),
        colour_meets_contrast=meets_contrast(org.primary_colour),
        role=membership.role,
    )


@router.get("/slug-available")
def slug_available(slug: str, db: DbSession, _: CurrentUser) -> SlugCheckOut:
    available, message = service.slug_available(db, slug)
    return SlugCheckOut(available=available, message=message)


@router.post("", status_code=status.HTTP_201_CREATED)
def create_organisation(body: OrganisationIn, db: DbSession, user: CurrentUser) -> OrganisationOut:
    membership = service.create_organisation(db, user, body.name, body.slug, body.website)
    return organisation_out(membership)


@router.get("/{organisation_id}")
def get_organisation(membership: MemberOf) -> OrganisationOut:
    return organisation_out(membership)


@router.patch("/{organisation_id}")
def update_organisation(
    body: OrganisationUpdateIn, membership: AdminOf, db: DbSession
) -> OrganisationOut:
    changes = {field: getattr(body, field) for field in body.model_fields_set}
    service.update_organisation(db, membership.organisation, membership.user, changes)
    return organisation_out(membership)


@router.put("/{organisation_id}/slug")
def change_slug(body: SlugIn, membership: AdminOf, db: DbSession) -> OrganisationOut:
    service.change_slug(db, membership.organisation, membership.user, body.slug)
    return organisation_out(membership)


@router.put("/{organisation_id}/logo")
def upload_logo(
    file: UploadFile,
    membership: AdminOf,
    db: DbSession,
    settings: AppSettings,
    storage: FileStorage,
) -> OrganisationOut:
    # Read one byte past the limit so oversized files are detected without loading them fully.
    data = file.file.read(settings.logo_max_bytes + 1)
    service.set_logo(
        db, membership.organisation, membership.user, data, settings.logo_max_bytes, storage
    )
    return organisation_out(membership)


@router.delete("/{organisation_id}/logo")
def remove_logo(membership: AdminOf, db: DbSession, storage: FileStorage) -> OrganisationOut:
    service.remove_logo(db, membership.organisation, membership.user, storage)
    return organisation_out(membership)
