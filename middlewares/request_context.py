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
        except Exception:
            duration_ms = round((time.perf_counter() - start) * 1000)
            logging.getLogger("app.request").exception(
                '%s - "%s %s HTTP/1.1" %s %s ms',
                request.client.host if request.client else "-",
                request.method,
                request.url.path,
                500,
                duration_ms,
            )
            request_id_ctx.reset(token)
            raise

        duration_ms = round((time.perf_counter() - start) * 1000)

        logging.getLogger("app.request").info(
            '%s - "%s %s HTTP/1.1" %s %s ms',
            request.client.host if request.client else "-",
            request.method,
            request.url.path,
            response.status_code,
            duration_ms,
        )

        response.headers["X-Request-ID"] = request_id
        request_id_ctx.reset(token)
        return response
    