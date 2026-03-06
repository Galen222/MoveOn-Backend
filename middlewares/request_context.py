# middlewares/request_context.py
import logging
import time
import uuid
from contextvars import ContextVar
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request

request_id_ctx: ContextVar[str] = ContextVar("request_id", default="-")

def get_request_id() -> str:
    return request_id_ctx.get()

class RequestContextMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        request_id = request.headers.get("x-request-id") or str(uuid.uuid4())
        token = request_id_ctx.set(request_id)
        start = time.perf_counter()

        try:
            response = await call_next(request)
        finally:
            duration_ms = round((time.perf_counter() - start) * 1000, 2)
            logging.getLogger("app.request").info(
                "request method=%s path=%s client=%s duration_ms=%s",
                request.method,
                request.url.path,
                request.client.host if request.client else "-",
                duration_ms,
            )
            request_id_ctx.reset(token)

        response.headers["X-Request-ID"] = request_id
        return response
    