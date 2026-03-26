#!/bin/bash
set -e

echo "Waiting for database..."
while ! python -c "
import os, sys
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'satmakon.settings')
import django; django.setup()
from django.db import connections
try:
    connections['default'].cursor()
except Exception:
    sys.exit(1)
" 2>/dev/null; do
    echo "Database unavailable - sleeping 2s..."
    sleep 2
done
echo "Database is ready!"

echo "Running migrations..."
python manage.py migrate --noinput

echo "Collecting static files..."
python manage.py collectstatic --noinput

exec gunicorn satmakon.wsgi:application --bind 0.0.0.0:8000 --workers 2 --threads 2 --timeout 120