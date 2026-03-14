# services/identity_rate_limit.py

from __future__ import annotations

import time
import logging
from threading import RLock
from typing import Optional, Tuple

from cachetools import TTLCache

from config import settings

logger = logging.getLogger("app.security")


class IdentityRateLimitExceeded(Exception):
    def __init__(self, mensaje: str = "Demasiadas peticiones. Inténtalo más tarde."):
        super().__init__(mensaje)
        self.mensaje = mensaje


_MAX_BUCKETS = 10_000
_MAX_TTL_SECONDS = 24 * 3600

_BUCKETS: TTLCache[tuple[str, str], tuple[float, int]] = TTLCache(
    maxsize=_MAX_BUCKETS,
    ttl=_MAX_TTL_SECONDS,
    timer=time.time,  # ← clave para que cuadre con tus timestamps y tests
)

_BUCKETS_LOCK = RLock()


def _parse_limit(limit_str: str) -> Optional[Tuple[int, int]]:
    s = (limit_str or "").strip()
    if not s:
        return None

    try:
        left, right = s.split("/", 1)
        n = int(left.strip())
        unit = right.strip().lower()
    except Exception:
        return None

    if n <= 0:
        return None

    if unit in ("second", "seconds"):
        return (n, 1)
    if unit in ("minute", "minutes"):
        return (n, 60)
    if unit in ("hour", "hours"):
        return (n, 3600)
    if unit in ("day", "days"):
        return (n, 86400)

    return None


def _purge_old(now: float | None = None) -> None:
    with _BUCKETS_LOCK:
        if now is None:
            _BUCKETS.expire()
        else:
            _BUCKETS.expire(now)


def check_identity_limit(scope: str, identity: str, limit_str: str) -> None:
    if not settings.ENABLE_RATE_LIMIT_ID:
        return

    parsed = _parse_limit(limit_str)
    if not parsed:
        return

    max_hits, window_seconds = parsed

    ident = (identity or "").strip().lower()
    if not ident:
        return

    now = time.time()
    key = (scope, ident)

    with _BUCKETS_LOCK:
        _purge_old(now)

        window_start, count = _BUCKETS.get(key, (now, 0))

        if now - window_start >= window_seconds:
            window_start, count = now, 0

        count += 1
        _BUCKETS[key] = (window_start, count)

    if count > max_hits:
        logger.warning(
            "limite_por_identidad_superado",
            extra={
                "scope": scope,
                "identidad": ident,
                "max_hits": max_hits,
                "window_seconds": window_seconds,
                "hits_actuales": count,
            },
        )
        raise IdentityRateLimitExceeded()
