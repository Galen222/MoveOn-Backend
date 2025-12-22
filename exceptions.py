"""
Módulo de Manejo de Excepciones Personalizadas.
"""
from fastapi import Request, status
from fastapi.responses import JSONResponse
from typing import Any

async def manejador_validacion_personalizado(request: Request, exc: Any):
    """
    Intercepta errores de validación y limpia los prefijos técnicos.
    Usamos 'Any' para evitar conflictos de tipos con Pylance.
    """
    errores_limpios = []
    
    # Verifica que 'exc' tenga el método errors (propio de RequestValidationError)
    if hasattr(exc, "errors"):
        for error in exc.errors():
            mensaje_original = error.get("msg", "")
            # Limpia los prefijos
            mensaje_limpio = mensaje_original.replace("Value error, ", "")
            
            campo = error.get("loc")[-1]
            
            errores_limpios.append({
                "columna": campo,
                "mensaje": mensaje_limpio
            })

    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        content={"detail": errores_limpios}
    )