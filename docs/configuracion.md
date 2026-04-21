# Configuración

La configuración de la aplicación se centraliza en `config.py` mediante la clase `Settings`.

## Grupos principales de configuración

### Base de datos

- Usuario, contraseña, host, puerto y nombre de base de datos.
- Parámetros de pool como tamaño, overflow, timeout y recycle.

### Seguridad y sesión

- Secretos de acceso y refresh.
- Algoritmo JWT.
- Identificador y secreto de sesión de aplicación.
- Emisor y audiencia JWT.

### Almacenamiento

- Tipo de almacenamiento (`local` o `cloudinary`).
- Directorio de subida local.
- Credenciales de Cloudinary.

### Email

- Host, puerto, usuario y contraseña SMTP.
- Timeouts y reintentos.

### Límite de tasa

- Activación de rate limiting por IP.
- Activación de rate limiting por identidad.
- Límites específicos por operación.

### Proxy y cabeceras

- Confianza en proxies LAN y WAN.
- Orden de cabeceras para resolución de IP.
- HSTS, CSP, X-Frame-Options, Referrer-Policy y Permissions-Policy.

### Documentación y operación

- Activación de Swagger con `ENABLE_DOCS`.
- Creación automática de tablas.
- Nivel y formato de logs.

## Recomendaciones

- Mantén los secretos fuera del repositorio.
- Usa valores distintos por entorno.
- Revisa especialmente JWT, email y almacenamiento antes de despliegue.
- Usa `.env.example` como referencia base y adapta los valores reales a tu entorno.

## Referencia automática

La definición completa de la configuración está documentada en la referencia API del módulo `config`.
