"""
Esquemas de Validación de Datos (Pydantic V2).

"""
from pydantic import BaseModel, EmailStr, Field, field_validator
import re

class RegistroUsuario(BaseModel):
    """
    Esquema de registro con control total sobre los mensajes de error.
    """
    usuario: str = Field(...)
    email: EmailStr 
    contraseña: str = Field(...)

    @field_validator('usuario')
    @classmethod
    def validar_nombre_usuario(cls, valor: str) -> str:
        # Validación de longitud manual
        if len(valor) < 5:
            raise ValueError('Error: El nombre de usuario debe tener al menos 5 caracteres')
        # Validación de caracteres
        if not re.match("^[a-zA-Z0-9]*$", valor):
            raise ValueError('Error: El nombre de usuario solo puede contener letras y números')
        return valor

    @field_validator('email', mode='wrap')
    @classmethod
    def validar_email_mensaje_custom(cls, v, handler):
        try:
            return handler(v)
        except Exception:
            raise ValueError('Error: El formato del correo electrónico no es válido')

    @field_validator('contraseña')
    @classmethod
    def validar_contraseña_segura(cls, valor: str) -> str:
        # Validación de longitud manual
        if len(valor) < 8:
            raise ValueError('Error: La contraseña debe tener al menos 8 caracteres')
        # Validación de contenido
        if not any(char.isupper() for char in valor):
            raise ValueError('Error: La contraseña debe incluir al menos una letra mayúscula')
        if not any(char.isdigit() for char in valor):
            raise ValueError('Error: La contraseña debe incluir al menos un número')
        return valor

class LoginUsuario(BaseModel):
    identificador: str
    contraseña: str