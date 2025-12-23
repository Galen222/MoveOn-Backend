# schemas.py

"""
Esquemas de Validación de Datos (Pydantic V2).

Define la estructura de los datos que entran y salen de la API, 
asegurando que cumplan con las reglas de negocio antes de tocar la DB.
"""
from pydantic import BaseModel, EmailStr, Field, field_validator
from datetime import date
from typing import Optional, Any
import re

# Funciones de lógica de validación

def validar_nombre_real_logica(v: str) -> str:
    """Regla para el nombre real: longitud y símbolos."""
    if len(v) < 3:
        raise ValueError('Error: El nombre real es demasiado corto')
    if not re.match("^[a-zA-Z0-9áéíóúÁÉÍÓÚñÑ ]*$", v):
        raise ValueError('Error: El nombre real no puede contener símbolos')
    return v

def validar_contraseña_logica(v: str) -> str:
    """Regla para contraseña: longitud, mayúscula y número."""
    if len(v) < 8:
        raise ValueError('Error: La contraseña debe tener al menos 8 caracteres')
    if not any(char.isupper() for char in v):
        raise ValueError('Error: La contraseña debe incluir al menos una letra mayúscula')
    if not any(char.isdigit() for char in v):
        raise ValueError('Error: La contraseña debe incluir al menos un número')
    return v

def validar_fecha_nacimiento_logica(v: date) -> date:
    """Regla para edad mínima (13 años) y evitar fechas futuras."""
    hoy = date.today()
    if v > hoy:
        raise ValueError('Error: La fecha de nacimiento no puede ser en el futuro')
    edad = hoy.year - v.year - ((hoy.month, hoy.day) < (v.month, v.day))
    if edad < 13:
        raise ValueError('Error: Debes tener al menos 13 años para registrarte')
    return v

class RegistroUsuario(BaseModel):
    """
    Esquema para validar el registro de un nuevo usuario.
    """
    nombre_usuario: str = Field(...)
    nombre_real: str = Field(...)
    email: EmailStr 
    contraseña: str = Field(...)
    fecha_nacimiento: date
    ciudad: Optional[str] = None
    perfil_visible: bool = Field(default=True)

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
    def puente_nombre_reg(cls, v):
        return validar_nombre_real_logica(v)
    
    @field_validator('email', mode='before')
    @classmethod
    def email_a_minusculas(cls, valor: Any) -> Any:
        """Convierte el email a minúsculas antes de procesar."""
        if isinstance(valor, str):
            return valor.lower().strip()
        return valor
    
    @field_validator('email', mode='wrap')
    @classmethod
    def validar_email_mensaje_custom(cls, v, handler):
        """Recoge errores de EmailStr para devolver un mensaje en el formato utilizado."""
        try:
            return handler(v)
        except Exception:
            raise ValueError('Error: El formato del correo electrónico no es válido')

    @field_validator('contraseña')
    @classmethod
    def puente_contraseña_reg(cls, v):
        return validar_contraseña_logica(v)

    @field_validator('fecha_nacimiento')
    @classmethod
    def puente_fecha_reg(cls, v):
        return validar_fecha_nacimiento_logica(v)

class LoginUsuario(BaseModel):
    """Esquema para validar las credenciales en el inicio de sesión."""
    identificador: str 
    contraseña: str

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
    ciudad: Optional[str] = None
    perfil_visible: Optional[bool] = None

    @field_validator('nombre_real')
    @classmethod
    def puente_nombre_edit(cls, v):
        return validar_nombre_real_logica(v) if v is not None else v

    @field_validator('email', mode='before')
    @classmethod
    def email_a_minusculas_edit(cls, v):
        if v is not None and isinstance(v, str):
            return v.lower().strip()
        return v

    @field_validator('email', mode='wrap')
    @classmethod
    def validar_email_edit_custom(cls, v, handler):
        if v is None: 
            return v
        try:
            return handler(v)
        except Exception:
            raise ValueError('Error: El formato del correo electrónico no es válido')

    @field_validator('contraseña')
    @classmethod
    def puente_contraseña_edit(cls, v):
        return validar_contraseña_logica(v) if v is not None else v

    @field_validator('fecha_nacimiento')
    @classmethod
    def puente_fecha_edit(cls, v):
        return validar_fecha_nacimiento_logica(v) if v is not None else v