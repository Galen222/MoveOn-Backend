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
    """Ciclo de vida de la app: inicializa y libera recursos del proceso.

    En el arranque, intenta abrir la conexión a PostgreSQL. Si la base de
    datos está caída, registra el fallo y deja continuar para que los
    endpoints de salud (``/healthz``, ``/readyz``) puedan seguir
    respondiendo. Configura además el almacenamiento local de imágenes
    montando ``/imagenes`` cuando ``STORAGE_TYPE == "local"``.

    En el apagado cierra la pool de la base de datos de forma ordenada.

    Args:
        app: instancia de ``FastAPI`` sobre la que montar recursos.

    Yields:
        Control a FastAPI mientras la aplicación está en funcionamiento.
    """
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
    version="1.0.8",
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
    ("POST", "/actividad/guardar"): 256 * 1024,
}

# Configurar el limitador (usa la IP del usuario para contar)
app.state.limiter = limiter

# Middleware de SlowAPI (si no, el límite de tasa puede no comportarse correctamente)
if settings.ENABLE_RATE_LIMIT_IP:
    app.add_middleware(SlowAPIMiddleware)

# Middleware de tamaño del cuerpo para rutas JSON sensibles.
# Se añade aquí para que las respuestas 413 sigan pasando por
# petición_id y cabeceras de seguridad.
app.add_middleware(
    RequestSizeLimitMiddleware,
    route_limits=REQUEST_SIZE_LIMITS,
)

# Middleware de contexto/petición_id
app.add_middleware(RequestContextMiddleware)

# Middleware de Seguridad
if settings.ENABLE_SECURITY_HEADERS:
    app.add_middleware(SecurityHeadersMiddleware)


# Manejador del límite de tasa por IP
@app.exception_handler(RateLimitExceeded)
async def rate_limit_handler(request: Request, exc: RateLimitExceeded):
    """Handler de ``RateLimitExceeded`` (rate limit por IP de ``slowapi``).

    Registra el límite superado junto con la IP del cliente (resolviendo
    correctamente la IP real detrás de proxies confiables) y responde
    429 con el mensaje estándar, preservando las cabeceras de rate limit
    que ``slowapi`` haya incluido en la excepción.

    Args:
        request: petición entrante que disparó el rate limit.
        exc: excepción lanzada por ``slowapi`` con las cabeceras ``Retry-After``.

    Returns:
        Respuesta 429 con mensaje neutro y cabeceras de rate limit propagadas.
    """
    # Gestiona límite de tasa handler.
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


# Manejador del límite de tasa por identidad
@app.exception_handler(IdentityRateLimitExceeded)
async def identity_rate_limit_handler(request: Request, exc: IdentityRateLimitExceeded):
    """Handler del rate limit por identidad (no por IP).

    Lo dispara ``services/identity_rate_limit.py`` cuando un mismo
    email/usuario supera el umbral en operaciones sensibles como login
    o recuperación de contraseña, evitando ataques de fuerza bruta
    incluso si el atacante rota IPs.

    Args:
        request: petición entrante que disparó el límite.
        exc: excepción con el mensaje humano a devolver.

    Returns:
        Respuesta 429 con el mensaje específico aportado por la excepción.
    """
    return error_response(status_code=429, mensaje=exc.mensaje)


# Registro de excepciones.
# Para mostrar los errores de las validaciones de Pydantic
# con el mismo formato que los personalizados.
app.add_exception_handler(RequestValidationError, manejador_validacion_personalizado)


async def http_exception_handler_wrapper(
    request: Request, exc: Exception
) -> JSONResponse:
    """Adaptador que delega en el handler apropiado según el tipo real.

    FastAPI registra este wrapper para ``HTTPException``, pero el
    propio framework a veces entrega aquí excepciones más genéricas
    (por ejemplo al envolver errores en middlewares). Esta capa
    comprueba el tipo en runtime y delega en
    ``manejador_http_exception`` para HTTP o en el de excepción no
    controlada en cualquier otro caso.

    Args:
        request: petición entrante.
        exc: excepción capturada por el framework.

    Returns:
        Respuesta JSON con el formato estándar de error del API.
    """
    if isinstance(exc, HTTPException):
        return manejador_http_exception(request, exc)
    return manejador_excepcion_no_controlada(request, exc)


async def generic_exception_handler_wrapper(
    request: Request, exc: Exception
) -> JSONResponse:
    """Handler global para cualquier excepción no controlada.

    Siempre delega en ``manejador_excepcion_no_controlada``, que
    registra el traceback completo y devuelve un 500 genérico sin
    filtrar internals al cliente.

    Args:
        request: petición entrante.
        exc: excepción no capturada por ningún handler específico.

    Returns:
        Respuesta 500 con mensaje neutro y ``error_code`` genérico.
    """
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
    """Endpoint raíz de sanity check accesible públicamente.

    No consulta base de datos, sólo verifica que el proceso responde
    (útil para probes de load balancer que solo miran 2xx). El
    decorador ``@rate_limit`` evita que scanners automáticos
    desencadenen ruido.

    Args:
        request: petición entrante; la necesita ``slowapi`` para aplicar el rate limit.

    Returns:
        Diccionario simple con el estado del servicio.
    """
    return {"estado": "en linea", "aplicacion": "MoveOn API"}


@app.get("/healthz", include_in_schema=False)
@app.head("/healthz", include_in_schema=False)
async def healthz():
    """Probe de liveness sin dependencias externas.

    Devuelve 200 mientras el proceso esté vivo, aunque la base de datos
    esté caída. Es el endpoint que Kubernetes/Heroku debe usar para
    reiniciar contenedores colgados, distinto del readiness.

    Returns:
        ``{"status": "ok"}`` siempre que el proceso pueda servir la petición.
    """
    return {"status": "ok"}


@app.get("/readyz", include_in_schema=False)
async def readyz(db: AsyncSession = Depends(database.obtener_db)):
    """Probe de readiness que valida también la base de datos.

    Ejecuta un ``SELECT 1`` para confirmar que la app puede aceptar
    tráfico útil. Si la base de datos no responde, devuelve 503 para
    que el balanceador saque la instancia del pool hasta que se
    recupere, sin tumbar el proceso (liveness sigue sana).

    Args:
        db: sesión asíncrona inyectada por FastAPI.

    Returns:
        ``{"status": "ready", "database": "ok"}`` si la consulta triunfa;
        respuesta 503 con ``{"status": "not_ready", "database": "error"}`` en caso contrario.
    """
    # Devuelve el estado de preparación del servicio.
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
    """Sirve el ``favicon.ico`` del repositorio si existe.

    Navegadores y previews de enlaces lo piden automáticamente; si no
    se trata aquí explícitamente genera ruido en los logs. Si falta el
    fichero devuelve 404 con ``FAVICON_NOT_FOUND`` en lugar de un error
    genérico.

    Args:
        request: petición entrante; la necesita ``slowapi``.

    Returns:
        Contenido binario del favicon con su ``Content-Type`` correcto.

    Raises:
        AppHTTPException: 404 ``FAVICON_NOT_FOUND`` si el fichero no existe en disco.
    """
    if not os.path.exists("favicon.ico"):
        raise app_http_exception(
            status_code=404,
            mensaje="No existe favicon.ico",
            error_code="FAVICON_NOT_FOUND",
        )
    return FileResponse("favicon.ico")
