"""Policy owners and public help routes (US-024). Every change is audited."""

from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from app.audit import AuditAction, changed_fields, record
from app.errors import NotFound
from app.models import HelpRoute, Organisation, Policy, PolicyOwner, User

OWNER_FIELDS = ("name", "job_title", "email", "phone")
ROUTE_FIELDS = ("label", "route_type", "destination", "description")


def _snapshot(obj, fields) -> dict:
    return {f: (str(getattr(obj, f)) if getattr(obj, f) is not None else None) for f in fields}


def _audit(db, organisation_id, actor, action, obj, label, **kw) -> None:
    record(
        db,
        organisation_id=organisation_id,
        actor=actor,
        action=action,
        object_type="contact" if isinstance(obj, PolicyOwner) else "help_route",
        object_id=obj.id,
        object_label=label,
        **kw,
    )


# --- Policy owners ---


def list_owners(db: Session, organisation: Organisation) -> list[PolicyOwner]:
    return list(
        db.scalars(
            select(PolicyOwner)
            .where(PolicyOwner.organisation_id == organisation.id)
            .order_by(func.lower(PolicyOwner.name))
        )
    )


def get_owner(db: Session, organisation: Organisation, owner_id) -> PolicyOwner:
    owner = db.get(PolicyOwner, owner_id)
    if owner is None or owner.organisation_id != organisation.id:
        raise NotFound("This contact could not be found.")
    return owner


def create_owner(db: Session, organisation: Organisation, actor: User, data: dict) -> PolicyOwner:
    owner = PolicyOwner(organisation_id=organisation.id, **data)
    db.add(owner)
    db.flush()
    _audit(
        db,
        organisation.id,
        actor,
        AuditAction.CONTACT_CREATED,
        owner,
        owner.name,
        new=_snapshot(owner, OWNER_FIELDS),
    )
    db.commit()
    return owner


def update_owner(db: Session, owner: PolicyOwner, actor: User, data: dict) -> PolicyOwner:
    before = _snapshot(owner, OWNER_FIELDS)
    for field, value in data.items():
        setattr(owner, field, value)
    previous, new = changed_fields(before, _snapshot(owner, OWNER_FIELDS))
    if new:
        _audit(
            db,
            owner.organisation_id,
            actor,
            AuditAction.CONTACT_UPDATED,
            owner,
            owner.name,
            previous=previous,
            new=new,
        )
    db.commit()
    return owner


def delete_owner(db: Session, owner: PolicyOwner, actor: User) -> None:
    """Remove a contact. Policies they owned become "not assigned" (audited per policy)."""
    for policy in db.scalars(select(Policy).where(Policy.owner_id == owner.id)):
        _audit_assignment(db, policy, actor, AuditAction.POLICY_OWNER_CHANGED, owner.name, None)
        policy.owner_id = None
    _audit(
        db,
        owner.organisation_id,
        actor,
        AuditAction.CONTACT_DELETED,
        owner,
        owner.name,
        previous=_snapshot(owner, OWNER_FIELDS),
    )
    db.delete(owner)
    db.commit()


# --- Public help routes ---


def list_routes(db: Session, organisation: Organisation) -> list[HelpRoute]:
    return list(
        db.scalars(
            select(HelpRoute)
            .where(HelpRoute.organisation_id == organisation.id)
            .order_by(HelpRoute.is_default.desc(), func.lower(HelpRoute.label))
        )
    )


def get_route(db: Session, organisation: Organisation, route_id) -> HelpRoute:
    route = db.get(HelpRoute, route_id)
    if route is None or route.organisation_id != organisation.id:
        raise NotFound("This help route could not be found.")
    return route


def default_route(db: Session, organisation_id) -> HelpRoute | None:
    return db.scalar(
        select(HelpRoute).where(
            HelpRoute.organisation_id == organisation_id, HelpRoute.is_default.is_(True)
        )
    )


def create_route(
    db: Session, organisation: Organisation, actor: User, data: dict, make_default: bool
) -> HelpRoute:
    route = HelpRoute(organisation_id=organisation.id, **data)
    db.add(route)
    db.flush()
    _audit(
        db,
        organisation.id,
        actor,
        AuditAction.HELP_ROUTE_CREATED,
        route,
        route.label,
        new=_snapshot(route, ROUTE_FIELDS),
    )
    # The first route becomes the default automatically, so public escalation always has one.
    if make_default or default_route(db, organisation.id) is None:
        _set_default(db, route, actor)
    db.commit()
    return route


def update_route(db: Session, route: HelpRoute, actor: User, data: dict) -> HelpRoute:
    before = _snapshot(route, ROUTE_FIELDS)
    for field, value in data.items():
        setattr(route, field, value)
    previous, new = changed_fields(before, _snapshot(route, ROUTE_FIELDS))
    if new:
        _audit(
            db,
            route.organisation_id,
            actor,
            AuditAction.HELP_ROUTE_UPDATED,
            route,
            route.label,
            previous=previous,
            new=new,
        )
    db.commit()
    return route


def _set_default(db: Session, route: HelpRoute, actor: User) -> None:
    current = default_route(db, route.organisation_id)
    if current is not None and current.id == route.id:
        return
    db.execute(
        update(HelpRoute)
        .where(HelpRoute.organisation_id == route.organisation_id)
        .values(is_default=False)
    )
    db.flush()
    route.is_default = True
    _audit(
        db,
        route.organisation_id,
        actor,
        AuditAction.DEFAULT_HELP_ROUTE_CHANGED,
        route,
        route.label,
        previous={"default": current.label if current else None},
        new={"default": route.label},
    )


def make_default(db: Session, route: HelpRoute, actor: User) -> HelpRoute:
    _set_default(db, route, actor)
    db.commit()
    return route


def delete_route(db: Session, route: HelpRoute, actor: User) -> None:
    for policy in db.scalars(select(Policy).where(Policy.help_route_id == route.id)):
        _audit_assignment(
            db, policy, actor, AuditAction.PUBLIC_HELP_ROUTE_CHANGED, route.label, None
        )
        policy.help_route_id = None
    _audit(
        db,
        route.organisation_id,
        actor,
        AuditAction.HELP_ROUTE_DELETED,
        route,
        route.label,
        previous=_snapshot(route, ROUTE_FIELDS),
    )
    db.delete(route)
    db.commit()


# --- Usage and assignment ---


def usage_counts(db: Session, organisation: Organisation, column) -> dict:
    rows = db.execute(
        select(column, func.count())
        .where(Policy.organisation_id == organisation.id, column.is_not(None))
        .group_by(column)
    )
    return {str(k): n for k, n in rows}


def _audit_assignment(db, policy: Policy, actor, action, before: str | None, after: str | None):
    record(
        db,
        organisation_id=policy.organisation_id,
        actor=actor,
        action=action,
        object_type="policy",
        object_id=policy.id,
        object_label=policy.name,
        previous={"contact": before},
        new={"contact": after},
    )
