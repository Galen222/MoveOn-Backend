# config.py

from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    # Base de Datos
    DB_USER: str
    DB_PASSWORD: str
    DB_HOST: str
    DB_PORT: str
    DB_NAME: str

    # Seguridad App
    APP_ID_SECRET: str
    APP_SESSION_SECRET: str
    SECRET_KEY: str
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 1440

    # Almacenamiento
    STORAGE_TYPE: str = "local"
    UPLOAD_DIR: str = "uploads"
    
    # Cloudinary
    # Es mejor ponerles un valor por defecto para que no fallen si usas modo local
    CLOUDINARY_CLOUD_NAME: str = ""
    CLOUDINARY_API_KEY: str = ""
    CLOUDINARY_API_SECRET: str = ""

    # Email
    EMAIL_HOST: str
    EMAIL_PORT: int = 587
    EMAIL_USER: str
    EMAIL_PASS: str

    # CONFIGURACIÓN MODERNA DE PYDANTIC V2
    model_config = SettingsConfigDict(
        env_file=".env",
        case_sensitive=True, # Distingue entre mayusculas y minusculas
        extra="ignore" # Si hay variables extra en el .env, no da error
    )

settings = Settings() # type: ignore