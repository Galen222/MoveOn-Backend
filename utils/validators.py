# utils/validators.py

import re
from datetime import date, datetime, timedelta
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

def validar_fecha_ruta_logica(v: datetime) -> datetime:
    """Lógica: No se pueden guardar actividades del futuro."""
    if v:

        ahora = datetime.now(v.tzinfo if v.tzinfo else None)
        # CAMBIO: Se da 10 minutos de margen por si el reloj del móvil está adelantado.
        margen = ahora + timedelta(minutes=10)
        if v > margen:
            raise ValueError('Error: La fecha de la actividad no puede ser en el futuro')
    return v

def validar_distancia_logica(v: float) -> float:
    """Lógica: Nadie corre más de 300km en una sola sesión (Sanity Check)."""
    # 300,000 metros = 300km
    if v > 300000:
        raise ValueError('Error: La distancia parece incorrecta (máximo 300km)')
    return v

def validar_duracion_logica(v: int) -> int:
    """Lógica: Una actividad no suele durar más de 24 horas seguidas."""
    # 86400 segundos = 24 horas
    if v > 86400:
        raise ValueError('Error: La duración excede el límite de 24 horas')
    return v

def validar_calorias_logica(v: int) -> int:
    """Lógica: Quemar más de 10.000 calorías en una sesión es fisiológicamente improbable."""
    if v > 10000:
        raise ValueError('Error: Las calorías parecen incorrectas (máximo 10.000)')
    return v

def validar_polilinea_logica(v: str) -> str:
    """Lógica: La polilínea no puede ser muy corta si existe."""
    if v is None:
        return None 
    if len(v) < 5:
        raise ValueError('Error: La ruta parece inválida')
    return v