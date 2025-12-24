# exceptions.py

"""
Módulo de Manejo de Excepciones Personalizadas.
"""
from fastapi import Request, status
from fastapi.responses import JSONResponse
from typing import Any

async def manejador_validacion_personalizado(request: Request, exc: Any):
    """
    Intercepta errores de validación y limpia los prefijos técnicos.
    Uso 'Any' para evitar conflictos de tipos con Pylance.
    """
    # Esto se hizo solo en pricipio para poner bonito el mensaje de error 
    # si el email no pasa la validación ya que lo valida una libreria
    # y el mensaje que proporciona no es igual a los creados por mi
    # en el resto de errores de validación.
    
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