# routers/#activities.py

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from typing import List
import schemas
import auth
from database import obtener_db
from services import activities_service 

router = APIRouter(tags=["Actividades"])

@router.post("/actividad/guardar", response_model=schemas.RespuestaObtenerActividad)
def guardar_actividad(
    datos: schemas.GuardarActividad,
    db: Session = Depends(obtener_db),
    usuario_actual: str = Depends(auth.obtener_usuario_actual),
    _auth_app=Depends(auth.verificar_sesion_aplicacion)
):
    return activities_service.crear_actividad(db, usuario_actual, datos)

@router.get("/actividad/obtener", response_model=List[schemas.RespuestaObtenerActividad])
def obtener_actividad(
    skip: int = 0,
    limit: int = 20,
    db: Session = Depends(obtener_db),
    usuario_actual: str = Depends(auth.obtener_usuario_actual),
    _auth_app=Depends(auth.verificar_sesion_aplicacion)
):
    """
    Descarga historial paginado para no sobrecargar la memoria del servidor
    y garantizar que el usuario recibe todo en un entorno con poca cobertura WIFI o de datos.
    Ejemplo: /actividad/obtener?skip=0&limit=20
    """
    return activities_service.obtener_actividades(db, usuario_actual, skip, limit)

@router.delete("/actividad/borrar/{id_actividad}", response_model=schemas.RespuestaGenerica)
def borrar_actividad(
    id_actividad: int,
    db: Session = Depends(obtener_db),
    usuario_actual: str = Depends(auth.obtener_usuario_actual),
    _auth_app=Depends(auth.verificar_sesion_aplicacion)
):
    return activities_service.eliminar_actividad(db, usuario_actual, id_actividad)