# schemas.py

"""
Esquemas de Validación de Datos (Pydantic V2).

Define la estructura de los datos que entran y salen de la API, 
asegurando que cumplan con las reglas de negocio antes de tocar la DB.
"""
from pydantic import BaseModel, EmailStr, Field, field_validator, model_validator
from datetime import date
from typing import Optional, Any
import re
from enum import Enum
from utils import validators

class ProvinciaEspaña(str, Enum):
    # Andalucía
    ALMERIA = "Almería"
    CADIZ = "Cádiz"
    CORDOBA = "Córdoba"
    GRANADA = "Granada"
    HUELVA = "Huelva"
    JAEN = "Jaén"
    MALAGA = "Málaga"
    SEVILLA = "Sevilla"
    # Aragón
    HUESCA = "Huesca"
    TERUEL = "Teruel"
    ZARAGOZA = "Zaragoza"
    # Asturias
    ASTURIAS = "Asturias"
    # Baleares
    BALEARES = "Islas Baleares"
    # Canarias
    LAS_PALMAS = "Las Palmas"
    SANTA_CRUZ_TENERIFE = "Santa Cruz de Tenerife"
    # Cantabria
    CANTABRIA = "Cantabria"
    # Castilla-La Mancha
    ALBACETE = "Albacete"
    CIUDAD_REAL = "Ciudad Real"
    CUENCA = "Cuenca"
    GUADALAJARA = "Guadalajara"
    TOLEDO = "Toledo"
    # Castilla y León
    AVILA = "Ávila"
    BURGOS = "Burgos"
    LEON = "León"
    PALENCIA = "Palencia"
    SALAMANCA = "Salamanca"
    SEGOVIA = "Segovia"
    SORIA = "Soria"
    VALLADOLID = "Valladolid"
    ZAMORA = "Zamora"
    # Cataluña
    BARCELONA = "Barcelona"
    GIRONA = "Girona"
    LLEIDA = "Lleida"
    TARRAGONA = "Tarragona"
    # Extremadura
    BADAJOZ = "Badajoz"
    CACERES = "Cáceres"
    # Galicia
    A_CORUNA = "A Coruña"
    LUGO = "Lugo"
    OURENSE = "Ourense"
    PONTEVEDRA = "Pontevedra"
    # Madrid
    MADRID = "Madrid"
    # Murcia
    MURCIA = "Murcia"
    # Navarra
    NAVARRA = "Navarra"
    # País Vasco
    ALAVA = "Álava"
    GUIPUZCOA = "Guipúzcoa"
    VIZCAYA = "Vizcaya"
    # La Rioja
    RIOJA = "La Rioja"
    # Comunidad Valenciana
    ALICANTE = "Alicante"
    CASTELLON = "Castellón"
    VALENCIA = "Valencia"
    # Ciudades Autónomas
    CEUTA = "Ceuta"
    MELILLA = "Melilla"

class RegistroUsuario(BaseModel):
    """
    Esquema para validar los campos en el registro de un nuevo usuario.
    """
    nombre_usuario: str = Field(...)
    email: EmailStr 
    contraseña: str = Field(...)
    nombre_real: Optional[str] = None
    fecha_nacimiento: date
    provincia: Optional[ProvinciaEspaña] = None
    perfil_visible: bool = Field(default=True)
    
    @model_validator(mode='before')
    @classmethod
    def validar_campos_requeridos_registro(cls, values: Any) -> Any:
        """Revisa que se reciban todos los campos obligatorios."""        
        if isinstance(values, dict):
            if 'nombre_usuario' not in values or not values['nombre_usuario']:
                raise ValueError('Error: El nombre de usuario es obligatorio')
            if 'email' not in values or not values['email']:
                raise ValueError('Error: El email es obligatorio')
            if 'contraseña' not in values or not values['contraseña']:
                raise ValueError('Error: La contraseña es obligatoria')
            if 'fecha_nacimiento' not in values:
                raise ValueError('Error: La fecha de nacimiento es obligatoria')
        return values
    
    @field_validator('nombre_usuario')
    @classmethod
    def validar_nombre_usuario(cls, valor: str) -> str:
        # Quitar espacios.
        valor = valor.strip()
        # Validación de longitud mínima.
        if len(valor) < 5:
            raise ValueError('Error: El nombre de usuario debe tener al menos 5 caracteres')
        # Validación formato alfanumérico sin espacios.
        if not re.match("^[a-zA-Z0-9]*$", valor):
            raise ValueError('Error: El nombre de usuario solo puede contener letras y números')
        return valor

    @field_validator('nombre_real')
    @classmethod
    def validar_nombre_real_registro(cls, v):
        if v is None: return v
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
        return validators.interceptar_error_pydantic(v, handler,'Error: El formato del correo electrónico no es válido')

    @field_validator('contraseña')
    @classmethod
    def validar_contraseña_registro(cls, v):
        return validators.validar_contraseña_logica(v)

    @field_validator('fecha_nacimiento', mode='wrap')
    @classmethod
    def validar_fecha_nacimiento_registro_custom(cls, v, handler):
        """Intercepta el formato de fecha para devolver un mensaje en el formato estandar."""
        return validators.interceptar_error_pydantic(v, handler,'Error: La fecha debe tener formato AAAA-MM-DD')

    @field_validator('fecha_nacimiento')
    @classmethod
    def validar_fecha_nacimiento_registro(cls, v):
        return validators.validar_fecha_nacimiento_logica(v)

    @field_validator('provincia', mode='wrap')
    @classmethod
    def validar_provincia_custom(cls, v, handler):
        """Intercepta el error de Enum para devolver un mensaje en el formato estandar."""
        return validators.interceptar_error_pydantic(v, handler,'Error: La ubicación seleccionada no es válida')

    @field_validator('perfil_visible', mode='wrap')
    @classmethod
    def validar_perfil_visible_registro_custom(cls, v, handler):
        """Intercepta sino llega un boolean para devolver un mensaje en el formato estandar."""
        return validators.interceptar_error_pydantic(v, handler,'Error: El formato de perfil visible no es válido')        

class LoginUsuario(BaseModel):
    """Esquema para validar las credenciales en el inicio de sesión."""
    identificador: str 
    contraseña: str
    
    @model_validator(mode='before')
    @classmethod
    def validar_campos_requeridos_login(cls, values: Any) -> Any:
        """Revisa que se reciban todos los campos obligatorios."""          
        if isinstance(values, dict):
            if 'identificador' not in values or not values['identificador']:
                raise ValueError('Error: El identificador es obligatorio')
            if 'contraseña' not in values or not values['contraseña']:
                raise ValueError('Error: La contraseña es obligatoria')
        return values
    
    @field_validator('identificador', mode='before')
    @classmethod
    def limpiar_identificador(cls, valor: Any) -> Any:
        if isinstance(valor, str):
            # Quitar espacios.
            valor_limpio = valor.strip()
            if not valor_limpio:
                raise ValueError('Error: El identificador no puede estar vacío')
            return valor_limpio
        return valor

class ActualizarPerfil(BaseModel):
    """Esquema para actualizaciones del perfil de usuario."""
    nombre_real: Optional[str] = None
    email: Optional[EmailStr] = None
    contraseña: Optional[str] = None
    fecha_nacimiento: Optional[date] = None
    provincia: Optional[ProvinciaEspaña] = None
    perfil_visible: Optional[bool] = None

    @field_validator('nombre_real')
    @classmethod
    def validar_nombre_real_actualizacion(cls, v):
        if v is None: return v
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
        return validators.interceptar_error_pydantic(v, handler,'Error: El formato del correo electrónico no es válido')

    @field_validator('contraseña')
    @classmethod
    def validar_contraseña_actualizacion(cls, v):
        return validators.validar_contraseña_logica(v) if v is not None else v

    @field_validator('fecha_nacimiento', mode='wrap')
    @classmethod
    def validar_fecha_nacimiento_actualizacion_custom(cls, v, handler):
        """Intercepta el formato de fecha para devolver un mensaje en el formato estandar."""        
        return validators.interceptar_error_pydantic(v, handler,'Error: La fecha debe tener formato AAAA-MM-DD')

    @field_validator('fecha_nacimiento')
    @classmethod
    def validar_fecha_nacimiento_actualizacion(cls, v):
        return validators.validar_fecha_nacimiento_logica(v) if v is not None else v

    @field_validator('provincia', mode='wrap')
    @classmethod
    def validar_provincia_actualizacion_custom(cls, v, handler):
        """Intercepta el error de Enum para para devolver un mensaje en el formato estandar."""
        return validators.interceptar_error_pydantic(v, handler,'Error: La ubicación seleccionada no es válida')
        
    @field_validator('perfil_visible', mode='wrap')
    @classmethod
    def validar_perfil_visible_actualizacion_custom(cls, v, handler):
        """Intercepta sino llega un boolean para devolver un mensaje en el formato estandar."""        
        return validators.interceptar_error_pydantic(v, handler,'Error: El formato de perfil visible no es válido')        
    
class SolicitarRecuperacion(BaseModel):
    """Esquema para pedir el código enviando solo el email."""
    email: EmailStr
    
    @model_validator(mode='before')
    @classmethod
    def validar_email_recuperacion(cls, values: Any) -> Any:
        """Revisa que se reciban todos los campos obligatorios."""          
        if isinstance(values, dict):
            if 'email' not in values or not values['email']:
                raise ValueError('Error: El email es obligatorio')
        return values
    
    @field_validator('email', mode='wrap')
    @classmethod
    def validar_email_recuperacion_custom(cls, v, handler):
        """Intercepta el error de EmailStr para devolver un mensaje en el formato estandar."""        
        return validators.interceptar_error_pydantic(v, handler,'Error: El formato del correo electrónico no es válido')

class ConfirmarRecuperacion(BaseModel):
    """Esquema para cambiar la contraseña usando el código recibido."""
    email: EmailStr
    codigo: str = Field(...)
    nueva_contraseña: str
    
    @model_validator(mode='before')
    @classmethod
    def validar_campos_recuperacion(cls, values: Any) -> Any:
        """Revisa que se reciban todos los campos obligatorios."""          
        if isinstance(values, dict):
            if 'email' not in values or not values['email']:
                raise ValueError('Error: El email es obligatorio')
            if 'codigo' not in values or not values['codigo']:
                raise ValueError('Error: El código es obligatorio')
            if 'nueva_contraseña' not in values or not values['nueva_contraseña']:
                raise ValueError('Error: La nueva contraseña es obligatoria')
        return values
    
    @field_validator('nueva_contraseña')
    @classmethod
    def validar_nueva_contraseña_recuperacion(cls, v):
        return validators.validar_contraseña_logica(v)
    
    @field_validator('codigo', mode='before')
    @classmethod
    def limpiar_codigo(cls, v) -> Any:
        if isinstance(v, str):
            #Quitar espacios delante y detrás.
            valor_limpio = v.strip()
            if not valor_limpio:
                raise ValueError('Error: El código no puede estar vacío')
            if len(valor_limpio) != 6:
                raise ValueError('Error: El código debe tener exactamente 6 caracteres')
            return valor_limpio
        return v
    
    @field_validator('email', mode='wrap')
    @classmethod
    def validar_email_recuperacion_custom(cls, v, handler):
        """Intercepta el error de EmailStr para devolver un mensaje en el formato estandar."""        
        return validators.interceptar_error_pydantic(v, handler,'Error: El formato del correo electrónico no es válido')