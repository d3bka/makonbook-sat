from .settings import *  # noqa: F401,F403

STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
}
MIDDLEWARE = [
    item for item in MIDDLEWARE
    if item != "apps.base.middleware.MakonErrorPageMiddleware"
]
PASSWORD_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]
