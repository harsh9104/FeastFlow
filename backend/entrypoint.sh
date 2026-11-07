#!/bin/sh
set -e
alembic upgrade head
exec gunicorn app.main:app -k uvicorn.workers.UvicornWorker -w "${WEB_CONCURRENCY:-2}" --keep-alive 75 -b 0.0.0.0:8000
