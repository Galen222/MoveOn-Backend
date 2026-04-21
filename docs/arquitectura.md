# Arquitectura

## Visión general

El backend sigue una organización por capas ligera:

1. **Routers**: reciben la petición HTTP, aplican dependencias y delegan.
2. **Services**: contienen la lógica de negocio y coordinan operaciones.
3. **Database / ORM**: define entidades, acceso a datos y sesión asíncrona.
4. **Utils / Domain**: concentran validaciones, cálculos y enums reutilizables.
5. **Middlewares**: aplican seguridad transversal y control de peticiones.

## Entrada principal

`main.py` crea la aplicación FastAPI, registra middlewares, configura el ciclo de vida y monta las rutas.

## Seguridad

La seguridad se reparte entre varios módulos:

- `auth.py` para JWT, handshake y autenticación.
- `ip_rate_limit.py` para limitación por IP.
- `services/identity_rate_limit.py` para limitación por identidad.
- `middlewares/security_headers.py` para cabeceras de seguridad.

## Organización funcional

### Gestión de acceso

- Handshake de aplicación.
- Login, refresh y logout.
- Autenticación social.
- Gestión de recuperación de contraseña.

### Gestión de usuarios

- Registro.
- Perfil propio y perfil público.
- Actualización de datos.
- Gestión de imagen.
- Ranking y búsquedas.

### Gestión de actividades

- Guardado de actividad.
- Diagnóstico de actividad.
- Consulta y listados.
- Estadísticas o resúmenes asociados.

## Persistencia

`database.py` centraliza el motor asíncrono de SQLAlchemy, el `sessionmaker`, los modelos ORM y distintas validaciones de persistencia.

## Migrations

La carpeta `alembic/` contiene la configuración y revisiones de migración de la base de datos.

## Scripts y soporte

La carpeta `scripts/` se utiliza para sembrado de datos y limpieza de entornos de prueba.
