# ip_rate_limit.py

"""Módulo relacionado con IP rate limit."""

from __future__ import annotations

from ipaddress import ip_address, ip_network
from typing import Optional

from fastapi import Request
from slowapi import Limiter
from starlette.types import Scope

from config import settings
from utils.ip_cliente import (
    extract_ip_from_headers as _extract_ip_from_headers_common,
    get_client_ip as _get_client_ip_common,
    get_client_ip_from_scope as _get_client_ip_from_scope_common,
)


# Parsear listas CSV de configuración.
def _parse_csv(value: str) -> list[str]:
    """Analiza csv."""
    if not value:
        return []
    return [x.strip() for x in value.split(",") if x.strip()]


# Compilar rangos CIDR válidos desde env.
def _compile_networks(cidrs_csv: str) -> list:
    """Gestiona compile networks."""
    nets = []
    for cidr in _parse_csv(cidrs_csv):
        try:
            nets.append(ip_network(cidr, strict=False))
        except Exception:
            # Si alguien mete un CIDR inválido en env, lo ignoramos (fail-soft)
            pass
    return nets


# Compilar IPs sueltas válidas desde env.
def _compile_ips(ips_csv: str) -> set[str]:
    """Gestiona compile ips."""
    out = set()
    for ip in _parse_csv(ips_csv):
        try:
            out.add(str(ip_address(ip)))
        except Exception:
            pass
    return out


LAN_NETS = _compile_networks(
    settings.TRUST_PROXY_LAN_CIDRS if settings.TRUST_PROXY_LAN else ""
)
WAN_NETS = _compile_networks(
    settings.TRUST_PROXY_WAN_CIDRS if settings.TRUST_PROXY_WAN else ""
)
WAN_IPS = _compile_ips(settings.TRUST_PROXY_WAN_IPS if settings.TRUST_PROXY_WAN else "")

HEADER_ORDER = [
    h.strip().lower() for h in _parse_csv(settings.TRUST_PROXY_HEADER_ORDER)
]
if not HEADER_ORDER:
    HEADER_ORDER = ["x-forwarded-for", "x-real-ip"]


def conn_from_trusted_proxy(request: Request) -> bool:
    """
    Solo confiamos en X-Forwarded-For / X-Real-IP si la conexión TCP viene
    de un proxy que nosotros consideramos confiable (LAN o WAN).
    """
    client = request.client.host if request.client else None
    if not client:
        return False

    try:
        ip = ip_address(client)
    except Exception:
        return False

    # Proxy LAN
    if settings.TRUST_PROXY_LAN:
        for net in LAN_NETS:
            if ip in net:
                return True

    # Proxy WAN (IPs y/o rangos)
    if settings.TRUST_PROXY_WAN:
        if str(ip) in WAN_IPS:
            return True
        for net in WAN_NETS:
            if ip in net:
                return True

    return False


def _extract_ip_from_headers(request: Request) -> Optional[str]:
    """
    Extrae IP cliente desde headers en orden de prioridad.
    - X-Forwarded-For puede traer una lista "client, proxy1, proxy2"
      -> nos quedamos con el primer valor.
    """
    return _extract_ip_from_headers_common(request.headers, HEADER_ORDER)


def get_client_ip(request: Request) -> str:
    """
    Función de clave para SlowAPI.
    - Si NO estamos detrás de proxy confiable -> IP real del socket.
    - Si SÍ -> usamos headers (XFF/X-Real-IP) según orden en env.
    """
    return _get_client_ip_common(
        request,
        is_trusted_proxy=conn_from_trusted_proxy,
        header_order=HEADER_ORDER,
    )


def get_client_ip_from_scope(scope: Scope) -> str:
    """
    Variante para middlewares ASGI puros que solo disponen del scope.
    Reutiliza la misma lógica de resolución de IP que get_client_ip.
    """
    return _get_client_ip_from_scope_common(
        scope,
        is_trusted_proxy=conn_from_trusted_proxy,
        header_order=HEADER_ORDER,
    )


# Limiter global por IP.
limiter = Limiter(key_func=get_client_ip)


def rate_limit(limit_value: str):
    """
    Decorador para rate-limits configurables por env.
    Si ENABLE_RATE_LIMIT_IP=false -> no aplica límite.
    Si limit_value está vacío -> no aplica límite.
    """
    if not settings.ENABLE_RATE_LIMIT_IP:
        return lambda f: f

    lv = (limit_value or "").strip()
    if not lv:
        return lambda f: f

    return limiter.limit(lv)
