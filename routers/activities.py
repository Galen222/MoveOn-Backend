# routers/#activities.py

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from typing import List
import schemas
import auth
from database import obtener_db
from services import activities_service 

router = APIRouter(tags=["Actividades"])

@router.post("/actividad/guardar", response_model=schemas.RespuestaObtenerActividad)
async def guardar_actividad(
    datos: schemas.GuardarActividad,
    db: AsyncSession = Depends(obtener_db),
    usuario_actual: str = Depends(auth.obtener_usuario_actual),
    _auth_app=Depends(auth.verificar_sesion_aplicacion)
):
    return await activities_service.crear_actividad(db, usuario_actual, datos)

@router.get("/actividad/obtener/{id_actividad}", response_model=schemas.RespuestaObtenerActividad)
async def obtener_actividad(
    id_actividad: int,
    db: AsyncSession = Depends(obtener_db),
    usuario_actual: str = Depends(auth.obtener_usuario_actual),
    _auth_app=Depends(auth.verificar_sesion_aplicacion)
):
    """
    Obtiene el detalle de una actividad específica por su ID.
    Útil si la App necesita recargar los detalles de una ruta concreta.
    """
    return await activities_service.obtener_actividad(db, usuario_actual, id_actividad)

@router.get("/actividad/obtener_todas", response_model=List[schemas.RespuestaObtenerActividad])
async def obtener_todas_actividades(
    skip: int = 0,
    limit: int = 20,
    db: AsyncSession = Depends(obtener_db),
    usuario_actual: str = Depends(auth.obtener_usuario_actual),
    _auth_app=Depends(auth.verificar_sesion_aplicacion)
):
    """
    Este endpoint es para obtener toda la BD de rutas cuando el usuario vuelve a la app despues de desinstalar.
    Descarga el historial paginado para no sobrecargar la memoria del servidor
    y garantizar que el usuario recibe todos las rutas en un entorno con poca cobertura WIFI/datos.
    Ejemplo: /actividad/obtener?skip=0&limit=20
    """
    return await activities_service.obtener_actividades(db, usuario_actual, skip, limit)

@router.delete("/actividad/borrar/{id_actividad}", response_model=schemas.RespuestaBorrarActividad)
async def borrar_actividad(
    id_actividad: int,
    db: AsyncSession = Depends(obtener_db),
    usuario_actual: str = Depends(auth.obtener_usuario_actual),
    _auth_app=Depends(auth.verificar_sesion_aplicacion)
):
    return await activities_service.eliminar_actividad(db, usuario_actual, id_actividad)

@router.delete("/actividad/borrar_todas", response_model=schemas.RespuestaGenerica)
async def borrar_todas_actividades(
    db: AsyncSession = Depends(obtener_db),
    usuario_actual: str = Depends(auth.obtener_usuario_actual),
    _auth_app=Depends(auth.verificar_sesion_aplicacion)
):
    """
    Borra absolutamente todo el historial deportivo del usuario.
    Se usa para resetear datos desde la App.
    """
    return await activities_service.eliminar_actividades(db, usuario_actual)
