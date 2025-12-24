# database.py

"""
Configuración de la Base de Datos y Modelos.

Este módulo establece la conexión con PostgreSQL mediante SQLAlchemy y define
la estructura de la tabla de usuarios.
"""
from datetime import datetime, date, timezone
from typing import Optional
from sqlalchemy import create_engine, String, Date, DateTime, Boolean
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, sessionmaker
from config import settings

# Construcción de la URL de conexión para PostgreSQL
DATABASE_URL = f"postgresql://{settings.DB_USER}:{settings.DB_PASSWORD}@{settings.DB_HOST}:{settings.DB_PORT}/{settings.DB_NAME}"

# Configuración del motor de SQLAlchemy y la sesión
engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

class Base(DeclarativeBase):
    """Clase base para todos los modelos con soporte de tipado moderno."""
    pass

class Usuario(Base):
    """
    Modelo de SQLAlchemy para la tabla de usuarios.

    Atributos:
        id: Identificador único autoincremental y clave primaria.
        nombre_usuario: Identificador único de acceso.
        nombre_real: Nombre y apellidos reales del usuario (alfanumérico).
        email: Dirección de correo electrónico única y validada.
        contraseña_encriptada: Hash seguro generado mediante bcrypt.
        fecha_nacimiento: Fecha de nacimiento para control de edad mínima.
        ciudad: Ubicación geográfica opcional proporcionada por el usuario.
        foto_perfil: Ruta o nombre del archivo de imagen (predeterminado o subido).
        fecha_registro: Marca de tiempo automática de la creación de cuenta.
        fecha_eula: Registro de cuándo el usuario aceptó los términos de servicio.
        perfil_visible: Ajuste de privacidad para mostrar u ocultar datos a terceros.
        codigo_recuperacion: Código unico y temporal para recuperación de contraseña.
        codigo_expiracion: Tiempo de expiración del código de recuperación.
    """
    __tablename__ = "usuarios"
    
    # Identificadores y datos de acceso
    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    nombre_usuario: Mapped[str] = mapped_column(String, unique=True, index=True)
    email: Mapped[str] = mapped_column(String, unique=True, index=True)
    contraseña_encriptada: Mapped[str] = mapped_column(String, nullable=False)
    
    # Información personal y perfil
    nombre_real: Mapped[str] = mapped_column(String, nullable=False)
    fecha_nacimiento: Mapped[date] = mapped_column(Date, nullable=False)
    ciudad: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    foto_perfil: Mapped[str] = mapped_column(String, default="default_avatar.png")
    
    # Metadatos automáticos del servidor
    fecha_registro: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc))
    fecha_eula: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc))
    
    # Ajustes de privacidad del usuario
    perfil_visible: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    
    # Recuperación de contraseña
    codigo_recuperacion: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    codigo_expiracion: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)

def init_db():
    """
    Inicialización de la base de datos.
    
    Crea físicamente las tablas definidas en los modelos de SQLAlchemy 
    si estas no existen previamente en la base de datos PostgreSQL.
    """
    Base.metadata.create_all(bind=engine)
    
def obtener_db():
    """Dependencia para la conexión a la base de datos."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()