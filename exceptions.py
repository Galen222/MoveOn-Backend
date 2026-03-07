"""
Módulo de Manejo de Excepciones Personalizadas.
"""

from typing import Any, Mapping
import logging
import re

from fastapi import HTTPException, Request, status
from fastapi.responses import JSONResponse


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
        "mensaje": mensaje,
    }

    if detail is not None:
        content["detail"] = detail

    return JSONResponse(
        status_code=status_code,
        content=content,
        headers=headers,
    )


def _limpiar_mensaje_validacion(error: dict[str, Any]) -> str:
    """
    Limpia el mensaje de validación manteniendo compatibilidad con la salida actual.

    Estrategia:
    - Si Pydantic V2 expone la excepción original en ctx["error"], la usamos.
      Esto evita depender de prefijos técnicos como "Value error, ".
    - Para el resto, mantenemos una limpieza conservadora del mensaje original.
    - No introducimos traducciones nuevas para no cambiar la salida actual.
    """
    tipo = error.get("type", "")
    ctx = error.get("ctx") or {}
    mensaje_original = str(error.get("msg", "") or "")

    # Caso ideal en Pydantic V2: recuperamos el ValueError/AssertionError original
    if tipo in ("value_error", "assertion_error"):
        ctx_error = ctx.get("error")
        if ctx_error:
            msg = str(ctx_error).strip()
            return (msg[:1].upper() + msg[1:]) if msg else msg

    # Compatibilidad con el comportamiento actual:
    # limpiar solo prefijos técnicos conocidos, sin reinterpretar el mensaje.
    msg = mensaje_original

    prefijos_a_limpiar = (
        "Value error, ",
        "Assertion failed, ",
    )
    for prefijo in prefijos_a_limpiar:
        if msg.startswith(prefijo):
            msg = msg[len(prefijo):]
            break

    # Conserva tu limpieza anterior por regex para casos residuales
    # sin tocar el significado del mensaje.
    msg = re.sub(r"^(Value error,\s*)", "", msg, flags=re.IGNORECASE).strip()

    # Capitalizar como hasta ahora
    return (msg[:1].upper() + msg[1:]) if msg else msg


def manejador_validacion_personalizado(request: Request, exc: Any) -> JSONResponse:
    """
    Intercepta errores de validación y los transforma al formato estándar que consume Android:
    {
      "estatus": "error",
      "mensaje": "Solicitud inválida",
      "detail": [
        {"columna": "...", "mensaje": "..."}
      ]
    }

    Mantiene compatibilidad:
    - claves: columna, mensaje
    - capitalización del mensaje
    - limpieza del prefijo técnico de Pydantic
    """
    errores_limpios: list[dict[str, Any]] = []

    if hasattr(exc, "errors"):
        for error in exc.errors():
            loc = error.get("loc") or []
            campo = loc[-1] if loc else "general"

            msg = _limpiar_mensaje_validacion(error)

            errores_limpios.append(
                {
                    "columna": str(campo),
                    "mensaje": msg,
                }
            )

    return error_response(
        status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
        mensaje="Solicitud inválida",
        detail=errores_limpios,
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
            headers=exc.headers,
        )

    if isinstance(exc.detail, list):
        return error_response(
            status_code=exc.status_code,
            mensaje="Solicitud inválida",
            detail=exc.detail,
            headers=exc.headers,
        )

    return error_response(
        status_code=exc.status_code,
        mensaje="Error en la solicitud",
        headers=exc.headers,
    )


def manejador_excepcion_no_controlada(request: Request, exc: Exception) -> JSONResponse:
    """
    Captura errores no controlados para no devolver respuestas inconsistentes.
    """
    logging.getLogger("app.error").exception(
        "unhandled_exception",
        extra={
            "method": request.method,
            "path": request.url.path,
        },
    )

    return error_response(
        status_code=500,
        mensaje="Ha ocurrido un error interno",
    )
    