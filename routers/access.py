# routers/access.py

"""
Endpoints de Seguridad de Aplicación y Autenticación.

Gestiona el apretón de manos (handshake) inicial para validar la App,
el inicio de sesión, refresh y cierre de sesión.
"""
from fastapi import APIRouter, Depends, Header, Request, BackgroundTasks
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.concurrency import run_in_threadpool

import auth
import schemas
from database import obtener_db
from services import access_service, social_auth_service
from config import settings
from exceptions import app_http_exception
from ip_rate_limit import rate_limit
from services.identity_rate_limit import check_identity_limit
import hmac
import logging
from typing import Optional

logger = logging.getLogger("app.auth")

router = APIRouter(tags=["Seguridad"])


# Valida el identificador de app y entrega un token de sesión temporal.
@router.get("/handshake", response_model=schemas.RespuestaHandshake)
@rate_limit(settings.RL_HANDSHAKE)
async def handshake(request: Request, x_app_id: Optional[str] = Header(default=None)):
    """Endpoint inicial que valida la identidad del cliente y emite un token de sesión.

    Comprueba con ``hmac.compare_digest`` (comparación en tiempo constante)
    que el ``x-app-id`` recibido coincida con el configurado en el backend.
    Es el primer filtro contra clientes no oficiales: si el id no coincide,
    responde 403 con ``INVALID_APP_ORIGIN`` y registra el intento.

    Si la comprobación pasa, devuelve un JWT ``app_session`` de corta
    vida que el resto de endpoints protegidos por ``verificar_sesion_aplicacion``
    exigirán en cada petición.

    Args:
        request: petición entrante (``slowapi`` la usa para aplicar el rate limit).
        x_app_id: valor de la cabecera ``x-app-id`` inyectado por FastAPI.

    Returns:
        Diccionario ``{"app_session_token": <JWT>}``.

    Raises:
        AppHTTPException: 403 ``INVALID_APP_ORIGIN`` si el ``x-app-id`` no coincide.
    """
    # Valida la aplicación cliente y genera una sesión temporal.
    if not hmac.compare_digest((x_app_id or ""), settings.APP_ID):
        logger.warning(
            "handshake_fallido",
            extra={
                "motivo": "app_id_invalido",
                "path": request.url.path,
                "method": request.method,
            },
        )
        raise app_http_exception(
            status_code=403,
            mensaje="Error: El acceso no proviene de la aplicación MoveOn",
            error_code="INVALID_APP_ORIGIN",
        )

    logger.info(
        "handshake_correcto",
        extra={
            "path": request.url.path,
            "method": request.method,
        },
    )

    return {"app_session_token": auth.crear_token_aplicacion()}


# Autentica al usuario y genera access token + refresh token.
@router.post("/login", response_model=schemas.RespuestaLogin)
@rate_limit(settings.RL_LOGIN)  # configurable por env
async def login(
    request: Request,
    datos: schemas.Login,
    db: AsyncSession = Depends(obtener_db),
    _auth_app=Depends(auth.verificar_sesion_aplicacion),
):
    # Límite de tasa adicional por identidad (antiabuso distribuido)
    # Lanza IdentityRateLimitExceeded (main.py la maneja).
    """Autentica por nombre de usuario o email y emite access + refresh token.

    Flujo:

    1. Aplica rate-limit por identidad (``check_identity_limit``) para
       frenar fuerza bruta distribuida que rota IPs pero repite el mismo email.
    2. Busca al usuario con ``access_service.buscar_por_identificador`` (acepta email o nombre).
    3. Verifica la contraseña en un threadpool (``bcrypt`` es síncrono y costoso).
    4. En cualquier fallo devuelve siempre el mismo ``INVALID_CREDENTIALS``
       para no revelar si el usuario existe o no.
    5. Al éxito, delega la emisión de tokens en ``crear_sesion_login``.

    Args:
        request: petición entrante (usada por ``slowapi`` para rate limit).
        datos: credenciales del usuario (identificador + password).
        db: sesión asíncrona de SQLAlchemy.
        _auth_app: dependencia que exige un ``app_session`` válido; inyectada por FastAPI.

    Returns:
        ``RespuestaLogin`` con ``access_token`` y ``refresh_token``.

    Raises:
        AppHTTPException: 401 ``INVALID_CREDENTIALS`` si el usuario no existe o la contraseña no coincide.
        IdentityRateLimitExceeded: si la identidad ha superado el rate limit de login.
    """
    check_identity_limit("login", datos.identificador, settings.RL_LOGIN_ID)

    # Búsqueda flexible por nombre o email.
    usuario_encontrado = await access_service.buscar_por_identificador(
        db, datos.identificador
    )

    # Validación de existencia y coincidencia de hash de contraseña.
    if not usuario_encontrado:
        logger.info(
            "inicio_sesion_fallido",
            extra={
                "identificador": datos.identificador,
                "motivo": "usuario_no_encontrado",
            },
        )
        raise app_http_exception(
            status_code=401,
            mensaje="Error: Credenciales no validas",
            error_code="INVALID_CREDENTIALS",
        )

    es_valido = await run_in_threadpool(
        auth.comprobar_password,
        datos.password,
        str(usuario_encontrado.password_encriptada),
    )
    if not es_valido:
        logger.info(
            "inicio_sesion_fallido",
            extra={
                "identificador": datos.identificador,
                "motivo": "password_invalida",
            },
        )
        raise app_http_exception(
            status_code=401,
            mensaje="Error: Credenciales no validas",
            error_code="INVALID_CREDENTIALS",
        )

    logger.info(
        "inicio_sesion_correcto",
        extra={
            "usuario_id": usuario_encontrado.id,
            "usuario": usuario_encontrado.nombre_usuario,
        },
    )
    return await access_service.crear_sesion_login(db, usuario_encontrado)


@router.post("/login/social", response_model=schemas.RespuestaLogin)
@rate_limit(settings.RL_LOGIN)
async def login_social(
    request: Request,
    datos: schemas.LoginSocial,
    db: AsyncSession = Depends(obtener_db),
    _auth_app=Depends(auth.verificar_sesion_aplicacion),
):
    """Autentica usando un proveedor externo (Google) ya verificado.

    El flujo es paralelo a ``login`` pero parte de un token de
    proveedor (``id_token`` de Google) que el backend verifica antes
    de fiarse. Si la cuenta social aún no está vinculada a ningún
    usuario del sistema, responde 404 ``SOCIAL_ACCOUNT_NOT_REGISTERED``
    para que el cliente dirija al usuario al flujo de registro social.

    Efectos colaterales: si el usuario existe y no tiene foto de
    perfil pero el proveedor sí devuelve una, se guarda como foto
    inicial.

    Args:
        request: petición entrante.
        datos: contiene el ``provider`` y el ``token`` del proveedor externo.
        db: sesión asíncrona de SQLAlchemy.
        _auth_app: dependencia de sesión de aplicación.

    Returns:
        ``RespuestaLogin`` con los tokens emitidos para el usuario local.

    Raises:
        AppHTTPException: 404 ``SOCIAL_ACCOUNT_NOT_REGISTERED`` si la cuenta social no está vinculada.
        Cualquier error de ``social_auth_service.verificar_token_social`` si el token del proveedor no es válido.
    """
    # Gestiona login social.
    identidad = await social_auth_service.verificar_token_social(
        datos.provider, datos.token
    )

    check_identity_limit(
        "login",
        f"{identidad.provider}:{identidad.provider_user_id}",
        settings.RL_LOGIN_ID,
    )

    vinculo = await social_auth_service.buscar_vinculo_social(
        db, identidad.provider, identidad.provider_user_id
    )
    if not vinculo:
        logger.info(
            "inicio_sesion_social_fallido",
            extra={
                "provider": identidad.provider,
                "provider_user_id": identidad.provider_user_id,
                "motivo": "cuenta_social_no_registrada",
            },
        )
        raise app_http_exception(
            status_code=404,
            mensaje="Error: Esta cuenta social todavía no está registrada en MoveOn",
            error_code="SOCIAL_ACCOUNT_NOT_REGISTERED",
        )

    usuario = await access_service.buscar_usuario_por_id(db, vinculo.usuario_id)
    social_auth_service.actualizar_metadata_vinculo(vinculo, identidad)

    if not usuario.foto_perfil and identidad.avatar_url:
        usuario.foto_perfil = identidad.avatar_url
        await db.commit()
        await db.refresh(usuario)

    logger.info(
        "inicio_sesion_social_correcto",
        extra={
            "usuario_id": usuario.id,
            "usuario": usuario.nombre_usuario,
            "provider": identidad.provider,
        },
    )
    return await access_service.crear_sesion_login(db, usuario)


# Renueva la sesión usando refresh token con rotación.
@router.post("/token/refresh", response_model=schemas.RespuestaRefreshToken)
@rate_limit(settings.RL_REFRESH)
async def refresh_token(
    request: Request,
    datos: schemas.SolicitudRefreshToken,
    db: AsyncSession = Depends(obtener_db),
    _auth_app=Depends(auth.verificar_sesion_aplicacion),
):
    """Renueva la pareja access/refresh rotando el refresh token recibido.

    Delega toda la lógica en ``access_service.refrescar_sesion``, que
    valida el token, verifica que no haya sido revocado, emite uno
    nuevo dentro de la misma familia y marca el anterior como usado
    para detectar reutilizaciones (robos) posteriores.

    Args:
        request: petición entrante.
        datos: contiene el ``refresh_token`` a rotar.
        db: sesión asíncrona de SQLAlchemy.
        _auth_app: dependencia de sesión de aplicación.

    Returns:
        ``RespuestaRefreshToken`` con los nuevos access y refresh tokens.
    """
    return await access_service.refrescar_sesion(db, datos.refresh_token)


# Revoca la sesión actual (refresh token).
@router.post("/logout", response_model=schemas.RespuestaGenerica)
@rate_limit(settings.RL_LOGOUT)
async def logout(
    request: Request,
    datos: schemas.SolicitudLogout,
    db: AsyncSession = Depends(obtener_db),
    _auth_app=Depends(auth.verificar_sesion_aplicacion),
):
    """Revoca explícitamente el refresh token recibido.

    Delega en ``access_service.cerrar_sesion``, que marca el refresh
    como revocado para que ni él ni ningún derivado suyo puedan
    renovar sesión. El access token en vuelo sigue siendo válido
    hasta su expiración corta: no se invalida aquí por diseño para
    no pagar una consulta por cada petición a la base de datos.

    Args:
        request: petición entrante.
        datos: contiene el ``refresh_token`` a revocar.
        db: sesión asíncrona de SQLAlchemy.
        _auth_app: dependencia de sesión de aplicación.

    Returns:
        ``RespuestaGenerica`` confirmando la revocación.
    """
    return await access_service.cerrar_sesion(db, datos.refresh_token)


# Solicitar código de 6 dígitos al email.
# Se envía en segundo plano para no bloquear la API mientras responde el servidor SMTP.
@router.post("/password/solicitar", response_model=schemas.RespuestaGenerica)
@rate_limit(settings.RL_PASSWORD_SOLICITAR)
async def solicitar_password(
    request: Request,
    datos: schemas.SolicitarPassword,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(obtener_db),
    _auth_app=Depends(auth.verificar_sesion_aplicacion),
):
    # Límite de tasa adicional por identidad (antiabuso distribuido)
    """Inicia el flujo de recuperación de contraseña por email.

    El envío del correo se delega a ``BackgroundTasks`` para que la
    respuesta no quede bloqueada esperando al servidor SMTP. Aplica
    un rate limit específico por identidad (email) para evitar que un
    atacante use el servicio como canal de spam.

    La respuesta es genérica intencionadamente: no distingue si el
    email existe en el sistema o no, para no permitir enumeración de
    cuentas.

    Args:
        request: petición entrante.
        datos: contiene el ``email`` y ``locale`` para elegir la plantilla.
        background_tasks: acumulador de tareas para despachar fuera del request.
        db: sesión asíncrona de SQLAlchemy.
        _auth_app: dependencia de sesión de aplicación.

    Returns:
        ``RespuestaGenerica`` neutra, independientemente de si el email existía.
    """
    check_identity_limit(
        "password_solicitar", datos.email, settings.RL_PASSWORD_SOLICITAR_ID
    )

    return await access_service.generar_codigo_recuperacion(
        db, datos.email, background_tasks, datos.locale
    )


# Confirma el código y actualiza la contraseña.
@router.post("/password/confirmar", response_model=schemas.RespuestaGenerica)
@rate_limit(settings.RL_PASSWORD_CONFIRMAR)
async def confirmar_password(
    request: Request,
    datos: schemas.ConfirmarPassword,
    db: AsyncSession = Depends(obtener_db),
    _auth_app=Depends(auth.verificar_sesion_aplicacion),
):
    # Límite de tasa adicional por identidad (antiabuso distribuido)
    """Completa el reseteo de contraseña verificando el código recibido.

    Aplica también rate limit por identidad para dificultar fuerza
    bruta contra el código de 6 dígitos. El propio
    ``access_service.resetear_password`` hace la validación de ``email``
    + ``código`` + expiración.

    Args:
        request: petición entrante.
        datos: contiene ``email``, ``código`` y ``nueva_password``.
        db: sesión asíncrona de SQLAlchemy.
        _auth_app: dependencia de sesión de aplicación.

    Returns:
        ``RespuestaGenerica`` confirmando el cambio si todo fue correcto.
    """
    check_identity_limit(
        "password_confirmar", datos.email, settings.RL_PASSWORD_CONFIRMAR_ID
    )

    return await access_service.resetear_password(db, datos)
