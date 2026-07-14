#!/usr/bin/env bash
# Vercel build: install, collect static, run DB migrations against Neon.
# DIRECT_DATABASE_URL (non-pooled) is preferred for migrations because DDL
# through pgbouncer can misbehave; falls back to DATABASE_URL.
set -euo pipefail

pip install -r requirements.txt
python manage.py collectstatic --noinput

if [ -n "${DATABASE_URL:-}" ]; then
  DATABASE_URL="${DIRECT_DATABASE_URL:-$DATABASE_URL}" python manage.py migrate --noinput
else
  echo "DATABASE_URL not set - skipping migrate (local/preview without DB)"
fi
