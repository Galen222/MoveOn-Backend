# MoveOn Backend

Documentación de proyecto del backend de **MoveOn**, una API desarrollada con **FastAPI** y **PostgreSQL** para autenticación, gestión de usuarios, rutas y actividades deportivas.

## Qué incluye esta documentación

| Área | Contenido |
|---|---|
| Guías funcionales | Arranque, configuración, ejecución y mantenimiento del proyecto. |
| Arquitectura | Resumen de la organización interna del backend y reparto de responsabilidades. |
| Referencia API | Documentación automática generada a partir de los módulos Python existentes. |
| Operación | Scripts, pruebas y migraciones. |

## Estructura del backend

| Zona | Descripción |
|---|---|
| `main.py` | Punto de entrada y configuración de la aplicación FastAPI. |
| `auth.py` | Autenticación, tokens y seguridad de acceso. |
| `config.py` | Configuración central mediante variables de entorno. |
| `database.py` | Motor de base de datos, modelos ORM y helpers de acceso. |
| `routers/` | Definición de endpoints HTTP. |
| `services/` | Lógica de negocio desacoplada de los routers. |
| `middlewares/` | Middlewares de seguridad, contexto y tamaño de petición. |
| `utils/` | Validaciones y utilidades auxiliares. |
| `domain/` | Enums y tipos de dominio. |
| `scripts/` | Utilidades de soporte y carga de datos. |
| `tests/` | Pruebas automatizadas. |

## Flujo recomendado de lectura

1. **Puesta en marcha** para instalar y levantar el proyecto.
2. **Arquitectura** para entender cómo se reparten responsabilidades.
3. **Configuración** para revisar variables de entorno y banderas operativas.
4. **Referencia API** para navegar por los módulos y clases.

## Generación de la documentación en HTML

```powershell
mkdocs build --clean
start .\site\index.html
```

La salida generada se guardará en la carpeta `site/`.
