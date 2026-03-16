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
from services import access_service
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
# routers/access.py
@router.get("/handshake", response_model=schemas.RespuestaHandshake)
@rate_limit(settings.RL_HANDSHAKE)
async def handshake(request: Request, x_app_id: Optional[str] = Header(default=None)):
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
    # Rate-limit adicional por identidad (anti-abuso distribuido)
    # Lanza IdentityRateLimitExceeded (main.py la maneja).
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


# Renueva la sesión usando refresh token con rotación.
@router.post("/token/refresh", response_model=schemas.RespuestaRefreshToken)
@rate_limit(settings.RL_REFRESH)
async def refresh_token(
    request: Request,
    datos: schemas.SolicitudRefreshToken,
    db: AsyncSession = Depends(obtener_db),
    _auth_app=Depends(auth.verificar_sesion_aplicacion),
):
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
    # Rate-limit adicional por identidad (anti-abuso distribuido)
    check_identity_limit(
        "password_solicitar", datos.email, settings.RL_PASSWORD_SOLICITAR_ID
    )

    return await access_service.generar_codigo_recuperacion(
        db, datos.email, background_tasks
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
    # Rate-limit adicional por identidad (anti-abuso distribuido)
    check_identity_limit(
        "password_confirmar", datos.email, settings.RL_PASSWORD_CONFIRMAR_ID
    )

    return await access_service.resetear_password(db, datos)
