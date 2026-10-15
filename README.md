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

## Deploy (Render + Neon, free tiers)
`render.yaml` is a Render Blueprint. It creates one free web service, built from the `Dockerfile`, that serves
the API and the React app from the same URL. Migrations run on every start. The database is a free Neon Postgres
database, which supports pgvector.

1. Neon (https://neon.tech): create a project (region: AWS Europe, Frankfurt) and copy its connection string.
2. Render: **New → Blueprint**, choose this repository, paste the Neon connection string into
   `PC_DATABASE_URL`, then click **Apply**.
3. When the deploy finishes, open the service URL. `/api/health` should return `{"status":"ok"}`.

Free-tier limits: the service sleeps after 15 minutes without traffic, so the first request then takes about
a minute. It also has 512 MB of memory.
