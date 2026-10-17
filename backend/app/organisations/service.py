"""Organisation creation, settings, slugs and logos (US-002, US-004, US-005).

Every change records an audit event in the same transaction (US-005A).
"""

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.audit import AuditAction, changed_fields, record
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


def _audit_org(db: Session, organisation: Organisation, actor: User, action: AuditAction, **kw):
    record(
        db,
        organisation_id=organisation.id,
        actor=actor,
        action=action,
        object_type="organisation",
        object_id=organisation.id,
        object_label=organisation.name,
        **kw,
    )


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
        db.flush()
        _audit_org(
            db,
            organisation,
            user,
            AuditAction.ORGANISATION_CREATED,
            new={"name": name, "slug": slug, "website": website},
        )
        db.commit()
    except IntegrityError:
        # Someone else claimed the slug between the check and the insert.
        db.rollback()
        raise AppError(409, "slug_taken", SLUG_TAKEN, {"slug": SLUG_TAKEN}) from None
    return membership


def set_logo(
    db: Session,
    organisation: Organisation,
    actor: User,
    data: bytes,
    max_bytes: int,
    storage: Storage,
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
    _audit_org(
        db,
        organisation,
        actor,
        AuditAction.LOGO_UPDATED,
        previous={"logo": "Logo set" if old_key else "No logo"},
        new={"logo": "New logo uploaded"},
    )
    db.commit()
    if old_key:
        storage.delete(old_key)


EDITABLE_FIELDS = ("name", "website", "primary_colour")


def update_organisation(
    db: Session, organisation: Organisation, actor: User, changes: dict
) -> None:
    """Apply already-validated changes to the organisation's basic details (US-004)."""
    before = {f: getattr(organisation, f) for f in EDITABLE_FIELDS}
    for field, value in changes.items():
        if field in EDITABLE_FIELDS:
            setattr(organisation, field, value)
    after = {f: getattr(organisation, f) for f in EDITABLE_FIELDS}
    previous, new = changed_fields(before, after)
    if new:
        _audit_org(
            db,
            organisation,
            actor,
            AuditAction.ORGANISATION_SETTINGS_CHANGED,
            previous=previous,
            new=new,
        )
    db.commit()


def remove_logo(db: Session, organisation: Organisation, actor: User, storage: Storage) -> None:
    old_key = organisation.logo_key
    if old_key is None:
        return
    organisation.logo_key = None
    organisation.logo_content_type = None
    _audit_org(
        db,
        organisation,
        actor,
        AuditAction.LOGO_REMOVED,
        previous={"logo": "Logo set"},
        new={"logo": "No logo"},
    )
    db.commit()
    storage.delete(old_key)


def change_slug(db: Session, organisation: Organisation, actor: User, slug: str) -> None:
    """Change the public URL (US-005). The old URL stops working immediately."""
    if slug == organisation.slug:
        return
    taken = db.scalar(
        select(Organisation.id).where(Organisation.slug == slug, Organisation.id != organisation.id)
    )
    if taken:
        raise AppError(409, "slug_taken", SLUG_TAKEN, {"slug": SLUG_TAKEN})
    previous = organisation.slug
    organisation.slug = slug
    _audit_org(
        db,
        organisation,
        actor,
        AuditAction.PUBLIC_URL_CHANGED,
        previous={"slug": previous},
        new={"slug": slug},
    )
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise AppError(409, "slug_taken", SLUG_TAKEN, {"slug": SLUG_TAKEN}) from None
