# database.py

"""
Configuración de la Base de Datos y Modelos (ASYNC).

Este módulo establece la conexión con PostgreSQL mediante SQLAlchemy async
y define la estructura de las tablas.
"""
from datetime import datetime, date, timezone
from typing import Optional, AsyncGenerator
from urllib.parse import quote_plus
from sqlalchemy import (
    String, Date, DateTime, Boolean, Integer, Float, ForeignKey, Text, Index, func
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from sqlalchemy.ext.asyncio import (
    create_async_engine,
    AsyncSession,
    async_sessionmaker,
)

from config import settings

# Construcción de la URL de conexión para PostgreSQL
user_safe = quote_plus(settings.DB_USER)
pass_safe = quote_plus(settings.DB_PASSWORD)

DATABASE_URL = (
    f"postgresql+asyncpg://{user_safe}:{pass_safe}"
    f"@{settings.DB_HOST}:{settings.DB_PORT}/{settings.DB_NAME}"
)

# Motor ASYNC
engine = create_async_engine(
    DATABASE_URL,
    pool_pre_ping=True,
)

# Sesiones ASYNC
AsyncSessionLocal = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    autoflush=False,
    autocommit=False,
    expire_on_commit=False,  # evita expiraciones raras tras commit
)

class Base(DeclarativeBase):
    """Clase base para todos los modelos con soporte de tipado moderno."""
    pass

class Usuario(Base):
    """
    Modelo para la tabla de usuarios.

    Atributos:
        id: Identificador único autoincremental y clave primaria.
        nombre_usuario: Identificador único de acceso.
        nombre_real: Nombre y apellidos reales del usuario (alfanumérico).
        email: Dirección de correo electrónico única y validada.
        password_encriptada: Hash seguro generado mediante bcrypt.
        fecha_nacimiento: Fecha de nacimiento para control de edad mínima y control de calorias.
        genero: hombre, mujer u otro para control de calorias detallado.
        altura: altura personal para control de calorias detallado.        
        peso: peso personal para control de calorias detallado.
        provincia: Ubicación geográfica opcional proporcionada por el usuario.
        foto_perfil: Ruta o nombre del archivo de imagen (predeterminado o subido).
        total_metros: Distancia total recorrida para calcular el Ranking.
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
    password_encriptada: Mapped[str] = mapped_column(String, nullable=False)
    # Información personal y perfil
    nombre_real: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    fecha_nacimiento: Mapped[date] = mapped_column(Date, nullable=False)
    genero: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    altura: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    peso: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    provincia: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    foto_perfil: Mapped[str] = mapped_column(String, default="default_avatar.png")
    total_metros: Mapped[float] = mapped_column(Float, default=0.0, index=True)
    # Metadatos automáticos del servidor
    fecha_registro: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    fecha_eula: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    # Ajustes de privacidad del usuario
    perfil_visible: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    # Recuperación de contraseña
    # Guardamos el HASH SHA-256 del código (64 caracteres), no el código en claro
    codigo_recuperacion: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    codigo_expiracion: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    
    __table_args__ = (
        # Evita duplicados tipo Usuario/usuARio/USUARIO
        Index("uq_usuarios_nombre_usuario_lower", func.lower(nombre_usuario), unique=True),

        # Blinda incluso si alguien guarda emails con mayúsculas
        Index("uq_usuarios_email_lower", func.lower(email), unique=True),
    )
class Actividad(Base):
    """
    Modelo para registrar las actividades deportivas.
    Relación 1:N con Usuario (Un usuario tiene muchas actividades).
    
    Atributos:
        usuario_id: Identificador único del usuario y clave primaria.
        tipo: Tipo de actividad realizada en la ruta.
        distancia: Distancia recorrida en la ruta en metros.
        duracion: Tiempo haciendo la ruta en segundos.
        calorias_quemadas: Total de calorias quemadas durante la ruta.
        ruta_polilinea: Ruta realizada en formato string de Google Maps.
        ruta_mapa_url: URL con la ruta generada a traves de la polilinea.
        fecha_ruta: fecha en la que se realizo la ruta.
    """
    __tablename__ = "actividades"
    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    usuario_id: Mapped[int] = mapped_column(ForeignKey("usuarios.id", ondelete="CASCADE"), nullable=False, index=True )
    # Datos de ruta.
    tipo: Mapped[str] = mapped_column(String, nullable=False)
    distancia: Mapped[float] = mapped_column(Float, nullable=False)
    duracion: Mapped[int] = mapped_column(Integer, nullable=False)
    calorias_quemadas: Mapped[int] = mapped_column(Integer, nullable=False)
    # Datos de la ruta (Geometría).
    # Uso Text porque la polyline puede ser muy larga.
    ruta_polilinea: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    # Instantanea del mapa
    ruta_mapa_url: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    fecha_ruta: Mapped[datetime] = mapped_column(DateTime(timezone=True),  default=lambda: datetime.now(timezone.utc), index=True)
    
class SesionRefresh(Base):
    """
    Guarda sesiones refresh por dispositivo/sesión para permitir:
    - expiración larga
    - rotación
    - revocación (logout)
    """
    __tablename__ = "sesiones_refresh"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    usuario_id: Mapped[int] = mapped_column(ForeignKey("usuarios.id", ondelete="CASCADE"), nullable=False, index=True)
    # Identidad del refresh token (JWT)
    jti: Mapped[str] = mapped_column(String, unique=True, index=True)
    familia_id: Mapped[str] = mapped_column(String, index=True)
    # Hash del refresh token (nunca guardamos el token en claro)
    token_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    # Ciclo de vida
    creada_en: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    ultimo_uso_en: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    expira_en: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    # Revocación / rotación
    revocada_en: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True, index=True)
    reemplazada_por_jti: Mapped[Optional[str]] = mapped_column(String, nullable=True)

async def init_db() -> None:
    """
    Inicialización de la base de datos.
    
    Crea físicamente las tablas definidas en los modelos de SQLAlchemy 
    si estas no existen previamente en la base de datos PostgreSQL.
    """
    # Solo crea las tablas si lo indica el .env
    if not settings.AUTO_CREATE_TABLES:
        return
    
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

async def close_db() -> None:
    """Cerrar el engine (graceful shutdown)."""
    await engine.dispose()

async def obtener_db() -> AsyncGenerator[AsyncSession, None]:
    """Dependencia ASYNC para la conexión a la base de datos."""
    async with AsyncSessionLocal() as db:
        yield db
