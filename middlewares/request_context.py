# middlewares/request_context.py

"""Implementa middleware relacionado con la aplicación."""

import logging
import time
import uuid
from contextvars import ContextVar

from starlette.types import ASGIApp, Message, Receive, Scope, Send

from ip_rate_limit import HEADER_ORDER, conn_from_trusted_proxy
from utils.ip_cliente import get_client_ip_from_scope

request_id_ctx: ContextVar[str] = ContextVar("request_id", default="-")


# Obtener petición_id actual para logging estructurado.
def get_request_id() -> str:
    """Devuelve el ``request_id`` de la petición actual desde el ``contextvar``.

    Fuera de una petición (arranque, tareas de fondo) devuelve ``"-"`` en
    lugar de lanzar excepción, para que los logs de arranque no rompan.

    Returns:
        UUID del request en curso, o ``"-"`` si no hay petición activa.
    """
    return request_id_ctx.get()


class RequestContextMiddleware:
    """Middleware para request context."""

    def __init__(self, app: ASGIApp):
        """Guarda la app ASGI aguas abajo para poder invocarla en ``__call__``.

        Args:
            app: siguiente aplicación ASGI en la cadena.
        """
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        """Asigna un ``request_id`` a cada petición y registra su resultado.

        Flujo:

        1. Para peticiones no HTTP (websockets, lifespan), delega sin tocar.
        2. Toma el ``x-request-id`` del cliente si viene, o genera un UUID.
        3. Publica ese id en ``request_id_ctx`` para que el logger lo use.
        4. Envuelve ``send`` para inyectar el mismo id en la cabecera de
           respuesta y emitir un log ``peticion_completada`` al terminar
           el último chunk, con ``status_code`` y duración real.
        5. Si la app aguas abajo lanza, registra ``peticion_fallida`` con
           traceback y re-lanza para que los handlers de FastAPI respondan.

        Args:
            scope: contexto ASGI de la conexión.
            receive: callable ASGI para recibir mensajes del cliente.
            send: callable ASGI para enviar mensajes al cliente.
        """
        # Procesa la llamada de la instancia.
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        headers = {
            key.decode("latin-1").lower(): value.decode("latin-1")
            for key, value in scope.get("headers", [])
        }

        request_id = headers.get("x-request-id") or str(uuid.uuid4())
        token = request_id_ctx.set(request_id)
        start = time.perf_counter()

        client_ip = get_client_ip_from_scope(
            scope,
            is_trusted_proxy=conn_from_trusted_proxy,
            header_order=HEADER_ORDER,
        )
        method = scope.get("method", "-")
        path = scope.get("path", "-")
        logger = logging.getLogger("app.request")

        status_code = 500

        async def send_wrapper(message: Message) -> None:
            """Intercepta los mensajes ``send`` para anotar cabecera y log final.

            En ``http.response.start`` añade la cabecera ``x-request-id`` con
            el id actual (útil para que el cliente correlacione errores). En
            ``http.response.body`` con ``more_body=False`` emite el log
            ``peticion_completada`` con ``status_code`` y ``duration_ms``.

            Args:
                message: mensaje ASGI emitido por la app aguas abajo.
            """
            # Envía wrapper.
            nonlocal status_code

            if message["type"] == "http.response.start":
                status_code = int(message["status"])

                response_headers = list(message.get("headers", []))
                response_headers.append((b"x-request-id", request_id.encode("latin-1")))
                message = {**message, "headers": response_headers}

            if message["type"] == "http.response.body" and not message.get(
                "more_body", False
            ):
                duration_ms = round((time.perf_counter() - start) * 1000)

                logger.info(
                    "peticion_completada",
                    extra={
                        "request_id": request_id,
                        "client_ip": client_ip,
                        "method": method,
                        "path": path,
                        "status_code": status_code,
                        "duration_ms": duration_ms,
                    },
                )

            await send(message)

        try:
            await self.app(scope, receive, send_wrapper)
        except Exception:
            duration_ms = round((time.perf_counter() - start) * 1000)

            logger.exception(
                "peticion_fallida",
                extra={
                    "request_id": request_id,
                    "client_ip": client_ip,
                    "method": method,
                    "path": path,
                    "status_code": 500,
                    "duration_ms": duration_ms,
                },
            )
            raise
        finally:
            request_id_ctx.reset(token)
