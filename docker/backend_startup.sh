#!/bin/sh
set -eu


alembic -c /opt/app/backend/alembic.ini upgrade head

exec "$@"