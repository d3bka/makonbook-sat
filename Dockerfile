FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

WORKDIR /app

# Install system dependencies for psycopg2 and PyMuPDF
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    libpq-dev \
    libmupdf-dev \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies
COPY r.txt .
RUN pip install --no-cache-dir -r r.txt

# Copy project
COPY . .

# Create necessary directories
RUN mkdir -p /app/logs /app/staticfiles /app/media

# Collect static files
RUN SECRET_KEY=build-placeholder \
    DB_ENGINE=django.db.backends.sqlite3 \
    python manage.py collectstatic --noinput 2>/dev/null || true

# Make entrypoint executable
RUN chmod +x /app/entrypoint.sh

EXPOSE 8000

ENTRYPOINT ["/app/entrypoint.sh"]
