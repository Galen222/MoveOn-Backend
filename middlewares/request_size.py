# middlewares/request_size.py

"""Implementa middleware relacionado con la aplicación."""

from __future__ import annotations

from starlette.types import ASGIApp, Message, Receive, Scope, Send

from exceptions import error_response


class RequestSizeLimitMiddleware:
    """
    Middleware ASGI puro para limitar el tamaño del cuerpo en rutas concretas.

    Diseño intencionado:
    - Se aplica solo a endpoints sensibles con bodies JSON pequeños.
    - No intenta sustituir al proxy reverso para límites globales.
    - No se aplica a subida de ficheros (/perfil/foto), porque esa ruta ya tiene
      validación específica de tamaño en file_service.

    Funcionamiento:
    - Si Content-Length supera el límite, responde 413 sin pasar al endpoint.
    - Si no hay Content-Length fiable, lee el cuerpo por chunks hasta el límite.
    - Si el cuerpo cabe en el límite, lo reinyecta al downstream tal cual.
    """

    def __init__(
        self,
        app: ASGIApp,
        route_limits: dict[tuple[str, str], int] | None = None,
        error_message: str = "El cuerpo de la solicitud supera el tamaño máximo permitido",
    ) -> None:
        """Inicializa la instancia."""
        self.app = app
        self.route_limits = {
            (method.upper(), path): int(limit)
            for (method, path), limit in (route_limits or {}).items()
            if int(limit) > 0
        }
        self.error_message = error_message

    def _build_413_response(self):
        """Construye la respuesta HTTP 413."""
        return error_response(
            status_code=413,
            mensaje=self.error_message,
            headers={
                "Cache-Control": "no-store",
                "Pragma": "no-cache",
            },
        )

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        """Procesa la llamada de la instancia."""
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        method = scope.get("method", "").upper()
        path = scope.get("path", "")
        limit = self.route_limits.get((method, path))

        if not limit:
            await self.app(scope, receive, send)
            return

        headers = {
            key.decode("latin-1").lower(): value.decode("latin-1")
            for key, value in scope.get("headers", [])
        }

        content_length = headers.get("content-length")
        if content_length:
            try:
                if int(content_length) > limit:
                    response = self._build_413_response()
                    await response(scope, receive, send)
                    return
            except ValueError:
                # Si la cabecera está mal formada, seguimos con validación streaming.
                pass

        body_chunks: list[Message] = []
        total = 0
        more_body = True

        while more_body:
            message = await receive()

            if message["type"] == "http.disconnect":
                body_chunks.append(message)
                break

            if message["type"] != "http.request":
                body_chunks.append(message)
                continue

            chunk = message.get("body", b"")
            total += len(chunk)

            if total > limit:
                response = self._build_413_response()
                await response(scope, receive, send)
                return

            body_chunks.append(message)
            more_body = bool(message.get("more_body", False))

        replay = _ReplayReceive(body_chunks)
        await self.app(scope, replay, send)


class _ReplayReceive:
    """Reinyecta aguas abajo los mensajes http.request ya leídos."""

    def __init__(self, messages: list[Message]) -> None:
        """Inicializa la instancia."""
        self._messages = list(messages)
        self._index = 0

    async def __call__(self) -> Message:
        """Procesa la llamada de la instancia."""
        if self._index < len(self._messages):
            message = self._messages[self._index]
            self._index += 1
            return message
        return {"type": "http.request", "body": b"", "more_body": False}
