# services/access_service.py

"""Implementa la lógica de negocio de este servicio."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import hashlib
import hmac
import logging
import secrets
import uuid

from fastapi import BackgroundTasks, HTTPException
from sqlalchemy import and_, or_, select, update, func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import delete as sa_delete
from starlette.concurrency import run_in_threadpool

import auth
import database
import schemas
from config import settings
from exceptions import app_http_exception
from services import email_service
from typing import Optional

logger = logging.getLogger("app.auth")


def _ahora_utc() -> datetime:
    """Devuelve el ``datetime`` actual con ``tzinfo=UTC``.

    Se centraliza aquí para que todas las marcas temporales de los
    refresh tokens (emisión, expiración, revocación, último uso)
    se calculen contra la misma referencia y sean fáciles de
    monkey-patchear en tests.

    Returns:
        Fecha y hora actual en UTC.
    """
    return datetime.now(timezone.utc)


def _normalizar_utc(dt: datetime) -> datetime:
    # Por compatibilidad si SQLAlchemy devuelve naive datetime
    """Garantiza que un ``datetime`` tiene ``tzinfo``, asumiendo UTC si no.

    Algunos drivers de SQLAlchemy/PostgreSQL devuelven ``datetime``
    naive aunque la columna sea ``TIMESTAMPTZ``. Para evitar romper
    comparaciones posteriores con valores aware, se les adjunta
    explícitamente ``UTC`` aquí.

    Args:
        dt: ``datetime`` posiblemente naive leído de la base.

    Returns:
        El mismo ``datetime`` con ``tzinfo=UTC`` garantizado.
    """
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def _hash_refresh_token(token: str) -> str:
    """
    Hash del refresh token para guardarlo en BD sin almacenarlo en claro.
    Usamos HMAC-SHA256 con un secreto dedicado (REFRESH_HASH_SECRET).
    """
    key = (settings.REFRESH_HASH_SECRET).encode("utf-8")
    return hmac.new(key, token.encode("utf-8"), hashlib.sha256).hexdigest()


async def _revocar_familia_refresh(db: AsyncSession, familia_id: str):
    """Revoca todos los refresh tokens vivos de una misma familia.

    Una "familia" agrupa los refresh tokens emitidos tras un mismo
    login: al rotar, cada nuevo refresh hereda la misma ``familia_id``.
    Si se detecta que un refresh ya rotado vuelve a usarse (indicio de
    robo), se revoca la familia completa para cortar la cadena.

    No hace commit: lo deja en manos del llamador para que pueda
    combinar la revocación con otras operaciones en la misma transacción.

    Args:
        db: sesión asíncrona de SQLAlchemy.
        familia_id: id común a todos los refresh tokens derivados del mismo login.
    """
    ahora = _ahora_utc()

    await db.execute(
        update(database.SesionRefresh)
        .where(
            database.SesionRefresh.familia_id == familia_id,
            database.SesionRefresh.revocada_en.is_(None),
        )
        .values(revocada_en=ahora)
    )


async def buscar_por_identificador(db: AsyncSession, identificador: str):
    """Busca un usuario por email o por nombre de usuario (case-insensitive).

    Permite que el campo ``identificador`` del login admita cualquiera
    de los dos: en el formulario el usuario escribe lo que recuerde.
    La comparación usa ``LOWER(columna)`` para ser case-insensitive
    incluso cuando los índices son sobre el valor original.

    Args:
        db: sesión asíncrona de SQLAlchemy.
        identificador: cadena que puede ser email o nombre de usuario.

    Returns:
        Fila ``Usuario`` si existe, ``None`` si no se encuentra ninguna coincidencia.
    """
    # Email se guarda en minúsculas. Usuario se guarda como lo escribe el usuario, pero se compara case-insensitive.
    identificador_limpio = identificador.strip().lower()

    return (
        await db.execute(
            select(database.Usuario).where(
                (func.lower(database.Usuario.email) == identificador_limpio)
                | (func.lower(database.Usuario.nombre_usuario) == identificador_limpio)
            )
        )
    ).scalar_one_or_none()


async def buscar_usuario_por_id(db: AsyncSession, usuario_id: int):
    """Busca un usuario por id, lanzando 404 si no existe.

    Se usa en flujos donde ya tenemos un id validado (sub de un token
    ya aceptado) pero queremos tratar como error irrecuperable que el
    usuario haya desaparecido entre emisión del token y esta llamada
    (p. ej. cuenta borrada hace segundos).

    Args:
        db: sesión asíncrona de SQLAlchemy.
        usuario_id: id numérico del usuario.

    Returns:
        Fila ``Usuario``.

    Raises:
        AppHTTPException: 404 ``USER_NOT_FOUND`` si no se encuentra el usuario.
    """
    # Gestiona buscar usuario por identificador.
    usuario = (
        await db.execute(
            select(database.Usuario).where(database.Usuario.id == usuario_id)
        )
    ).scalar_one_or_none()

    if not usuario:
        raise app_http_exception(
            status_code=404,
            mensaje="Error: Usuario no encontrado",
            error_code="USER_NOT_FOUND",
        )

    return usuario


async def crear_sesion_login(db: AsyncSession, usuario: database.Usuario):
    """
    Crea una sesión de login completa:
    - access token (corto)
    - refresh token (largo)
    - registro de refresh en DB (hash)
    """
    # Construye sesion login.
    ahora = _ahora_utc()
    jti = uuid.uuid4().hex
    familia_id = uuid.uuid4().hex

    refresh_token = auth.crear_token_refresh(usuario.id, jti, familia_id)
    refresh_hash = _hash_refresh_token(refresh_token)

    sesion = database.SesionRefresh(
        usuario_id=usuario.id,
        jti=jti,
        familia_id=familia_id,
        token_hash=refresh_hash,
        creada_en=ahora,
        ultimo_uso_en=ahora,
        expira_en=ahora + timedelta(days=auth.REFRESH_TOKEN_EXPIRE_DAYS),
        revocada_en=None,
        reemplazada_por_jti=None,
    )

    try:
        await _limpiar_sesiones_refresh_usuario(db, usuario.id)
        db.add(sesion)
        await db.commit()
    except Exception:
        await db.rollback()
        raise

    logger.info(
        "sesion_login_creada",
        extra={
            "usuario": usuario.nombre_usuario,
            "usuario_id": usuario.id,
            "jti": jti,
            "familia_id": familia_id,
            "refresh_expira_dias": auth.REFRESH_TOKEN_EXPIRE_DAYS,
        },
    )

    token_acceso = auth.crear_token_acceso({"sub": str(usuario.id)})

    return {
        "estatus": "success",
        "nombre_usuario": usuario.nombre_usuario,
        "token_acceso": token_acceso,
        "refresh_token": refresh_token,
    }


def _hash_codigo_recuperacion(codigo: str) -> str:
    """
    Hash HMAC-SHA256 del código OTP.
    Así, si alguien roba la BD, no puede verificar códigos sin el secreto.
    """
    key = (settings.CODE_HASH_SECRET).encode("utf-8")
    return hmac.new(key, codigo.encode("utf-8"), hashlib.sha256).hexdigest()


def _mensaje_recuperacion_generico(locale: str) -> str:
    """Devuelve la frase neutra de respuesta del endpoint de recuperación.

    El backend responde siempre lo mismo independientemente de si el
    email existe, está vinculado a Google o no aparece registrado.
    Centralizar el texto aquí evita discrepancias entre ramas que
    podrían ser explotadas para enumerar cuentas.

    Args:
        locale: ``"es"`` o ``"en"``; cualquier otro valor cae a español.

    Returns:
        Texto localizado del mensaje neutro.
    """
    if locale == "en":
        return (
            "If the account supports recovery, you will receive instructions by email."
        )
    return "Si la cuenta admite recuperación, recibirás instrucciones por correo."


def _safe_log_usuario_id(usuario: object) -> int | None:
    """Devuelve el id del usuario si es un entero positivo, o ``None`` si no.

    Se usa para alimentar el campo ``usuario_id`` de los logs
    estructurados. Blindar esta lectura evita que un ``MagicMock`` en
    tests, o una fila parcialmente cargada, acaben serializando objetos
    extraños a los logs.

    Args:
        usuario: cualquier objeto con (o sin) atributo ``id``.

    Returns:
        ``id`` entero positivo del usuario, o ``None`` si no es un entero válido.
    """
    valor = getattr(usuario, "id", None)
    return valor if isinstance(valor, int) and valor > 0 else None


async def _usuario_tiene_vinculo_google(db: AsyncSession, usuario_id: object) -> bool:
    """
    Devuelve ``True`` solo si existe un vínculo Google real en BD.

    Notas:
    - En tests con ``MagicMock``/``AsyncMock`` no debemos interpretar valores simulados
      como si fuesen vínculos sociales reales.
    - Si el resultado de ``db.execute`` no expone ``scalar_one_or_none()`` de forma
      válida, se considera que no existe vínculo.
    """
    # Gestiona usuario tiene vinculo google.
    if not isinstance(usuario_id, int) or usuario_id <= 0:
        return False

    result = await db.execute(
        select(database.UsuarioAuthSocial.id)
        .where(
            database.UsuarioAuthSocial.usuario_id == usuario_id,
            database.UsuarioAuthSocial.provider
            == schemas.ProveedorAuthSocial.GOOGLE.value,
        )
        .limit(1)
    )

    scalar_one_or_none = getattr(result, "scalar_one_or_none", None)
    if not callable(scalar_one_or_none):
        return False

    vinculo_id = scalar_one_or_none()
    return isinstance(vinculo_id, int) and vinculo_id > 0


async def refrescar_sesion(db: AsyncSession, refresh_token: str):
    """
    Valida y rota el refresh token.
    Invalida el refresh anterior y emite uno nuevo + access nuevo.
    """
    payload = auth.decodificar_token_refresh(refresh_token)

    usuario_id_token = payload.get("sub")
    jti = payload.get("jti")
    familia_id = payload.get("fam")

    if not isinstance(usuario_id_token, str) or not usuario_id_token.isdigit():
        raise app_http_exception(
            status_code=401,
            mensaje="Error: Refresh token inválido (sub)",
            error_code="REFRESH_TOKEN_INVALID_SUB",
        )
    if not isinstance(jti, str) or not jti:
        raise app_http_exception(
            status_code=401,
            mensaje="Error: Refresh token inválido (jti)",
            error_code="REFRESH_TOKEN_INVALID_JTI",
        )
    if not isinstance(familia_id, str) or not familia_id:
        raise app_http_exception(
            status_code=401,
            mensaje="Error: Refresh token inválido (familia)",
            error_code="REFRESH_TOKEN_INVALID_FAMILY",
        )

    usuario_id_token = int(usuario_id_token)

    async def _commit_or_rollback():
        """Commit con rollback automático ante error, manteniendo la transacción consistente.

        Se extrae como función anidada porque este patrón se repite en
        varios puntos de ``refrescar_sesion`` (revocar, rotar, guardar
        métricas de uso). Al fallar, deshace la transacción y re-lanza la
        excepción para que el handler superior responda con un 5xx.

        Raises:
            Exception: la misma que haya lanzado el commit original, tras hacer rollback.
        """
        try:
            await db.commit()
        except Exception:
            await db.rollback()
            raise

    # Bloqueo de fila para evitar race condition: 2 refresh simultáneos con el mismo token
    # podrían rotar el token dos veces si no se bloquea la sesión.
    sesion = (
        await db.execute(
            select(database.SesionRefresh)
            .where(database.SesionRefresh.jti == jti)
            .with_for_update()
        )
    ).scalar_one_or_none()

    if not sesion:
        logger.warning(
            "sesion_refresh_no_encontrada",
            extra={
                "usuario_id": usuario_id_token,
                "jti": jti,
                "familia_id": familia_id,
            },
        )
        raise app_http_exception(
            status_code=401,
            mensaje="Error: Refresh token inválido",
            error_code="REFRESH_TOKEN_INVALID",
        )

    refresh_hash = _hash_refresh_token(refresh_token)
    if not hmac.compare_digest(str(sesion.token_hash), refresh_hash):
        logger.warning(
            "hash_refresh_no_coincide",
            extra={
                "jti": jti,
                "familia_id": sesion.familia_id,
                "usuario_id": sesion.usuario_id,
            },
        )
        # Token manipulado / no coincide con el registrado
        await _revocar_familia_refresh(db, sesion.familia_id)
        await _commit_or_rollback()
        raise app_http_exception(
            status_code=401,
            mensaje="Error: Refresh token inválido o reutilizado",
            error_code="REFRESH_TOKEN_INVALID_OR_REUSED",
        )

    if sesion.revocada_en is not None:
        logger.warning(
            "reutilizacion_refresh_detectada",
            extra={
                "jti": sesion.jti,
                "familia_id": sesion.familia_id,
                "usuario_id": sesion.usuario_id,
            },
        )
        # Reutilización de token rotado/revocado => revocamos toda la familia
        await _revocar_familia_refresh(db, sesion.familia_id)
        await _commit_or_rollback()
        raise app_http_exception(
            status_code=401,
            mensaje="Error: Refresh token reutilizado",
            error_code="REFRESH_TOKEN_REUSED",
        )

    ahora = _ahora_utc()
    if ahora > _normalizar_utc(sesion.expira_en):
        logger.info(
            "refresh_expirado",
            extra={
                "jti": sesion.jti,
                "familia_id": sesion.familia_id,
                "usuario_id": sesion.usuario_id,
            },
        )
        sesion.revocada_en = ahora
        await _commit_or_rollback()
        raise app_http_exception(
            status_code=401,
            mensaje="Error: Refresh token expirado",
            error_code="REFRESH_TOKEN_EXPIRED",
        )

    usuario = (
        await db.execute(
            select(database.Usuario).where(database.Usuario.id == sesion.usuario_id)
        )
    ).scalar_one_or_none()

    if not usuario:
        logger.warning(
            "usuario_refresh_no_encontrado",
            extra={
                "usuario_id": sesion.usuario_id,
                "jti": sesion.jti,
                "familia_id": sesion.familia_id,
            },
        )
        sesion.revocada_en = ahora
        await _commit_or_rollback()
        raise app_http_exception(
            status_code=401,
            mensaje="Error: Usuario no encontrado",
            error_code="USER_NOT_FOUND",
        )

    # Rotación: invalidar refresh actual y crear uno nuevo en la misma familia
    nuevo_jti = uuid.uuid4().hex
    nuevo_refresh_token = auth.crear_token_refresh(
        usuario.id, nuevo_jti, sesion.familia_id
    )
    nuevo_refresh_hash = _hash_refresh_token(nuevo_refresh_token)

    nueva_sesion = database.SesionRefresh(
        usuario_id=usuario.id,
        jti=nuevo_jti,
        familia_id=sesion.familia_id,
        token_hash=nuevo_refresh_hash,
        creada_en=ahora,
        ultimo_uso_en=ahora,
        expira_en=ahora + timedelta(days=auth.REFRESH_TOKEN_EXPIRE_DAYS),
        revocada_en=None,
        reemplazada_por_jti=None,
    )

    sesion.ultimo_uso_en = ahora
    sesion.revocada_en = ahora
    sesion.reemplazada_por_jti = nuevo_jti

    await _limpiar_sesiones_refresh_usuario(db, usuario.id)
    db.add(nueva_sesion)
    await _commit_or_rollback()

    logger.info(
        "sesion_refresh_rotada",
        extra={
            "usuario": usuario.nombre_usuario,
            "usuario_id": usuario.id,
            "jti_antiguo": jti,
            "jti_nuevo": nuevo_jti,
            "familia_id": sesion.familia_id,
        },
    )

    nuevo_token_acceso = auth.crear_token_acceso({"sub": str(usuario.id)})

    return {
        "estatus": "success",
        "nombre_usuario": usuario.nombre_usuario,
        "token_acceso": nuevo_token_acceso,
        "refresh_token": nuevo_refresh_token,
    }


async def _limpiar_sesiones_refresh_usuario(
    db: AsyncSession, usuario_id: int, older_than_days: Optional[int] = None
):
    """Elimina refresh tokens viejos de un usuario para no acumular basura.

    Borra filas que cumplan simultáneamente:

    - Están revocadas o expiradas.
    - Y su ``ultimo_uso_en`` es más antiguo que ``older_than_days`` (o
      ``NULL``, es decir nunca usadas).

    Esto mantiene el histórico reciente útil para auditoría y limita el
    crecimiento indefinido de la tabla. El llamador decide cuándo
    ejecutarlo (por ejemplo tras cada login exitoso) y si hace commit.

    Args:
        db: sesión asíncrona de SQLAlchemy.
        usuario_id: id del usuario sobre el que se limpia.
        older_than_days: días de antigüedad mínima para borrar. Si es ``None`` usa ``settings.REFRESH_SESSION_CLEANUP_DAYS``.
    """
    # Normaliza sesiones refresco usuario.
    if older_than_days is None:
        older_than_days = int(settings.REFRESH_SESSION_CLEANUP_DAYS)

    ahora = _ahora_utc()
    cutoff = ahora - timedelta(days=older_than_days)

    await db.execute(
        sa_delete(database.SesionRefresh).where(
            and_(
                database.SesionRefresh.usuario_id == usuario_id,
                or_(
                    database.SesionRefresh.revocada_en.is_not(None),
                    database.SesionRefresh.expira_en < ahora,
                ),
                or_(
                    database.SesionRefresh.ultimo_uso_en < cutoff,
                    database.SesionRefresh.ultimo_uso_en.is_(None),
                ),
            )
        )
    )


async def cerrar_sesion(db: AsyncSession, refresh_token: str):
    """
    Revoca la sesión actual a partir del refresh token.
    Idempotente (si ya está revocado o es inválido, respondemos éxito).
    """
    try:
        payload = auth.decodificar_token_refresh(refresh_token)
    except HTTPException as exc:
        if getattr(exc, "error_code", None) != "REFRESH_TOKEN_INVALID_OR_EXPIRED":
            raise
        logger.info(
            "logout_idempotente_refresh_invalido",
            extra={},
        )
        # Idempotencia: no revelamos demasiado
        return {"estatus": "success", "mensaje": "Sesión cerrada"}

    jti = payload.get("jti")
    if not isinstance(jti, str) or not jti:
        logger.warning(
            "logout_payload_refresh_invalido",
            extra={},
        )
        return {"estatus": "success", "mensaje": "Sesión cerrada"}

    sesion = (
        await db.execute(
            select(database.SesionRefresh).where(database.SesionRefresh.jti == jti)
        )
    ).scalar_one_or_none()

    if not sesion:
        logger.info(
            "logout_idempotente_sesion_no_encontrada",
            extra={
                "jti": jti,
            },
        )
        return {"estatus": "success", "mensaje": "Sesión cerrada"}

    # Validamos hash para evitar revocar jti con token distinto manipulado
    if not hmac.compare_digest(
        str(sesion.token_hash), _hash_refresh_token(refresh_token)
    ):
        logger.warning(
            "logout_hash_refresh_no_coincide",
            extra={
                "jti": jti,
                "usuario_id": sesion.usuario_id,
            },
        )
        return {"estatus": "success", "mensaje": "Sesión cerrada"}

    if sesion.revocada_en is None:
        ahora = _ahora_utc()
        sesion.revocada_en = ahora
        sesion.ultimo_uso_en = ahora
        try:
            await db.commit()
        except Exception:
            await db.rollback()
            raise

        logger.info(
            "logout_correcto",
            extra={
                "usuario_id": sesion.usuario_id,
                "jti": sesion.jti,
                "familia_id": sesion.familia_id,
            },
        )
    else:
        logger.info(
            "logout_idempotente_ya_revocado",
            extra={
                "usuario_id": sesion.usuario_id,
                "jti": sesion.jti,
                "familia_id": sesion.familia_id,
            },
        )

    return {"estatus": "success", "mensaje": "Sesión cerrada"}


async def generar_codigo_recuperacion(
    db: AsyncSession,
    email: str,
    background_tasks: BackgroundTasks,
    locale: str,
):
    """Inicia el flujo de recuperación sin revelar el estado de la cuenta.

    La respuesta es siempre neutra (``_mensaje_recuperacion_generico``),
    tanto si el email no existe, como si la cuenta es de Google, como
    si se ha generado un código nuevo. El comportamiento diferencial
    ocurre solo en el correo enviado:

    - **Email no registrado**: no envía nada, solo registra un log
      informativo. El atacante no puede enumerar cuentas por el tiempo
      de respuesta porque no se hace ningún trabajo extra.
    - **Cuenta vinculada a Google**: limpia cualquier código pendiente y
      envía el aviso explicando que debe usar "Continuar con Google",
      para que solo el dueño del buzón vea el tipo de cuenta.
    - **Cuenta local**: genera un código de 6 dígitos con validez
      configurable (``RECOVERY_CODE_EXPIRE_MINUTES``) y lo guarda
      hasheado (``_hash_codigo_recuperacion``) junto con su expiración.
      Aplica un cooldown de 60 s desde el último envío para no spamear
      al usuario si pulsa "reenviar" varias veces seguidas.

    El email se envía con ``BackgroundTasks`` para no bloquear la
    respuesta esperando al SMTP.

    Args:
        db: sesión asíncrona de SQLAlchemy.
        email: email solicitado por el usuario (se normaliza a minúsculas).
        background_tasks: acumulador de tareas para diferir el envío del email.
        locale: idioma preferido del usuario, se normaliza vía ``SolicitarPassword`` a ``"es"``/``"en"``.

    Returns:
        Diccionario ``{"estatus": "success", "mensaje": <texto neutro>}`` independiente de la rama interna.
    """
    email_normalizado = email.strip().lower()
    locale_normalizado = schemas.SolicitarPassword.model_validate(
        {"email": email_normalizado, "locale": locale}
    ).locale

    usuario = (
        await db.execute(
            select(database.Usuario)
            .where(database.Usuario.email == email_normalizado)
            .with_for_update()
        )
    ).scalar_one_or_none()

    # Si existe el correo, mantenemos respuesta neutra pero diferenciamos el correo enviado.
    if usuario:
        tiene_google = await _usuario_tiene_vinculo_google(db, int(usuario.id))

        if tiene_google:
            cambios_pendientes = (
                usuario.codigo_recuperacion is not None
                or usuario.codigo_expiracion is not None
            )
            usuario.codigo_recuperacion = None
            usuario.codigo_expiracion = None

            if cambios_pendientes:
                try:
                    await db.commit()
                except Exception:
                    await db.rollback()
                    raise

            background_tasks.add_task(
                email_service.enviar_aviso_recuperacion_google,
                email_normalizado,
                locale_normalizado,
            )

            logger.info(
                "recuperacion_password_cuenta_google",
                extra={
                    "usuario_id": _safe_log_usuario_id(usuario),
                    "email": email_normalizado,
                    "provider": "google",
                    "locale": locale_normalizado,
                },
            )
        else:
            ahora = _ahora_utc()
            if usuario.codigo_expiracion and usuario.codigo_recuperacion:
                expiracion_actual = _normalizar_utc(usuario.codigo_expiracion)
                emitido_en = expiracion_actual - timedelta(
                    minutes=int(settings.RECOVERY_CODE_EXPIRE_MINUTES)
                )
                if expiracion_actual > ahora and (ahora - emitido_en) < timedelta(seconds=60):
                    logger.info(
                        "codigo_recuperacion_omitido_por_cooldown",
                        extra={
                            "usuario_id": usuario.id,
                            "email": email_normalizado,
                            "locale": locale_normalizado,
                        },
                    )
                    return {
                        "estatus": "success",
                        "mensaje": _mensaje_recuperacion_generico(locale_normalizado),
                    }

            # Genera un código aleatorio con validez de 15 minutos.
            codigo = f"{secrets.randbelow(900000) + 100000:06d}"
            usuario.codigo_recuperacion = _hash_codigo_recuperacion(codigo)
            usuario.codigo_expiracion = ahora + timedelta(
                minutes=int(settings.RECOVERY_CODE_EXPIRE_MINUTES)
            )

            try:
                await db.commit()
            except Exception:
                await db.rollback()
                raise

            background_tasks.add_task(
                email_service.enviar_codigo_recuperacion,
                email_normalizado,
                codigo,
                int(settings.RECOVERY_CODE_EXPIRE_MINUTES),
                locale_normalizado,
            )

            logger.info(
                "codigo_recuperacion_generado",
                extra={
                    "usuario_id": usuario.id,
                    "email": email_normalizado,
                    "expira_minutos": int(settings.RECOVERY_CODE_EXPIRE_MINUTES),
                    "locale": locale_normalizado,
                },
            )
    else:
        logger.info(
            "recuperacion_password_email_no_registrado",
            extra={
                "email": email_normalizado,
                "locale": locale_normalizado,
            },
        )

    return {
        "estatus": "success",
        "mensaje": _mensaje_recuperacion_generico(locale_normalizado),
    }


async def resetear_password(db: AsyncSession, datos: schemas.ConfirmarPassword):
    """Valida un código de recuperación y actualiza la contraseña del usuario.

    Flujo:

    1. Hashea el código recibido (``_hash_codigo_recuperacion``) y
       busca al usuario por email con ese hash guardado. Así nunca
       se compara el código en claro y un dump de la base no basta
       para suplantar identidades.
    2. Verifica que el código no haya expirado contra
       ``codigo_expiracion`` normalizado a UTC.
    3. Encripta la nueva contraseña con bcrypt y la persiste.
    4. Limpia los campos de código para que no se pueda reutilizar, y
       actualiza ``password_changed_at`` con la hora actual: esto
       invalida automáticamente los access tokens anteriores del
       usuario (ver ``auth.obtener_usuario_actual``).
    5. Revoca todas las sesiones de refresh activas para forzar al
       usuario a hacer login en todos sus dispositivos.

    Args:
        db: sesión asíncrona de SQLAlchemy.
        datos: ``ConfirmarPassword`` con ``email``, ``codigo`` y ``nueva_password``.

    Returns:
        ``RespuestaGenerica`` confirmando el cambio si todo ha ido bien.

    Raises:
        AppHTTPException: 400 ``INVALID_RECOVERY_CODE`` si email+código no coinciden con ningún usuario.
        AppHTTPException: 400 ``RECOVERY_CODE_EXPIRED`` si el código existe pero ha caducado.
    """
    # Hashear el código recibido para compararlo con el hash guardado
    codigo_hash = _hash_codigo_recuperacion(datos.codigo)

    usuario = (
        await db.execute(
            select(database.Usuario)
            .where(
                database.Usuario.email == datos.email.lower(),
                database.Usuario.codigo_recuperacion == codigo_hash,
            )
            .with_for_update()
        )
    ).scalar_one_or_none()

    if not usuario or not usuario.codigo_expiracion:
        logger.warning(
            "reset_password_codigo_o_email_invalidos",
            extra={
                "email": datos.email.lower(),
            },
        )
        raise app_http_exception(
            status_code=400,
            mensaje="Error: Código o email inválidos",
            error_code="RECOVERY_CODE_OR_EMAIL_INVALID",
        )

    if _ahora_utc() > _normalizar_utc(usuario.codigo_expiracion):
        logger.info(
            "reset_password_codigo_expirado",
            extra={
                "usuario_id": usuario.id,
                "email": datos.email.lower(),
            },
        )
        raise app_http_exception(
            status_code=400,
            mensaje="Error: El código ha expirado",
            error_code="CODE_EXPIRED",
        )

    if await _usuario_tiene_vinculo_google(db, int(usuario.id)):
        try:
            usuario.codigo_recuperacion = None
            usuario.codigo_expiracion = None
            await db.commit()
        except Exception:
            await db.rollback()
            raise

        logger.info(
            "reset_password_rechazado_cuenta_google",
            extra={
                "usuario_id": _safe_log_usuario_id(usuario),
                "email": datos.email.lower(),
                "provider": "google",
            },
        )
        raise app_http_exception(
            status_code=400,
            mensaje="Error: Código o email inválidos",
            error_code="RECOVERY_CODE_OR_EMAIL_INVALID",
            detail={
                "mensaje": "Error: Código o email inválidos",
                "error_code": "RECOVERY_CODE_OR_EMAIL_INVALID",
            },
        )

    try:
        usuario.password_encriptada = await run_in_threadpool(
            auth.encriptar_password, datos.nueva_password
        )
        usuario.codigo_recuperacion = None
        usuario.codigo_expiracion = None

        # Seguridad extra: revocar refresh tokens activos del usuario al cambiar contraseña
        ahora = _ahora_utc()
        usuario.password_changed_at = ahora
        await db.execute(
            update(database.SesionRefresh)
            .where(
                database.SesionRefresh.usuario_id == usuario.id,
                database.SesionRefresh.revocada_en.is_(None),
            )
            .values(revocada_en=ahora)
        )
        await db.commit()
    except Exception:
        await db.rollback()
        raise

    logger.info(
        "password_actualizada_correctamente",
        extra={
            "usuario": usuario.nombre_usuario,
            "usuario_id": usuario.id,
            "tokens_refresh_revocados": True,
        },
    )

    return {"estatus": "success", "mensaje": "Contraseña actualizada correctamente"}
