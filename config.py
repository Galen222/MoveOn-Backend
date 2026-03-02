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
    APP_SESSION_EXPIRE_MINUTES: int = 5
    
    # Seguridad App JWT acceso corto
    ACCESS_TOKEN_SECRET: str
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30

    # Seguridad App JWT acceso largo
    REFRESH_TOKEN_SECRET: str
    REFRESH_TOKEN_EXPIRE_DAYS: int = 30

    # Seguridad App Cifrado
    ALGORITHM: str = "HS256"
    
    # Hash de refresh tokens en DB (pepper). Si lo dejas vacío, se usará REFRESH_TOKEN_SECRET
    REFRESH_HASH_SECRET: str
    
    # Operacional
    AUTO_CREATE_TABLES: bool = True    
    
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
    
    # CORS
    ENABLE_CORS: bool = False
    CORS_ORIGINS: str = "https://miapp.com, http://localhost:3000"

    # SWAGGER
    ENABLE_DOCS: bool = True
    
    # Proxy
    TRUST_PROXY_LAN: bool = False
    TRUST_PROXY_LAN_CIDRS: str = (
    "127.0.0.1/32,"
    "10.0.0.0/8,"
    "172.16.0.0/12,"
    "192.168.0.0/16,"
    "::1/128,"
    "fc00::/7"
    )
    TRUST_PROXY_WAN: bool = False
    TRUST_PROXY_WAN_IPS: str = ""      # ej: "203.0.113.10,198.51.100.22"
    TRUST_PROXY_WAN_CIDRS: str = ""    # ej: "203.0.113.0/24,198.51.100.22/32"
    TRUST_PROXY_HEADER_ORDER: str = "x-forwarded-for,x-real-ip"
    
    # JWT hardening (mismo issuer/audience para TODOS los JWT)
    JWT_ISSUER: str = "moveon_api"
    JWT_AUDIENCE: str = "moveon_app"
    
    model_config = SettingsConfigDict(
        env_file=".env",
        case_sensitive=True, # Distingue entre mayusculas y minusculas.
        extra="ignore" # Si hay variables extra en el .env, no da error.
    )

settings = Settings() # type: ignore
