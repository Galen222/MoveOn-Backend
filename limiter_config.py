# limiter_config.py

from __future__ import annotations

from ipaddress import ip_address, ip_network
from typing import Optional

from fastapi import Request
from slowapi import Limiter
from slowapi.util import get_remote_address

from config import settings


def _parse_csv(value: str) -> list[str]:
    if not value:
        return []
    return [x.strip() for x in value.split(",") if x.strip()]


def _compile_networks(cidrs_csv: str) -> list:
    nets = []
    for cidr in _parse_csv(cidrs_csv):
        try:
            nets.append(ip_network(cidr, strict=False))
        except Exception:
            # Si alguien mete un CIDR inválido en env, lo ignoramos (fail-soft)
            pass
    return nets


def _compile_ips(ips_csv: str) -> set[str]:
    out = set()
    for ip in _parse_csv(ips_csv):
        try:
            out.add(str(ip_address(ip)))
        except Exception:
            pass
    return out


LAN_NETS = _compile_networks(settings.TRUST_PROXY_LAN_CIDRS if settings.TRUST_PROXY_LAN else "")
WAN_NETS = _compile_networks(settings.TRUST_PROXY_WAN_CIDRS if settings.TRUST_PROXY_WAN else "")
WAN_IPS = _compile_ips(settings.TRUST_PROXY_WAN_IPS if settings.TRUST_PROXY_WAN else "")

HEADER_ORDER = [h.strip().lower() for h in _parse_csv(settings.TRUST_PROXY_HEADER_ORDER)]
if not HEADER_ORDER:
    HEADER_ORDER = ["x-forwarded-for", "x-real-ip"]


def _conn_from_trusted_proxy(request: Request) -> bool:
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
    for header in HEADER_ORDER:
        raw = request.headers.get(header)
        if not raw:
            continue

        if header == "x-forwarded-for":
            raw = raw.split(",")[0].strip()

        try:
            return str(ip_address(raw.strip()))
        except Exception:
            continue

    return None


def get_client_ip(request: Request) -> str:
    """
    Key func para SlowAPI.
    - Si NO estamos detrás de proxy confiable -> IP real del socket (get_remote_address)
    - Si SÍ -> usamos headers (XFF/X-Real-IP) según orden en env
    """
    if _conn_from_trusted_proxy(request):
        ip = _extract_ip_from_headers(request)
        if ip:
            return ip

    return get_remote_address(request)


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
