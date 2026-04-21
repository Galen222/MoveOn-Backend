# Ejecución

## Ejecución en desarrollo

```powershell
uvicorn main:app --reload
```

## Generación del HTML de documentación

```powershell
mkdocs build --clean
start .\site\index.html
```

## Ejecución de scripts auxiliares

Los scripts de la carpeta `scripts/` se pueden lanzar desde la raíz del proyecto con el entorno virtual activo.

Ejemplo:

```powershell
python .\scripts\seed_fake_data.py
```

## Revisión previa a despliegue

- Comprobar variables de entorno.
- Verificar conectividad con la base de datos.
- Ejecutar pruebas principales.
- Regenerar la documentación HTML si hubo cambios de código o docstrings.
