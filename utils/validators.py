# utils/validators.py

import re
from datetime import date, datetime, timedelta, timezone
from typing import Any


def interceptar_error_pydantic(valor: Any, handler, mensaje_error: str):
    """
    Ejecuta el validador por defecto de Pydantic (handler).
    Si falla, lanza un ValueError con un mensaje personalizado limpio.
    """
    try:
        return handler(valor)
    except Exception:
        raise ValueError(mensaje_error)

# Funciones de lógica de validación

def validar_nombre_real_logica(v: str) -> str:
    """Regla para el nombre real: longitud y símbolos."""
    if len(v) < 3:
        raise ValueError('Error: El nombre real es demasiado corto')
    
    # Límite superior para evitar payloads absurdamente grandes
    if len(v) > 80:
        raise ValueError("Error: El nombre real no puede superar los 80 caracteres")

    # Solo letras (incluye acentos/ñ/ü), espacios, apóstrofe y guion
    if not re.match(r"^[a-zA-ZáéíóúÁÉÍÓÚñÑüÜ\s'-]+$", v):
        raise ValueError('Error: El nombre no puede contener números ni símbolos especiales')

    return v


def validar_password_logica(v: str) -> str:
    """Regla para contraseña: longitud, mayúscula y número."""
    if len(v) < 8:
        raise ValueError(
            'Error: La contraseña debe tener al menos 8 caracteres')
    # bcrypt solo usa los primeros 72 bytes; limita para evitar truncado / DoS
    if len(v) > 128:
        raise ValueError("Error: La contraseña no puede superar los 128 caracteres")
    if not any(char.isupper() for char in v):
        raise ValueError(
            'Error: La contraseña debe incluir al menos una letra mayúscula')
    if not any(char.isdigit() for char in v):
        raise ValueError(
            'Error: La contraseña debe incluir al menos un número')
    return v


def validar_fecha_nacimiento_logica(v: date) -> date:
    """Regla para edad mínima (18 años) y evitar fechas futuras."""
    hoy = date.today()
    if v > hoy:
        raise ValueError(
            'Error: La fecha de nacimiento no puede ser en el futuro')
    edad = hoy.year - v.year - ((hoy.month, hoy.day) < (v.month, v.day))
    if edad < 18:
        raise ValueError(
            'Error: Debes tener al menos 18 años para registrarte')
    return v


def validar_altura_logica(v: int) -> int:
    """Valida la altura en cm."""
    if v is None:
        return v
    if not (50 <= v <= 300):
        raise ValueError('Error: La altura debe estar entre 50cm y 300cm')
    return v


def validar_peso_logica(v: float) -> float:
    """Valida el peso en kg."""
    if v is None:
        return v
    if not (20 <= v <= 300):
        raise ValueError('Error: El peso debe estar entre 20kg y 300kg')
    return v


def validar_fecha_ruta_logica(v: datetime) -> datetime:
    if v:
        ahora = datetime.now(timezone.utc)

        # Normalizar v a UTC para comparar y almacenar siempre igual
        v_utc = v.replace(tzinfo=timezone.utc) if v.tzinfo is None else v.astimezone(timezone.utc)

        margen = ahora + timedelta(minutes=10)
        if v_utc > margen:
            raise ValueError("Error: La fecha de la actividad no puede ser en el futuro")

        return v_utc

    return v


def validar_distancia_logica(v: int) -> int:
    """
    Nadie corre más de 300km en una sola sesión (Sanity Check).
    Debe ser positiva y máximo 300km.
    """
    # 300,000 metros = 300km.
    if v <= 0:
        raise ValueError('Error: La distancia debe ser mayor a 0')
    if v > 300000:
        raise ValueError(
            'Error: La distancia parece incorrecta (máximo 300km)')
    return v


def validar_duracion_logica(v: int) -> int:
    """
    Una actividad no suele durar más de 24 horas seguidas.
    Debe ser positiva y máximo 24 horas.
    """
    # 86400 segundos = 24 horas.
    if v <= 0:
        raise ValueError('Error: La duración debe ser mayor a 0')
    if v > 86400:
        raise ValueError('Error: La duración excede el límite de 24 horas')
    return v


def validar_calorias_logica(v: int) -> int:
    """
    Quemar más de 10.000 calorías en una sesión es fisiológicamente improbable.
    Debe ser positiva y máximo 10.000.
    """
    if v <= 0:
        raise ValueError('Error: Las calorías deben ser mayor a 0')
    if v > 10000:
        raise ValueError(
            'Error: Las calorías parecen incorrectas (máximo 10.000)')
    return v


def validar_polilinea_logica(v: str) -> str:
    """La polilínea no puede ser muy corta si existe."""
    if v is None:
        return None
    if len(v) < 5:
        raise ValueError('Error: La ruta parece inválida')
    return v
