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

    # Sumamos los metros recorridos de la actividad a los metros totales que tiene el usuario
    metros_actuales = usuario.total_metros if usuario.total_metros else 0.0
    usuario.total_metros = metros_actuales + datos.distancia

    # Se guarda en BD.
    db.add(nueva_actividad)
    db.commit()
    db.refresh(nueva_actividad)
    
    # Se calculan los puntos para el Ranking
    puntos_actualizados = int(usuario.total_metros / 1000)

    respuesta = {
        "id": nueva_actividad.id,
        "tipo": nueva_actividad.tipo,
        "distancia": nueva_actividad.distancia,
        "duracion": nueva_actividad.duracion,
        "calorias_quemadas": nueva_actividad.calorias_quemadas,
        "ruta_polilinea": nueva_actividad.ruta_polilinea,
        "ruta_mapa_url": nueva_actividad.ruta_mapa_url,
        "fecha_ruta": nueva_actividad.fecha_ruta,
        "nuevo_total_puntos": puntos_actualizados
    }
    
    return respuesta

def obtener_actividad(db: Session, usuario_actual: str, id_actividad: int):
    # Burcar usuario
    usuario = db.query(database.Usuario).filter(database.Usuario.nombre_usuario == usuario_actual).first()
    if not usuario:
        raise HTTPException(status_code=404, detail="Error: Usuario no encontrado")

    # Buscar la actividad asegurando que pertenezca a este usuario
    actividad = db.query(database.Actividad).filter(
        database.Actividad.id == id_actividad,
        database.Actividad.usuario_id == usuario.id
    ).first()

    if not actividad:
        raise HTTPException(status_code=404, detail="Error: Actividad no encontrada")

    return actividad

def obtener_actividades(db: Session, usuario_actual: str, skip: int, limit: int):
    """
    Obtiene la lista paginada de actividades de un usuario específico.
    """
    # Se Busca el usuario para obtener su ID.
    usuario = db.query(database.Usuario).filter(database.Usuario.nombre_usuario == usuario_actual).first()
    
    if not usuario:
        raise HTTPException(status_code=404, detail="Error: Usuario no encontrado")

    # Se Hace la query filtrando por ese ID de usuario.
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

    # Se resta la distancia en metros recorrida de la ruta al borrarla.
    if usuario.total_metros:
        usuario.total_metros -= actividad.distancia
        # Evitar números negativos por errores de redondeo flotante
        if usuario.total_metros < 0: 
            usuario.total_metros = 0.0

    db.delete(actividad)
    db.commit()
    return {"estatus": "success", "mensaje": "Actividad eliminada"}

def eliminar_actividades(db: Session, usuario_actual: str):
    # Buscar usuario
    usuario = db.query(database.Usuario).filter(database.Usuario.nombre_usuario == usuario_actual).first()
    if not usuario:
        raise HTTPException(status_code=404, detail="Error: Usuario no encontrado")

    # Borrado masivo. Buscar todas las actividades donde el usuario_id coincida y borrarlas de golpe.
    num_borrados = db.query(database.Actividad)\
        .filter(database.Actividad.usuario_id == usuario.id)\
        .delete(synchronize_session=False)
        
    # Borrar todos los metros recorridos de las actividades del usuario.
    usuario.total_metros = 0.0

    db.commit()
    
    return {
        "estatus": "success", 
        "mensaje": f"Historial de actividades eliminado correctamente. Se han borrado {num_borrados} actividades."
    }