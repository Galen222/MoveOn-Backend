# services/identity_rate_limit.py

"""
Rate limit in-memory por identidad (identificador/email).
- Útil para frenar ataques distribuidos (botnet) donde el rate-limit por IP no basta.
- No requiere Redis (asumes 1 instancia del proceso).
- Se configura por env con strings tipo: "10/minute", "5/hour".
- Lanza una excepción propia y main.py la transforma a RespuestaGenerica.
"""

from __future__ import annotations

import time
from typing import Optional, Tuple

from config import settings


class IdentityRateLimitExceeded(Exception):
    """
    Excepción propia para el rate limit por identidad.

    La capturamos en main.py con app.exception_handler(...) para devolver un JSON
    con el mismo formato que RespuestaGenerica:
      {"estatus": "error", "mensaje": "..."}
    """
    def __init__(self, mensaje: str = "Demasiadas peticiones. Inténtalo más tarde."):
        super().__init__(mensaje)
        self.mensaje = mensaje


# (scope, identity) -> (window_start_epoch, count)
_BUCKETS: dict[tuple[str, str], tuple[float, int]] = {}


def _parse_limit(limit_str: str) -> Optional[Tuple[int, int]]:
    """
    Convierte "10/minute" -> (10, 60)
    Soporta: second(s), minute(s), hour(s), day(s)
    """
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


def _purge_old(now: float, max_age_seconds: int = 24 * 3600) -> None:
    """
    Purga sencilla para que el dict no crezca indefinidamente.
    Borra buckets que no se han usado en mucho tiempo.

    Nota: iteramos sobre list(_BUCKETS.keys()) para evitar:
      RuntimeError: dictionary changed size during iteration
    """
    if len(_BUCKETS) < 10_000:
        return

    cutoff = now - max_age_seconds
    keys_to_delete = []
    for k in list(_BUCKETS.keys()):
        val = _BUCKETS.get(k)
        if val and val[0] < cutoff:
            keys_to_delete.append(k)

    for k in keys_to_delete:
        _BUCKETS.pop(k, None)


def check_identity_limit(scope: str, identity: str, limit_str: str) -> None:
    """
    Aplica rate limit por identidad.

    - Si se excede el límite -> lanza IdentityRateLimitExceeded (429)
      que main.py transforma a JSON RespuestaGenerica.
    - Si no aplica (desactivado / inválido / sin identidad) -> no hace nada.
    """
    # Feature-flag por env
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
    _purge_old(now)

    key = (scope, ident)
    window_start, count = _BUCKETS.get(key, (now, 0))

    # Ventana nueva
    if now - window_start >= window_seconds:
        window_start, count = now, 0

    count += 1
    _BUCKETS[key] = (window_start, count)

    if count > max_hits:
        # IMPORTANTe:
        # No devolvemos JSONResponse aquí (rompería response_model),
        # sino que lanzamos una excepción capturada por main.py.
        raise IdentityRateLimitExceeded()