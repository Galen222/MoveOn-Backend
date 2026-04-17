# main.py

"""
Punto de Entrada Principal - MoveOn API.
CORS no se implementa pues el backend se consume por una app Android y no una web.
"""
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request, Depends, HTTPException
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.responses import FileResponse
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession
from routers import users, access, activities
from exceptions import (
    manejador_validacion_personalizado,
    manejador_http_exception,
    manejador_excepcion_no_controlada,
    error_response,
)
import database
from fastapi.staticfiles import StaticFiles
import os
import logging
from config import settings
from exceptions import app_http_exception

from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware
from middlewares.security_headers import SecurityHeadersMiddleware
from middlewares.request_context import RequestContextMiddleware
from middlewares.request_size import RequestSizeLimitMiddleware
from logging_config import setup_logging
from ip_rate_limit import HEADER_ORDER, conn_from_trusted_proxy, limiter, rate_limit
from services.identity_rate_limit import IdentityRateLimitExceeded
from utils.ip_cliente import get_client_ip

setup_logging()

logger = logging.getLogger("app.main")


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Inicializar base de datos sin bloquear el arranque si PostgreSQL está caído.
    try:
        await database.init_db()
    except Exception as exc:
        logger.warning(
            "fallo_inesperado_BD_inicio_continua",
            extra={
                "error_type": type(exc).__name__,
                "error": str(exc),
            },
        )

    # Obtener el tipo de almacenamiento para las imagenes.
    # Seleccionando entre local (desarrollo) y Cloudinary (producción)
    STORAGE_TYPE = settings.STORAGE_TYPE
    # Configurar almacenamiento local si es necesario.
    if STORAGE_TYPE == "local":
        # Usar la variable de settings con el nombre de la carpeta.
        carpeta_imagenes = settings.UPLOAD_DIR
        # Crear la carpeta para guardar imagenes en local si no existe.
        if not os.path.exists(carpeta_imagenes):
            os.makedirs(carpeta_imagenes)
        # Se monta la carpeta para que sea accesible vía URL
        # http://127.0.0.1:8000/imagenes/foto.jpg
        app.mount("/imagenes", StaticFiles(directory=carpeta_imagenes), name="imagenes")

    logger.info(
        "aplicacion_iniciada",
        extra={
            "storage_type": settings.STORAGE_TYPE,
            "enable_docs": settings.ENABLE_DOCS,
            "enable_rate_limit_ip": settings.ENABLE_RATE_LIMIT_IP,
            "enable_rate_limit_id": settings.ENABLE_RATE_LIMIT_ID,
            "enable_security_headers": settings.ENABLE_SECURITY_HEADERS,
            "trust_proxy_lan": settings.TRUST_PROXY_LAN,
            "trust_proxy_wan": settings.TRUST_PROXY_WAN,
        },
    )

    yield

    await database.close_db()

    logger.info(
        "aplicacion_detenida",
        extra={},
    )


# Declaración de API.
app = FastAPI(
    title="MoveOn API",
    description="Backend de la aplicación MoveOn",
    version="0.9.6",
    lifespan=lifespan,
    docs_url="/docs" if settings.ENABLE_DOCS else None,
    redoc_url="/redoc" if settings.ENABLE_DOCS else None,
    openapi_url="/openapi.json" if settings.ENABLE_DOCS else None,
)

REQUEST_SIZE_LIMITS = {
    ("POST", "/login"): 8 * 1024,
    ("POST", "/registro"): 16 * 1024,
    ("POST", "/password/solicitar"): 4 * 1024,
    ("POST", "/password/confirmar"): 8 * 1024,
}

# Configurar el limitador (usa la IP del usuario para contar)
app.state.limiter = limiter

# Middleware de SlowAPI (si no, el rate limit puede no comportarse correctamente)
if settings.ENABLE_RATE_LIMIT_IP:
    app.add_middleware(SlowAPIMiddleware)

# Middleware de tamaño del body para rutas JSON sensibles.
# Se añade aquí para que las respuestas 413 sigan pasando por
# request_id y cabeceras de seguridad.
app.add_middleware(
    RequestSizeLimitMiddleware,
    route_limits=REQUEST_SIZE_LIMITS,
)

# Middleware de contexto/request_id
app.add_middleware(RequestContextMiddleware)

# Middleware de Seguridad
if settings.ENABLE_SECURITY_HEADERS:
    app.add_middleware(SecurityHeadersMiddleware)


# Handler de rate limit IP
@app.exception_handler(RateLimitExceeded)
async def rate_limit_handler(request: Request, exc: RateLimitExceeded):
    headers = getattr(exc, "headers", None) or {}

    logger.warning(
        "limite_por_ip_superado",
        extra={
            "method": request.method,
            "path": request.url.path,
            "client_ip": get_client_ip(
                request,
                is_trusted_proxy=conn_from_trusted_proxy,
                header_order=HEADER_ORDER,
            ),
        },
    )

    return error_response(
        status_code=429,
        mensaje="Demasiadas peticiones. Inténtalo más tarde.",
        headers=headers,
    )


# Handler de rate limit por identidad
@app.exception_handler(IdentityRateLimitExceeded)
async def identity_rate_limit_handler(request: Request, exc: IdentityRateLimitExceeded):
    return error_response(status_code=429, mensaje=exc.mensaje)


# Registro de excepciones.
# Para mostrar los errores de las validaciones de Pydantic
# con el mismo formato que los personalizados.
app.add_exception_handler(RequestValidationError, manejador_validacion_personalizado)


async def http_exception_handler_wrapper(
    request: Request, exc: Exception
) -> JSONResponse:
    if isinstance(exc, HTTPException):
        return manejador_http_exception(request, exc)
    return manejador_excepcion_no_controlada(request, exc)


async def generic_exception_handler_wrapper(
    request: Request, exc: Exception
) -> JSONResponse:
    return manejador_excepcion_no_controlada(request, exc)


app.add_exception_handler(HTTPException, http_exception_handler_wrapper)
app.add_exception_handler(Exception, generic_exception_handler_wrapper)

# Rutas a los endpoints.
app.include_router(access.router)
app.include_router(users.router)
app.include_router(activities.router)


# Endpoint raiz.
@app.get("/")
@rate_limit(settings.RL_ROOT)
async def home(request: Request):
    return {"estado": "en linea", "aplicacion": "MoveOn API"}


@app.get("/healthz", include_in_schema=False)
@app.head("/healthz", include_in_schema=False)
async def healthz():
    return {"status": "ok"}


@app.get("/readyz", include_in_schema=False)
async def readyz(db: AsyncSession = Depends(database.obtener_db)):
    try:
        await db.execute(text("SELECT 1"))

        logger.debug(
            "comprobacion_readiness_correcta",
            extra={},
        )

        return {"status": "ready", "database": "ok"}
    except Exception:
        logger.exception(
            "comprobacion_readiness_fallida",
            extra={},
        )

        return JSONResponse(
            status_code=503,
            content={"status": "not_ready", "database": "error"},
        )


# Endpoint icono.
@app.get("/favicon.ico", include_in_schema=False)
@rate_limit(settings.RL_FAVICON)
async def favicon(request: Request):
    if not os.path.exists("favicon.ico"):
        raise app_http_exception(
            status_code=404,
            mensaje="No existe favicon.ico",
            error_code="FAVICON_NOT_FOUND",
        )
    return FileResponse("favicon.ico")
