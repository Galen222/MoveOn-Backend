# Pruebas y scripts

## Pruebas automatizadas

La carpeta `tests/` agrupa pruebas para:

- autenticación
- configuración
- routers
- servicios
- middlewares
- validadores
- utilidades y esquemas

### Ejecución

```powershell
pytest
```

O bien:

```powershell
pytest -q
```

## Scripts de soporte

La carpeta `scripts/` incluye utilidades orientadas a desarrollo y datos de prueba.

### Scripts detectados

- `cleanup_fake_data.py`
- `seed_aportillo.py`
- `seed_fake_data.py`
- `seed_galen.py`

## Uso recomendado

- Ejecuta los seeds únicamente contra bases de datos de desarrollo o pruebas.
- Documenta cualquier dependencia previa de datos antes de lanzar un script.
- Mantén esta sección actualizada si se añaden nuevos scripts operativos.
