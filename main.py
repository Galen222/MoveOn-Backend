"""
Punto de Entrada Principal - MoveOn API.
"""
from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError
from routers import users
from exceptions import manejador_validacion_personalizado
import database

app = FastAPI(
    title="MoveOn API",
    description="Backend modular con seguridad Handshake + JWT",
    version="0.1.2"
)

# Inicializar base de datos
database.init_db()

# registro de excepciones
app.add_exception_handler(RequestValidationError, manejador_validacion_personalizado)

# Incluir rutas
app.include_router(users.router)

@app.get("/")
def home():
    return {"estado": "en linea", "aplicacion": "MoveOn API"}