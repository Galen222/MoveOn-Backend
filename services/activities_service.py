# services/activities_service.py

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import func, case, select, delete as sa_delete, func
from fastapi import HTTPException
import logging
import database
import schemas
from utils import calculos

logger = logging.getLogger("app.activities")


async def crear_actividad(db: AsyncSession, usuario_actual_id: int, datos: schemas.GuardarActividad):
    """
    Busca al usuario y registra una nueva actividad deportiva.
    """
    # Se busca el usuario por su ID (viene del token)
    usuario = (await db.execute(
        select(database.Usuario)
        .where(database.Usuario.id == usuario_actual_id)
        .with_for_update()
    )).scalar_one_or_none()
    
    if not usuario:
        logger.warning(
            "crear_actividad_usuario_no_encontrado",
            extra={
                "usuario_id": usuario_actual_id,
            },
        )
        raise HTTPException(status_code=404, detail="Error: Usuario no encontrado")

    # Se Crea el objeto de base de datos.
    nueva_actividad = database.Actividad(
        usuario_id=usuario.id,
        tipo=datos.tipo.value,
        distancia=datos.distancia,
        duracion=datos.duracion,
        calorias_quemadas=datos.calorias_quemadas,
        ruta_polilinea=datos.ruta_polilinea,
        ruta_mapa_url=str(datos.ruta_mapa_url) if datos.ruta_mapa_url else None,
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
    
    logger.info(
        "actividad_creada",
        extra={
            "usuario_id": usuario.id,
            "actividad_id": nueva_actividad.id,
            "tipo": nueva_actividad.tipo,
            "distancia": nueva_actividad.distancia,
            "duracion": nueva_actividad.duracion,
            "nuevo_total_metros": usuario.total_metros,
        },
    )

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

async def obtener_actividad(db: AsyncSession, usuario_actual_id: int, id_actividad: int):
    # Burcar usuario
    usuario = (await db.execute(
        select(database.Usuario).where(database.Usuario.id == usuario_actual_id)
    )).scalar_one_or_none()
    if not usuario:
        logger.warning(
            "obtener_actividad_usuario_no_encontrado",
            extra={
                "usuario_id": usuario_actual_id,
                "actividad_id": id_actividad,
            },
        )
        raise HTTPException(status_code=404, detail="Error: Usuario no encontrado")

    # Buscar la actividad asegurando que pertenezca a este usuario
    actividad = (await db.execute(
        select(database.Actividad).where(
            database.Actividad.id == id_actividad,
            database.Actividad.usuario_id == usuario.id
        )
    )).scalar_one_or_none()

    if not actividad:
        logger.info(
            "actividad_no_encontrada",
            extra={
                "usuario_id": usuario.id,
                "actividad_id": id_actividad,
            },
        )
        raise HTTPException(status_code=404, detail="Error: Actividad no encontrada")

    return actividad

async def obtener_actividades(db: AsyncSession, usuario_actual_id: int, skip: int, limit: int):
    """
    Obtiene la lista paginada de actividades del usuario autenticado
    junto con metadata de paginación.
    """
    total = (await db.execute(
        select(func.count())
        .select_from(database.Actividad)
        .where(database.Actividad.usuario_id == usuario_actual_id)
    )).scalar_one()

    items = (await db.execute(
        select(database.Actividad)
        .where(database.Actividad.usuario_id == usuario_actual_id)
        .order_by(database.Actividad.fecha_ruta.desc(), database.Actividad.id.desc())
        .offset(skip)
        .limit(limit)
    )).scalars().all()

    logger.debug(
        "lista_actividades_obtenida",
        extra={
            "usuario_id": usuario_actual_id,
            "skip": skip,
            "limit": limit,
            "total": total,
            "devueltas": len(items),
            "has_more": (skip + limit) < total,
        },
    )

    return {
        "items": items,
        "total": total,
        "skip": skip,
        "limit": limit,
        "has_more": (skip + limit) < total,
    }

async def eliminar_actividad(db: AsyncSession, usuario_actual_id: int, id_actividad: int):
    usuario = (await db.execute(
        select(database.Usuario)
        .where(database.Usuario.id == usuario_actual_id)
        .with_for_update()
    )).scalar_one_or_none()
    if not usuario:
        logger.warning(
            "borrar_actividad_usuario_no_encontrado",
            extra={
                "usuario_id": usuario_actual_id,
                "actividad_id": id_actividad,
            },
        )
        raise HTTPException(status_code=404, detail="Error: Usuario no encontrado")

    actividad = (await db.execute(
        select(database.Actividad).where(
            database.Actividad.id == id_actividad,
            database.Actividad.usuario_id == usuario.id
        )
    )).scalar_one_or_none()

    if not actividad:
        logger.info(
            "borrar_actividad_no_encontrada",
            extra={
                "usuario_id": usuario.id,
                "actividad_id": id_actividad,
            },
        )
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
    
    logger.info(
        "actividad_eliminada",
        extra={
            "usuario_id": usuario.id,
            "actividad_id": id_actividad,
            "distancia_restada": actividad.distancia,
            "nuevo_total_metros": usuario.total_metros,
        },
    )

    # Recalcular los puntos con el valor actualizado
    puntos = calculos.calcular_puntos_nivel(usuario.total_metros)
    return {
        "estatus": "success", 
        "mensaje": "Actividad eliminada",
        "nuevo_total_puntos": puntos
    }

async def eliminar_actividades(db: AsyncSession, usuario_actual_id: int):
    # Buscar usuario (bloqueo para evitar race conditions con crear_actividad/eliminar_actividad)
    usuario = (await db.execute(
        select(database.Usuario)
        .where(database.Usuario.id == usuario_actual_id)
        .with_for_update()
    )).scalar_one_or_none()

    if not usuario:
        logger.warning(
            "borrar_todas_actividades_usuario_no_encontrado",
            extra={
                "usuario_id": usuario_actual_id,
            },
        )
        raise HTTPException(status_code=404, detail="Error: Usuario no encontrado")

    # Contar cuántas hay, para devolver el número borrado.
    num_borrados = (await db.execute(
        select(func.count())
        .select_from(database.Actividad)
        .where(database.Actividad.usuario_id == usuario.id)
    )).scalar_one()

    # Borrado masivo de actividades
    await db.execute(
        sa_delete(database.Actividad).where(database.Actividad.usuario_id == usuario.id)
    )

    # Reset de metros (tu backend trabaja en metros enteros)
    usuario.total_metros = 0

    await db.commit()

    logger.info(
        "borrado_total_actividades_completado",
        extra={
            "usuario_id": usuario.id,
            "num_borradas": int(num_borrados),
            "nuevo_total_metros": 0,
        },
    )

    return {
        "estatus": "success",
        "mensaje": f"Historial de actividades eliminado correctamente. Se han borrado {int(num_borrados)} actividades."
    }
    