# services/activities_service.py

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import case, select, delete as sa_delete, func
from fastapi import HTTPException
import database
import schemas
from utils import calculos

async def crear_actividad(db: AsyncSession, usuario_actual: str, datos: schemas.GuardarActividad):
    """
    Busca al usuario y registra una nueva actividad deportiva.
    """
    # Se busca el usuario por su nombre (viene del token)
    usuario = (await db.execute(
        select(database.Usuario)
        .where(database.Usuario.nombre_usuario == usuario_actual)
        .with_for_update()
    )).scalar_one_or_none()
    
    if not usuario:
        raise HTTPException(status_code=404, detail="Error: Usuario no encontrado")

    # Se Crea el objeto de base de datos.
    nueva_actividad = database.Actividad(
        usuario_id=usuario.id,
        tipo=datos.tipo.value,
        distancia=datos.distancia,
        duracion=datos.duracion,
        calorias_quemadas=datos.calorias_quemadas,
        ruta_polilinea=datos.ruta_polilinea,
        ruta_mapa_url=datos.ruta_mapa_url,        
        fecha_ruta=datos.fecha_ruta
    )

    # Sumar los metros recorridos de la actividad a los metros totales que tiene el usuario.
    # Se toma el valor directo de la BD y no el valor en Python para no caer en una race condition.
    usuario.total_metros = database.Usuario.total_metros + datos.distancia

    # Se guarda en BD.
    db.add(nueva_actividad)
    await db.commit()
    await db.refresh(nueva_actividad)
    # Al haber hecho el calculo en la BD, Python no sabe el nuevo valor.
    # Debido a eso se refresca el usuario.
    await db.refresh(usuario)
    
    # Calcular los puntos para el Ranking.
    puntos_actualizados = calculos.calcular_puntos_nivel(usuario.total_metros)

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

async def obtener_actividad(db: AsyncSession, usuario_actual: str, id_actividad: int):
    # Burcar usuario
    usuario = (await db.execute(
        select(database.Usuario).where(database.Usuario.nombre_usuario == usuario_actual)
    )).scalar_one_or_none()
    if not usuario:
        raise HTTPException(status_code=404, detail="Error: Usuario no encontrado")

    # Buscar la actividad asegurando que pertenezca a este usuario
    actividad = (await db.execute(
        select(database.Actividad).where(
            database.Actividad.id == id_actividad,
            database.Actividad.usuario_id == usuario.id
        )
    )).scalar_one_or_none()

    if not actividad:
        raise HTTPException(status_code=404, detail="Error: Actividad no encontrada")

    return actividad

async def obtener_actividades(db: AsyncSession, usuario_actual: str, skip: int, limit: int):
    """
    Obtiene la lista paginada de actividades de un usuario específico.
    """
    # Se Busca el usuario para obtener su ID.
    usuario = (await db.execute(
        select(database.Usuario).where(database.Usuario.nombre_usuario == usuario_actual)
    )).scalar_one_or_none()
    
    if not usuario:
        raise HTTPException(status_code=404, detail="Error: Usuario no encontrado")

    # Se Hace la query filtrando por ese ID de usuario.
    actividades = (await db.execute(
        select(database.Actividad)
            .where(database.Actividad.usuario_id == usuario.id)
            .order_by(database.Actividad.fecha_ruta.desc(), database.Actividad.id.desc())
            .offset(skip)
            .limit(limit)
    )).scalars().all()
        
    return actividades

async def eliminar_actividad(db: AsyncSession, usuario_actual: str, id_actividad: int):
    usuario = (await db.execute(
        select(database.Usuario)
        .where(database.Usuario.nombre_usuario == usuario_actual)
        .with_for_update()
    )).scalar_one_or_none()
    if not usuario:
        raise HTTPException(status_code=404, detail="Error: Usuario no encontrado")

    actividad = (await db.execute(
        select(database.Actividad).where(
            database.Actividad.id == id_actividad,
            database.Actividad.usuario_id == usuario.id
        )
    )).scalar_one_or_none()

    if not actividad:
        raise HTTPException(status_code=404, detail="Error: Actividad no encontrada")

    # Se resta la distancia en metros recorrida de la ruta al borrarla.
    # Evita números negativos por errores de redondeo flotante.
    # Calculo directo en BD para evitar Race conditions.
    usuario.total_metros = case(
        (database.Usuario.total_metros - actividad.distancia < 0, 0),
        else_=database.Usuario.total_metros - actividad.distancia
    )

    await db.delete(actividad)
    await db.commit()
    
    # Refrescar para traer de la BD el valor real de 'total_metros' tras el 'case'
    await db.refresh(usuario) 
    
    # Recalcular los puntos con el valor actualizado
    puntos = calculos.calcular_puntos_nivel(usuario.total_metros)
    return {
        "estatus": "success", 
        "mensaje": "Actividad eliminada",
        "nuevo_total_puntos": puntos
    }

async def eliminar_actividades(db: AsyncSession, usuario_actual: str):
    # Buscar usuario
    usuario = (await db.execute(
        select(database.Usuario).where(database.Usuario.nombre_usuario == usuario_actual)
    )).scalar_one_or_none()
    if not usuario:
        raise HTTPException(status_code=404, detail="Error: Usuario no encontrado")

    # Borrado masivo. Buscar todas las actividades donde el usuario_id coincida y borrarlas de golpe.
    # Primero contamos cuántas hay, para poder devolver el número borrado.
    num_borrados = (await db.execute(
        select(func.count())
        .select_from(database.Actividad)
        .where(database.Actividad.usuario_id == usuario.id)
    )).scalar_one()

    await db.execute(
        sa_delete(database.Actividad).where(database.Actividad.usuario_id == usuario.id)
    )

    # Borrar todos los metros recorridos de las actividades del usuario.
    usuario.total_metros = 0.0

    await db.commit()

    return {
        "estatus": "success",
        "mensaje": f"Historial de actividades eliminado correctamente. Se han borrado {int(num_borrados)} actividades."
    }
    