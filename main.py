"""
Punto de Entrada Principal - MoveOn API.
"""
from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError
from routers import users
from exceptions import manejador_validacion_personalizado
import database
from fastapi.staticfiles import StaticFiles
import os

app = FastAPI(
    title="MoveOn API",
    description="Backend de la aplicación MoveOn",
    version="0.1.4"
)

# Inicializar base de datos
database.init_db()

# registro de excepciones
app.add_exception_handler(RequestValidationError, manejador_validacion_personalizado)

# Incluir rutas
app.include_router(users.router)

# Crear la carpeta para guardar imagenes si no existe
if not os.path.exists("uploads"):
    os.makedirs("uploads")

# Montamos la carpeta para que sea accesible vía URL
# http://127.0.0.1:8000/imagenes/nombre_foto.jpg
# En producción creo que usaremos Cloudinary
app.mount("/imagenes", StaticFiles(directory="uploads"), name="imagenes")

@app.get("/")
def home():
    return {"estado": "en linea", "aplicacion": "MoveOn API"}