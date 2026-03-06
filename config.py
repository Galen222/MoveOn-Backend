# config.py

from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    # Base de Datos
    DB_USER: str
    DB_PASSWORD: str
    DB_HOST: str
    DB_PORT: int
    DB_NAME: str
    DB_POOL_SIZE: int = 10
    DB_MAX_OVERFLOW: int = 20
    DB_POOL_TIMEOUT: int = 30
    DB_POOL_RECYCLE: int = 1800
    
    # Operacional
    AUTO_CREATE_TABLES: bool = False   
    
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
    
    # Hash pepper para HMAC
    REFRESH_HASH_SECRET: str
    CODE_HASH_SECRET: str
    
    # Almacenamiento
    STORAGE_TYPE: str = "cloudinary"
    UPLOAD_DIR: str = "uploads"
    
    # Cloudinary
    CLOUDINARY_CLOUD_NAME: str = ""
    CLOUDINARY_API_KEY: str = ""
    CLOUDINARY_API_SECRET: str = ""
    
    # Tamaño imagenes de perfil
    MAX_IMAGE_PIXELS: int = 13_000_000      # 13MP por defecto
    MAX_IMAGE_BYTES: int = 2 * 1024 * 1024  # 2MB por defecto
    IMAGE_JPEG_QUALITY: int = 85            # calidad del re-encode JPEG
    
    # Email
    EMAIL_HOST: str
    EMAIL_PORT: int = 587
    EMAIL_USER: str
    EMAIL_PASS: str
    
    # JWT hardening (mismo issuer/audience para TODOS los JWT)
    JWT_ISSUER: str = "moveon_api"
    JWT_AUDIENCE: str = "moveon_app"
    
    # CORS
    ENABLE_CORS: bool = False
    CORS_ORIGINS: str = "https://miapp.com, http://localhost:3000"
    
    # SWAGGER
    ENABLE_DOCS: bool = False
    
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
    
    # Security headers
    ENABLE_SECURITY_HEADERS: bool = False
    SEC_HEADERS_RESPECT_X_FORWARDED_PROTO: bool = False
    SEC_HEADERS_HSTS_SECONDS: int = 31536000
    SEC_HEADERS_HSTS_INCLUDE_SUBDOMAINS: bool = True
    SEC_HEADERS_HSTS_PRELOAD: bool = False
    SEC_HEADERS_X_FRAME_OPTIONS: str = "DENY"  # o SAMEORIGIN
    SEC_HEADERS_REFERRER_POLICY: str = "no-referrer"
    SEC_HEADERS_PERMISSIONS_POLICY: str = "geolocation=(), microphone=(), camera=()"
    SEC_HEADERS_CONTENT_SECURITY_POLICY: str = ""  # opcional (en APIs suele ir vacío)
    
    # Rate Limit
    ENABLE_RATE_LIMIT_IP: bool = True      # SlowAPI (por IP)
    ENABLE_RATE_LIMIT_ID: bool = True     # In-memory (por email/usuario)
    # IP Públicos / Auth
    RL_HANDSHAKE: str = "60/minute"
    RL_LOGIN: str = "20/minute"
    RL_REFRESH: str = "60/minute"
    RL_LOGOUT: str = "60/minute"
    RL_PASSWORD_SOLICITAR: str = "10/hour"
    RL_PASSWORD_CONFIRMAR: str = "20/hour"
    RL_REGISTRO: str = "10/hour"
    # IP Usuarios (autenticados)
    RL_PERFIL_INFO: str = "600/minute"
    RL_PERFIL_PUBLICO: str = "600/minute"
    RL_PERFIL_FOTO: str = "60/minute"
    RL_PERFIL_ACTUALIZAR: str = "120/minute"
    RL_PERFIL_BORRAR: str = "10/hour"
    RL_PERFIL_BUSCAR: str = "240/minute"
    RL_RANKING: str = "240/minute"
    # IP Actividades (autenticados)
    RL_ACTIVIDAD_GUARDAR: str = "60/minute"
    RL_ACTIVIDAD_OBTENER: str = "600/minute"
    RL_ACTIVIDAD_OBTENER_TODAS: str = "240/minute"
    RL_ACTIVIDAD_BORRAR: str = "120/minute"
    RL_ACTIVIDAD_BORRAR_TODAS: str = "10/hour"    
    # IP Extra (main.py)
    RL_ROOT: str = "120/minute"
    RL_FAVICON: str = "120/minute"
    # ID Usuarios (autenticados)
    RL_REGISTRO_ID: str = "5/hour"    
    RL_LOGIN_ID: str = "10/minute"
    RL_PASSWORD_SOLICITAR_ID: str = "5/hour"
    RL_PASSWORD_CONFIRMAR_ID: str = "10/hour"
    
    # --- Limpieza de sesiones refresh ---
    REFRESH_SESSION_CLEANUP_DAYS: int = 30

    # --- Recuperación de contraseña (OTP) ---
    RECOVERY_CODE_EXPIRE_MINUTES: int = 15
    
    model_config = SettingsConfigDict(
        env_file=".env",
        case_sensitive=True, # Distingue entre mayusculas y minusculas.
        extra="ignore" # Si hay variables extra en el .env, no da error.
    )
    
settings = Settings() # type: ignore
