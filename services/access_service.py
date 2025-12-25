# services/access_service.py

from sqlalchemy.orm import Session
from fastapi import HTTPException
from datetime import datetime, timedelta, timezone
import random
import database
import auth
import schemas
from services import email_service
from fastapi.concurrency import run_in_threadpool

def buscar_por_identificador(db: Session, identificador: str):
    """Búsqueda para login (email o nombre de usuario)."""
    identificador_limpio = identificador.strip()
    return db.query(database.Usuario).filter(
        (database.Usuario.email == identificador_limpio.lower()) | 
        (database.Usuario.nombre_usuario == identificador_limpio)
    ).first()

async def generar_codigo_recuperacion(db: Session, email: str):
    """Genera el OTP de 6 dígitos y lo envía por email."""
    usuario = await run_in_threadpool(
        lambda: db.query(database.Usuario).filter(database.Usuario.email == email.lower()).first()
    )
    
    # Si existe el correo se envía pero pero el mensaje de respuesta es el mismo para evitar pistas.
    if usuario:
        #  genera un código aleatorio con validez de 15 minutos.
        codigo = f"{random.randint(100000, 999999)}"
        usuario.codigo_recuperacion = codigo
        usuario.codigo_expiracion = datetime.now(timezone.utc) + timedelta(minutes=15)
    
        await run_in_threadpool(db.commit)
        # Envia el código por correo al usuario.
        await email_service.enviar_codigo_recuperacion(email, codigo)
    
    return {"estatus": "success", "mensaje": "Si el email corresponde a un usuario recibirá un código"}

def resetear_contraseña(db: Session, datos: schemas.ConfirmarRecuperacion):
    """Valida el OTP y actualiza la contraseña."""
    usuario = db.query(database.Usuario).filter(
        database.Usuario.email == datos.email.lower(),
        database.Usuario.codigo_recuperacion == datos.codigo
    ).first()

    if not usuario or not usuario.codigo_expiracion:
        raise HTTPException(status_code=400, detail="Error: Código o email inválidos")

    if datetime.now(timezone.utc) > usuario.codigo_expiracion.replace(tzinfo=timezone.utc):
        raise HTTPException(status_code=400, detail="Error: El código ha expirado")

    usuario.contraseña_encriptada = auth.encriptar_contraseña(datos.nueva_contraseña)
    usuario.codigo_recuperacion = None
    usuario.codigo_expiracion = None
    
    db.commit()
    return {"estatus": "success", "mensaje": "Contraseña actualizada correctamente"}