import os

from celery import Celery

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "satmakon.settings")

app = Celery("satmakon")
app.config_from_object("django.conf:settings", namespace="CELERY")
app.autodiscover_tasks()
