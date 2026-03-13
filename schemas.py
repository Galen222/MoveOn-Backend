# schemas.py

"""
Esquemas de Validación de Datos (Pydantic V2).

Define la estructura de los datos que entran y salen de la API, 
asegurando que cumplan con las reglas de negocio antes de tocar la DB.
"""
from pydantic import BaseModel, EmailStr, Field, field_validator, model_validator, StrictInt, ConfigDict, AnyHttpUrl
from datetime import date, datetime
from typing import Optional, Any, List
import re
from utils import validators
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

    @model_validator(mode='before')
    @classmethod
    def validar_campos_requeridos_registro(cls, values: Any) -> Any:
        """Revisa que se reciban todos los campos obligatorios."""
        if isinstance(values, dict):
            if 'nombre_usuario' not in values or not values['nombre_usuario']:
                raise ValueError('Error: El nombre de usuario es obligatorio')
            if 'email' not in values or not values['email']:
                raise ValueError('Error: El email es obligatorio')
            if 'password' not in values or not values['password']:
                raise ValueError('Error: La contraseña es obligatoria')
            if 'fecha_nacimiento' not in values:
                raise ValueError(
                    'Error: La fecha de nacimiento es obligatoria')
        return values

    @field_validator('nombre_usuario')
    @classmethod
    def validar_nombre_usuario(cls, valor: str) -> str:
        # Quitar espacios.
        valor = valor.strip()
        # Validación de longitud mínima.
        if len(valor) < 5:
            raise ValueError(
                'Error: El nombre de usuario debe tener al menos 5 caracteres')

        if len(valor) > 50:  # ✅ añadido
            raise ValueError(
                "Error: El nombre de usuario no puede superar los 50 caracteres")
        # Validación formato alfanumérico sin espacios.
        if not re.match("^[a-zA-Z0-9]*$", valor):
            raise ValueError(
                'Error: El nombre de usuario solo puede contener letras y números')
        return valor

    @field_validator('nombre_real')
    @classmethod
    def validar_nombre_real_registro(cls, v):
        if v is None:
            return v
        v = v.strip()
        return validators.validar_nombre_real_logica(v)

    @field_validator('email', mode='before')
    @classmethod
    def validar_email_registro(cls, valor: Any) -> Any:
        """Convierte el email a minúsculas antes de procesar."""
        if isinstance(valor, str):
            return valor.lower().strip()
        return valor

    @field_validator('email', mode='wrap')
    @classmethod
    def validar_email_registro_custom(cls, v, handler):
        """Intercepta el error de EmailStr para devolver un mensaje en el formato estandar."""
        return validators.interceptar_error_pydantic(v, handler, 'Error: El formato del correo electrónico no es válido')

    @field_validator('password')
    @classmethod
    def validar_password_registro(cls, v):
        return validators.validar_password_logica(v)

    @field_validator('fecha_nacimiento', mode='wrap')
    @classmethod
    def validar_fecha_nacimiento_registro_custom(cls, v, handler):
        """Intercepta el formato de fecha para devolver un mensaje en el formato estandar."""
        return validators.interceptar_error_pydantic(v, handler, 'Error: La fecha debe tener formato AAAA-MM-DD')

    @field_validator('fecha_nacimiento')
    @classmethod
    def validar_fecha_nacimiento_registro(cls, v):
        return validators.validar_fecha_nacimiento_logica(v)

    @field_validator('genero', mode='wrap')
    @classmethod
    def validar_genero_registro_custom(cls, v, handler):
        """Intercepta el genero para devolver un mensaje en el formato estandar."""
        return validators.interceptar_error_pydantic(v, handler, 'Error: El género seleccionado no es válido')

    @field_validator('altura', mode='wrap')
    @classmethod
    def validar_altura_registro_custom(cls, v, handler):
        """Intercepta la altura para devolver un mensaje en el formato estandar."""
        return validators.interceptar_error_pydantic(v, handler, 'Error: La altura debe ser un número entero en centimetros')

    @field_validator('altura')
    @classmethod
    def validar_altura_registro(cls, v):
        return validators.validar_altura_logica(v)

    @field_validator('peso', mode='wrap')
    @classmethod
    def validar_peso_registro_custom(cls, v, handler):
        """Intercepta el peso para devolver un mensaje en el formato estandar."""
        return validators.interceptar_error_pydantic(v, handler, 'Error: El peso debe ser un número en kilos')

    @field_validator('peso')
    @classmethod
    def validar_peso_registro(cls, v):
        return validators.validar_peso_logica(v)

    @field_validator('provincia', mode='wrap')
    @classmethod
    def validar_provincia_registro_custom(cls, v, handler):
        """Intercepta el error de Enum para devolver un mensaje en el formato estandar."""
        return validators.interceptar_error_pydantic(v, handler, 'Error: La ubicación seleccionada no es válida')

    @field_validator('perfil_visible', mode='wrap')
    @classmethod
    def validar_perfil_visible_registro_custom(cls, v, handler):
        """Intercepta sino llega un boolean para devolver un mensaje en el formato estandar."""
        return validators.interceptar_error_pydantic(v, handler, 'Error: El formato de perfil visible no es válido')

    @field_validator('acepta_terminos')
    @classmethod
    def validar_acepta_terminos(cls, v: bool) -> bool:
        if not v:
            raise ValueError(
                'Error: Debes aceptar los Términos y la Política de Privacidad para registrarte')
        return v

    @field_validator('fecha_aceptacion_terminos', mode='wrap')
    @classmethod
    def validar_fecha_aceptacion_terminos_custom(cls, v, handler):
        return validators.interceptar_error_pydantic(
            v, handler,
            'Error: La fecha de aceptación debe tener formato ISO-8601'
        )

    @field_validator('fecha_aceptacion_terminos')
    @classmethod
    def validar_fecha_aceptacion_terminos(cls, v: datetime) -> datetime:
        from datetime import timedelta, timezone
        ahora = datetime.now(timezone.utc)
        v_utc = v if v.tzinfo else v.replace(tzinfo=timezone.utc)
        if v_utc > ahora + timedelta(minutes=5):
            raise ValueError(
                'Error: La fecha de aceptación no puede ser futura')
        return v_utc

    @field_validator('version_terminos')
    @classmethod
    def validar_version_terminos(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError(
                'Error: La versión de los términos es obligatoria')
        return v


class RespuestaRegistro(BaseModel):
    estatus: str
    mensaje: str
    nombre_usuario: str


class Login(BaseModel):
    """Esquema para validar las credenciales en el inicio de sesión."""
    identificador: str
    password: str

    @model_validator(mode='before')
    @classmethod
    def validar_campos_requeridos_login(cls, values: Any) -> Any:
        """Revisa que se reciban todos los campos obligatorios."""
        if isinstance(values, dict):
            if 'identificador' not in values or not values['identificador']:
                raise ValueError('Error: El identificador es obligatorio')
            if 'password' not in values or not values['password']:
                raise ValueError('Error: La contraseña es obligatoria')
        return values

    @field_validator('identificador', mode='before')
    @classmethod
    def limpiar_identificador(cls, valor: Any) -> Any:
        if isinstance(valor, str):
            # Quitar espacios.
            valor_limpio = valor.strip()
            if not valor_limpio:
                raise ValueError(
                    'Error: El identificador no puede estar vacío')
            return valor_limpio
        return valor


class RespuestaLogin(BaseModel):
    estatus: str
    nombre_usuario: str
    token_acceso: str
    refresh_token: str


class SolicitudRefreshToken(BaseModel):
    refresh_token: str = Field(...)

    @model_validator(mode='before')
    @classmethod
    def validar_campos_requeridos_refresh(cls, values: Any) -> Any:
        if isinstance(values, dict):
            if 'refresh_token' not in values or not values['refresh_token']:
                raise ValueError('Error: El refresh token es obligatorio')
        return values

    @field_validator('refresh_token', mode='before')
    @classmethod
    def limpiar_refresh_token(cls, valor: Any) -> Any:
        if isinstance(valor, str):
            valor_limpio = valor.strip()
            if not valor_limpio:
                raise ValueError(
                    'Error: El refresh token no puede estar vacío')
            return valor_limpio
        return valor


class RespuestaRefreshToken(BaseModel):
    estatus: str
    nombre_usuario: str
    token_acceso: str
    refresh_token: str


class SolicitudLogout(SolicitudRefreshToken):
    """Recibe el refresh token para revocar la sesión actual."""
    pass


class RespuestaInformacionPerfil(BaseModel):
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

    @field_validator('nombre_real')
    @classmethod
    def validar_nombre_real_actualizacion(cls, v):
        if v is None:
            return v
        v = v.strip()
        return validators.validar_nombre_real_logica(v)

    @field_validator('email', mode='before')
    @classmethod
    def validar_email_actualizacion(cls, v):
        """Convierte el email a minúsculas antes de procesar."""
        if v is not None and isinstance(v, str):
            return v.lower().strip()
        return v

    @field_validator('email', mode='wrap')
    @classmethod
    def validar_email_actualizacion_custom(cls, v, handler):
        """Intercepta el error de EmailStr para devolver un mensaje en el formato estandar."""
        return validators.interceptar_error_pydantic(v, handler, 'Error: El formato del correo electrónico no es válido')

    @field_validator('password')
    @classmethod
    def validar_password_actualizacion(cls, v):
        return validators.validar_password_logica(v) if v is not None else v

    @field_validator('fecha_nacimiento', mode='wrap')
    @classmethod
    def validar_fecha_nacimiento_actualizacion_custom(cls, v, handler):
        """Intercepta el formato de fecha para devolver un mensaje en el formato estandar."""
        return validators.interceptar_error_pydantic(v, handler, 'Error: La fecha debe tener formato AAAA-MM-DD')

    @field_validator('fecha_nacimiento')
    @classmethod
    def validar_fecha_nacimiento_actualizacion(cls, v):
        return validators.validar_fecha_nacimiento_logica(v) if v is not None else v

    @field_validator('genero', mode='wrap')
    @classmethod
    def validar_genero_actualizacion_custom(cls, v, handler):
        """Intercepta el genero para devolver un mensaje en el formato estandar."""
        return validators.interceptar_error_pydantic(v, handler, 'Error: El género seleccionado no es válido')

    @field_validator('altura', mode='wrap')
    @classmethod
    def validar_altura_actualizacion_custom(cls, v, handler):
        """Intercepta la altura para devolver un mensaje en el formato estandar."""
        return validators.interceptar_error_pydantic(v, handler, 'Error: La altura debe ser un número entero en cm')

    @field_validator('altura')
    @classmethod
    def validar_altura_actualizacion(cls, v):
        return validators.validar_altura_logica(v)

    @field_validator('peso', mode='wrap')
    @classmethod
    def validar_peso_actualizacion_custom(cls, v, handler):
        """Intercepta el peso para devolver un mensaje en el formato estandar."""
        return validators.interceptar_error_pydantic(v, handler, 'Error: El peso debe ser un número en kilos')

    @field_validator('peso')
    @classmethod
    def validar_peso_actualizacion(cls, v):
        return validators.validar_peso_logica(v)

    @field_validator('provincia', mode='wrap')
    @classmethod
    def validar_provincia_actualizacion_custom(cls, v, handler):
        """Intercepta el error de Enum para para devolver un mensaje en el formato estandar."""
        return validators.interceptar_error_pydantic(v, handler, 'Error: La ubicación seleccionada no es válida')

    @field_validator('perfil_visible', mode='wrap')
    @classmethod
    def validar_perfil_visible_actualizacion_custom(cls, v, handler):
        """Intercepta sino llega un boolean para devolver un mensaje en el formato estandar."""
        return validators.interceptar_error_pydantic(v, handler, 'Error: El formato de perfil visible no es válido')

    @field_validator('objetivo_semanal_metros')
    @classmethod
    def validar_objetivo_semanal(cls, v: Optional[int]) -> Optional[int]:
        if v is None:
            return v
        if not isinstance(v, int):
            raise ValueError(
                'Error: El objetivo semanal debe ser un número entero en metros')
        if not (10 <= v <= 2_000_000):
            raise ValueError(
                'Error: El objetivo semanal debe estar entre 10 y 2 000 000 metros')
        return v

    @field_validator('objetivo_mensual_metros')
    @classmethod
    def validar_objetivo_mensual(cls, v: Optional[int]) -> Optional[int]:
        if v is None:
            return v
        if not isinstance(v, int):
            raise ValueError(
                'Error: El objetivo mensual debe ser un número entero en metros')
        if not (10 <= v <= 2_000_000):
            raise ValueError(
                'Error: El objetivo mensual debe estar entre 10 y 2 000 000 metros')
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


class SolicitarPassword(BaseModel):
    """Esquema para pedir el código enviando solo el email."""
    email: EmailStr

    @model_validator(mode='before')
    @classmethod
    def validar_campos_requeridos_solicitar_recuperacion(cls, values: Any) -> Any:
        """Revisa que se reciban todos los campos obligatorios."""
        if isinstance(values, dict):
            if 'email' not in values or not values['email']:
                raise ValueError('Error: El email es obligatorio')
        return values

    @field_validator('email', mode='before')
    @classmethod
    def validar_email_solicitar_recuperacion(cls, valor: Any) -> Any:
        """Convierte el email a minúsculas antes de procesar."""
        if isinstance(valor, str):
            return valor.lower().strip()
        return valor

    @field_validator('email', mode='wrap')
    @classmethod
    def validar_email_solicitar_recuperacion_custom(cls, v, handler):
        """Intercepta el error de EmailStr para devolver un mensaje en el formato estandar."""
        return validators.interceptar_error_pydantic(v, handler, 'Error: El formato del correo electrónico no es válido')


class ConfirmarPassword(BaseModel):
    """Esquema para cambiar la contraseña usando el código recibido."""
    email: EmailStr
    codigo: str = Field(...)
    nueva_password: str

    @model_validator(mode='before')
    @classmethod
    def validar_campos_confirmar_recuperacion(cls, values: Any) -> Any:
        """Revisa que se reciban todos los campos obligatorios."""
        if isinstance(values, dict):
            if 'email' not in values or not values['email']:
                raise ValueError('Error: El email es obligatorio')
            if 'codigo' not in values or not values['codigo']:
                raise ValueError('Error: El código es obligatorio')
            if 'nueva_password' not in values or not values['nueva_password']:
                raise ValueError('Error: La nueva contraseña es obligatoria')
        return values

    @field_validator('nueva_password')
    @classmethod
    def validar_nueva_password_confirmar_recuperacion(cls, v):
        return validators.validar_password_logica(v)

    @field_validator('codigo', mode='before')
    @classmethod
    def limpiar_codigo_confirmar_recuperacion(cls, v) -> Any:
        if isinstance(v, str):
            # Quitar espacios delante y detrás.
            valor_limpio = v.strip()
            if not valor_limpio:
                raise ValueError('Error: El código no puede estar vacío')
            if len(valor_limpio) != 6:
                raise ValueError(
                    'Error: El código debe tener exactamente 6 caracteres')
            if not valor_limpio.isdigit():
                raise ValueError('Error: El código debe contener solo números')
            return valor_limpio
        return v

    @field_validator('email', mode='before')
    @classmethod
    def validar_email_confirmar_recuperacion(cls, valor: Any) -> Any:
        """Convierte el email a minúsculas antes de procesar."""
        if isinstance(valor, str):
            return valor.lower().strip()
        return valor

    @field_validator('email', mode='wrap')
    @classmethod
    def validar_email_confirmar_recuperacion_custom(cls, v, handler):
        """Intercepta el error de EmailStr para devolver un mensaje en el formato estandar."""
        return validators.interceptar_error_pydantic(v, handler, 'Error: El formato del correo electrónico no es válido')


class GuardarActividad(BaseModel):
    tipo: TipoActividad
    distancia: StrictInt = Field(...)
    duracion: StrictInt = Field(...)
    calorias_quemadas: StrictInt = Field(...)
    ruta_polilinea: Optional[str] = None
    # URL válida (http/https) + límite razonable
    ruta_mapa_url: Optional[AnyHttpUrl] = Field(None, max_length=2048)
    fecha_ruta: datetime

    @model_validator(mode='before')
    @classmethod
    def validar_campos_requeridos_actividad(cls, values: Any) -> Any:
        """Revisa manualmente que lleguen los datos para dar el mensaje de error personalizado."""
        if isinstance(values, dict):
            if 'tipo' not in values:
                raise ValueError('Error: El tipo de actividad es obligatorio')
            if 'distancia' not in values:
                raise ValueError('Error: La distancia es obligatoria')
            if 'duracion' not in values:
                raise ValueError('Error: La duración es obligatoria')
            if 'calorias_quemadas' not in values:
                raise ValueError(
                    'Error: Las calorías quemadas son obligatorias')
        return values

    @field_validator('tipo', mode='wrap')
    @classmethod
    def validar_tipo_actividad_custom(cls, v, handler):
        """Intercepta errores en el Enum de tipo de actividad."""
        return validators.interceptar_error_pydantic(v, handler, 'Error: El tipo de actividad no es válido')

    @field_validator('distancia', mode='wrap')
    @classmethod
    def validar_distancia_actividad_custom(cls, v, handler):
        """Intercepta errores de tipo en distancia."""
        return validators.interceptar_error_pydantic(v, handler, 'Error: La distancia debe ser un número válido en metros')

    @field_validator('distancia')
    @classmethod
    def validar_distancia_actividad(cls, v):
        return validators.validar_distancia_logica(v)

    @field_validator('duracion', mode='wrap')
    @classmethod
    def validar_duracion_actividad_custom(cls, v, handler):
        """Intercepta errores de tipo en duración."""
        return validators.interceptar_error_pydantic(v, handler, 'Error: La duración debe ser un número entero en segundos')

    @field_validator('duracion')
    @classmethod
    def validar_duracion_actividad(cls, v):
        return validators.validar_duracion_logica(v)

    @field_validator('calorias_quemadas', mode='wrap')
    @classmethod
    def validar_calorias_actividad_custom(cls, v, handler):
        """Intercepta errores de tipo en calorías."""
        return validators.interceptar_error_pydantic(v, handler, 'Error: Las calorías deben ser un número entero')

    @field_validator('calorias_quemadas')
    @classmethod
    def validar_calorias_actividad(cls, v):
        return validators.validar_calorias_logica(v)

    @field_validator('fecha_ruta', mode='wrap')
    @classmethod
    def validar_fecha_ruta_actividad_custom(cls, v, handler):
        """Intercepta errores de formato de fecha."""
        return validators.interceptar_error_pydantic(v, handler, 'Error: El formato de fecha no es válido')

    @field_validator('fecha_ruta')
    @classmethod
    def validar_fecha_ruta_actividad(cls, v):
        # Primero validamos formato (wrap) implícito en Pydantic, luego lógica
        return validators.validar_fecha_ruta_logica(v)

    @field_validator('ruta_polilinea', mode='before')
    @classmethod
    def validar_polilinea_actividad(cls, v):
        if v == "":
            return None
        return validators.validar_polilinea_logica(v)


class RespuestaObtenerActividad(BaseModel):
    model_config = ConfigDict(from_attributes=True, populate_by_name=True)

    id: int
    tipo: str
    distancia: StrictInt = Field(...)
    duracion: int
    calorias_quemadas: int
    ruta_polilinea: Optional[str] = None
    ruta_mapa_url: Optional[str] = None
    fecha_ruta: datetime
    nuevo_total_puntos: Optional[int] = None


class RespuestaObtenerActividadesPaginada(BaseModel):
    items: List[RespuestaObtenerActividad]
    total: int
    skip: int
    limit: int
    has_more: bool


class RespuestaBorrarActividad(BaseModel):
    estatus: str
    mensaje: str
    nuevo_total_puntos: int


class ObtenerRanking(BaseModel):
    nombre_usuario: str
    foto_perfil: Optional[str] = None
    foto_version: int = 0
    total_puntos: int


class RespuestaGenerica(BaseModel):
    estatus: str
    mensaje: str
