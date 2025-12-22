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
from fastapi import HTTPException, Header, Depends
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from dotenv import load_dotenv
from typing import Optional, Any

# Carga de configuración de seguridad
load_dotenv()

# Parámetros de configuración del sistema de tokens
SECRET_KEY = os.getenv("SECRET_KEY", "")
ALGORITHM = os.getenv("ALGORITHM", "HS256")
ACCESS_TOKEN_EXPIRE_MINUTES = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", "1440"))
APP_ID_SECRET = os.getenv("APP_ID_SECRET", "")
APP_SESSION_SECRET = os.getenv("APP_SESSION_SECRET", "")

# Instancia de seguridad que activa el botón "Authorize" en Swagger
security_scheme = HTTPBearer()

def encriptar_contraseña(contraseña: str) -> str:
    """Cifra una contraseña de texto plano usando bcrypt."""
    salt = bcrypt.gensalt()
    return bcrypt.hashpw(contraseña.encode('utf-8'), salt).decode('utf-8')

def comprobar_contraseña(contraseña_plana: str, contraseña_encriptada: str) -> bool:
    """Compara una contraseña plana ingresada con el hash almacenado en la base de datos."""
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
    """Middleware que valida que la petición contenga un token de handshake."""
    # Validar presencia del encabezado
    if not x_app_session:
        raise HTTPException(status_code=403, detail="Error: Falta el token de sesión")
    try:
        # Decodificar y validar firma y audiencia del token        
        jwt.decode(x_app_session, str(APP_SESSION_SECRET), algorithms=[ALGORITHM], audience="moveon_app")
        return x_app_session
    except JWTError:
        raise HTTPException(status_code=403, detail="Error: Token inválido o expirado")

def obtener_usuario_actual(res: HTTPAuthorizationCredentials = Depends(security_scheme)) -> str:
    """
    Extrae el usuario validando el token. 
    Usa la dependencia de FastAPI para capturar el token del botón Authorize.
    """
    # El token ya viene limpio sin la palabra "Bearer" gracias a HTTPAuthorizationCredentials
    token = res.credentials

    try:
        payload: dict[str, Any] = jwt.decode(token, str(SECRET_KEY), algorithms=[ALGORITHM])
        usuario_id = payload.get("sub")
        
        if usuario_id is None or not isinstance(usuario_id, str):
            raise HTTPException(status_code=401, detail="Error: Token no contiene un usuario válido")
            
        return usuario_id
    except JWTError:
        raise HTTPException(status_code=401, detail="Error: Token de acceso inválido o expirado")