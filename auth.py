# auth.py

"""
Módulo de Seguridad y Gestión de Tokens.

Gestiona el cifrado de contraseñas mediante bcrypt, la generación de tokens JWT
para sesiones de usuario y el sistema de validación de handshake.
"""
import bcrypt
from datetime import datetime, timedelta, timezone
import jwt
import logging
from jwt.exceptions import InvalidTokenError
from fastapi import Header, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from typing import Any, Optional
from config import settings
from exceptions import app_http_exception
import database

logger = logging.getLogger("app.auth")

# Parámetros de configuración del sistema de tokens
ACCESS_TOKEN_SECRET = settings.ACCESS_TOKEN_SECRET
REFRESH_TOKEN_SECRET = settings.REFRESH_TOKEN_SECRET
ALGORITHM = settings.ALGORITHM
ACCESS_TOKEN_EXPIRE_MINUTES = settings.ACCESS_TOKEN_EXPIRE_MINUTES
REFRESH_TOKEN_EXPIRE_DAYS = settings.REFRESH_TOKEN_EXPIRE_DAYS
APP_ID = settings.APP_ID
APP_SESSION_SECRET = settings.APP_SESSION_SECRET
APP_SESSION_EXPIRE_MINUTES = settings.APP_SESSION_EXPIRE_MINUTES
# Endurecimiento de JWT (mismo emisor/audiencia para todos los JWT)
JWT_ISSUER = settings.JWT_ISSUER
JWT_AUDIENCE = settings.JWT_AUDIENCE

# Instancia de seguridad que activa el botón "Autorizar" en Swagger.
security_scheme = HTTPBearer()


def encriptar_password(password: str) -> str:
    """Cifra una contraseña en claro usando bcrypt con salt aleatorio por llamada.

    bcrypt genera un salt nuevo cada vez, por lo que cifrar dos veces la
    misma contraseña produce hashes distintos aunque ambos sean válidos.

    Args:
        password: contraseña en claro tal como la introdujo el usuario.

    Returns:
        Hash bcrypt codificado en UTF-8, listo para persistir en la base
        de datos.
    """
    salt = bcrypt.gensalt()
    return bcrypt.hashpw(password.encode("utf-8"), salt).decode("utf-8")


def comprobar_password(password_plana: str, password_encriptada: str) -> bool:
    """Verifica una contraseña en claro contra el hash bcrypt almacenado.

    La comparación se delega en ``bcrypt.checkpw``, que realiza una
    comparación en tiempo constante para mitigar ataques de canal lateral
    por temporización.

    Args:
        password_plana: contraseña tal como la acaba de introducir el usuario.
        password_encriptada: hash bcrypt tal como está guardado en la base de datos.

    Returns:
        ``True`` si la contraseña coincide con el hash; ``False`` en caso contrario.
    """
    return bcrypt.checkpw(
        password_plana.encode("utf-8"), password_encriptada.encode("utf-8")
    )


def _ahora_utc() -> datetime:
    """Devuelve el ``datetime`` actual con ``tzinfo=UTC``.

    Se centraliza aquí para que todos los JWT (exp/iat) se firmen contra
    la misma referencia temporal y los tests puedan monkey-patchearla
    en un único sitio.

    Returns:
        Fecha y hora actual del sistema en UTC.
    """
    return datetime.now(timezone.utc)


def codifica_jwt(payload: dict, secret: str, expires_delta: timedelta, typ: str) -> str:
    """Firma un JWT con los claims comunes a todos los tokens de la app.

    Añade automáticamente ``exp``, ``iat``, ``iss``, ``aud`` y ``typ``
    encima del ``payload`` recibido, de forma que la decodificación
    correspondiente pueda validar esos mismos claims de manera uniforme.

    Args:
        payload: claims específicos del token (p. ej. ``sub``, ``jti``, ``fam``).
        secret: clave secreta con la que se firma el JWT (distinta por tipo).
        expires_delta: tiempo de vida del token a partir del instante actual.
        typ: valor del claim ``typ`` (``access``, ``refresh`` o ``app_session``).

    Returns:
        JWT serializado como cadena codificada con ``ALGORITHM``.
    """
    # Gestiona codifica JWT.
    ahora = _ahora_utc()
    exp = ahora + expires_delta

    datos = payload.copy()
    datos.update(
        {
            "exp": int(exp.timestamp()),
            "iat": int(ahora.timestamp()),
            "iss": JWT_ISSUER,
            "aud": JWT_AUDIENCE,
            "typ": typ,
        }
    )

    return jwt.encode(datos, str(secret), algorithm=ALGORITHM)


def decodifica_jwt(token: str, secret: str, expected_typ: str) -> dict[str, Any]:
    """Decodifica y valida un JWT aplicando todas las comprobaciones canónicas.

    Verifica firma, expiración, emisor, audiencia y que el claim ``typ``
    coincida con el esperado. Si el ``typ`` no coincide se lanza una
    ``AppHTTPException`` 401 explícita en lugar de un simple
    ``InvalidTokenError`` para poder devolver un ``error_code`` útil.

    Args:
        token: JWT serializado recibido del cliente.
        secret: clave secreta con la que se firmó el token (la correspondiente al tipo).
        expected_typ: valor que debe tener el claim ``typ`` (``access``, ``refresh``...).

    Returns:
        Diccionario con los claims decodificados.

    Raises:
        AppHTTPException: si el ``typ`` no coincide con ``expected_typ`` (401).
        jwt.InvalidTokenError: si la firma, la expiración o los claims de emisor/audiencia no son válidos.
    """
    # Gestiona decodifica JWT.
    payload: dict[str, Any] = jwt.decode(
        token,
        str(secret),
        algorithms=[ALGORITHM],
        audience=JWT_AUDIENCE,
        issuer=JWT_ISSUER,
        options={"require": ["exp", "iat"]},
    )

    if payload.get("typ") != expected_typ:
        raise app_http_exception(
            status_code=401,
            mensaje=f"Error: Token no es de tipo {expected_typ}",
            error_code="TOKEN_TYPE_MISMATCH",
        )

    return payload


def crear_token_aplicacion() -> str:
    """Emite el JWT de corta duración que el cliente usa en el handshake.

    El token de ``app_session`` no representa a un usuario: acredita que
    la petición procede de una instalación legítima de la app. Se firma
    con su propio secreto y expira según ``APP_SESSION_EXPIRE_MINUTES``.

    Returns:
        JWT de tipo ``app_session`` listo para enviarse al cliente.
    """
    # Token "app_session" con el mismo esquema de claims que el resto
    return codifica_jwt(
        payload={},  # no necesitas sub aquí, pero podrías añadir {"sub": "app"} si quieres
        secret=APP_SESSION_SECRET,
        expires_delta=timedelta(minutes=APP_SESSION_EXPIRE_MINUTES),
        typ="app_session",
    )


def verificar_sesion_aplicacion(x_app_session: Optional[str] = Header(default=None)):
    """Dependencia FastAPI que exige un ``x-app-session`` válido en la cabecera.

    Se usa para proteger endpoints públicos (login, registro, recuperación)
    de peticiones que no vienen desde el cliente oficial. Si el token falta
    o es inválido/expirado, responde 403 con un ``error_code`` distinto en
    cada caso para que el cliente pueda distinguirlos y decidir si repite
    el handshake.

    Args:
        x_app_session: valor de la cabecera ``x-app-session`` inyectado por FastAPI.

    Returns:
        El propio token cuando es válido, por si el endpoint quiere usarlo.

    Raises:
        AppHTTPException: 403 ``SESSION_TOKEN_MISSING`` si la cabecera no está presente.
        AppHTTPException: 403 ``TOKEN_INVALID_OR_EXPIRED`` si el token es inválido o ha caducado; incluye la cabecera ``x-app-session-expired`` para que el cliente re-handshakee.
    """
    # Validar presencia del encabezado
    if not x_app_session:
        logger.warning(
            "sesion_aplicacion_ausente",
            extra={},
        )
        raise app_http_exception(
            status_code=403,
            mensaje="Error: Falta el token de sesión",
            error_code="SESSION_TOKEN_MISSING",
            headers={"x-app-session-expired": "1"},
        )

    try:
        # Validación uniforme (firma + exp + iss + aud + typ)
        decodifica_jwt(x_app_session, APP_SESSION_SECRET, "app_session")
        return x_app_session
    except (InvalidTokenError, HTTPException):
        logger.warning(
            "sesion_aplicacion_invalida_o_expirada",
            extra={},
        )
        raise app_http_exception(
            status_code=403,
            mensaje="Error: Token inválido o expirado",
            error_code="TOKEN_INVALID_OR_EXPIRED",
            headers={"x-app-session-expired": "1"},
        )


def crear_token_acceso(datos: dict) -> str:
    """Emite el access token de un usuario autenticado.

    El access token es de vida corta (``ACCESS_TOKEN_EXPIRE_MINUTES``) y
    contiene los claims necesarios para identificar al usuario en cada
    petición. La renovación se hace con el refresh token, no pidiendo
    credenciales de nuevo.

    Args:
        datos: claims a incrustar en el token; como mínimo debe contener ``sub`` con el id de usuario.

    Returns:
        JWT de tipo ``access`` firmado con ``ACCESS_TOKEN_SECRET``.
    """
    return codifica_jwt(
        payload=datos,
        secret=ACCESS_TOKEN_SECRET,
        expires_delta=timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES),
        typ="access",
    )


def crear_token_refresh(usuario_id: int, jti: str, familia_id: str) -> str:
    """Emite un refresh token con soporte de rotación por familia.

    El ``jti`` identifica al token concreto y el ``fam`` identifica la
    cadena de refresh tokens emitidos tras un mismo login. Esto permite
    detectar reutilizaciones (si alguien usa un token antiguo ya rotado
    se invalida toda la familia) y mitigar robos.

    Args:
        usuario_id: identificador numérico del usuario dueño del refresh token.
        jti: identificador único de este refresh concreto, usado para deduplicar/revocar.
        familia_id: identificador común a todos los refresh tokens derivados del mismo login.

    Returns:
        JWT de tipo ``refresh`` firmado con ``REFRESH_TOKEN_SECRET``.
    """
    payload = {"sub": str(usuario_id), "jti": jti, "fam": familia_id}
    return codifica_jwt(
        payload=payload,
        secret=REFRESH_TOKEN_SECRET,
        expires_delta=timedelta(days=REFRESH_TOKEN_EXPIRE_DAYS),
        typ="refresh",
    )


def decodificar_token_refresh(refresh_token: str) -> dict[str, Any]:
    """Decodifica un refresh token y valida todos sus claims.

    Si la firma, la expiración o cualquier otro claim es inválido, lanza
    una ``AppHTTPException`` 401 con ``error_code`` específico para que el
    cliente pueda forzar un re-login en lugar de reintentar.

    Args:
        refresh_token: JWT de refresh tal como lo envió el cliente.

    Returns:
        Claims decodificados del token (incluye ``sub``, ``jti``, ``fam``).

    Raises:
        AppHTTPException: 401 ``REFRESH_TOKEN_INVALID_OR_EXPIRED`` si el token no se puede validar.
    """
    try:
        return decodifica_jwt(refresh_token, REFRESH_TOKEN_SECRET, "refresh")
    except InvalidTokenError:
        logger.warning(
            "decodificacion_refresh_fallida",
            extra={},
        )
        raise app_http_exception(
            status_code=401,
            mensaje="Error: Refresh token inválido o expirado",
            error_code="REFRESH_TOKEN_INVALID_OR_EXPIRED",
        )


async def obtener_usuario_actual(
    res: HTTPAuthorizationCredentials = Depends(security_scheme),
    db: AsyncSession = Depends(database.obtener_db),
) -> int:
    """Dependencia FastAPI que extrae y valida al usuario del access token.

    Extrae el token del header ``Authorization: Bearer`` usando
    ``HTTPBearer``, lo decodifica como JWT de tipo ``access`` y, tras
    comprobar que ``sub`` es un entero válido, verifica además que el
    token no sea anterior al último cambio de contraseña del usuario
    (``password_changed_at``). Esto invalida tokens vivos cuando el
    usuario cambia la contraseña desde otro dispositivo.

    Args:
        res: credenciales inyectadas por ``HTTPBearer`` (sólo el valor del token, sin ``Bearer``).
        db: sesión asíncrona de SQLAlchemy inyectada por FastAPI.

    Returns:
        Identificador numérico del usuario autenticado.

    Raises:
        AppHTTPException: 401 ``TOKEN_MISSING_VALID_USER`` si ``sub`` no es un entero válido.
        AppHTTPException: 401 ``SESSION_REVOKED_BY_PASSWORD_CHANGE`` si el token se emitió antes del último cambio de contraseña.
        AppHTTPException: 401 ``ACCESS_TOKEN_INVALID_OR_EXPIRED`` si el token es inválido o ha caducado.
    """
    # El token ya viene limpio sin la palabra "Bearer" gracias a HTTPAuthorizationCredentials.
    # Obtiene usuario actual.
    token = res.credentials

    try:
        payload = decodifica_jwt(token, ACCESS_TOKEN_SECRET, "access")

        sub = payload.get("sub")
        iat = payload.get("iat")
        if sub is None or not isinstance(sub, str) or not sub.isdigit():
            logger.warning(
                "access_token_sin_sub_valido",
                extra={},
            )
            raise app_http_exception(
                status_code=401,
                mensaje="Error: Token no contiene un usuario válido",
                error_code="TOKEN_MISSING_VALID_USER",
            )

        usuario_id = int(sub)
        password_changed_at = (
            await db.execute(
                select(database.Usuario.password_changed_at).where(
                    database.Usuario.id == usuario_id
                )
            )
        ).scalar_one_or_none()

        if (
            password_changed_at is not None
            and isinstance(iat, int)
            and iat < int(password_changed_at.timestamp())
        ):
            logger.warning(
                "access_token_invalidado_por_cambio_password",
                extra={"usuario_id": usuario_id},
            )
            raise app_http_exception(
                status_code=401,
                mensaje="Error: Sesión invalidada por cambio de contraseña",
                error_code="SESSION_REVOKED_BY_PASSWORD_CHANGE",
            )

        return usuario_id
    except InvalidTokenError:
        logger.warning(
            "access_token_invalido_o_expirado",
            extra={},
        )
        raise app_http_exception(
            status_code=401,
            mensaje="Error: Token de acceso inválido o expirado",
            error_code="ACCESS_TOKEN_INVALID_OR_EXPIRED",
        )
