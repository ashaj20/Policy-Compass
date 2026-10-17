"""Organisation creation, slugs and logos (US-002)."""

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.errors import AppError
from app.models import Membership, Organisation, Role, User
from app.organisations.validation import check_slug, detect_logo_type
from app.storage import Storage

SLUG_TAKEN = "This URL is already taken. Please choose another"


def memberships_for(db: Session, user: User) -> list[Membership]:
    return list(
        db.scalars(
            select(Membership).where(Membership.user_id == user.id).order_by(Membership.created_at)
        )
    )


def slug_available(db: Session, slug: str) -> tuple[bool, str | None]:
    try:
        slug = check_slug(slug)
    except ValueError as exc:
        return False, str(exc)
    if db.scalar(select(Organisation.id).where(Organisation.slug == slug)):
        return False, SLUG_TAKEN
    return True, None


def create_organisation(
    db: Session, user: User, name: str, slug: str, website: str | None
) -> Membership:
    # Beta: one organisation per person, which keeps tenant context unambiguous.
    if memberships_for(db, user):
        raise AppError(409, "already_member", "You already belong to an organisation.")
    if db.scalar(select(Organisation.id).where(Organisation.slug == slug)):
        raise AppError(409, "slug_taken", SLUG_TAKEN, {"slug": SLUG_TAKEN})

    organisation = Organisation(name=name, slug=slug, website=website)
    membership = Membership(organisation=organisation, user_id=user.id, role=Role.ADMIN)
    db.add_all([organisation, membership])
    try:
        db.commit()
    except IntegrityError:
        # Someone else claimed the slug between the check and the insert.
        db.rollback()
        raise AppError(409, "slug_taken", SLUG_TAKEN, {"slug": SLUG_TAKEN}) from None
    return membership


def set_logo(
    db: Session, organisation: Organisation, data: bytes, max_bytes: int, storage: Storage
) -> None:
    if not data:
        raise AppError(422, "invalid_logo", "Choose an image file to upload.")
    if len(data) > max_bytes:
        raise AppError(
            413, "logo_too_large", f"The logo must be {max_bytes // (1024 * 1024)} MB or smaller."
        )
    detected = detect_logo_type(data)
    if detected is None:
        raise AppError(422, "invalid_logo", "The logo must be a PNG, JPEG or WebP image.")
    content_type, extension = detected

    old_key = organisation.logo_key
    organisation.logo_key = storage.save(f"logos/{organisation.id}", data, extension)
    organisation.logo_content_type = content_type
    db.commit()
    if old_key:
        storage.delete(old_key)


EDITABLE_FIELDS = {"name", "website"}


def update_organisation(db: Session, organisation: Organisation, changes: dict) -> None:
    """Apply already-validated changes to the organisation's basic details (US-004)."""
    for field, value in changes.items():
        if field in EDITABLE_FIELDS:
            setattr(organisation, field, value)
    db.commit()


def remove_logo(db: Session, organisation: Organisation, storage: Storage) -> None:
    old_key = organisation.logo_key
    organisation.logo_key = None
    organisation.logo_content_type = None
    db.commit()
    if old_key:
        storage.delete(old_key)


def change_slug(db: Session, organisation: Organisation, slug: str) -> None:
    """Change the public URL (US-005). The old URL stops working immediately."""
    if slug == organisation.slug:
        return
    taken = db.scalar(
        select(Organisation.id).where(Organisation.slug == slug, Organisation.id != organisation.id)
    )
    if taken:
        raise AppError(409, "slug_taken", SLUG_TAKEN, {"slug": SLUG_TAKEN})
    organisation.slug = slug
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise AppError(409, "slug_taken", SLUG_TAKEN, {"slug": SLUG_TAKEN}) from None
