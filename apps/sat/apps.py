from django.apps import AppConfig


class SatConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'apps.sat'

    def ready(self):
        from . import additional  # noqa: F401
        from . import signals  # noqa: F401