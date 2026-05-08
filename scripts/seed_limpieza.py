"""Elimina exclusivamente actividades creadas por los seeds actuales.

Este cleanup NO borra usuarios, sesiones refresh ni datos ajenos. Solo elimina
actividades identificadas por los ``client_local_id`` actuales de:
- ``scripts/seed_galen.py``
- ``scripts/seed_aportillo.py``
- ``scripts/seed_usuarios.py``

La limpieza de Galen y Aportillo no depende de los usernames configurados:
busca los identificadores reservados en todas las cuentas existentes, cubriendo
cuentas actuales y futuras. No incluye huellas legacy de Galen.
"""

from __future__ import annotations

from pathlib import Path
import sys
from collections.abc import Iterable

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import asyncio  # noqa: E402
from sqlalchemy import delete, func, select  # noqa: E402

import database  # noqa: E402

GALEN_SEED_VERSION = "galen-v2-60"
GALEN_TOTAL_ACTIVIDADES = 60
GALEN_CLIENT_LOCAL_IDS = tuple(
    f"{GALEN_SEED_VERSION}-{indice:03d}"
    for indice in range(1, GALEN_TOTAL_ACTIVIDADES + 1)
)

APORTILLO_SEED_VERSION = "aportillo-v2-60"
APORTILLO_TOTAL_ACTIVIDADES = 60
APORTILLO_CLIENT_LOCAL_IDS = tuple(
    f"{APORTILLO_SEED_VERSION}-{indice:03d}"
    for indice in range(1, APORTILLO_TOTAL_ACTIVIDADES + 1)
)

USUARIOS_SEED_VERSION = "usuarios-v1-30u"
USUARIOS_TOTAL = 30
USUARIOS_ACTIVIDADES_POR_USUARIO = 4
USUARIOS_CLIENT_LOCAL_IDS = tuple(
    f"{USUARIOS_SEED_VERSION}-u{indice_usuario:02d}-a{indice_actividad:02d}"
    for indice_usuario in range(1, USUARIOS_TOTAL + 1)
    for indice_actividad in range(1, USUARIOS_ACTIVIDADES_POR_USUARIO + 1)
)


def construir_condicion_client_local_ids(client_local_ids: Iterable[str]):
    """Construye la condición para actividades con IDs de cliente de seed."""
    ids = tuple(client_local_ids)
    if not ids:
        return None
    return database.Actividad.client_local_id.in_(ids)


def pedir_confirmacion(pregunta: str) -> bool:
    """Pide confirmación S/N por consola."""
    while True:
        respuesta = input(f"{pregunta} [S/N]: ").strip().lower()
        if respuesta in {"s", "si", "sí", "y", "yes"}:
            return True
        if respuesta in {"n", "no"}:
            return False
        print("Respuesta no válida. Escribe S o N.")


async def inicializar_base_datos() -> bool:
    """Inicializa la sesión asíncrona de base de datos si hace falta."""
    if database.AsyncSessionLocal is None:
        if hasattr(database, "init_db"):
            await database.init_db()
        elif hasattr(database, "_init_db_objects"):
            database._init_db_objects()

    if database.AsyncSessionLocal is None:
        print("No se ha podido inicializar AsyncSessionLocal.")
        return False

    return True


async def contar_actividades(db, condicion) -> int:
    """Cuenta actividades que cumplen una condición."""
    if condicion is None:
        return 0

    return int(
        (
            await db.execute(
                select(func.count())
                .select_from(database.Actividad)
                .where(condicion)
            )
        ).scalar_one()
        or 0
    )


async def listar_resumen_por_usuario(db, condicion) -> list[tuple[str, str, int]]:
    """Devuelve un resumen de actividades seed agrupadas por usuario."""
    if condicion is None:
        return []

    result = await db.execute(
        select(
            database.Usuario.nombre_usuario,
            database.Usuario.email,
            func.count(database.Actividad.id),
        )
        .join(database.Actividad, database.Actividad.usuario_id == database.Usuario.id)
        .where(condicion)
        .group_by(database.Usuario.id, database.Usuario.nombre_usuario, database.Usuario.email)
        .order_by(database.Usuario.nombre_usuario)
    )

    return [(fila[0], fila[1], int(fila[2])) for fila in result.all()]


def imprimir_resumen(nombre_seed: str, resumen: list[tuple[str, str, int]]) -> None:
    """Muestra por consola qué se ha encontrado para un seed."""
    total = sum(total_usuario for _, _, total_usuario in resumen)

    print()
    print(f"Seed {nombre_seed}: {total} actividades detectadas.")
    if not resumen:
        return

    print("Usuarios afectados:")
    for nombre_usuario, email, total_usuario in resumen:
        print(f"- {nombre_usuario} ({email}): {total_usuario}")


async def borrar_actividades_por_condicion(db, condicion) -> int:
    """Borra solo actividades que cumplen la condición indicada."""
    if condicion is None:
        return 0

    total = await contar_actividades(db, condicion)
    if total == 0:
        return 0

    await db.execute(delete(database.Actividad).where(condicion))
    return total


async def procesar_seed(db, nombre_seed: str, client_local_ids: Iterable[str]) -> int:
    """Muestra resumen, pregunta y borra un grupo de actividades seed."""
    condicion = construir_condicion_client_local_ids(client_local_ids)
    resumen = await listar_resumen_por_usuario(db, condicion)
    imprimir_resumen(nombre_seed, resumen)

    if not pedir_confirmacion(f"¿Borrar las actividades seed actuales de {nombre_seed}?"):
        print(f"[SKIP] No se borran actividades seed de {nombre_seed}.")
        return 0

    return await borrar_actividades_por_condicion(db, condicion)


async def cleanup_fake_data() -> None:
    """Borra, previa confirmación, actividades seed actuales."""
    if not await inicializar_base_datos():
        return

    async with database.AsyncSessionLocal() as db:
        total_galen = 0
        total_aportillo = 0
        total_usuarios = 0

        try:
            total_galen = await procesar_seed(db, "Galen", GALEN_CLIENT_LOCAL_IDS)
            total_aportillo = await procesar_seed(
                db,
                "Aportillo",
                APORTILLO_CLIENT_LOCAL_IDS,
            )
            total_usuarios = await procesar_seed(
                db,
                "usuarios generales",
                USUARIOS_CLIENT_LOCAL_IDS,
            )

            await db.commit()

        except Exception:
            await db.rollback()
            raise

    print()
    print("Borrado completado:")
    print(f"- Actividades seed Galen borradas: {total_galen}")
    print(f"- Actividades seed Aportillo borradas: {total_aportillo}")
    print(f"- Actividades seed usuarios generales borradas: {total_usuarios}")
    print("- Usuarios borrados: 0")
    print("- Sesiones refresh borradas: 0")


async def main() -> None:
    """Punto de entrada CLI."""
    await cleanup_fake_data()


if __name__ == "__main__":
    asyncio.run(main())
