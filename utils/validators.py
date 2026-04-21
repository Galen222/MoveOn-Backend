# utils/validators.py

"""Incluye utilidades auxiliares de la aplicación."""

import re
from datetime import date, datetime, timedelta, timezone
from typing import Any

from exceptions import AppValidationError


def interceptar_error_pydantic(
    valor: Any, handler, error_code: str, mensaje_error: str
):
    """
    Ejecuta el validador por defecto de Pydantic (handler).
    Si falla, lanza un AppValidationError con mensaje limpio y error_code explícito.
    """
    try:
        return handler(valor)
    except Exception:
        raise AppValidationError(mensaje_error, error_code)


# Funciones de lógica de validación


def validar_nombre_real_logica(v: str) -> str:
    """Regla para el nombre real: longitud y símbolos."""
    if len(v) < 3:
        raise AppValidationError(
            "Error: El nombre real es demasiado corto", "REAL_NAME_TOO_SHORT"
        )

    # Límite superior para evitar carga útils absurdamente grandes
    if len(v) > 80:
        raise AppValidationError(
            "Error: El nombre real no puede superar los 80 caracteres",
            "REAL_NAME_TOO_LONG",
        )

    # Solo letras (incluye acentos/ñ/ü), espacios, apóstrofe y guion
    if not re.match(r"^[a-zA-ZáéíóúÁÉÍÓÚñÑüÜ\s'-]+$", v):
        raise AppValidationError(
            "Error: El nombre no puede contener números ni símbolos especiales",
            "REAL_NAME_INVALID_CHARACTERS",
        )

    return v


def validar_password_logica(v: str) -> str:
    """Regla para contraseña: longitud, mayúscula y número."""
    if len(v) < 8:
        raise AppValidationError(
            "Error: La contraseña debe tener al menos 8 caracteres",
            "PASSWORD_TOO_SHORT",
        )
    # bcrypt solo usa los primeros 72 bytes reales
    if len(v.encode("utf-8")) > 72:
        raise AppValidationError(
            "Error: La contraseña no puede superar los 72 bytes en UTF-8",
            "PASSWORD_TOO_LONG_BYTES",
        )
    if not any(char.isupper() for char in v):
        raise AppValidationError(
            "Error: La contraseña debe incluir al menos una letra mayúscula",
            "PASSWORD_MISSING_UPPERCASE",
        )
    if not any(char.isdigit() for char in v):
        raise AppValidationError(
            "Error: La contraseña debe incluir al menos un número",
            "PASSWORD_MISSING_NUMBER",
        )
    return v


def validar_fecha_nacimiento_logica(v: date) -> date:
    """Regla para edad mínima (18 años) y evitar fechas futuras."""
    hoy = date.today()
    if v > hoy:
        raise AppValidationError(
            "Error: La fecha de nacimiento no puede ser en el futuro",
            "BIRTH_DATE_IN_FUTURE",
        )
    edad = hoy.year - v.year - ((hoy.month, hoy.day) < (v.month, v.day))
    if edad < 18:
        raise AppValidationError(
            "Error: Debes tener al menos 18 años para registrarte",
            "AGE_RESTRICTION_NOT_MET",
        )
    return v


def validar_altura_logica(v: int) -> int:
    """Valida la altura en cm."""
    if v is None:
        return v
    if not (50 <= v <= 300):
        raise AppValidationError(
            "Error: La altura debe estar entre 50cm y 300cm", "HEIGHT_OUT_OF_RANGE"
        )
    return v


def validar_peso_logica(v: float) -> float:
    """Valida el peso en kg."""
    if v is None:
        return v
    if not (20 <= v <= 300):
        raise AppValidationError(
            "Error: El peso debe estar entre 20kg y 300kg", "WEIGHT_OUT_OF_RANGE"
        )
    return v


def validar_fecha_ruta_logica(v: datetime) -> datetime:
    """Valida fecha ruta logica."""
    if v:
        ahora = datetime.now(timezone.utc)

        # Normalizar v a UTC para comparar y almacenar siempre igual
        v_utc = (
            v.replace(tzinfo=timezone.utc)
            if v.tzinfo is None
            else v.astimezone(timezone.utc)
        )

        margen = ahora + timedelta(minutes=10)
        if v_utc > margen:
            raise AppValidationError(
                "Error: La fecha de la actividad no puede ser en el futuro",
                "ACTIVITY_DATE_IN_FUTURE",
            )

        return v_utc

    return v


def validar_distancia_logica(v: int) -> int:
    """
    Nadie corre más de 300km en una sola sesión (Sanity Check).
    Debe ser positiva y máximo 300km.
    """
    # 300,000 metros = 300km.
    if v <= 0:
        raise AppValidationError(
            "Error: La distancia debe ser mayor a 0", "DISTANCE_MUST_BE_POSITIVE"
        )
    if v > 300000:
        raise AppValidationError(
            "Error: La distancia parece incorrecta (máximo 300km)",
            "DISTANCE_OUT_OF_RANGE",
        )
    return v


def validar_duracion_logica(v: int) -> int:
    """
    Una actividad no suele durar más de 24 horas seguidas.
    Debe ser positiva y máximo 24 horas.
    """
    # 86400 segundos = 24 horas.
    if v <= 0:
        raise AppValidationError(
            "Error: La duración debe ser mayor a 0", "DURATION_MUST_BE_POSITIVE"
        )
    if v > 86400:
        raise AppValidationError(
            "Error: La duración excede el límite de 24 horas", "DURATION_TOO_LONG"
        )
    return v


def validar_calorias_logica(v: int) -> int:
    """
    Quemar más de 10.000 calorías en una sesión es fisiológicamente improbable.
    Debe ser positiva y máximo 10.000.
    """
    if v <= 0:
        raise AppValidationError(
            "Error: Las calorías deben ser mayor a 0", "CALORIES_MUST_BE_POSITIVE"
        )
    if v > 10000:
        raise AppValidationError(
            "Error: Las calorías parecen incorrectas (máximo 10.000)",
            "CALORIES_OUT_OF_RANGE",
        )
    return v


def validar_polilinea_logica(v: str) -> str:
    """La polilínea no puede ser muy corta si existe."""
    if v is None:
        return None
    if len(v) < 5:
        raise AppValidationError("Error: La ruta parece inválida", "ROUTE_INVALID")
    return v


def validar_duracion_no_negativa_logica(
    v: int, field_name: str, error_prefix: str
) -> int:
    """Valida duraciones no negativas con máximo operativo de 24 horas."""
    if v < 0:
        raise AppValidationError(
            f"Error: {field_name} no puede ser negativa",
            f"{error_prefix}_NEGATIVE",
        )
    if v > 86400:
        raise AppValidationError(
            f"Error: {field_name} excede el límite de 24 horas",
            f"{error_prefix}_TOO_LONG",
        )
    return v


def validar_ritmo_segundos_km_logica(v: int, field_name: str, error_prefix: str) -> int:
    """Valida ritmos en segundos por kilómetro."""
    if v < 0:
        raise AppValidationError(
            f"Error: {field_name} no puede ser negativo",
            f"{error_prefix}_NEGATIVE",
        )
    if v > 3600:
        raise AppValidationError(
            f"Error: {field_name} parece inválido",
            f"{error_prefix}_OUT_OF_RANGE",
        )
    return v


def validar_velocidad_x100_logica(v: int, field_name: str, error_prefix: str) -> int:
    """Valida velocidades expresadas como km/h * 100."""
    if v < 0:
        raise AppValidationError(
            f"Error: {field_name} no puede ser negativa",
            f"{error_prefix}_NEGATIVE",
        )
    if v > 10000:
        raise AppValidationError(
            f"Error: {field_name} parece inválida",
            f"{error_prefix}_OUT_OF_RANGE",
        )
    return v


def validar_contador_tracking_logica(v: int, field_name: str, error_prefix: str) -> int:
    """Valida contadores de pausas/alertas del tracking."""
    if v < 0:
        raise AppValidationError(
            f"Error: {field_name} no puede ser negativo",
            f"{error_prefix}_NEGATIVE",
        )
    if v > 500:
        raise AppValidationError(
            f"Error: {field_name} excede el límite permitido",
            f"{error_prefix}_OUT_OF_RANGE",
        )
    return v
