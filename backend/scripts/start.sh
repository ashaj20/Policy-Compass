#!/bin/sh
# Apply database migrations, then start the API. Render sets $PORT.
set -e
alembic upgrade head
exec uvicorn app.main:app --host 0.0.0.0 --port "${PORT:-8000}" --proxy-headers --forwarded-allow-ips="*"
