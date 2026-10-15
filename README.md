# Policy Compass

Turn approved policies into clear, cited answers — and say so plainly when the evidence isn't there.

Beta in development. See `docs/REVIEW.md` for the agreed requirements and decisions, and `CLAUDE.md` for
the build workflow.

## Run locally
Requirements: Python 3.13 with [uv](https://docs.astral.sh/uv/), Node 22, Docker (or Postgres 16 + pgvector).

```bash
docker compose up -d db

cd backend
cp .env.example .env
uv sync
uv run alembic upgrade head
uv run uvicorn app.main:app --reload      # http://localhost:8000/api/health

cd ../frontend
npm install
npm run dev                               # http://localhost:5173
```

## Tests
```bash
cd backend && uv run pytest
cd frontend && npm test
```
