from django.apps import AppConfig


class RatingsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.ratings"
    verbose_name = "Student ratings"

    def ready(self):
        from . import signals  # noqa: F401
