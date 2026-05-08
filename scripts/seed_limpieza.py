"""Limpia únicamente actividades creadas por los seeders.

Este script NO borra usuarios ni borra todas las actividades de un usuario.
Solo elimina actividades cuyo ``client_local_id`` empieza por uno de los
prefijos activos de seed definidos en ``SEED_CLIENT_LOCAL_ID_PREFIXES``.
"""

from __future__ import annotations

from pathlib import Path
import sys

# Añadir la raíz del proyecto ANTES de importar módulos internos.
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import asyncio  # noqa: E402
from collections import Counter  # noqa: E402

from sqlalchemy import or_, select  # noqa: E402

import database  # noqa: E402

# La limpieza se limita a client_local_id LIKE '<prefijo>%'.
SEED_CLIENT_LOCAL_ID_PREFIXES = (
    "usuarios-v2-30-",
    "aportillo-v3-60-",
    "galen-v3-60-",
)


def construir_filtro_seed():
    """Devuelve un filtro SQLAlchemy que solo apunta a actividades seed."""
    return or_(
        *(
            database.Actividad.client_local_id.like(f"{prefix}%")
            for prefix in SEED_CLIENT_LOCAL_ID_PREFIXES
        )
    )


def detectar_prefijo(client_local_id: str | None) -> str:
    """Identifica qué seed generó una actividad a partir de su client_local_id."""
    if not client_local_id:
        return "sin-client-local-id"

    for prefix in SEED_CLIENT_LOCAL_ID_PREFIXES:
        if client_local_id.startswith(prefix):
            return prefix.rstrip("-")

    return "otro"


async def listar_actividades_seed(db):
    """Carga únicamente actividades cuyo client_local_id pertenece a los seeds."""
    result = await db.execute(
        select(database.Actividad).where(construir_filtro_seed())
    )
    return list(result.scalars().all())


async def limpiar_actividades_seed() -> int:
    """Borra solo actividades de seed y devuelve cuántas ha afectado."""
    await database.init_db()

    if database.AsyncSessionLocal is None:
        raise RuntimeError("No se pudo inicializar AsyncSessionLocal")

    async with database.AsyncSessionLocal() as db:
        actividades = await listar_actividades_seed(db)
        resumen = Counter(
            detectar_prefijo(getattr(actividad, "client_local_id", None))
            for actividad in actividades
        )

        print("=== Limpieza de actividades seed ===")
        print(f"Actividades seed encontradas: {len(actividades)}")

        for prefijo, total in sorted(resumen.items()):
            print(f"- {prefijo}: {total}")

        if not actividades:
            print("No se ha borrado nada.")
            return 0

        for actividad in actividades:
            await db.delete(actividad)

        await db.commit()
        print(f"Actividades seed borradas: {len(actividades)}")
        print("Usuarios conservados: todos")
        return len(actividades)


async def main() -> None:
    await limpiar_actividades_seed()


if __name__ == "__main__":
    asyncio.run(main())
