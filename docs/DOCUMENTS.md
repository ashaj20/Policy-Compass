# Policy Compass — Source Documents

| # | Document | Status |
|---|----------|--------|
| 1 | Technical Specification v1.1 (25 Sep 2026) | Received |
| 2 | Story-by-Story Detailed Design v1.0 (8 epics / 40 stories) | Received |
| 3 | UX/UI Mockup Design Brief | Received |
| 4 | Additional Requirements (assumed = 'master spec') | Received |

Agreed stack: Python FastAPI, React, Postgres + pgvector, Claude API, built-in auth. See REVIEW.md for all decisions.

## Open issues found in Technical Spec v1.1
1. Activation: is it manual (Ready -> admin activates) or automatic? Section 8 and Journey A differ.
2. "Validation" step not defined.
3. Lifecycle: "Draft" unused; no explicit "processed, not yet active" state; Active/inactive flag can contradict Status.
4. Retention periods (Section 22) are not specified.
5. Answer statuses "Insufficient evidence" and "Escalated" overlap.
6. "Configured policy hierarchy" for conflicts (Section 12) has no data model or UI.
7. "Appropriately configured Both" content for public is undefined; internal owner of a Both policy must stay hidden from public users.
8. Policy-owner "visibility" field values are undefined.
9. "Permitted" internal content: there is no per-policy staff restriction model; currently every staff member sees all internal content.
10. LLM, embedding and hosting choices are not specified.

## Conflicts: Story Design v1.0 vs Technical Spec v1.1
C1. Version update / activation / Superseded (Spec 8, 14, Journey D, AC-04): no story covers it. Stories go straight upload -> READY.
C2. Retrieval filter `status = READY` (US-013) is only safe if a processed-but-not-activated version is not READY.
C3. Hard delete (US-010) vs retention of history and traceability (Spec 8.8, 15, AC-02). Spec has Restore; stories don't.
C4. Audit trail (Spec 15, AC-08): no story. US-035 analytics events are not audit events.
C5. Knowledge-gap workflow with status, notes and resolution (Spec 18, AC-10): US-033 is only a filter.
C6. Feedback reasons for "No" (Spec 17): US-020 is Yes/No only.
C7. Answer statuses: Spec has Escalated and Error; stories have only ANSWERED and INSUFFICIENT_EVIDENCE.
C8. Conflicting evidence (Spec 12): no story.
C9. Password reset and invitations (Spec 4): no story. US-003 "Add member" by email doesn't say what happens if the person has no account.
C10. Widget: Spec 26 asks for a floating launcher; US-030 says plain iframe and no JS SDK.
C11. Validation processing step (Spec 7, 19): not in stories.
C12. Screens in spec but no story: version history (17), knowledge gaps (19), audit/activity (24), widget closed/open (31-32).
C13. Retention rules (Spec 22): no story.
C14. Dashboard: "questions this week" (Spec 24) vs "this month" (US-021, US-031).
C15. Help-route fields: Spec has label/type/destination/description; US-024 has type/label/email/phone/website.
C16. Roles: ADMIN/MEMBER (stories) vs Administrator/Staff Member (spec). Naming only.
C17. Internal owner shown to public "if explicitly configured as public" (US-017) vs "never automatically become public" (Spec 21). Compatible only if this is an explicit admin choice; needs defining.

## Stack implications from the stories
S1. US-001 assumes Supabase Auth. Works with FastAPI by verifying Supabase JWTs. Alternative: self-hosted auth.
S2. US-011 assumes Dify as the RAG provider behind a RAGService abstraction. Alternative: in-house pgvector + Claude.
    The choice affects how audience, status and tenant filters (AC-03, AC-12) and section-level citations are enforced.
S3. Build process: one story at a time, in order. Each story: migrations, UI, API, validation, security, tests. Report files changed.
