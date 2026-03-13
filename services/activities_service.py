# services/activities_service.py

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import func, select, delete as sa_delete, and_
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
        raise HTTPException(
            status_code=404, detail="Error: Usuario no encontrado")

    # Se Crea el objeto de base de datos.
    nueva_actividad = database.Actividad(
        usuario_id=usuario.id,
        tipo=datos.tipo.value,
        distancia=datos.distancia,
        duracion=datos.duracion,
        calorias_quemadas=datos.calorias_quemadas,
        ruta_polilinea=datos.ruta_polilinea,
        ruta_mapa_url=str(
            datos.ruta_mapa_url) if datos.ruta_mapa_url else None,
        fecha_ruta=datos.fecha_ruta
    )

    # Sumar distancia y calorías al acumulado histórico del usuario.
    # La fila del usuario ya está bloqueada con FOR UPDATE, así que el cálculo puede hacerse
    # en Python sin caer en una race condition y manteniendo el tipo como int para Pylance.
    total_actual = int(usuario.total_metros or 0)
    usuario.total_metros = total_actual + int(datos.distancia)

    total_calorias_actual = int(usuario.total_calorias or 0)
    usuario.total_calorias = total_calorias_actual + \
        int(datos.calorias_quemadas)

    # Se guarda en BD.
    try:
        db.add(nueva_actividad)
        await db.commit()
        await db.refresh(nueva_actividad)
    except Exception:
        await db.rollback()
        raise

    logger.info(
        "actividad_creada",
        extra={
            "usuario_id": usuario.id,
            "actividad_id": nueva_actividad.id,
            "tipo": nueva_actividad.tipo,
            "distancia": nueva_actividad.distancia,
            "duracion": nueva_actividad.duracion,
            "nuevo_total_metros": usuario.total_metros,
            "nuevo_total_calorias": usuario.total_calorias,
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
    # Reducimos queries duplicadas: en vez de consultar primero el usuario y luego la actividad,
    # se hace una sola query con OUTER JOIN para seguir distinguiendo entre usuario inexistente
    # y actividad inexistente o que no pertenece a este usuario.
    fila = (await db.execute(
        select(database.Usuario.id, database.Actividad)
        .select_from(database.Usuario)
        .outerjoin(
            database.Actividad,
            and_(
                database.Actividad.id == id_actividad,
                database.Actividad.usuario_id == database.Usuario.id
            )
        )
        .where(database.Usuario.id == usuario_actual_id)
    )).first()

    if not fila:
        logger.warning(
            "obtener_actividad_usuario_no_encontrado",
            extra={
                "usuario_id": usuario_actual_id,
                "actividad_id": id_actividad,
            },
        )
        raise HTTPException(
            status_code=404, detail="Error: Usuario no encontrado")

    _, actividad = fila

    # Buscar la actividad asegurando que pertenezca a este usuario
    if not actividad:
        logger.info(
            "actividad_no_encontrada",
            extra={
                "usuario_id": usuario_actual_id,
                "actividad_id": id_actividad,
            },
        )
        raise HTTPException(
            status_code=404, detail="Error: Actividad no encontrada")

    return actividad


async def obtener_actividades(db: AsyncSession, usuario_actual_id: int, skip: int, limit: int):
    """
    Obtiene la lista paginada de actividades del usuario autenticado
    junto con metadata de paginación.
    """
    # Validar que el usuario exista, igual que en el resto de operaciones
    # de actividades, para no devolver una lista vacía si el token apunta
    # a un usuario ya inexistente.
    usuario_existe = (await db.execute(
        select(database.Usuario.id)
        .where(database.Usuario.id == usuario_actual_id)
    )).scalar_one_or_none()

    if not usuario_existe:
        logger.warning(
            "obtener_actividades_usuario_no_encontrado",
            extra={
                "usuario_id": usuario_actual_id,
                "skip": skip,
                "limit": limit,
            },
        )
        raise HTTPException(
            status_code=404, detail="Error: Usuario no encontrado")

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
    # Se sigue bloqueando el usuario porque se modifica total_metros,
    # pero usuario + actividad se recuperan en una sola query.
    fila = (await db.execute(
        select(database.Usuario, database.Actividad)
        .select_from(database.Usuario)
        .outerjoin(
            database.Actividad,
            and_(
                database.Actividad.id == id_actividad,
                database.Actividad.usuario_id == database.Usuario.id
            )
        )
        .where(database.Usuario.id == usuario_actual_id)
        .with_for_update(of=database.Usuario)
    )).first()

    if not fila:
        logger.warning(
            "borrar_actividad_usuario_no_encontrado",
            extra={
                "usuario_id": usuario_actual_id,
                "actividad_id": id_actividad,
            },
        )
        raise HTTPException(
            status_code=404, detail="Error: Usuario no encontrado")

    usuario, actividad = fila

    if not actividad:
        logger.info(
            "borrar_actividad_no_encontrada",
            extra={
                "usuario_id": usuario.id,
                "actividad_id": id_actividad,
            },
        )
        raise HTTPException(
            status_code=404, detail="Error: Actividad no encontrada")

    # Se resta la distancia y las calorías al eliminar la actividad.
    # Evita números negativos por errores de redondeo flotante.
    # La fila del usuario está bloqueada, así que el cálculo puede hacerse en Python
    # y mantener el atributo tipado como int.
    try:
        total_actual = int(usuario.total_metros or 0)
        distancia_actividad = int(actividad.distancia or 0)
        usuario.total_metros = max(0, total_actual - distancia_actividad)

        total_calorias_actual = int(usuario.total_calorias or 0)
        calorias_actividad = int(actividad.calorias_quemadas or 0)
        usuario.total_calorias = max(
            0, total_calorias_actual - calorias_actividad)

        await db.delete(actividad)
        await db.commit()
    except Exception:
        await db.rollback()
        raise

    logger.info(
        "actividad_eliminada",
        extra={
            "usuario_id": usuario.id,
            "actividad_id": id_actividad,
            "distancia_restada": actividad.distancia,
            "calorias_restadas": actividad.calorias_quemadas,
            "nuevo_total_metros": usuario.total_metros,
            "nuevo_total_calorias": usuario.total_calorias,
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
        raise HTTPException(
            status_code=404, detail="Error: Usuario no encontrado")

    # Contar cuántas hay, para devolver el número borrado.
    num_borrados = (await db.execute(
        select(func.count())
        .select_from(database.Actividad)
        .where(database.Actividad.usuario_id == usuario.id)
    )).scalar_one()

    try:
        # Borrado masivo de actividades
        await db.execute(
            sa_delete(database.Actividad).where(
                database.Actividad.usuario_id == usuario.id)
        )

        # Reset de metros y calorías
        usuario.total_metros = 0
        usuario.total_calorias = 0

        await db.commit()
    except Exception:
        await db.rollback()
        raise

    logger.info(
        "borrado_total_actividades_completado",
        extra={
            "usuario_id": usuario.id,
            "num_borradas": int(num_borrados),
            "nuevo_total_metros": 0,
            "nuevo_total_calorias": 0,
        },
    )

    return {
        "estatus": "success",
        "mensaje": f"Historial de actividades eliminado correctamente. Se han borrado {int(num_borrados)} actividades."
    }
