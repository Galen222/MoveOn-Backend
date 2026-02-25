# services/access_service.py

from sqlalchemy.orm import Session
from fastapi import HTTPException, BackgroundTasks
from datetime import datetime, timedelta, timezone
from jose import JWTError
import random
import hashlib
import uuid

import database
import auth
import schemas
from services import email_service

def _ahora_utc() -> datetime:
    return datetime.now(timezone.utc)

def _normalizar_utc(dt: datetime) -> datetime:
    # Por compatibilidad si SQLAlchemy devuelve naive datetime
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)

def _hash_refresh_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()

def _revocar_familia_refresh(db: Session, familia_id: str):
    ahora = _ahora_utc()
    sesiones = db.query(database.SesionRefresh).filter(
        database.SesionRefresh.familia_id == familia_id,
        database.SesionRefresh.revocada_en.is_(None)
    ).all()

    for s in sesiones:
        s.revocada_en = ahora

def buscar_por_identificador(db: Session, identificador: str):
    """Búsqueda para login (email o nombre de usuario)."""
    identificador_limpio = identificador.strip()
    return db.query(database.Usuario).filter(
        (database.Usuario.email == identificador_limpio.lower()) |
        (database.Usuario.nombre_usuario == identificador_limpio)
    ).first()

def crear_sesion_login(db: Session, usuario: database.Usuario):
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

    db.add(sesion)
    db.commit()

    token_acceso = auth.crear_token_acceso({"sub": usuario.nombre_usuario})

    return {
        "estatus": "success",
        "nombre_usuario": usuario.nombre_usuario,
        "token_acceso": token_acceso,
        "refresh_token": refresh_token
    }

def refrescar_sesion(db: Session, refresh_token: str):
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

    sesion = db.query(database.SesionRefresh).filter(
        database.SesionRefresh.jti == jti
    ).first()

    if not sesion:
        raise HTTPException(status_code=401, detail="Error: Refresh token inválido")

    refresh_hash = _hash_refresh_token(refresh_token)
    if sesion.token_hash != refresh_hash:
        # Token manipulado / no coincide con el registrado
        _revocar_familia_refresh(db, sesion.familia_id)
        db.commit()
        raise HTTPException(status_code=401, detail="Error: Refresh token inválido o reutilizado")

    if sesion.revocada_en is not None:
        # Reutilización de token rotado/revocado => revocamos toda la familia
        _revocar_familia_refresh(db, sesion.familia_id)
        db.commit()
        raise HTTPException(status_code=401, detail="Error: Refresh token reutilizado")

    ahora = _ahora_utc()
    if ahora > _normalizar_utc(sesion.expira_en):
        sesion.revocada_en = ahora
        db.commit()
        raise HTTPException(status_code=401, detail="Error: Refresh token expirado")

    usuario = db.query(database.Usuario).filter(database.Usuario.id == sesion.usuario_id).first()
    if not usuario:
        sesion.revocada_en = ahora
        db.commit()
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

    db.add(nueva_sesion)
    db.commit()

    nuevo_token_acceso = auth.crear_token_acceso({"sub": usuario.nombre_usuario})

    return {
        "estatus": "success",
        "nombre_usuario": usuario.nombre_usuario,
        "token_acceso": nuevo_token_acceso,
        "refresh_token": nuevo_refresh_token
    }

def cerrar_sesion(db: Session, refresh_token: str):
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

    sesion = db.query(database.SesionRefresh).filter(
        database.SesionRefresh.jti == jti
    ).first()

    if not sesion:
        return {"estatus": "success", "mensaje": "Sesión cerrada"}

    # Validamos hash para evitar revocar jti con token distinto manipulado
    if sesion.token_hash != _hash_refresh_token(refresh_token):
        return {"estatus": "success", "mensaje": "Sesión cerrada"}

    if sesion.revocada_en is None:
        sesion.revocada_en = _ahora_utc()
        sesion.ultimo_uso_en = _ahora_utc()
        db.commit()

    return {"estatus": "success", "mensaje": "Sesión cerrada"}

def generar_codigo_recuperacion(db: Session, email: str, background_tasks: BackgroundTasks):
    """Genera el OTP de 6 dígitos y lo envía por email."""
    usuario = db.query(database.Usuario).filter(database.Usuario.email == email.lower()).first()

    # Si existe el correo se envía pero el mensaje de respuesta es el mismo para evitar pistas.
    if usuario:
        #  genera un código aleatorio con validez de 15 minutos.
        codigo = f"{random.randint(100000, 999999)}"
        usuario.codigo_recuperacion = codigo
        usuario.codigo_expiracion = _ahora_utc() + timedelta(minutes=15)

        db.commit()
        # Envia el código por correo al usuario.
        background_tasks.add_task(email_service.enviar_codigo_recuperacion, email, codigo)

    return {"estatus": "success", "mensaje": "Si el email corresponde a un usuario recibirá un código"}

def resetear_contraseña(db: Session, datos: schemas.ConfirmarContraseña):
    """Valida el OTP y actualiza la contraseña."""
    usuario = db.query(database.Usuario).filter(
        database.Usuario.email == datos.email.lower(),
        database.Usuario.codigo_recuperacion == datos.codigo
    ).first()

    if not usuario or not usuario.codigo_expiracion:
        raise HTTPException(status_code=400, detail="Error: Código o email inválidos")

    if _ahora_utc() > _normalizar_utc(usuario.codigo_expiracion):
        raise HTTPException(status_code=400, detail="Error: El código ha expirado")

    usuario.contraseña_encriptada = auth.encriptar_contraseña(datos.nueva_contraseña)
    usuario.codigo_recuperacion = None
    usuario.codigo_expiracion = None

    # Seguridad extra: revocar refresh tokens activos del usuario al cambiar contraseña
    sesiones_activas = db.query(database.SesionRefresh).filter(
        database.SesionRefresh.usuario_id == usuario.id,
        database.SesionRefresh.revocada_en.is_(None)
    ).all()
    ahora = _ahora_utc()
    for s in sesiones_activas:
        s.revocada_en = ahora

    db.commit()
    return {"estatus": "success", "mensaje": "Contraseña actualizada correctamente"}
