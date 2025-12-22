# schemas.py

"""
Esquemas de Validación de Datos (Pydantic V2).

"""
from pydantic import BaseModel, EmailStr, Field, field_validator
from datetime import date
from typing import Optional, Any
import re

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
        # Validación de longitud mínima
        if len(valor) < 5:
            raise ValueError('Error: El nombre de usuario debe tener al menos 5 caracteres')
        # Validación formato alfanumérico sin espacios
        if not re.match("^[a-zA-Z0-9]*$", valor):
            raise ValueError('Error: El nombre de usuario solo puede contener letras y números')
        return valor

    @field_validator('nombre_real')
    @classmethod
    def validar_nombre_real(cls, valor: str) -> str:
        # Validación de longitud mínima
        if len(valor) < 3:
            raise ValueError('Error: El nombre real es demasiado corto')
        # Validación formato alfanumérico permitiendo espacios, letras (tildes/ñ) y números.
        if not re.match("^[a-zA-Z0-9áéíóúÁÉÍÓÚñÑ ]*$", valor):
            raise ValueError('Error: El nombre real no puede contener símbolos')
        return valor
    
    @field_validator('email', mode='before')
    @classmethod
    def email_a_minusculas(cls, valor: Any) -> Any:
        """Convierte el email a minúsculas antes de la validación formal."""
        if isinstance(valor, str):
            return valor.lower()
        return valor
    
    @field_validator('email', mode='wrap')
    @classmethod
    def validar_email_mensaje_custom(cls, v, handler):
        """Traduce el errores de EmailStr al mismo formato general"""
        try:
            return handler(v)
        except Exception:
            raise ValueError('Error: El formato del correo electrónico no es válido')

    @field_validator('contraseña')
    @classmethod
    def validar_contraseña_segura(cls, valor: str) -> str:
        # Validación de longitud mínima
        if len(valor) < 8:
            raise ValueError('Error: La contraseña debe tener al menos 8 caracteres')
        # Validación al menos una letra mayuscula
        if not any(char.isupper() for char in valor):
            raise ValueError('Error: La contraseña debe incluir al menos una letra mayúscula')
        # Validación al menos un número        
        if not any(char.isdigit() for char in valor):
            raise ValueError('Error: La contraseña debe incluir al menos un número')
        return valor

    @field_validator('fecha_nacimiento')
    @classmethod
    def validar_edad_minima(cls, valor: date) -> date:
        hoy = date.today()
        edad = hoy.year - valor.year - ((hoy.month, hoy.day) < (valor.month, valor.day))
        if edad < 13:
            raise ValueError('Error: Debes tener al menos 13 años para registrarte')
        return valor

class LoginUsuario(BaseModel):
    """Esquema para validar las credenciales en el inicio de sesión."""
    identificador: str 
    contraseña: str

    @field_validator('identificador', mode='before')
    @classmethod
    def identificador_a_minusculas(cls, valor: Any) -> Any:
        """Convierte el identificador a minúsculas por si el usuario usa su email para loguearse."""
        if isinstance(valor, str):
            return valor.lower()
        return valor

class ActualizarPerfil(BaseModel):
    """Esquema para actualizaciones parciales del perfil."""
    nombre_real: Optional[str] = None
    ciudad: Optional[str] = None
    foto_perfil: Optional[str] = None
    perfil_visible: Optional[bool] = None