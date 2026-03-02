# auth.py

"""
Módulo de Seguridad y Gestión de Tokens.

Gestiona el cifrado de contraseñas mediante bcrypt, la generación de tokens JWT 
para sesiones de usuario y el sistema de validación de handshake.
"""
import bcrypt
from datetime import datetime, timedelta, timezone
from jose import jwt, JWTError
from fastapi import HTTPException, Header, Depends
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from typing import Any
from config import settings

# Parámetros de configuración del sistema de tokens
ACCESS_TOKEN_SECRET = settings.ACCESS_TOKEN_SECRET
REFRESH_TOKEN_SECRET = settings.REFRESH_TOKEN_SECRET
ALGORITHM = settings.ALGORITHM
ACCESS_TOKEN_EXPIRE_MINUTES = settings.ACCESS_TOKEN_EXPIRE_MINUTES
REFRESH_TOKEN_EXPIRE_DAYS = settings.REFRESH_TOKEN_EXPIRE_DAYS
APP_ID = settings.APP_ID
APP_SESSION_SECRET = settings.APP_SESSION_SECRET
APP_SESSION_EXPIRE_MINUTES = settings.APP_SESSION_EXPIRE_MINUTES

# Instancia de seguridad que activa el botón "Authorize" en Swagger.
security_scheme = HTTPBearer()

def encriptar_password(password: str) -> str:
    """Cifra una contraseña de texto plano usando bcrypt."""
    salt = bcrypt.gensalt()
    return bcrypt.hashpw(password.encode('utf-8'), salt).decode('utf-8')

def comprobar_password(password_plana: str, password_encriptada: str) -> bool:
    """Compara una contraseña plana ingresada con el hash almacenado en la base de datos."""
    return bcrypt.checkpw(password_plana.encode('utf-8'), password_encriptada.encode('utf-8'))

def crear_token_aplicacion() -> str:
    """Genera un token JWT de corta duración (5 minutos) para el apretón de manos inicial."""
    expiracion = datetime.now(timezone.utc) + timedelta(minutes=APP_SESSION_EXPIRE_MINUTES)
    datos_a_cifrar = {"exp": expiracion, "aud": "moveon_app"}
    return jwt.encode(datos_a_cifrar, str(APP_SESSION_SECRET), algorithm=ALGORITHM)

def crear_token_acceso(datos: dict) -> str:
    """Genera el token de acceso (corto) para un usuario autenticado correctamente."""
    datos_copia = datos.copy()
    expiracion = datetime.now(timezone.utc) + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    datos_copia.update({
        "exp": expiracion,
        "typ": "access"
    })
    return jwt.encode(datos_copia, str(ACCESS_TOKEN_SECRET), algorithm=ALGORITHM)

def crear_token_refresh(nombre_usuario: str, jti: str, familia_id: str) -> str:
    """Genera el refresh token (largo) con rotación."""
    expiracion = datetime.now(timezone.utc) + timedelta(days=REFRESH_TOKEN_EXPIRE_DAYS)
    payload = {
        "sub": nombre_usuario,
        "jti": jti,
        "fam": familia_id,
        "typ": "refresh",
        "exp": expiracion
    }
    return jwt.encode(payload, str(REFRESH_TOKEN_SECRET), algorithm=ALGORITHM)

def decodificar_token_refresh(refresh_token: str) -> dict[str, Any]:
    """Decodifica y valida un refresh token."""
    try:
        payload: dict[str, Any] = jwt.decode(
            refresh_token,
            str(REFRESH_TOKEN_SECRET),
            algorithms=[ALGORITHM]
        )

        if payload.get("typ") != "refresh":
            raise HTTPException(status_code=401, detail="Error: Token refresh inválido")

        return payload
    except JWTError:
        raise HTTPException(status_code=401, detail="Error: Refresh token inválido o expirado")

def verificar_sesion_aplicacion(x_app_session: str = Header(None)):
    """Middleware que valida que la petición contenga un token de handshake."""
    # Validar presencia del encabezado
    if not x_app_session:
        raise HTTPException(
            status_code=403, 
            detail="Error: Falta el token de sesión",
            headers={"x-app-session-expired": "1"}
        )
    try:
        # Decodificar y validar firma y audiencia del token   
        jwt.decode(
            x_app_session,
            str(APP_SESSION_SECRET),
            algorithms=[ALGORITHM],
            audience="moveon_app"
        )
        return x_app_session
    except JWTError:
        raise HTTPException(
            status_code=403, 
            detail="Error: Token inválido o expirado",
            headers={"x-app-session-expired": "1"}
        )

def obtener_usuario_actual(res: HTTPAuthorizationCredentials = Depends(security_scheme)) -> str:
    """
    Extrae el usuario validando el token de acceso.
    Usa la dependencia de FastAPI para capturar el token del botón Authorize.
    """
    # El token ya viene limpio sin la palabra "Bearer" gracias a HTTPAuthorizationCredentials.
    token = res.credentials

    try:
        payload: dict[str, Any] = jwt.decode(token, str(ACCESS_TOKEN_SECRET), algorithms=[ALGORITHM])

        if payload.get("typ") != "access":
            raise HTTPException(status_code=401, detail="Error: Token no es de acceso")

        usuario_id = payload.get("sub")

        if usuario_id is None or not isinstance(usuario_id, str):
            raise HTTPException(status_code=401, detail="Error: Token no contiene un usuario válido")

        return usuario_id
    except JWTError:
        raise HTTPException(status_code=401, detail="Error: Token de acceso inválido o expirado")
    