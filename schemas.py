# schemas.py

"""
Esquemas de Validación de Datos (Pydantic V2).

Define la estructura de los datos que entran y salen de la API,
asegurando que cumplan con las reglas de negocio antes de tocar la DB.
"""
from pydantic import (
    BaseModel,
    EmailStr,
    Field,
    field_validator,
    model_validator,
    StrictInt,
    ConfigDict,
    AnyHttpUrl,
)
from datetime import date, datetime
from enum import Enum
from typing import Optional, Any, List
import re
from utils import validators
from exceptions import AppValidationError
from domain.enums import ProvinciaEspaña, GeneroUsuario, TipoActividad


class RespuestaHandshake(BaseModel):
    """Esquema para la respuesta del handshake inicial."""

    app_session_token: str


class Registro(BaseModel):
    """
    Esquema para validar los campos en el registro de un nuevo usuario.
    """

    nombre_usuario: str = Field(..., min_length=5, max_length=50)
    email: EmailStr
    password: str = Field(...)
    nombre_real: Optional[str] = None
    fecha_nacimiento: date
    genero: Optional[GeneroUsuario] = None
    altura: Optional[int] = None
    peso: Optional[float] = None
    provincia: Optional[ProvinciaEspaña] = None
    perfil_visible: bool = Field(default=True)
    acepta_terminos: bool = Field(...)
    fecha_aceptacion_terminos: datetime = Field(...)
    version_terminos: str = Field(..., max_length=10)

    @model_validator(mode="before")
    @classmethod
    def validar_campos_requeridos_registro(cls, values: Any) -> Any:
        """Revisa que se reciban todos los campos obligatorios."""
        # Valida campos requeridos registro.
        if isinstance(values, dict):
            if "nombre_usuario" not in values or not values["nombre_usuario"]:
                raise AppValidationError(
                    "Error: El nombre de usuario es obligatorio", "USERNAME_REQUIRED"
                )
            if "email" not in values or not values["email"]:
                raise AppValidationError(
                    "Error: El email es obligatorio", "EMAIL_REQUIRED"
                )
            if "password" not in values or not values["password"]:
                raise AppValidationError(
                    "Error: La contraseña es obligatoria", "PASSWORD_REQUIRED"
                )
            if "fecha_nacimiento" not in values:
                raise AppValidationError(
                    "Error: La fecha de nacimiento es obligatoria",
                    "BIRTH_DATE_REQUIRED",
                )
        return values

    @field_validator("nombre_usuario")
    @classmethod
    def validar_nombre_usuario(cls, valor: str) -> str:
        # Quitar espacios.
        """Valida nombre usuario."""
        valor = valor.strip()
        # Validación de longitud mínima.
        if len(valor) < 5:
            raise AppValidationError(
                "Error: El nombre de usuario debe tener al menos 5 caracteres",
                "USERNAME_TOO_SHORT",
            )

        if len(valor) > 50:  # ✅ añadido
            raise AppValidationError(
                "Error: El nombre de usuario no puede superar los 50 caracteres",
                "USERNAME_TOO_LONG",
            )
        # Validación formato alfanumérico sin espacios.
        if not re.match("^[a-zA-Z0-9]*$", valor):
            raise AppValidationError(
                "Error: El nombre de usuario solo puede contener letras y números",
                "USERNAME_INVALID_FORMAT",
            )
        return valor

    @field_validator("nombre_real")
    @classmethod
    def validar_nombre_real_registro(cls, v):
        """Valida nombre real registro."""
        if v is None:
            return v
        v = v.strip()
        return validators.validar_nombre_real_logica(v)

    @field_validator("email", mode="before")
    @classmethod
    def validar_email_registro(cls, valor: Any) -> Any:
        """Convierte el email a minúsculas antes de procesar."""
        if isinstance(valor, str):
            return valor.lower().strip()
        return valor

    @field_validator("email", mode="wrap")
    @classmethod
    def validar_email_registro_custom(cls, v, handler):
        """Intercepta el error de EmailStr para devolver un mensaje en el formato estandar."""
        return validators.interceptar_error_pydantic(
            v,
            handler,
            "EMAIL_FORMAT_INVALID",
            "Error: El formato del correo electrónico no es válido",
        )

    @field_validator("password")
    @classmethod
    def validar_password_registro(cls, v):
        """Valida password registro."""
        return validators.validar_password_logica(v)

    @field_validator("fecha_nacimiento", mode="wrap")
    @classmethod
    def validar_fecha_nacimiento_registro_custom(cls, v, handler):
        """Intercepta el formato de fecha para devolver un mensaje en el formato estandar."""
        return validators.interceptar_error_pydantic(
            v,
            handler,
            "VALIDATION_ERROR",
            "Error: La fecha debe tener formato AAAA-MM-DD",
        )

    @field_validator("fecha_nacimiento")
    @classmethod
    def validar_fecha_nacimiento_registro(cls, v):
        """Valida fecha nacimiento registro."""
        return validators.validar_fecha_nacimiento_logica(v)

    @field_validator("genero", mode="wrap")
    @classmethod
    def validar_genero_registro_custom(cls, v, handler):
        """Intercepta el genero para devolver un mensaje en el formato estandar."""
        return validators.interceptar_error_pydantic(
            v, handler, "VALIDATION_ERROR", "Error: El género seleccionado no es válido"
        )

    @field_validator("altura", mode="wrap")
    @classmethod
    def validar_altura_registro_custom(cls, v, handler):
        """Intercepta la altura para devolver un mensaje en el formato estandar."""
        return validators.interceptar_error_pydantic(
            v,
            handler,
            "VALIDATION_ERROR",
            "Error: La altura debe ser un número entero en centimetros",
        )

    @field_validator("altura")
    @classmethod
    def validar_altura_registro(cls, v):
        """Valida altura registro."""
        return validators.validar_altura_logica(v)

    @field_validator("peso", mode="wrap")
    @classmethod
    def validar_peso_registro_custom(cls, v, handler):
        """Intercepta el peso para devolver un mensaje en el formato estandar."""
        return validators.interceptar_error_pydantic(
            v,
            handler,
            "WEIGHT_MUST_BE_KILOGRAM_NUMBER",
            "Error: El peso debe ser un número en kilos",
        )

    @field_validator("peso")
    @classmethod
    def validar_peso_registro(cls, v):
        """Valida peso registro."""
        return validators.validar_peso_logica(v)

    @field_validator("provincia", mode="wrap")
    @classmethod
    def validar_provincia_registro_custom(cls, v, handler):
        """Intercepta el error de Enum para devolver un mensaje en el formato estandar."""
        return validators.interceptar_error_pydantic(
            v,
            handler,
            "VALIDATION_ERROR",
            "Error: La ubicación seleccionada no es válida",
        )

    @field_validator("perfil_visible", mode="wrap")
    @classmethod
    def validar_perfil_visible_registro_custom(cls, v, handler):
        """Intercepta sino llega un boolean para devolver un mensaje en el formato estandar."""
        return validators.interceptar_error_pydantic(
            v,
            handler,
            "VALIDATION_ERROR",
            "Error: El formato de perfil visible no es válido",
        )

    @field_validator("acepta_terminos")
    @classmethod
    def validar_acepta_terminos(cls, v: bool) -> bool:
        """Valida acepta terminos."""
        if not v:
            raise AppValidationError(
                "Error: Debes aceptar los Términos y la Política de Privacidad para registrarte",
                "REGISTRATION_CONSENTS_REQUIRED",
            )
        return v

    @field_validator("fecha_aceptacion_terminos", mode="wrap")
    @classmethod
    def validar_fecha_aceptacion_terminos_custom(cls, v, handler):
        """Valida fecha aceptacion terminos custom."""
        return validators.interceptar_error_pydantic(
            v,
            handler,
            "VALIDATION_ERROR",
            "Error: La fecha de aceptación debe tener formato ISO-8601",
        )

    @field_validator("fecha_aceptacion_terminos")
    @classmethod
    def validar_fecha_aceptacion_terminos(cls, v: datetime) -> datetime:
        """Valida fecha aceptacion terminos."""
        from datetime import timedelta, timezone

        ahora = datetime.now(timezone.utc)
        v_utc = v if v.tzinfo else v.replace(tzinfo=timezone.utc)
        if v_utc > ahora + timedelta(minutes=5):
            raise AppValidationError(
                "Error: La fecha de aceptación no puede ser futura",
                "TERMS_ACCEPTED_AT_IN_FUTURE",
            )
        return v_utc

    @field_validator("version_terminos")
    @classmethod
    def validar_version_terminos(cls, v: str) -> str:
        """Valida version terminos."""
        v = v.strip()
        if not v:
            raise AppValidationError(
                "Error: La versión de los términos es obligatoria",
                "TERMS_VERSION_REQUIRED",
            )
        return v


class RespuestaRegistro(BaseModel):
    """Representa respuesta registro."""

    estatus: str
    mensaje: str
    nombre_usuario: str


class ProveedorAuthSocial(str, Enum):
    """Representa proveedor autenticación social."""

    GOOGLE = "google"


class LoginSocial(BaseModel):
    """Representa login social."""

    provider: ProveedorAuthSocial
    token: str

    @model_validator(mode="before")
    @classmethod
    def validar_campos_requeridos_login_social(cls, values: Any) -> Any:
        """Valida campos requeridos login social."""
        if isinstance(values, dict):
            if "provider" not in values or not values["provider"]:
                raise AppValidationError(
                    "Error: El proveedor social es obligatorio",
                    "SOCIAL_PROVIDER_REQUIRED",
                )
            if "token" not in values or not values["token"]:
                raise AppValidationError(
                    "Error: El token social es obligatorio",
                    "SOCIAL_TOKEN_REQUIRED",
                )
        return values

    @field_validator("token", mode="before")
    @classmethod
    def limpiar_token_social(cls, valor: Any) -> Any:
        """Normaliza token social."""
        if isinstance(valor, str):
            valor_limpio = valor.strip()
            if not valor_limpio:
                raise AppValidationError(
                    "Error: El token social no puede estar vacío",
                    "SOCIAL_TOKEN_EMPTY",
                )
            return valor_limpio
        return valor


class RegistroSocial(BaseModel):
    """Representa registro social."""

    provider: ProveedorAuthSocial
    token: str
    nombre_usuario: str = Field(..., min_length=5, max_length=50)
    fecha_nacimiento: date
    perfil_visible: bool = Field(default=True)
    acepta_terminos: bool = Field(...)
    fecha_aceptacion_terminos: datetime = Field(...)
    version_terminos: str = Field(..., max_length=10)

    @model_validator(mode="before")
    @classmethod
    def validar_campos_requeridos_registro_social(cls, values: Any) -> Any:
        """Valida campos requeridos registro social."""
        # Valida campos requeridos registro social.
        if isinstance(values, dict):
            if "provider" not in values or not values["provider"]:
                raise AppValidationError(
                    "Error: El proveedor social es obligatorio",
                    "SOCIAL_PROVIDER_REQUIRED",
                )
            if "token" not in values or not values["token"]:
                raise AppValidationError(
                    "Error: El token social es obligatorio",
                    "SOCIAL_TOKEN_REQUIRED",
                )
            if "nombre_usuario" not in values or not values["nombre_usuario"]:
                raise AppValidationError(
                    "Error: El nombre de usuario es obligatorio",
                    "USERNAME_REQUIRED",
                )
            if "fecha_nacimiento" not in values:
                raise AppValidationError(
                    "Error: La fecha de nacimiento es obligatoria",
                    "BIRTH_DATE_REQUIRED",
                )
        return values

    @field_validator("token", mode="before")
    @classmethod
    def limpiar_token_registro_social(cls, valor: Any) -> Any:
        """Normaliza token registro social."""
        if isinstance(valor, str):
            valor_limpio = valor.strip()
            if not valor_limpio:
                raise AppValidationError(
                    "Error: El token social no puede estar vacío",
                    "SOCIAL_TOKEN_EMPTY",
                )
            return valor_limpio
        return valor

    @field_validator("nombre_usuario")
    @classmethod
    def validar_nombre_usuario_social(cls, valor: str) -> str:
        """Valida nombre usuario social."""
        # Valida nombre usuario social.
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
        if not re.match("^[a-zA-Z0-9]*$", valor):
            raise AppValidationError(
                "Error: El nombre de usuario solo puede contener letras y números",
                "USERNAME_INVALID_FORMAT",
            )
        return valor

    @field_validator("fecha_nacimiento", mode="wrap")
    @classmethod
    def validar_fecha_nacimiento_social_custom(cls, v, handler):
        """Valida fecha nacimiento social custom."""
        return validators.interceptar_error_pydantic(
            v,
            handler,
            "VALIDATION_ERROR",
            "Error: La fecha debe tener formato AAAA-MM-DD",
        )

    @field_validator("fecha_nacimiento")
    @classmethod
    def validar_fecha_nacimiento_social(cls, v):
        """Valida fecha nacimiento social."""
        return validators.validar_fecha_nacimiento_logica(v)

    @field_validator("perfil_visible", mode="wrap")
    @classmethod
    def validar_perfil_visible_social_custom(cls, v, handler):
        """Valida perfil visible social custom."""
        return validators.interceptar_error_pydantic(
            v,
            handler,
            "VALIDATION_ERROR",
            "Error: El formato de perfil visible no es válido",
        )

    @field_validator("acepta_terminos")
    @classmethod
    def validar_acepta_terminos_social(cls, v: bool) -> bool:
        """Valida acepta terminos social."""
        if not v:
            raise AppValidationError(
                "Error: Debes aceptar los Términos y la Política de Privacidad para registrarte",
                "REGISTRATION_CONSENTS_REQUIRED",
            )
        return v

    @field_validator("fecha_aceptacion_terminos", mode="wrap")
    @classmethod
    def validar_fecha_aceptacion_terminos_social_custom(cls, v, handler):
        """Valida fecha aceptacion terminos social custom."""
        return validators.interceptar_error_pydantic(
            v,
            handler,
            "VALIDATION_ERROR",
            "Error: La fecha de aceptación debe tener formato ISO-8601",
        )

    @field_validator("fecha_aceptacion_terminos")
    @classmethod
    def validar_fecha_aceptacion_terminos_social(cls, v: datetime) -> datetime:
        """Valida fecha aceptacion terminos social."""
        from datetime import timedelta, timezone

        ahora = datetime.now(timezone.utc)
        v_utc = v if v.tzinfo else v.replace(tzinfo=timezone.utc)
        if v_utc > ahora + timedelta(minutes=5):
            raise AppValidationError(
                "Error: La fecha de aceptación no puede ser futura",
                "TERMS_ACCEPTED_AT_IN_FUTURE",
            )
        return v_utc

    @field_validator("version_terminos")
    @classmethod
    def validar_version_terminos_social(cls, v: str) -> str:
        """Valida version terminos social."""
        v = v.strip()
        if not v:
            raise AppValidationError(
                "Error: La versión de los términos es obligatoria",
                "TERMS_VERSION_REQUIRED",
            )
        return v


class Login(BaseModel):
    """Esquema para validar las credenciales en el inicio de sesión."""

    identificador: str
    password: str

    @model_validator(mode="before")
    @classmethod
    def validar_campos_requeridos_login(cls, values: Any) -> Any:
        """Revisa que se reciban todos los campos obligatorios."""
        if isinstance(values, dict):
            if "identificador" not in values or not values["identificador"]:
                raise AppValidationError(
                    "Error: El identificador es obligatorio", "IDENTIFIER_REQUIRED"
                )
            if "password" not in values or not values["password"]:
                raise AppValidationError(
                    "Error: La contraseña es obligatoria", "PASSWORD_REQUIRED"
                )
        return values

    @field_validator("identificador", mode="before")
    @classmethod
    def limpiar_identificador(cls, valor: Any) -> Any:
        """Normaliza identificador."""
        if isinstance(valor, str):
            # Quitar espacios.
            valor_limpio = valor.strip()
            if not valor_limpio:
                raise AppValidationError(
                    "Error: El identificador no puede estar vacío", "IDENTIFIER_EMPTY"
                )
            return valor_limpio
        return valor


class RespuestaLogin(BaseModel):
    """Representa respuesta login."""

    estatus: str
    nombre_usuario: str
    token_acceso: str
    refresh_token: str


class SolicitudRefreshToken(BaseModel):
    """Representa solicitud refresco token."""

    refresh_token: str = Field(...)

    @model_validator(mode="before")
    @classmethod
    def validar_campos_requeridos_refresh(cls, values: Any) -> Any:
        """Valida campos requeridos refresco."""
        if isinstance(values, dict):
            if "refresh_token" not in values or not values["refresh_token"]:
                raise AppValidationError(
                    "Error: El refresh token es obligatorio", "REFRESH_TOKEN_REQUIRED"
                )
        return values

    @field_validator("refresh_token", mode="before")
    @classmethod
    def limpiar_refresh_token(cls, valor: Any) -> Any:
        """Normaliza refresco token."""
        if isinstance(valor, str):
            valor_limpio = valor.strip()
            if not valor_limpio:
                raise AppValidationError(
                    "Error: El refresh token no puede estar vacío",
                    "REFRESH_TOKEN_EMPTY",
                )
            return valor_limpio
        return valor


class RespuestaRefreshToken(BaseModel):
    """Representa respuesta refresco token."""

    estatus: str
    nombre_usuario: str
    token_acceso: str
    refresh_token: str


class SolicitudLogout(SolicitudRefreshToken):
    """Recibe el refresh token para revocar la sesión actual."""

    pass


class RespuestaInformacionPerfil(BaseModel):
    """Representa respuesta informacion perfil."""

    model_config = ConfigDict(from_attributes=True)

    nombre_usuario: str
    nombre_real: Optional[str] = None
    email: EmailStr
    fecha_nacimiento: date
    genero: Optional[str] = None
    altura: Optional[int] = None
    peso: Optional[float] = None
    provincia: Optional[str] = None
    foto_perfil: Optional[str] = None
    foto_version: int = 0
    perfil_visible: bool
    total_puntos: int
    total_calorias: int = 0
    total_calorias: int = 0
    total_duracion_segundos: int = 0
    total_actividades: int = 0
    objetivo_semanal_metros: int = 50000
    objetivo_semanal_metros: int = 50000
    objetivo_mensual_metros: int = 150000


class ActualizarPerfil(BaseModel):
    """Esquema para actualizaciones del perfil de usuario."""

    nombre_real: Optional[str] = None
    email: Optional[EmailStr] = None
    password: Optional[str] = None
    fecha_nacimiento: Optional[date] = None
    genero: Optional[GeneroUsuario] = None
    altura: Optional[int] = None
    peso: Optional[float] = None
    provincia: Optional[ProvinciaEspaña] = None
    perfil_visible: Optional[bool] = None
    objetivo_semanal_metros: Optional[int] = None
    objetivo_mensual_metros: Optional[int] = None

    @field_validator("nombre_real")
    @classmethod
    def validar_nombre_real_actualizacion(cls, v):
        """Valida nombre real actualizacion."""
        if v is None:
            return v
        v = v.strip()
        return validators.validar_nombre_real_logica(v)

    @field_validator("email", mode="before")
    @classmethod
    def validar_email_actualizacion(cls, v):
        """Convierte el email a minúsculas antes de procesar."""
        if v is not None and isinstance(v, str):
            return v.lower().strip()
        return v

    @field_validator("email", mode="wrap")
    @classmethod
    def validar_email_actualizacion_custom(cls, v, handler):
        """Intercepta el error de EmailStr para devolver un mensaje en el formato estandar."""
        return validators.interceptar_error_pydantic(
            v,
            handler,
            "EMAIL_FORMAT_INVALID",
            "Error: El formato del correo electrónico no es válido",
        )

    @field_validator("password")
    @classmethod
    def validar_password_actualizacion(cls, v):
        """Valida password actualizacion."""
        return validators.validar_password_logica(v) if v is not None else v

    @field_validator("fecha_nacimiento", mode="wrap")
    @classmethod
    def validar_fecha_nacimiento_actualizacion_custom(cls, v, handler):
        """Intercepta el formato de fecha para devolver un mensaje en el formato estandar."""
        return validators.interceptar_error_pydantic(
            v,
            handler,
            "VALIDATION_ERROR",
            "Error: La fecha debe tener formato AAAA-MM-DD",
        )

    @field_validator("fecha_nacimiento")
    @classmethod
    def validar_fecha_nacimiento_actualizacion(cls, v):
        """Valida fecha nacimiento actualizacion."""
        return validators.validar_fecha_nacimiento_logica(v) if v is not None else v

    @field_validator("genero", mode="wrap")
    @classmethod
    def validar_genero_actualizacion_custom(cls, v, handler):
        """Intercepta el genero para devolver un mensaje en el formato estandar."""
        return validators.interceptar_error_pydantic(
            v, handler, "VALIDATION_ERROR", "Error: El género seleccionado no es válido"
        )

    @field_validator("altura", mode="wrap")
    @classmethod
    def validar_altura_actualizacion_custom(cls, v, handler):
        """Intercepta la altura para devolver un mensaje en el formato estandar."""
        return validators.interceptar_error_pydantic(
            v,
            handler,
            "VALIDATION_ERROR",
            "Error: La altura debe ser un número entero en cm",
        )

    @field_validator("altura")
    @classmethod
    def validar_altura_actualizacion(cls, v):
        """Valida altura actualizacion."""
        return validators.validar_altura_logica(v)

    @field_validator("peso", mode="wrap")
    @classmethod
    def validar_peso_actualizacion_custom(cls, v, handler):
        """Intercepta el peso para devolver un mensaje en el formato estandar."""
        return validators.interceptar_error_pydantic(
            v,
            handler,
            "WEIGHT_MUST_BE_KILOGRAM_NUMBER",
            "Error: El peso debe ser un número en kilos",
        )

    @field_validator("peso")
    @classmethod
    def validar_peso_actualizacion(cls, v):
        """Valida peso actualizacion."""
        return validators.validar_peso_logica(v)

    @field_validator("provincia", mode="wrap")
    @classmethod
    def validar_provincia_actualizacion_custom(cls, v, handler):
        """Intercepta el error de Enum para para devolver un mensaje en el formato estandar."""
        return validators.interceptar_error_pydantic(
            v,
            handler,
            "VALIDATION_ERROR",
            "Error: La ubicación seleccionada no es válida",
        )

    @field_validator("perfil_visible", mode="wrap")
    @classmethod
    def validar_perfil_visible_actualizacion_custom(cls, v, handler):
        """Intercepta sino llega un boolean para devolver un mensaje en el formato estandar."""
        return validators.interceptar_error_pydantic(
            v,
            handler,
            "VALIDATION_ERROR",
            "Error: El formato de perfil visible no es válido",
        )

    @field_validator("objetivo_semanal_metros")
    @classmethod
    def validar_objetivo_semanal(cls, v: Optional[int]) -> Optional[int]:
        """Valida objetivo semanal."""
        if v is None:
            return v
        if not isinstance(v, int):
            raise AppValidationError(
                "Error: El objetivo semanal debe ser un número entero en metros",
                "WEEKLY_GOAL_MUST_BE_INTEGER_METERS",
            )
        if not (10 <= v <= 2_000_000):
            raise AppValidationError(
                "Error: El objetivo semanal debe estar entre 10 y 2 000 000 metros",
                "WEEKLY_GOAL_OUT_OF_RANGE",
            )
        return v

    @field_validator("objetivo_mensual_metros")
    @classmethod
    def validar_objetivo_mensual(cls, v: Optional[int]) -> Optional[int]:
        """Valida objetivo mensual."""
        if v is None:
            return v
        if not isinstance(v, int):
            raise AppValidationError(
                "Error: El objetivo mensual debe ser un número entero en metros",
                "MONTHLY_GOAL_MUST_BE_INTEGER_METERS",
            )
        if not (10 <= v <= 2_000_000):
            raise AppValidationError(
                "Error: El objetivo mensual debe estar entre 10 y 2 000 000 metros",
                "MONTHLY_GOAL_OUT_OF_RANGE",
            )
        return v


class InformacionPerfilPublico(BaseModel):
    """
    Esquema reducido para ver el perfil de otro usuario.
    Oculta datos sensibles (email, peso, fecha nacimiento, etc).
    """

    nombre_usuario: str
    provincia: Optional[str] = None
    foto_perfil: Optional[str] = None
    foto_version: int = 0
    total_puntos: int


class BusquedaUsuario(BaseModel):
    """
    Esquema para resultados de la barra de búsqueda.
    """

    nombre_usuario: str
    foto_perfil: Optional[str] = None
    foto_version: int = 0


class RespuestaBusquedaUsuariosPaginada(BaseModel):
    """
    Esquema para resultados paginados de la barra de búsqueda.
    """

    items: List[BusquedaUsuario]
    total: int
    skip: int
    limit: int
    has_more: bool


class ReportePerfilInapropiado(BaseModel):
    """Representa reporte perfil inapropiado."""

    nombre_usuario_reportado: str = Field(..., min_length=1, max_length=50)
    reportar_nombre: bool = False
    reportar_foto: bool = False
    observaciones: Optional[str] = Field(default=None, max_length=500)

    @model_validator(mode="before")
    @classmethod
    def validar_campos_requeridos(cls, values: Any) -> Any:
        """Valida campos requeridos."""
        if isinstance(values, dict):
            if (
                "nombre_usuario_reportado" not in values
                or values["nombre_usuario_reportado"] is None
            ):
                raise AppValidationError(
                    "Error: El nombre de usuario reportado es obligatorio",
                    "REPORT_TARGET_USERNAME_REQUIRED",
                )
        return values

    @field_validator("nombre_usuario_reportado", mode="before")
    @classmethod
    def limpiar_nombre_usuario_reportado(cls, valor: Any) -> Any:
        """Normaliza nombre usuario reportado."""
        if isinstance(valor, str):
            valor_limpio = valor.strip()
            if not valor_limpio:
                raise AppValidationError(
                    "Error: El nombre de usuario reportado no puede estar vacío",
                    "REPORT_TARGET_USERNAME_EMPTY",
                )
            return valor_limpio
        return valor

    @field_validator("observaciones", mode="before")
    @classmethod
    def limpiar_observaciones(cls, valor: Any) -> Any:
        """Normaliza observaciones."""
        if valor is None:
            return None
        if isinstance(valor, str):
            valor_limpio = valor.strip()
            return valor_limpio or None
        return valor

    @model_validator(mode="after")
    def validar_motivos(self):
        """Valida motivos."""
        if not self.reportar_nombre and not self.reportar_foto:
            raise AppValidationError(
                "Error: Debes marcar al menos una opción de reporte",
                "AT_LEAST_ONE_REPORT_REASON_REQUIRED",
            )
        return self


class SolicitarPassword(BaseModel):
    """Esquema para solicitar recuperación indicando el idioma del correo."""

    email: EmailStr
    locale: str

    @model_validator(mode="before")
    @classmethod
    def validar_campos_requeridos_solicitar_recuperacion(cls, values: Any) -> Any:
        """Revisa que se reciban todos los campos obligatorios."""
        if isinstance(values, dict):
            if "email" not in values or not values["email"]:
                raise AppValidationError(
                    "Error: El email es obligatorio", "EMAIL_REQUIRED"
                )
            if "locale" not in values or not values["locale"]:
                raise AppValidationError(
                    "Error: El idioma es obligatorio", "LOCALE_REQUIRED"
                )
        return values

    @field_validator("email", mode="before")
    @classmethod
    def validar_email_solicitar_recuperacion(cls, valor: Any) -> Any:
        """Convierte el email a minúsculas antes de procesar."""
        if isinstance(valor, str):
            return valor.lower().strip()
        return valor

    @field_validator("email", mode="wrap")
    @classmethod
    def validar_email_solicitar_recuperacion_custom(cls, v, handler):
        """Intercepta el error de EmailStr para devolver un mensaje en el formato estandar."""
        return validators.interceptar_error_pydantic(
            v,
            handler,
            "EMAIL_FORMAT_INVALID",
            "Error: El formato del correo electrónico no es válido",
        )

    @field_validator("locale", mode="before")
    @classmethod
    def validar_locale_solicitar_recuperacion(cls, valor: Any) -> str:
        """Valida configuración regional solicitar recuperacion."""
        # Valida configuración regional solicitar recuperacion.
        if not isinstance(valor, str):
            raise AppValidationError(
                "Error: El idioma debe ser un texto", "LOCALE_MUST_BE_TEXT"
            )

        locale = valor.strip().lower().replace("_", "-")
        if not locale:
            raise AppValidationError(
                "Error: El idioma es obligatorio", "LOCALE_REQUIRED"
            )
        if locale.startswith("es"):
            return "es"
        if locale.startswith("en"):
            return "en"

        raise AppValidationError(
            "Error: El idioma no es compatible", "LOCALE_NOT_SUPPORTED"
        )


class ConfirmarPassword(BaseModel):
    """Esquema para cambiar la contraseña usando el código recibido."""

    email: EmailStr
    codigo: str = Field(...)
    nueva_password: str

    @model_validator(mode="before")
    @classmethod
    def validar_campos_confirmar_recuperacion(cls, values: Any) -> Any:
        """Revisa que se reciban todos los campos obligatorios."""
        # Valida campos confirmar recuperacion.
        if isinstance(values, dict):
            if "email" not in values or not values["email"]:
                raise AppValidationError(
                    "Error: El email es obligatorio", "EMAIL_REQUIRED"
                )
            if "codigo" not in values or not values["codigo"]:
                raise AppValidationError(
                    "Error: El código es obligatorio", "CODE_REQUIRED"
                )
            if "nueva_password" not in values or not values["nueva_password"]:
                raise AppValidationError(
                    "Error: La nueva contraseña es obligatoria", "NEW_PASSWORD_REQUIRED"
                )
        return values

    @field_validator("nueva_password")
    @classmethod
    def validar_nueva_password_confirmar_recuperacion(cls, v):
        """Valida nueva password confirmar recuperacion."""
        return validators.validar_password_logica(v)

    @field_validator("codigo", mode="before")
    @classmethod
    def limpiar_codigo_confirmar_recuperacion(cls, v) -> Any:
        """Normaliza codigo confirmar recuperacion."""
        if isinstance(v, str):
            # Quitar espacios delante y detrás.
            valor_limpio = v.strip()
            if not valor_limpio:
                raise AppValidationError(
                    "Error: El código no puede estar vacío", "CODE_EMPTY"
                )
            if len(valor_limpio) != 6:
                raise AppValidationError(
                    "Error: El código debe tener exactamente 6 caracteres",
                    "CODE_INVALID_LENGTH",
                )
            if not valor_limpio.isdigit():
                raise AppValidationError(
                    "Error: El código debe contener solo números",
                    "CODE_MUST_BE_NUMERIC",
                )
            return valor_limpio
        return v

    @field_validator("email", mode="before")
    @classmethod
    def validar_email_confirmar_recuperacion(cls, valor: Any) -> Any:
        """Convierte el email a minúsculas antes de procesar."""
        if isinstance(valor, str):
            return valor.lower().strip()
        return valor

    @field_validator("email", mode="wrap")
    @classmethod
    def validar_email_confirmar_recuperacion_custom(cls, v, handler):
        """Intercepta el error de EmailStr para devolver un mensaje en el formato estandar."""
        return validators.interceptar_error_pydantic(
            v,
            handler,
            "EMAIL_FORMAT_INVALID",
            "Error: El formato del correo electrónico no es válido",
        )


class GuardarActividad(BaseModel):
    """Payload validado para persistir una actividad con métricas enriquecidas."""

    tipo: TipoActividad
    distancia: StrictInt = Field(...)
    duracion_total: StrictInt = Field(...)
    duracion_movimiento: StrictInt = Field(...)
    duracion_parado: StrictInt = Field(default=0)
    duracion_pausa_manual: StrictInt = Field(default=0)
    calorias_quemadas: StrictInt = Field(...)
    ritmo_medio_movimiento: StrictInt = Field(default=0)
    ritmo_medio_total: StrictInt = Field(default=0)
    ritmo_maximo: StrictInt = Field(default=0)
    velocidad_media_x100: StrictInt = Field(default=0)
    velocidad_max_x100: StrictInt = Field(default=0)
    auto_pausas: StrictInt = Field(default=0)
    pausas_manuales: StrictInt = Field(default=0)
    alertas_velocidad: StrictInt = Field(default=0)
    ruta_polilinea: Optional[str] = None
    ruta_mapa_url: Optional[AnyHttpUrl] = Field(None, max_length=2048)
    fecha_ruta: datetime

    @model_validator(mode="before")
    @classmethod
    def validar_campos_requeridos_actividad(cls, values: Any) -> Any:
        """Valida campos requeridos actividad."""
        # Valida campos requeridos actividad.
        if isinstance(values, dict):
            required_fields = {
                "tipo": (
                    "Error: El tipo de actividad es obligatorio",
                    "ACTIVITY_TYPE_REQUIRED",
                ),
                "distancia": (
                    "Error: La distancia es obligatoria",
                    "DISTANCE_REQUIRED",
                ),
                "duracion_total": (
                    "Error: La duración total es obligatoria",
                    "TOTAL_DURATION_REQUIRED",
                ),
                "duracion_movimiento": (
                    "Error: La duración en movimiento es obligatoria",
                    "MOVING_DURATION_REQUIRED",
                ),
                "calorias_quemadas": (
                    "Error: Las calorías quemadas son obligatorias",
                    "BURNED_CALORIES_REQUIRED",
                ),
                "fecha_ruta": (
                    "Error: La fecha de la actividad es obligatoria",
                    "ACTIVITY_DATE_REQUIRED",
                ),
            }
            for field_name, (message, code) in required_fields.items():
                if field_name not in values:
                    raise AppValidationError(message, code)
        return values

    @field_validator("tipo", mode="wrap")
    @classmethod
    def validar_tipo_actividad_custom(cls, v, handler):
        """Valida tipo actividad custom."""
        return validators.interceptar_error_pydantic(
            v, handler, "VALIDATION_ERROR", "Error: El tipo de actividad no es válido"
        )

    @field_validator("distancia", mode="wrap")
    @classmethod
    def validar_distancia_actividad_custom(cls, v, handler):
        """Valida distancia actividad custom."""
        return validators.interceptar_error_pydantic(
            v,
            handler,
            "VALIDATION_ERROR",
            "Error: La distancia debe ser un número válido en metros",
        )

    @field_validator("distancia")
    @classmethod
    def validar_distancia_actividad(cls, v):
        """Valida distancia actividad."""
        return validators.validar_distancia_logica(v)

    @field_validator(
        "duracion_total",
        "duracion_movimiento",
        "duracion_parado",
        "duracion_pausa_manual",
        mode="wrap",
    )
    @classmethod
    def validar_duraciones_custom(cls, v, handler):
        """Valida duraciones custom."""
        return validators.interceptar_error_pydantic(
            v,
            handler,
            "VALIDATION_ERROR",
            "Error: Las duraciones deben ser números enteros en segundos",
        )

    @field_validator("duracion_total")
    @classmethod
    def validar_duracion_total(cls, v):
        """Valida duracion total."""
        return validators.validar_duracion_logica(v)

    @field_validator("duracion_movimiento")
    @classmethod
    def validar_duracion_movimiento(cls, v):
        """Valida duracion movimiento."""
        return validators.validar_duracion_logica(v)

    @field_validator("duracion_parado")
    @classmethod
    def validar_duracion_parado(cls, v):
        """Valida duracion parado."""
        return validators.validar_duracion_no_negativa_logica(
            v, "la duración parada", "STOPPED_DURATION"
        )

    @field_validator("duracion_pausa_manual")
    @classmethod
    def validar_duracion_pausa_manual(cls, v):
        """Valida duracion pausa manual."""
        return validators.validar_duracion_no_negativa_logica(
            v, "la duración de pausa manual", "MANUAL_PAUSE_DURATION"
        )

    @field_validator("calorias_quemadas", mode="wrap")
    @classmethod
    def validar_calorias_actividad_custom(cls, v, handler):
        """Valida calorias actividad custom."""
        return validators.interceptar_error_pydantic(
            v,
            handler,
            "CALORIES_MUST_BE_INTEGER",
            "Error: Las calorías deben ser un número entero",
        )

    @field_validator("calorias_quemadas")
    @classmethod
    def validar_calorias_actividad(cls, v):
        """Valida calorias actividad."""
        return validators.validar_calorias_logica(v)

    @field_validator("ritmo_medio_movimiento", "ritmo_medio_total", mode="wrap")
    @classmethod
    def validar_ritmos_custom(cls, v, handler):
        """Valida ritmos custom."""
        return validators.interceptar_error_pydantic(
            v,
            handler,
            "VALIDATION_ERROR",
            "Error: Los ritmos deben ser enteros en segundos por kilómetro",
        )

    @field_validator("ritmo_medio_movimiento")
    @classmethod
    def validar_ritmo_medio_movimiento(cls, v):
        """Valida ritmo medio movimiento."""
        return validators.validar_ritmo_segundos_km_logica(
            v, "el ritmo medio en movimiento", "MOVING_PACE"
        )

    @field_validator("ritmo_medio_total")
    @classmethod
    def validar_ritmo_medio_total(cls, v):
        """Valida ritmo medio total."""
        return validators.validar_ritmo_segundos_km_logica(
            v, "el ritmo medio total", "TOTAL_PACE"
        )

    @field_validator("velocidad_media_x100", "velocidad_max_x100", mode="wrap")
    @classmethod
    def validar_velocidades_custom(cls, v, handler):
        """Valida velocidades custom."""
        return validators.interceptar_error_pydantic(
            v,
            handler,
            "VALIDATION_ERROR",
            "Error: Las velocidades deben ser enteros en km/h x100",
        )

    @field_validator("velocidad_media_x100")
    @classmethod
    def validar_velocidad_media(cls, v):
        """Valida velocidad media."""
        return validators.validar_velocidad_x100_logica(
            v, "la velocidad media", "AVERAGE_SPEED"
        )

    @field_validator("velocidad_max_x100")
    @classmethod
    def validar_velocidad_max(cls, v):
        """Valida velocidad max."""
        return validators.validar_velocidad_x100_logica(
            v, "la velocidad máxima", "MAX_SPEED"
        )

    @field_validator("auto_pausas", "pausas_manuales", "alertas_velocidad", mode="wrap")
    @classmethod
    def validar_contadores_custom(cls, v, handler):
        """Valida contadores custom."""
        return validators.interceptar_error_pydantic(
            v,
            handler,
            "VALIDATION_ERROR",
            "Error: Los contadores deben ser enteros no negativos",
        )

    @field_validator("auto_pausas")
    @classmethod
    def validar_auto_pausas(cls, v):
        """Valida auto pausas."""
        return validators.validar_contador_tracking_logica(
            v, "las auto pausas", "AUTO_PAUSE_COUNT"
        )

    @field_validator("pausas_manuales")
    @classmethod
    def validar_pausas_manuales(cls, v):
        """Valida pausas manuales."""
        return validators.validar_contador_tracking_logica(
            v, "las pausas manuales", "MANUAL_PAUSE_COUNT"
        )

    @field_validator("alertas_velocidad")
    @classmethod
    def validar_alertas_velocidad(cls, v):
        """Valida alertas velocidad."""
        return validators.validar_contador_tracking_logica(
            v, "las alertas de velocidad", "SPEED_ALERT_COUNT"
        )

    @field_validator("fecha_ruta", mode="wrap")
    @classmethod
    def validar_fecha_ruta_actividad_custom(cls, v, handler):
        """Valida fecha ruta actividad custom."""
        return validators.interceptar_error_pydantic(
            v, handler, "VALIDATION_ERROR", "Error: El formato de fecha no es válido"
        )

    @field_validator("fecha_ruta")
    @classmethod
    def validar_fecha_ruta_actividad(cls, v):
        """Valida fecha ruta actividad."""
        return validators.validar_fecha_ruta_logica(v)

    @field_validator("ruta_polilinea", mode="before")
    @classmethod
    def validar_polilinea_actividad(cls, v):
        """Valida polilinea actividad."""
        if v == "":
            return None
        return validators.validar_polilinea_logica(v)

    @model_validator(mode="after")
    def validar_consistencia_temporal(self):
        """Valida consistencia temporal."""
        # Valida consistencia temporal.
        if self.duracion_movimiento > self.duracion_total:
            raise AppValidationError(
                "Error: La duración en movimiento no puede superar la duración total",
                "MOVING_DURATION_EXCEEDS_TOTAL",
            )
        if self.duracion_parado > self.duracion_total:
            raise AppValidationError(
                "Error: La duración parada no puede superar la duración total",
                "STOPPED_DURATION_EXCEEDS_TOTAL",
            )
        if self.duracion_movimiento + self.duracion_parado != self.duracion_total:
            raise AppValidationError(
                "Error: La suma de duración en movimiento y parada debe coincidir con la duración total",
                "DURATION_BREAKDOWN_MISMATCH",
            )
        if self.duracion_pausa_manual > self.duracion_total:
            raise AppValidationError(
                "Error: La pausa manual no puede superar la duración total",
                "MANUAL_PAUSE_EXCEEDS_TOTAL",
            )
        if self.velocidad_max_x100 < self.velocidad_media_x100:
            raise AppValidationError(
                "Error: La velocidad máxima no puede ser menor que la velocidad media",
                "MAX_SPEED_BELOW_AVERAGE_SPEED",
            )
        if self.distancia > 0 and self.duracion_movimiento <= 0:
            raise AppValidationError(
                "Error: Una actividad con distancia debe tener tiempo en movimiento",
                "MOVING_DURATION_REQUIRED_FOR_DISTANCE",
            )
        if self.duracion_movimiento > 0 and self.ritmo_medio_movimiento <= 0:
            raise AppValidationError(
                "Error: Falta el ritmo medio en movimiento",
                "MOVING_PACE_REQUIRED",
            )
        if self.duracion_total > 0 and self.ritmo_medio_total <= 0:
            raise AppValidationError(
                "Error: Falta el ritmo medio total",
                "TOTAL_PACE_REQUIRED",
            )
        if self.ritmo_maximo < 0:
            raise AppValidationError(
                "Error: El ritmo máximo no puede ser negativo",
                "MAX_PACE_NEGATIVE",
            )
        return self


class EventoDiagnosticoActividad(BaseModel):
    """
    Evento individual de la línea temporal de diagnóstico.

    Cada evento representa un cambio relevante del seguimiento: creación del servicio,
    auto-pausa, reanudación, guardado, destrucción, etc.
    """

    at: datetime
    tipo: str = Field(..., min_length=1, max_length=64)
    detalle: Optional[str] = Field(default=None, max_length=500)

    @field_validator("tipo")
    @classmethod
    def validar_tipo(cls, valor: str) -> str:
        """Valida tipo."""
        valor = valor.strip()
        if not valor:
            raise AppValidationError(
                "Error: El tipo de evento es obligatorio",
                "DIAGNOSTIC_EVENT_TYPE_REQUIRED",
            )
        return valor

    @field_validator("detalle")
    @classmethod
    def validar_detalle(cls, valor: Optional[str]) -> Optional[str]:
        """Valida detalle."""
        if valor is None:
            return None
        valor = valor.strip()
        return valor or None


class GuardarActividadDiagnostico(BaseModel):
    """
    Carga útil del endpoint de diagnóstico de actividad.

    Se utiliza solo para builds internas con telemetría automática activada.
    No sustituye al carga útil de ``GuardarActividad`` y no afecta al cálculo de
    puntos, métricas agregadas ni ranking.
    """

    actividad_id: Optional[StrictInt] = Field(default=None)
    actividad_local_id: Optional[str] = Field(default=None, max_length=64)

    session_started_at: Optional[datetime] = None
    session_finished_at: Optional[datetime] = None
    last_timer_tick_at: Optional[datetime] = None
    service_created_at: Optional[datetime] = None
    service_destroyed_at: Optional[datetime] = None

    elapsed_seconds: StrictInt = Field(default=0)
    moving_seconds: StrictInt = Field(default=0)
    stopped_seconds: StrictInt = Field(default=0)
    manual_pause_seconds: StrictInt = Field(default=0)

    distance_meters: StrictInt = Field(default=0)
    average_pace_total: StrictInt = Field(default=0)
    average_pace_moving: StrictInt = Field(default=0)
    max_pace: StrictInt = Field(default=0)

    auto_pauses: StrictInt = Field(default=0)
    manual_pauses: StrictInt = Field(default=0)
    speed_alerts: StrictInt = Field(default=0)

    running_classified_seconds: StrictInt = Field(default=0)
    walking_classified_seconds: StrictInt = Field(default=0)
    service_restart_count: StrictInt = Field(default=0)

    current_status: Optional[str] = Field(default=None, max_length=40)
    app_version: Optional[str] = Field(default=None, max_length=64)
    os_version: Optional[str] = Field(default=None, max_length=64)
    manufacturer: Optional[str] = Field(default=None, max_length=64)
    model: Optional[str] = Field(default=None, max_length=128)

    # Bloques auxiliares serializados por backend como JSON textual.
    device_info: Optional[dict[str, Any]] = None
    event_log: List[EventoDiagnosticoActividad] = Field(default_factory=list)

    @field_validator(
        "actividad_local_id",
        "current_status",
        "app_version",
        "os_version",
        "manufacturer",
        "model",
    )
    @classmethod
    def limpiar_textos_opcionales(cls, valor: Optional[str]) -> Optional[str]:
        """Normaliza textos opcionales."""
        if valor is None:
            return None
        valor = valor.strip()
        return valor or None

    @field_validator(
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
    @classmethod
    def validar_no_negativos(cls, valor: int) -> int:
        """Valida no negativos."""
        if valor < 0:
            raise AppValidationError(
                "Error: Los valores del diagnóstico no pueden ser negativos",
                "DIAGNOSTIC_NEGATIVE_VALUE",
            )
        return valor

    @model_validator(mode="after")
    def validar_consistencia(self):
        # Validación mínima para no persistir un breakdown temporal imposible.
        """Valida consistencia."""
        if self.moving_seconds > self.elapsed_seconds:
            raise AppValidationError(
                "Error: El tiempo en movimiento no puede superar el tiempo total",
                "DIAGNOSTIC_MOVING_EXCEEDS_ELAPSED",
            )
        if self.stopped_seconds > self.elapsed_seconds:
            raise AppValidationError(
                "Error: El tiempo parado no puede superar el tiempo total",
                "DIAGNOSTIC_STOPPED_EXCEEDS_ELAPSED",
            )
        return self


class RespuestaGuardarActividadDiagnostico(BaseModel):
    """Respuesta simple del endpoint de diagnóstico de actividad."""

    estatus: str
    mensaje: str
    diagnostico_id: int


class RespuestaObtenerActividad(BaseModel):
    """Representa respuesta obtener actividad."""

    model_config = ConfigDict(from_attributes=True, populate_by_name=True)

    id: int
    tipo: str
    distancia: StrictInt = Field(...)
    duracion_total: int
    duracion_movimiento: int
    duracion_parado: int
    duracion_pausa_manual: int
    calorias_quemadas: int
    ritmo_medio_movimiento: int
    ritmo_medio_total: int
    ritmo_maximo: int
    velocidad_media_x100: int
    velocidad_max_x100: int
    auto_pausas: int
    pausas_manuales: int
    alertas_velocidad: int
    ruta_polilinea: Optional[str] = None
    ruta_mapa_url: Optional[str] = None
    fecha_ruta: datetime
    nuevo_total_puntos: Optional[int] = None


class RespuestaObtenerActividadesPaginada(BaseModel):
    """Representa respuesta obtener actividades paginada."""

    items: List[RespuestaObtenerActividad]
    total: int
    skip: int
    limit: int
    has_more: bool


class RespuestaBorrarActividad(BaseModel):
    """Representa respuesta borrar actividad."""

    estatus: str
    mensaje: str
    nuevo_total_puntos: int


class ObtenerRanking(BaseModel):
    """Representa obtener ranking."""

    posicion: int
    nombre_usuario: str
    foto_perfil: Optional[str] = None
    foto_version: int = 0
    total_puntos: int
    total_metros: int


class RespuestaGenerica(BaseModel):
    """Representa respuesta generica."""

    estatus: str
    mensaje: str
