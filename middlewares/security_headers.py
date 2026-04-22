# middlewares/security_headers.py

"""Implementa middleware relacionado con la aplicación."""

from starlette.requests import Request
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from config import settings
from ip_rate_limit import conn_from_trusted_proxy


class SecurityHeadersMiddleware:
    """Middleware para security headers."""

    def __init__(self, app: ASGIApp):
        """Guarda la app ASGI aguas abajo para inyectar cabeceras en su salida.

        Args:
            app: siguiente aplicación ASGI en la cadena.
        """
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        """Inyecta cabeceras de seguridad estándar en cada respuesta HTTP.

        Para peticiones no HTTP pasa sin tocar. Para HTTP envuelve ``send``
        para añadir HSTS (solo si la petición fue HTTPS, respetando
        ``X-Forwarded-Proto`` únicamente si viene de un proxy confiable),
        ``X-Content-Type-Options``, ``X-Frame-Options``, ``Referrer-Policy``,
        ``Permissions-Policy`` y opcionalmente ``Content-Security-Policy``.
        Los valores concretos vienen de ``settings.SEC_HEADERS_*``.

        Args:
            scope: contexto ASGI de la conexión.
            receive: callable ASGI para recibir mensajes del cliente.
            send: callable ASGI para enviar mensajes al cliente.
        """
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        request = Request(scope, receive=receive)

        async def send_wrapper(message: Message) -> None:
            """Intercepta ``http.response.start`` para añadir las cabeceras.

            Solo modifica mensajes de inicio de respuesta; el resto pasan sin
            tocar. Respeta ``settings.ENABLE_SECURITY_HEADERS`` como toggle
            global, aunque en la práctica el middleware no se monta si está
            deshabilitado.

            Args:
                message: mensaje ASGI emitido por la app aguas abajo.
            """
            if (
                message["type"] == "http.response.start"
                and settings.ENABLE_SECURITY_HEADERS
            ):
                response_headers = list(message.get("headers", []))

                # HTTPS directo
                is_https = request.url.scheme == "https"

                # Solo confiar en X-Forwarded-Proto si la conexión viene
                # de un proxy que nosotros consideramos confiable
                if (
                    settings.SEC_HEADERS_RESPECT_X_FORWARDED_PROTO
                    and conn_from_trusted_proxy(request)
                ):
                    xf_proto = request.headers.get("x-forwarded-proto")
                    if xf_proto:
                        is_https = xf_proto.split(",")[0].strip().lower() == "https"

                # HSTS solo si la petición original fue HTTPS
                if is_https and settings.SEC_HEADERS_HSTS_SECONDS > 0:
                    hsts = f"max-age={int(settings.SEC_HEADERS_HSTS_SECONDS)}"
                    if settings.SEC_HEADERS_HSTS_INCLUDE_SUBDOMAINS:
                        hsts += "; includeSubDomains"
                    if settings.SEC_HEADERS_HSTS_PRELOAD:
                        hsts += "; preload"
                    response_headers.append(
                        (b"strict-transport-security", hsts.encode("latin-1"))
                    )

                response_headers.append((b"x-content-type-options", b"nosniff"))
                response_headers.append(
                    (
                        b"x-frame-options",
                        str(settings.SEC_HEADERS_X_FRAME_OPTIONS).encode("latin-1"),
                    )
                )
                response_headers.append(
                    (
                        b"referrer-policy",
                        str(settings.SEC_HEADERS_REFERRER_POLICY).encode("latin-1"),
                    )
                )
                response_headers.append(
                    (
                        b"permissions-policy",
                        str(settings.SEC_HEADERS_PERMISSIONS_POLICY).encode("latin-1"),
                    )
                )

                if settings.SEC_HEADERS_CONTENT_SECURITY_POLICY:
                    response_headers.append(
                        (
                            b"content-security-policy",
                            str(settings.SEC_HEADERS_CONTENT_SECURITY_POLICY).encode(
                                "latin-1"
                            ),
                        )
                    )

                message = {**message, "headers": response_headers}

            await send(message)

        await self.app(scope, receive, send_wrapper)
