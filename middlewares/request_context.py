# middlewares/request_context.py

import logging
import time
import uuid
from contextvars import ContextVar

from starlette.types import ASGIApp, Message, Receive, Scope, Send

from ip_rate_limit import HEADER_ORDER, conn_from_trusted_proxy
from utils.ip_cliente import get_client_ip_from_scope


request_id_ctx: ContextVar[str] = ContextVar("request_id", default="-")


# Obtener request_id actual para logging estructurado.
def get_request_id() -> str:
    return request_id_ctx.get()


class RequestContextMiddleware:
    def __init__(self, app: ASGIApp):
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
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
            nonlocal status_code

            if message["type"] == "http.response.start":
                status_code = int(message["status"])

                response_headers = list(message.get("headers", []))
                response_headers.append((b"x-request-id", request_id.encode("latin-1")))
                message = {**message, "headers": response_headers}

            if message["type"] == "http.response.body" and not message.get("more_body", False):
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
