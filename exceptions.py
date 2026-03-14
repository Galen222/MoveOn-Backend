"""
Módulo de Manejo de Excepciones Personalizadas.
"""

from __future__ import annotations

from typing import Any, Mapping
import logging
import re
import unicodedata

from fastapi import HTTPException, Request, status
from fastapi.responses import JSONResponse

HTTP_422_UNPROCESSABLE = getattr(
    status,
    "HTTP_422_UNPROCESSABLE_CONTENT",
    status.HTTP_422_UNPROCESSABLE_CONTENT,
)

_GENERIC_ERROR_CODES_BY_STATUS: dict[int, str] = {
    status.HTTP_400_BAD_REQUEST: "BAD_REQUEST",
    status.HTTP_413_CONTENT_TOO_LARGE: "PAYLOAD_TOO_LARGE",
    HTTP_422_UNPROCESSABLE: "VALIDATION_ERROR",
    status.HTTP_429_TOO_MANY_REQUESTS: "RATE_LIMIT_EXCEEDED",
    status.HTTP_500_INTERNAL_SERVER_ERROR: "INTERNAL_SERVER_ERROR",
}

_MESSAGE_TO_ERROR_CODE: dict[str, str] = {
    "acepta_terminos debe ser booleano": "TERMS_ACCEPTANCE_MUST_BE_BOOLEAN",
    "Actividad no encontrada": "ACTIVITY_NOT_FOUND",
    "APP_SESSION_SECRET, ACCESS_TOKEN_SECRET, REFRESH_TOKEN_SECRET, REFRESH_HASH_SECRET y CODE_HASH_SECRET deben ser distintos entre sí": "SECRETS_MUST_BE_DISTINCT",
    "Error en la solicitud": "BAD_REQUEST",
    "Cloudinary no devolvió URL válida": "CLOUDINARY_INVALID_URL",
    "Código o email inválidos": "RECOVERY_CODE_OR_EMAIL_INVALID",
    "Contenido malicioso detectado": "MALICIOUS_CONTENT_DETECTED",
    "CORS_ORIGINS debe ser una lista o un string separado por comas": "CORS_ORIGINS_INVALID_FORMAT",
    "Credenciales no validas": "INVALID_CREDENTIALS",
    "Debes aceptar los términos para crear un usuario": "ACCOUNT_TERMS_ACCEPTANCE_REQUIRED",
    "Debes aceptar los Términos y la Política de Privacidad para registrarte": "REGISTRATION_CONSENTS_REQUIRED",
    "Debes tener al menos 18 años para registrarte": "AGE_RESTRICTION_NOT_MET",
    "El acceso no proviene de la aplicación MoveOn": "INVALID_APP_ORIGIN",
    "El archivo no es una imagen válida": "INVALID_IMAGE_FILE",
    "El código debe contener solo números": "CODE_MUST_BE_NUMERIC",
    "El código debe tener exactamente 6 caracteres": "CODE_INVALID_LENGTH",
    "El código es obligatorio": "CODE_REQUIRED",
    "El código ha expirado": "CODE_EXPIRED",
    "El código no puede estar vacío": "CODE_EMPTY",
    "El email debe ser un texto": "EMAIL_MUST_BE_TEXT",
    "El email es obligatorio": "EMAIL_REQUIRED",
    "El email no puede ser null": "EMAIL_NULL",
    "El email ya está en uso": "EMAIL_ALREADY_IN_USE",
    "El formato del correo electrónico no es válido": "EMAIL_FORMAT_INVALID",
    "El identificador es obligatorio": "IDENTIFIER_REQUIRED",
    "El identificador no puede estar vacío": "IDENTIFIER_EMPTY",
    "El nombre de usuario debe ser un texto": "USERNAME_MUST_BE_TEXT",
    "El nombre de usuario debe tener al menos 5 caracteres": "USERNAME_TOO_SHORT",
    "El nombre de usuario es obligatorio": "USERNAME_REQUIRED",
    "El nombre de usuario no puede estar vacío": "USERNAME_EMPTY",
    "El nombre de usuario no puede superar los 50 caracteres": "USERNAME_TOO_LONG",
    "El nombre de usuario o el email ya están en uso": "USERNAME_OR_EMAIL_ALREADY_IN_USE",
    "El nombre de usuario solo puede contener letras y números": "USERNAME_INVALID_FORMAT",
    "El nombre de usuario ya está en uso": "USERNAME_ALREADY_IN_USE",
    "El nombre no puede contener números ni símbolos especiales": "REAL_NAME_INVALID_CHARACTERS",
    "El nombre real debe ser un texto": "REAL_NAME_MUST_BE_TEXT",
    "El nombre real es demasiado corto": "REAL_NAME_TOO_SHORT",
    "El nombre real no puede superar los 80 caracteres": "REAL_NAME_TOO_LONG",
    "El objetivo mensual debe estar entre 10 y 2 000 000 metros": "MONTHLY_GOAL_OUT_OF_RANGE",
    "El objetivo mensual debe ser un número entero": "MONTHLY_GOAL_MUST_BE_INTEGER",
    "El objetivo mensual debe ser un número entero en metros": "MONTHLY_GOAL_MUST_BE_INTEGER_METERS",
    "El objetivo mensual no puede ser null": "MONTHLY_GOAL_NULL",
    "El objetivo semanal debe estar entre 10 y 2 000 000 metros": "WEEKLY_GOAL_OUT_OF_RANGE",
    "El objetivo semanal debe ser un número entero": "WEEKLY_GOAL_MUST_BE_INTEGER",
    "El objetivo semanal debe ser un número entero en metros": "WEEKLY_GOAL_MUST_BE_INTEGER_METERS",
    "El objetivo semanal no puede ser null": "WEEKLY_GOAL_NULL",
    "El peso debe estar entre 20kg y 300kg": "WEIGHT_OUT_OF_RANGE",
    "El peso debe ser un número en kilos": "WEIGHT_MUST_BE_KILOGRAM_NUMBER",
    "El refresh token es obligatorio": "REFRESH_TOKEN_REQUIRED",
    "El refresh token no puede estar vacío": "REFRESH_TOKEN_EMPTY",
    "El tipo de actividad es obligatorio": "ACTIVITY_TYPE_REQUIRED",
    "El total de calorías debe ser un número entero": "TOTAL_CALORIES_MUST_BE_INTEGER",
    "El total de calorías no puede ser negativo": "TOTAL_CALORIES_NEGATIVE",
    "El total de metros debe ser un número entero": "TOTAL_DISTANCE_MUST_BE_INTEGER",
    "El total de metros no puede ser negativo": "TOTAL_DISTANCE_NEGATIVE",
    "Este perfil es privado": "PROFILE_PRIVATE",
    "expira_en es obligatorio": "EXPIRES_AT_REQUIRED",
    "Falta el token de sesión": "SESSION_TOKEN_MISSING",
    "fecha_ruta debe ser una fecha-hora válida": "ROUTE_DATE_INVALID",
    "Ha ocurrido un error interno": "INTERNAL_SERVER_ERROR",
    "Imagen demasiado grande": "IMAGE_TOO_LARGE",
    "La altura debe estar entre 50cm y 300cm": "HEIGHT_OUT_OF_RANGE",
    "La altura debe ser un número entero en centímetros": "HEIGHT_MUST_BE_INTEGER_CENTIMETERS",
    "La contraseña debe incluir al menos un número": "PASSWORD_MISSING_NUMBER",
    "La contraseña debe incluir al menos una letra mayúscula": "PASSWORD_MISSING_UPPERCASE",
    "La contraseña debe tener al menos 8 caracteres": "PASSWORD_TOO_SHORT",
    "La contraseña es obligatoria": "PASSWORD_REQUIRED",
    "La contraseña no puede ser null": "PASSWORD_NULL",
    "La contraseña no puede superar los 72 bytes en UTF-8": "PASSWORD_TOO_LONG_BYTES",
    "La distancia debe ser mayor a 0": "DISTANCE_MUST_BE_POSITIVE",
    "La distancia debe ser un número entero": "DISTANCE_MUST_BE_INTEGER",
    "La distancia es obligatoria": "DISTANCE_REQUIRED",
    "La distancia parece incorrecta (máximo 300km)": "DISTANCE_OUT_OF_RANGE",
    "La duración debe ser mayor a 0": "DURATION_MUST_BE_POSITIVE",
    "La duración debe ser un número entero": "DURATION_MUST_BE_INTEGER",
    "La duración es obligatoria": "DURATION_REQUIRED",
    "La duración excede el límite de 24 horas": "DURATION_TOO_LONG",
    "La fecha de aceptación debe ser una fecha-hora válida": "TERMS_ACCEPTED_AT_INVALID_DATETIME",
    "La fecha de aceptación no puede ser futura": "TERMS_ACCEPTED_AT_IN_FUTURE",
    "La fecha de la actividad no puede ser en el futuro": "ACTIVITY_DATE_IN_FUTURE",
    "La fecha de nacimiento debe ser una fecha válida": "BIRTH_DATE_INVALID",
    "La fecha de nacimiento es obligatoria": "BIRTH_DATE_REQUIRED",
    "La fecha de nacimiento no puede ser en el futuro": "BIRTH_DATE_IN_FUTURE",
    "La fecha de nacimiento no puede ser null": "BIRTH_DATE_NULL",
    "La nueva contraseña es obligatoria": "NEW_PASSWORD_REQUIRED",
    "La polilínea debe ser un texto": "POLYLINE_MUST_BE_TEXT",
    "La ruta parece inválida": "ROUTE_INVALID",
    "La versión de los términos es obligatoria": "TERMS_VERSION_REQUIRED",
    "La versión de los términos no puede superar los 10 caracteres": "TERMS_VERSION_TOO_LONG",
    "La versión de términos debe ser un texto": "TERMS_VERSION_MUST_BE_TEXT",
    "Las calorías deben ser mayor a 0": "CALORIES_MUST_BE_POSITIVE",
    "Las calorías deben ser un número entero": "CALORIES_MUST_BE_INTEGER",
    "Las calorías parecen incorrectas (máximo 10.000)": "CALORIES_OUT_OF_RANGE",
    "Las calorías quemadas son obligatorias": "BURNED_CALORIES_REQUIRED",
    "No existe favicon.ico": "FAVICON_NOT_FOUND",
    "No se ha podido actualizar la foto de perfil": "PROFILE_PHOTO_UPDATE_FAILED",
    "No se ha podido guardar la imagen localmente": "IMAGE_SAVE_FAILED",
    "No se ha podido procesar la imagen": "IMAGE_PROCESSING_FAILED",
    "No se ha podido subir la imagen a la nube": "IMAGE_UPLOAD_FAILED",
    "No se pudo validar el contenido en este momento": "CONTENT_VALIDATION_UNAVAILABLE",
    "El archivo o los datos son demasiado grandes": "PAYLOAD_TOO_LARGE",
    "Perfil de usuario no encontrado": "USER_PROFILE_NOT_FOUND",
    "perfil_visible debe ser booleano": "PROFILE_VISIBILITY_MUST_BE_BOOLEAN",
    "perfil_visible no puede ser null": "PROFILE_VISIBILITY_NULL",
    "PUBLIC_BASE_URL debe empezar por http:// o https://": "PUBLIC_BASE_URL_INVALID_SCHEME",
    "PUBLIC_BASE_URL debe ser un string": "PUBLIC_BASE_URL_MUST_BE_STRING",
    "Demasiadas peticiones. Inténtalo más tarde.": "RATE_LIMIT_EXCEEDED",
    "Refresh token expirado": "REFRESH_TOKEN_EXPIRED",
    "Refresh token inválido": "REFRESH_TOKEN_INVALID",
    "Refresh token inválido (familia)": "REFRESH_TOKEN_INVALID_FAMILY",
    "Refresh token inválido (jti)": "REFRESH_TOKEN_INVALID_JTI",
    "Refresh token inválido o expirado": "REFRESH_TOKEN_INVALID_OR_EXPIRED",
    "Refresh token inválido o reutilizado": "REFRESH_TOKEN_INVALID_OR_REUSED",
    "Refresh token inválido (sub)": "REFRESH_TOKEN_INVALID_SUB",
    "Refresh token reutilizado": "REFRESH_TOKEN_REUSED",
    "Solo imágenes JPG o PNG": "IMAGE_FORMAT_NOT_ALLOWED",
    "Token de acceso inválido o expirado": "ACCESS_TOKEN_INVALID_OR_EXPIRED",
    "token_hash es obligatorio": "TOKEN_HASH_REQUIRED",
    "Token inválido o expirado": "TOKEN_INVALID_OR_EXPIRED",
    "Token no contiene un usuario válido": "TOKEN_MISSING_VALID_USER",
    "usuario_id debe ser mayor a 0": "USER_ID_MUST_BE_POSITIVE",
    "usuario_id debe ser un entero": "USER_ID_MUST_BE_INTEGER",
    "Usuario no encontrado": "USER_NOT_FOUND",
    "Solicitud inválida": "VALIDATION_ERROR",
    "recurso no encontrado": "RESOURCE_NOT_FOUND",
    "no autorizado": "UNAUTHORIZED",
    "token expirado": "TOKEN_EXPIRED",
}


def _quitar_prefijo_error(mensaje: str) -> str:
    mensaje = (mensaje or "").strip()
    if mensaje.lower().startswith("error: "):
        return mensaje[7:].strip()
    return mensaje


def _normalize_lookup_key(texto: str) -> str:
    base = _quitar_prefijo_error(texto)
    if not base:
        return ""

    normalizado = unicodedata.normalize("NFKC", base)
    normalizado = re.sub(r"\s+", " ", normalizado).strip()
    return normalizado.lower()


def _legacy_slug_error_code(texto: str) -> str:
    base = _quitar_prefijo_error(texto)
    if not base:
        return "UNKNOWN_ERROR"

    normalizado = unicodedata.normalize("NFKD", base)
    ascii_text = "".join(ch for ch in normalizado if not unicodedata.combining(ch))
    ascii_text = ascii_text.upper()
    ascii_text = re.sub(r"[^A-Z0-9]+", "_", ascii_text)
    ascii_text = re.sub(r"_+", "_", ascii_text).strip("_")
    return ascii_text or "UNKNOWN_ERROR"


def _semantic_error_code_from_message(texto: str | None) -> str | None:
    if not texto:
        return None

    key = _normalize_lookup_key(texto)
    if not key:
        return None

    if key in _MESSAGE_TO_ERROR_CODE:
        return _MESSAGE_TO_ERROR_CODE[key]

    return _legacy_slug_error_code(texto)


def _primer_mensaje_de_detail(detail: list[dict[str, Any]] | None) -> str | None:
    if not detail:
        return None

    for item in detail:
        if not isinstance(item, dict):
            continue
        for key in ("mensaje", "msg", "message", "error"):
            value = item.get(key)
            if isinstance(value, str) and value.strip():
                return value
    return None


def _normalize_explicit_error_code(error_code: str | None) -> str | None:
    if not error_code or not isinstance(error_code, str):
        return None

    normalized = re.sub(r"[^A-Za-z0-9]+", "_", error_code).strip("_")
    return normalized.upper() or None


def _normalizar_detail(
    detail: list[dict[str, Any]] | None,
) -> list[dict[str, Any]] | None:
    if detail is None:
        return None

    normalizado: list[dict[str, Any]] = []
    for item in detail:
        if not isinstance(item, dict):
            normalizado.append(item)
            continue

        nuevo = dict(item)
        if not nuevo.get("error_code"):
            mensaje = None
            for key in ("mensaje", "msg", "message", "error"):
                value = nuevo.get(key)
                if isinstance(value, str) and value.strip():
                    mensaje = value
                    break
            if mensaje:
                nuevo["error_code"] = _semantic_error_code_from_message(mensaje)
        else:
            nuevo["error_code"] = _normalize_explicit_error_code(
                nuevo.get("error_code")
            )
        normalizado.append(nuevo)
    return normalizado


def _inferir_error_code(
    status_code: int,
    mensaje: str,
    detail: list[dict[str, Any]] | None = None,
    explicit_error_code: str | None = None,
) -> str:
    explicit = _normalize_explicit_error_code(explicit_error_code)
    if explicit:
        return explicit

    if status_code in _GENERIC_ERROR_CODES_BY_STATUS:
        return _GENERIC_ERROR_CODES_BY_STATUS[status_code]

    primer_mensaje_detail = _primer_mensaje_de_detail(detail)
    if primer_mensaje_detail:
        code = _semantic_error_code_from_message(primer_mensaje_detail)
        if code:
            return code

    if mensaje:
        code = _semantic_error_code_from_message(mensaje)
        if code:
            return code

    return _GENERIC_ERROR_CODES_BY_STATUS.get(status_code, "UNKNOWN_ERROR")


def error_response(
    status_code: int,
    mensaje: str,
    detail: list[dict[str, Any]] | None = None,
    headers: Mapping[str, str] | None = None,
    error_code: str | None = None,
) -> JSONResponse:
    """
    Devuelve un JSON de error con formato estándar para Android.
    - Siempre incluye: estatus, mensaje, error_code
    - Solo incluye: detail, cuando exista
    - detail se normaliza añadiendo error_code por entrada cuando falta
    """
    detail_normalizado = _normalizar_detail(detail)
    resolved_error_code = _inferir_error_code(
        status_code=status_code,
        mensaje=mensaje,
        detail=detail_normalizado,
        explicit_error_code=error_code,
    )

    content: dict[str, Any] = {
        "estatus": "error",
        "mensaje": mensaje,
        "error_code": resolved_error_code,
    }

    if detail_normalizado is not None:
        content["detail"] = detail_normalizado

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

    if tipo in ("value_error", "assertion_error"):
        ctx_error = ctx.get("error")
        if ctx_error:
            msg = str(ctx_error).strip()
            return (msg[:1].upper() + msg[1:]) if msg else msg

    msg = mensaje_original

    prefijos_a_limpiar = (
        "Value error, ",
        "Assertion failed, ",
    )
    for prefijo in prefijos_a_limpiar:
        if msg.startswith(prefijo):
            msg = msg[len(prefijo) :]
            break

    msg = re.sub(r"^(Value error,\s*)", "", msg, flags=re.IGNORECASE).strip()
    return (msg[:1].upper() + msg[1:]) if msg else msg


def manejador_validacion_personalizado(request: Request, exc: Any) -> JSONResponse:
    """
    Intercepta errores de validación y los transforma al formato estándar que consume Android:
    {
      "estatus": "error",
      "mensaje": "Solicitud inválida",
      "error_code": "VALIDATION_ERROR",
      "detail": [
        {"columna": "...", "mensaje": "...", "error_code": "..."}
      ]
    }
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
                    "error_code": _semantic_error_code_from_message(msg),
                }
            )

    return error_response(
        status_code=HTTP_422_UNPROCESSABLE,
        mensaje="Solicitud inválida",
        detail=errores_limpios,
        error_code="VALIDATION_ERROR",
    )


def manejador_http_exception(request: Request, exc: HTTPException) -> JSONResponse:
    """
    Convierte cualquier HTTPException del backend al formato estándar:
    { estatus: "error", mensaje: "...", error_code: "..." }

    Además acepta detail dict estructurado para facilitar una migración gradual:
    {
      "mensaje": "...",
      "error_code": "...",
      "detail": [...]
    }
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
            error_code="VALIDATION_ERROR",
        )

    if isinstance(exc.detail, dict):
        mensaje = exc.detail.get("mensaje")
        if not isinstance(mensaje, str) or not mensaje.strip():
            mensaje = exc.detail.get("message")
        if not isinstance(mensaje, str) or not mensaje.strip():
            mensaje = exc.detail.get("error")
        if not isinstance(mensaje, str) or not mensaje.strip():
            mensaje = "Error en la solicitud"

        detail = exc.detail.get("detail")
        if not isinstance(detail, list):
            detail = None

        error_code = exc.detail.get("error_code")
        if not isinstance(error_code, str) or not error_code.strip():
            error_code = None

        return error_response(
            status_code=exc.status_code,
            mensaje=mensaje,
            detail=detail,
            headers=exc.headers,
            error_code=error_code,
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
        "excepcion_no_controlada",
        extra={
            "method": request.method,
            "path": request.url.path,
        },
    )

    return error_response(
        status_code=500,
        mensaje="Ha ocurrido un error interno",
        error_code="INTERNAL_SERVER_ERROR",
    )
