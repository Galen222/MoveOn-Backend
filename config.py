# config.py

from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    # Base de Datos
    DB_USER: str
    DB_PASSWORD: str
    DB_HOST: str
    DB_PORT: int
    DB_NAME: str

    # Seguridad App
    APP_ID: str
    APP_SESSION_SECRET: str
    
    # Seguridad App JWT acceso corto
    SECRET_KEY: str
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30

    # Seguridad App JWT acceso largo
    REFRESH_TOKEN_SECRET: str
    REFRESH_TOKEN_EXPIRE_DAYS: int = 30

    # Seguridad App Cifrado
    ALGORITHM: str = "HS256"
    
    # Almacenamiento
    STORAGE_TYPE: str = "local"
    UPLOAD_DIR: str = "uploads"
    
    # Cloudinary
    CLOUDINARY_CLOUD_NAME: str = ""
    CLOUDINARY_API_KEY: str = ""
    CLOUDINARY_API_SECRET: str = ""

    # Email
    EMAIL_HOST: str
    EMAIL_PORT: int = 587
    EMAIL_USER: str
    EMAIL_PASS: str

    # Configuración Pydantic V2.
    model_config = SettingsConfigDict(
        env_file=".env",
        case_sensitive=True, # Distingue entre mayusculas y minusculas.
        extra="ignore" # Si hay variables extra en el .env, no da error.
    )

settings = Settings() # type: ignore
