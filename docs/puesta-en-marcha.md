# Puesta en marcha

## Requisitos previos

- Python 3.11 o superior.
- Entorno virtual activo.
- PostgreSQL disponible.
- Variables de entorno configuradas en el archivo correspondiente.

## Instalación de dependencias

```powershell
.\venv\Scripts\activate
pip install -r requirements.txt
```

Para construir la documentación del proyecto:

```powershell
pip install -r requirements-docs.txt
```

## Generación del HTML de documentación

```powershell
mkdocs build --clean
start .\site\index.html
```

## Arranque del backend

```powershell
uvicorn main:app --reload
```

## Recomendaciones iniciales

1. Verificar que la conexión a base de datos es correcta.
2. Confirmar que las migraciones están aplicadas.
3. Lanzar el backend en local antes de ejecutar scripts de soporte.
4. Generar la documentación HTML para revisar que la API queda indexada.
