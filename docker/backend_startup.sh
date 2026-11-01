#!/bin/sh
set -eu


alembic -c /opt/app/backend/alembic.ini upgrade head

exec uvicorn backend.app.main:app \
    --app-dir /opt/app \
    --host 0.0.0.0 \
    --port 8000 \
    --reload \
    --reload-dir /opt/app/backend