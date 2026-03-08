# utils/client_ip.py

from __future__ import annotations

from ipaddress import ip_address
from typing import Callable, Mapping, Optional, Sequence

from fastapi import Request
from starlette.requests import Request as StarletteRequest
from starlette.types import Scope


# Tipo para el callback que decide si la conexión actual viene
# de un proxy que nosotros consideramos confiable.
TrustedProxyChecker = Callable[[Request], bool]



def get_socket_client_ip(request: Request) -> str:
    """
    Obtiene la IP del socket TCP asociada a la request.

    <p>Este helper es deliberadamente defensivo: si Starlette no puede aportar
    un objeto <code>request.client</code>, devuelve <code>"-"</code> en lugar
    de lanzar una excepción. Eso permite reutilizarlo en logs, rate limiting y
    middlewares sin tener que repetir ternarios en cada llamada.</p>

    @param request Request HTTP de FastAPI / Starlette.
    @return La IP del socket si existe; en caso contrario, <code>"-"</code>.
    """
    return request.client.host if request.client else "-"



def get_socket_client_ip_from_scope(scope: Scope) -> str:
    """
    Obtiene la IP del socket TCP a partir del <code>scope</code> ASGI.

    <p>Está pensada para middlewares ASGI puros, donde todavía no siempre
    interesa construir un objeto <code>Request</code> completo. Si el scope no
    trae cliente o el formato no es el esperado, devuelve <code>"-"</code>.</p>

    @param scope Scope ASGI de la conexión actual.
    @return La IP del socket si existe; en caso contrario, <code>"-"</code>.
    """
    client = scope.get("client")
    return client[0] if client else "-"



def extract_ip_from_headers(headers: Mapping[str, str], header_order: Sequence[str]) -> Optional[str]:
    """
    Extrae una IP cliente válida desde cabeceras HTTP en orden de prioridad.

    <p>El caso más habitual es <code>X-Forwarded-For</code>, que puede traer una
    lista como <code>"client, proxy1, proxy2"</code>. En ese caso se toma el
    primer valor, que es el cliente original. Si el valor no es una IP válida,
    se ignora y se prueba la siguiente cabecera configurada.</p>

    @param headers Cabeceras HTTP disponibles en la request.
    @param header_order Orden de prioridad de cabeceras a inspeccionar.
    @return La primera IP válida encontrada, o <code>None</code> si no hay ninguna.
    """
    for header in header_order:
        raw = headers.get(header)
        if not raw:
            continue

        if header == "x-forwarded-for":
            raw = raw.split(",")[0].strip()

        try:
            return str(ip_address(raw.strip()))
        except Exception:
            continue

    return None



def get_client_ip(
    request: Request,
    *,
    is_trusted_proxy: TrustedProxyChecker,
    header_order: Sequence[str],
) -> str:
    """
    Resuelve la IP cliente real de una request HTTP.

    <p>La estrategia es la siguiente:</p>
    <ol>
      <li>Si la conexión TCP no viene de un proxy confiable, se usa la IP del socket.</li>
      <li>Si sí viene de un proxy confiable, se intenta extraer la IP real desde
      las cabeceras configuradas.</li>
      <li>Si esas cabeceras faltan o son inválidas, se vuelve a la IP del socket
      como fallback seguro.</li>
    </ol>

    <p>La decisión de confianza del proxy se inyecta mediante callback para no
    acoplar esta utilidad a un módulo concreto como <code>ip_rate_limit.py</code>.</p>

    @param request Request HTTP de FastAPI / Starlette.
    @param is_trusted_proxy Función que decide si la conexión actual viene de un proxy confiable.
    @param header_order Orden de cabeceras a inspeccionar cuando hay proxy confiable.
    @return La IP cliente resuelta de forma segura.
    """
    if is_trusted_proxy(request):
        ip = extract_ip_from_headers(request.headers, header_order)
        if ip:
            return ip

    return get_socket_client_ip(request)



def get_client_ip_from_scope(
    scope: Scope,
    *,
    is_trusted_proxy: TrustedProxyChecker,
    header_order: Sequence[str],
) -> str:
    """
    Resuelve la IP cliente real a partir de un <code>scope</code> ASGI.

    <p>Este helper permite reutilizar exactamente la misma lógica de extracción
    de IP en middlewares ASGI puros, sin duplicar código entre infraestructura,
    rate limiting y handlers. Internamente intenta construir una
    <code>Request</code> de Starlette para reutilizar la lógica común; si eso
    falla por cualquier motivo, cae a la IP del socket.</p>

    @param scope Scope ASGI de la conexión actual.
    @param is_trusted_proxy Función que decide si la conexión actual viene de un proxy confiable.
    @param header_order Orden de cabeceras a inspeccionar cuando hay proxy confiable.
    @return La IP cliente resuelta de forma segura.
    """
    if scope.get("type") != "http":
        return "-"

    try:
        request = StarletteRequest(scope)
        return get_client_ip(
            request,
            is_trusted_proxy=is_trusted_proxy,
            header_order=header_order,
        )
    except Exception:
        return get_socket_client_ip_from_scope(scope)
