from pathlib import Path
import os
from urllib.parse import urlparse, parse_qs, unquote
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
dotenv_path = BASE_DIR / '.env'
load_dotenv(dotenv_path)



def env_bool(name: str, default: bool = False) -> bool:
    return os.getenv(name, str(default)).strip().lower() in ("1", "true", "yes", "on")


def env_list(name: str, default: str = "") -> list[str]:
    value = os.getenv(name, default)
    return [item.strip() for item in value.split(",") if item.strip()]


def env_str(name: str, default: str = "") -> str:
    return os.getenv(name, default).strip() or default


SECRET_KEY = os.getenv("SECRET_KEY")
if not SECRET_KEY:
    config_path = BASE_DIR / "satmakon" / "config.ini"
    if config_path.exists():
        with open(config_path, "r", encoding="utf-8") as file:
            SECRET_KEY = file.readline().strip()
    else:
        raise RuntimeError("SECRET_KEY env var not set and config.ini not found")


DEBUG = env_bool("DEBUG", False)

<<<<<<< HEAD
# Keep the canonical production hosts available even when an older .env is
# accidentally mounted during deployment. A stale host/origin list causes
# valid authenticated POST requests to fail before they reach the view.
_CANONICAL_ALLOWED_HOSTS = [
    "makonbook.uz",
    "www.makonbook.uz",
    "makonbook.satmakon.com",
    "makonbook-sat.ondigitalocean.app",
    "127.0.0.1",
    "localhost",
]
ALLOWED_HOSTS = list(dict.fromkeys(
    env_list("ALLOWED_HOSTS") + _CANONICAL_ALLOWED_HOSTS
))

_CANONICAL_CSRF_ORIGINS = [
    "https://makonbook.uz",
    "https://www.makonbook.uz",
    "https://makonbook.satmakon.com",
    "https://makonbook-sat.ondigitalocean.app",
]
CSRF_TRUSTED_ORIGINS = list(dict.fromkeys(
    env_list("CSRF_TRUSTED_ORIGINS") + _CANONICAL_CSRF_ORIGINS
))
# The one hostname search engines and social-card scrapers should see. The app
# answers on several names, so sitemap.xml, robots.txt and the og: tags all
# build their absolute URLs from this rather than from the request host --
# otherwise every alias advertises itself as a separate copy of the site.
SITE_DOMAIN = env_str("SITE_DOMAIN", "makonbook.uz")
SITE_PROTOCOL = env_str("SITE_PROTOCOL", "http" if DEBUG else "https")
SITE_URL = f"{SITE_PROTOCOL}://{SITE_DOMAIN}"
=======
ALLOWED_HOSTS = ["*"]

CSRF_TRUSTED_ORIGINS = env_list("CSRF_TRUSTED_ORIGINS")
>>>>>>> 8bac338a46e0ea29b051683a0812ace0f67efd8d


INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "django.contrib.humanize",
    "django.contrib.sitemaps",
    "storages",

    "django.contrib.sites",
    "allauth",
    "allauth.account",
    "allauth.socialaccount",
    "allauth.socialaccount.providers.google",

    "apps.base.apps.BaseConfig",
    "apps.sat.apps.SatConfig",
    "apps.apclasses.apps.ApClassesConfig",
    "apps.ratings.apps.RatingsConfig",
    "apps.telegram_bot",
]


MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "apps.base.middleware.MakonErrorPageMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "allauth.account.middleware.AccountMiddleware",
    "apps.sat.middleware.ClientSoftwareMiddleware",
    "apps.sat.middleware.RequestTimeoutMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]


ROOT_URLCONF = "satmakon.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
                "apps.base.context_processors.site_meta",
                "apps.base.context_processors.test_import_meta",
            ],
        },
    },
]

WSGI_APPLICATION = "satmakon.wsgi.application"


def database_from_url(db_url: str) -> dict:
    parsed = urlparse(db_url)
    scheme = parsed.scheme.lower()

    if scheme in ("postgres", "postgresql", "pgsql"):
        engine = "django.db.backends.postgresql"
    elif scheme in ("sqlite", "sqlite3"):
        engine = "django.db.backends.sqlite3"
    else:
        raise ValueError(f"Unsupported database scheme: {scheme}")

    if engine == "django.db.backends.sqlite3":
        db_name = parsed.path.lstrip("/") or str(BASE_DIR / "db.sqlite3")
        return {
            "ENGINE": engine,
            "NAME": db_name,
        }

    query = parse_qs(parsed.query)
    options = {}

    if "sslmode" in query:
        options["sslmode"] = query["sslmode"][0]
    elif not DEBUG:
        options["sslmode"] = os.getenv("DB_SSLMODE", "require")

    db_config = {
        "ENGINE": engine,
        "NAME": parsed.path.lstrip("/"),
        "USER": unquote(parsed.username or ""),
        "PASSWORD": unquote(parsed.password or ""),
        "HOST": parsed.hostname or "",
        "PORT": str(parsed.port or ""),
        "CONN_MAX_AGE": int(os.getenv("DB_CONN_MAX_AGE", "600")),
    }

    if options:
        db_config["OPTIONS"] = options

    return db_config


DATABASE_URL = os.getenv("DATABASE_URL", "").strip()

if DATABASE_URL:
    DATABASES = {
        "default": database_from_url(DATABASE_URL)
    }
else:
    DB_ENGINE = os.getenv("DB_ENGINE", "django.db.backends.sqlite3")

    if DB_ENGINE == "django.db.backends.postgresql":
        db_options = {}
        db_sslmode = os.getenv("DB_SSLMODE", "").strip()
        if db_sslmode:
            db_options["sslmode"] = db_sslmode
        elif not DEBUG:
            db_options["sslmode"] = "require"

        DATABASES = {
            "default": {
                "ENGINE": os.getenv("DB_ENGINE"),
                "NAME": os.getenv("DB_NAME"),
                "USER": os.getenv("DB_USER"),
                "PASSWORD": os.getenv("DB_PASSWORD"),
                "HOST": os.getenv("DB_HOST"),
                "PORT": os.getenv("DB_PORT"),
                "CONN_MAX_AGE": 0,
                "CONN_HEALTH_CHECKS": True,
                "OPTIONS": db_options,
            }
        }
    else:
        DATABASES = {
            "default": {
                "ENGINE": "django.db.backends.sqlite3",
                "NAME": BASE_DIR / "db.sqlite3",
            }
        }


AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]


LANGUAGE_CODE = "en-us"
TIME_ZONE = "Asia/Tashkent"
USE_I18N = True
USE_TZ = True


STATIC_URL = "/static/"
STATIC_ROOT = BASE_DIR / "staticfiles"

STATICFILES_DIRS = []
project_static_dir = BASE_DIR / "static"
if project_static_dir.exists():
    STATICFILES_DIRS.append(project_static_dir)

STATICFILES_STORAGE = "whitenoise.storage.CompressedManifestStaticFilesStorage"

MEDIA_URL = "/media/"
MEDIA_ROOT = BASE_DIR / "media"

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# Email settings for verification/password reset codes
EMAIL_BACKEND = env_str("EMAIL_BACKEND", "django.core.mail.backends.smtp.EmailBackend")
EMAIL_HOST = env_str("EMAIL_HOST", "smtp.gmail.com")
EMAIL_PORT = int(env_str("EMAIL_PORT", "587"))
EMAIL_USE_TLS = env_bool("EMAIL_USE_TLS", True)
EMAIL_USE_SSL = env_bool("EMAIL_USE_SSL", False)
EMAIL_HOST_USER = env_str("EMAIL_HOST_USER", "")
EMAIL_HOST_PASSWORD = env_str("EMAIL_HOST_PASSWORD", env_str("EMAIL_PASSWORD", ""))
DEFAULT_FROM_EMAIL = env_str("DEFAULT_FROM_EMAIL", EMAIL_HOST_USER or "webmaster@localhost")
SERVER_EMAIL = env_str("SERVER_EMAIL", DEFAULT_FROM_EMAIL)


# File upload and request size limits for test submissions
DATA_UPLOAD_MAX_MEMORY_SIZE = 50 * 1024 * 1024  # 50MB
DATA_UPLOAD_MAX_NUMBER_FIELDS = 10000
DATA_UPLOAD_MAX_NUMBER_FILES = 100
FILE_UPLOAD_MAX_MEMORY_SIZE = 50 * 1024 * 1024  # 50MBs

# Request timeout settings
REQUEST_TIMEOUT = 60  # seconds

# Public registration throttling. These defaults are intentionally tolerant of
# school NATs while still stopping repeated automated submissions.
REGISTRATION_RATE_LIMIT_ENABLED = env_bool("REGISTRATION_RATE_LIMIT_ENABLED", True)
REGISTRATION_RATE_LIMIT_IP_MAX = int(os.getenv("REGISTRATION_RATE_LIMIT_IP_MAX", "20"))
REGISTRATION_RATE_LIMIT_IP_WINDOW_SECONDS = int(os.getenv("REGISTRATION_RATE_LIMIT_IP_WINDOW_SECONDS", "600"))
REGISTRATION_RATE_LIMIT_IDENTIFIER_MAX = int(os.getenv("REGISTRATION_RATE_LIMIT_IDENTIFIER_MAX", "5"))
REGISTRATION_RATE_LIMIT_IDENTIFIER_WINDOW_SECONDS = int(os.getenv("REGISTRATION_RATE_LIMIT_IDENTIFIER_WINDOW_SECONDS", "1800"))

# Test Import Center upload/queue throttling. The short cooldown is primarily
# an idempotency guard against double-clicks; the wider window protects the
# expensive upload + background-audit pipeline from repeated requests.
TEST_IMPORT_RATE_LIMIT_ENABLED = env_bool("TEST_IMPORT_RATE_LIMIT_ENABLED", True)
TEST_IMPORT_SUBMIT_COOLDOWN_SECONDS = int(os.getenv("TEST_IMPORT_SUBMIT_COOLDOWN_SECONDS", "15"))
TEST_IMPORT_RATE_LIMIT_MAX = int(os.getenv("TEST_IMPORT_RATE_LIMIT_MAX", "6"))
TEST_IMPORT_RATE_LIMIT_WINDOW_SECONDS = int(os.getenv("TEST_IMPORT_RATE_LIMIT_WINDOW_SECONDS", "600"))

# Shared Redis counters in production; zero-setup in-memory counters in local
# DEBUG mode. Set REGISTRATION_RATE_LIMIT_CACHE_URL explicitly to use Redis
# while running Django directly from a local virtualenv.
REGISTRATION_RATE_LIMIT_CACHE_URL = os.getenv("REGISTRATION_RATE_LIMIT_CACHE_URL", "").strip()
if REGISTRATION_RATE_LIMIT_CACHE_URL:
    CACHES = {
        "default": {
            "BACKEND": "django.core.cache.backends.redis.RedisCache",
            "LOCATION": REGISTRATION_RATE_LIMIT_CACHE_URL,
            "KEY_PREFIX": "makonbook",
        }
    }
elif DEBUG:
    CACHES = {
        "default": {
            "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
            "LOCATION": "makonbook-dev",
        }
    }
else:
    CACHES = {
        "default": {
            "BACKEND": "django.core.cache.backends.redis.RedisCache",
            "LOCATION": "redis://redis:6379/3",
            "KEY_PREFIX": "makonbook",
        }
    }


# Logging configuration for monitoring large requests
LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'handlers': {
        'console': {
            'class': 'logging.StreamHandler',
        },
    },
    'loggers': {
        'apps.sat.middleware': {
            'handlers': ['console'],
            'level': 'INFO',
        },
    },
}


SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
USE_X_FORWARDED_HOST = True

SESSION_COOKIE_SECURE = not DEBUG
CSRF_COOKIE_SECURE = not DEBUG

# v35 deliberately uses a new cookie name. Browsers can retain an old host-only
# and an old domain-wide ``csrftoken`` at the same time; Django may then receive
# the wrong value and reject an otherwise valid form. A versioned name starts
# with one unambiguous cookie without weakening CSRF protection.
CSRF_COOKIE_NAME = env_str("CSRF_COOKIE_NAME", "makonbook_csrftoken_v35")
CSRF_COOKIE_PATH = "/"
CSRF_COOKIE_HTTPONLY = False
CSRF_COOKIE_SAMESITE = env_str("CSRF_COOKIE_SAMESITE", "Lax")
SESSION_COOKIE_SAMESITE = env_str("SESSION_COOKIE_SAMESITE", "Lax")

SECURE_SSL_REDIRECT = env_bool("SECURE_SSL_REDIRECT", not DEBUG)

SECURE_HSTS_SECONDS = int(os.getenv("SECURE_HSTS_SECONDS", "0" if DEBUG else "31536000"))
SECURE_HSTS_INCLUDE_SUBDOMAINS = env_bool("SECURE_HSTS_INCLUDE_SUBDOMAINS", not DEBUG)
SECURE_HSTS_PRELOAD = env_bool("SECURE_HSTS_PRELOAD", not DEBUG)


R2_ACCESS_KEY_ID = os.getenv("R2_ACCESS_KEY_ID")
R2_SECRET_ACCESS_KEY = os.getenv("R2_SECRET_ACCESS_KEY")
R2_BUCKET_NAME = os.getenv("R2_BUCKET_NAME")
R2_ENDPOINT_URL = os.getenv("R2_ENDPOINT_URL")

AWS_ACCESS_KEY_ID = R2_ACCESS_KEY_ID
AWS_SECRET_ACCESS_KEY = R2_SECRET_ACCESS_KEY
AWS_STORAGE_BUCKET_NAME = R2_BUCKET_NAME
AWS_S3_ENDPOINT_URL = R2_ENDPOINT_URL
AWS_S3_REGION_NAME = os.getenv("R2_REGION", "auto")

AWS_S3_SIGNATURE_VERSION = "s3v4"
AWS_S3_ADDRESSING_STYLE = "virtual"
AWS_S3_USE_SSL = True
AWS_S3_VERIFY = True
AWS_S3_CUSTOM_DOMAIN = os.getenv(
    "AWS_S3_CUSTOM_DOMAIN",
    "pub-2967bfd7582a441fa07820ea020c1616.r2.dev"
)
AWS_S3_URL_PROTOCOL = "https:"
AWS_QUERYSTRING_AUTH = False
AWS_DEFAULT_ACL = None
AWS_S3_FILE_OVERWRITE = False

STORAGES = {
    "default": {
        "BACKEND": "apps.sat.storages.PublicStorage",
    },
    "staticfiles": {
        "BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage",
    },
}

PRIVATE_MEDIA_STORAGE = "apps.sat.storages.PrivateStorage"


LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "simple": {
            "format": "{levelname} {message}",
            "style": "{",
        },
        "verbose": {
            "format": "{levelname} {asctime} {module} {message}",
            "style": "{",
        },
    },
    "handlers": {
        "console": {
            "class": "logging.StreamHandler",
            "formatter": "verbose" if not DEBUG else "simple",
        },
    },
    "root": {
        "handlers": ["console"],
        "level": "INFO",
    },
    "loggers": {
        "django": {
            "handlers": ["console"],
            "level": "INFO",
            "propagate": False,
        },
        "django.request": {
            "handlers": ["console"],
            "level": "ERROR",
            "propagate": False,
        },
        "apps": {
            "handlers": ["console"],
            "level": "INFO",
            "propagate": False,
        },
    },
}

LOGIN_URL = '/login/'
LOGIN_REDIRECT_URL = 'sat_menu'
LOGOUT_REDIRECT_URL = '/login/'
<<<<<<< HEAD

AUTHENTICATION_BACKENDS = [
    "django.contrib.auth.backends.ModelBackend",
    "allauth.account.auth_backends.AuthenticationBackend",
]

SITE_ID = int(os.getenv("SITE_ID", "1"))

LOGIN_URL = "/login/"
LOGIN_REDIRECT_URL = "/sat/"
ACCOUNT_LOGOUT_REDIRECT_URL = "/login/"

ACCOUNT_EMAIL_VERIFICATION = "none"
# ACCOUNT_EMAIL_REQUIRED = True
ACCOUNT_SIGNUP_FIELDS = ["email*", "username*", "password1*", "password2*"]

SOCIALACCOUNT_EMAIL_REQUIRED = True
SOCIALACCOUNT_EMAIL_VERIFICATION = "none"

GOOGLE_OAUTH_CLIENT_ID = os.getenv("GOOGLE_OAUTH_CLIENT_ID", "")
GOOGLE_OAUTH_CLIENT_SECRET = os.getenv("GOOGLE_OAUTH_CLIENT_SECRET", "")

SOCIALACCOUNT_PROVIDERS = {
    "google": {
        "VERIFIED_EMAIL": True,
        "EMAIL_AUTHENTICATION": True,
        "EMAIL_AUTHENTICATION_AUTO_CONNECT": True,
        "APPS": [
            {
                "client_id": GOOGLE_OAUTH_CLIENT_ID,
                "secret": GOOGLE_OAUTH_CLIENT_SECRET,
                "key": "",
                "settings": {
                    "scope": ["profile", "email"],
                    "auth_params": {"access_type": "online"},
                },
            }
        ],
        "OAUTH_PKCE_ENABLED": True,
    }
}

# Celery / Redis remain available for unrelated background tasks (for example video conversion).
# Structured Test Import does NOT enqueue Celery jobs and does not require Redis.
CELERY_BROKER_URL = os.getenv("CELERY_BROKER_URL", "redis://redis:6379/1")
CELERY_RESULT_BACKEND = os.getenv("CELERY_RESULT_BACKEND", "redis://redis:6379/2")
CELERY_TASK_TRACK_STARTED = True
CELERY_WORKER_PREFETCH_MULTIPLIER = 1
CELERY_BROKER_CONNECTION_RETRY_ON_STARTUP = True
CELERY_RESULT_EXPIRES = int(os.getenv("CELERY_RESULT_EXPIRES", "86400"))
CELERY_ACCEPT_CONTENT = ["json"]
CELERY_TASK_SERIALIZER = "json"
CELERY_RESULT_SERIALIZER = "json"
CELERY_TIMEZONE = TIME_ZONE

# AI is used for administrator/manager-run question-bank audits.
# Structured-PDF imports themselves are deterministic and do not require an AI provider.
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY", "")
DEEPSEEK_BASE_URL = os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com")

# Prefer DeepSeek automatically when its key is configured; set QUESTION_AUDIT_PROVIDER explicitly to override.
QUESTION_AUDIT_PROVIDER = os.getenv(
    "QUESTION_AUDIT_PROVIDER",
    "deepseek" if DEEPSEEK_API_KEY else "openai",
).strip().lower()
_default_question_audit_model = "deepseek-v4-flash" if QUESTION_AUDIT_PROVIDER == "deepseek" else "gpt-5.6-terra"
QUESTION_AUDIT_MODEL = os.getenv("QUESTION_AUDIT_MODEL", _default_question_audit_model).strip()
# Ignore stale model names when switching providers (for example an old gpt-* value in .env).
if QUESTION_AUDIT_PROVIDER == "deepseek" and not QUESTION_AUDIT_MODEL.startswith("deepseek-"):
    QUESTION_AUDIT_MODEL = "deepseek-v4-flash"
elif QUESTION_AUDIT_PROVIDER == "openai" and QUESTION_AUDIT_MODEL.startswith("deepseek-"):
    QUESTION_AUDIT_MODEL = "gpt-5.6-terra"
QUESTION_AUDIT_TIMEOUT_SECONDS = int(os.getenv("QUESTION_AUDIT_TIMEOUT_SECONDS", "90"))
QUESTION_AUDIT_BATCH_SIZE = max(1, min(30, int(os.getenv("QUESTION_AUDIT_BATCH_SIZE", "12"))))
QUESTION_AUDIT_MAX_TOKENS = max(1000, int(os.getenv("QUESTION_AUDIT_MAX_TOKENS", "12000")))
QUESTION_AUDIT_JSON_RETRIES = max(1, min(4, int(os.getenv("QUESTION_AUDIT_JSON_RETRIES", "2"))))
QUESTION_AUDIT_DEEPSEEK_THINKING = os.getenv("QUESTION_AUDIT_DEEPSEEK_THINKING", "0").strip().lower() in {"1", "true", "yes", "on"}
QUESTION_AUDIT_DEEPSEEK_REASONING_EFFORT = os.getenv("QUESTION_AUDIT_DEEPSEEK_REASONING_EFFORT", "low")

# Legacy arbitrary-PDF AI extraction remains OpenAI-only for old import records.
# New MakonBook Structured PDF v1/v2 imports never call TEST_IMPORT_MODEL.
TEST_IMPORT_MODEL = os.getenv("TEST_IMPORT_MODEL", "gpt-5.6-terra")
TEST_IMPORT_AUDIT_MODEL = os.getenv("TEST_IMPORT_AUDIT_MODEL", QUESTION_AUDIT_MODEL).strip()
if QUESTION_AUDIT_PROVIDER == "deepseek" and not TEST_IMPORT_AUDIT_MODEL.startswith("deepseek-"):
    TEST_IMPORT_AUDIT_MODEL = QUESTION_AUDIT_MODEL
elif QUESTION_AUDIT_PROVIDER == "openai" and TEST_IMPORT_AUDIT_MODEL.startswith("deepseek-"):
    TEST_IMPORT_AUDIT_MODEL = QUESTION_AUDIT_MODEL
TEST_IMPORT_TIMEOUT_SECONDS = int(os.getenv("TEST_IMPORT_TIMEOUT_SECONDS", "180"))
TEST_IMPORT_RUN_AI_AUDIT = os.getenv("TEST_IMPORT_RUN_AI_AUDIT", "1").strip().lower() not in {"0", "false", "no", "off"}  # CLI/legacy opt-in only; web import never auto-audits.
=======
>>>>>>> 8bac338a46e0ea29b051683a0812ace0f67efd8d
