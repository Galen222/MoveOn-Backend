# scripts/cleanup_fake_data.py

"""Elimina exclusivamente los datos simulados creados por el seed general.

El script localiza a los usuarios de prueba por email o nombre de usuario,
borra primero sus actividades y sesiones refresh para respetar la
integridad referencial y, por último, elimina las cuentas semilla.
"""

from __future__ import annotations

from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import asyncio  # noqa: E402
from sqlalchemy import delete, func, or_, select  # noqa: E402

import database  # noqa: E402

"""
Script para borrar exclusivamente los datos creados por scripts/seed_fake_data.py.

Qué elimina:
- Actividades de los usuarios simulados
- Sesiones refresh de esos usuarios
- Los propios usuarios simulados

Usuarios objetivo:
- Emails: prueba01@prueba.com ... prueba20@prueba.com
- Usernames: los 20 usernames definidos en el seed actual

No toca ningún otro usuario ni ningún otro dato fuera de ese conjunto.
Uso:
    python scripts/cleanup_fake_data.py
"""

TOTAL_USUARIOS = 20

EMAILS_FAKE = [f"prueba{i:02d}@prueba.com" for i in range(1, TOTAL_USUARIOS + 1)]

USERNAMES_FAKE = [
    "carlosmartin01",
    "luciafernandez02",
    "javiersanchez03",
    "martalopez04",
    "alejandroruiz05",
    "paulagomez06",
    "danieltorres07",
    "elenanavarro08",
    "sergioromero09",
    "claudiacastro10",
    "adrianortega11",
    "nereamolina12",
    "ivandelgado13",
    "lauravega14",
    "pablogil15",
    "saraherrera16",
    "rubenleon17",
    "andreapena18",
    "davidcruz19",
    "noeliacano20",
]


async def cleanup_fake_data() -> None:
    """Borra de la base de datos el dataset demo generado por el seed masivo.

    Inicializa la sesión si todavía no existe, localiza primero a los usuarios
    objetivo y calcula cuántas actividades, sesiones refresh y cuentas se van a
    eliminar antes de ejecutar el borrado transaccional.
    """
    # Eliminar los datos simulados creados para las pruebas.
    if database.AsyncSessionLocal is None:
        database._init_db_objects()

    if database.AsyncSessionLocal is None:
        print("No se ha podido inicializar AsyncSessionLocal.")
        return

    async with database.AsyncSessionLocal() as db:
        result = await db.execute(
            select(
                database.Usuario.id,
                database.Usuario.nombre_usuario,
                database.Usuario.email,
            ).where(
                or_(
                    database.Usuario.email.in_(EMAILS_FAKE),
                    database.Usuario.nombre_usuario.in_(USERNAMES_FAKE),
                )
            )
        )
        filas = result.all()

        if not filas:
            print("No se han encontrado usuarios simulados para borrar.")
            return

        user_ids = [fila.id for fila in filas]

        print("Usuarios encontrados para borrar:")
        for fila in filas:
            print(f"- {fila.nombre_usuario} ({fila.email})")

        try:
            actividades_borradas = (
                await db.execute(
                    select(func.count())
                    .select_from(database.Actividad)
                    .where(database.Actividad.usuario_id.in_(user_ids))
                )
            ).scalar_one()

            sesiones_borradas = (
                await db.execute(
                    select(func.count())
                    .select_from(database.SesionRefresh)
                    .where(database.SesionRefresh.usuario_id.in_(user_ids))
                )
            ).scalar_one()

            usuarios_borrados = (
                await db.execute(
                    select(func.count())
                    .select_from(database.Usuario)
                    .where(database.Usuario.id.in_(user_ids))
                )
            ).scalar_one()

            await db.execute(
                delete(database.Actividad).where(
                    database.Actividad.usuario_id.in_(user_ids)
                )
            )

            await db.execute(
                delete(database.SesionRefresh).where(
                    database.SesionRefresh.usuario_id.in_(user_ids)
                )
            )

            await db.execute(
                delete(database.Usuario).where(database.Usuario.id.in_(user_ids))
            )

            await db.commit()

        except Exception:
            await db.rollback()
            raise

        print()
        print("Borrado completado:")
        print(f"- Actividades borradas: {actividades_borradas}")
        print(f"- Sesiones refresh borradas: {sesiones_borradas}")
        print(f"- Usuarios borrados: {usuarios_borrados}")


async def main() -> None:
    """Sirve como punto de entrada CLI del script de limpieza.

    Mantiene separada la función principal para poder reutilizarla o probarla
    sin depender del bloque ``if __name__ == "__main__"``.
    """
    await cleanup_fake_data()


if __name__ == "__main__":
    asyncio.run(main())
