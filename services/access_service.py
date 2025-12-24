# services/access_service.py

from sqlalchemy.orm import Session
from fastapi import HTTPException
from datetime import datetime, timedelta, timezone
import random
import database
import auth
import schemas
from services.email_service import EmailService

class AccessService:
    def __init__(self):
        self.email_service = EmailService()

    def buscar_por_identificador(self, db: Session, identificador: str):
        """Búsqueda para login (email o nombre de usuario)."""
        identificador_limpio = identificador.strip()
        return db.query(database.Usuario).filter(
            (database.Usuario.email == identificador_limpio.lower()) | 
            (database.Usuario.nombre_usuario == identificador_limpio)
        ).first()

    async def generar_codigo_recuperacion(self, db: Session, email: str):
        """Genera el OTP de 6 dígitos y lo envía por email."""
        usuario = db.query(database.Usuario).filter(database.Usuario.email == email.lower()).first()
        
        if not usuario:
            return {"estatus": "success", "mensaje": "Si el email existe recibirás un código"}

        codigo = f"{random.randint(100000, 999999)}"
        usuario.codigo_recuperacion = codigo
        usuario.codigo_expiracion = datetime.now(timezone.utc) + timedelta(minutes=15)
        
        db.commit()
        await self.email_service.enviar_codigo_recuperacion(email, codigo)
        
        return {"estatus": "success", "mensaje": "Si el email existe recibirás un código"}

    def resetear_contraseña(self, db: Session, datos: schemas.ConfirmarRecuperacion):
        """Valida el OTP y actualiza la contraseña definitiva."""
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