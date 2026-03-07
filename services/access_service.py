# services/access_service.py

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import hashlib
import hmac
import secrets
import uuid

from fastapi import BackgroundTasks, HTTPException
from sqlalchemy import select, update, func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import delete as sa_delete
from starlette.concurrency import run_in_threadpool

import auth
import database
import schemas
from config import settings
from services import email_service
from typing import Optional

def _ahora_utc() -> datetime:
    return datetime.now(timezone.utc)

def _normalizar_utc(dt: datetime) -> datetime:
    # Por compatibilidad si SQLAlchemy devuelve naive datetime
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)

def _hash_refresh_token(token: str) -> str:
    """
    Hash del refresh token para guardarlo en BD sin almacenarlo en claro.
    Usamos HMAC-SHA256 con un secreto dedicado (REFRESH_HASH_SECRET).
    """
    key = (settings.REFRESH_HASH_SECRET).encode("utf-8")
    return hmac.new(key, token.encode("utf-8"), hashlib.sha256).hexdigest()

async def _revocar_familia_refresh(db: AsyncSession, familia_id: str):
    ahora = _ahora_utc()

    await db.execute(
        update(database.SesionRefresh)
        .where(
            database.SesionRefresh.familia_id == familia_id,
            database.SesionRefresh.revocada_en.is_(None)
        )
        .values(revocada_en=ahora)
    )

async def buscar_por_identificador(db: AsyncSession, identificador: str):
    """Búsqueda para login (email o nombre de usuario)."""
    # Email se guarda en minúsculas. Usuario se guarda como lo escribe el usuario, pero se compara case-insensitive.
    identificador_limpio = identificador.strip().lower()

    return (await db.execute(
        select(database.Usuario).where(
            (database.Usuario.email == identificador_limpio) |
            (func.lower(database.Usuario.nombre_usuario) == identificador_limpio)
        )
    )).scalar_one_or_none()

async def crear_sesion_login(db: AsyncSession, usuario: database.Usuario):
    """
    Crea una sesión de login completa:
    - access token (corto)
    - refresh token (largo)
    - registro de refresh en DB (hash)
    """
    ahora = _ahora_utc()
    jti = uuid.uuid4().hex
    familia_id = uuid.uuid4().hex

    refresh_token = auth.crear_token_refresh(usuario.nombre_usuario, jti, familia_id)
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
        reemplazada_por_jti=None
    )
    
    await _limpiar_sesiones_refresh_usuario(db, usuario.id)
    db.add(sesion)
    await db.commit()

    token_acceso = auth.crear_token_acceso({"sub": usuario.nombre_usuario})

    return {
        "estatus": "success",
        "nombre_usuario": usuario.nombre_usuario,
        "token_acceso": token_acceso,
        "refresh_token": refresh_token
    }

def _hash_codigo_recuperacion(codigo: str) -> str:
    """
    Hash HMAC-SHA256 del código OTP.
    Así, si alguien roba la BD, no puede verificar códigos sin el secreto.
    """
    key = (settings.CODE_HASH_SECRET).encode("utf-8")
    return hmac.new(key, codigo.encode("utf-8"), hashlib.sha256).hexdigest()

async def refrescar_sesion(db: AsyncSession, refresh_token: str):
    """
    Valida y rota el refresh token.
    Invalida el refresh anterior y emite uno nuevo + access nuevo.
    """
    payload = auth.decodificar_token_refresh(refresh_token)

    nombre_usuario = payload.get("sub")
    jti = payload.get("jti")
    familia_id = payload.get("fam")

    if not isinstance(nombre_usuario, str) or not nombre_usuario:
        raise HTTPException(status_code=401, detail="Error: Refresh token inválido (sub)")
    if not isinstance(jti, str) or not jti:
        raise HTTPException(status_code=401, detail="Error: Refresh token inválido (jti)")
    if not isinstance(familia_id, str) or not familia_id:
        raise HTTPException(status_code=401, detail="Error: Refresh token inválido (familia)")

    # Bloqueo de fila para evitar race condition: 2 refresh simultáneos con el mismo token
    # podrían rotar el token dos veces si no se bloquea la sesión.
    sesion = (await db.execute(
        select(database.SesionRefresh)
        .where(database.SesionRefresh.jti == jti)
        .with_for_update()
    )).scalar_one_or_none()

    if not sesion:
        raise HTTPException(status_code=401, detail="Error: Refresh token inválido")

    refresh_hash = _hash_refresh_token(refresh_token)
    if not hmac.compare_digest(str(sesion.token_hash), refresh_hash):
        # Token manipulado / no coincide con el registrado
        await _revocar_familia_refresh(db, sesion.familia_id)
        await db.commit()
        raise HTTPException(status_code=401, detail="Error: Refresh token inválido o reutilizado")

    if sesion.revocada_en is not None:
        # Reutilización de token rotado/revocado => revocamos toda la familia
        await _revocar_familia_refresh(db, sesion.familia_id)
        await db.commit()
        raise HTTPException(status_code=401, detail="Error: Refresh token reutilizado")

    ahora = _ahora_utc()
    if ahora > _normalizar_utc(sesion.expira_en):
        sesion.revocada_en = ahora
        await db.commit()
        raise HTTPException(status_code=401, detail="Error: Refresh token expirado")

    usuario = (await db.execute(
        select(database.Usuario).where(database.Usuario.id == sesion.usuario_id)
    )).scalar_one_or_none()

    if not usuario:
        sesion.revocada_en = ahora
        await db.commit()
        raise HTTPException(status_code=401, detail="Error: Usuario no encontrado")

    # Rotación: invalidar refresh actual y crear uno nuevo en la misma familia
    nuevo_jti = uuid.uuid4().hex
    nuevo_refresh_token = auth.crear_token_refresh(usuario.nombre_usuario, nuevo_jti, sesion.familia_id)
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
        reemplazada_por_jti=None
    )
    
    sesion.ultimo_uso_en = ahora
    sesion.revocada_en = ahora
    sesion.reemplazada_por_jti = nuevo_jti
    
    await _limpiar_sesiones_refresh_usuario(db, usuario.id)
    db.add(nueva_sesion)
    await db.commit()
    
    nuevo_token_acceso = auth.crear_token_acceso({"sub": usuario.nombre_usuario})
    
    return {
        "estatus": "success",
        "nombre_usuario": usuario.nombre_usuario,
        "token_acceso": nuevo_token_acceso,
        "refresh_token": nuevo_refresh_token
    }
    
async def _limpiar_sesiones_refresh_usuario(db: AsyncSession, usuario_id: int, older_than_days: Optional[int] = None):
    if older_than_days is None:
        older_than_days = int(settings.REFRESH_SESSION_CLEANUP_DAYS)
    ahora = _ahora_utc()
    cutoff = ahora - timedelta(days=older_than_days)

    await db.execute(
        sa_delete(database.SesionRefresh).where(
            database.SesionRefresh.usuario_id == usuario_id,

            # Estado: solo revocadas o expiradas
            (database.SesionRefresh.revocada_en.is_not(None)) |
            (database.SesionRefresh.expira_en < ahora),

            # Antigüedad: antiguas o nunca usadas (NULL)
            (database.SesionRefresh.ultimo_uso_en < cutoff) |
            (database.SesionRefresh.ultimo_uso_en.is_(None))
        )
    )

async def cerrar_sesion(db: AsyncSession, refresh_token: str):
    """
    Revoca la sesión actual a partir del refresh token.
    Idempotente (si ya está revocado o es inválido, respondemos éxito).
    """
    try:
        payload = auth.decodificar_token_refresh(refresh_token)
    except HTTPException:
        # Idempotencia: no revelamos demasiado
        return {"estatus": "success", "mensaje": "Sesión cerrada"}

    jti = payload.get("jti")
    if not isinstance(jti, str) or not jti:
        return {"estatus": "success", "mensaje": "Sesión cerrada"}

    sesion = (await db.execute(
        select(database.SesionRefresh).where(database.SesionRefresh.jti == jti)
    )).scalar_one_or_none()

    if not sesion:
        return {"estatus": "success", "mensaje": "Sesión cerrada"}

    # Validamos hash para evitar revocar jti con token distinto manipulado
    if not hmac.compare_digest(str(sesion.token_hash), _hash_refresh_token(refresh_token)):
        return {"estatus": "success", "mensaje": "Sesión cerrada"}

    if sesion.revocada_en is None:
        ahora = _ahora_utc()
        sesion.revocada_en = ahora
        sesion.ultimo_uso_en = ahora
        await db.commit()

    return {"estatus": "success", "mensaje": "Sesión cerrada"}

async def generar_codigo_recuperacion(db: AsyncSession, email: str, background_tasks: BackgroundTasks):
    """Genera el OTP de 6 dígitos y lo envía por email."""
    usuario = (await db.execute(
        select(database.Usuario)
        .where(database.Usuario.email == email.lower())
        .with_for_update()
    )).scalar_one_or_none()

    # Si existe el correo se envía pero el mensaje de respuesta es el mismo para evitar pistas.
    if usuario:
        # Genera un código aleatorio con validez de 15 minutos.
        # Usamos 'secrets' (aleatoriedad criptográfica) y lo formateamos a 6 dígitos.
        codigo = f"{secrets.randbelow(900000) + 100000:06d}"
        # Guardar el HASH en BD (no el código en claro)
        usuario.codigo_recuperacion = _hash_codigo_recuperacion(codigo)
        usuario.codigo_expiracion = _ahora_utc() + timedelta(minutes=int(settings.RECOVERY_CODE_EXPIRE_MINUTES))

        await db.commit()
        # Envia el código por correo al usuario.
        background_tasks.add_task(email_service.enviar_codigo_recuperacion, email, codigo, int(settings.RECOVERY_CODE_EXPIRE_MINUTES))

    return {"estatus": "success", "mensaje": "Si el email corresponde a un usuario recibirá un código"}

async def resetear_password(db: AsyncSession, datos: schemas.ConfirmarPassword):
    """Valida el OTP y actualiza la contraseña."""
    # Hashear el código recibido para compararlo con el hash guardado
    codigo_hash = _hash_codigo_recuperacion(datos.codigo)

    usuario = (await db.execute(
        select(database.Usuario).where(
            database.Usuario.email == datos.email.lower(),
            database.Usuario.codigo_recuperacion == codigo_hash
        ).with_for_update()
    )).scalar_one_or_none()

    if not usuario or not usuario.codigo_expiracion:
        raise HTTPException(status_code=400, detail="Error: Código o email inválidos")

    if _ahora_utc() > _normalizar_utc(usuario.codigo_expiracion):
        raise HTTPException(status_code=400, detail="Error: El código ha expirado")

    usuario.password_encriptada = await run_in_threadpool(auth.encriptar_password, datos.nueva_password)
    usuario.codigo_recuperacion = None
    usuario.codigo_expiracion = None

    # Seguridad extra: revocar refresh tokens activos del usuario al cambiar contraseña
    ahora = _ahora_utc()
    await db.execute(
        update(database.SesionRefresh)
        .where(
            database.SesionRefresh.usuario_id == usuario.id,
            database.SesionRefresh.revocada_en.is_(None)
        )
        .values(revocada_en=ahora)
    )
    await db.commit()
    return {"estatus": "success", "mensaje": "Contraseña actualizada correctamente"}