# database.py

"""
Configuración de la Base de Datos y Modelos.

Este módulo establece la conexión con PostgreSQL mediante SQLAlchemy y define
la estructura de la tabla de usuarios utilizando variables de entorno.
"""
import os
from dotenv import load_dotenv
from sqlalchemy import create_engine, Column, Integer, String
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker

# Cargar variables desde el archivo .env
load_dotenv()

# Configuración de credenciales de la base de datos
DB_USER = os.getenv("DB_USER")
DB_PASSWORD = os.getenv("DB_PASSWORD")
DB_HOST = os.getenv("DB_HOST")
DB_PORT = os.getenv("DB_PORT")
DB_NAME = os.getenv("DB_NAME")

# Construcción de la URL de conexión para PostgreSQL
DATABASE_URL = f"postgresql://{DB_USER}:{DB_PASSWORD}@{DB_HOST}:{DB_PORT}/{DB_NAME}"

# Configuración del motor de SQLAlchemy y la sesión
engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

class Usuario(Base):
    """
    Modelo de SQLAlchemy para la tabla de usuarios.
    
    Attributes:
        id: Identificador único autoincremental.
        nombre: Nombre de usuario único para inicio de sesión.
        email: Correo electrónico único.
        contraseña_encriptada: Hash de la contraseña generado con bcrypt.
    """
    __tablename__ = "usuarios"
    id = Column(Integer, primary_key=True, index=True)
    nombre = Column(String, unique=True, index=True)
    email = Column(String, unique=True, index=True)
    contraseña_encriptada = Column(String)

def init_db():
    """Crea las tablas físicamente en la base de datos de Postgres si no existen."""
    Base.metadata.create_all(bind=engine)