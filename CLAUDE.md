# Policy Compass — build instructions

AI policy knowledge platform: organisations upload approved policies; staff and the public ask questions
and get answers grounded only in approved evidence, with citations, or a clear "not enough evidence" response
plus the configured escalation route.

**Safety principle: no answer is better than an unsupported answer.**

## Source documents (read before implementing a story)
- `docs/REVIEW.md` — consolidated review of the four source documents, plus every agreed decision. Decisions there
  override the original documents.
- The Technical Specification v1.1 is the architectural source of truth. If documents conflict: flag it, don't
  silently choose; resolve with the user.

## Stack
- `backend/`: Python 3.13, FastAPI, SQLAlchemy 2 (sync), Alembic, Postgres 16 + pgvector, pytest. Managed with `uv`.
- `frontend/`: React 19 + TypeScript, Vite, React Router, Vitest + Testing Library. Plain CSS with tokens in
  `src/styles/tokens.css`.
- Auth is built in (no external provider). RAG is in-house (pgvector + Claude) behind a `RAGService` interface.
  Embeddings use a local model behind an interface.

## Commands
```
# database (local): docker compose up -d db   (or a local Postgres with pgvector)
cd backend && uv run alembic upgrade head && uv run uvicorn app.main:app --reload
cd backend && uv run pytest && uv run ruff check . && uv run ruff format --check .
cd frontend && npm run dev
cd frontend && npm test && npm run lint && npm run build
```
Tests need the test database `policy_compass_test` (see `backend/tests/conftest.py`, `PC_TEST_DATABASE_URL`).

## Story workflow
Implement stories one at a time, in the order in `docs/REVIEW.md` section E. For each story:
1. Inspect the existing implementation; don't rebuild what exists.
2. Implement only that story's scope — don't build future stories early.
3. Add or update migrations, API, UI, validation, security checks and tests.
4. Run backend and frontend tests and lint; fix failures.
5. Commit that story on its own (message `US-0NN: ...`) and push to GitHub before starting the next one, so each story is a
   restore point.
6. Report files changed and tests run.

## Non-negotiable rules
- Authorisation is enforced server-side on every endpoint. The UI is never the security boundary.
- Every query on tenant data is scoped by `organisation_id`. Cross-tenant access must fail (AC-11).
- Retrieval only uses the **active**, READY version of non-archived policies whose audience permits the requester.
  Public requests never see INTERNAL content, internal owners, members, questions or audit data (AC-03, AC-12).
- Activation is always a manual admin action; record who and when, and write the audit event in the same
  transaction (decision A1). A failed version never replaces the active one (AC-04).
- Never invent contacts, URLs, emails, phone numbers or citations. Only show configured data and evidence
  that was actually used (AC-07, AC-02).
- Users see plain-English errors only; unexpected errors return an `error_id`, never a stack trace.
- Accessibility: labelled inputs, keyboard support, visible focus, status messages via live regions, never
  colour alone, 44px touch targets.
- Demo data is fictional (Riverside Housing, `example.org` addresses).
