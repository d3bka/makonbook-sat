#!/bin/sh
set -eu

mkdir -p /app/staticfiles /app/media /app/logs

wait_for_database() {
  if [ "${DB_ENGINE:-}" != "django.db.backends.postgresql" ] && [ -z "${DATABASE_URL:-}" ]; then
    return 0
  fi

  timeout="${DB_WAIT_TIMEOUT:-90}"
  interval="${DB_WAIT_INTERVAL:-2}"

  echo "Waiting for PostgreSQL at ${DB_HOST:-database}:${DB_PORT:-5432} (timeout: ${timeout}s)..."

  python - "$timeout" "$interval" <<'PY'
import os
import sys
import time
from urllib.parse import urlparse, unquote

import psycopg2

timeout = int(sys.argv[1])
interval = max(1, int(sys.argv[2]))
deadline = time.monotonic() + timeout
last_error = None

while time.monotonic() < deadline:
    try:
        database_url = os.getenv("DATABASE_URL", "").strip()
        if database_url:
            parsed = urlparse(database_url)
            conn = psycopg2.connect(
                dbname=parsed.path.lstrip("/"),
                user=unquote(parsed.username or ""),
                password=unquote(parsed.password or ""),
                host=parsed.hostname or "",
                port=parsed.port or 5432,
                connect_timeout=5,
            )
        else:
            conn = psycopg2.connect(
                dbname=os.environ["DB_NAME"],
                user=os.environ["DB_USER"],
                password=os.environ["DB_PASSWORD"],
                host=os.getenv("DB_HOST", "db"),
                port=os.getenv("DB_PORT", "5432"),
                connect_timeout=5,
            )
        conn.close()
        print("PostgreSQL is available.")
        raise SystemExit(0)
    except Exception as exc:  # noqa: BLE001
        last_error = exc
        time.sleep(interval)

print(f"PostgreSQL was not available before timeout: {last_error}", file=sys.stderr)
raise SystemExit(1)
PY
}

wait_for_database

if [ "${RUN_MIGRATIONS:-1}" = "1" ]; then
  echo "Applying database migrations..."
  python manage.py migrate --noinput
fi

if [ "${COLLECTSTATIC_ON_START:-1}" = "1" ]; then
  echo "Collecting static files..."
  python manage.py collectstatic --noinput
fi

exec "$@"
