# routers/activities.py

from fastapi import APIRouter, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession
from typing import List
import schemas
import auth
from database import obtener_db
from services import activities_service
from config import settings
from limiter_config import rate_limit

# Inyectamos la dependencia a nivel de Router para todos los endpoints de este archivo
router = APIRouter(
    tags=["Actividades"],
    dependencies=[Depends(auth.verificar_sesion_aplicacion)]
)


@router.post("/actividad/guardar", response_model=schemas.RespuestaObtenerActividad)
@rate_limit(settings.RL_ACTIVIDAD_GUARDAR)
async def guardar_actividad(
    request: Request,
    datos: schemas.GuardarActividad,
    db: AsyncSession = Depends(obtener_db),
    usuario_actual: str = Depends(auth.obtener_usuario_actual)
):
    return await activities_service.crear_actividad(db, usuario_actual, datos)


@router.get("/actividad/obtener/{id_actividad}", response_model=schemas.RespuestaObtenerActividad)
@rate_limit(settings.RL_ACTIVIDAD_OBTENER)
async def obtener_actividad(
    request: Request,
    id_actividad: int,
    db: AsyncSession = Depends(obtener_db),
    usuario_actual: str = Depends(auth.obtener_usuario_actual)
):
    """
    Obtiene el detalle de una actividad específica por su ID.
    Útil si la App necesita recargar los detalles de una ruta concreta.
    """
    return await activities_service.obtener_actividad(db, usuario_actual, id_actividad)


@router.get("/actividad/obtener_todas", response_model=List[schemas.RespuestaObtenerActividad])
@rate_limit(settings.RL_ACTIVIDAD_OBTENER_TODAS)
async def obtener_todas_actividades(
    request: Request,
    skip: int = 0,
    limit: int = 20,
    db: AsyncSession = Depends(obtener_db),
    usuario_actual: str = Depends(auth.obtener_usuario_actual)
):
    """
    Este endpoint es para obtener toda la BD de rutas cuando el usuario vuelve a la app despues de desinstalar.
    Descarga el historial paginado para no sobrecargar la memoria del servidor
    y garantizar que el usuario recibe todos las rutas en un entorno con poca cobertura WIFI/datos.
    Ejemplo: /actividad/obtener?skip=0&limit=20
    """
    return await activities_service.obtener_actividades(db, usuario_actual, skip, limit)


@router.delete("/actividad/borrar/{id_actividad}", response_model=schemas.RespuestaBorrarActividad)
@rate_limit(settings.RL_ACTIVIDAD_BORRAR)
async def borrar_actividad(
    request: Request,
    id_actividad: int,
    db: AsyncSession = Depends(obtener_db),
    usuario_actual: str = Depends(auth.obtener_usuario_actual)
):
    return await activities_service.eliminar_actividad(db, usuario_actual, id_actividad)


@router.delete("/actividad/borrar_todas", response_model=schemas.RespuestaGenerica)
@rate_limit(settings.RL_ACTIVIDAD_BORRAR_TODAS)
async def borrar_todas_actividades(
    request: Request,
    db: AsyncSession = Depends(obtener_db),
    usuario_actual: str = Depends(auth.obtener_usuario_actual)
):
    """
    Borra absolutamente todo el historial deportivo del usuario.
    Se usa para resetear datos desde la App.
    """
    return await activities_service.eliminar_actividades(db, usuario_actual)
