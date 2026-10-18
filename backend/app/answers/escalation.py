"""Where to send someone when we can't answer (US-017). We never invent a contact route.

- Staff (INTERNAL) are pointed to the policy owner of the most relevant policy that has one.
- The public are pointed to the most relevant policy's help route, else the organisation's
  default help route. Policy owners are internal-only and are never used here (REVIEW C4).
- If nothing is configured, there is no contact and the caller shows the generic message.

Contacts are looked up when the response is built, never cached, so edits take effect at once.
"""

import uuid
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import HelpRoute, Policy, PolicyOwner
from app.policies.audience import Requester


@dataclass(frozen=True)
class OwnerContact:
    name: str
    job_title: str | None
    email: str | None
    phone: str | None
    policy_name: str


@dataclass(frozen=True)
class HelpContact:
    label: str
    route_type: str
    destination: str
    description: str | None


def _related_policies(
    db: Session, organisation_id: uuid.UUID, policy_ids: list[str]
) -> list[Policy]:
    """The given policies of this organisation, kept in the given (most relevant first) order."""
    ids = [uuid.UUID(p) for p in policy_ids]
    if not ids:
        return []
    found = {
        p.id: p
        for p in db.scalars(
            select(Policy).where(
                Policy.organisation_id == organisation_id,
                Policy.id.in_(ids),
                Policy.archived_at.is_(None),
            )
        )
    }
    return [found[i] for i in ids if i in found]


def find_owner(
    db: Session, organisation_id: uuid.UUID, policy_ids: list[str]
) -> OwnerContact | None:
    for policy in _related_policies(db, organisation_id, policy_ids):
        owner: PolicyOwner | None = policy.owner
        if owner is not None and owner.organisation_id == organisation_id:
            return OwnerContact(owner.name, owner.job_title, owner.email, owner.phone, policy.name)
    return None


def find_help_route(
    db: Session, organisation_id: uuid.UUID, policy_ids: list[str]
) -> HelpContact | None:
    route: HelpRoute | None = None
    for policy in _related_policies(db, organisation_id, policy_ids):
        if policy.help_route is not None and policy.help_route.organisation_id == organisation_id:
            route = policy.help_route
            break
    if route is None:
        route = db.scalar(
            select(HelpRoute).where(
                HelpRoute.organisation_id == organisation_id, HelpRoute.is_default.is_(True)
            )
        )
    if route is None:
        return None
    return HelpContact(route.label, route.route_type, route.destination, route.description)


def find_escalation(
    db: Session, organisation_id: uuid.UUID, requester: Requester, policy_ids: list[str]
) -> OwnerContact | HelpContact | None:
    if requester == Requester.INTERNAL:
        return find_owner(db, organisation_id, policy_ids)
    return find_help_route(db, organisation_id, policy_ids)
