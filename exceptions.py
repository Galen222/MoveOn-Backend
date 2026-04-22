# exceptions.py

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
    """Normaliza un ``error_code`` a la forma canónica ``MAYUSCULAS_CON_GUIONES_BAJOS``.

    Sustituye cualquier carácter no alfanumérico por ``_``, recorta los
    guiones bajos de los extremos y pasa el resultado a mayúsculas. Devuelve
    ``None`` si la entrada no es una cadena o queda vacía después de
    normalizar, lo que permite al llamador caer al genérico por status.

    Args:
        error_code: código tal como lo envió el servicio que levantó la excepción.

    Returns:
        Código en forma canónica, o ``None`` si la entrada no produce ninguno útil.
    """
    if not isinstance(error_code, str) or not error_code.strip():
        return None
    normalized = re.sub(r"[^A-Za-z0-9]+", "_", error_code).strip("_")
    return normalized.upper() or None


class AppValidationError(ValueError):
    """ValueError con ``error_code`` explícito para validadores Pydantic."""

    def __init__(self, mensaje: str, error_code: str):
        """Crea el error con el ``error_code`` ya normalizado.

        Si el código recibido no es válido tras normalizar, se cae al genérico
        ``VALIDATION_ERROR`` para que los validadores Pydantic siempre produzcan
        algún código útil.

        Args:
            mensaje: mensaje humano que se mostrará al usuario.
            error_code: código canónico del error; si no normaliza se usa ``VALIDATION_ERROR``.
        """
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
        """Construye la excepción HTTP añadiendo ``error_code`` y mensaje público.

        A diferencia del ``HTTPException`` estándar de FastAPI, esta variante
        guarda por separado:

        - ``error_code``: código canónico legible por máquina, útil para que el
          cliente Android reaccione programáticamente (p. ej. refrescar sesión).
        - ``public_message``: mensaje humano localizado, que es lo que el
          handler final devuelve al cliente independientemente de ``detail``.

        Si ``error_code`` no normaliza a nada, se asigna el genérico que
        corresponda al ``status_code`` según ``_GENERIC_ERROR_CODES_BY_STATUS``.

        Args:
            status_code: código HTTP a devolver.
            mensaje: mensaje humano para el usuario final.
            error_code: identificador canónico del error para que el cliente reaccione.
            headers: cabeceras adicionales a incluir en la respuesta.
            detail: cuerpo detallado opcional (p. ej. lista de errores por campo); si falta se usa ``mensaje``.
        """
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
    """Factoría de conveniencia para crear una ``AppHTTPException``.

    Existe para que los sitios que levantan el error no tengan que
    importar la clase directamente y mantener un estilo homogéneo
    en todo el código base.

    Args:
        status_code: código HTTP a devolver.
        mensaje: mensaje humano que verá el usuario final.
        error_code: identificador canónico del error para el cliente.
        headers: cabeceras opcionales que añadir a la respuesta.
        detail: cuerpo detallado opcional.

    Returns:
        Instancia lista para lanzar con ``raise``.
    """
    return AppHTTPException(
        status_code=status_code,
        mensaje=mensaje,
        error_code=error_code,
        headers=headers,
        detail=detail,
    )


def _first_detail_error_code(detail: list[dict[str, Any]] | None) -> str | None:
    """Extrae el primer ``error_code`` normalizado de una lista de detalles.

    Recorre los elementos de ``detail`` y devuelve el primer código
    válido que encuentre. Se usa como fuente secundaria cuando la
    excepción no trae ``error_code`` explícito pero alguno de los ítems
    de la validación por campo sí lo tiene.

    Args:
        detail: lista de diccionarios con detalles por campo, tal como la produce Pydantic.

    Returns:
        Primer código canónico encontrado, o ``None`` si no hay ninguno utilizable.
    """
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
    """Devuelve la lista de detalles con todos sus ``error_code`` normalizados.

    Los elementos que no son diccionarios se preservan tal cual (por si
    algún handler personalizado ya devuelve un tipo distinto). El resto
    se copia y se sustituye su ``error_code`` por la versión canónica
    (o por ``default_error_code`` si el original no normaliza).

    Args:
        detail: lista original tal como viene de la excepción.
        default_error_code: código a aplicar cuando un ítem no tenga uno normalizable.

    Returns:
        Lista nueva con los códigos normalizados, o ``None`` si la entrada era ``None``.
    """
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
    """Elige el ``error_code`` final usando una cadena de preferencia fija.

    El orden es: código explícito → primer código útil dentro de ``detail``
    → genérico asociado al ``status_code``. Centralizar esta lógica aquí
    asegura que todos los handlers respondan con la misma prioridad.

    Args:
        status_code: status HTTP que se va a devolver.
        explicit_error_code: código explícito pasado por el llamador, si lo hubiera.
        detail: lista opcional de detalles por campo donde buscar un código secundario.

    Returns:
        Código canónico que se incluirá en la respuesta JSON.
    """
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
    """Construye la ``JSONResponse`` de error con el formato estable del API.

    Este es el único punto que serializa errores hacia el cliente: siempre
    produce un objeto con ``estatus``, ``mensaje`` y ``error_code``, y añade
    ``detail`` cuando hay información por campo. Unificarlo aquí permite
    que el cliente Android parsee errores sin condicionales por endpoint.

    Args:
        status_code: código HTTP a devolver.
        mensaje: mensaje humano para el usuario final.
        detail: lista opcional de errores por campo.
        headers: cabeceras opcionales de la respuesta.
        error_code: código canónico explícito; si no se pasa se resuelve desde ``detail``/``status_code``.

    Returns:
        Respuesta JSON lista para devolver desde un handler de FastAPI.
    """
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
    """Limpia el mensaje de un error de validación de Pydantic para la UI.

    Pydantic prefija muchos mensajes con ``Value error,`` o
    ``Assertion failed,`` y, para errores custom, el mensaje útil vive en
    ``ctx['error']``. Esta función prioriza el contexto si existe, recorta
    los prefijos ruidosos y deja la primera letra en mayúscula.

    Args:
        error: item tal como lo devuelve ``ValidationError.errors()``.

    Returns:
        Mensaje limpio y presentable al usuario final.
    """
    # Normaliza mensaje validacion.
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
    """Handler global de ``RequestValidationError`` para FastAPI.

    Convierte la lista cruda de errores de Pydantic en el formato
    ``{columna, mensaje, error_code}`` por ítem que espera el cliente,
    elige un ``error_code`` top-level (el primero útil de la lista o
    ``VALIDATION_ERROR``) y responde 422 con ``error_response``.

    Args:
        request: petición entrante (no se usa, pero FastAPI la entrega siempre).
        exc: excepción de validación con el método ``.errors()``.

    Returns:
        Respuesta 422 con la lista de errores ya limpia y un ``error_code`` coherente.
    """
    # Gestiona manejador validacion personalizado.
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
    """Handler global de ``HTTPException`` que uniformiza el formato de salida.

    Materializa los distintos formatos que ``HTTPException.detail`` puede
    tener (str, list o dict) en la misma respuesta estándar del API,
    usando ``public_message`` si está disponible y cayendo al ``detail``
    crudo si no.

    Args:
        request: petición entrante (no se usa, pero FastAPI la entrega).
        exc: excepción HTTP levantada por cualquier endpoint o dependencia.

    Returns:
        Respuesta JSON con el mismo esquema que el resto de errores del API.
    """
    # Gestiona manejador HTTP exception.
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
    """Último recurso: convierte cualquier excepción no capturada en un 500.

    Registra el error completo en el logger ``app.error`` con ``exception``
    (incluye traceback) y devuelve un 500 con ``INTERNAL_SERVER_ERROR``
    sin filtrar detalles internos al cliente, para no exponer información
    sensible.

    Args:
        request: petición entrante; se registra su método y path en el log.
        exc: excepción no controlada capturada por FastAPI.

    Returns:
        Respuesta 500 genérica con mensaje público neutro.
    """
    logging.getLogger("app.error").exception(
        "excepcion_no_controlada",
        extra={"method": request.method, "path": request.url.path},
    )
    return error_response(
        status_code=500,
        mensaje="Ha ocurrido un error interno",
        error_code="INTERNAL_SERVER_ERROR",
    )
