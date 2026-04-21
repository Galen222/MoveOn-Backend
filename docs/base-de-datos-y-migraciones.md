# Base de datos y migraciones

## ORM y acceso a datos

La aplicación usa SQLAlchemy asíncrono para gestionar:

- motor de base de datos
- sesión asíncrona
- modelos ORM
- helpers de inicialización y cierre

El punto central es `database.py`.

## Migraciones

La carpeta `alembic/` contiene:

- `alembic.ini`
- `env.py`
- `versions/`

## Comandos habituales

### Aplicar la última migración

```powershell
alembic upgrade head
```

### Crear una nueva revisión

```powershell
alembic revision -m "descripcion_del_cambio"
```

### Retroceder una revisión

```powershell
alembic downgrade -1
```

## Recomendaciones operativas

- Mantén sincronizados los modelos ORM y las revisiones de Alembic.
- Evita editar revisiones ya aplicadas en otros entornos.
- Revisa la configuración de conexión antes de ejecutar migraciones.
- Si usas datos de prueba, ejecuta los scripts de sembrado solo en desarrollo o testing.
