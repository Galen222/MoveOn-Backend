# main.py

"""
Punto de Entrada Principal - MoveOn API.
"""
from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from routers import users, access
from exceptions import manejador_validacion_personalizado
import database
from fastapi.staticfiles import StaticFiles
import os
from config import settings

# Declaración de API.
app = FastAPI(
    title="MoveOn API",
    description="Backend de la aplicación MoveOn",
    version="0.1.8"
)

# Configuración de CORS para permitir peticiones desde la App.
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
app.add_exception_handler(RequestValidationError, manejador_validacion_personalizado)

# Incluir rutas.
app.include_router(users.router)
app.include_router(access.router)

# Obtener el tipo de almacenamiento para las imagenes.
STORAGE_TYPE = settings.STORAGE_TYPE

# Configurar almacenamiento local si es necesario.
if STORAGE_TYPE == "local":
    # Crear la carpeta para guardar imagenes en local si no existe.
    if not os.path.exists("uploads"):
        os.makedirs("uploads")
    # Se monta la carpeta para que sea accesible vía URL
    # http://127.0.0.1:8000/imagenes/default_avatar.jpg    
    app.mount("/imagenes", StaticFiles(directory="uploads"), name="imagenes")

# Endpoint raiz.
@app.get("/")
def home():
    return {"estado": "en linea", "aplicacion": "MoveOn API"}