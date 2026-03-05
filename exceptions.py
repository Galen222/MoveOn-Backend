# exceptions.py

"""
Módulo de Manejo de Excepciones Personalizadas.
"""
from fastapi import Request, status
from fastapi.responses import JSONResponse
from typing import Any
import re

def manejador_validacion_personalizado(request: Request, exc: Any):
    """
    Intercepta errores de validación y limpia los prefijos técnicos.
    """
    errores_limpios = []
    
    # Verifica que 'exc' tenga el método errors (propio de RequestValidationError)
    if hasattr(exc, "errors"):
        for error in exc.errors():
            mensaje_original = error.get("msg", "")
            # Limpia el prefijo de error de Pydantic de forma segura con Regex.
            mensaje_limpio = re.sub(r"^(Value error,\s*|Assertion failed,\s*|Input should be.*,\s*)", "", mensaje_original)
        
            loc = error.get("loc") or []
            campo = loc[-1] if loc else "general"
            errores_limpios.append({
                "columna": campo,
                "mensaje": mensaje_limpio.strip().capitalize()
            })

    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        content={"detail": errores_limpios}
    )
    