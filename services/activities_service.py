# services/activities_service.py

from sqlalchemy.orm import Session
from fastapi import HTTPException
import database
import schemas

def crear_actividad(db: Session, usuario_actual: str, datos: schemas.GuardarActividad):
    """
    Busca al usuario y registra una nueva actividad deportiva.
    """
    # Se busca el usuario por su nombre (viene del token)
    usuario = db.query(database.Usuario).filter(database.Usuario.nombre_usuario == usuario_actual).first()
    
    if not usuario:
        raise HTTPException(status_code=404, detail="Error: Usuario no encontrado")

    # Se Crea el objeto de base de datos.
    nueva_actividad = database.Actividad(
        usuario_id=usuario.id,
        tipo=datos.tipo,
        distancia=datos.distancia,
        duracion=datos.duracion,
        calorias_quemadas=datos.calorias_quemadas,
        ruta_polilinea=datos.ruta_polilinea,
        ruta_mapa_url=datos.ruta_mapa_url,        
        fecha_ruta=datos.fecha_ruta
    )

    # Se guarda en BD.
    db.add(nueva_actividad)
    db.commit()
    db.refresh(nueva_actividad)
    
    return nueva_actividad

def obtener_actividades(db: Session, usuario_actual: str, skip: int, limit: int):
    """
    Obtiene la lista paginada de actividades de un usuario específico.
    """
    # Se Busca el usuario para obtener su ID
    usuario = db.query(database.Usuario).filter(database.Usuario.nombre_usuario == usuario_actual).first()
    
    if not usuario:
        raise HTTPException(status_code=404, detail="Error: Usuario no encontrado")

    # Se Hace la query filtrando por ese ID de usuario
    actividades = db.query(database.Actividad)\
        .filter(database.Actividad.usuario_id == usuario.id)\
        .order_by(database.Actividad.fecha_ruta.desc(), database.Actividad.id.desc())\
        .offset(skip)\
        .limit(limit)\
        .all()
        
    return actividades

def eliminar_actividad(db: Session, usuario_actual: str, id_actividad: int):
    usuario = db.query(database.Usuario).filter(database.Usuario.nombre_usuario == usuario_actual).first()
    if not usuario:
        raise HTTPException(status_code=404, detail="Error: Usuario no encontrado")

    actividad = db.query(database.Actividad).filter(
        database.Actividad.id == id_actividad,
        database.Actividad.usuario_id == usuario.id
    ).first()

    if not actividad:
        raise HTTPException(status_code=404, detail="Error: Actividad no encontrada")

    db.delete(actividad)
    db.commit()
    return {"estatus": "success", "mensaje": "Actividad eliminada"}