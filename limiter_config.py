# limiter_config.py

from __future__ import annotations

import ipaddress
from typing import Optional, List

from slowapi import Limiter
from slowapi.util import get_remote_address
from starlette.requests import Request

from config import settings


# Proxy LAN
TRUST_PROXY_LAN: bool = settings.TRUST_PROXY_LAN
# Proxy WAN
TRUST_PROXY_WAN: bool = settings.TRUST_PROXY_WAN

# Orden de prioridad de headers para extraer IP cliente
HEADER_ORDER = [
    h.strip().lower()
    for h in (settings.TRUST_PROXY_HEADER_ORDER or "x-forwarded-for,x-real-ip").split(",")
    if h.strip()
]


def _parse_cidrs(csv: str) -> List[ipaddress._BaseNetwork]:
    nets: List[ipaddress._BaseNetwork] = []
    for part in [p.strip() for p in csv.split(",") if p.strip()]:
        try:
            nets.append(ipaddress.ip_network(part, strict=False))
        except ValueError:
            continue
    return nets


def _ip_to_host_net(ip_str: str) -> Optional[ipaddress._BaseNetwork]:
    """Convierte una IP suelta a red host: v4 -> /32, v6 -> /128."""
    try:
        ip = ipaddress.ip_address(ip_str.strip())
    except ValueError:
        return None
    cidr = f"{ip}/{32 if ip.version == 4 else 128}"
    try:
        return ipaddress.ip_network(cidr, strict=False)
    except ValueError:
        return None


def _load_trusted_lan_nets() -> List[ipaddress._BaseNetwork]:
    # En config.py ya tienes defaults seguros, así que aquí solo parseamos
    return _parse_cidrs(settings.TRUST_PROXY_LAN_CIDRS or "")


def _load_trusted_wan_nets() -> List[ipaddress._BaseNetwork]:
    """
    Carga IP(s) públicas y/o CIDRs de proxy desde:
      - TRUST_PROXY_WAN_IPS (CSV de IPs sueltas)
      - TRUST_PROXY_WAN_CIDRS (CSV de CIDRs)
    Si no se configura nada, la lista queda vacía (seguro por defecto).
    """
    nets: List[ipaddress._BaseNetwork] = []

    ips = (settings.TRUST_PROXY_WAN_IPS or "").strip()
    if ips:
        for ip_str in [p.strip() for p in ips.split(",") if p.strip()]:
            net = _ip_to_host_net(ip_str)
            if net is not None:
                nets.append(net)

    cidrs = (settings.TRUST_PROXY_WAN_CIDRS or "").strip()
    if cidrs:
        nets.extend(_parse_cidrs(cidrs))

    return nets


_TRUSTED_LAN_NETS = _load_trusted_lan_nets()
_TRUSTED_WAN_NETS = _load_trusted_wan_nets()


def _is_trusted_proxy(peer_ip: str) -> bool:
    try:
        ip = ipaddress.ip_address(peer_ip)
    except ValueError:
        return False

    if TRUST_PROXY_LAN and any(ip in net for net in _TRUSTED_LAN_NETS):
        return True

    if TRUST_PROXY_WAN and any(ip in net for net in _TRUSTED_WAN_NETS):
        return True

    return False


def _first_valid_ip_from_xff(xff: str) -> Optional[str]:
    # X-Forwarded-For: "client, proxy1, proxy2"
    for candidate in [p.strip() for p in xff.split(",")]:
        if not candidate:
            continue
        try:
            ipaddress.ip_address(candidate)
            return candidate
        except ValueError:
            continue
    return None


def _extract_client_ip_from_headers(request: Request) -> Optional[str]:
    # Se respeta el orden configurado en TRUST_PROXY_HEADER_ORDER
    headers = request.headers

    for h in HEADER_ORDER:
        if h == "x-forwarded-for":
            xff = headers.get("x-forwarded-for")
            if xff:
                ip = _first_valid_ip_from_xff(xff)
                if ip:
                    return ip

        elif h == "x-real-ip":
            xri = headers.get("x-real-ip")
            if xri:
                xri = xri.strip()
                try:
                    ipaddress.ip_address(xri)
                    return xri
                except ValueError:
                    pass

        else:
            # Permite headers extra (p.ej. "cf-connecting-ip") sin tocar código:
            val = headers.get(h)
            if val:
                val = val.strip()
                try:
                    ipaddress.ip_address(val)
                    return val
                except ValueError:
                    pass

    return None


def get_client_ip(request: Request) -> str:
    """
    - Si TRUST_PROXY_LAN/WAN están desactivados -> comportamiento original (IP real socket)
    - Si están activados -> SOLO confiar en headers si la conexión viene de un proxy confiable
    """
    if not (TRUST_PROXY_LAN or TRUST_PROXY_WAN):
        return get_remote_address(request)

    peer = request.client.host if request.client else ""
    if peer and _is_trusted_proxy(peer):
        ip = _extract_client_ip_from_headers(request)
        if ip:
            return ip

    return get_remote_address(request)


limiter = Limiter(key_func=get_client_ip)
