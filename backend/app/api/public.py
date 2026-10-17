"""Public, unauthenticated endpoints.

Responses here are built field by field from an explicit allow-list. Nothing internal (members,
owners, settings) may ever be added to these models (AC-12).
"""

from fastapi import APIRouter, Response
from pydantic import BaseModel
from sqlalchemy import select

from app.api.organisations import logo_url
from app.deps import DbSession, FileStorage
from app.errors import NotFound
from app.models import Organisation
from app.organisations.validation import text_colour_for

router = APIRouter(prefix="/public", tags=["public"])

ORG_NOT_FOUND = "We couldn't find this organisation's Policy Compass page."


class PublicOrganisationOut(BaseModel):
    name: str
    slug: str
    website: str | None
    logo_url: str | None
    primary_colour: str
    brand_text_colour: str


def _organisation(db, slug: str) -> Organisation:
    org = db.scalar(select(Organisation).where(Organisation.slug == slug.lower()))
    if org is None:
        raise NotFound(ORG_NOT_FOUND)
    return org


@router.get("/organisations/{slug}")
def public_organisation(slug: str, db: DbSession) -> PublicOrganisationOut:
    org = _organisation(db, slug)
    return PublicOrganisationOut(
        name=org.name,
        slug=org.slug,
        website=org.website,
        logo_url=logo_url(org),
        primary_colour=org.primary_colour,
        brand_text_colour=text_colour_for(org.primary_colour),
    )


@router.get("/organisations/{slug}/logo")
def public_logo(slug: str, db: DbSession, storage: FileStorage) -> Response:
    org = _organisation(db, slug)
    if not org.logo_key:
        raise NotFound("This organisation hasn't added a logo.")
    return Response(
        storage.read(org.logo_key),
        media_type=org.logo_content_type,
        headers={
            "Cache-Control": "public, max-age=86400",
            "X-Content-Type-Options": "nosniff",
            "Content-Security-Policy": "default-src 'none'",
        },
    )
