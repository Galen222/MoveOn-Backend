# services/identity_rate_limit.py

"""Implementa la lógica de negocio de este servicio."""

from __future__ import annotations

import time
import logging
from threading import RLock
from typing import Optional, Tuple

from cachetools import TTLCache

from config import settings

logger = logging.getLogger("app.security")


class IdentityRateLimitExceeded(Exception):
    """Representa identidad rate limit exceeded."""

    def __init__(self, mensaje: str = "Demasiadas peticiones. Inténtalo más tarde."):
        """Construye la excepción con el mensaje humano a devolver en el 429.

        El mensaje se guarda aparte de ``args`` para que el handler en
        ``main.py`` pueda leerlo directamente como ``exc.mensaje``.

        Args:
            mensaje: texto que el cliente verá en la respuesta 429.
        """
        super().__init__(mensaje)
        self.mensaje = mensaje


_MAX_BUCKETS = 10_000
_MAX_TTL_SECONDS = 24 * 3600

_BUCKETS: TTLCache[tuple[str, str], tuple[float, int]] = TTLCache(
    maxsize=_MAX_BUCKETS,
    ttl=_MAX_TTL_SECONDS,
    timer=time.time,  # clave para que cuadre con timestamps y tests
)

_BUCKETS_LOCK = RLock()


def _parse_limit(limit_str: str) -> Optional[Tuple[int, int]]:
    """Parsea una cadena de límite tipo ``5/minute`` a (tope, ventana_segundos).

    Acepta las unidades habituales de ``slowapi`` (``second``, ``minute``,
    ``hour``, ``day``, en singular o plural). Devuelve ``None`` ante
    entradas vacías, mal formadas o con un tope no positivo para que el
    llamador lo interprete como "sin límite".

    Args:
        limit_str: cadena con el formato ``"<N>/<unidad>"``.

    Returns:
        Tupla ``(N, ventana_en_segundos)`` o ``None`` si la cadena no es válida.
    """
    # Analiza limit.
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
    """Fuerza la expiración de entradas viejas de ``_BUCKETS``.

    ``TTLCache.expire`` sólo se dispara de forma perezosa en lecturas/
    escrituras, así que ``check_identity_limit`` lo llama antes de
    medir para que el conteo refleje siempre la ventana actual.

    Args:
        now: timestamp con el que comparar. Si es ``None``, usa el reloj interno de ``TTLCache``.
    """
    with _BUCKETS_LOCK:
        if now is None:
            _BUCKETS.expire()
        else:
            _BUCKETS.expire(now)


def check_identity_limit(scope: str, identity: str, limit_str: str) -> None:
    """Aplica rate-limit por identidad lógica (no por IP) y lanza si se supera.

    Agrupa por ``(scope, identidad)`` para que distintos scopes
    (``login``, ``registro``, ``password_solicitar``...) lleven cuentas
    independientes. La ``identidad`` se normaliza con ``.strip().lower()``
    para que ``User@X.com`` y ``user@x.com`` cuenten juntos.

    Toda la operación (leer bucket, resetear ventana si procede,
    incrementar, guardar, comprobar) ocurre dentro de un único
    ``RLock`` para que dos peticiones concurrentes no consigan evadir
    el tope.

    Si ``settings.ENABLE_RATE_LIMIT_ID`` es falso o ``limit_str`` no es
    parseable, la función no hace nada: así los entornos de dev y los
    tests pueden desactivarlo globalmente.

    Args:
        scope: categoría del rate limit (p. ej. ``"login"``, ``"registro"``).
        identity: identificador lógico (email, ``provider:sub``...); se normaliza.
        limit_str: cadena de límite, p. ej. ``"5/minute"``.

    Raises:
        IdentityRateLimitExceeded: si se supera el tope dentro de la ventana configurada.
    """
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

    # leer + reset de ventana + incrementar + persistir + validar
    # ocurre dentro de la misma sección crítica.
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
