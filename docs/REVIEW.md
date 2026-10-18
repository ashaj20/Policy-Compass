# Policy Compass Beta — Consolidated Document Review

Documents reviewed:
1. Technical Specification v1.1 (source of truth, see Spec §41)
2. Story-by-Story Detailed Design v1.0 (40 stories)
3. UX/UI Mockup Design Brief
4. Additional Requirements

Each item: **the conflict or gap**, then a **proposed resolution**. Nothing is final until you agree it.
Items marked **[DECIDE]** need your call. The rest have a recommended default I will use unless you object.

---

## A. Decisions that shape the build

> **DECIDED (15 Oct 2026)**
> - A1: **Always manual activation — a human approves.** Every version, including the first, goes Processing -> Ready (awaiting approval). An administrator explicitly approves and activates it. Only the active version is retrievable. Activation supersedes the previous active version.
>   - Recorded on the version: `activated_by` (user ID) and `activated_at` (UTC timestamp). These are shown on policy detail and version history.
>   - The previous version records `superseded_at` and `superseded_by` (the user who activated its replacement).
>   - Audit events `POLICY_ACTIVATED` and `POLICY_SUPERSEDED` record the actor, timestamp, previous active version and new active version, in the same database transaction as the switch.
>   - Only ADMIN can activate. This is enforced server-side, and only a version in READY can be activated.
>   - The activation dialog shows the policy name, the version being activated and the version it replaces, and needs explicit confirmation.
> - A2: **Auth built into FastAPI.** argon2 password hashes, email verification, password-reset and invite tokens, SMTP (console backend in dev).
> - A3: **In-house RAG.** Postgres + pgvector, Claude for answers, behind a `RAGService` interface.
> - A5: **Local embeddings model**, kept behind an interface so it can be swapped for a hosted provider such as Voyage later.
> - A6 (18 Oct 2026): **Answers by Claude Haiku 5.5 (`claude-haiku-5-5`), to use credits sparingly.**
>   - Hard app cap: **100 Claude answers per organisation per day**. Beyond the cap, questions get the escalation route.
>   - Claude is only called when retrieval finds sufficient evidence. Only the top passages are sent, output is capped, and identical questions against unchanged policies reuse the cached answer.
>   - Automated tests never call the API.
> - Sections B–E: **proposed defaults accepted for now** (15 Oct 2026), to be refined later.
> - A4: **No hard delete.** US-010 is replaced by US-010A (versioning & activation). Archive/Restore only.

### A1. Who activates a new version? [DECIDED — manual human approval, see above]
- Additional Req §2.3: "Once successfully processed, it **becomes** the active version" (automatic).
- Additional Req §11, Spec §8/§14: "New Version Ready → **Activate** New Version" (an admin step). Rule 7 (human control) supports a manual step.
- Stories: no activation step at all (upload → READY).

Proposed: the **first version** of a new policy activates automatically once processed, because there is nothing to protect.
A **new version of an existing policy** goes to *Ready (awaiting activation)*. An admin clicks **Activate**. The old version then becomes *Superseded*.

### A2. Auth provider [DECIDE]
US-001 assumes Supabase Auth. The agreed stack is FastAPI + React.
- Option 1: Supabase Auth (handles verification email and password reset). FastAPI verifies Supabase JWTs. Needs a Supabase project.
- Option 2: Auth built into FastAPI: argon2 password hashes, email verification and reset tokens, SMTP. No external dependency, but more code.

### A3. RAG provider [DECIDE]
US-011 assumes Dify behind a `RAGService` abstraction.
- Option 1: Dify. The retrieval security boundary (AC-03, AC-12) then depends on Dify metadata filters. Section-level citations depend on what Dify returns.
- Option 2: In-house. Postgres + pgvector for search, Claude for answer generation, all behind the same `RAGService` interface.
  Tenant, audience and status filters become a SQL `WHERE` clause on the same query, so they are easy to test.
  Section headings are kept per chunk, which gives section-level citations.
- Recommended: **Option 2.** Keep the `RAGService` interface so Dify could be added later.

### A4. Delete vs. retention [DECIDE]
US-010 hard-deletes a policy (record, file and index). The Spec requires keeping version history and audit (§8.8, §15), traceable past answers (AC-02), and Restore.
Delete appears in no other document.

Proposed: **drop hard delete from the beta.** Archive and Restore cover the need.
If delete is needed, allow it only for policies that never became active (Draft/Failed), and write an audit event.

---

## B. Missing stories (required by Spec/Additional Req; no story covers them)

| Need | Source | Proposed story placement |
|---|---|---|
| Upload new version, activation, Superseded, failed update keeps the active version | Spec §8, §14, AC-04; Add. Req §2, §11 | **US-010A** in Epic 2. The data model needs it before RAG work starts |
| Version history screen | Spec screen 17 | Part of US-010A |
| Restore archived policy | Spec §3.1; Add. Req §1 | Extend US-009 |
| Audit trail + basic activity view | Spec §15, AC-08; Add. Req §3 | **US-005A**. A shared audit service, added early so every later admin story writes events |
| Password reset | Spec §4 | Extend US-001 |
| Member invitation (person has no account yet) | Spec §4; US-003 | Extend US-003: invite token sent by email, accepted at signup or login |
| Validation step in processing | Spec §7, §19 | Extend US-011 (see C1) |
| Conflicting evidence | Spec §12; Add. Req §4 | Extend US-014 |
| Feedback reasons on "No" | Spec §17; Add. Req §5 | Extend US-020 |
| Knowledge-gap workflow (Open → Investigating → Resolved → Closed, notes, resolution) | Spec §18, AC-10; Add. Req §6 | **US-033A** after US-033 |
| Repeated negative feedback + simple operational status view | Spec §23; Add. Req §9 | **US-035A** |
| Retention rules documented and shown to admins | Spec §22; Add. Req §8 | **US-035B** (see C6) |
| Widget closed/open (floating launcher) | Spec §26; UX §28 | Extend US-030 (see B-W) |

**B-W. Widget.** US-030 asks for a plain iframe with no JS SDK. The Spec and UX brief want a floating launcher.
Proposed: provide a small `<script>` snippet (~50 lines, no SDK) that adds a launcher button and opens the public page in an iframe panel.
Also give the plain iframe code as an alternative. Both use the same public API.

---

## C. Gaps where I propose a default

**C1. What "validation" checks.** The document:
- passed the file checks (extension, MIME type, size)
- produced non-empty extracted text above a minimum length
- has at least one indexed chunk
- passes a test search: retrieving the document's own first chunk finds it.

If any check fails, the version is set to Failed.

**C2. Lifecycle states.**
- **Draft:** metadata saved, file not yet processed.
- **Processing.**
- **Ready:** processed. It is active, or awaiting activation if another version is still active.
- **Superseded, Archived, Failed.**

Rules:
- Each policy has at most one active version, enforced by the database (`policies.active_version_id`).
- The `is_active` flag is derived from that, so it cannot disagree with the status.
- Retrieval uses only versions where `status = READY` **and** the version is the active version **and** the policy is not archived.
- This closes the gap in US-013, which filters on `status = READY` alone.

**C3. Answer statuses.**
- `ANSWERED`
- `INSUFFICIENT_EVIDENCE`, which covers conflicts as well (stored with reason `no_evidence` or `conflict`)
- `ERROR`

"Escalated" appears in the UX mockup's question table. I propose recording it as a flag, `escalation_shown`, rather than as a separate status. That avoids overlap with Insufficient evidence.

**C4. Owner visibility (Spec §21, US-017).**
- Values: `internal` (default) and `public`.
- An owner marked `public` is still never shown automatically. Public escalation **only ever uses public help routes**.
- In the beta, `public` visibility therefore only affects what is shown in public citations: nothing.
- Recommended simplification: keep the field, but lock it to `internal` in the beta.
  This meets "internal contacts must never automatically become public" with no exceptions to test.

**C5. "Both" audience.** A Both policy is retrievable internally and publicly.
On the public side, its owner is never returned. Only its public help route, or the organisation's default route, is shown.

**C6. Retention defaults.** Configuration is not built in the beta; these are documented and shown on a read-only Settings page.
| Data | Retention |
|---|---|
| Uploaded documents | Kept for the life of the policy, including superseded/archived versions |
| Questions and answers | 12 months, then deleted |
| Feedback | 12 months, kept with the question |
| Knowledge gaps | Until Closed + 12 months |
| Audit events | 6 years |
| Analytics | Event-level 12 months; aggregate counts kept |

Public questions store no IP address and no user identifier. Only a random session ID is kept for session history.

**C7. Staff permissions.**
- There is no per-policy staff restriction in the beta, so staff can see every Ready internal/both policy.
- The policy list is read-only for staff, with no Contacts or Settings in their navigation.
- The Questions page shows staff **their own** questions only. Admins see all questions, internal and public.

**C8. Citation "View source".** Opens a source view of the cited version, scrolled to and highlighting the cited section excerpt.
- Public users can only open citations for Public/Both active versions.
- This uses a separate public endpoint that does the same audience check.

---

## D. Minor conflicts (proposed resolution)

| # | Conflict | Resolution |
|---|---|---|
| D1 | Signup: confirm password (US-001) vs. none (UX) | Include confirm password |
| D2 | `/internal/setup` is org creation (US-002) and also the checklist (UX §10) | `/internal/setup/organisation` for creation, `/internal/setup` for the checklist |
| D3 | Slug field on create-org (US-002) vs. absent (UX §9) | Generated from the name and shown as an editable preview |
| D4 | Dashboard "questions this month" (US-021/031) vs. "this week" (Spec, UX) | This week |
| D5 | Help-route fields: email/phone/website (US-024) vs. type + destination (Spec, UX) | Type + one destination field, validated per type, plus a description |
| D6 | Role names ADMIN/MEMBER vs. Administrator/Staff Member | DB values `ADMIN`/`STAFF`; UI labels "Administrator"/"Staff member" |
| D7 | Error message "[Retry]" (US-006) vs. full message (Spec §20) | Use the Spec wording and both actions |
| D8 | Dashboard and analytics split across US-021, US-031 and UX §29 | One dashboard. Staff see Ask + their recent questions; admins also see metrics + operational alerts |

---

## E. Proposed revised build order

> **Order change agreed 17 Oct 2026:** after US-008, build US-022 (policy list) and US-023 (policy detail) next, so archive/restore (US-009) and versioning (US-010A) have their buttons in the right place. Then continue with US-009, US-010A, US-011 onwards. US-021 (dashboard) and the rest of Epic 5 stay in their original place.
Stories run in order as the Story Design requires. **New/extended items are in bold.**

1. **Foundations:** repo, FastAPI + React + Postgres, design tokens, component library base, CI, test harness
2. 001 (**+ password reset**), 002, 003 (**+ invitations**), 004, 005, **005A audit service + activity view**
3. 006, 007, 008, 009 (**+ restore**), **010A versioning & activation** (replaces 010 delete)
4. 011 (**+ validation**), 012, 013, 014 (**+ conflicts**), 015
5. 016–020 (**020 + feedback reasons**)
6. 021–025
7. 026–030 (**030 + launcher script**)
8. 031–033, **033A knowledge gaps**, 034, 035, **035A ops status**, **035B retention**
9. 036–040

Security tests for AC-03, AC-04, AC-11 and AC-12 are written with the story that adds each boundary, not left until Epic 8.
Epic 8 then makes the suite complete and runs the evaluation set.

---

## F. Policy approval workflow (raised 17 Oct 2026) [DECIDED, see F-decisions]

**Proposal:** *New* when first uploaded → a **staff member** changes it to *Ready – awaiting approval* → an **administrator** approves → *Published*.

This adds a human review step, done by staff, before the admin approval agreed in A1. It conflicts with or extends the source documents as follows.

| # | Proposal vs. source documents | Conflict | Needs a decision |
|---|---|---|---|
| F1 | Staff mark a version "Ready" | **Direct conflict.** Spec §3.2 says staff "cannot upload or modify policies". Add. Req §1 says staff "must not be able to change … policy content". Spec §39 says the beta doesn't need "complicated approval hierarchies". | Who may do the review step: every staff member, a new "Reviewer" role, or administrators only? |
| F2 | Status names *New / Ready – awaiting approval / Published* | Spec §7 and Add. Req §2 list *Draft, Processing, Ready, Superseded, Archived, Failed*. In the spec, "Ready" means *successfully processed*, not *reviewed by a person*. | Confirm the new names replace the spec's names in the UI. |
| F3 | Where automatic processing fits | The proposal doesn't mention processing or *Failed*. The spec requires automatic processing and validation before a version can be used, and a failed update must never replace the active version (AC-04). | Proposed: processing runs automatically while the version is *New*. A version can only be marked ready once processing succeeded. If processing fails, the version shows *Failed*. |
| F4 | Same person submits and approves? | Not covered. In a small organisation the only administrator might do both steps. | Must review and approval be done by different people? |
| F5 | Sending back | Not covered. | Can an administrator reject a version back to *New* with a reason? Can a reviewer withdraw it? |
| F6 | First version vs. later versions | A1 already says every version needs approval, including the first. | Confirm the workflow applies to every version. |
| F7 | "Published" wording | On the public side, "published" could be read as "public". | Proposed: *Published* means "live for its audience". Internal policies show *Published* too, with the Internal badge alongside. |
| F8 | Staff visibility | C7 / US-022 currently let staff see Ready policies only. Reviewers would need to see *New* versions to review them. | Follows from F1. |

**Proposed data model (no change to anything already agreed):** keep two separate facts on each version instead of one overloaded status.
- **Processing:** Processing → Processed / Failed (automatic).
- **Approval:** New → Awaiting approval → Published → Superseded (people).
- The UI shows one combined label: *Processing*, *Failed*, *New*, *Ready – awaiting approval*, *Published*, *Superseded*, plus *Archived* at policy level.

**Retrieval rule becomes:** only the **Published** version of a non-archived policy, permitted for the requester's audience. The rule is the same; the name changes from "active READY".

**Audit additions:**
- Version submitted for approval (who, when).
- Approval rejected (who, when, reason).
- Plus the already-agreed version activated / superseded events, renamed *published* / *superseded*.

**Effect on code already built:** small.
- Uploads currently start in `PROCESSING` and the list/detail show `Ready`.
- One migration adds the approval field. Labels and staff visibility are adjusted in the same story (US-010A).

### F-decisions (17 Oct 2026)
These replace the "Proposed data model" above and extend A1.

- **Statuses (spec names kept, plus Active):** PROCESSING → DRAFT → READY ("Ready – awaiting approval") → ACTIVE → SUPERSEDED. FAILED if processing fails. ARCHIVED stays at policy level.
  - DRAFT now means "processed successfully, not yet reviewed". It is the user's "New".
- **F1 Review step:** **any member, staff or admin,** may mark a DRAFT version Ready. This deliberately extends Spec §3.2 for this one action. Staff still cannot upload, edit, approve, archive or change policy details.
- **F4:** the same person may mark ready and approve. An admin can do both.
- **F5:** an administrator can **reject** a Ready version back to Draft with a **required reason**, which is audited and shown on the policy. The person who marked it ready, or an admin, can **withdraw** it back to Draft.
- **F6:** applies to every version, including the first (as A1).
- **Approval:** administrators only. Approving makes the version ACTIVE and records `activated_by` and `activated_at`. The previous ACTIVE version becomes SUPERSEDED and records `superseded_by` and `superseded_at`. Both events are audited in the same transaction.
- **One active version:** the database allows at most one ACTIVE version per policy (partial unique index).
- **F8 Staff visibility:** staff see non-archived policies that have an Active version, plus versions waiting for review (Draft/Ready), so they can review them. They never see Processing-only or Failed-only uploads.
- **Retrieval:** only the ACTIVE version of a non-archived policy permitted for the requester's audience.
- **New version while another is pending:** the older pending version (never active) becomes SUPERSEDED and is kept for history. There is only ever one version in progress.
