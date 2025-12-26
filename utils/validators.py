# utils/validators.py

import re
from datetime import date
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
    
    # REGEX:
    # ^ inicio
    # [ ... ] lista de caracteres permitidos
    # a-zA-Z : letras inglesas
    # áéíóúÁÉÍÓÚñÑ : letras españolas comunes
    # üÜ : diéresis
    # \s : espacios
    # ' : apóstrofe (ej. O'Connor)
    # - : guiones (ej. Ana-Maria)
    # + : uno o más caracteres
    # $ : fin
    if not re.match(r"^[a-zA-ZáéíóúÁÉÍÓÚñÑüÜ\s'-]+$", v):
        raise ValueError('Error: El nombre no puede contener números ni símbolos especiales')
        
    return v

def validar_contraseña_logica(v: str) -> str:
    """Regla para contraseña: longitud, mayúscula y número."""
    if len(v) < 8:
        raise ValueError('Error: La contraseña debe tener al menos 8 caracteres')
    if not any(char.isupper() for char in v):
        raise ValueError('Error: La contraseña debe incluir al menos una letra mayúscula')
    if not any(char.isdigit() for char in v):
        raise ValueError('Error: La contraseña debe incluir al menos un número')
    return v

def validar_fecha_nacimiento_logica(v: date) -> date:
    """Regla para edad mínima (13 años) y evitar fechas futuras."""
    hoy = date.today()
    if v > hoy:
        raise ValueError('Error: La fecha de nacimiento no puede ser en el futuro')
    edad = hoy.year - v.year - ((hoy.month, hoy.day) < (v.month, v.day))
    if edad < 13:
        raise ValueError('Error: Debes tener al menos 13 años para registrarte')
    return v

def validar_altura_logica(v: int) -> int:
    """Valida la altura en cm."""
    if v is None: return v
    if not (50 <= v <= 300):
        raise ValueError('Error: La altura debe estar entre 50cm y 300cm')
    return v

def validar_peso_logica(v: float) -> float:
    """Valida el peso en kg."""
    if v is None: return v
    if not (20 <= v <= 300):
        raise ValueError('Error: El peso debe estar entre 20kg y 300kg')
    return v