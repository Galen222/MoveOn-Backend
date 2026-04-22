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
        """Precompila el diccionario de límites a claves ``(METHOD_UPPER, path)``.

        Las entradas con límite no positivo se descartan para no introducir
        comprobaciones inútiles, y los métodos se normalizan a mayúsculas
        de una vez para evitar hacerlo en cada petición.

        Args:
            app: siguiente aplicación ASGI en la cadena.
            route_limits: diccionario ``{(método, path): límite_en_bytes}``; entradas con límite <= 0 se ignoran.
            error_message: mensaje humano devuelto en el 413 cuando se supera el límite.
        """
        self.app = app
        self.route_limits = {
            (method.upper(), path): int(limit)
            for (method, path), limit in (route_limits or {}).items()
            if int(limit) > 0
        }
        self.error_message = error_message

    def _build_413_response(self):
        """Construye la respuesta 413 común a todos los caminos de corte.

        La extrae a método para que el mensaje y las cabeceras (``no-store``
        siempre, para que proxies no cacheen un 413 transitorio) estén
        centralizados.

        Returns:
            ``JSONResponse`` 413 con el esquema estándar del API y cabeceras anti-caché.
        """
        return error_response(
            status_code=413,
            mensaje=self.error_message,
            headers={
                "Cache-Control": "no-store",
                "Pragma": "no-cache",
            },
        )

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        """Aplica el límite de tamaño del cuerpo para la ruta concreta en curso.

        Algoritmo:

        1. Si la petición no es HTTP o la ruta no está en ``route_limits``,
           pasa sin inspeccionar (ni siquiera lee el cuerpo).
        2. Si hay ``Content-Length`` fiable, responde 413 directamente sin
           leer el cuerpo cuando excede el límite.
        3. Si no hay ``Content-Length`` o está mal formado, lee chunks del
           cuerpo hasta el límite y responde 413 en cuanto el total lo pase.
        4. Si el cuerpo entra por debajo del límite, reinyecta los mensajes
           ya leídos al endpoint mediante ``_ReplayReceive`` para que la
           ruta los vea tal cual habrían llegado.

        Args:
            scope: contexto ASGI de la conexión.
            receive: callable ASGI para recibir mensajes del cliente.
            send: callable ASGI para enviar mensajes al cliente.
        """
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
        """Guarda una copia de los mensajes ya leídos para poder reemitirlos.

        Se copia con ``list(messages)`` para que un mutado posterior de la
        lista original no afecte al replay (invariante: el replay entrega
        siempre la misma secuencia que validó el middleware).

        Args:
            messages: mensajes ASGI ``http.request`` leídos del cliente.
        """
        self._messages = list(messages)
        self._index = 0

    async def __call__(self) -> Message:
        """Entrega el siguiente mensaje ya leído, o un EOF si ya se agotaron.

        El EOF (``more_body=False``) con body vacío es necesario para que
        la app aguas abajo sepa que no quedan más chunks por leer.

        Returns:
            Siguiente mensaje ASGI en la secuencia, o un mensaje de cierre con cuerpo vacío.
        """
        if self._index < len(self._messages):
            message = self._messages[self._index]
            self._index += 1
            return message
        return {"type": "http.request", "body": b"", "more_body": False}
