"""US-014: answers are grounded in permitted evidence, or the system says it can't answer.

A scripted stand-in replaces Claude, so these tests never use API credits.
"""

from types import SimpleNamespace

import pytest
from sqlalchemy import select

from app.answers.model import (
    ClaudeAnswerModel,
    GroundedAnswer,
    ModelReply,
    build_prompt,
)
from app.answers.service import AnswerStatus, Reason, answer_question
from app.config import Settings
from app.models import LlmUsage
from app.policies.audience import Requester
from app.rag.embeddings import HashingEmbedder
from tests.files import docx_with_sections

SETTINGS = Settings(retrieval_min_score=0.3, llm_daily_answer_cap=100, anthropic_api_key=None)


class ScriptedModel:
    """Returns pre-set replies and records exactly what it was shown."""

    def __init__(self, *replies: ModelReply):
        self.replies = list(replies)
        self.calls: list[tuple[str, list]] = []

    def answer(self, question, passages):
        self.calls.append((question, passages))
        return self.replies.pop(0) if self.replies else self.replies_default()

    @staticmethod
    def replies_default():
        return reply(True, "Emergency repairs are attended within 24 hours.", ["P1"])


def reply(sufficient, answer, cited, conflict=False, problem=None):
    if problem:
        return ModelReply(None, problem)
    return ModelReply(
        GroundedAnswer(
            sufficient=sufficient, conflict=conflict, answer=answer, cited_passages=cited
        ),
        None,
        input_tokens=900,
        output_tokens=120,
    )


@pytest.fixture
def org(make_client, process_inline):
    jane = make_client("jane@example.org")
    org_id = jane.post(
        "/api/organisations", json={"name": "Riverside Housing", "slug": "riverside-housing"}
    ).json()["id"]
    return jane, org_id


def add_policy(client, org_id, name, audience, sections, version="1.0"):
    resp = client.post(
        f"/api/organisations/{org_id}/policies",
        data={
            "name": name,
            "version": version,
            "effective_date": "2026-09-01",
            "audience": audience,
            "category": "Repairs",
        },
        files={"file": (f"{name}.docx", docx_with_sections(sections), "application/octet-stream")},
    )
    body = resp.json()
    base = (
        f"/api/organisations/{org_id}/policies/{body['id']}/versions/{body['latest_version']['id']}"
    )
    client.post(f"{base}/mark-ready")
    client.post(f"{base}/activate")
    return body["id"]


REPAIRS = {
    "Emergency repairs": [
        "Emergency repairs such as gas leaks or flooding are attended within 24 hours of a report."
    ],
    "Routine repairs": ["Routine repairs are completed within 28 calendar days of a report."],
}


def ask(db, org_id, question, model, requester=Requester.INTERNAL, settings=SETTINGS):
    return answer_question(
        db,
        organisation_id=org_id,
        requester=requester,
        question=question,
        embedder=HashingEmbedder(),
        model=model,
        settings=settings,
    )


QUESTION = "How quickly are emergency repairs attended?"


# --- Evidence gate ---


def test_no_relevant_evidence_means_no_model_call(org, db):
    jane, org_id = org
    add_policy(jane, org_id, "Repairs Policy", "INTERNAL", REPAIRS)
    model = ScriptedModel()
    result = ask(db, org_id, "Can tenants keep pets in supported housing?", model)
    assert result.status == AnswerStatus.INSUFFICIENT_EVIDENCE
    assert result.reason == Reason.NO_EVIDENCE
    assert result.answer is None and result.citations == []
    assert model.calls == []  # no credits spent


def test_no_policies_at_all(org, db):
    _, org_id = org
    model = ScriptedModel()
    result = ask(db, org_id, QUESTION, model)
    assert result.reason == Reason.NO_EVIDENCE and model.calls == []


# --- Grounded answers and citations ---


def test_supported_answer_cites_the_passages_used(org, db):
    jane, org_id = org
    policy_id = add_policy(jane, org_id, "Repairs Policy", "INTERNAL", REPAIRS)
    model = ScriptedModel(
        reply(True, "  Emergency repairs are attended within\n24 hours. ", ["P1"])
    )
    result = ask(db, org_id, QUESTION, model)
    assert result.status == AnswerStatus.ANSWERED
    assert result.answer == "Emergency repairs are attended within 24 hours."
    [citation] = result.citations
    question, passages = model.calls[0]
    assert question == QUESTION
    assert citation.chunk_id == str(passages[0].chunk_id)
    assert citation.policy_id == policy_id and citation.policy_name == "Repairs Policy"
    assert citation.version_label == "1.0" and citation.effective_date == "2026-09-01"
    assert citation.section == passages[0].section
    assert citation.excerpt == passages[0].text
    assert policy_id in result.searched_policy_ids


def test_citations_of_passages_that_were_not_supplied_are_dropped(org, db):
    jane, org_id = org
    add_policy(jane, org_id, "Repairs Policy", "INTERNAL", REPAIRS)
    result = ask(db, org_id, QUESTION, ScriptedModel(reply(True, "Within 24 hours.", ["P1", "P9"])))
    assert result.status == AnswerStatus.ANSWERED
    assert len(result.citations) == 1


@pytest.mark.parametrize(
    ("model_reply", "reason"),
    [
        (reply(True, "Within 24 hours.", []), Reason.NOT_SUPPORTED),  # no citation at all
        (reply(True, "Within 24 hours.", ["P7"]), Reason.NOT_SUPPORTED),  # only invented ones
        (reply(False, "", []), Reason.NOT_SUPPORTED),  # model says evidence isn't enough
        (reply(True, "   ", ["P1"]), Reason.NOT_SUPPORTED),  # empty answer
        (reply(True, "It depends.", ["P1"], conflict=True), Reason.CONFLICT),
        (reply(None, None, None, problem="refused"), Reason.UNAVAILABLE),
        (reply(None, None, None, problem="truncated"), Reason.UNAVAILABLE),
        (reply(None, None, None, problem="unavailable"), Reason.UNAVAILABLE),
    ],
)
def test_anything_short_of_a_supported_answer_escalates(org, db, model_reply, reason):
    jane, org_id = org
    add_policy(jane, org_id, "Repairs Policy", "INTERNAL", REPAIRS)
    result = ask(db, org_id, QUESTION, ScriptedModel(model_reply))
    assert result.status == AnswerStatus.INSUFFICIENT_EVIDENCE
    assert result.reason == reason
    assert result.answer is None and result.citations == []


def test_without_an_api_key_questions_escalate(org, db):
    jane, org_id = org
    add_policy(jane, org_id, "Repairs Policy", "INTERNAL", REPAIRS)
    result = ask(db, org_id, QUESTION, None)
    assert result.reason == Reason.UNAVAILABLE


# --- Audience boundary at the model ---


def test_public_questions_never_send_internal_passages_to_the_model(org, db):
    jane, org_id = org
    add_policy(
        jane,
        org_id,
        "Internal Escalations",
        "INTERNAL",
        {
            "Emergency repairs escalation": [
                "Emergency repairs escalations go to the internal duty manager."
            ]
        },
    )
    add_policy(jane, org_id, "Repairs Policy", "PUBLIC", REPAIRS)
    model = ScriptedModel()
    ask(db, org_id, QUESTION + " Who handles escalations?", model, Requester.PUBLIC)
    _, passages = model.calls[0]
    assert {p.policy_name for p in passages} == {"Repairs Policy"}
    assert all(p.audience != "INTERNAL" for p in passages)


# --- Saving credits: reuse and the daily cap ---


def test_repeated_questions_reuse_the_answer_until_the_evidence_changes(org, db):
    jane, org_id = org
    policy_id = add_policy(jane, org_id, "Repairs Policy", "INTERNAL", REPAIRS)
    model = ScriptedModel()
    first = ask(db, org_id, QUESTION, model)
    again = ask(db, org_id, "  how QUICKLY are emergency repairs attended?  ", model)
    assert len(model.calls) == 1
    assert again.from_cache and again.answer == first.answer
    assert again.citations == first.citations

    # A newly approved version replaces the passages, so the old answer is not reused.
    resp = jane.post(
        f"/api/organisations/{org_id}/policies/{policy_id}/versions",
        data={"version": "2.0", "effective_date": "2026-10-01"},
        files={"file": ("v2.docx", docx_with_sections(REPAIRS), "application/octet-stream")},
    )
    v2 = resp.json()["versions"][0]["id"]
    base = f"/api/organisations/{org_id}/policies/{policy_id}/versions/{v2}"
    jane.post(f"{base}/mark-ready")
    jane.post(f"{base}/activate")
    ask(db, org_id, QUESTION, model)
    assert len(model.calls) == 2


def test_temporary_problems_are_not_reused(org, db):
    jane, org_id = org
    add_policy(jane, org_id, "Repairs Policy", "INTERNAL", REPAIRS)
    model = ScriptedModel(reply(None, None, None, problem="unavailable"))
    assert ask(db, org_id, QUESTION, model).reason == Reason.UNAVAILABLE
    assert ask(db, org_id, QUESTION, model).status == AnswerStatus.ANSWERED
    assert len(model.calls) == 2


def test_daily_cap_stops_model_calls_and_tracks_tokens(org, db, make_client):
    jane, org_id = org
    add_policy(jane, org_id, "Repairs Policy", "INTERNAL", REPAIRS)
    capped = Settings(retrieval_min_score=0.3, llm_daily_answer_cap=2)
    model = ScriptedModel()
    ask(db, org_id, QUESTION, model, settings=capped)
    ask(db, org_id, "When are emergency repairs attended?", model, settings=capped)
    third = ask(db, org_id, "Are emergency repairs attended within hours?", model, settings=capped)
    assert third.reason == Reason.LIMIT_REACHED
    assert len(model.calls) == 2
    usage = db.scalar(select(LlmUsage).where(LlmUsage.organisation_id == org_id))
    assert usage.answers == 2 and usage.input_tokens == 1800 and usage.output_tokens == 240
    # Cached answers don't count towards the cap.
    assert ask(db, org_id, QUESTION, model, settings=capped).status == AnswerStatus.ANSWERED

    # Another organisation has its own allowance.
    mark = make_client("mark@example.org")
    other = mark.post("/api/organisations", json={"name": "Other", "slug": "other-org"}).json()[
        "id"
    ]
    add_policy(mark, other, "Other Repairs", "INTERNAL", REPAIRS)
    assert ask(db, other, QUESTION, model, settings=capped).status == AnswerStatus.ANSWERED


# --- The Claude call itself ---


def test_prompt_labels_passages_with_their_source_and_keeps_them_as_data(org, db):
    jane, org_id = org
    add_policy(jane, org_id, "Repairs Policy", "INTERNAL", REPAIRS)
    model = ScriptedModel()
    ask(db, org_id, QUESTION, model)
    _, passages = model.calls[0]
    prompt = build_prompt(QUESTION, passages)
    assert '<passage label="P1" source="Repairs Policy, version 1.0, section: ' in prompt
    assert prompt.rstrip().endswith(f"<question>\n{QUESTION}\n</question>")


def _fake_client(response=None, error=None):
    def parse(**kwargs):
        _fake_client.kwargs = kwargs
        if error:
            raise error
        return response

    return SimpleNamespace(messages=SimpleNamespace(parse=parse))


def _response(stop_reason, parsed):
    return SimpleNamespace(
        stop_reason=stop_reason,
        parsed_output=parsed,
        usage=SimpleNamespace(input_tokens=1000, output_tokens=150),
    )


def test_claude_model_requests_structured_low_effort_output():
    model = ClaudeAnswerModel("sk-test", "claude-haiku-5-5", 1500, 30.0)
    parsed = GroundedAnswer(sufficient=True, conflict=False, answer="Yes.", cited_passages=["P1"])
    model.client = _fake_client(_response("end_turn", parsed))
    result = model.answer("Q?", [])
    assert result.answer == parsed and result.problem is None
    assert (result.input_tokens, result.output_tokens) == (1000, 150)
    sent = _fake_client.kwargs
    assert sent["model"] == "claude-haiku-5-5" and sent["max_tokens"] == 1500
    assert sent["output_format"] is GroundedAnswer
    assert sent["output_config"] == {"effort": "low"}
    assert "only the policy passages" in sent["system"]


@pytest.mark.parametrize(
    ("stop_reason", "problem"), [("refusal", "refused"), ("max_tokens", "truncated")]
)
def test_claude_refusals_and_truncation_are_not_answers(stop_reason, problem):
    model = ClaudeAnswerModel("sk-test", "claude-haiku-5-5", 1500, 30.0)
    model.client = _fake_client(_response(stop_reason, None))
    result = model.answer("Q?", [])
    assert result.answer is None and result.problem == problem


def test_claude_connection_problems_are_reported_safely():
    import anthropic
    import httpx2 as httpx

    model = ClaudeAnswerModel("sk-test", "claude-haiku-5-5", 1500, 30.0)
    error = anthropic.APIConnectionError(request=httpx.Request("POST", "https://api.anthropic.com"))
    model.client = _fake_client(error=error)
    assert model.answer("Q?", []).problem == "unavailable"
