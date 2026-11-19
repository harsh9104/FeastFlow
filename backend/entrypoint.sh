#!/bin/sh
# API container start: apply migrations, make sure the admin exists, then serve.
set -e
alembic upgrade head
python -m app.seed
exec uvicorn app.main:app --host 0.0.0.0 --port 8000 --proxy-headers
