"""US-013: retrieval only returns permitted, active, non-archived evidence from one organisation."""

import pytest
from sqlalchemy import update

from app.models import PolicyVersion, VersionStatus
from app.policies.audience import Requester
from app.rag.embeddings import HashingEmbedder
from app.rag.retrieval import retrieve
from tests.files import docx_with_sections

EMBEDDER = HashingEmbedder()


@pytest.fixture
def org(make_client, process_inline):
    jane = make_client("jane@example.org")
    resp = jane.post(
        "/api/organisations", json={"name": "Riverside Housing", "slug": "riverside-housing"}
    )
    return jane, resp.json()["id"]


def add_policy(client, org_id, name, audience, sections, activate=True, version="1.0"):
    """Upload, process (inline), and optionally mark ready and approve a policy."""
    resp = client.post(
        f"/api/organisations/{org_id}/policies",
        data={
            "name": name,
            "version": version,
            "effective_date": "2026-09-01",
            "audience": audience,
            "category": "Test",
        },
        files={"file": (f"{name}.docx", docx_with_sections(sections), "application/octet-stream")},
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    policy_id, version_id = body["id"], body["latest_version"]["id"]
    assert body["latest_version"]["status"] == "DRAFT"
    if activate:
        approve(client, org_id, policy_id, version_id)
    return policy_id, version_id


def approve(client, org_id, policy_id, version_id):
    base = f"/api/organisations/{org_id}/policies/{policy_id}/versions/{version_id}"
    assert client.post(f"{base}/mark-ready").status_code == 200
    assert client.post(f"{base}/activate").status_code == 200


def ask(db, org_id, question, requester=Requester.INTERNAL, limit=6):
    return retrieve(
        db,
        organisation_id=org_id,
        requester=requester,
        question=question,
        embedder=EMBEDDER,
        limit=limit,
    )


REPAIRS = {
    "Emergency repairs": [
        "Emergency repairs such as gas leaks or flooding are attended within 24 hours."
    ],
    "Routine repairs": ["Routine repairs are completed within 28 calendar days."],
}


def test_returns_the_most_relevant_passage_with_citation_details(org, db):
    jane, org_id = org
    policy_id, version_id = add_policy(jane, org_id, "Repairs Policy", "INTERNAL", REPAIRS)
    results = ask(db, org_id, "How quickly are emergency repairs like flooding attended?")
    top = results[0]
    assert top.policy_name == "Repairs Policy"
    assert top.section == "Emergency repairs"
    assert str(top.version_id) == version_id and top.version_label == "1.0"
    assert top.effective_date.isoformat() == "2026-09-01"
    assert "24 hours" in top.text
    assert top.score > results[-1].score or len(results) == 1


def test_only_the_active_version_is_used(org, db):
    jane, org_id = org
    policy_id, v1 = add_policy(jane, org_id, "Repairs Policy", "INTERNAL", REPAIRS)
    # A newer version is uploaded and processed, but not yet approved.
    resp = jane.post(
        f"/api/organisations/{org_id}/policies/{policy_id}/versions",
        data={"version": "2.0", "effective_date": "2026-10-01"},
        files={
            "file": (
                "v2.docx",
                docx_with_sections(
                    {
                        "Emergency repairs": [
                            "Emergency repairs are now attended within four hours, day or night."
                        ]
                    }
                ),
                "application/octet-stream",
            )
        },
    )
    v2 = resp.json()["versions"][0]["id"]
    texts = [p.text for p in ask(db, org_id, "emergency repairs attended hours")]
    assert any("within 24 hours" in t for t in texts)
    assert not any("within four hours" in t for t in texts)

    approve(jane, org_id, policy_id, v2)
    results = ask(db, org_id, "emergency repairs attended hours")
    assert {str(p.version_id) for p in results} == {v2}  # superseded v1 is never used
    assert any("within four hours" in p.text for p in results)


@pytest.mark.parametrize(
    "status",
    [VersionStatus.DRAFT, VersionStatus.READY, VersionStatus.FAILED, VersionStatus.SUPERSEDED],
)
def test_versions_that_are_not_active_are_never_used(org, db, status):
    jane, org_id = org
    _, version_id = add_policy(jane, org_id, "Repairs Policy", "INTERNAL", REPAIRS, activate=False)
    db.execute(update(PolicyVersion).where(PolicyVersion.id == version_id).values(status=status))
    assert ask(db, org_id, "emergency repairs") == []


def test_archived_policies_are_never_used(org, db):
    jane, org_id = org
    policy_id, _ = add_policy(jane, org_id, "Repairs Policy", "INTERNAL", REPAIRS)
    assert ask(db, org_id, "emergency repairs")
    jane.post(f"/api/organisations/{org_id}/policies/{policy_id}/archive")
    db.expire_all()
    assert ask(db, org_id, "emergency repairs") == []
    jane.post(f"/api/organisations/{org_id}/policies/{policy_id}/restore")
    db.expire_all()
    assert ask(db, org_id, "emergency repairs")


def test_public_requests_never_retrieve_internal_content(org, db):
    jane, org_id = org
    add_policy(
        jane,
        org_id,
        "Internal Policy A",
        "INTERNAL",
        {"Repairs escalation": ["Internal manager for repairs escalation is Jane Smith."]},
    )
    add_policy(
        jane,
        org_id,
        "Public Policy B",
        "PUBLIC",
        {"Reporting repairs": ["Report repairs online or call the repairs helpdesk."]},
    )
    add_policy(
        jane,
        org_id,
        "Both Policy C",
        "BOTH",
        {
            "Repair times": [
                "Repairs are prioritised by urgency, safety and the needs of the household."
            ]
        },
    )
    question = "Who is the internal manager responsible for repairs escalation?"

    public = ask(db, org_id, question, Requester.PUBLIC, limit=20)
    assert {p.policy_name for p in public} == {"Public Policy B", "Both Policy C"}
    assert all("Jane Smith" not in p.text for p in public)

    internal = ask(db, org_id, question, Requester.INTERNAL, limit=20)
    assert {p.policy_name for p in internal} == {
        "Internal Policy A",
        "Public Policy B",
        "Both Policy C",
    }
    assert internal[0].policy_name == "Internal Policy A"


def test_other_organisations_are_never_searched(org, db, make_client):
    jane, org_id = org
    add_policy(jane, org_id, "Repairs Policy", "PUBLIC", REPAIRS)
    mark = make_client("mark@example.org")
    other_id = mark.post("/api/organisations", json={"name": "Other", "slug": "other-org"}).json()[
        "id"
    ]
    add_policy(
        mark,
        other_id,
        "Other Org Repairs",
        "PUBLIC",
        {"Emergency repairs": ["Other org attends emergency repairs within 2 hours."]},
    )
    results = ask(db, org_id, "emergency repairs", Requester.PUBLIC, limit=20)
    assert {p.policy_name for p in results} == {"Repairs Policy"}
    other = ask(db, other_id, "emergency repairs", Requester.PUBLIC, limit=20)
    assert {p.policy_name for p in other} == {"Other Org Repairs"}


def test_empty_questions_and_limits(org, db):
    jane, org_id = org
    add_policy(jane, org_id, "Repairs Policy", "INTERNAL", REPAIRS)
    assert ask(db, org_id, "   ") == []
    assert len(ask(db, org_id, "repairs", limit=1)) == 1
    assert len(ask(db, org_id, "repairs", limit=0)) == 0
    assert len(ask(db, org_id, "repairs " * 2000)) >= 1  # very long questions are trimmed


def test_no_policies_means_no_evidence(org, db):
    _, org_id = org
    assert ask(db, org_id, "Are pets allowed in supported accommodation?") == []
