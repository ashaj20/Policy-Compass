"""Contacts (US-024): internal policy owners and public help routes.

Members can see them (staff need escalation details); only administrators can change them.
These endpoints are internal: policy owners are never exposed by any public endpoint.
"""

import uuid

from fastapi import APIRouter, status
from pydantic import BaseModel, ValidationInfo, field_validator

from app.contacts import service
from app.contacts.validation import check_destination, check_email, check_phone, check_text
from app.deps import AdminOf, DbSession, MemberOf
from app.models import HelpRoute, Policy, PolicyOwner, RouteType

router = APIRouter(prefix="/organisations/{organisation_id}", tags=["contacts"])


class OwnerIn(BaseModel):
    name: str
    job_title: str | None = None
    email: str | None = None
    phone: str | None = None

    @field_validator("name")
    @classmethod
    def valid_name(cls, v: str) -> str:
        return check_text(v, "the contact's name", 120, required=True)

    @field_validator("job_title")
    @classmethod
    def valid_title(cls, v: str | None) -> str | None:
        return check_text(v, "a job title", 120, required=False)

    _email = field_validator("email")(check_email)

    @field_validator("phone")
    @classmethod
    def valid_phone(cls, v: str | None, info: ValidationInfo) -> str | None:
        phone = check_phone(v)
        # A contact is only useful if staff can reach them. (If the email itself was invalid it
        # is missing from info.data and already has its own error.)
        if not phone and "email" in info.data and not info.data["email"]:
            raise ValueError("Enter an email address or phone number")
        return phone


class OwnerOut(BaseModel):
    id: str
    name: str
    job_title: str | None
    email: str | None
    phone: str | None
    policy_count: int = 0


class RouteIn(BaseModel):
    label: str
    route_type: RouteType
    destination: str
    description: str | None = None
    is_default: bool = False

    @field_validator("label")
    @classmethod
    def valid_label(cls, v: str) -> str:
        return check_text(v, "a label, for example Repairs Helpdesk", 120, required=True)

    @field_validator("destination")
    @classmethod
    def valid_destination(cls, v: str, info: ValidationInfo) -> str:
        route_type = info.data.get("route_type")
        if route_type is None:
            return v  # the type error is reported on its own field
        return check_destination(route_type, v)

    @field_validator("description")
    @classmethod
    def valid_description(cls, v: str | None) -> str | None:
        return check_text(v, "a description", 300, required=False)


class RouteOut(BaseModel):
    id: str
    label: str
    route_type: RouteType
    destination: str
    description: str | None
    is_default: bool
    policy_count: int = 0


class ContactsOut(BaseModel):
    owners: list[OwnerOut]
    help_routes: list[RouteOut]


def owner_out(o: PolicyOwner, count: int = 0) -> OwnerOut:
    return OwnerOut(
        id=str(o.id),
        name=o.name,
        job_title=o.job_title,
        email=o.email,
        phone=o.phone,
        policy_count=count,
    )


def route_out(r: HelpRoute, count: int = 0) -> RouteOut:
    return RouteOut(
        id=str(r.id),
        label=r.label,
        route_type=r.route_type,
        destination=r.destination,
        description=r.description,
        is_default=r.is_default,
        policy_count=count,
    )


@router.get("/contacts")
def list_contacts(membership: MemberOf, db: DbSession) -> ContactsOut:
    org = membership.organisation
    owner_counts = service.usage_counts(db, org, Policy.owner_id)
    route_counts = service.usage_counts(db, org, Policy.help_route_id)
    return ContactsOut(
        owners=[owner_out(o, owner_counts.get(str(o.id), 0)) for o in service.list_owners(db, org)],
        help_routes=[
            route_out(r, route_counts.get(str(r.id), 0)) for r in service.list_routes(db, org)
        ],
    )


@router.post("/policy-owners", status_code=status.HTTP_201_CREATED)
def create_owner(body: OwnerIn, admin: AdminOf, db: DbSession) -> OwnerOut:
    return owner_out(service.create_owner(db, admin.organisation, admin.user, body.model_dump()))


@router.put("/policy-owners/{owner_id}")
def update_owner(owner_id: uuid.UUID, body: OwnerIn, admin: AdminOf, db: DbSession) -> OwnerOut:
    owner = service.get_owner(db, admin.organisation, owner_id)
    return owner_out(service.update_owner(db, owner, admin.user, body.model_dump()))


@router.delete("/policy-owners/{owner_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_owner(owner_id: uuid.UUID, admin: AdminOf, db: DbSession) -> None:
    service.delete_owner(db, service.get_owner(db, admin.organisation, owner_id), admin.user)


@router.post("/help-routes", status_code=status.HTTP_201_CREATED)
def create_route(body: RouteIn, admin: AdminOf, db: DbSession) -> RouteOut:
    data = body.model_dump(exclude={"is_default"})
    return route_out(
        service.create_route(db, admin.organisation, admin.user, data, body.is_default)
    )


@router.put("/help-routes/{route_id}")
def update_route(route_id: uuid.UUID, body: RouteIn, admin: AdminOf, db: DbSession) -> RouteOut:
    route = service.get_route(db, admin.organisation, route_id)
    route = service.update_route(db, route, admin.user, body.model_dump(exclude={"is_default"}))
    if body.is_default:
        route = service.make_default(db, route, admin.user)
    return route_out(route)


@router.post("/help-routes/{route_id}/default")
def make_default(route_id: uuid.UUID, admin: AdminOf, db: DbSession) -> RouteOut:
    route = service.get_route(db, admin.organisation, route_id)
    return route_out(service.make_default(db, route, admin.user))


@router.delete("/help-routes/{route_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_route(route_id: uuid.UUID, admin: AdminOf, db: DbSession) -> None:
    service.delete_route(db, service.get_route(db, admin.organisation, route_id), admin.user)
