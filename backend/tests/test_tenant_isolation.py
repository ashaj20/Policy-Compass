"""US-036 / AC-11: one organisation can never access another organisation's data.

This sweep discovers every organisation-scoped route from the app itself, so endpoints added
later are covered automatically. An administrator of Organisation B ("Mark") calls each route:
  1. with Organisation A's ID in the URL, and
  2. with Organisation B's own ID but Organisation A's object IDs (policy, version, contact...).
Every call must be refused, none of Organisation A's data may change, and no response may
contain anything identifying Organisation A's data.
"""

import re
import uuid

import pytest
from sqlalchemy import select, update

from app.models import (
    AnswerFeedback,
    AuditEvent,
    DocumentChunk,
    HelpRoute,
    Invitation,
    KnowledgeGap,
    Membership,
    Organisation,
    Policy,
    PolicyOwner,
    PolicyVersion,
    Question,
    Role,
    User,
    VersionStatus,
)
from tests.files import PDF_BYTES

# Distinctive strings planted in Organisation A's data; none may ever appear in Mark's responses.
SECRETS = [
    "Riverside Housing",
    "riverside-housing",
    "Secret Repairs Policy",
    "Jane Smith",
    "jane.smith@example.org",
    "Riverside Helpdesk",
    "repairs@riverside.example",
    "john@example.org",
    "invitee@example.org",
    "Secret question about boiler budgets",
]


@pytest.fixture
def world(make_client, db):
    jane = make_client("jane@example.org")
    org_a = jane.post(
        "/api/organisations", json={"name": "Riverside Housing", "slug": "riverside-housing"}
    ).json()["id"]
    base = f"/api/organisations/{org_a}"
    owner = jane.post(
        f"{base}/policy-owners", json={"name": "Jane Smith", "email": "jane.smith@example.org"}
    ).json()["id"]
    route = jane.post(
        f"{base}/help-routes",
        json={
            "label": "Riverside Helpdesk",
            "route_type": "EMAIL",
            "destination": "repairs@riverside.example",
        },
    ).json()["id"]
    upload = jane.post(
        f"{base}/policies",
        data={
            "name": "Secret Repairs Policy",
            "version": "1.0",
            "effective_date": "2026-09-01",
            "audience": "BOTH",
            "category": "Repairs",
            "owner_id": owner,
            "help_route_id": route,
        },
        files={"file": ("p.pdf", PDF_BYTES, "application/pdf")},
    ).json()
    policy, version = upload["id"], upload["latest_version"]["id"]
    db.execute(
        update(PolicyVersion).where(PolicyVersion.id == version).values(status=VersionStatus.DRAFT)
    )
    db.expire_all()
    make_client("john@example.org")
    john = db.scalar(select(User).where(User.email == "john@example.org"))
    member = Membership(organisation_id=org_a, user_id=john.id, role=Role.STAFF)
    db.add(member)
    db.flush()
    invitation = jane.post(f"{base}/invitations", json={"email": "invitee@example.org"}).json()[
        "id"
    ]
    audit_event = jane.get(f"{base}/audit-events").json()["events"][0]["id"]
    question = jane.post(
        f"{base}/questions", json={"question": "Secret question about boiler budgets?"}
    ).json()["id"]

    mark = make_client("mark@example.org")
    gap = jane.post(f"{base}/knowledge-gaps", json={"question_id": question}).json()["id"]
    org_b = mark.post("/api/organisations", json={"name": "Other Org", "slug": "other-org"}).json()[
        "id"
    ]
    ids_a = {
        "organisation_id": org_a,
        "policy_id": policy,
        "version_id": version,
        "owner_id": owner,
        "route_id": route,
        "membership_id": str(member.id),
        "invitation_id": invitation,
        "before": audit_event,
        "question_id": question,
        "gap_id": gap,
    }
    return {"mark": mark, "org_a": org_a, "org_b": org_b, "ids": ids_a}


def org_routes(app):
    """Every organisation-scoped (method, path), from the app's own API schema."""
    routes = []
    for path, operations in app.openapi()["paths"].items():
        if "{organisation_id}" in path:
            for method in operations:
                routes.append((method.upper(), path))
    return sorted(routes)


def fill(path: str, values: dict) -> str:
    def sub(m):
        name = m.group(1)
        if name not in values:
            raise AssertionError(f"Tenant sweep doesn't know how to fill {{{name}}} in {path}")
        return values[name]

    return re.sub(r"\{(\w+)\}", sub, path)


def snapshot(db, org_id) -> dict:
    """Everything belonging to Organisation A that an attacker might try to change."""
    db.expire_all()
    org = db.get(Organisation, org_id)
    return {
        "org": (org.name, org.slug, org.website, org.logo_key, org.primary_colour),
        "policies": sorted(
            (p.name, p.category, p.audience, str(p.owner_id), str(p.help_route_id), p.archived_at)
            for p in db.scalars(select(Policy).where(Policy.organisation_id == org_id))
        ),
        "versions": sorted(
            (v.version_label, v.status)
            for v in db.scalars(
                select(PolicyVersion).where(PolicyVersion.organisation_id == org_id)
            )
        ),
        "owners": sorted(
            (o.name, o.email)
            for o in db.scalars(select(PolicyOwner).where(PolicyOwner.organisation_id == org_id))
        ),
        "routes": sorted(
            (r.label, r.destination, r.is_default)
            for r in db.scalars(select(HelpRoute).where(HelpRoute.organisation_id == org_id))
        ),
        "members": sorted(
            (str(m.user_id), m.role)
            for m in db.scalars(select(Membership).where(Membership.organisation_id == org_id))
        ),
        "invitations": sorted(
            (i.email, i.revoked_at is None)
            for i in db.scalars(select(Invitation).where(Invitation.organisation_id == org_id))
        ),
        "audit": len(
            list(db.scalars(select(AuditEvent.id).where(AuditEvent.organisation_id == org_id)))
        ),
        "questions": sorted(
            (q.question, q.status)
            for q in db.scalars(select(Question).where(Question.organisation_id == org_id))
        ),
        "feedback": sorted(
            (str(f.question_id), f.helpful, f.reason)
            for f in db.scalars(
                select(AnswerFeedback).where(AnswerFeedback.organisation_id == org_id)
            )
        ),
        "gaps": sorted(
            (g.question, g.status, g.notes or "")
            for g in db.scalars(select(KnowledgeGap).where(KnowledgeGap.organisation_id == org_id))
        ),
        "chunks": len(
            list(
                db.scalars(select(DocumentChunk.id).where(DocumentChunk.organisation_id == org_id))
            )
        ),
    }


def call(client, method, url):
    if method in ("POST", "PUT", "PATCH"):
        # A plausible body so requests reach the access checks rather than stopping at shape.
        return client.request(
            method,
            url,
            json={
                "name": "Hijacked",
                "email": "x@example.org",
                "role": "ADMIN",
                "slug": "hijacked-slug",
                "label": "Hijacked",
                "route_type": "EMAIL",
                "destination": "x@example.org",
                "reason": "hijack",
                "audience": "PUBLIC",
                "helpful": False,
            },
        )
    return client.request(method, url)


def assert_refused_without_leaks(resp, method, url):
    assert resp.status_code in (403, 404, 409, 422), f"{method} {url} -> {resp.status_code}"
    body = resp.text
    for secret in SECRETS:
        assert secret not in body, f"{method} {url} leaked {secret!r}"


def test_the_sweep_covers_every_organisation_route(app):
    routes = org_routes(app)
    # A floor that only goes up: if routes are removed this will flag it for review.
    assert len(routes) >= 35, routes


def test_other_organisation_ids_in_the_url_are_always_refused(world, app, db):
    mark, ids = world["mark"], world["ids"]
    before = snapshot(db, world["org_a"])
    for method, path in org_routes(app):
        url = fill(path, ids)
        resp = call(mark, method, url)
        # The organisation itself isn't Mark's, so every route must answer "not found".
        assert resp.status_code == 404, f"{method} {url} -> {resp.status_code} {resp.text[:200]}"
        assert_refused_without_leaks(resp, method, url)
    assert snapshot(db, world["org_a"]) == before


def test_other_organisation_object_ids_through_own_url_are_always_refused(world, app, db):
    mark, ids = world["mark"], world["ids"]
    own = dict(ids, organisation_id=world["org_b"])
    before = snapshot(db, world["org_a"])
    for method, path in org_routes(app):
        if not re.search(r"\{(?!organisation_id)\w+\}", path):
            continue  # routes with no object IDs only ever touch Mark's own organisation
        url = fill(path, own)
        resp = call(mark, method, url)
        assert_refused_without_leaks(resp, method, url)
    assert snapshot(db, world["org_a"]) == before


def test_own_organisation_lists_never_include_another_organisations_data(world, app):
    mark, org_b = world["mark"], world["org_b"]
    for method, path in org_routes(app):
        if method != "GET" or re.search(r"\{(?!organisation_id)\w+\}", path):
            continue
        url = fill(path, {"organisation_id": org_b})
        resp = mark.get(url)
        assert resp.status_code == 200, f"GET {url} -> {resp.status_code}"
        for secret in SECRETS:
            assert secret not in resp.text, f"GET {url} leaked {secret!r}"


def test_random_ids_are_indistinguishable_from_other_tenants_ids(world):
    """Probing can't tell "exists in another organisation" from "doesn't exist"."""
    mark, ids = world["mark"], world["ids"]
    real = mark.get(f"/api/organisations/{ids['organisation_id']}")
    fake = mark.get(f"/api/organisations/{uuid.uuid4()}")
    assert real.status_code == fake.status_code == 404
    assert real.json() == fake.json()
