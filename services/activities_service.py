# services/activities_service.py

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import func, select, delete as sa_delete, and_
from exceptions import app_http_exception
import logging
import database
import schemas
from utils import calculos

logger = logging.getLogger("app.activities")


async def crear_actividad(
    db: AsyncSession, usuario_actual_id: int, datos: schemas.GuardarActividad
):
    """
    Busca al usuario y registra una nueva actividad deportiva enriquecida.
    """
    usuario = (
        await db.execute(
            select(database.Usuario)
            .where(database.Usuario.id == usuario_actual_id)
            .with_for_update()
        )
    ).scalar_one_or_none()

    if not usuario:
        logger.warning(
            "crear_actividad_usuario_no_encontrado",
            extra={"usuario_id": usuario_actual_id},
        )
        raise app_http_exception(
            status_code=404,
            mensaje="Error: Usuario no encontrado",
            error_code="USER_NOT_FOUND",
        )

    nueva_actividad = database.Actividad(
        usuario_id=usuario.id,
        tipo=datos.tipo.value,
        distancia=datos.distancia,
        duracion_total=datos.duracion_total,
        duracion_movimiento=datos.duracion_movimiento,
        duracion_parado=datos.duracion_parado,
        duracion_pausa_manual=datos.duracion_pausa_manual,
        calorias_quemadas=datos.calorias_quemadas,
        ritmo_medio_movimiento=datos.ritmo_medio_movimiento,
        ritmo_medio_total=datos.ritmo_medio_total,
        velocidad_media_x100=datos.velocidad_media_x100,
        velocidad_max_x100=datos.velocidad_max_x100,
        auto_pausas=datos.auto_pausas,
        pausas_manuales=datos.pausas_manuales,
        alertas_velocidad=datos.alertas_velocidad,
        ruta_polilinea=datos.ruta_polilinea,
        ruta_mapa_url=str(
            datos.ruta_mapa_url) if datos.ruta_mapa_url else None,
        fecha_ruta=datos.fecha_ruta,
    )

    total_actual = int(usuario.total_metros or 0)
    usuario.total_metros = total_actual + int(datos.distancia)

    total_calorias_actual = int(usuario.total_calorias or 0)
    usuario.total_calorias = total_calorias_actual + \
        int(datos.calorias_quemadas)

    total_duracion_actual = int(usuario.total_duracion_segundos or 0)
    usuario.total_duracion_segundos = total_duracion_actual + \
        int(datos.duracion_total)

    total_actividades_actual = int(usuario.total_actividades or 0)
    usuario.total_actividades = total_actividades_actual + 1

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
            "duracion_total": nueva_actividad.duracion_total,
            "duracion_movimiento": nueva_actividad.duracion_movimiento,
            "duracion_parado": nueva_actividad.duracion_parado,
            "nuevo_total_metros": usuario.total_metros,
            "nuevo_total_calorias": usuario.total_calorias,
            "nuevo_total_duracion": usuario.total_duracion_segundos,
            "nuevo_total_actividades": usuario.total_actividades,
        },
    )

    puntos_actualizados = calculos.calcular_puntos_nivel(usuario.total_metros)

    respuesta = {
        "id": nueva_actividad.id,
        "tipo": nueva_actividad.tipo,
        "distancia": nueva_actividad.distancia,
        "duracion_total": nueva_actividad.duracion_total,
        "duracion_movimiento": nueva_actividad.duracion_movimiento,
        "duracion_parado": nueva_actividad.duracion_parado,
        "duracion_pausa_manual": nueva_actividad.duracion_pausa_manual,
        "calorias_quemadas": nueva_actividad.calorias_quemadas,
        "ritmo_medio_movimiento": nueva_actividad.ritmo_medio_movimiento,
        "ritmo_medio_total": nueva_actividad.ritmo_medio_total,
        "velocidad_media_x100": nueva_actividad.velocidad_media_x100,
        "velocidad_max_x100": nueva_actividad.velocidad_max_x100,
        "auto_pausas": nueva_actividad.auto_pausas,
        "pausas_manuales": nueva_actividad.pausas_manuales,
        "alertas_velocidad": nueva_actividad.alertas_velocidad,
        "ruta_polilinea": nueva_actividad.ruta_polilinea,
        "ruta_mapa_url": nueva_actividad.ruta_mapa_url,
        "fecha_ruta": nueva_actividad.fecha_ruta,
        "nuevo_total_puntos": puntos_actualizados,
    }

    return respuesta


async def obtener_actividad(
    db: AsyncSession, usuario_actual_id: int, id_actividad: int
):
    # Reducimos queries duplicadas: en vez de consultar primero el usuario y luego la actividad,
    # se hace una sola query con OUTER JOIN para seguir distinguiendo entre usuario inexistente
    # y actividad inexistente o que no pertenece a este usuario.
    fila = (
        await db.execute(
            select(database.Usuario.id, database.Actividad)
            .select_from(database.Usuario)
            .outerjoin(
                database.Actividad,
                and_(
                    database.Actividad.id == id_actividad,
                    database.Actividad.usuario_id == database.Usuario.id,
                ),
            )
            .where(database.Usuario.id == usuario_actual_id)
        )
    ).first()

    if not fila:
        logger.warning(
            "obtener_actividad_usuario_no_encontrado",
            extra={
                "usuario_id": usuario_actual_id,
                "actividad_id": id_actividad,
            },
        )
        raise app_http_exception(
            status_code=404,
            mensaje="Error: Usuario no encontrado",
            error_code="USER_NOT_FOUND",
        )

    _, actividad = fila

    if not actividad:
        logger.info(
            "actividad_no_encontrada",
            extra={
                "usuario_id": usuario_actual_id,
                "actividad_id": id_actividad,
            },
        )
        raise app_http_exception(
            status_code=404,
            mensaje="Error: Actividad no encontrada",
            error_code="ACTIVITY_NOT_FOUND",
        )

    return actividad


async def obtener_actividades(
    db: AsyncSession, usuario_actual_id: int, skip: int, limit: int
):
    """
    Obtiene la lista paginada de actividades del usuario autenticado
    junto con metadata de paginación.
    """
    usuario_existe = (
        await db.execute(
            select(database.Usuario.id).where(
                database.Usuario.id == usuario_actual_id)
        )
    ).scalar_one_or_none()

    if not usuario_existe:
        logger.warning(
            "obtener_actividades_usuario_no_encontrado",
            extra={
                "usuario_id": usuario_actual_id,
                "skip": skip,
                "limit": limit,
            },
        )
        raise app_http_exception(
            status_code=404,
            mensaje="Error: Usuario no encontrado",
            error_code="USER_NOT_FOUND",
        )

    total = (
        await db.execute(
            select(func.count())
            .select_from(database.Actividad)
            .where(database.Actividad.usuario_id == usuario_actual_id)
        )
    ).scalar_one()

    items = (
        (
            await db.execute(
                select(database.Actividad)
                .where(database.Actividad.usuario_id == usuario_actual_id)
                .order_by(
                    database.Actividad.fecha_ruta.desc(), database.Actividad.id.desc()
                )
                .offset(skip)
                .limit(limit)
            )
        )
        .scalars()
        .all()
    )

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


async def eliminar_actividad(
    db: AsyncSession, usuario_actual_id: int, id_actividad: int
):
    # Se sigue bloqueando el usuario porque se modifican los acumulados,
    # pero usuario + actividad se recuperan en una sola query.
    fila = (
        await db.execute(
            select(database.Usuario, database.Actividad)
            .select_from(database.Usuario)
            .outerjoin(
                database.Actividad,
                and_(
                    database.Actividad.id == id_actividad,
                    database.Actividad.usuario_id == database.Usuario.id,
                ),
            )
            .where(database.Usuario.id == usuario_actual_id)
            .with_for_update(of=database.Usuario)
        )
    ).first()

    if not fila:
        logger.warning(
            "borrar_actividad_usuario_no_encontrado",
            extra={
                "usuario_id": usuario_actual_id,
                "actividad_id": id_actividad,
            },
        )
        raise app_http_exception(
            status_code=404,
            mensaje="Error: Usuario no encontrado",
            error_code="USER_NOT_FOUND",
        )

    usuario, actividad = fila

    if not actividad:
        logger.info(
            "borrar_actividad_no_encontrada",
            extra={
                "usuario_id": usuario.id,
                "actividad_id": id_actividad,
            },
        )
        raise app_http_exception(
            status_code=404,
            mensaje="Error: Actividad no encontrada",
            error_code="ACTIVITY_NOT_FOUND",
        )

    try:
        total_actual = int(usuario.total_metros or 0)
        distancia_actividad = int(actividad.distancia or 0)
        usuario.total_metros = max(0, total_actual - distancia_actividad)

        total_calorias_actual = int(usuario.total_calorias or 0)
        calorias_actividad = int(actividad.calorias_quemadas or 0)
        usuario.total_calorias = max(
            0, total_calorias_actual - calorias_actividad)

        total_duracion_actual = int(usuario.total_duracion_segundos or 0)
        duracion_actividad = int(actividad.duracion_total or 0)
        usuario.total_duracion_segundos = max(
            0, total_duracion_actual - duracion_actividad)

        total_actividades_actual = int(usuario.total_actividades or 0)
        usuario.total_actividades = max(0, total_actividades_actual - 1)

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
            "duracion_restada": actividad.duracion_total,
            "nuevo_total_metros": usuario.total_metros,
            "nuevo_total_calorias": usuario.total_calorias,
            "nuevo_total_duracion": usuario.total_duracion_segundos,
            "nuevo_total_actividades": usuario.total_actividades,
        },
    )

    puntos = calculos.calcular_puntos_nivel(usuario.total_metros)
    return {
        "estatus": "success",
        "mensaje": "Actividad eliminada",
        "nuevo_total_puntos": puntos,
    }


async def eliminar_actividades(db: AsyncSession, usuario_actual_id: int):
    usuario = (
        await db.execute(
            select(database.Usuario)
            .where(database.Usuario.id == usuario_actual_id)
            .with_for_update()
        )
    ).scalar_one_or_none()

    if not usuario:
        logger.warning(
            "borrar_todas_actividades_usuario_no_encontrado",
            extra={
                "usuario_id": usuario_actual_id,
            },
        )
        raise app_http_exception(
            status_code=404,
            mensaje="Error: Usuario no encontrado",
            error_code="USER_NOT_FOUND",
        )

    num_borrados = (
        await db.execute(
            select(func.count())
            .select_from(database.Actividad)
            .where(database.Actividad.usuario_id == usuario.id)
        )
    ).scalar_one()

    try:
        await db.execute(
            sa_delete(database.Actividad).where(
                database.Actividad.usuario_id == usuario.id
            )
        )

        usuario.total_metros = 0
        usuario.total_calorias = 0
        usuario.total_duracion_segundos = 0
        usuario.total_actividades = 0

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
            "nuevo_total_duracion": 0,
            "nuevo_total_actividades": 0,
        },
    )

    return {
        "estatus": "success",
        "mensaje": f"Historial de actividades eliminado correctamente. Se han borrado {int(num_borrados)} actividades.",
    }
