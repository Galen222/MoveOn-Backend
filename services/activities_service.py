# services/activities_service.py

"""Implementa la lógica de negocio de este servicio."""

import json
from typing import Any
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
) -> dict[str, Any]:
    """Registra una nueva actividad y actualiza los acumulados del usuario.

    Flujo:

    1. Bloquea la fila del usuario con ``with_for_update`` para evitar
       carreras con otras operaciones (ranking, otra subida concurrente).
    2. Si el cliente envió ``client_local_id``, busca una actividad ya
       existente con ese mismo id y la devuelve tal cual: esta clave
       hace la operación idempotente, de forma que un reintento del
       cliente Android no duplica actividades.
    3. Si es nueva, inserta la actividad, actualiza los totales
       agregados del usuario (metros, calorías, duración, contador)
       y hace commit dentro de la misma transacción.
    4. Devuelve el payload con el ``nuevo_total_puntos`` recalculado
       (``1 km = 1 punto``) para que el cliente pueda actualizar la UI
       sin una segunda llamada.

    Args:
        db: sesión asíncrona de SQLAlchemy.
        usuario_actual_id: id del usuario autenticado (inyectado por el router).
        datos: ``GuardarActividad`` con todas las métricas ya calculadas en el dispositivo.

    Returns:
        Diccionario con la actividad persistida y ``nuevo_total_puntos`` actualizado.

    Raises:
        AppHTTPException: 404 ``USER_NOT_FOUND`` si el id de usuario ya no existe (cuenta borrada entre el login y esta llamada).
    """
    # Construye actividad.
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

    if datos.client_local_id:
        actividad_existente = (
            await db.execute(
                select(database.Actividad).where(
                    database.Actividad.usuario_id == usuario.id,
                    database.Actividad.client_local_id == datos.client_local_id,
                )
            )
        ).scalar_one_or_none()

        if actividad_existente:
            logger.info(
                "actividad_idempotente_reutilizada",
                extra={
                    "usuario_id": usuario.id,
                    "actividad_id": actividad_existente.id,
                    "client_local_id": datos.client_local_id,
                },
            )

            puntos_actualizados = calculos.calcular_puntos_nivel(
                int(usuario.total_metros or 0)
            )

            return {
                "id": actividad_existente.id,
                "tipo": actividad_existente.tipo,
                "distancia": actividad_existente.distancia,
                "duracion_total": actividad_existente.duracion_total,
                "duracion_movimiento": actividad_existente.duracion_movimiento,
                "duracion_parado": actividad_existente.duracion_parado,
                "duracion_pausa_manual": actividad_existente.duracion_pausa_manual,
                "calorias_quemadas": actividad_existente.calorias_quemadas,
                "ritmo_medio_movimiento": actividad_existente.ritmo_medio_movimiento,
                "ritmo_medio_total": actividad_existente.ritmo_medio_total,
                "ritmo_maximo": actividad_existente.ritmo_maximo,
                "velocidad_media_x100": actividad_existente.velocidad_media_x100,
                "velocidad_max_x100": actividad_existente.velocidad_max_x100,
                "auto_pausas": actividad_existente.auto_pausas,
                "pausas_manuales": actividad_existente.pausas_manuales,
                "alertas_velocidad": actividad_existente.alertas_velocidad,
                "ruta_polilinea": actividad_existente.ruta_polilinea,
                "ruta_mapa_url": actividad_existente.ruta_mapa_url,
                "fecha_ruta": actividad_existente.fecha_ruta,
                "nuevo_total_puntos": puntos_actualizados,
            }

    nueva_actividad = database.Actividad(
        client_local_id=datos.client_local_id,
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
        ritmo_maximo=datos.ritmo_maximo,
        velocidad_media_x100=datos.velocidad_media_x100,
        velocidad_max_x100=datos.velocidad_max_x100,
        auto_pausas=datos.auto_pausas,
        pausas_manuales=datos.pausas_manuales,
        alertas_velocidad=datos.alertas_velocidad,
        ruta_polilinea=datos.ruta_polilinea,
        ruta_mapa_url=str(datos.ruta_mapa_url) if datos.ruta_mapa_url else None,
        fecha_ruta=datos.fecha_ruta,
    )

    total_actual = int(usuario.total_metros or 0)
    usuario.total_metros = total_actual + int(datos.distancia)

    total_calorias_actual = int(usuario.total_calorias or 0)
    usuario.total_calorias = total_calorias_actual + int(datos.calorias_quemadas)

    total_duracion_actual = int(usuario.total_duracion_segundos or 0)
    usuario.total_duracion_segundos = total_duracion_actual + int(datos.duracion_total)

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
        "ritmo_maximo": nueva_actividad.ritmo_maximo,
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


def _serializar_json_seguro(valor) -> str | None:
    """
    Convierte estructuras Python del diagnóstico a texto JSON.

    Se usa solo para persistir el bloque de telemetría auxiliar sin tocar la
    lógica existente del resto de operaciones del servicio.
    """
    if valor in (None, {}, []):
        return None
    return json.dumps(valor, ensure_ascii=False, separators=(",", ":"))


async def guardar_actividad_diagnostico(
    db: AsyncSession,
    usuario_actual_id: int,
    datos: schemas.GuardarActividadDiagnostico,
) -> schemas.RespuestaGuardarActividadDiagnostico:
    """
    Guarda telemetría de diagnóstico enviada automáticamente por la app.

    Este flujo es independiente del guardado normal de actividades:
    - no recalcula puntos
    - no altera acumulados del perfil
    - no modifica ranking
    """
    # Guarda actividad diagnostico.
    usuario = (
        await db.execute(
            select(database.Usuario).where(database.Usuario.id == usuario_actual_id)
        )
    ).scalar_one_or_none()

    if not usuario:
        logger.warning(
            "guardar_diagnostico_usuario_no_encontrado",
            extra={"usuario_id": usuario_actual_id},
        )
        raise app_http_exception(
            status_code=404,
            mensaje="Error: Usuario no encontrado",
            error_code="USER_NOT_FOUND",
        )

    actividad_id_validada = None
    if datos.actividad_id is not None:
        actividad = (
            await db.execute(
                select(database.Actividad).where(
                    database.Actividad.id == datos.actividad_id,
                    database.Actividad.usuario_id == usuario.id,
                )
            )
        ).scalar_one_or_none()

        if not actividad:
            logger.warning(
                "guardar_diagnostico_actividad_no_encontrada",
                extra={
                    "usuario_id": usuario.id,
                    "actividad_id": datos.actividad_id,
                },
            )
            raise app_http_exception(
                status_code=404,
                mensaje="Error: Actividad no encontrada",
                error_code="ACTIVITY_NOT_FOUND",
            )

        actividad_id_validada = actividad.id

    diagnostico = database.ActividadDiagnostico(
        usuario_id=usuario.id,
        actividad_id=actividad_id_validada,
        actividad_local_id=datos.actividad_local_id,
        session_started_at=datos.session_started_at,
        session_finished_at=datos.session_finished_at,
        last_timer_tick_at=datos.last_timer_tick_at,
        service_created_at=datos.service_created_at,
        service_destroyed_at=datos.service_destroyed_at,
        elapsed_seconds=datos.elapsed_seconds,
        moving_seconds=datos.moving_seconds,
        stopped_seconds=datos.stopped_seconds,
        manual_pause_seconds=datos.manual_pause_seconds,
        distance_meters=datos.distance_meters,
        average_pace_total=datos.average_pace_total,
        average_pace_moving=datos.average_pace_moving,
        max_pace=datos.max_pace,
        auto_pauses=datos.auto_pauses,
        manual_pauses=datos.manual_pauses,
        speed_alerts=datos.speed_alerts,
        running_classified_seconds=datos.running_classified_seconds,
        walking_classified_seconds=datos.walking_classified_seconds,
        service_restart_count=datos.service_restart_count,
        current_status=datos.current_status,
        app_version=datos.app_version,
        os_version=datos.os_version,
        manufacturer=datos.manufacturer,
        model=datos.model,
        event_log_json=_serializar_json_seguro(
            [item.model_dump(mode="json") for item in datos.event_log]
        ),
        device_info_json=_serializar_json_seguro(datos.device_info),
    )

    try:
        db.add(diagnostico)
        await db.commit()
        await db.refresh(diagnostico)
    except Exception:
        await db.rollback()
        raise

    logger.info(
        "actividad_diagnostico_guardado",
        extra={
            "usuario_id": usuario.id,
            "diagnostico_id": diagnostico.id,
            "actividad_id": diagnostico.actividad_id,
            "actividad_local_id": diagnostico.actividad_local_id,
        },
    )

    return schemas.RespuestaGuardarActividadDiagnostico(
        estatus="success",
        mensaje="Diagnóstico de actividad guardado correctamente",
        diagnostico_id=diagnostico.id,
    )


async def obtener_actividad(
    db: AsyncSession, usuario_actual_id: int, id_actividad: int
):
    # Reducimos queries duplicadas: en vez de consultar primero el usuario y luego la actividad,
    # se hace una sola query con OUTER JOIN para seguir distinguiendo entre usuario inexistente
    # y actividad inexistente o que no pertenece a este usuario.
    """Recupera una actividad concreta verificando pertenencia en una sola query.

    Usa un ``OUTER JOIN`` entre ``Usuario`` y ``Actividad`` filtrado por
    id de actividad y id de dueño, de modo que:

    - Si el usuario no existe, ``fila`` es ``None`` → 404 con ``USER_NOT_FOUND``.
    - Si el usuario existe pero la actividad no (o no es suya), la columna
      de actividad viene a ``None`` → 404 con ``ACTIVITY_NOT_FOUND``.

    Este diseño evita exponer la diferencia entre "no existe" y "no es
    tuya": ambos casos responden 404 para no permitir enumeración de
    actividades ajenas.

    Args:
        db: sesión asíncrona de SQLAlchemy.
        usuario_actual_id: id del usuario autenticado.
        id_actividad: id remoto de la actividad solicitada.

    Returns:
        Diccionario con el contrato de ``RespuestaObtenerActividad``.

    Raises:
        AppHTTPException: 404 ``USER_NOT_FOUND`` si el usuario no existe.
        AppHTTPException: 404 ``ACTIVITY_NOT_FOUND`` si la actividad no existe o no pertenece al usuario.
    """
    # Obtiene actividad.
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
    # Obtiene actividades.
    usuario_existe = (
        await db.execute(
            select(database.Usuario.id).where(database.Usuario.id == usuario_actual_id)
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
    """Borra una actividad del usuario y actualiza los acumulados.

    Sigue el mismo patrón que ``obtener_actividad`` para la verificación:
    una sola query con ``OUTER JOIN`` y ``with_for_update`` sobre el
    usuario para evitar carreras en los totales. Tras borrar, resta las
    métricas de la actividad a los acumulados (metros, calorías,
    duración, contador) y hace commit en la misma transacción.

    Devuelve el nuevo total de puntos recalculado para que el cliente
    pueda actualizar la UI sin una segunda llamada.

    Args:
        db: sesión asíncrona de SQLAlchemy.
        usuario_actual_id: id del usuario autenticado.
        id_actividad: id remoto de la actividad a borrar.

    Returns:
        Diccionario con ``estatus``, ``mensaje`` y ``nuevo_total_puntos``.

    Raises:
        AppHTTPException: 404 ``USER_NOT_FOUND`` si el usuario no existe.
        AppHTTPException: 404 ``ACTIVITY_NOT_FOUND`` si la actividad no existe o no pertenece al usuario.
    """
    # Elimina actividad.
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
            .with_for_update()
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
        usuario.total_calorias = max(0, total_calorias_actual - calorias_actividad)

        total_duracion_actual = int(usuario.total_duracion_segundos or 0)
        duracion_actividad = int(actividad.duracion_total or 0)
        usuario.total_duracion_segundos = max(
            0, total_duracion_actual - duracion_actividad
        )

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
    """Borra todo el historial deportivo del usuario y resetea sus acumulados.

    Se usa desde la pantalla "borrar mis datos" de la app. Cuenta
    primero cuántas actividades se van a borrar (solo para el log), lanza
    un único ``DELETE`` sobre la tabla de actividades filtrando por dueño,
    y pone a cero los acumulados del usuario. Todo en una sola
    transacción con rollback ante cualquier error para no dejar los
    contadores descuadrados con la tabla.

    Args:
        db: sesión asíncrona de SQLAlchemy.
        usuario_actual_id: id del usuario autenticado.

    Returns:
        ``RespuestaGenerica`` confirmando el borrado masivo.

    Raises:
        AppHTTPException: 404 ``USER_NOT_FOUND`` si el usuario no existe.
    """
    # Elimina actividades.
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
