# auth.py

"""
Módulo de Seguridad y Gestión de Tokens.

Gestiona el cifrado de contraseñas mediante bcrypt, la generación de tokens JWT 
para sesiones de usuario y el sistema de validación de handshake.
"""
import os
import bcrypt
from datetime import datetime, timedelta, timezone
from jose import jwt, JWTError
from fastapi import HTTPException, Header
from dotenv import load_dotenv

# Carga de configuración de seguridad
load_dotenv()

# Parámetros de configuración del sistema de tokens
SECRET_KEY = os.getenv("SECRET_KEY", "")
ALGORITHM = os.getenv("ALGORITHM", "HS256")
ACCESS_TOKEN_EXPIRE_MINUTES = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", "1440"))
APP_ID_SECRET = os.getenv("APP_ID_SECRET", "")
APP_SESSION_SECRET = os.getenv("APP_SESSION_SECRET", "")

def encriptar_contraseña(contraseña: str) -> str:
    """Cifra una contraseña de texto plano usando una sal aleatoria de bcrypt."""
    salt = bcrypt.gensalt()
    return bcrypt.hashpw(contraseña.encode('utf-8'), salt).decode('utf-8')

def comprobar_contraseña(contraseña_plana: str, contraseña_encriptada: str) -> bool:
    """Compara una contraseña ingresada con el hash almacenado en la base de datos."""
    return bcrypt.checkpw(contraseña_plana.encode('utf-8'), contraseña_encriptada.encode('utf-8'))

def crear_token_aplicacion() -> str:
    """Genera un token JWT de corta duración (5 min) para el apretón de manos inicial."""
    expiracion = datetime.now(timezone.utc) + timedelta(minutes=5)
    datos_a_cifrar = {"exp": expiracion, "aud": "moveon_app"}
    return jwt.encode(datos_a_cifrar, str(APP_SESSION_SECRET), algorithm=ALGORITHM)

def crear_token_acceso(datos: dict) -> str:
    """Genera el token de acceso final para un usuario autenticado correctamente."""
    datos_copia = datos.copy()
    expiracion = datetime.now(timezone.utc) + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    datos_copia.update({"exp": expiracion})
    return jwt.encode(datos_copia, str(SECRET_KEY), algorithm=ALGORITHM)

def verificar_sesion_aplicacion(x_app_session: str = Header(None)):
    """
    Middleware que valida que la petición contenga un token de handshake válido.
    
    Raises:
        HTTPException: Error 403 si el token falta, es inválido o ha caducado.
    """
    # Validar presencia del encabezado
    if not x_app_session:
        raise HTTPException(status_code=403, detail="Acceso denegado: Falta el token de sesión")
    
    try:
        # Decodificar y validar firma y audiencia del token
        jwt.decode(x_app_session, str(APP_SESSION_SECRET), algorithms=[ALGORITHM], audience="moveon_app")
        return x_app_session
    except JWTError:
        # Error si el token ha sido manipulado o expiró
        raise HTTPException(status_code=403, detail="Acceso denegado: Token inválido o expirado")