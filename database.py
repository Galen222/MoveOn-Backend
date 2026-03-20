# database.py

"""
Configuración de la Base de Datos y Modelos (ASYNC).

Objetivos de este módulo:
- Centralizar la conexión ASYNC a PostgreSQL.
- Definir los modelos ORM del proyecto.
- Aplicar una segunda capa de validación en Python con SQLAlchemy (@validates).
- Endurecer la base de datos con CheckConstraint e índices útiles.
- Mantener compatibilidad con el diseño actual del proyecto:
  * los enums se persisten como String
  * schemas.py y database.py comparten domain.enums
  * total_puntos se calcula a partir de total_metros
"""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from typing import Optional, AsyncGenerator, Any
from urllib.parse import quote_plus
import logging
import re

import sqlalchemy as sa
from email_validator import EmailNotValidError, validate_email
from pydantic import AnyHttpUrl, TypeAdapter, ValidationError as PydanticValidationError
from sqlalchemy import (
    String,
    Date,
    DateTime,
    Boolean,
    Integer,
    BigInteger,
    Float,
    ForeignKey,
    Text,
    Index,
    CheckConstraint,
    func,
    text,
)
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, validates

from config import settings
from domain.enums import ProvinciaEspaña, GeneroUsuario, TipoActividad
from utils import validators
from exceptions import AppValidationError


# =========================================================
# Conexión a base de datos (lazy)
# =========================================================

logger = logging.getLogger("app.database")

engine: AsyncEngine | None = None
AsyncSessionLocal: async_sessionmaker[AsyncSession] | None = None


def _build_database_url() -> str:
    """Construye la URL de conexión escapando usuario y password."""
    user_safe = quote_plus(settings.DB_USER)
    pass_safe = quote_plus(settings.DB_PASSWORD)

    return (
        f"postgresql+asyncpg://{user_safe}:{pass_safe}"
        f"@{settings.DB_HOST}:{settings.DB_PORT}/{settings.DB_NAME}"
    )


def get_database_url() -> str:
    """
    Devuelve la URL de base de datos lista para ser usada por la app o por Alembic.

    Se expone como helper público para evitar que herramientas externas dependan de
    detalles internos del módulo.
    """
    return _build_database_url()


# Compatibilidad con Alembic/env.py y con cualquier import legado.
DATABASE_URL = get_database_url()


def _init_db_objects() -> None:
    """
    Inicializa engine y sessionmaker solo una vez.

    No abre conexión real a PostgreSQL; solo prepara los objetos de SQLAlchemy.
    """
    global engine, AsyncSessionLocal

    if engine is not None and AsyncSessionLocal is not None:
        return

    database_url = _build_database_url()

    engine = create_async_engine(
        database_url,
        pool_pre_ping=True,
        pool_size=int(settings.DB_POOL_SIZE),
        max_overflow=int(settings.DB_MAX_OVERFLOW),
        pool_timeout=int(settings.DB_POOL_TIMEOUT),
        pool_recycle=int(settings.DB_POOL_RECYCLE),
    )

    AsyncSessionLocal = async_sessionmaker(
        bind=engine,
        class_=AsyncSession,
        autoflush=False,
        autocommit=False,
        expire_on_commit=False,  # evita expiraciones molestas tras commit
    )


# =========================================================
# Base declarativa
# =========================================================


class Base(DeclarativeBase):
    """Clase base para todos los modelos ORM."""

    pass


# =========================================================
# Constantes y helpers internos
# =========================================================

# Regex en Python para validaciones ORM
_USERNAME_RE = re.compile(r"^[a-zA-Z0-9]+$")
_HEX64_RE = re.compile(r"^[0-9a-f]{64}$", re.IGNORECASE)

# Adaptador Pydantic para validar URLs http/https igual que en schemas.py
_HTTP_URL_ADAPTER = TypeAdapter(AnyHttpUrl)

# Valores válidos compartidos desde domain.enums
VALID_GENEROS = {item.value for item in GeneroUsuario}
VALID_PROVINCIAS = {item.value for item in ProvinciaEspaña}
VALID_TIPOS_ACTIVIDAD = {item.value for item in TipoActividad}


def _ahora_utc() -> datetime:
    """Devuelve la fecha/hora actual en UTC."""
    return datetime.now(timezone.utc)


def _normalizar_datetime_utc(v: Optional[datetime]) -> Optional[datetime]:
    """
    Normaliza un datetime a UTC.

    - Si llega naive, lo interpretamos como UTC por compatibilidad.
    - Si llega aware, lo convertimos a UTC.
    """
    if v is None:
        return None
    return (
        v.replace(tzinfo=timezone.utc)
        if v.tzinfo is None
        else v.astimezone(timezone.utc)
    )


def _sql_quote(value: str) -> str:
    """Escapa un string para incrustarlo de forma segura en un CheckConstraint SQL."""
    return "'" + value.replace("'", "''") + "'"


def _sql_in_values(values: set[str]) -> str:
    """Convierte un set de valores a una lista SQL: 'A', 'B', 'C'."""
    return ", ".join(_sql_quote(v) for v in sorted(values))


def _build_enum_check_sql(
    column_name: str, values: set[str], allow_null: bool = True
) -> str:
    """
    Genera el SQL para un constraint tipo:
      columna IN ('A', 'B', ...)
    o:
      columna IS NULL OR columna IN (...)
    """
    clause = f"{column_name} IN ({_sql_in_values(values)})"
    return f"{column_name} IS NULL OR {clause}" if allow_null else clause


def _validar_enum_str(
    valor: Optional[Any],
    permitidos: set[str],
    nombre_campo: str,
    *,
    must_be_text_code: str,
    invalid_code: str,
) -> Optional[str]:
    """
    Valida un valor de enum persistido como String.

    Acepta:
    - el Enum directamente
    - el .value del Enum
    - un string plano
    """
    if valor is None:
        return None

    if hasattr(valor, "value"):
        valor = valor.value

    if not isinstance(valor, str):
        raise AppValidationError(
            f"Error: {nombre_campo} debe ser un texto válido",
            must_be_text_code,
        )

    valor = valor.strip()
    if valor not in permitidos:
        raise AppValidationError(
            f"Error: {nombre_campo} no es válido",
            invalid_code,
        )

    return valor


def _validar_hex64_opcional(
    valor: Optional[str],
    nombre_campo: str,
    *,
    must_be_string_code: str,
    invalid_code: str,
) -> Optional[str]:
    """Valida un hash hexadecimal SHA-256 de 64 caracteres."""
    if valor is None:
        return None

    if not isinstance(valor, str):
        raise AppValidationError(
            f"Error: {nombre_campo} debe ser un string",
            must_be_string_code,
        )

    valor = valor.strip()
    if not _HEX64_RE.fullmatch(valor):
        raise AppValidationError(
            f"Error: {nombre_campo} debe ser un hash SHA-256 hexadecimal de 64 caracteres",
            invalid_code,
        )

    return valor.lower()


def _validar_texto_no_vacio(
    valor: str,
    nombre_campo: str,
    max_len: int,
    *,
    must_be_string_code: str,
    empty_code: str,
    too_long_code: str,
) -> str:
    """Valida que un texto no esté vacío y no supere una longitud máxima."""
    if not isinstance(valor, str):
        raise AppValidationError(
            f"Error: {nombre_campo} debe ser un string",
            must_be_string_code,
        )

    valor = valor.strip()
    if not valor:
        raise AppValidationError(
            f"Error: {nombre_campo} no puede estar vacío",
            empty_code,
        )
    if len(valor) > max_len:
        raise AppValidationError(
            f"Error: {nombre_campo} no puede superar los {max_len} caracteres",
            too_long_code,
        )

    return valor


def _validar_url_http_opcional(
    valor: Optional[str],
    nombre_campo: str,
    max_len: int = 2048,
    *,
    must_be_text_code: str,
    too_long_code: str,
    invalid_code: str,
) -> Optional[str]:
    """
    Valida una URL http/https opcional.

    Se usa el mismo criterio fuerte que en Pydantic con AnyHttpUrl.
    """
    if valor is None:
        return None

    if not isinstance(valor, str):
        raise AppValidationError(
            f"Error: {nombre_campo} debe ser un texto",
            must_be_text_code,
        )

    valor = valor.strip()
    if not valor:
        return None

    if len(valor) > max_len:
        raise AppValidationError(
            f"Error: {nombre_campo} no puede superar los {max_len} caracteres",
            too_long_code,
        )

    try:
        parsed = _HTTP_URL_ADAPTER.validate_python(valor)
    except PydanticValidationError:
        raise AppValidationError(
            f"Error: {nombre_campo} no es una URL http/https válida",
            invalid_code,
        )

    return str(parsed)


# =========================================================
# Modelo Usuario
# =========================================================


class Usuario(Base):
    """
    Tabla de usuarios.

    Diseño actual del proyecto:
    - genero y provincia se guardan como texto (String), no como Enum SQL nativo.
    - total_metros se persiste en DB.
    - total_puntos se calcula dinámicamente a partir de total_metros.
    """

    __tablename__ = "usuarios"

    # -------------------------
    # Identificadores y acceso
    # -------------------------
    id: Mapped[int] = mapped_column(primary_key=True)
    nombre_usuario: Mapped[str] = mapped_column(String(50), nullable=False)
    email: Mapped[str] = mapped_column(String(320), nullable=False)
    password_encriptada: Mapped[str] = mapped_column(String(255), nullable=False)

    # -------------------------
    # Datos de perfil
    # -------------------------
    nombre_real: Mapped[Optional[str]] = mapped_column(String(80), nullable=True)
    fecha_nacimiento: Mapped[date] = mapped_column(Date, nullable=False)
    genero: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    altura: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    peso: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    provincia: Mapped[Optional[str]] = mapped_column(String(40), nullable=True)

    # -------------------------
    # Imagen de perfil
    # -------------------------
    foto_perfil: Mapped[Optional[str]] = mapped_column(
        String(500),
        nullable=True,
    )
    foto_fecha_actualizacion: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    # -------------------------
    # Acumulado deportivo
    # -------------------------
    total_metros: Mapped[int] = mapped_column(
        BigInteger,
        nullable=False,
        default=0,
        server_default=text("0"),
        index=True,
    )

    total_calorias: Mapped[int] = mapped_column(
        BigInteger,
        nullable=False,
        default=0,
        server_default=text("0"),
    )

    # -------------------------
    # Objetivos del usuario
    # -------------------------
    objetivo_semanal_metros: Mapped[int] = mapped_column(
        BigInteger,
        nullable=False,
        default=50_000,
        server_default=text("50000"),
    )

    objetivo_mensual_metros: Mapped[int] = mapped_column(
        BigInteger,
        nullable=False,
        default=150_000,
        server_default=text("150000"),
    )

    # -------------------------
    # Trazabilidad / legal
    # -------------------------
    fecha_registro: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=_ahora_utc,
        server_default=text("CURRENT_TIMESTAMP"),
    )
    fecha_eula: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
    )
    acepta_terminos: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
    )
    version_terminos: Mapped[str] = mapped_column(
        String(10),
        nullable=False,
    )

    # -------------------------
    # Privacidad
    # -------------------------
    perfil_visible: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=True,
        server_default=sa.true(),
    )

    # -------------------------
    # Recuperación de contraseña
    # -------------------------
    codigo_recuperacion: Mapped[Optional[str]] = mapped_column(
        String(64),
        nullable=True,
    )
    codigo_expiracion: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    __table_args__ = (
        # Unicidad case-insensitive
        Index(
            "uq_usuarios_nombre_usuario_lower", func.lower(nombre_usuario), unique=True
        ),
        Index("uq_usuarios_email_lower", func.lower(email), unique=True),
        # Longitud y formato del username
        CheckConstraint(
            "char_length(nombre_usuario) BETWEEN 5 AND 50",
            name="ck_usuarios_nombre_usuario_len",
        ),
        CheckConstraint(
            "nombre_usuario ~ '^[A-Za-z0-9]+$'", name="ck_usuarios_nombre_usuario_alnum"
        ),
        # Email: saneado básico a nivel SQL
        # Nota: la validación fuerte real sigue en Python con email_validator.
        CheckConstraint(
            "char_length(email) BETWEEN 3 AND 320", name="ck_usuarios_email_len"
        ),
        CheckConstraint(
            "email = lower(btrim(email))", name="ck_usuarios_email_normalized_lower"
        ),
        CheckConstraint("email !~ '[[:space:]]'", name="ck_usuarios_email_no_spaces"),
        CheckConstraint(
            r"email ~ '^[^@[:space:]]+@[^@[:space:]]+\.[^@[:space:]]+$'",
            name="ck_usuarios_email_basic_format",
        ),
        # password hash no vacío
        CheckConstraint(
            "char_length(btrim(password_encriptada)) > 0",
            name="ck_usuarios_password_hash_non_empty",
        ),
        # nombre real, si viene, no puede ser vacío ni exceder 80
        CheckConstraint(
            "nombre_real IS NULL OR char_length(btrim(nombre_real)) BETWEEN 3 AND 80",
            name="ck_usuarios_nombre_real_len",
        ),
        # Edad mínima y evitar fechas futuras
        CheckConstraint(
            "fecha_nacimiento <= CURRENT_DATE",
            name="ck_usuarios_fecha_nacimiento_not_future",
        ),
        CheckConstraint(
            "fecha_nacimiento <= (CURRENT_DATE - INTERVAL '18 years')",
            name="ck_usuarios_fecha_nacimiento_adult",
        ),
        # Enums persistidos como String
        CheckConstraint(
            _build_enum_check_sql("genero", VALID_GENEROS, allow_null=True),
            name="ck_usuarios_genero_values",
        ),
        CheckConstraint(
            _build_enum_check_sql("provincia", VALID_PROVINCIAS, allow_null=True),
            name="ck_usuarios_provincia_values",
        ),
        # Rangos físicos razonables
        CheckConstraint(
            "altura IS NULL OR (altura BETWEEN 50 AND 300)",
            name="ck_usuarios_altura_range",
        ),
        CheckConstraint(
            "peso IS NULL OR (peso BETWEEN 20 AND 300)", name="ck_usuarios_peso_range"
        ),
        # Imagen y acumulados
        CheckConstraint(
            "foto_perfil IS NULL OR char_length(btrim(foto_perfil)) BETWEEN 1 AND 500",
            name="ck_usuarios_foto_perfil_len",
        ),
        CheckConstraint(
            "total_metros >= 0", name="ck_usuarios_total_metros_non_negative"
        ),
        CheckConstraint(
            "total_calorias >= 0", name="ck_usuarios_total_calorias_non_negative"
        ),
        # Objetivos: rangos razonables de negocio (10 m mínimo, 2 000 km máximo)
        CheckConstraint(
            "objetivo_semanal_metros BETWEEN 10 AND 2000000",
            name="ck_usuarios_objetivo_semanal_range",
        ),
        CheckConstraint(
            "objetivo_mensual_metros BETWEEN 10 AND 2000000",
            name="ck_usuarios_objetivo_mensual_range",
        ),
        # Términos: si el usuario existe en tabla, deben estar aceptados
        CheckConstraint(
            "acepta_terminos IS TRUE", name="ck_usuarios_acepta_terminos_true"
        ),
        CheckConstraint(
            "char_length(btrim(version_terminos)) BETWEEN 1 AND 10",
            name="ck_usuarios_version_terminos_len",
        ),
        # Código de recuperación: hash hex de 64 chars
        CheckConstraint(
            "codigo_recuperacion IS NULL OR codigo_recuperacion ~* '^[0-9a-f]{64}$'",
            name="ck_usuarios_codigo_recuperacion_hex64",
        ),
        # Coherencia: o están ambos NULL o están ambos rellenos
        CheckConstraint(
            "(codigo_recuperacion IS NULL) = (codigo_expiracion IS NULL)",
            name="ck_usuarios_codigo_recuperacion_pair",
        ),
    )

    @property
    def total_puntos(self) -> int:
        """
        Propiedad derivada de conveniencia.

        Regla actual del proyecto:
        1000 metros = 1 punto.
        """
        metros = int(self.total_metros or 0)
        return 0 if metros < 0 else metros // 1000

    # -----------------------------------------------------
    # Validaciones ORM: se ejecutan al asignar atributos
    # -----------------------------------------------------

    @validates("nombre_usuario")
    def validar_nombre_usuario(self, key: str, valor: str) -> str:
        if not isinstance(valor, str):
            raise AppValidationError(
                "Error: El nombre de usuario debe ser un texto", "USERNAME_MUST_BE_TEXT"
            )

        valor = valor.strip()

        if len(valor) < 5:
            raise AppValidationError(
                "Error: El nombre de usuario debe tener al menos 5 caracteres",
                "USERNAME_TOO_SHORT",
            )
        if len(valor) > 50:
            raise AppValidationError(
                "Error: El nombre de usuario no puede superar los 50 caracteres",
                "USERNAME_TOO_LONG",
            )
        if not _USERNAME_RE.fullmatch(valor):
            raise AppValidationError(
                "Error: El nombre de usuario solo puede contener letras y números",
                "USERNAME_INVALID_FORMAT",
            )

        return valor

    @validates("email")
    def validar_email(self, key: str, valor: str) -> str:
        if not isinstance(valor, str):
            raise AppValidationError(
                "Error: El email debe ser un texto", "EMAIL_MUST_BE_TEXT"
            )

        valor = valor.strip().lower()
        if not valor:
            raise AppValidationError("Error: El email es obligatorio", "EMAIL_REQUIRED")

        try:
            email_info = validate_email(valor, check_deliverability=False)
            return email_info.normalized.lower()
        except EmailNotValidError:
            raise AppValidationError(
                "Error: El formato del correo electrónico no es válido",
                "EMAIL_FORMAT_INVALID",
            )

    @validates("password_encriptada")
    def validar_password_encriptada(self, key: str, valor: str) -> str:
        return _validar_texto_no_vacio(
            valor,
            "La contraseña encriptada",
            255,
            must_be_string_code="ENCRYPTED_PASSWORD_MUST_BE_STRING",
            empty_code="ENCRYPTED_PASSWORD_EMPTY",
            too_long_code="ENCRYPTED_PASSWORD_TOO_LONG",
        )

    @validates("nombre_real")
    def validar_nombre_real(self, key: str, valor: Optional[str]) -> Optional[str]:
        if valor is None:
            return None
        if not isinstance(valor, str):
            raise AppValidationError(
                "Error: El nombre real debe ser un texto", "REAL_NAME_MUST_BE_TEXT"
            )

        valor = valor.strip()
        return validators.validar_nombre_real_logica(valor)

    @validates("fecha_nacimiento")
    def validar_fecha_nacimiento(self, key: str, valor: date) -> date:
        if not isinstance(valor, date):
            raise AppValidationError(
                "Error: La fecha de nacimiento debe ser una fecha válida",
                "BIRTH_DATE_INVALID",
            )
        return validators.validar_fecha_nacimiento_logica(valor)

    @validates("genero")
    def validar_genero(self, key: str, valor: Optional[Any]) -> Optional[str]:
        return _validar_enum_str(
            valor,
            VALID_GENEROS,
            "El género",
            must_be_text_code="GENDER_MUST_BE_TEXT",
            invalid_code="GENDER_INVALID",
        )

    @validates("altura")
    def validar_altura(self, key: str, valor: Optional[int]) -> Optional[int]:
        if valor is None:
            return None
        if not isinstance(valor, int):
            raise AppValidationError(
                "Error: La altura debe ser un número entero en centímetros",
                "HEIGHT_MUST_BE_INTEGER_CENTIMETERS",
            )
        return validators.validar_altura_logica(valor)

    @validates("peso")
    def validar_peso(self, key: str, valor: Optional[float]) -> Optional[float]:
        if valor is None:
            return None
        if not isinstance(valor, (int, float)):
            raise AppValidationError(
                "Error: El peso debe ser un número en kilos",
                "WEIGHT_MUST_BE_KILOGRAM_NUMBER",
            )
        return validators.validar_peso_logica(float(valor))

    @validates("provincia")
    def validar_provincia(self, key: str, valor: Optional[Any]) -> Optional[str]:
        return _validar_enum_str(
            valor,
            VALID_PROVINCIAS,
            "La provincia",
            must_be_text_code="PROVINCE_MUST_BE_TEXT",
            invalid_code="PROVINCE_INVALID",
        )

    @validates("foto_perfil")
    def validar_foto_perfil(self, key: str, valor: Optional[str]) -> Optional[str]:
        if valor is None:
            return None
        return _validar_texto_no_vacio(
            valor,
            "La foto de perfil",
            500,
            must_be_string_code="PROFILE_PHOTO_MUST_BE_STRING",
            empty_code="PROFILE_PHOTO_EMPTY",
            too_long_code="PROFILE_PHOTO_TOO_LONG",
        )

    @validates("foto_fecha_actualizacion", "fecha_registro", "codigo_expiracion")
    def validar_fechas_auxiliares(
        self, key: str, valor: Optional[datetime]
    ) -> Optional[datetime]:
        return _normalizar_datetime_utc(valor)

    @validates("fecha_eula")
    def validar_fecha_eula(self, key: str, valor: datetime) -> datetime:
        if not isinstance(valor, datetime):
            raise AppValidationError(
                "Error: La fecha de aceptación debe ser una fecha-hora válida",
                "TERMS_ACCEPTED_AT_INVALID",
            )

        valor_utc = _normalizar_datetime_utc(valor)
        assert valor_utc is not None

        # Misma lógica de schemas.py: margen pequeño para evitar falsos positivos por reloj.
        ahora = _ahora_utc()
        if valor_utc > ahora + timedelta(minutes=5):
            raise AppValidationError(
                "Error: La fecha de aceptación no puede ser futura",
                "TERMS_ACCEPTED_AT_IN_FUTURE",
            )

        return valor_utc

    @validates("total_metros")
    def validar_total_metros(self, key: str, valor: int) -> int:
        if not isinstance(valor, int):
            raise AppValidationError(
                "Error: El total de metros debe ser un número entero",
                "TOTAL_DISTANCE_MUST_BE_INTEGER",
            )
        if valor < 0:
            raise AppValidationError(
                "Error: El total de metros no puede ser negativo",
                "TOTAL_DISTANCE_NEGATIVE",
            )
        return valor

    @validates("total_calorias")
    def validar_total_calorias(self, key: str, valor: int) -> int:
        if not isinstance(valor, int):
            raise AppValidationError(
                "Error: El total de calorías debe ser un número entero",
                "TOTAL_CALORIES_MUST_BE_INTEGER",
            )
        if valor < 0:
            raise AppValidationError(
                "Error: El total de calorías no puede ser negativo",
                "TOTAL_CALORIES_NEGATIVE",
            )
        return valor

    @validates("objetivo_semanal_metros")
    def validar_objetivo_semanal(self, key: str, valor: int) -> int:
        if not isinstance(valor, int):
            raise AppValidationError(
                "Error: El objetivo semanal debe ser un número entero",
                "WEEKLY_GOAL_MUST_BE_INTEGER",
            )
        if not (10 <= valor <= 2_000_000):
            raise AppValidationError(
                "Error: El objetivo semanal debe estar entre 10 y 2 000 000 metros",
                "WEEKLY_GOAL_OUT_OF_RANGE",
            )
        return valor

    @validates("objetivo_mensual_metros")
    def validar_objetivo_mensual(self, key: str, valor: int) -> int:
        if not isinstance(valor, int):
            raise AppValidationError(
                "Error: El objetivo mensual debe ser un número entero",
                "MONTHLY_GOAL_MUST_BE_INTEGER",
            )
        if not (10 <= valor <= 2_000_000):
            raise AppValidationError(
                "Error: El objetivo mensual debe estar entre 10 y 2 000 000 metros",
                "MONTHLY_GOAL_OUT_OF_RANGE",
            )
        return valor

    @validates("acepta_terminos")
    def validar_acepta_terminos(self, key: str, valor: bool) -> bool:
        if not isinstance(valor, bool):
            raise AppValidationError(
                "Error: acepta_terminos debe ser booleano",
                "TERMS_ACCEPTANCE_MUST_BE_BOOLEAN",
            )
        if valor is not True:
            raise AppValidationError(
                "Error: Debes aceptar los términos para crear un usuario",
                "ACCOUNT_TERMS_ACCEPTANCE_REQUIRED",
            )
        return valor

    @validates("perfil_visible")
    def validar_perfil_visible(self, key: str, valor: bool) -> bool:
        if not isinstance(valor, bool):
            raise AppValidationError(
                "Error: perfil_visible debe ser booleano",
                "PROFILE_VISIBILITY_MUST_BE_BOOLEAN",
            )
        return valor

    @validates("version_terminos")
    def validar_version_terminos(self, key: str, valor: str) -> str:
        if not isinstance(valor, str):
            raise AppValidationError(
                "Error: La versión de términos debe ser un texto",
                "TERMS_VERSION_MUST_BE_TEXT",
            )

        valor = valor.strip()
        if not valor:
            raise AppValidationError(
                "Error: La versión de los términos es obligatoria",
                "TERMS_VERSION_REQUIRED",
            )
        if len(valor) > 10:
            raise AppValidationError(
                "Error: La versión de los términos no puede superar los 10 caracteres",
                "TERMS_VERSION_TOO_LONG",
            )

        return valor

    @validates("codigo_recuperacion")
    def validar_codigo_recuperacion(
        self, key: str, valor: Optional[str]
    ) -> Optional[str]:
        return _validar_hex64_opcional(
            valor,
            "codigo_recuperacion",
            must_be_string_code="RECOVERY_CODE_HASH_MUST_BE_STRING",
            invalid_code="RECOVERY_CODE_HASH_INVALID",
        )


# =========================================================
# Modelo Actividad
# =========================================================



class Actividad(Base):
    """
    Tabla de actividades deportivas enriquecida con métricas de tracking.

    Se mantienen valores enteros para facilitar validación, sincronización y
    compatibilidad con el cliente móvil offline.
    """

    __tablename__ = "actividades"

    id: Mapped[int] = mapped_column(primary_key=True)

    usuario_id: Mapped[int] = mapped_column(
        ForeignKey("usuarios.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    tipo: Mapped[str] = mapped_column(String(20), nullable=False)
    distancia: Mapped[int] = mapped_column(Integer, nullable=False)
    duracion_total: Mapped[int] = mapped_column(Integer, nullable=False)
    duracion_movimiento: Mapped[int] = mapped_column(Integer, nullable=False)
    duracion_parado: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default=text("0"))
    duracion_pausa_manual: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default=text("0"))
    calorias_quemadas: Mapped[int] = mapped_column(Integer, nullable=False)
    ritmo_medio_movimiento: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default=text("0"))
    ritmo_medio_total: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default=text("0"))
    velocidad_media_x100: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default=text("0"))
    velocidad_max_x100: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default=text("0"))
    auto_pausas: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default=text("0"))
    pausas_manuales: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default=text("0"))
    alertas_velocidad: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default=text("0"))

    ruta_polilinea: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    ruta_mapa_url: Mapped[Optional[str]] = mapped_column(String(2048), nullable=True)
    fecha_ruta: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=_ahora_utc,
        server_default=text("CURRENT_TIMESTAMP"),
        index=True,
    )

    __table_args__ = (
        CheckConstraint(
            _build_enum_check_sql("tipo", VALID_TIPOS_ACTIVIDAD, allow_null=False),
            name="ck_actividades_tipo_values",
        ),
        CheckConstraint("distancia > 0 AND distancia <= 300000", name="ck_actividades_distancia_range"),
        CheckConstraint("duracion_total > 0 AND duracion_total <= 86400", name="ck_actividades_duracion_total_range"),
        CheckConstraint("duracion_movimiento > 0 AND duracion_movimiento <= 86400", name="ck_actividades_duracion_movimiento_range"),
        CheckConstraint("duracion_parado >= 0 AND duracion_parado <= 86400", name="ck_actividades_duracion_parado_range"),
        CheckConstraint("duracion_pausa_manual >= 0 AND duracion_pausa_manual <= 86400", name="ck_actividades_duracion_pausa_manual_range"),
        CheckConstraint("duracion_movimiento + duracion_parado = duracion_total", name="ck_actividades_duracion_breakdown_match"),
        CheckConstraint("duracion_pausa_manual <= duracion_total", name="ck_actividades_duracion_pausa_manual_total"),
        CheckConstraint("calorias_quemadas > 0 AND calorias_quemadas <= 10000", name="ck_actividades_calorias_range"),
        CheckConstraint("ritmo_medio_movimiento >= 0 AND ritmo_medio_movimiento <= 3600", name="ck_actividades_ritmo_medio_movimiento_range"),
        CheckConstraint("ritmo_medio_total >= 0 AND ritmo_medio_total <= 3600", name="ck_actividades_ritmo_medio_total_range"),
        CheckConstraint("velocidad_media_x100 >= 0 AND velocidad_media_x100 <= 10000", name="ck_actividades_velocidad_media_range"),
        CheckConstraint("velocidad_max_x100 >= 0 AND velocidad_max_x100 <= 10000", name="ck_actividades_velocidad_max_range"),
        CheckConstraint("velocidad_max_x100 >= velocidad_media_x100", name="ck_actividades_velocidad_max_ge_media"),
        CheckConstraint("auto_pausas >= 0 AND auto_pausas <= 500", name="ck_actividades_auto_pausas_range"),
        CheckConstraint("pausas_manuales >= 0 AND pausas_manuales <= 500", name="ck_actividades_pausas_manuales_range"),
        CheckConstraint("alertas_velocidad >= 0 AND alertas_velocidad <= 500", name="ck_actividades_alertas_velocidad_range"),
        CheckConstraint("ruta_polilinea IS NULL OR char_length(ruta_polilinea) >= 5", name="ck_actividades_ruta_polilinea_len"),
        CheckConstraint("ruta_mapa_url IS NULL OR char_length(ruta_mapa_url) <= 2048", name="ck_actividades_ruta_mapa_url_len"),
        CheckConstraint(r"ruta_mapa_url IS NULL OR ruta_mapa_url ~* '^https?://'", name="ck_actividades_ruta_mapa_url_http"),
        Index("ix_actividades_usuario_fecha", "usuario_id", "fecha_ruta", "id"),
    )

    @validates("usuario_id")
    def validar_usuario_id(self, key: str, valor: int) -> int:
        if not isinstance(valor, int):
            raise AppValidationError(
                "Error: usuario_id debe ser un entero", "USER_ID_MUST_BE_INTEGER"
            )
        if valor <= 0:
            raise AppValidationError(
                "Error: usuario_id debe ser mayor a 0", "USER_ID_MUST_BE_POSITIVE"
            )
        return valor

    @validates("tipo")
    def validar_tipo(self, key: str, valor: Optional[Any]) -> str:
        """Valida y normaliza el tipo de actividad persistido como texto."""
        tipo_normalizado = _validar_enum_str(
            valor,
            VALID_TIPOS_ACTIVIDAD,
            "tipo",
            must_be_text_code="ACTIVITY_TYPE_MUST_BE_STRING",
            invalid_code="ACTIVITY_TYPE_INVALID",
        )
        if tipo_normalizado is None:
            raise AppValidationError(
                "Error: tipo es obligatorio",
                "ACTIVITY_TYPE_REQUIRED",
            )
        return tipo_normalizado

    @validates("distancia")
    def validar_distancia(self, key: str, valor: int) -> int:
        return validators.validar_distancia_logica(valor)

    @validates("duracion_total")
    def validar_duracion_total(self, key: str, valor: int) -> int:
        return validators.validar_duracion_logica(valor)

    @validates("duracion_movimiento")
    def validar_duracion_movimiento(self, key: str, valor: int) -> int:
        return validators.validar_duracion_logica(valor)

    @validates("duracion_parado")
    def validar_duracion_parado(self, key: str, valor: int) -> int:
        return validators.validar_duracion_no_negativa_logica(valor, "la duración parada", "STOPPED_DURATION")

    @validates("duracion_pausa_manual")
    def validar_duracion_pausa_manual(self, key: str, valor: int) -> int:
        return validators.validar_duracion_no_negativa_logica(valor, "la duración de pausa manual", "MANUAL_PAUSE_DURATION")

    @validates("calorias_quemadas")
    def validar_calorias(self, key: str, valor: int) -> int:
        return validators.validar_calorias_logica(valor)

    @validates("ritmo_medio_movimiento")
    def validar_ritmo_medio_movimiento(self, key: str, valor: int) -> int:
        return validators.validar_ritmo_segundos_km_logica(valor, "el ritmo medio en movimiento", "MOVING_PACE")

    @validates("ritmo_medio_total")
    def validar_ritmo_medio_total(self, key: str, valor: int) -> int:
        return validators.validar_ritmo_segundos_km_logica(valor, "el ritmo medio total", "TOTAL_PACE")

    @validates("velocidad_media_x100")
    def validar_velocidad_media(self, key: str, valor: int) -> int:
        return validators.validar_velocidad_x100_logica(valor, "la velocidad media", "AVERAGE_SPEED")

    @validates("velocidad_max_x100")
    def validar_velocidad_max(self, key: str, valor: int) -> int:
        return validators.validar_velocidad_x100_logica(valor, "la velocidad máxima", "MAX_SPEED")

    @validates("auto_pausas")
    def validar_auto_pausas(self, key: str, valor: int) -> int:
        return validators.validar_contador_tracking_logica(valor, "las auto pausas", "AUTO_PAUSE_COUNT")

    @validates("pausas_manuales")
    def validar_pausas_manuales(self, key: str, valor: int) -> int:
        return validators.validar_contador_tracking_logica(valor, "las pausas manuales", "MANUAL_PAUSE_COUNT")

    @validates("alertas_velocidad")
    def validar_alertas_velocidad(self, key: str, valor: int) -> int:
        return validators.validar_contador_tracking_logica(valor, "las alertas de velocidad", "SPEED_ALERT_COUNT")

    @validates("ruta_polilinea")
    def validar_ruta_polilinea(self, key: str, valor: Optional[str]) -> Optional[str]:
        """Valida la polilínea solo cuando existe, manteniendo el campo opcional."""
        if valor is None:
            return None
        return validators.validar_polilinea_logica(valor)

    @validates("ruta_mapa_url")
    def validar_ruta_mapa_url(self, key: str, valor: Optional[str]) -> Optional[str]:
        if valor is None:
            return None
        if len(valor) > 2048:
            raise AppValidationError(
                "Error: La URL del mapa es demasiado larga", "MAP_URL_TOO_LONG"
            )
        if not valor.lower().startswith(("http://", "https://")):
            raise AppValidationError(
                "Error: La URL del mapa debe empezar por http:// o https://",
                "MAP_URL_INVALID_SCHEME",
            )
        return valor

    @validates("fecha_ruta")
    def validar_fecha_ruta(self, key: str, valor: datetime) -> datetime:
        return validators.validar_fecha_ruta_logica(valor)


class SesionRefresh(Base):
    """
    Tabla para refresh tokens rotativos.

    Se guarda el hash del refresh token, nunca el token en claro.
    """

    __tablename__ = "sesiones_refresh"

    id: Mapped[int] = mapped_column(primary_key=True)

    usuario_id: Mapped[int] = mapped_column(
        ForeignKey("usuarios.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # jti y familia_id se dejan como string genérico por compatibilidad.
    # Hoy se generan con uuid.uuid4().hex, pero el modelo no fuerza ese formato exacto.
    jti: Mapped[str] = mapped_column(
        String(64), nullable=False, unique=True, index=True
    )
    familia_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)

    # hash HMAC-SHA256 del refresh token
    token_hash: Mapped[str] = mapped_column(String(64), nullable=False)

    creada_en: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=_ahora_utc,
        server_default=text("CURRENT_TIMESTAMP"),
    )
    ultimo_uso_en: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    expira_en: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        index=True,
    )
    revocada_en: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        index=True,
    )
    reemplazada_por_jti: Mapped[Optional[str]] = mapped_column(
        String(64),
        nullable=True,
    )

    __table_args__ = (
        CheckConstraint(
            "char_length(btrim(jti)) BETWEEN 1 AND 64",
            name="ck_sesiones_refresh_jti_non_empty",
        ),
        CheckConstraint(
            "char_length(btrim(familia_id)) BETWEEN 1 AND 64",
            name="ck_sesiones_refresh_familia_non_empty",
        ),
        CheckConstraint(
            "token_hash ~* '^[0-9a-f]{64}$'",
            name="ck_sesiones_refresh_token_hash_hex64",
        ),
        CheckConstraint(
            "reemplazada_por_jti IS NULL OR char_length(btrim(reemplazada_por_jti)) BETWEEN 1 AND 64",
            name="ck_sesiones_refresh_reemplazada_por_jti_len",
        ),
        CheckConstraint(
            "expira_en >= creada_en", name="ck_sesiones_refresh_expira_ge_creada"
        ),
        CheckConstraint(
            "ultimo_uso_en IS NULL OR ultimo_uso_en >= creada_en",
            name="ck_sesiones_refresh_ultimo_uso_ge_creada",
        ),
        CheckConstraint(
            "revocada_en IS NULL OR revocada_en >= creada_en",
            name="ck_sesiones_refresh_revocada_ge_creada",
        ),
    )

    @validates("usuario_id")
    def validar_usuario_id(self, key: str, valor: int) -> int:
        if not isinstance(valor, int):
            raise AppValidationError(
                "Error: usuario_id debe ser un entero", "USER_ID_MUST_BE_INTEGER"
            )
        if valor <= 0:
            raise AppValidationError(
                "Error: usuario_id debe ser mayor a 0", "USER_ID_MUST_BE_POSITIVE"
            )
        return valor

    @validates("jti", "familia_id", "reemplazada_por_jti")
    def validar_ids_sesion(self, key: str, valor: Optional[str]) -> Optional[str]:
        if valor is None:
            return None
        return _validar_texto_no_vacio(
            valor,
            key,
            64,
            must_be_string_code="SESSION_IDENTIFIER_MUST_BE_STRING",
            empty_code="SESSION_IDENTIFIER_EMPTY",
            too_long_code="SESSION_IDENTIFIER_TOO_LONG",
        )

    @validates("token_hash")
    def validar_token_hash(self, key: str, valor: str) -> str:
        resultado = _validar_hex64_opcional(
            valor,
            "token_hash",
            must_be_string_code="TOKEN_HASH_MUST_BE_STRING",
            invalid_code="TOKEN_HASH_INVALID",
        )
        if resultado is None:
            raise AppValidationError(
                "Error: token_hash es obligatorio", "TOKEN_HASH_REQUIRED"
            )
        return resultado

    @validates("creada_en", "ultimo_uso_en", "expira_en", "revocada_en")
    def validar_fechas(self, key: str, valor: Optional[datetime]) -> Optional[datetime]:
        valor = _normalizar_datetime_utc(valor)

        if key == "expira_en" and valor is None:
            raise AppValidationError(
                "Error: expira_en es obligatorio", "EXPIRES_AT_REQUIRED"
            )

        return valor


# =========================================================
# Inicialización y dependencias
# =========================================================


async def init_db() -> None:
    """
    Inicializa los objetos de BD y, si procede, crea tablas.

    Importante:
    - Si la BD no está disponible en startup, NO levantamos excepción.
    - La app arranca igualmente.
    - /readyz devolverá 503 mientras la BD siga caída.
    """
    _init_db_objects()

    if not settings.AUTO_CREATE_TABLES:
        return

    assert engine is not None  # para type checkers

    try:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

        logger.info(
            "db_init_ok",
            extra={"auto_create_tables": settings.AUTO_CREATE_TABLES},
        )
    except Exception as exc:
        logger.warning(
            "fallo_BD_inicio_continua",
            extra={
                "auto_create_tables": settings.AUTO_CREATE_TABLES,
                "error_type": type(exc).__name__,
                "error": str(exc),
            },
        )
        # No relanzamos: el servidor debe arrancar aunque PostgreSQL esté caído.


async def close_db() -> None:
    """Cierra el engine async de SQLAlchemy si existe."""
    global engine, AsyncSessionLocal

    if engine is None:
        return

    await engine.dispose()
    engine = None
    AsyncSessionLocal = None


async def obtener_db() -> AsyncGenerator[AsyncSession, None]:
    """
    Dependencia de FastAPI para inyectar una sesión async.
    Inicializa lazy engine/sessionmaker si aún no existen.
    """
    _init_db_objects()

    assert AsyncSessionLocal is not None  # para type checkers

    async with AsyncSessionLocal() as db:
        yield db


