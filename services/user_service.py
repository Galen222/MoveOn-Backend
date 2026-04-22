# services/user_service.py

"""
Servicio de Gestión de Usuarios.
Encapsula la lógica de negocio de registro y actualización de perfil.

Importante (Android Java): para que el backend reciba un null explícito
y lo pueda borrar, el cliente debe enviar los nulls en el JSON
(con Gson es new GsonBuilder().serializeNulls()), si no, el campo se omite
y el backend no puede distinguir “quiero borrarlo” de “no quiero tocarlo”.
"""

from __future__ import annotations

from datetime import datetime, timezone
import logging
import secrets
from typing import Any, Optional

from sqlalchemy import desc, select, update, func
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.concurrency import run_in_threadpool
from services import (
    text_moderation_service,
    email_service,
    access_service,
    social_auth_service,
)
from exceptions import app_http_exception
from fastapi import HTTPException
import auth
import database
import schemas
from utils import calculos

logger = logging.getLogger("app.users")


async def registrar_nuevo_usuario(
    db: AsyncSession,
    datos: schemas.Registro,
) -> dict[str, Any]:
    """
    Registro de nuevo usuario con validación de duplicados.

    Mejora (auditoría V12 # 3):
    - En vez de 2 queries separadas (nombre y email), hacemos 1 sola query OR.
    - Reduce ventanas de carrera y mejora rendimiento.
    - Aun así mantenemos el try/except IntegrityError como red de seguridad (concurrencia).
    """
    # Normalizaciones básicas
    nombre_usuario = datos.nombre_usuario.strip()
    if not nombre_usuario:
        raise app_http_exception(
            status_code=400,
            mensaje="Error: El nombre de usuario no puede estar vacío",
            error_code="USERNAME_EMPTY",
        )

    # Guardamos email siempre en minúsculas para que la unicidad sea consistente
    email = str(datos.email).strip().lower()
    nombre_key = nombre_usuario.lower()

    # Nombre real normalizado
    nombre_real = (
        datos.nombre_real.strip() if isinstance(datos.nombre_real, str) else None
    )

    # Moderación de texto
    await text_moderation_service.validar_nombre_usuario(nombre_usuario)
    if nombre_real:
        await text_moderation_service.validar_nombre_real(nombre_real)

    # 1) Detección de duplicados en UNA sola query
    # - nombre_usuario case-insensitive
    # - email exact match (ya lo normalizamos a lower)
    existente = (
        await db.execute(
            select(database.Usuario).where(
                (func.lower(database.Usuario.nombre_usuario) == nombre_key)
                | (database.Usuario.email == email)
            )
        )
    ).scalar_one_or_none()

    if existente:
        # Mensaje específico: ayuda a UX y evita ambigüedad
        if str(existente.nombre_usuario).lower() == nombre_key:
            logger.warning(
                "registro_usuario_nombre_duplicado",
                extra={
                    "nombre_usuario": nombre_usuario,
                    "email": email,
                },
            )
            raise app_http_exception(
                status_code=400,
                mensaje="Error: El nombre de usuario ya está en uso",
                error_code="USERNAME_ALREADY_IN_USE",
            )

        logger.warning(
            "registro_usuario_email_duplicado",
            extra={
                "nombre_usuario": nombre_usuario,
                "email": email,
            },
        )
        raise app_http_exception(
            status_code=400,
            mensaje="Error: El email ya está en uso",
            error_code="EMAIL_ALREADY_IN_USE",
        )

    # 2) Hash de contraseña en threadpool (bcrypt es CPU-bound y bloquea el event loop)
    password_hash = await run_in_threadpool(auth.encriptar_password, datos.password)

    # 3) Enums a string para persistir en columnas String (si viene None, guardar None)
    genero_val = datos.genero.value if datos.genero else None
    provincia_val = datos.provincia.value if datos.provincia else None

    # 4) Construcción del objeto Usuario
    nuevo_usuario = database.Usuario(
        nombre_usuario=nombre_usuario,
        email=email,
        password_encriptada=password_hash,
        nombre_real=nombre_real,
        fecha_nacimiento=datos.fecha_nacimiento,
        genero=genero_val,
        altura=datos.altura,
        peso=datos.peso,
        provincia=provincia_val,
        perfil_visible=datos.perfil_visible,
        acepta_terminos=datos.acepta_terminos,
        fecha_eula=datos.fecha_aceptacion_terminos,
        version_terminos=datos.version_terminos,
    )

    # 5) Persistencia con red de seguridad por si hay concurrencia (race condition)
    # Aunque hayamos detectado duplicados, otra petición puede colarse entre medias.
    try:
        db.add(nuevo_usuario)
        await db.commit()
        await db.refresh(nuevo_usuario)
    except IntegrityError:
        await db.rollback()
        logger.warning(
            "registro_usuario_error_integridad",
            extra={
                "nombre_usuario": nombre_usuario,
                "email": email,
            },
            exc_info=True,
        )
        raise app_http_exception(
            status_code=400,
            mensaje="Error: El nombre de usuario o el email ya están en uso",
            error_code="USERNAME_OR_EMAIL_ALREADY_IN_USE",
        )
    except Exception:
        await db.rollback()
        raise

    logger.info(
        "usuario_registrado",
        extra={
            "usuario": nuevo_usuario.nombre_usuario,
            "usuario_id": nuevo_usuario.id,
            "perfil_visible": nuevo_usuario.perfil_visible,
            "provincia": nuevo_usuario.provincia,
        },
    )

    return {
        "estatus": "success",
        "mensaje": "Usuario registrado correctamente",
        "nombre_usuario": nuevo_usuario.nombre_usuario,
    }


async def registrar_usuario_social(
    db: AsyncSession,
    datos: schemas.RegistroSocial,
    identidad: social_auth_service.SocialIdentity,
):
    """Registra un usuario nuevo vinculado a un proveedor social verificado.

    Flujo:

    1. Valida y normaliza el ``nombre_usuario`` solicitado (no vacío,
       moderación de texto para bloquear nombres prohibidos).
    2. Normaliza el email devuelto por el proveedor a minúsculas.
    3. Delega en lógica compartida de registro para crear el usuario
       en la base, añadir la foto de avatar inicial si el proveedor la
       devolvió, y crear el vínculo ``UsuarioAuthSocial`` correspondiente.
    4. Emite directamente una sesión de login (access + refresh) para
       que el cliente no tenga que llamar a ``/login/social`` justo
       después del registro.

    Args:
        db: sesión asíncrona de SQLAlchemy.
        datos: ``RegistroSocial`` con ``nombre_usuario``, evidencia de términos y el token social.
        identidad: ``SocialIdentity`` ya verificada por ``social_auth_service``.

    Returns:
        ``RespuestaLogin`` con los tokens de sesión emitidos para el nuevo usuario.

    Raises:
        AppHTTPException: 400 ``USERNAME_EMPTY`` si ``nombre_usuario`` está vacío tras recortar.
        AppHTTPException: 400/409 relativos a duplicados de usuario, email o vínculo social.
    """

    # Gestiona registrar usuario social.
    nombre_usuario = datos.nombre_usuario.strip()
    if not nombre_usuario:
        raise app_http_exception(
            status_code=400,
            mensaje="Error: El nombre de usuario no puede estar vacío",
            error_code="USERNAME_EMPTY",
        )

    await text_moderation_service.validar_nombre_usuario(nombre_usuario)

    email = identidad.email.strip().lower() if identidad.email else None
    if not email:
        raise app_http_exception(
            status_code=400,
            mensaje="Error: La cuenta social debe proporcionar un email válido",
            error_code="SOCIAL_EMAIL_REQUIRED",
        )

    vinculo_existente = await social_auth_service.buscar_vinculo_social(
        db, identidad.provider, identidad.provider_user_id
    )
    if vinculo_existente:
        usuario_existente = await obtener_perfil(db, vinculo_existente.usuario_id)
        social_auth_service.actualizar_metadata_vinculo(vinculo_existente, identidad)
        if not usuario_existente.foto_perfil and identidad.avatar_url:
            usuario_existente.foto_perfil = identidad.avatar_url
            await db.commit()
            await db.refresh(usuario_existente)
        return await access_service.crear_sesion_login(db, usuario_existente)

    nombre_key = nombre_usuario.lower()

    existente = (
        await db.execute(
            select(database.Usuario).where(
                (func.lower(database.Usuario.nombre_usuario) == nombre_key)
                | (database.Usuario.email == email)
            )
        )
    ).scalar_one_or_none()

    if existente:
        if str(existente.nombre_usuario).lower() == nombre_key:
            logger.warning(
                "registro_social_nombre_duplicado",
                extra={
                    "provider": identidad.provider,
                    "provider_user_id": identidad.provider_user_id,
                    "nombre_usuario": nombre_usuario,
                    "email": email,
                },
            )
            raise app_http_exception(
                status_code=400,
                mensaje="Error: El nombre de usuario ya está en uso",
                error_code="USERNAME_ALREADY_IN_USE",
            )

        logger.warning(
            "registro_social_email_duplicado",
            extra={
                "provider": identidad.provider,
                "provider_user_id": identidad.provider_user_id,
                "nombre_usuario": nombre_usuario,
                "email": email,
            },
        )
        raise app_http_exception(
            status_code=400,
            mensaje="Error: El email ya está en uso",
            error_code="EMAIL_ALREADY_IN_USE",
        )

    password_aleatoria = secrets.token_urlsafe(32)
    password_hash = await run_in_threadpool(auth.encriptar_password, password_aleatoria)

    nuevo_usuario = database.Usuario(
        nombre_usuario=nombre_usuario,
        email=email,
        password_encriptada=password_hash,
        nombre_real=identidad.nombre,
        fecha_nacimiento=datos.fecha_nacimiento,
        genero=None,
        altura=None,
        peso=None,
        provincia=None,
        foto_perfil=identidad.avatar_url,
        perfil_visible=datos.perfil_visible,
        acepta_terminos=datos.acepta_terminos,
        fecha_eula=datos.fecha_aceptacion_terminos,
        version_terminos=datos.version_terminos,
    )

    try:
        db.add(nuevo_usuario)
        await db.flush()

        vinculo = social_auth_service.crear_vinculo_social(
            usuario_id=int(nuevo_usuario.id),
            identidad=identidad,
        )
        db.add(vinculo)
        await db.flush()

        vinculo.ultimo_login_en = vinculo.creada_en

        await db.commit()
        await db.refresh(nuevo_usuario)
    except IntegrityError:
        await db.rollback()
        logger.warning(
            "registro_social_error_integridad",
            extra={
                "provider": identidad.provider,
                "provider_user_id": identidad.provider_user_id,
                "nombre_usuario": nombre_usuario,
                "email": email,
            },
            exc_info=True,
        )
        raise app_http_exception(
            status_code=400,
            mensaje="Error: El nombre de usuario, el email o la cuenta social ya están en uso",
            error_code="SOCIAL_ACCOUNT_OR_USER_ALREADY_IN_USE",
        )
    except Exception:
        await db.rollback()
        raise

    logger.info(
        "usuario_registrado_social",
        extra={
            "usuario": nuevo_usuario.nombre_usuario,
            "usuario_id": nuevo_usuario.id,
            "provider": identidad.provider,
            "provider_user_id": identidad.provider_user_id,
        },
    )

    return await access_service.crear_sesion_login(db, nuevo_usuario)


async def obtener_perfil(
    db: AsyncSession, usuario_actual_id: int, for_update: bool = False
):
    """Carga el perfil del usuario autenticado, opcionalmente bloqueando la fila.

    La bandera ``for_update`` aplica ``SELECT ... FOR UPDATE`` para casos
    en los que el llamador va a modificar el perfil justo después
    (``PATCH /perfil/actualizar``): así se evita que dos sincronizaciones
    concurrentes desde dos dispositivos pisen cambios del otro.

    Para lecturas puras (pantalla de perfil, cabecera del ranking) se
    llama sin bloqueo para no serializar accesos innecesariamente.

    Args:
        db: sesión asíncrona de SQLAlchemy.
        usuario_actual_id: id del usuario autenticado.
        for_update: ``True`` si el llamador va a modificar la fila tras leerla.

    Returns:
        Fila ``database.Usuario`` del usuario.

    Raises:
        AppHTTPException: 404 ``USER_NOT_FOUND`` si el id ya no existe en base de datos.
    """
    # Obtiene perfil.
    query = select(database.Usuario).where(database.Usuario.id == usuario_actual_id)

    if for_update:
        query = query.with_for_update()

    usuario = (await db.execute(query)).scalar_one_or_none()

    if not usuario:
        logger.warning(
            "perfil_no_encontrado",
            extra={
                "usuario_id": usuario_actual_id,
                "for_update": for_update,
            },
        )
        raise app_http_exception(
            status_code=404,
            mensaje="Error: Perfil de usuario no encontrado",
            error_code="USER_PROFILE_NOT_FOUND",
        )

    return usuario


async def actualizar_perfil_usuario(
    db: AsyncSession, usuario: database.Usuario, datos: schemas.ActualizarPerfil
):
    """Lógica para modificar el perfil de usuario (PATCH real).

    Reglas:
    - Si el campo NO viene en el JSON: no se toca en BD.
    - Si el campo viene con valor: se actualiza.
    - Si el campo viene explícitamente como null: se borra (se guarda NULL) SOLO si el campo es borrable.

    Nota importante (Pydantic v2):
    - Para distinguir entre "omitido" y "enviado como null", se usa:
        datos.model_dump(exclude_unset=True)
      Esto devuelve únicamente las claves presentes en la petición.
    """

    # Solo incluye campos presentes en el JSON (incluye explícitos null)
    payload = datos.model_dump(exclude_unset=True)
    campos_actualizados = sorted(payload.keys())

    try:
        # -------------------------
        # Campos opcionales BORRABLES (permiten null)
        # -------------------------

        if "nombre_real" in payload:
            nuevo_nombre_real = payload["nombre_real"]

            if isinstance(nuevo_nombre_real, str):
                nuevo_nombre_real = nuevo_nombre_real.strip()
                if not nuevo_nombre_real:
                    nuevo_nombre_real = None

            if nuevo_nombre_real:
                await text_moderation_service.validar_nombre_real(nuevo_nombre_real)

            usuario.nombre_real = nuevo_nombre_real

        if "genero" in payload:
            g = payload["genero"]
            usuario.genero = g.value if g is not None else None

        if "altura" in payload:
            usuario.altura = payload["altura"]

        if "peso" in payload:
            usuario.peso = payload["peso"]

        if "provincia" in payload:
            p = payload["provincia"]
            usuario.provincia = p.value if p is not None else None

        # -------------------------
        # Campos editables NO borrables (no aceptar null)
        # -------------------------

        if "email" in payload:
            if payload["email"] is None:
                raise app_http_exception(
                    status_code=400,
                    mensaje="Error: El email no puede ser null",
                    error_code="EMAIL_NULL",
                )

            email = str(payload["email"]).strip().lower()

            duplicado = (
                await db.execute(
                    select(database.Usuario).where(
                        database.Usuario.email == email,
                        database.Usuario.id != usuario.id,
                    )
                )
            ).scalar_one_or_none()

            if duplicado:
                logger.warning(
                    "actualizacion_perfil_email_duplicado",
                    extra={
                        "usuario": usuario.nombre_usuario,
                        "usuario_id": usuario.id,
                        "nuevo_email": email,
                    },
                )
                raise app_http_exception(
                    status_code=400,
                    mensaje="Error: El email ya está en uso",
                    error_code="EMAIL_ALREADY_IN_USE",
                )

            usuario.email = email

        if "password" in payload:
            if payload["password"] is None:
                raise app_http_exception(
                    status_code=400,
                    mensaje="Error: La contraseña no puede ser null",
                    error_code="PASSWORD_NULL",
                )

            usuario.password_encriptada = await run_in_threadpool(
                auth.encriptar_password, payload["password"]
            )

            # Seguridad extra: revocar refresh tokens activos del usuario al cambiar contraseña
            ahora = datetime.now(timezone.utc)
            usuario.password_changed_at = ahora
            await db.execute(
                update(database.SesionRefresh)
                .where(
                    database.SesionRefresh.usuario_id == usuario.id,
                    database.SesionRefresh.revocada_en.is_(None),
                )
                .values(revocada_en=ahora)
            )

        if "fecha_nacimiento" in payload:
            if payload["fecha_nacimiento"] is None:
                raise app_http_exception(
                    status_code=400,
                    mensaje="Error: La fecha de nacimiento no puede ser null",
                    error_code="BIRTH_DATE_NULL",
                )
            usuario.fecha_nacimiento = payload["fecha_nacimiento"]

        if "perfil_visible" in payload:
            if payload["perfil_visible"] is None:
                raise app_http_exception(
                    status_code=400,
                    mensaje="Error: perfil_visible no puede ser null",
                    error_code="PROFILE_VISIBILITY_NULL",
                )
            usuario.perfil_visible = payload["perfil_visible"]

        if "objetivo_semanal_metros" in payload:
            if payload["objetivo_semanal_metros"] is None:
                raise app_http_exception(
                    status_code=400,
                    mensaje="Error: El objetivo semanal no puede ser null",
                    error_code="WEEKLY_GOAL_NULL",
                )
            usuario.objetivo_semanal_metros = payload["objetivo_semanal_metros"]

        if "objetivo_mensual_metros" in payload:
            if payload["objetivo_mensual_metros"] is None:
                raise app_http_exception(
                    status_code=400,
                    mensaje="Error: El objetivo mensual no puede ser null",
                    error_code="MONTHLY_GOAL_NULL",
                )
            usuario.objetivo_mensual_metros = payload["objetivo_mensual_metros"]

        await db.commit()

    except HTTPException:
        await db.rollback()
        raise
    except IntegrityError:
        await db.rollback()
        logger.warning(
            "actualizacion_perfil_error_integridad",
            extra={
                "usuario": usuario.nombre_usuario,
                "usuario_id": usuario.id,
                "campos": campos_actualizados,
            },
            exc_info=True,
        )
        raise app_http_exception(
            status_code=400,
            mensaje="Error: El email ya está en uso",
            error_code="EMAIL_ALREADY_IN_USE",
        )
    except Exception:
        await db.rollback()
        raise

    logger.info(
        "perfil_actualizado",
        extra={
            "usuario": usuario.nombre_usuario,
            "usuario_id": usuario.id,
            "campos": campos_actualizados,
            "password_cambiada": "password" in payload,
            "email_cambiado": "email" in payload,
        },
    )

    return {
        "estatus": "success",
        "mensaje": "Perfil de usuario actualizado correctamente",
    }


async def obtener_perfil_publico(db: AsyncSession, nombre_objetivo: str):
    """
    Busca un usuario por nombre para mostrar su ficha pública.
    Solo devuelve datos si el usuario existe y tiene perfil_visible=True.
    """
    # Case-insensitive lookup: permite /perfil/publico/GaLeN aunque el guardado sea "Galen"
    nombre_key = nombre_objetivo.strip().lower()

    usuario = (
        await db.execute(
            select(database.Usuario).where(
                func.lower(database.Usuario.nombre_usuario) == nombre_key
            )
        )
    ).scalar_one_or_none()

    if not usuario:
        logger.info(
            "perfil_publico_no_encontrado",
            extra={
                "nombre_objetivo": nombre_objetivo,
            },
        )
        raise app_http_exception(
            status_code=404,
            mensaje="Error: Usuario no encontrado",
            error_code="USER_NOT_FOUND",
        )

    # LÓGICA DE PRIVACIDAD
    if not usuario.perfil_visible:
        logger.info(
            "perfil_publico_privado",
            extra={
                "usuario_objetivo": usuario.nombre_usuario,
            },
        )
        raise app_http_exception(
            status_code=403,
            mensaje="Error: Este perfil es privado",
            error_code="PROFILE_PRIVATE",
        )

    return usuario


async def buscar_usuario(
    db: AsyncSession,
    termino_busqueda: str,
    usuario_actual_id: int,
    skip: int,
    limit: int,
):
    """
    Busca usuarios cuyo nombre_usuario contenga el término.
    Filtros:
    1. Coincidencia parcial (ilike)
    2. Perfil visible (Privacidad)
    3. Excluye al usuario autenticado
    4. Paginación configurable (skip/limit)
    """
    # Gestiona buscar usuario.
    termino = termino_busqueda.strip()

    if not termino or len(termino) < 3:
        return {
            "items": [],
            "total": 0,
            "skip": skip,
            "limit": limit,
            "has_more": False,
        }

    termino_seguro = (
        termino.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    )

    filtros = (
        database.Usuario.perfil_visible.is_(True),
        database.Usuario.nombre_usuario.ilike(f"%{termino_seguro}%", escape="\\"),
        database.Usuario.id != usuario_actual_id,
    )

    total = (
        await db.execute(
            select(func.count()).select_from(database.Usuario).where(*filtros)
        )
    ).scalar_one()

    usuarios = (
        (
            await db.execute(
                select(database.Usuario)
                .where(*filtros)
                .order_by(
                    func.lower(database.Usuario.nombre_usuario).asc(),
                    database.Usuario.id.asc(),
                )
                .offset(skip)
                .limit(limit)
            )
        )
        .scalars()
        .all()
    )

    logger.debug(
        "busqueda_usuarios_completada",
        extra={
            "usuario_id": usuario_actual_id,
            "termino": termino,
            "skip": skip,
            "limit": limit,
            "total": total,
            "resultados": len(usuarios),
            "has_more": (skip + limit) < total,
        },
    )

    return {
        "items": usuarios,
        "total": total,
        "skip": skip,
        "limit": limit,
        "has_more": (skip + limit) < total,
    }


async def reportar_perfil_inapropiado(
    db: AsyncSession,
    usuario_actual_id: int,
    datos: schemas.ReportePerfilInapropiado,
):
    """Registra un reporte de un usuario contra otro y envía aviso a moderación.

    Comprueba que el usuario reportado exista (búsqueda case-insensitive
    sobre ``nombre_usuario``) y que no sea el propio reportante (no se
    puede reportar a uno mismo). Persiste el reporte en la base de datos
    con los flags de motivo y las observaciones, y delega el aviso al
    buzón de moderación en ``email_service.enviar_reporte_perfil_inapropiado``.

    Args:
        db: sesión asíncrona de SQLAlchemy.
        usuario_actual_id: id del usuario autenticado que lanza el reporte.
        datos: ``ReportePerfilInapropiado`` con el nombre del reportado,
            banderas de motivo y observaciones opcionales.

    Returns:
        ``RespuestaGenerica`` confirmando que el reporte se ha recibido.

    Raises:
        AppHTTPException: 404 ``USER_NOT_FOUND`` si el usuario reportado no existe.
        AppHTTPException: 400 ``CANNOT_REPORT_SELF`` si el usuario se reporta a sí mismo.
    """
    # Gestiona reportar perfil inapropiado.
    usuario_reportante = await obtener_perfil(db, usuario_actual_id)

    nombre_objetivo = datos.nombre_usuario_reportado.strip().lower()
    usuario_reportado = (
        await db.execute(
            select(database.Usuario).where(
                func.lower(database.Usuario.nombre_usuario) == nombre_objetivo
            )
        )
    ).scalar_one_or_none()

    if not usuario_reportado:
        raise app_http_exception(
            status_code=404,
            mensaje="Error: Usuario no encontrado",
            error_code="USER_NOT_FOUND",
        )

    if usuario_reportado.id == usuario_reportante.id:
        raise app_http_exception(
            status_code=400,
            mensaje="Error: No puedes reportarte a ti mismo",
            error_code="CANNOT_REPORT_YOURSELF",
        )

    enviado = await email_service.enviar_reporte_perfil_inapropiado(
        usuario_reportante=usuario_reportante.nombre_usuario,
        usuario_reportado=usuario_reportado.nombre_usuario,
        reportar_nombre=datos.reportar_nombre,
        reportar_foto=datos.reportar_foto,
        observaciones=datos.observaciones,
    )

    if not enviado:
        raise app_http_exception(
            status_code=503,
            mensaje="Error: No se ha podido enviar el reporte",
            error_code="REPORT_EMAIL_SEND_FAILED",
        )

    logger.info(
        "perfil_reportado",
        extra={
            "usuario_reportante_id": usuario_reportante.id,
            "usuario_reportante": usuario_reportante.nombre_usuario,
            "usuario_reportado_id": usuario_reportado.id,
            "usuario_reportado": usuario_reportado.nombre_usuario,
            "reportar_nombre": datos.reportar_nombre,
            "reportar_foto": datos.reportar_foto,
            "con_observaciones": bool(datos.observaciones),
        },
    )

    return {
        "estatus": "success",
        "mensaje": "Reporte enviado correctamente",
    }


async def eliminar_cuenta(db: AsyncSession, usuario: database.Usuario):
    """Elimina permanentemente el registro de la base de datos.

    Antes del DELETE, revoca explícitamente los refresh tokens activos
    para dejar registro limpio de revocación (revocada_en) en vez de depender
    solo del CASCADE.
    Nota: el access token activo sigue válido hasta su expiración natural
    (hasta ACCESS_TOKEN_EXPIRE_MINUTES). Para invalidación inmediata haría
    falta una blacklist en memoria.
    """
    # Elimina cuenta.
    try:
        ahora = datetime.now(timezone.utc)
        await db.execute(
            update(database.SesionRefresh)
            .where(
                database.SesionRefresh.usuario_id == usuario.id,
                database.SesionRefresh.revocada_en.is_(None),
            )
            .values(revocada_en=ahora)
        )

        await db.delete(usuario)
        await db.commit()
    except Exception:
        await db.rollback()
        raise

    logger.info(
        "cuenta_eliminada",
        extra={
            "usuario": usuario.nombre_usuario,
            "usuario_id": usuario.id,
        },
    )

    return {"estatus": "success", "mensaje": "Cuenta eliminada correctamente"}


async def obtener_ranking(db: AsyncSession, provincia: Optional[str] = None):
    """Obtiene el ranking de usuarios con posición explícita dentro del ámbito consultado.

    La posición se calcula siempre después de aplicar el filtro de provincia
    (si existe) y tras ordenar por metros descendentes. De este modo, el mismo
    usuario puede tener una posición nacional y otra provincial distintas sin
    que la app tenga que inferirlas a partir del índice visual de la lista.
    """
    # Obtiene ranking.
    query = select(
        database.Usuario.nombre_usuario,
        database.Usuario.foto_perfil,
        database.Usuario.total_metros,
        database.Usuario.foto_fecha_actualizacion,
    ).where(database.Usuario.perfil_visible.is_(True))

    if provincia:
        query = query.where(database.Usuario.provincia == provincia)

    query = query.order_by(desc(database.Usuario.total_metros)).limit(15)

    resultados = (await db.execute(query)).all()

    ranking = []
    for posicion, (nombre_usuario, foto_perfil, total_metros, foto_fecha) in enumerate(
        resultados,
        start=1,
    ):
        puntos = calculos.calcular_puntos_nivel(total_metros)
        foto_version = int(foto_fecha.timestamp()) if foto_fecha else 0
        ranking.append(
            {
                "posicion": posicion,
                "nombre_usuario": nombre_usuario,
                "foto_perfil": foto_perfil,
                "foto_version": foto_version,
                "total_puntos": puntos,
                "total_metros": total_metros,
            }
        )

    logger.debug(
        "ranking_generado",
        extra={
            "provincia": provincia,
            "resultados": len(ranking),
        },
    )

    return ranking
