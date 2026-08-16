import hashlib
import hmac
import logging
import time
from dataclasses import dataclass

from django.conf import settings
from django.core.cache import cache


logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class RateLimitResult:
    allowed: bool
    retry_after: int = 0
    scope: str = ""


def _digest(value: str) -> str:
    secret = (settings.SECRET_KEY or "makonbook").encode("utf-8", errors="ignore")
    return hmac.new(secret, value.encode("utf-8", errors="ignore"), hashlib.sha256).hexdigest()


def _client_ip(request) -> str:
    # nginx overwrites X-Real-IP with the actual peer address before proxying to
    # Django. Unlike trusting the first X-Forwarded-For value, this cannot be
    # bypassed merely by sending a forged X-Forwarded-For header.
    return (request.META.get("HTTP_X_REAL_IP") or request.META.get("REMOTE_ADDR") or "unknown").strip()[:128]


def _consume(scope: str, raw_key: str, *, limit: int, window_seconds: int) -> RateLimitResult:
    if not raw_key or limit <= 0 or window_seconds <= 0:
        return RateLimitResult(True)

    now = int(time.time())
    window_id = now // window_seconds
    retry_after = max(1, window_seconds - (now % window_seconds))
    key = f"registration:v42:{scope}:{window_id}:{_digest(f'{scope}:{raw_key}')}"

    try:
        # ``add`` initializes the key once. RedisCache's ``incr`` is atomic, so
        # all Gunicorn workers share the same counter in production. LocMemCache
        # remains a zero-setup development fallback.
        cache.add(key, 0, timeout=window_seconds + 5)
        hits = cache.incr(key)
    except Exception:
        # Registration should not take the entire site down if Redis is briefly
        # unavailable. Production monitoring should still surface this warning.
        logger.warning("Registration rate-limit backend unavailable; allowing request.", exc_info=True)
        return RateLimitResult(True)

    if hits > limit:
        return RateLimitResult(False, retry_after=retry_after, scope=scope)
    return RateLimitResult(True)


def check_registration_rate_limit(request, *, email: str = "", username: str = "") -> RateLimitResult:
    """Consume registration limits and return the first blocked scope.

    The IP limit is deliberately more tolerant than identifier limits because
    many MakonBook users may register from one school/NAT public address.
    """
    if not getattr(settings, "REGISTRATION_RATE_LIMIT_ENABLED", True):
        return RateLimitResult(True)

    checks = [
        (
            "ip",
            _client_ip(request),
            int(getattr(settings, "REGISTRATION_RATE_LIMIT_IP_MAX", 20)),
            int(getattr(settings, "REGISTRATION_RATE_LIMIT_IP_WINDOW_SECONDS", 600)),
        ),
        (
            "email",
            (email or "").strip().lower(),
            int(getattr(settings, "REGISTRATION_RATE_LIMIT_IDENTIFIER_MAX", 5)),
            int(getattr(settings, "REGISTRATION_RATE_LIMIT_IDENTIFIER_WINDOW_SECONDS", 1800)),
        ),
        (
            "username",
            (username or "").strip().lower(),
            int(getattr(settings, "REGISTRATION_RATE_LIMIT_IDENTIFIER_MAX", 5)),
            int(getattr(settings, "REGISTRATION_RATE_LIMIT_IDENTIFIER_WINDOW_SECONDS", 1800)),
        ),
    ]

    for scope, raw_key, limit, window_seconds in checks:
        result = _consume(scope, raw_key, limit=limit, window_seconds=window_seconds)
        if not result.allowed:
            return result

    return RateLimitResult(True)
