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
# JWT hardening (mismo issuer/audience para TODOS los JWT)
JWT_ISSUER = settings.JWT_ISSUER
JWT_AUDIENCE = settings.JWT_AUDIENCE

# Instancia de seguridad que activa el botón "Authorize" en Swagger.
security_scheme = HTTPBearer()


def encriptar_password(password: str) -> str:
    """Cifra una contraseña de texto plano usando bcrypt."""
    salt = bcrypt.gensalt()
    return bcrypt.hashpw(password.encode('utf-8'), salt).decode('utf-8')


def comprobar_password(password_plana: str, password_encriptada: str) -> bool:
    """Compara una contraseña plana ingresada con el hash almacenado en la base de datos."""
    return bcrypt.checkpw(password_plana.encode('utf-8'), password_encriptada.encode('utf-8'))


def _ahora_utc() -> datetime:
    return datetime.now(timezone.utc)


def codifica_jwt(payload: dict, secret: str, expires_delta: timedelta, typ: str) -> str:
    """
    Firma un JWT con claims comunes:
      - exp, iat, iss, aud, typ
    """
    ahora = _ahora_utc()
    exp = ahora + expires_delta

    datos = payload.copy()
    datos.update({
        "exp": exp,
        "iat": ahora,
        "iss": JWT_ISSUER,
        "aud": JWT_AUDIENCE,
        "typ": typ
    })

    return jwt.encode(datos, str(secret), algorithm=ALGORITHM)


def decodifica_jwt(token: str, secret: str, expected_typ: str) -> dict[str, Any]:
    """
    Decodifica y valida un JWT SIEMPRE igual:
      - firma
      - exp
      - iss
      - aud
      - typ
    """
    payload: dict[str, Any] = jwt.decode(
        token,
        str(secret),
        algorithms=[ALGORITHM],
        audience=JWT_AUDIENCE,
        issuer=JWT_ISSUER
    )

    if payload.get("typ") != expected_typ:
        raise HTTPException(status_code=401, detail=f"Error: Token no es de tipo {expected_typ}")

    return payload


def crear_token_aplicacion() -> str:
    """Genera un token JWT de corta duración para el apretón de manos inicial."""
    # Token "app_session" con el mismo esquema de claims que el resto
    return codifica_jwt(
        payload={},  # no necesitas sub aquí, pero podrías añadir {"sub": "app"} si quieres
        secret=APP_SESSION_SECRET,
        expires_delta=timedelta(minutes=APP_SESSION_EXPIRE_MINUTES),
        typ="app_session"
    )


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
        # Validación uniforme (firma + exp + iss + aud + typ)
        decodifica_jwt(x_app_session, APP_SESSION_SECRET, "app_session")
        return x_app_session
    except JWTError:
        raise HTTPException(
            status_code=403,
            detail="Error: Token inválido o expirado",
            headers={"x-app-session-expired": "1"}
        )
    except HTTPException:
        # Si falla por typ u otras validaciones, lo tratamos igual que expirado/inválido
        raise HTTPException(
            status_code=403,
            detail="Error: Token inválido o expirado",
            headers={"x-app-session-expired": "1"}
        )


def crear_token_acceso(datos: dict) -> str:
    """Genera el token de acceso (corto) para un usuario autenticado correctamente."""
    return codifica_jwt(
        payload=datos,
        secret=ACCESS_TOKEN_SECRET,
        expires_delta=timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES),
        typ="access"
    )


def crear_token_refresh(nombre_usuario: str, jti: str, familia_id: str) -> str:
    """Genera el refresh token (largo) con rotación."""
    payload = {
        "sub": nombre_usuario,
        "jti": jti,
        "fam": familia_id
    }
    return codifica_jwt(
        payload=payload,
        secret=REFRESH_TOKEN_SECRET,
        expires_delta=timedelta(days=REFRESH_TOKEN_EXPIRE_DAYS),
        typ="refresh"
    )


def decodificar_token_refresh(refresh_token: str) -> dict[str, Any]:
    """Decodifica y valida un refresh token."""
    try:
        return decodifica_jwt(refresh_token, REFRESH_TOKEN_SECRET, "refresh")
    except JWTError:
        raise HTTPException(status_code=401, detail="Error: Refresh token inválido o expirado")


def obtener_usuario_actual(res: HTTPAuthorizationCredentials = Depends(security_scheme)) -> str:
    """
    Extrae el usuario validando el token de acceso.
    Usa la dependencia de FastAPI para capturar el token del botón Authorize.
    """
    # El token ya viene limpio sin la palabra "Bearer" gracias a HTTPAuthorizationCredentials.
    token = res.credentials

    try:
        payload = decodifica_jwt(token, ACCESS_TOKEN_SECRET, "access")

        usuario_id = payload.get("sub")
        if usuario_id is None or not isinstance(usuario_id, str):
            raise HTTPException(status_code=401, detail="Error: Token no contiene un usuario válido")

        return usuario_id
    except JWTError:
        raise HTTPException(status_code=401, detail="Error: Token de acceso inválido o expirado")
    