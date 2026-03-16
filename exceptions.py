"""Contrato centralizado de errores del backend.

Reglas:
- Los errores específicos deben nacer con ``error_code`` explícito.
- Los mensajes humanos no se usan para inferir códigos.
- Si un error llega sin código explícito, se usa el genérico por status.
"""

from __future__ import annotations

from typing import Any, Mapping
import logging
import re

from fastapi import HTTPException, Request, status
from fastapi.responses import JSONResponse

_GENERIC_ERROR_CODES_BY_STATUS: dict[int, str] = {
    status.HTTP_400_BAD_REQUEST: "BAD_REQUEST",
    status.HTTP_401_UNAUTHORIZED: "UNAUTHORIZED",
    status.HTTP_403_FORBIDDEN: "FORBIDDEN",
    status.HTTP_404_NOT_FOUND: "RESOURCE_NOT_FOUND",
    status.HTTP_413_CONTENT_TOO_LARGE: "PAYLOAD_TOO_LARGE",
    status.HTTP_422_UNPROCESSABLE_CONTENT: "VALIDATION_ERROR",
    status.HTTP_429_TOO_MANY_REQUESTS: "RATE_LIMIT_EXCEEDED",
    status.HTTP_500_INTERNAL_SERVER_ERROR: "INTERNAL_SERVER_ERROR",
    status.HTTP_503_SERVICE_UNAVAILABLE: "SERVICE_UNAVAILABLE",
}


def _normalize_error_code(error_code: str | None) -> str | None:
    if not isinstance(error_code, str) or not error_code.strip():
        return None
    normalized = re.sub(r"[^A-Za-z0-9]+", "_", error_code).strip("_")
    return normalized.upper() or None


class AppValidationError(ValueError):
    """ValueError con ``error_code`` explícito para validadores Pydantic."""

    def __init__(self, mensaje: str, error_code: str):
        super().__init__(mensaje)
        self.error_code = _normalize_error_code(error_code) or "VALIDATION_ERROR"


class AppHTTPException(HTTPException):
    """HTTPException con ``error_code`` explícito para rutas/servicios."""

    def __init__(
        self,
        *,
        status_code: int,
        mensaje: str,
        error_code: str,
        headers: Mapping[str, str] | None = None,
        detail: Any | None = None,
    ) -> None:
        super().__init__(
            status_code=status_code,
            detail=detail if detail is not None else mensaje,
            headers=headers,
        )
        self.error_code = _normalize_error_code(
            error_code
        ) or _GENERIC_ERROR_CODES_BY_STATUS.get(status_code, "UNKNOWN_ERROR")
        self.public_message = mensaje


def app_http_exception(
    *,
    status_code: int,
    mensaje: str,
    error_code: str,
    headers: Mapping[str, str] | None = None,
    detail: Any | None = None,
) -> AppHTTPException:
    return AppHTTPException(
        status_code=status_code,
        mensaje=mensaje,
        error_code=error_code,
        headers=headers,
        detail=detail,
    )


def _first_detail_error_code(detail: list[dict[str, Any]] | None) -> str | None:
    if not isinstance(detail, list):
        return None
    for item in detail:
        if isinstance(item, dict):
            code = _normalize_error_code(item.get("error_code"))
            if code:
                return code
    return None


def _normalize_detail(
    detail: list[dict[str, Any]] | None, default_error_code: str
) -> list[dict[str, Any]] | None:
    if detail is None:
        return None
    normalized: list[dict[str, Any]] = []
    for item in detail:
        if not isinstance(item, dict):
            normalized.append(item)
            continue
        cur = dict(item)
        cur["error_code"] = (
            _normalize_error_code(cur.get("error_code")) or default_error_code
        )
        normalized.append(cur)
    return normalized


def _resolve_error_code(
    status_code: int,
    explicit_error_code: str | None,
    detail: list[dict[str, Any]] | None = None,
) -> str:
    explicit = _normalize_error_code(explicit_error_code)
    if explicit:
        return explicit
    detail_code = _first_detail_error_code(detail)
    if detail_code:
        return detail_code
    return _GENERIC_ERROR_CODES_BY_STATUS.get(status_code, "UNKNOWN_ERROR")


def error_response(
    status_code: int,
    mensaje: str,
    detail: list[dict[str, Any]] | None = None,
    headers: Mapping[str, str] | None = None,
    error_code: str | None = None,
) -> JSONResponse:
    resolved = _resolve_error_code(status_code, error_code, detail)
    normalized_detail = _normalize_detail(detail, resolved)
    content: dict[str, Any] = {
        "estatus": "error",
        "mensaje": mensaje,
        "error_code": resolved,
    }
    if normalized_detail is not None:
        content["detail"] = normalized_detail
    return JSONResponse(status_code=status_code, content=content, headers=headers)


def _limpiar_mensaje_validacion(error: dict[str, Any]) -> str:
    tipo = error.get("type", "")
    ctx = error.get("ctx") or {}
    mensaje_original = str(error.get("msg", "") or "")
    if tipo in ("value_error", "assertion_error"):
        ctx_error = ctx.get("error")
        if ctx_error:
            msg = str(ctx_error).strip()
            return (msg[:1].upper() + msg[1:]) if msg else msg
    msg = mensaje_original
    for prefijo in ("Value error, ", "Assertion failed, "):
        if msg.startswith(prefijo):
            msg = msg[len(prefijo) :]
            break
    msg = re.sub(r"^(Value error,\s*)", "", msg, flags=re.IGNORECASE).strip()
    return (msg[:1].upper() + msg[1:]) if msg else msg


def manejador_validacion_personalizado(request: Request, exc: Any) -> JSONResponse:
    errores_limpios: list[dict[str, Any]] = []
    if hasattr(exc, "errors"):
        for error in exc.errors():
            loc = error.get("loc") or []
            campo = loc[-1] if loc else "general"
            msg = _limpiar_mensaje_validacion(error)
            raw_exc = (error.get("ctx") or {}).get("error")
            item_code = (
                _normalize_error_code(getattr(raw_exc, "error_code", None))
                or "VALIDATION_ERROR"
            )
            errores_limpios.append(
                {"columna": str(campo), "mensaje": msg, "error_code": item_code}
            )
    top_level = _first_detail_error_code(errores_limpios) or "VALIDATION_ERROR"
    return error_response(
        status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
        mensaje="Solicitud inválida",
        detail=errores_limpios,
        error_code=top_level,
    )


def manejador_http_exception(request: Request, exc: HTTPException) -> JSONResponse:
    explicit = _normalize_error_code(getattr(exc, "error_code", None))
    public_message = getattr(exc, "public_message", None)
    if isinstance(exc.detail, str):
        return error_response(
            status_code=exc.status_code,
            mensaje=public_message or exc.detail,
            headers=exc.headers,
            error_code=explicit,
        )
    if isinstance(exc.detail, list):
        return error_response(
            status_code=exc.status_code,
            mensaje=public_message or "Solicitud inválida",
            detail=exc.detail,
            headers=exc.headers,
            error_code=explicit,
        )
    if isinstance(exc.detail, dict):
        mensaje = (
            exc.detail.get("mensaje")
            or exc.detail.get("message")
            or exc.detail.get("error")
            or public_message
            or "Error en la solicitud"
        )
        detail = (
            exc.detail.get("detail")
            if isinstance(exc.detail.get("detail"), list)
            else None
        )
        error_code = _normalize_error_code(exc.detail.get("error_code")) or explicit
        return error_response(
            status_code=exc.status_code,
            mensaje=mensaje,
            detail=detail,
            headers=exc.headers,
            error_code=error_code,
        )
    return error_response(
        status_code=exc.status_code,
        mensaje=public_message or "Error en la solicitud",
        headers=exc.headers,
        error_code=explicit,
    )


def manejador_excepcion_no_controlada(request: Request, exc: Exception) -> JSONResponse:
    logging.getLogger("app.error").exception(
        "excepcion_no_controlada",
        extra={"method": request.method, "path": request.url.path},
    )
    return error_response(
        status_code=500,
        mensaje="Ha ocurrido un error interno",
        error_code="INTERNAL_SERVER_ERROR",
    )
