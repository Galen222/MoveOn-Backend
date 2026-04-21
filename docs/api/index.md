# Referencia API

Esta sección recoge la referencia técnica del backend directamente desde el código fuente.

## Organización

| Área | Contenido |
|---|---|
| Módulos raíz | Configuración, autenticación, base de datos, esquemas y entrada principal. |
| Routers | Endpoints HTTP y dependencias FastAPI. |
| Services | Lógica de negocio y coordinación con base de datos, correo y almacenamiento. |
| Middlewares | Comportamiento transversal de las peticiones. |
| Utils | Validaciones, cálculos y helpers. |
| Domain | Enums y tipos compartidos. |
| Scripts | Utilidades operativas y semillas de datos. |
| Tests | Mapa de cobertura y organización del test suite. |

## Criterio de lectura

Empieza por **Módulos raíz** y después entra en **Routers** y **Services** para seguir el flujo normal de una petición.
