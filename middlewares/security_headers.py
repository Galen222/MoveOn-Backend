# middlewares/security_headers.py

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from config import settings

class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        response = await call_next(request)

        if not settings.ENABLE_SECURITY_HEADERS:
            return response

        # Detectar HTTPS real (directo) o detrás de proxy
        is_https = request.url.scheme == "https"
        if settings.SEC_HEADERS_RESPECT_X_FORWARDED_PROTO:
            xf_proto = request.headers.get("x-forwarded-proto")
            if xf_proto:
                is_https = xf_proto.split(",")[0].strip().lower() == "https"

        # HSTS solo si HTTPS
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
    