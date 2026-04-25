#!/bin/bash
set -e

MAX_TRIES="${DB_WAIT_MAX_TRIES:-30}"
SLEEP_SECS="${DB_WAIT_SLEEP_SECS:-2}"

echo "Waiting for database..."

i=1
while true; do
    if python -c "
import os
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'satmakon.settings')
import django
django.setup()
from django.db import connections
connections['default'].cursor()
print('Database connection OK')
"; then
        echo "Database is ready!"
        break
    fi

    if [ "$i" -ge "$MAX_TRIES" ]; then
        echo "Database did not become ready after $MAX_TRIES attempts"
        exit 1
    fi

    echo "Database unavailable - sleeping ${SLEEP_SECS}s... ($i/$MAX_TRIES)"
    i=$((i + 1))
    sleep "$SLEEP_SECS"
done

if [ "${RUN_MIGRATIONS:-1}" = "1" ]; then
    echo "Running migrations..."
    python manage.py migrate --noinput
fi

if [ "${COLLECTSTATIC_ON_START:-1}" = "1" ]; then
    echo "Collecting static files..."
    python manage.py collectstatic --noinput
fi

exec "$@"