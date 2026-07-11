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
- seguridad de los scripts de limpieza seed

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

### Seeds disponibles

- `seed_usuarios.py`: crea 30 cuentas demo y 4 actividades por cuenta.
- `seed_aportillo.py`: crea actividades seed en las cuentas configuradas de Aportillo.
- `seed_galen.py`: crea actividades seed en las cuentas configuradas de Galen.
- `seed_limpieza.py`: elimina de forma interactiva los grupos seed seleccionados.
- `seed_catalogo.py`: centraliza versiones e identidades estables compartidas por los scripts.

### Limpieza interactiva

Desde la raíz del backend:

```powershell
python .\scripts\seed_limpieza.py
```

El script pregunta por separado si se desea borrar:

1. Los 30 usuarios demo de `seed_usuarios.py` y todos sus datos.
2. Solo las actividades creadas por `seed_aportillo.py`.
3. Solo las actividades seed creadas para `Galen` y `GalenG`.

Antes del borrado muestra los registros encontrados y pide una confirmación final.

La limpieza de actividades se limita a sus prefijos `client_local_id`; las actividades reales sin prefijo seed se conservan. Los acumulados del perfil se corrigen en la misma transacción.

Las cuentas `Galen` y `GalenG` están protegidas frente al borrado de usuarios independientemente de si acceden con contraseña, Google o ambos métodos. Si se elige limpiar Galen, solo se eliminan sus actividades con prefijo seed.

## Uso recomendado

- Ejecuta los seeds únicamente contra bases de datos de desarrollo o pruebas.
- Comprueba que el `.env` apunta a la base de datos correcta antes de lanzar la limpieza.
- Revisa el resumen mostrado y confirma el borrado únicamente si coincide con lo esperado.
