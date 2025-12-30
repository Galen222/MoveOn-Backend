# main.py

"""
Punto de Entrada Principal - MoveOn API.
"""
from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from routers import users, access, activities
from exceptions import manejador_validacion_personalizado
import database
from fastapi.staticfiles import StaticFiles
import os
from config import settings
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from limiter_config import limiter

# Declaración de API.
app = FastAPI(
    title="MoveOn API",
    description="Backend de la aplicación MoveOn",
    version="0.2.9"
)

# Configurar el limitador (usa la IP del usuario para contar)
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler) # type: ignore

# Configuración de CORS para permitir peticiones externas.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Inicializar base de datos.
database.init_db()

# Registro de excepciones.
# Para mostrar los errores de las validaciones de Pydantic
# con el mismo formato que los personalizados.
app.add_exception_handler(RequestValidationError, manejador_validacion_personalizado)

# Rutas a los endpoints.
app.include_router(access.router)
app.include_router(users.router)
app.include_router(activities.router)

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

# Endpoint raiz.
@app.get("/")
def home():
    return {"estado": "en linea", "aplicacion": "MoveOn API"}