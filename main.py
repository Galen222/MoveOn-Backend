# main.py

"""
Punto de Entrada Principal - MoveOn API.
"""
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.responses import FileResponse
from routers import users, access, activities
from exceptions import manejador_validacion_personalizado
import database
from fastapi.staticfiles import StaticFiles
import os
from config import settings

from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware
from middlewares.security_headers import SecurityHeadersMiddleware
from limiter_config import limiter, rate_limit


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Inicializar base de datos.
    await database.init_db()

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
        # http://127.0.0.1:8000/imagenes/default_avatar.jpg
        app.mount("/imagenes", StaticFiles(directory=carpeta_imagenes), name="imagenes")

    yield

    # (Opcional) Cerrar recursos de la BD al apagar la app.
    await database.close_db()


# Declaración de API.
app = FastAPI(
    title="MoveOn API",
    description="Backend de la aplicación MoveOn",
    version="0.3.6",
    lifespan=lifespan,
    docs_url="/docs" if settings.ENABLE_DOCS else None,
    redoc_url="/redoc" if settings.ENABLE_DOCS else None,
    openapi_url="/openapi.json" if settings.ENABLE_DOCS else None
)

# Configurar el limitador (usa la IP del usuario para contar)
app.state.limiter = limiter

# Middleware de SlowAPI (si no, el rate limit puede no comportarse correctamente)
if settings.ENABLE_RATE_LIMIT_IP:
    app.add_middleware(SlowAPIMiddleware)

# Middleware de Seguridad
if settings.ENABLE_SECURITY_HEADERS:
    app.add_middleware(SecurityHeadersMiddleware)

# Handler (JSON consistente para Android + headers de rate limit si existen)
@app.exception_handler(RateLimitExceeded)
async def rate_limit_handler(request: Request, exc: RateLimitExceeded):
    headers = getattr(exc, "headers", None) or {}
    return JSONResponse(
        status_code=429,
        content={
            "estatus": "error",
            "mensaje": "Demasiadas peticiones. Inténtalo más tarde."
        },
        headers=headers
    )

# Configuración de CORS para permitir peticiones externas.
if settings.ENABLE_CORS:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[o.strip() for o in settings.CORS_ORIGINS.split(",") if o.strip()],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

# Registro de excepciones.
# Para mostrar los errores de las validaciones de Pydantic
# con el mismo formato que los personalizados.
app.add_exception_handler(RequestValidationError, manejador_validacion_personalizado)

# Rutas a los endpoints.
app.include_router(access.router)
app.include_router(users.router)
app.include_router(activities.router)

# Endpoint raiz.
@app.get("/")
@rate_limit(settings.RL_ROOT)
def home(request: Request):
    return {"estado": "en linea", "aplicacion": "MoveOn API"}

# Endpoint icono.
@app.get("/favicon.ico", include_in_schema=False)
@rate_limit(settings.RL_FAVICON)
async def favicon(request: Request):
    return FileResponse("favicon.ico")
