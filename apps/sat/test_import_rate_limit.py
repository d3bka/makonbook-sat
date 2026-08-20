import hashlib
import hmac
import logging
import time
from dataclasses import dataclass

from django.conf import settings
from django.core.cache import cache


logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ImportSubmitLimit:
    allowed: bool
    retry_after: int = 0
    scope: str = ""


def _digest(value: str) -> str:
    secret = (settings.SECRET_KEY or "makonbook").encode("utf-8", errors="ignore")
    return hmac.new(secret, value.encode("utf-8", errors="ignore"), hashlib.sha256).hexdigest()


def _counter(scope: str, raw_key: str, *, limit: int, window_seconds: int) -> ImportSubmitLimit:
    if not raw_key or limit <= 0 or window_seconds <= 0:
        return ImportSubmitLimit(True)

    now = int(time.time())
    window_id = now // window_seconds
    retry_after = max(1, window_seconds - (now % window_seconds))
    key = f"test-import:v43:{scope}:{window_id}:{_digest(f'{scope}:{raw_key}')}"

    try:
        cache.add(key, 0, timeout=window_seconds + 5)
        hits = cache.incr(key)
    except Exception:
        logger.warning("Test-import rate-limit backend unavailable; allowing request.", exc_info=True)
        return ImportSubmitLimit(True)

    if hits > limit:
        return ImportSubmitLimit(False, retry_after=retry_after, scope=scope)
    return ImportSubmitLimit(True)


def check_test_import_submit_limit(request) -> ImportSubmitLimit:
    """Throttle expensive import creation after the upload form is valid.

    Two independent guards are used:
    * a short atomic cooldown blocks double-clicks/replayed POSTs;
    * a wider per-user window prevents repeated heavy upload/queue requests.

    The user is authenticated and is the most reliable identifier here, so we
    deliberately do not rely on spoofable forwarded-IP headers.
    """
    if not getattr(settings, "TEST_IMPORT_RATE_LIMIT_ENABLED", True):
        return ImportSubmitLimit(True)

    user_key = str(getattr(request.user, "pk", "") or "")
    if not user_key:
        return ImportSubmitLimit(False, retry_after=15, scope="user")

    cooldown = int(getattr(settings, "TEST_IMPORT_SUBMIT_COOLDOWN_SECONDS", 15))
    cooldown_key = f"test-import:v43:cooldown:{_digest(user_key)}"
    if cooldown > 0:
        try:
            if not cache.add(cooldown_key, 1, timeout=cooldown):
                return ImportSubmitLimit(False, retry_after=cooldown, scope="cooldown")
        except Exception:
            logger.warning("Test-import cooldown backend unavailable; continuing.", exc_info=True)

    return _counter(
        "user",
        user_key,
        limit=int(getattr(settings, "TEST_IMPORT_RATE_LIMIT_MAX", 6)),
        window_seconds=int(getattr(settings, "TEST_IMPORT_RATE_LIMIT_WINDOW_SECONDS", 600)),
    )
