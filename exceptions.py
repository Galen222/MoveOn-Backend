# exceptions.py

"""
Módulo de Manejo de Excepciones Personalizadas.
"""
from fastapi import Request, status, HTTPException
from fastapi.responses import JSONResponse
from typing import Any, Mapping
import re
import logging


def error_response(
    status_code: int,
    mensaje: str,
    detail: list[dict[str, Any]] | None = None,
    headers: Mapping[str, str] | None = None,
) -> JSONResponse:
    """
    Devuelve un JSON de error con formato estándar para Android.
    - Siempre incluye: estatus, mensaje
    - Solo incluye: detail, cuando exista
    """
    content: dict[str, Any] = {
        "estatus": "error",
        "mensaje": mensaje
    }

    if detail is not None:
        content["detail"] = detail

    return JSONResponse(
        status_code=status_code,
        content=content,
        headers=headers
    )


def manejador_validacion_personalizado(request: Request, exc: Any) -> JSONResponse:
    """
    Intercepta errores de validación y limpia los prefijos técnicos.
    Mantiene el formato 'detail' + 'columna/mensaje' que Android ya soporta.
    """
    errores_limpios: list[dict[str, Any]] = []

    if hasattr(exc, "errors"):
        for error in exc.errors():
            mensaje_original = error.get("msg", "")
            mensaje_limpio = re.sub(
                r"^(Value error,\s*|Assertion failed,\s*|Input should be.*,\s*)",
                "",
                mensaje_original
            )

            loc = error.get("loc") or []
            campo = loc[-1] if loc else "general"
            msg = mensaje_limpio.strip()
            msg = (msg[:1].upper() + msg[1:]) if msg else msg

            errores_limpios.append({
                "columna": campo,
                "mensaje": msg
            })

    return error_response(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        mensaje="Solicitud inválida",
        detail=errores_limpios
    )


def manejador_http_exception(request: Request, exc: HTTPException) -> JSONResponse:
    """
    Convierte cualquier HTTPException del backend al formato estándar:
    { estatus: "error", mensaje: "..." }
    """
    if isinstance(exc.detail, str):
        return error_response(
            status_code=exc.status_code,
            mensaje=exc.detail,
            headers=exc.headers
        )

    if isinstance(exc.detail, list):
        return error_response(
            status_code=exc.status_code,
            mensaje="Solicitud inválida",
            detail=exc.detail,
            headers=exc.headers
        )

    return error_response(
        status_code=exc.status_code,
        mensaje="Error en la solicitud",
        headers=exc.headers
    )


def manejador_excepcion_no_controlada(request: Request, exc: Exception) -> JSONResponse:
    """
    Captura errores no controlados para no devolver respuestas inconsistentes.
    """
    logging.getLogger("app.error").exception(
        "unhandled_exception method=%s path=%s",
        request.method,
        request.url.path,
    )

    return error_response(
        status_code=500,
        mensaje="Ha ocurrido un error interno"
    )
    