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
    create_async_engine,
    AsyncSession,
    async_sessionmaker,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, validates

from config import settings
from domain.enums import ProvinciaEspaña, GeneroUsuario, TipoActividad
from utils import validators


# =========================================================
# Conexión a base de datos
# =========================================================

# Escapamos usuario y password por seguridad si contienen caracteres especiales.
user_safe = quote_plus(settings.DB_USER)
pass_safe = quote_plus(settings.DB_PASSWORD)

DATABASE_URL = (
    f"postgresql+asyncpg://{user_safe}:{pass_safe}"
    f"@{settings.DB_HOST}:{settings.DB_PORT}/{settings.DB_NAME}"
)

# Engine async con pool configurable desde .env
engine = create_async_engine(
    DATABASE_URL,
    pool_pre_ping=True,
    pool_size=int(settings.DB_POOL_SIZE),
    max_overflow=int(settings.DB_MAX_OVERFLOW),
    pool_timeout=int(settings.DB_POOL_TIMEOUT),
    pool_recycle=int(settings.DB_POOL_RECYCLE),
)

# Factory de sesiones async
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
    return v.replace(tzinfo=timezone.utc) if v.tzinfo is None else v.astimezone(timezone.utc)


def _sql_quote(value: str) -> str:
    """Escapa un string para incrustarlo de forma segura en un CheckConstraint SQL."""
    return "'" + value.replace("'", "''") + "'"


def _sql_in_values(values: set[str]) -> str:
    """Convierte un set de valores a una lista SQL: 'A', 'B', 'C'."""
    return ", ".join(_sql_quote(v) for v in sorted(values))


def _build_enum_check_sql(column_name: str, values: set[str], allow_null: bool = True) -> str:
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
        raise ValueError(f"Error: {nombre_campo} debe ser un texto válido")

    valor = valor.strip()
    if valor not in permitidos:
        raise ValueError(f"Error: {nombre_campo} no es válido")

    return valor


def _validar_hex64_opcional(valor: Optional[str], nombre_campo: str) -> Optional[str]:
    """Valida un hash hexadecimal SHA-256 de 64 caracteres."""
    if valor is None:
        return None

    if not isinstance(valor, str):
        raise ValueError(f"Error: {nombre_campo} debe ser un string")

    valor = valor.strip()
    if not _HEX64_RE.fullmatch(valor):
        raise ValueError(
            f"Error: {nombre_campo} debe ser un hash SHA-256 hexadecimal de 64 caracteres"
        )

    return valor.lower()


def _validar_texto_no_vacio(valor: str, nombre_campo: str, max_len: int) -> str:
    """Valida que un texto no esté vacío y no supere una longitud máxima."""
    if not isinstance(valor, str):
        raise ValueError(f"Error: {nombre_campo} debe ser un string")

    valor = valor.strip()
    if not valor:
        raise ValueError(f"Error: {nombre_campo} no puede estar vacío")
    if len(valor) > max_len:
        raise ValueError(f"Error: {nombre_campo} no puede superar los {max_len} caracteres")

    return valor


def _validar_url_http_opcional(valor: Optional[str], nombre_campo: str, max_len: int = 2048) -> Optional[str]:
    """
    Valida una URL http/https opcional.

    Se usa el mismo criterio fuerte que en Pydantic con AnyHttpUrl.
    """
    if valor is None:
        return None

    if not isinstance(valor, str):
        raise ValueError(f"Error: {nombre_campo} debe ser un texto")

    valor = valor.strip()
    if not valor:
        return None

    if len(valor) > max_len:
        raise ValueError(f"Error: {nombre_campo} no puede superar los {max_len} caracteres")

    try:
        parsed = _HTTP_URL_ADAPTER.validate_python(valor)
    except PydanticValidationError:
        raise ValueError(f"Error: {nombre_campo} no es una URL http/https válida")

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
        Index("uq_usuarios_nombre_usuario_lower", func.lower(nombre_usuario), unique=True),
        Index("uq_usuarios_email_lower", func.lower(email), unique=True),

        # Longitud y formato del username
        CheckConstraint("char_length(nombre_usuario) BETWEEN 5 AND 50", name="ck_usuarios_nombre_usuario_len"),
        CheckConstraint("nombre_usuario ~ '^[A-Za-z0-9]+$'", name="ck_usuarios_nombre_usuario_alnum"),

        # Email: saneado básico a nivel SQL
        # Nota: la validación fuerte real sigue en Python con email_validator.
        CheckConstraint("char_length(email) BETWEEN 3 AND 320", name="ck_usuarios_email_len"),
        CheckConstraint("email = lower(btrim(email))", name="ck_usuarios_email_normalized_lower"),
        CheckConstraint("email !~ '[[:space:]]'", name="ck_usuarios_email_no_spaces"),
        CheckConstraint(
            r"email ~ '^[^@[:space:]]+@[^@[:space:]]+\.[^@[:space:]]+$'",
            name="ck_usuarios_email_basic_format",
        ),

        # password hash no vacío
        CheckConstraint("char_length(btrim(password_encriptada)) > 0", name="ck_usuarios_password_hash_non_empty"),

        # nombre real, si viene, no puede ser vacío ni exceder 80
        CheckConstraint(
            "nombre_real IS NULL OR char_length(btrim(nombre_real)) BETWEEN 3 AND 80",
            name="ck_usuarios_nombre_real_len",
        ),

        # Edad mínima y evitar fechas futuras
        CheckConstraint("fecha_nacimiento <= CURRENT_DATE", name="ck_usuarios_fecha_nacimiento_not_future"),
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
        CheckConstraint("altura IS NULL OR (altura BETWEEN 50 AND 300)", name="ck_usuarios_altura_range"),
        CheckConstraint("peso IS NULL OR (peso BETWEEN 20 AND 300)", name="ck_usuarios_peso_range"),

        # Imagen y acumulados
        CheckConstraint("foto_perfil IS NULL OR char_length(btrim(foto_perfil)) BETWEEN 1 AND 500", name="ck_usuarios_foto_perfil_len"),
        CheckConstraint("total_metros >= 0", name="ck_usuarios_total_metros_non_negative"),

        # Términos: si el usuario existe en tabla, deben estar aceptados
        CheckConstraint("acepta_terminos IS TRUE", name="ck_usuarios_acepta_terminos_true"),
        CheckConstraint("char_length(btrim(version_terminos)) BETWEEN 1 AND 10", name="ck_usuarios_version_terminos_len"),

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
            raise ValueError("Error: El nombre de usuario debe ser un texto")

        valor = valor.strip()

        if len(valor) < 5:
            raise ValueError("Error: El nombre de usuario debe tener al menos 5 caracteres")
        if len(valor) > 50:
            raise ValueError("Error: El nombre de usuario no puede superar los 50 caracteres")
        if not _USERNAME_RE.fullmatch(valor):
            raise ValueError("Error: El nombre de usuario solo puede contener letras y números")

        return valor

    @validates("email")
    def validar_email(self, key: str, valor: str) -> str:
        if not isinstance(valor, str):
            raise ValueError("Error: El email debe ser un texto")

        valor = valor.strip().lower()
        if not valor:
            raise ValueError("Error: El email es obligatorio")

        try:
            email_info = validate_email(valor, check_deliverability=False)
            return email_info.normalized.lower()
        except EmailNotValidError:
            raise ValueError("Error: El formato del correo electrónico no es válido")

    @validates("password_encriptada")
    def validar_password_encriptada(self, key: str, valor: str) -> str:
        return _validar_texto_no_vacio(valor, "La contraseña encriptada", 255)

    @validates("nombre_real")
    def validar_nombre_real(self, key: str, valor: Optional[str]) -> Optional[str]:
        if valor is None:
            return None
        if not isinstance(valor, str):
            raise ValueError("Error: El nombre real debe ser un texto")

        valor = valor.strip()
        return validators.validar_nombre_real_logica(valor)

    @validates("fecha_nacimiento")
    def validar_fecha_nacimiento(self, key: str, valor: date) -> date:
        if not isinstance(valor, date):
            raise ValueError("Error: La fecha de nacimiento debe ser una fecha válida")
        return validators.validar_fecha_nacimiento_logica(valor)

    @validates("genero")
    def validar_genero(self, key: str, valor: Optional[Any]) -> Optional[str]:
        return _validar_enum_str(valor, VALID_GENEROS, "El género")

    @validates("altura")
    def validar_altura(self, key: str, valor: Optional[int]) -> Optional[int]:
        if valor is None:
            return None
        if not isinstance(valor, int):
            raise ValueError("Error: La altura debe ser un número entero en centímetros")
        return validators.validar_altura_logica(valor)

    @validates("peso")
    def validar_peso(self, key: str, valor: Optional[float]) -> Optional[float]:
        if valor is None:
            return None
        if not isinstance(valor, (int, float)):
            raise ValueError("Error: El peso debe ser un número en kilos")
        return validators.validar_peso_logica(float(valor))

    @validates("provincia")
    def validar_provincia(self, key: str, valor: Optional[Any]) -> Optional[str]:
        return _validar_enum_str(valor, VALID_PROVINCIAS, "La provincia")

    @validates("foto_perfil")
    def validar_foto_perfil(self, key: str, valor: Optional[str]) -> Optional[str]:
        if valor is None:
            return None
        return _validar_texto_no_vacio(valor, "La foto de perfil", 500)

    @validates("foto_fecha_actualizacion", "fecha_registro", "codigo_expiracion")
    def validar_fechas_auxiliares(self, key: str, valor: Optional[datetime]) -> Optional[datetime]:
        return _normalizar_datetime_utc(valor)

    @validates("fecha_eula")
    def validar_fecha_eula(self, key: str, valor: datetime) -> datetime:
        if not isinstance(valor, datetime):
            raise ValueError("Error: La fecha de aceptación debe ser una fecha-hora válida")

        valor_utc = _normalizar_datetime_utc(valor)
        assert valor_utc is not None

        # Misma lógica de schemas.py: margen pequeño para evitar falsos positivos por reloj.
        ahora = _ahora_utc()
        if valor_utc > ahora + timedelta(minutes=5):
            raise ValueError("Error: La fecha de aceptación no puede ser futura")

        return valor_utc

    @validates("total_metros")
    def validar_total_metros(self, key: str, valor: int) -> int:
        if not isinstance(valor, int):
            raise ValueError("Error: El total de metros debe ser un número entero")
        if valor < 0:
            raise ValueError("Error: El total de metros no puede ser negativo")
        return valor

    @validates("acepta_terminos")
    def validar_acepta_terminos(self, key: str, valor: bool) -> bool:
        if not isinstance(valor, bool):
            raise ValueError("Error: acepta_terminos debe ser booleano")
        if valor is not True:
            raise ValueError("Error: Debes aceptar los términos para crear un usuario")
        return valor

    @validates("perfil_visible")
    def validar_perfil_visible(self, key: str, valor: bool) -> bool:
        if not isinstance(valor, bool):
            raise ValueError("Error: perfil_visible debe ser booleano")
        return valor

    @validates("version_terminos")
    def validar_version_terminos(self, key: str, valor: str) -> str:
        if not isinstance(valor, str):
            raise ValueError("Error: La versión de términos debe ser un texto")

        valor = valor.strip()
        if not valor:
            raise ValueError("Error: La versión de los términos es obligatoria")
        if len(valor) > 10:
            raise ValueError("Error: La versión de los términos no puede superar los 10 caracteres")

        return valor

    @validates("codigo_recuperacion")
    def validar_codigo_recuperacion(self, key: str, valor: Optional[str]) -> Optional[str]:
        return _validar_hex64_opcional(valor, "codigo_recuperacion")


# =========================================================
# Modelo Actividad
# =========================================================

class Actividad(Base):
    """
    Tabla de actividades deportivas.

    Se persiste el tipo como String para mantener compatibilidad con los servicios
    actuales, pero el valor queda restringido por enum compartido y por checks SQL.
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
    duracion: Mapped[int] = mapped_column(Integer, nullable=False)
    calorias_quemadas: Mapped[int] = mapped_column(Integer, nullable=False)

    # La polilínea puede ser larga; por eso se deja en Text
    ruta_polilinea: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # La URL sí tiene un límite real en el schema: 2048
    ruta_mapa_url: Mapped[Optional[str]] = mapped_column(String(2048), nullable=True)

    fecha_ruta: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=_ahora_utc,
        server_default=text("CURRENT_TIMESTAMP"),
        index=True,
    )

    __table_args__ = (
        # Enum compartido
        CheckConstraint(
            _build_enum_check_sql("tipo", VALID_TIPOS_ACTIVIDAD, allow_null=False),
            name="ck_actividades_tipo_values",
        ),

        # Reglas de negocio de actividad
        CheckConstraint("distancia > 0 AND distancia <= 300000", name="ck_actividades_distancia_range"),
        CheckConstraint("duracion > 0 AND duracion <= 86400", name="ck_actividades_duracion_range"),
        CheckConstraint("calorias_quemadas > 0 AND calorias_quemadas <= 10000", name="ck_actividades_calorias_range"),

        # Ruta opcional
        CheckConstraint(
            "ruta_polilinea IS NULL OR char_length(ruta_polilinea) >= 5",
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

        # Índice útil para recuperar actividades por usuario y fecha
        Index("ix_actividades_usuario_fecha", "usuario_id", "fecha_ruta", "id"),
    )

    @validates("usuario_id")
    def validar_usuario_id(self, key: str, valor: int) -> int:
        if not isinstance(valor, int):
            raise ValueError("Error: usuario_id debe ser un entero")
        if valor <= 0:
            raise ValueError("Error: usuario_id debe ser mayor a 0")
        return valor

    @validates("tipo")
    def validar_tipo(self, key: str, valor: Optional[Any]) -> str:
        resultado = _validar_enum_str(valor, VALID_TIPOS_ACTIVIDAD, "El tipo de actividad")
        if resultado is None:
            raise ValueError("Error: El tipo de actividad es obligatorio")
        return resultado

    @validates("distancia")
    def validar_distancia(self, key: str, valor: int) -> int:
        if not isinstance(valor, int):
            raise ValueError("Error: La distancia debe ser un número entero")
        return validators.validar_distancia_logica(valor)

    @validates("duracion")
    def validar_duracion(self, key: str, valor: int) -> int:
        if not isinstance(valor, int):
            raise ValueError("Error: La duración debe ser un número entero")
        return validators.validar_duracion_logica(valor)

    @validates("calorias_quemadas")
    def validar_calorias(self, key: str, valor: int) -> int:
        if not isinstance(valor, int):
            raise ValueError("Error: Las calorías deben ser un número entero")
        return validators.validar_calorias_logica(valor)

    @validates("ruta_polilinea")
    def validar_ruta_polilinea(self, key: str, valor: Optional[str]) -> Optional[str]:
        if valor == "":
            return None
        if valor is None:
            return None
        if not isinstance(valor, str):
            raise ValueError("Error: La polilínea debe ser un texto")
        return validators.validar_polilinea_logica(valor)

    @validates("ruta_mapa_url")
    def validar_ruta_mapa_url(self, key: str, valor: Optional[str]) -> Optional[str]:
        return _validar_url_http_opcional(valor, "La URL del mapa", 2048)

    @validates("fecha_ruta")
    def validar_fecha_ruta(self, key: str, valor: datetime) -> datetime:
        if not isinstance(valor, datetime):
            raise ValueError("Error: fecha_ruta debe ser una fecha-hora válida")
        return validators.validar_fecha_ruta_logica(valor)


# =========================================================
# Modelo SesionRefresh
# =========================================================

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
    jti: Mapped[str] = mapped_column(String(64), nullable=False, unique=True, index=True)
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
        CheckConstraint("char_length(btrim(jti)) BETWEEN 1 AND 64", name="ck_sesiones_refresh_jti_non_empty"),
        CheckConstraint("char_length(btrim(familia_id)) BETWEEN 1 AND 64", name="ck_sesiones_refresh_familia_non_empty"),
        CheckConstraint(
            "token_hash ~* '^[0-9a-f]{64}$'",
            name="ck_sesiones_refresh_token_hash_hex64",
        ),
        CheckConstraint(
            "reemplazada_por_jti IS NULL OR char_length(btrim(reemplazada_por_jti)) BETWEEN 1 AND 64",
            name="ck_sesiones_refresh_reemplazada_por_jti_len",
        ),
        CheckConstraint("expira_en >= creada_en", name="ck_sesiones_refresh_expira_ge_creada"),
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
            raise ValueError("Error: usuario_id debe ser un entero")
        if valor <= 0:
            raise ValueError("Error: usuario_id debe ser mayor a 0")
        return valor

    @validates("jti", "familia_id", "reemplazada_por_jti")
    def validar_ids_sesion(self, key: str, valor: Optional[str]) -> Optional[str]:
        if valor is None:
            return None
        return _validar_texto_no_vacio(valor, key, 64)

    @validates("token_hash")
    def validar_token_hash(self, key: str, valor: str) -> str:
        resultado = _validar_hex64_opcional(valor, "token_hash")
        if resultado is None:
            raise ValueError("Error: token_hash es obligatorio")
        return resultado

    @validates("creada_en", "ultimo_uso_en", "expira_en", "revocada_en")
    def validar_fechas(self, key: str, valor: Optional[datetime]) -> Optional[datetime]:
        valor = _normalizar_datetime_utc(valor)

        if key == "expira_en" and valor is None:
            raise ValueError("Error: expira_en es obligatorio")

        return valor


# =========================================================
# Inicialización y dependencias
# =========================================================

async def init_db() -> None:
    """
    Crea las tablas si AUTO_CREATE_TABLES=true.

    En producción, si usas Alembic, lo habitual es dejar esto desactivado
    y aplicar las migraciones manualmente.
    """
    if not settings.AUTO_CREATE_TABLES:
        return

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


async def close_db() -> None:
    """Cierra el engine async de SQLAlchemy."""
    await engine.dispose()


async def obtener_db() -> AsyncGenerator[AsyncSession, None]:
    """
    Dependencia de FastAPI para inyectar una sesión async.
    """
    async with AsyncSessionLocal() as db:
        yield db
        