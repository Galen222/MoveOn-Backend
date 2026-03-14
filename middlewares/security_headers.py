# middlewares/security_headers.py

from starlette.requests import Request
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from config import settings
from ip_rate_limit import conn_from_trusted_proxy


class SecurityHeadersMiddleware:
    def __init__(self, app: ASGIApp):
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        request = Request(scope, receive=receive)

        async def send_wrapper(message: Message) -> None:
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

                # HSTS solo si la request original fue HTTPS
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
