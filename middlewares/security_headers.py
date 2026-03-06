# middlewares/security_headers.py

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from config import settings
from ip_rate_limit import conn_from_trusted_proxy

class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        response = await call_next(request)

        if not settings.ENABLE_SECURITY_HEADERS:
            return response

        # HTTPS directo
        is_https = request.url.scheme == "https"

        # Solo confiar en X-Forwarded-Proto si la conexión viene
        # de un proxy que nosotros consideramos confiable
        if settings.SEC_HEADERS_RESPECT_X_FORWARDED_PROTO and conn_from_trusted_proxy(request):
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
            response.headers["Strict-Transport-Security"] = hsts

        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = settings.SEC_HEADERS_X_FRAME_OPTIONS
        response.headers["Referrer-Policy"] = settings.SEC_HEADERS_REFERRER_POLICY
        response.headers["Permissions-Policy"] = settings.SEC_HEADERS_PERMISSIONS_POLICY

        if settings.SEC_HEADERS_CONTENT_SECURITY_POLICY:
            response.headers["Content-Security-Policy"] = settings.SEC_HEADERS_CONTENT_SECURITY_POLICY

        return response
    