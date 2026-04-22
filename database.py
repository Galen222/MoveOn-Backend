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
    """Construye la URL de conexión a PostgreSQL escapando usuario y password.

    Usa ``urllib.parse.quote_plus`` porque el password puede contener
    caracteres especiales (``@``, ``/``, ``:``, ``#``...) que romperían
    el parseo del DSN si se inyectan tal cual. Sin escapar,
    ``secret@pass`` haría que el parser entendiese ``@pass`` como host.

    Returns:
        URL ``postgresql+asyncpg://user:pass@host:port/dbname`` lista para ``create_async_engine``.
    """
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
# Constantes y ayudantes internos
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
VALID_SOCIAL_PROVIDERS = {"google"}


def _ahora_utc() -> datetime:
    """Devuelve el ``datetime`` actual con ``tzinfo=UTC``.

    Centralizado aquí para que todas las marcas de tiempo que genera
    este módulo (``fecha_eula``, validaciones de no-futuro, etc.) usen
    la misma referencia y sea fácil de monkey-patchear en tests.

    Returns:
        Fecha y hora actual en UTC.
    """
    return datetime.now(timezone.utc)


def _normalizar_datetime_utc(v: Optional[datetime]) -> Optional[datetime]:
    """Garantiza que un ``datetime`` está expresado en UTC.

    Dos casos:

    - Entrada naive: se asume UTC y se le adjunta ``tzinfo`` (los
      drivers antiguos y algunos flows legacy devuelven naive aunque
      la columna sea ``TIMESTAMPTZ``).
    - Entrada aware: se convierte a UTC con ``astimezone`` para que los
      comparadores posteriores nunca mezclen zonas.

    Unificar ambos caminos aquí evita que cada validador tenga que
    repetir el mismo chequeo de ``tzinfo``.

    Args:
        v: ``datetime`` a normalizar, o ``None``.

    Returns:
        ``datetime`` en UTC, o ``None`` si la entrada era ``None``.
    """
    if v is None:
        return None
    return (
        v.replace(tzinfo=timezone.utc)
        if v.tzinfo is None
        else v.astimezone(timezone.utc)
    )


def _sql_quote(value: str) -> str:
    """Escapa un string para incrustarlo de forma segura en un ``CheckConstraint`` SQL.

    SQLAlchemy permite pasar la cláusula como texto crudo; los valores
    que se inyectan provienen de enums propios del dominio (no input
    de usuario) pero aun así se escapa ``'`` a ``''`` para no romper
    el DDL si algún enum incluyera una comilla en el futuro.

    Args:
        value: cadena a incrustar literalmente en SQL.

    Returns:
        Cadena entrecomillada (``'valor'``) con comillas internas escapadas.
    """
    return "'" + value.replace("'", "''") + "'"


def _sql_in_values(values: set[str]) -> str:
    """Convierte un conjunto de valores en la lista literal de un ``IN (...)``.

    Ordena con ``sorted`` antes de juntar para que el DDL generado sea
    determinista entre ejecuciones: dos migraciones idénticas producen
    el mismo SQL y no aparecen falsos diffs.

    Args:
        values: conjunto de valores a enumerar (p. ej. ``.value`` de un enum).

    Returns:
        Cadena ``'A', 'B', 'C'`` con los valores ya escapados para SQL.
    """
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
    # Valida enum str.
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
    """Valida que un texto opcional sea un hash SHA-256 hexadecimal (64 caracteres).

    Se usa para columnas que guardan HMAC-SHA256 de tokens o códigos
    (por ejemplo ``codigo_recuperacion`` o el hash de refresh tokens).
    Normaliza a minúsculas para que el formato en base de datos sea
    homogéneo y evita que comparaciones case-sensitive fallen por un
    flip de caso en origen.

    Args:
        valor: cadena candidata, o ``None`` para permitir ausencia del hash.
        nombre_campo: nombre humano del campo, usado en los mensajes de error.
        must_be_string_code: ``error_code`` a usar si el valor no es cadena.
        invalid_code: ``error_code`` a usar si no coincide con el patrón hex64.

    Returns:
        Hash en minúsculas ya validado, o ``None`` si la entrada era ``None``.

    Raises:
        AppValidationError: ``must_be_string_code`` si el valor no es una cadena.
        AppValidationError: ``invalid_code`` si la cadena no coincide con ``^[0-9a-fA-F]{64}$``.
    """
    # Valida hex64 opcional.
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
    """Valida que un texto obligatorio no esté vacío y no supere ``max_len``.

    Helper genérico usado por varios ``@validates`` para no duplicar la
    terna de comprobaciones (tipo, no vacío, longitud) en cada columna.
    Recorta espacios antes de comprobar longitud para que ``"   "`` cuente
    como vacío y ``"  hola  "`` use 4 caracteres, no 8.

    Args:
        valor: cadena candidata.
        nombre_campo: nombre humano del campo, usado en los mensajes de error.
        max_len: longitud máxima permitida (incluida).
        must_be_string_code: ``error_code`` si el valor no es cadena.
        empty_code: ``error_code`` si queda vacío tras recortar.
        too_long_code: ``error_code`` si supera ``max_len``.

    Returns:
        Cadena recortada si pasa todas las comprobaciones.

    Raises:
        AppValidationError: con uno de los tres códigos según el fallo detectado.
    """
    # Valida texto no vacio.
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
    # Valida URL HTTP opcional.
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
    total_duracion_segundos: Mapped[int] = mapped_column(
        BigInteger,
        nullable=False,
        default=0,
        server_default=text("0"),
    )

    total_actividades: Mapped[int] = mapped_column(
        Integer,
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
    password_changed_at: Mapped[Optional[datetime]] = mapped_column(
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
        CheckConstraint(
            "total_duracion_segundos >= 0",
            name="ck_usuarios_total_duracion_non_negative",
        ),
        CheckConstraint(
            "total_actividades >= 0",
            name="ck_usuarios_total_actividades_non_negative",
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
        """Valida a nivel ORM el ``nombre_usuario`` al asignarse al atributo.

        Duplica las reglas que aplica ``schemas.Registro.validar_nombre_usuario``
        (longitud 5–50, alfanumérico) como segunda capa de defensa: si el
        alta se hiciera saltándose el esquema Pydantic (por ejemplo desde
        un script interno o un test), SQLAlchemy sigue rechazando valores
        inválidos antes de escribir en la base.

        Args:
            key: nombre del atributo, lo pasa SQLAlchemy al decorador ``@validates``.
            valor: valor que se está asignando.

        Returns:
            Nombre recortado si pasa las comprobaciones.

        Raises:
            AppValidationError: ``USERNAME_MUST_BE_TEXT`` si no es cadena.
            AppValidationError: ``USERNAME_TOO_SHORT`` si tiene menos de 5.
            AppValidationError: ``USERNAME_TOO_LONG`` si supera 50.
            AppValidationError: ``USERNAME_INVALID_FORMAT`` si no es alfanumérico.
        """
        # Valida nombre usuario.
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
        """Valida y normaliza el email al asignarse al atributo.

        A diferencia del validator de Pydantic (que usa ``EmailStr``), aquí
        se usa ``email_validator.validate_email`` con
        ``check_deliverability=False``: no queremos hacer DNS en cada
        asignación del ORM (los tests y los scripts lo convertirían en
        lento e inestable), pero sí validar la sintaxis RFC.

        Se normaliza a minúsculas antes y después de ``validate_email`` para
        que la columna siempre guarde la misma forma canónica (evita
        duplicados cuando un usuario se registra con ``Juan@X.com`` y otro
        intenta hacerlo con ``juan@x.com``).

        Args:
            key: nombre del atributo.
            valor: email tal como llega.

        Returns:
            Email normalizado a minúsculas.

        Raises:
            AppValidationError: ``EMAIL_MUST_BE_TEXT`` si no es cadena.
            AppValidationError: ``EMAIL_REQUIRED`` si queda vacío tras recortar.
            AppValidationError: ``EMAIL_FORMAT_INVALID`` si la sintaxis no es válida.
        """
        # Valida correo electrónico.
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
        """Valida que el hash bcrypt almacenado no esté vacío y quepa en la columna.

        Bcrypt produce siempre cadenas de unos 60 caracteres, pero se da
        margen hasta 255 (tamaño de la columna) para absorber futuros
        cambios de algoritmo sin tener que alterar el esquema.

        Args:
            key: nombre del atributo.
            valor: hash en claro tal como lo genera ``auth.hash_password``.

        Returns:
            Hash recortado si pasa las comprobaciones.

        Raises:
            AppValidationError: ``ENCRYPTED_PASSWORD_MUST_BE_STRING``, ``ENCRYPTED_PASSWORD_EMPTY`` o ``ENCRYPTED_PASSWORD_TOO_LONG`` según el fallo.
        """
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
        """Valida el nombre real opcional del usuario.

        Respeta ``None`` porque el campo no es obligatorio en el modelo.
        Si hay valor, lo recorta y delega en
        ``validators.validar_nombre_real_logica``, que impone las mismas
        reglas que el esquema Pydantic (longitud, caracteres latinos).

        Args:
            key: nombre del atributo.
            valor: nombre real o ``None``.

        Returns:
            Nombre recortado, o ``None`` si no se proporcionó.

        Raises:
            AppValidationError: ``REAL_NAME_MUST_BE_TEXT`` si no es cadena.
            AppValidationError: las demás que levante ``validar_nombre_real_logica``.
        """
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
        """Valida la fecha de nacimiento a nivel ORM.

        Exige tipo ``date`` (no cadena: Pydantic ya parseó arriba) y aplica
        la edad mínima y la no-futuro vía
        ``validators.validar_fecha_nacimiento_logica``.

        Args:
            key: nombre del atributo.
            valor: fecha de nacimiento ya parseada.

        Returns:
            La misma fecha si pasa las comprobaciones.

        Raises:
            AppValidationError: ``BIRTH_DATE_INVALID`` si no es ``date``.
            AppValidationError: ``BIRTH_DATE_IN_FUTURE`` o ``AGE_RESTRICTION_NOT_MET`` según la regla violada.
        """
        if not isinstance(valor, date):
            raise AppValidationError(
                "Error: La fecha de nacimiento debe ser una fecha válida",
                "BIRTH_DATE_INVALID",
            )
        return validators.validar_fecha_nacimiento_logica(valor)

    @validates("genero")
    def validar_genero(self, key: str, valor: Optional[Any]) -> Optional[str]:
        """Valida el género contra el enum ``GeneroUsuario``.

        Delega en ``_validar_enum_str`` con el conjunto de ``VALID_GENEROS``
        (los ``.value`` del enum). Acepta el enum directamente o su valor
        como cadena para que llamadores distintos (API vs scripts) puedan
        pasar cualquiera de las dos formas.

        Args:
            key: nombre del atributo.
            valor: valor candidato (enum, cadena o ``None``).

        Returns:
            Cadena canónica del enum, o ``None`` si se pasó ``None``.

        Raises:
            AppValidationError: ``GENDER_MUST_BE_TEXT`` si no es cadena.
            AppValidationError: ``GENDER_INVALID`` si no pertenece al enum.
        """
        return _validar_enum_str(
            valor,
            VALID_GENEROS,
            "El género",
            must_be_text_code="GENDER_MUST_BE_TEXT",
            invalid_code="GENDER_INVALID",
        )

    @validates("altura")
    def validar_altura(self, key: str, valor: Optional[int]) -> Optional[int]:
        """Valida la altura en centímetros a nivel ORM.

        Admite ``None`` (campo opcional) y exige tipo ``int`` estricto
        (no ``float``) porque el cliente Android siempre envía enteros y
        un ``float`` aquí indicaría un bug de capa superior. Delega la
        comprobación de rango en ``validators.validar_altura_logica``.

        Args:
            key: nombre del atributo.
            valor: altura en centímetros o ``None``.

        Returns:
            El mismo valor si pasa.

        Raises:
            AppValidationError: ``HEIGHT_MUST_BE_INTEGER_CENTIMETERS`` si no es entero.
            AppValidationError: ``HEIGHT_OUT_OF_RANGE`` si no está en [50, 300].
        """
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
        """Valida el peso en kilogramos a nivel ORM.

        Admite ``None`` y acepta ``int`` o ``float`` (el usuario puede
        introducir 70 o 70.5). Lo convierte siempre a ``float`` antes de
        delegar en ``validators.validar_peso_logica`` para que la columna
        ``Float`` de SQLAlchemy reciba siempre el mismo tipo.

        Args:
            key: nombre del atributo.
            valor: peso en kg o ``None``.

        Returns:
            Peso como ``float``, o ``None`` si no se proporcionó.

        Raises:
            AppValidationError: ``WEIGHT_MUST_BE_KILOGRAM_NUMBER`` si no es numérico.
            AppValidationError: ``WEIGHT_OUT_OF_RANGE`` si no está en [20, 300].
        """
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
        """Valida la provincia contra el enum ``ProvinciaEspaña``.

        Delega en ``_validar_enum_str`` con ``VALID_PROVINCIAS``. Como el
        campo es opcional, ``None`` se pasa tal cual.

        Args:
            key: nombre del atributo.
            valor: valor candidato (enum, cadena o ``None``).

        Returns:
            Cadena canónica del enum, o ``None``.

        Raises:
            AppValidationError: ``PROVINCE_MUST_BE_TEXT`` si no es cadena.
            AppValidationError: ``PROVINCE_INVALID`` si no pertenece al enum.
        """
        return _validar_enum_str(
            valor,
            VALID_PROVINCIAS,
            "La provincia",
            must_be_text_code="PROVINCE_MUST_BE_TEXT",
            invalid_code="PROVINCE_INVALID",
        )

    @validates("foto_perfil")
    def validar_foto_perfil(self, key: str, valor: Optional[str]) -> Optional[str]:
        """Valida la URL o nombre de fichero de la foto de perfil.

        Admite ``None`` (usuario sin foto). Cuando hay valor, delega en
        ``_validar_texto_no_vacio`` con tope de 500 caracteres, suficiente
        para URLs de Cloudinary con ``public_id`` largo pero que descarta
        valores claramente rotos o intentos de DoS por payload grande.

        Args:
            key: nombre del atributo.
            valor: URL/nombre o ``None``.

        Returns:
            Valor recortado, o ``None`` si no había foto.

        Raises:
            AppValidationError: ``PROFILE_PHOTO_MUST_BE_STRING``, ``PROFILE_PHOTO_EMPTY`` o ``PROFILE_PHOTO_TOO_LONG``.
        """
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

    @validates(
        "foto_fecha_actualizacion",
        "fecha_registro",
        "codigo_expiracion",
        "password_changed_at",
    )
    def validar_fechas_auxiliares(
        self, key: str, valor: Optional[datetime]
    ) -> Optional[datetime]:
        """Normaliza a UTC las columnas de timestamp auxiliares del usuario.

        Un único validator cubre ``foto_fecha_actualizacion``,
        ``fecha_registro``, ``codigo_expiracion`` y ``password_changed_at``
        porque todos comparten la misma necesidad: que se guarden siempre
        con ``tzinfo`` y en UTC para evitar comparaciones ambiguas.

        Args:
            key: nombre del atributo, lo usa SQLAlchemy pero aquí no se diferencia.
            valor: ``datetime`` o ``None``.

        Returns:
            ``datetime`` en UTC, o ``None`` si la entrada era ``None``.
        """
        return _normalizar_datetime_utc(valor)

    @validates("fecha_eula")
    def validar_fecha_eula(self, key: str, valor: datetime) -> datetime:
        """Valida y normaliza la marca de aceptación de términos a UTC.

        Obligatoria a nivel ORM: el alta no puede ocurrir sin evidencia
        de aceptación. Normaliza a UTC y rechaza valores más de 5 minutos
        en el futuro (mismo margen que el validator del esquema Pydantic
        para absorber desajustes de reloj del cliente).

        Args:
            key: nombre del atributo.
            valor: ``datetime`` propuesto.

        Returns:
            El mismo instante en UTC.

        Raises:
            AppValidationError: ``TERMS_ACCEPTED_AT_INVALID`` si no es ``datetime``.
            AppValidationError: ``TERMS_ACCEPTED_AT_IN_FUTURE`` si supera ``ahora + 5 minutos``.
        """
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
        """Valida el acumulado de metros del usuario.

        El total se actualiza incrementalmente al guardar/borrar
        actividades. Forzar ``int >= 0`` aquí atrapa bugs del servicio
        (p. ej. un decremento mal calculado que dejaría el contador en
        negativo) antes de que lleguen a la base.

        Args:
            key: nombre del atributo.
            valor: total acumulado en metros.

        Returns:
            El mismo valor si pasa.

        Raises:
            AppValidationError: ``TOTAL_DISTANCE_MUST_BE_INTEGER`` si no es entero.
            AppValidationError: ``TOTAL_DISTANCE_NEGATIVE`` si es negativo.
        """
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
        """Valida el acumulado de calorías del usuario.

        Mismos invariantes que ``total_metros`` (entero no negativo). El
        código se replica en vez de extraer a helper compartido para que
        cada columna mantenga su ``error_code`` específico y pueda
        evolucionar por separado.

        Args:
            key: nombre del atributo.
            valor: total de calorías acumuladas.

        Returns:
            El mismo valor si pasa.

        Raises:
            AppValidationError: ``TOTAL_CALORIES_MUST_BE_INTEGER`` o ``TOTAL_CALORIES_NEGATIVE``.
        """
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

    @validates("total_duracion_segundos")
    def validar_total_duracion(self, key: str, valor: int) -> int:
        """Valida el acumulado de segundos del usuario.

        Entero no negativo. Ver ``validar_total_metros`` para el razonamiento
        sobre por qué se valida aquí además de en la capa de servicio.

        Args:
            key: nombre del atributo.
            valor: total de segundos de actividad.

        Returns:
            El mismo valor si pasa.

        Raises:
            AppValidationError: ``TOTAL_DURATION_MUST_BE_INTEGER`` o ``TOTAL_DURATION_NEGATIVE``.
        """
        if not isinstance(valor, int):
            raise AppValidationError(
                "Error: El total de duración debe ser un número entero",
                "TOTAL_DURATION_MUST_BE_INTEGER",
            )
        if valor < 0:
            raise AppValidationError(
                "Error: El total de duración no puede ser negativo",
                "TOTAL_DURATION_NEGATIVE",
            )
        return valor

    @validates("total_actividades")
    def validar_total_actividades(self, key: str, valor: int) -> int:
        """Valida el contador de actividades guardadas.

        Entero no negativo. Mismo patrón que los demás acumulados.

        Args:
            key: nombre del atributo.
            valor: número de actividades registradas.

        Returns:
            El mismo valor si pasa.

        Raises:
            AppValidationError: ``TOTAL_ACTIVITIES_MUST_BE_INTEGER`` o ``TOTAL_ACTIVITIES_NEGATIVE``.
        """
        if not isinstance(valor, int):
            raise AppValidationError(
                "Error: El total de actividades debe ser un número entero",
                "TOTAL_ACTIVITIES_MUST_BE_INTEGER",
            )
        if valor < 0:
            raise AppValidationError(
                "Error: El total de actividades no puede ser negativo",
                "TOTAL_ACTIVITIES_NEGATIVE",
            )
        return valor

    @validates("objetivo_semanal_metros")
    def validar_objetivo_semanal(self, key: str, valor: int) -> int:
        """Valida el objetivo semanal de metros a nivel ORM.

        Replica el rango del esquema Pydantic (10 m – 2 000 000 m). A
        diferencia del esquema, aquí el valor no es opcional porque el
        modelo tiene un default en la columna; el validator se ejecuta
        también en asignaciones directas desde código que pudieran
        romper el invariante.

        Args:
            key: nombre del atributo.
            valor: objetivo en metros.

        Returns:
            El mismo valor si pasa.

        Raises:
            AppValidationError: ``WEEKLY_GOAL_MUST_BE_INTEGER`` o ``WEEKLY_GOAL_OUT_OF_RANGE``.
        """
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
        """Valida el objetivo mensual de metros a nivel ORM.

        Mismo rango que el semanal. No se fuerza aquí la relación
        ``mensual >= semanal × 4`` para permitir configuraciones más
        flexibles del usuario.

        Args:
            key: nombre del atributo.
            valor: objetivo en metros.

        Returns:
            El mismo valor si pasa.

        Raises:
            AppValidationError: ``MONTHLY_GOAL_MUST_BE_INTEGER`` o ``MONTHLY_GOAL_OUT_OF_RANGE``.
        """
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
        """Exige ``True`` explícito en el booleano de aceptación de términos.

        Una fila ``Usuario`` sin ``acepta_terminos=True`` no puede existir:
        el servicio lo lleva como evidencia legal del consentimiento. Se
        valida aquí además del esquema Pydantic como doble capa que
        impide crear registros por rutas internas (scripts, tests) que
        salten el esquema.

        Args:
            key: nombre del atributo.
            valor: valor del booleano.

        Returns:
            ``True`` si pasa.

        Raises:
            AppValidationError: ``TERMS_ACCEPTANCE_MUST_BE_BOOLEAN`` si no es ``bool``.
            AppValidationError: ``ACCOUNT_TERMS_ACCEPTANCE_REQUIRED`` si es ``False``.
        """
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
        """Valida que la visibilidad del perfil sea un booleano estricto.

        A diferencia de ``acepta_terminos``, aquí se permite ``False`` (el
        usuario puede decidir ocultarse del ranking y búsqueda). Solo se
        rechaza que el tipo sea incorrecto.

        Args:
            key: nombre del atributo.
            valor: valor candidato.

        Returns:
            El booleano si es de tipo correcto.

        Raises:
            AppValidationError: ``PROFILE_VISIBILITY_MUST_BE_BOOLEAN`` si no es ``bool``.
        """
        if not isinstance(valor, bool):
            raise AppValidationError(
                "Error: perfil_visible debe ser booleano",
                "PROFILE_VISIBILITY_MUST_BE_BOOLEAN",
            )
        return valor

    @validates("version_terminos")
    def validar_version_terminos(self, key: str, valor: str) -> str:
        """Valida la versión de términos que aceptó el usuario.

        Exige cadena no vacía tras recortar y tope de 10 caracteres (igual
        que el esquema). Se almacena tal cual la envió el cliente (no se
        fuerza caso) para poder auditar qué versión exacta del documento
        legal se presentó al usuario en ese alta.

        Args:
            key: nombre del atributo.
            valor: versión declarada.

        Returns:
            Versión recortada si pasa.

        Raises:
            AppValidationError: ``TERMS_VERSION_MUST_BE_TEXT`` si no es cadena.
            AppValidationError: ``TERMS_VERSION_REQUIRED`` si queda vacía tras recortar.
            AppValidationError: ``TERMS_VERSION_TOO_LONG`` si supera 10 caracteres.
        """
        # Valida version terminos.
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
        """Valida que el código de recuperación guardado sea un hash SHA-256 válido.

        La columna nunca guarda el código en claro: el servicio lo hashea
        con HMAC-SHA256 antes de persistir. Aquí se valida el formato del
        hash (64 hex) como defensa frente a escrituras accidentales del
        código en claro.

        Args:
            key: nombre del atributo.
            valor: hash SHA-256 hexadecimal, o ``None`` para limpiar.

        Returns:
            Hash en minúsculas, o ``None``.

        Raises:
            AppValidationError: ``RECOVERY_CODE_HASH_MUST_BE_STRING`` si no es cadena.
            AppValidationError: ``RECOVERY_CODE_HASH_INVALID`` si no coincide con el patrón hex64.
        """
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
    Tabla de actividades deportivas enriquecida con métricas de seguimiento.

    Se mantienen valores enteros para facilitar validación, sincronización y
    compatibilidad con el cliente móvil offline.
    """

    __tablename__ = "actividades"

    id: Mapped[int] = mapped_column(primary_key=True)

    client_local_id: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)

    usuario_id: Mapped[int] = mapped_column(
        ForeignKey("usuarios.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    tipo: Mapped[str] = mapped_column(String(20), nullable=False)
    distancia: Mapped[int] = mapped_column(Integer, nullable=False)
    duracion_total: Mapped[int] = mapped_column(Integer, nullable=False)
    duracion_movimiento: Mapped[int] = mapped_column(Integer, nullable=False)
    duracion_parado: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default=text("0")
    )
    duracion_pausa_manual: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default=text("0")
    )
    calorias_quemadas: Mapped[int] = mapped_column(Integer, nullable=False)
    ritmo_medio_movimiento: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default=text("0")
    )
    ritmo_medio_total: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default=text("0")
    )
    ritmo_maximo: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default=text("0")
    )
    velocidad_media_x100: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default=text("0")
    )
    velocidad_max_x100: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default=text("0")
    )
    auto_pausas: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default=text("0")
    )
    pausas_manuales: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default=text("0")
    )
    alertas_velocidad: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default=text("0")
    )

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
        CheckConstraint(
            "client_local_id IS NULL OR char_length(btrim(client_local_id)) BETWEEN 1 AND 64",
            name="ck_actividades_client_local_id_len",
        ),
        CheckConstraint(
            "distancia > 0 AND distancia <= 300000",
            name="ck_actividades_distancia_range",
        ),
        CheckConstraint(
            "duracion_total > 0 AND duracion_total <= 86400",
            name="ck_actividades_duracion_total_range",
        ),
        CheckConstraint(
            "duracion_movimiento > 0 AND duracion_movimiento <= 86400",
            name="ck_actividades_duracion_movimiento_range",
        ),
        CheckConstraint(
            "duracion_parado >= 0 AND duracion_parado <= 86400",
            name="ck_actividades_duracion_parado_range",
        ),
        CheckConstraint(
            "duracion_pausa_manual >= 0 AND duracion_pausa_manual <= 86400",
            name="ck_actividades_duracion_pausa_manual_range",
        ),
        CheckConstraint(
            "duracion_movimiento + duracion_parado = duracion_total",
            name="ck_actividades_duracion_breakdown_match",
        ),
        CheckConstraint(
            "duracion_pausa_manual <= duracion_total",
            name="ck_actividades_duracion_pausa_manual_total",
        ),
        CheckConstraint(
            "calorias_quemadas > 0 AND calorias_quemadas <= 10000",
            name="ck_actividades_calorias_range",
        ),
        CheckConstraint(
            "ritmo_medio_movimiento >= 0 AND ritmo_medio_movimiento <= 3600",
            name="ck_actividades_ritmo_medio_movimiento_range",
        ),
        CheckConstraint(
            "ritmo_medio_total >= 0 AND ritmo_medio_total <= 3600",
            name="ck_actividades_ritmo_medio_total_range",
        ),
        CheckConstraint(
            "ritmo_maximo >= 0 AND ritmo_maximo <= 3600",
            name="ck_actividades_ritmo_maximo_range",
        ),
        CheckConstraint(
            "velocidad_media_x100 >= 0 AND velocidad_media_x100 <= 10000",
            name="ck_actividades_velocidad_media_range",
        ),
        CheckConstraint(
            "velocidad_max_x100 >= 0 AND velocidad_max_x100 <= 10000",
            name="ck_actividades_velocidad_max_range",
        ),
        CheckConstraint(
            "velocidad_max_x100 >= velocidad_media_x100",
            name="ck_actividades_velocidad_max_ge_media",
        ),
        CheckConstraint(
            "auto_pausas >= 0 AND auto_pausas <= 500",
            name="ck_actividades_auto_pausas_range",
        ),
        CheckConstraint(
            "pausas_manuales >= 0 AND pausas_manuales <= 500",
            name="ck_actividades_pausas_manuales_range",
        ),
        CheckConstraint(
            "alertas_velocidad >= 0 AND alertas_velocidad <= 500",
            name="ck_actividades_alertas_velocidad_range",
        ),
        CheckConstraint(
            "ruta_polilinea IS NULL OR char_length(ruta_polilinea) BETWEEN 5 AND 200000",
            name="ck_actividades_ruta_polilinea_len",
        ),
        CheckConstraint(
            "ruta_mapa_url IS NULL OR char_length(ruta_mapa_url) <= 2048",
            name="ck_actividades_ruta_mapa_url_len",
        ),
        CheckConstraint(
            r"ruta_mapa_url IS NULL OR ruta_mapa_url ~* '^https?://'",
            name="ck_actividades_ruta_mapa_url_http",
        ),
        Index("ix_actividades_usuario_fecha", "usuario_id", "fecha_ruta", "id"),
        Index(
            "uq_actividades_usuario_client_local_id",
            "usuario_id",
            "client_local_id",
            unique=True,
            postgresql_where=text("client_local_id IS NOT NULL"),
        ),
    )

    @validates("usuario_id")
    def validar_usuario_id(self, key: str, valor: int) -> int:
        """Valida el ``usuario_id`` de la actividad como entero positivo.

        Aunque la FK y el NOT NULL del esquema ya impiden valores basura,
        esta validación temprana devuelve un ``error_code`` canónico en vez
        del genérico de SQLAlchemy cuando se asigna un tipo incorrecto
        (``int`` esperado) o un id no positivo.

        Args:
            key: nombre del atributo (lo pasa SQLAlchemy al ``@validates``).
            valor: id del usuario propietario.

        Returns:
            El mismo valor si pasa.

        Raises:
            AppValidationError: ``USER_ID_MUST_BE_INTEGER`` si no es entero.
            AppValidationError: ``USER_ID_MUST_BE_POSITIVE`` si ``valor <= 0``.
        """
        if not isinstance(valor, int):
            raise AppValidationError(
                "Error: usuario_id debe ser un entero", "USER_ID_MUST_BE_INTEGER"
            )
        if valor <= 0:
            raise AppValidationError(
                "Error: usuario_id debe ser mayor a 0", "USER_ID_MUST_BE_POSITIVE"
            )
        return valor

    @validates("client_local_id")
    def validar_client_local_id(self, key: str, valor: Optional[str]) -> Optional[str]:
        """Valida el identificador local opcional para idempotencia de subidas.

        Este id lo genera la app Android al crear la actividad y lo reenvía
        en el POST para que el backend pueda detectar reintentos y devolver
        la actividad ya persistida en lugar de crear duplicados. Admite
        ``None`` (cliente antiguo) y cuando hay valor aplica la terna de
        comprobaciones (tipo, no vacío, longitud <= 64) vía
        ``_validar_texto_no_vacio``.

        Args:
            key: nombre del atributo.
            valor: id local o ``None``.

        Returns:
            Id recortado, o ``None`` si no se proporcionó.

        Raises:
            AppValidationError: ``ACTIVITY_CLIENT_LOCAL_ID_MUST_BE_STRING``, ``ACTIVITY_CLIENT_LOCAL_ID_EMPTY`` o ``ACTIVITY_CLIENT_LOCAL_ID_TOO_LONG``.
        """
        if valor is None:
            return None
        return _validar_texto_no_vacio(
            valor,
            "client_local_id",
            64,
            must_be_string_code="ACTIVITY_CLIENT_LOCAL_ID_MUST_BE_STRING",
            empty_code="ACTIVITY_CLIENT_LOCAL_ID_EMPTY",
            too_long_code="ACTIVITY_CLIENT_LOCAL_ID_TOO_LONG",
        )

    @validates("tipo")
    def validar_tipo(self, key: str, valor: Optional[Any]) -> str:
        """Valida y normaliza el tipo de actividad persistido como texto.

        Delega en ``_validar_enum_str`` con ``VALID_TIPOS_ACTIVIDAD``. A
        diferencia de otros enums del modelo, ``tipo`` es obligatorio:
        una actividad sin tipo no tiene sentido. Como
        ``_validar_enum_str`` devuelve ``None`` para entrada ``None``, se
        comprueba después y se levanta ``ACTIVITY_TYPE_REQUIRED`` aquí
        para mantener todos los errores de este campo agrupados.

        Args:
            key: nombre del atributo.
            valor: valor candidato (enum, cadena o ``None``).

        Returns:
            Cadena canónica del enum.

        Raises:
            AppValidationError: ``ACTIVITY_TYPE_MUST_BE_STRING`` si no es cadena.
            AppValidationError: ``ACTIVITY_TYPE_INVALID`` si no pertenece al enum.
            AppValidationError: ``ACTIVITY_TYPE_REQUIRED`` si llega ``None``.
        """
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
        """Valida la distancia en metros (>0, <=300 km).

        Delega en ``validators.validar_distancia_logica``, que además del
        rango rechaza valores fisiológicamente imposibles (300 km de tope
        actúa como cortafuegos ante clientes rotos).

        Args:
            key: nombre del atributo.
            valor: distancia en metros.

        Returns:
            El mismo valor si pasa.

        Raises:
            AppValidationError: ``DISTANCE_MUST_BE_POSITIVE`` o ``DISTANCE_OUT_OF_RANGE``.
        """
        return validators.validar_distancia_logica(valor)

    @validates("duracion_total")
    def validar_duracion_total(self, key: str, valor: int) -> int:
        """Valida la duración total (>0, <=24 horas).

        Delega en ``validators.validar_duracion_logica``. Una actividad sin
        tiempo no tiene sentido; el tope de 24 h descarta entradas absurdas.

        Args:
            key: nombre del atributo.
            valor: duración total en segundos.

        Returns:
            El mismo valor si pasa.

        Raises:
            AppValidationError: ``DURATION_MUST_BE_POSITIVE`` o ``DURATION_TOO_LONG``.
        """
        return validators.validar_duracion_logica(valor)

    @validates("duracion_movimiento")
    def validar_duracion_movimiento(self, key: str, valor: int) -> int:
        """Valida la duración en movimiento (>0, <=24 horas).

        Mismo validador que ``duracion_total``. La consistencia
        ``duracion_movimiento <= duracion_total`` se impone a nivel de
        esquema Pydantic; aquí solo validamos rangos individuales.

        Args:
            key: nombre del atributo.
            valor: duración en movimiento en segundos.

        Returns:
            El mismo valor si pasa.

        Raises:
            AppValidationError: ``DURATION_MUST_BE_POSITIVE`` o ``DURATION_TOO_LONG``.
        """
        return validators.validar_duracion_logica(valor)

    @validates("duracion_parado")
    def validar_duracion_parado(self, key: str, valor: int) -> int:
        """Valida la duración parada (0 permitido, tope 24 horas).

        Delega en ``validators.validar_duracion_no_negativa_logica``, que
        a diferencia de ``validar_duracion_logica`` admite ``0``: es
        perfectamente legítimo que una actividad no haya tenido ninguna
        pausa.

        Args:
            key: nombre del atributo.
            valor: duración parada en segundos.

        Returns:
            El mismo valor si pasa.

        Raises:
            AppValidationError: ``STOPPED_DURATION_NEGATIVE`` o ``STOPPED_DURATION_TOO_LONG``.
        """
        return validators.validar_duracion_no_negativa_logica(
            valor, "la duración parada", "STOPPED_DURATION"
        )

    @validates("duracion_pausa_manual")
    def validar_duracion_pausa_manual(self, key: str, valor: int) -> int:
        """Valida la duración de pausa manual (0 permitido, tope 24 horas).

        Misma semántica que ``duracion_parado`` pero con prefijo de error
        ``MANUAL_PAUSE_DURATION`` para distinguir el origen en logs/UI.

        Args:
            key: nombre del atributo.
            valor: duración de pausa manual en segundos.

        Returns:
            El mismo valor si pasa.

        Raises:
            AppValidationError: ``MANUAL_PAUSE_DURATION_NEGATIVE`` o ``MANUAL_PAUSE_DURATION_TOO_LONG``.
        """
        return validators.validar_duracion_no_negativa_logica(
            valor, "la duración de pausa manual", "MANUAL_PAUSE_DURATION"
        )

    @validates("calorias_quemadas")
    def validar_calorias(self, key: str, valor: int) -> int:
        """Valida las calorías quemadas (>0, <=10000).

        Delega en ``validators.validar_calorias_logica``. El tope
        fisiológico descarta inputs absurdos.

        Args:
            key: nombre del atributo.
            valor: calorías quemadas en la sesión.

        Returns:
            El mismo valor si pasa.

        Raises:
            AppValidationError: ``CALORIES_MUST_BE_POSITIVE`` o ``CALORIES_OUT_OF_RANGE``.
        """
        return validators.validar_calorias_logica(valor)

    @validates("ritmo_medio_movimiento")
    def validar_ritmo_medio_movimiento(self, key: str, valor: int) -> int:
        """Valida el ritmo medio en movimiento (0–3600 s/km).

        Delega en ``validators.validar_ritmo_segundos_km_logica`` con
        prefijo ``MOVING_PACE``.

        Args:
            key: nombre del atributo.
            valor: ritmo en segundos por kilómetro.

        Returns:
            El mismo valor si pasa.

        Raises:
            AppValidationError: ``MOVING_PACE_NEGATIVE`` o ``MOVING_PACE_OUT_OF_RANGE``.
        """
        return validators.validar_ritmo_segundos_km_logica(
            valor, "el ritmo medio en movimiento", "MOVING_PACE"
        )

    @validates("ritmo_medio_total")
    def validar_ritmo_medio_total(self, key: str, valor: int) -> int:
        """Valida el ritmo medio total (0–3600 s/km).

        Mismo rango que el de movimiento, con prefijo ``TOTAL_PACE`` para
        distinguir el origen en logs/UI.

        Args:
            key: nombre del atributo.
            valor: ritmo en segundos por kilómetro.

        Returns:
            El mismo valor si pasa.

        Raises:
            AppValidationError: ``TOTAL_PACE_NEGATIVE`` o ``TOTAL_PACE_OUT_OF_RANGE``.
        """
        return validators.validar_ritmo_segundos_km_logica(
            valor, "el ritmo medio total", "TOTAL_PACE"
        )

    @validates("ritmo_maximo")
    def validar_ritmo_maximo(self, key: str, valor: int) -> int:
        """Valida el ritmo máximo (0–3600 s/km).

        Mismo rango que los anteriores, con prefijo ``MAX_PACE``.

        Args:
            key: nombre del atributo.
            valor: ritmo máximo alcanzado en segundos por kilómetro.

        Returns:
            El mismo valor si pasa.

        Raises:
            AppValidationError: ``MAX_PACE_NEGATIVE`` o ``MAX_PACE_OUT_OF_RANGE``.
        """
        return validators.validar_ritmo_segundos_km_logica(
            valor, "el ritmo máximo", "MAX_PACE"
        )

    @validates("velocidad_media_x100")
    def validar_velocidad_media(self, key: str, valor: int) -> int:
        """Valida la velocidad media en formato km/h × 100 (0–10000).

        Delega en ``validators.validar_velocidad_x100_logica`` con prefijo
        ``AVERAGE_SPEED``. El tope 10 000 equivale a 100 km/h.

        Args:
            key: nombre del atributo.
            valor: velocidad media expresada como km/h × 100.

        Returns:
            El mismo valor si pasa.

        Raises:
            AppValidationError: ``AVERAGE_SPEED_NEGATIVE`` o ``AVERAGE_SPEED_OUT_OF_RANGE``.
        """
        return validators.validar_velocidad_x100_logica(
            valor, "la velocidad media", "AVERAGE_SPEED"
        )

    @validates("velocidad_max_x100")
    def validar_velocidad_max(self, key: str, valor: int) -> int:
        """Valida la velocidad máxima en formato km/h × 100 (0–10000).

        Mismo rango que la media, con prefijo ``MAX_SPEED``. La
        consistencia ``máxima >= media`` se impone en el esquema Pydantic
        (``GuardarActividad.validar_consistencia_temporal``).

        Args:
            key: nombre del atributo.
            valor: velocidad máxima expresada como km/h × 100.

        Returns:
            El mismo valor si pasa.

        Raises:
            AppValidationError: ``MAX_SPEED_NEGATIVE`` o ``MAX_SPEED_OUT_OF_RANGE``.
        """
        return validators.validar_velocidad_x100_logica(
            valor, "la velocidad máxima", "MAX_SPEED"
        )

    @validates("auto_pausas")
    def validar_auto_pausas(self, key: str, valor: int) -> int:
        """Valida el contador de auto-pausas (0–500).

        Delega en ``validators.validar_contador_tracking_logica`` con
        prefijo ``AUTO_PAUSE_COUNT``.

        Args:
            key: nombre del atributo.
            valor: número de auto-pausas detectadas.

        Returns:
            El mismo valor si pasa.

        Raises:
            AppValidationError: ``AUTO_PAUSE_COUNT_NEGATIVE`` o ``AUTO_PAUSE_COUNT_OUT_OF_RANGE``.
        """
        return validators.validar_contador_tracking_logica(
            valor, "las auto pausas", "AUTO_PAUSE_COUNT"
        )

    @validates("pausas_manuales")
    def validar_pausas_manuales(self, key: str, valor: int) -> int:
        """Valida el contador de pausas manuales (0–500).

        Mismo validador, con prefijo ``MANUAL_PAUSE_COUNT``.

        Args:
            key: nombre del atributo.
            valor: número de pausas manuales.

        Returns:
            El mismo valor si pasa.

        Raises:
            AppValidationError: ``MANUAL_PAUSE_COUNT_NEGATIVE`` o ``MANUAL_PAUSE_COUNT_OUT_OF_RANGE``.
        """
        return validators.validar_contador_tracking_logica(
            valor, "las pausas manuales", "MANUAL_PAUSE_COUNT"
        )

    @validates("alertas_velocidad")
    def validar_alertas_velocidad(self, key: str, valor: int) -> int:
        """Valida el contador de alertas de velocidad (0–500).

        Mismo validador, con prefijo ``SPEED_ALERT_COUNT``.

        Args:
            key: nombre del atributo.
            valor: número de alertas disparadas durante la sesión.

        Returns:
            El mismo valor si pasa.

        Raises:
            AppValidationError: ``SPEED_ALERT_COUNT_NEGATIVE`` o ``SPEED_ALERT_COUNT_OUT_OF_RANGE``.
        """
        return validators.validar_contador_tracking_logica(
            valor, "las alertas de velocidad", "SPEED_ALERT_COUNT"
        )

    @validates("ruta_polilinea")
    def validar_ruta_polilinea(self, key: str, valor: Optional[str]) -> Optional[str]:
        """Valida la polilínea solo cuando existe, manteniendo el campo opcional.

        Admite ``None`` (actividades sin GPS grabado). Cuando hay valor,
        delega en ``validators.validar_polilinea_logica``, que exige tamaño
        mínimo (descartar ``"abc"`` que no es ninguna ruta real) y máximo
        (protección contra payloads descomunales).

        Args:
            key: nombre del atributo.
            valor: polilínea codificada o ``None``.

        Returns:
            El mismo valor si pasa (``None`` si entró ``None``).

        Raises:
            AppValidationError: ``ROUTE_INVALID`` o ``ROUTE_TOO_LARGE``.
        """
        if valor is None:
            return None
        return validators.validar_polilinea_logica(valor)

    @validates("ruta_mapa_url")
    def validar_ruta_mapa_url(self, key: str, valor: Optional[str]) -> Optional[str]:
        """Valida la URL del mapa estático generado para la actividad.

        Admite ``None`` (actividades sin mapa asociado). Cuando hay valor,
        se aplican dos comprobaciones:

        - Longitud <= 2048 caracteres (margen amplio; URLs con ``public_id``
          complejo de Cloudinary pueden crecer).
        - Esquema ``http://`` o ``https://``: la app nunca cargaría un mapa
          desde otro esquema y cualquier otra cosa es sospechosa.

        Args:
            key: nombre del atributo.
            valor: URL o ``None``.

        Returns:
            La misma URL si pasa (``None`` si entró ``None``).

        Raises:
            AppValidationError: ``MAP_URL_TOO_LONG`` si supera 2048 caracteres.
            AppValidationError: ``MAP_URL_INVALID_SCHEME`` si no empieza por ``http://`` o ``https://``.
        """
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
        """Valida y normaliza a UTC la fecha/hora reportada para la actividad.

        Delega en ``validators.validar_fecha_ruta_logica``: exige
        ``tzinfo`` (sin zona no se puede comparar entre dispositivos),
        rechaza más de 10 minutos en el futuro (absorbe desajustes
        de reloj cliente/servidor) y devuelve el instante siempre en UTC
        para que la columna guarde valores homogéneos.

        Args:
            key: nombre del atributo.
            valor: ``datetime`` propuesto por el cliente.

        Returns:
            El mismo instante en UTC.

        Raises:
            AppValidationError: ``ACTIVITY_DATE_MISSING_TIMEZONE`` o ``ACTIVITY_DATE_IN_FUTURE``.
        """
        return validators.validar_fecha_ruta_logica(valor)


class ActividadDiagnostico(Base):
    """
    Persistencia de telemetría de seguimiento enviada automáticamente por builds internas.

    Esta tabla NO sustituye a ``Actividad`` ni participa en los acumulados del perfil.
    Su única finalidad es permitir depurar sesiones problemáticas reportadas por testers
    remotos sin necesidad de tener físicamente el móvil.

    Diseño:
    - ``actividad_id`` es opcional para no bloquear el envío del diagnóstico si la
      actividad todavía no existe en backend o si el guardado principal ha fallado.
    - ``event_log_json`` y ``device_info_json`` se guardan como texto JSON para
      mantener la migración sencilla y desacoplada del tipo JSONB.
    """

    __tablename__ = "actividades_diagnostico"

    id: Mapped[int] = mapped_column(primary_key=True)

    usuario_id: Mapped[int] = mapped_column(
        ForeignKey("usuarios.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    actividad_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("actividades.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    actividad_local_id: Mapped[Optional[str]] = mapped_column(
        String(64), nullable=True, index=True
    )

    session_started_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    session_finished_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    last_timer_tick_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    service_created_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    service_destroyed_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    elapsed_seconds: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default=text("0")
    )
    moving_seconds: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default=text("0")
    )
    stopped_seconds: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default=text("0")
    )
    manual_pause_seconds: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default=text("0")
    )

    distance_meters: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default=text("0")
    )
    average_pace_total: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default=text("0")
    )
    average_pace_moving: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default=text("0")
    )
    max_pace: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default=text("0")
    )

    auto_pauses: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default=text("0")
    )
    manual_pauses: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default=text("0")
    )
    speed_alerts: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default=text("0")
    )

    running_classified_seconds: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default=text("0")
    )
    walking_classified_seconds: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default=text("0")
    )
    service_restart_count: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default=text("0")
    )

    current_status: Mapped[Optional[str]] = mapped_column(String(40), nullable=True)
    app_version: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    os_version: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    manufacturer: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    model: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)

    event_log_json: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    device_info_json: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    creada_en: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=_ahora_utc,
        server_default=text("CURRENT_TIMESTAMP"),
        index=True,
    )

    __table_args__ = (
        CheckConstraint(
            "elapsed_seconds >= 0", name="ck_act_diag_elapsed_non_negative"
        ),
        CheckConstraint("moving_seconds >= 0", name="ck_act_diag_moving_non_negative"),
        CheckConstraint(
            "stopped_seconds >= 0", name="ck_act_diag_stopped_non_negative"
        ),
        CheckConstraint(
            "manual_pause_seconds >= 0", name="ck_act_diag_manual_pause_non_negative"
        ),
        CheckConstraint(
            "distance_meters >= 0", name="ck_act_diag_distance_non_negative"
        ),
        CheckConstraint(
            "average_pace_total >= 0", name="ck_act_diag_avg_total_non_negative"
        ),
        CheckConstraint(
            "average_pace_moving >= 0", name="ck_act_diag_avg_moving_non_negative"
        ),
        CheckConstraint("max_pace >= 0", name="ck_act_diag_max_pace_non_negative"),
        CheckConstraint(
            "auto_pauses >= 0", name="ck_act_diag_auto_pauses_non_negative"
        ),
        CheckConstraint(
            "manual_pauses >= 0", name="ck_act_diag_manual_pauses_non_negative"
        ),
        CheckConstraint(
            "speed_alerts >= 0", name="ck_act_diag_speed_alerts_non_negative"
        ),
        CheckConstraint(
            "running_classified_seconds >= 0", name="ck_act_diag_running_non_negative"
        ),
        CheckConstraint(
            "walking_classified_seconds >= 0", name="ck_act_diag_walking_non_negative"
        ),
        CheckConstraint(
            "service_restart_count >= 0", name="ck_act_diag_restart_non_negative"
        ),
        CheckConstraint(
            "actividad_local_id IS NULL OR char_length(btrim(actividad_local_id)) BETWEEN 1 AND 64",
            name="ck_act_diag_local_id_len",
        ),
        CheckConstraint(
            "current_status IS NULL OR char_length(btrim(current_status)) BETWEEN 1 AND 40",
            name="ck_act_diag_status_len",
        ),
        CheckConstraint(
            "app_version IS NULL OR char_length(btrim(app_version)) <= 64",
            name="ck_act_diag_app_version_len",
        ),
        CheckConstraint(
            "os_version IS NULL OR char_length(btrim(os_version)) <= 64",
            name="ck_act_diag_os_version_len",
        ),
        CheckConstraint(
            "manufacturer IS NULL OR char_length(btrim(manufacturer)) <= 64",
            name="ck_act_diag_manufacturer_len",
        ),
        CheckConstraint(
            "model IS NULL OR char_length(btrim(model)) <= 128",
            name="ck_act_diag_model_len",
        ),
        Index(
            "ix_actividades_diagnostico_usuario_creada", "usuario_id", "creada_en", "id"
        ),
    )

    @validates("usuario_id")
    def validar_usuario_id(self, key: str, valor: int) -> int:
        """Valida el ``usuario_id`` de la fila de diagnóstico como entero positivo.

        Usa ``error_code`` específico con prefijo ``DIAGNOSTIC_`` para
        distinguir en logs que el fallo viene del pipeline de telemetría
        interna, no del pipeline principal de actividades.

        Args:
            key: nombre del atributo.
            valor: id del usuario dueño del diagnóstico.

        Returns:
            El mismo valor si pasa.

        Raises:
            AppValidationError: ``DIAGNOSTIC_USER_ID_MUST_BE_INTEGER`` o ``DIAGNOSTIC_USER_ID_MUST_BE_POSITIVE``.
        """
        if not isinstance(valor, int):
            raise AppValidationError(
                "Error: usuario_id debe ser un entero",
                "DIAGNOSTIC_USER_ID_MUST_BE_INTEGER",
            )
        if valor <= 0:
            raise AppValidationError(
                "Error: usuario_id debe ser mayor a 0",
                "DIAGNOSTIC_USER_ID_MUST_BE_POSITIVE",
            )
        return valor

    @validates("actividad_id")
    def validar_actividad_id(self, key: str, valor: Optional[int]) -> Optional[int]:
        """Valida el ``actividad_id`` opcional de la fila de diagnóstico.

        Se permite ``None`` a propósito: el diagnóstico puede enviarse
        incluso si la actividad principal no se ha persistido (porque el
        guardado falló o porque aún no se ha llamado). Cuando hay valor,
        sigue las mismas reglas que el resto de ids: entero y positivo.

        Args:
            key: nombre del atributo.
            valor: id remoto de la actividad asociada, o ``None``.

        Returns:
            El mismo valor si pasa; ``None`` si no hay asociación.

        Raises:
            AppValidationError: ``DIAGNOSTIC_ACTIVITY_ID_MUST_BE_INTEGER`` o ``DIAGNOSTIC_ACTIVITY_ID_MUST_BE_POSITIVE``.
        """
        if valor is None:
            return None
        if not isinstance(valor, int):
            raise AppValidationError(
                "Error: actividad_id debe ser un entero",
                "DIAGNOSTIC_ACTIVITY_ID_MUST_BE_INTEGER",
            )
        if valor <= 0:
            raise AppValidationError(
                "Error: actividad_id debe ser mayor a 0",
                "DIAGNOSTIC_ACTIVITY_ID_MUST_BE_POSITIVE",
            )
        return valor

    @validates(
        "actividad_local_id",
        "current_status",
        "app_version",
        "os_version",
        "manufacturer",
        "model",
    )
    def validar_textos_cortos(self, key: str, valor: Optional[str]) -> Optional[str]:
        """Valida y normaliza los campos de texto descriptivos del diagnóstico.

        Un único validator cubre ``actividad_local_id``, ``current_status``,
        ``app_version``, ``os_version``, ``manufacturer`` y ``model``: son
        todos cadenas descriptivas opcionales que solo necesitan ser
        cadenas reales. Recorta espacios y colapsa cadenas vacías a ``None``
        para no ensuciar la tabla con entradas sin contenido real.

        Args:
            key: nombre del atributo; el mismo validator se invoca para varios.
            valor: cadena o ``None``.

        Returns:
            Cadena recortada si aporta contenido; ``None`` si estaba vacía o era ``None``.

        Raises:
            AppValidationError: ``DIAGNOSTIC_TEXT_FIELD_MUST_BE_STRING`` si el valor no es cadena.
        """
        if valor is None:
            return None
        if not isinstance(valor, str):
            raise AppValidationError(
                "Error: el campo de diagnóstico debe ser texto",
                "DIAGNOSTIC_TEXT_FIELD_MUST_BE_STRING",
            )
        valor = valor.strip()
        return valor or None

    @validates(
        "session_started_at",
        "session_finished_at",
        "last_timer_tick_at",
        "service_created_at",
        "service_destroyed_at",
        "creada_en",
    )
    def validar_fechas(self, key: str, valor: Optional[datetime]) -> Optional[datetime]:
        """Normaliza a UTC todas las columnas de timestamp del diagnóstico.

        Cubre los hitos de la sesión (``session_started_at``,
        ``session_finished_at``, ``last_timer_tick_at``,
        ``service_created_at``, ``service_destroyed_at``) y la propia
        ``creada_en``. Todas son opcionales salvo ``creada_en``, que tiene
        valor por defecto a nivel de columna; el ORM se ocupa del default.

        Args:
            key: nombre del atributo; el validator se invoca para varios.
            valor: ``datetime`` o ``None``.

        Returns:
            ``datetime`` en UTC, o ``None``.
        """
        return _normalizar_datetime_utc(valor)

    @validates(
        "elapsed_seconds",
        "moving_seconds",
        "stopped_seconds",
        "manual_pause_seconds",
        "distance_meters",
        "average_pace_total",
        "average_pace_moving",
        "max_pace",
        "auto_pauses",
        "manual_pauses",
        "speed_alerts",
        "running_classified_seconds",
        "walking_classified_seconds",
        "service_restart_count",
    )
    def validar_enteros_no_negativos(self, key: str, valor: int) -> int:
        """Valida que los contadores numéricos del diagnóstico sean enteros >= 0.

        Aplica a todos los campos numéricos del diagnóstico (tiempos,
        distancia, ritmos, contadores de pausas, classifications y restart
        count). No se fijan topes máximos individuales porque el
        diagnóstico puede cubrir sesiones extremadamente largas y preferimos
        tener la telemetría aunque sea atípica; para consistencia cruzada
        (``moving_seconds <= elapsed_seconds``) existe el validator de
        esquema Pydantic.

        Args:
            key: nombre del atributo; el validator se invoca para varios.
            valor: entero candidato.

        Returns:
            El mismo valor si es no negativo.

        Raises:
            AppValidationError: ``DIAGNOSTIC_NUMERIC_FIELD_MUST_BE_INTEGER`` si no es entero.
            AppValidationError: ``DIAGNOSTIC_NUMERIC_FIELD_NEGATIVE`` si es negativo.
        """
        if not isinstance(valor, int):
            raise AppValidationError(
                "Error: el valor de diagnóstico debe ser un entero",
                "DIAGNOSTIC_NUMERIC_FIELD_MUST_BE_INTEGER",
            )
        if valor < 0:
            raise AppValidationError(
                "Error: el valor de diagnóstico no puede ser negativo",
                "DIAGNOSTIC_NUMERIC_FIELD_NEGATIVE",
            )
        return valor

    @validates("event_log_json", "device_info_json")
    def validar_json_serializado(self, key: str, valor: Optional[str]) -> Optional[str]:
        """Valida que los campos JSON textuales sean cadenas (o ``None``).

        Aplica a ``event_log_json`` y ``device_info_json``, que guardan
        estructuras serializadas por el backend como texto para poder
        inspeccionarlas sin depender de funciones JSON de PostgreSQL.
        Aquí solo se valida el tipo y se colapsa cadena vacía a ``None``;
        la validez del JSON como tal se asume ya hecha por quien serializó.

        Args:
            key: nombre del atributo.
            valor: cadena serializada o ``None``.

        Returns:
            Cadena recortada si aporta contenido, ``None`` si estaba vacía o era ``None``.

        Raises:
            AppValidationError: ``DIAGNOSTIC_JSON_FIELD_MUST_BE_STRING`` si no es cadena.
        """
        if valor is None:
            return None
        if not isinstance(valor, str):
            raise AppValidationError(
                "Error: el JSON de diagnóstico debe ser texto",
                "DIAGNOSTIC_JSON_FIELD_MUST_BE_STRING",
            )
        valor = valor.strip()
        return valor or None


class UsuarioAuthSocial(Base):
    """
    Vincula una cuenta interna con un proveedor de autenticación social.

    Permite soportar múltiples proveedores por usuario sin mezclar la lógica
    del login tradicional con la identidad externa.
    """

    __tablename__ = "usuarios_auth_social"

    id: Mapped[int] = mapped_column(primary_key=True)

    usuario_id: Mapped[int] = mapped_column(
        ForeignKey("usuarios.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    provider: Mapped[str] = mapped_column(String(20), nullable=False)
    provider_user_id: Mapped[str] = mapped_column(String(255), nullable=False)
    email_social: Mapped[Optional[str]] = mapped_column(String(320), nullable=True)
    nombre_social: Mapped[Optional[str]] = mapped_column(String(120), nullable=True)
    avatar_url: Mapped[Optional[str]] = mapped_column(String(2048), nullable=True)
    creada_en: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=_ahora_utc,
        server_default=text("CURRENT_TIMESTAMP"),
    )
    ultimo_login_en: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    __table_args__ = (
        sa.UniqueConstraint(
            "provider",
            "provider_user_id",
            name="uq_usuarios_auth_social_provider_user",
        ),
        sa.UniqueConstraint(
            "usuario_id",
            "provider",
            name="uq_usuarios_auth_social_usuario_provider",
        ),
        CheckConstraint(
            _build_enum_check_sql("provider", VALID_SOCIAL_PROVIDERS, allow_null=False),
            name="ck_usuarios_auth_social_provider_values",
        ),
        CheckConstraint(
            "char_length(btrim(provider_user_id)) BETWEEN 1 AND 255",
            name="ck_usuarios_auth_social_provider_user_id_len",
        ),
        CheckConstraint(
            "email_social IS NULL OR char_length(email_social) BETWEEN 3 AND 320",
            name="ck_usuarios_auth_social_email_len",
        ),
        CheckConstraint(
            "email_social IS NULL OR email_social = lower(btrim(email_social))",
            name="ck_usuarios_auth_social_email_normalized_lower",
        ),
        CheckConstraint(
            "email_social IS NULL OR email_social !~ '[[:space:]]'",
            name="ck_usuarios_auth_social_email_no_spaces",
        ),
        CheckConstraint(
            "nombre_social IS NULL OR char_length(btrim(nombre_social)) BETWEEN 1 AND 120",
            name="ck_usuarios_auth_social_nombre_social_len",
        ),
        CheckConstraint(
            "avatar_url IS NULL OR char_length(avatar_url) <= 2048",
            name="ck_usuarios_auth_social_avatar_url_len",
        ),
        CheckConstraint(
            r"avatar_url IS NULL OR avatar_url ~* '^https?://'",
            name="ck_usuarios_auth_social_avatar_url_http",
        ),
        CheckConstraint(
            "ultimo_login_en IS NULL OR ultimo_login_en >= creada_en",
            name="ck_usuarios_auth_social_ultimo_login_ge_creada",
        ),
    )

    @validates("usuario_id")
    def validar_usuario_id(self, key: str, valor: int) -> int:
        """Valida el ``usuario_id`` al que se vincula la cuenta social.

        Mismas reglas que en el resto de tablas: entero positivo. Además
        de la propia FK, el ``error_code`` específico permite que un alta
        fallida por id inválido se distinga claramente en los logs de
        auth social.

        Args:
            key: nombre del atributo.
            valor: id del usuario local.

        Returns:
            El mismo valor si pasa.

        Raises:
            AppValidationError: ``USER_ID_MUST_BE_INTEGER`` o ``USER_ID_MUST_BE_POSITIVE``.
        """
        if not isinstance(valor, int):
            raise AppValidationError(
                "Error: usuario_id debe ser un entero", "USER_ID_MUST_BE_INTEGER"
            )
        if valor <= 0:
            raise AppValidationError(
                "Error: usuario_id debe ser mayor a 0", "USER_ID_MUST_BE_POSITIVE"
            )
        return valor

    @validates("provider")
    def validar_provider(self, key: str, valor: str) -> str:
        """Valida el identificador del proveedor social contra la lista soportada.

        Delega en ``_validar_enum_str`` con ``VALID_SOCIAL_PROVIDERS``
        (hoy solo ``{"google"}``). A diferencia del resto de validadores
        basados en ``_validar_enum_str``, aquí el valor es obligatorio y
        una ``assert`` confirma que el helper no devolvió ``None`` para
        contentar al type checker.

        Args:
            key: nombre del atributo.
            valor: identificador del proveedor.

        Returns:
            Identificador del proveedor recortado y validado.

        Raises:
            AppValidationError: ``SOCIAL_PROVIDER_MUST_BE_TEXT`` si no es cadena.
            AppValidationError: ``SOCIAL_PROVIDER_INVALID`` si no pertenece a la lista soportada.
        """
        resultado = _validar_enum_str(
            valor,
            VALID_SOCIAL_PROVIDERS,
            "provider",
            must_be_text_code="SOCIAL_PROVIDER_MUST_BE_TEXT",
            invalid_code="SOCIAL_PROVIDER_INVALID",
        )
        assert resultado is not None
        return resultado

    @validates("provider_user_id")
    def validar_provider_user_id(self, key: str, valor: str) -> str:
        """Valida el ``sub`` del proveedor (id inmutable del usuario en Google, etc.).

        Tope 255 caracteres para dar margen al ``sub`` de Google (21 hoy)
        sin quedarnos cortos ante proveedores futuros con ids más largos.
        No se fuerza formato específico porque varía entre proveedores.

        Args:
            key: nombre del atributo.
            valor: id del usuario en el proveedor.

        Returns:
            Id recortado.

        Raises:
            AppValidationError: ``SOCIAL_PROVIDER_USER_ID_MUST_BE_STRING``, ``SOCIAL_PROVIDER_USER_ID_EMPTY`` o ``SOCIAL_PROVIDER_USER_ID_TOO_LONG``.
        """
        return _validar_texto_no_vacio(
            valor,
            "provider_user_id",
            255,
            must_be_string_code="SOCIAL_PROVIDER_USER_ID_MUST_BE_STRING",
            empty_code="SOCIAL_PROVIDER_USER_ID_EMPTY",
            too_long_code="SOCIAL_PROVIDER_USER_ID_TOO_LONG",
        )

    @validates("email_social")
    def validar_email_social(self, key: str, valor: Optional[str]) -> Optional[str]:
        """Valida el email que el proveedor social devolvió para el usuario.

        Admite ``None`` (no todos los proveedores devuelven email) y además
        colapsa cadena vacía tras recortar a ``None`` también: si el
        proveedor envía ``""`` queremos guardarlo como "no tiene email" y
        no como una cadena vacía. Cuando hay contenido real, se valida la
        sintaxis con ``email_validator`` (sin deliverability: ya confiamos
        en que el proveedor validó su propio lado) y se normaliza a
        minúsculas para detectar duplicados correctamente.

        Args:
            key: nombre del atributo.
            valor: email candidato o ``None``.

        Returns:
            Email en minúsculas ya validado, o ``None``.

        Raises:
            AppValidationError: ``SOCIAL_EMAIL_MUST_BE_TEXT`` si no es cadena.
            AppValidationError: ``SOCIAL_EMAIL_FORMAT_INVALID`` si la sintaxis no es válida.
        """
        # Valida correo electrónico social.
        if valor is None:
            return None

        if not isinstance(valor, str):
            raise AppValidationError(
                "Error: El email social debe ser un texto",
                "SOCIAL_EMAIL_MUST_BE_TEXT",
            )

        valor = valor.strip().lower()
        if not valor:
            return None

        try:
            email_info = validate_email(valor, check_deliverability=False)
            return email_info.normalized.lower()
        except EmailNotValidError:
            raise AppValidationError(
                "Error: El formato del correo electrónico social no es válido",
                "SOCIAL_EMAIL_FORMAT_INVALID",
            )

    @validates("nombre_social")
    def validar_nombre_social(self, key: str, valor: Optional[str]) -> Optional[str]:
        """Valida el nombre que el proveedor social devolvió para el usuario.

        Admite ``None``. Cuando hay valor, aplica la terna estándar
        (tipo, no vacío, longitud <= 120). No aplica la misma política
        restrictiva de caracteres que ``Usuario.nombre_real`` porque los
        proveedores pueden devolver nombres con caracteres que nuestra
        regex interna no admitiría (p. ej. caracteres CJK), y rechazar
        eso rompería registros legítimos.

        Args:
            key: nombre del atributo.
            valor: nombre social o ``None``.

        Returns:
            Nombre recortado si pasa, ``None`` si se pasó ``None``.

        Raises:
            AppValidationError: ``SOCIAL_NAME_MUST_BE_STRING``, ``SOCIAL_NAME_EMPTY`` o ``SOCIAL_NAME_TOO_LONG``.
        """
        if valor is None:
            return None
        return _validar_texto_no_vacio(
            valor,
            "nombre_social",
            120,
            must_be_string_code="SOCIAL_NAME_MUST_BE_STRING",
            empty_code="SOCIAL_NAME_EMPTY",
            too_long_code="SOCIAL_NAME_TOO_LONG",
        )

    @validates("avatar_url")
    def validar_avatar_url(self, key: str, valor: Optional[str]) -> Optional[str]:
        """Valida la URL del avatar que devuelve el proveedor social.

        Delega en ``_validar_url_http_opcional``: exige cadena y esquema
        ``http``/``https`` con tope de 2048 caracteres.

        Args:
            key: nombre del atributo.
            valor: URL o ``None``.

        Returns:
            URL recortada si pasa, ``None`` si no había.

        Raises:
            AppValidationError: ``SOCIAL_AVATAR_URL_MUST_BE_TEXT``, ``SOCIAL_AVATAR_URL_TOO_LONG`` o ``SOCIAL_AVATAR_URL_INVALID``.
        """
        return _validar_url_http_opcional(
            valor,
            "avatar_url",
            2048,
            must_be_text_code="SOCIAL_AVATAR_URL_MUST_BE_TEXT",
            too_long_code="SOCIAL_AVATAR_URL_TOO_LONG",
            invalid_code="SOCIAL_AVATAR_URL_INVALID",
        )

    @validates("creada_en", "ultimo_login_en")
    def validar_fechas(self, key: str, valor: Optional[datetime]) -> Optional[datetime]:
        """Normaliza a UTC las columnas de timestamp del vínculo social.

        Cubre ``creada_en`` (cuándo se vinculó la cuenta) y
        ``ultimo_login_en`` (cuándo fue el último login social). Garantizar
        UTC aquí evita comparaciones ambiguas al listar cuentas por
        "último uso" o purgar vínculos inactivos.

        Args:
            key: nombre del atributo.
            valor: ``datetime`` o ``None``.

        Returns:
            ``datetime`` en UTC, o ``None``.
        """
        return _normalizar_datetime_utc(valor)


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
        """Valida el ``usuario_id`` dueño del refresh token.

        Entero positivo, mismas reglas que las demás tablas. Los refresh
        tokens se indexan por usuario para que el logout global
        (``_limpiar_sesiones_refresh_usuario``) pueda purgar todas las
        sesiones de un usuario de una sola query.

        Args:
            key: nombre del atributo.
            valor: id del usuario.

        Returns:
            El mismo valor si pasa.

        Raises:
            AppValidationError: ``USER_ID_MUST_BE_INTEGER`` o ``USER_ID_MUST_BE_POSITIVE``.
        """
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
        """Valida los identificadores de sesión ``jti``, ``familia_id`` y ``reemplazada_por_jti``.

        El ``jti`` es el id único del refresh token individual; ``familia_id``
        agrupa todos los tokens derivados del mismo login (para revocar
        toda la familia ante reuso sospechoso); ``reemplazada_por_jti`` es
        opcional y apunta al token que sustituyó al actual tras una
        rotación. Los tres comparten el mismo validador porque siguen las
        mismas reglas: texto no vacío de hasta 64 caracteres (hex de un
        ``uuid4().hex``).

        Args:
            key: nombre del atributo.
            valor: identificador o ``None``.

        Returns:
            Id recortado o ``None`` si entró ``None`` (solo permitido en ``reemplazada_por_jti``).

        Raises:
            AppValidationError: ``SESSION_IDENTIFIER_MUST_BE_STRING``, ``SESSION_IDENTIFIER_EMPTY`` o ``SESSION_IDENTIFIER_TOO_LONG``.
        """
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
        """Valida que el hash del refresh token sea un SHA-256 hexadecimal obligatorio.

        La columna nunca guarda el refresh token en claro: el servicio lo
        hashea con HMAC-SHA256 antes de persistir, usando
        ``settings.REFRESH_HASH_SECRET``. Este validator delega en
        ``_validar_hex64_opcional`` y después fuerza no-nulo porque
        ``token_hash`` sí es obligatorio (aunque el helper admite ``None``
        por diseño para reutilizarlo desde otros campos opcionales).

        Args:
            key: nombre del atributo.
            valor: hash SHA-256 hexadecimal.

        Returns:
            Hash en minúsculas.

        Raises:
            AppValidationError: ``TOKEN_HASH_MUST_BE_STRING`` si no es cadena.
            AppValidationError: ``TOKEN_HASH_INVALID`` si no coincide con el patrón hex64.
            AppValidationError: ``TOKEN_HASH_REQUIRED`` si llega ``None``.
        """
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
        """Normaliza a UTC las columnas temporales y exige ``expira_en`` presente.

        Cubre ``creada_en``, ``ultimo_uso_en``, ``expira_en`` y
        ``revocada_en``. El único obligatorio es ``expira_en``: sin fecha
        de expiración el token sería válido para siempre, lo cual es
        negado por diseño de seguridad. Los demás pueden ser ``None``
        (``ultimo_uso_en`` hasta el primer uso, ``revocada_en`` mientras
        siga vivo).

        Args:
            key: nombre del atributo.
            valor: ``datetime`` o ``None``.

        Returns:
            ``datetime`` en UTC, o ``None`` para las columnas opcionales.

        Raises:
            AppValidationError: ``EXPIRES_AT_REQUIRED`` si ``key == 'expira_en'`` y ``valor is None``.
        """
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
