from __future__ import annotations

from pathlib import Path
import sys

# Permite importar módulos del proyecto al ejecutar el script con:
# python scripts/<nombre_script>.py
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

# scripts/cleanup_fake_data.py

"""
Script para borrar los 20 usuarios fake de prueba y sus datos asociados.

Qué elimina:
- Actividades de esos usuarios.
- Sesiones refresh de esos usuarios.
- Los propios usuarios fake.

Usuarios objetivo:
- usuario1 .. usuario20
- usuario1@prueba.com .. usuario20@prueba.com

Uso:
    python scripts/cleanup_fake_data.py

Notas:
- Pensado para entorno de desarrollo.
- Hace commit real en la base de datos configurada en tu .env.
- Si algún usuario no existe, simplemente no lo borra.
"""

import asyncio
from sqlalchemy import delete, select

import database


# =========================================================
# Configuración del borrado
# =========================================================

EMAILS_FAKE = [f"usuario{i}@prueba.com" for i in range(1, 21)]
USERNAMES_FAKE = [f"usuario{i}" for i in range(1, 21)]


# =========================================================
# Lógica principal
# =========================================================

async def cleanup_fake_data() -> None:
    """
    Borra actividades, sesiones refresh y usuarios fake.
    """
    async with database.AsyncSessionLocal() as db:
        # Localizar los usuarios fake existentes.
        result = await db.execute(
            select(database.Usuario.id, database.Usuario.nombre_usuario, database.Usuario.email).where(
                database.Usuario.email.in_(EMAILS_FAKE)
            )
        )
        filas = result.all()

        if not filas:
            print("No se han encontrado usuarios fake para borrar.")
            return

        user_ids = [fila.id for fila in filas]
        usernames = [fila.nombre_usuario for fila in filas]
        emails = [fila.email for fila in filas]

        print("Usuarios encontrados para borrar:")
        for nombre_usuario, email in zip(usernames, emails):
            print(f"- {nombre_usuario} ({email})")

        # Borrar actividades asociadas.
        delete_actividades = await db.execute(
            delete(database.Actividad).where(database.Actividad.usuario_id.in_(user_ids))
        )

        # Borrar sesiones refresh asociadas.
        delete_sesiones = await db.execute(
            delete(database.SesionRefresh).where(database.SesionRefresh.usuario_id.in_(user_ids))
        )

        # Borrar usuarios fake.
        delete_usuarios = await db.execute(
            delete(database.Usuario).where(
                database.Usuario.id.in_(user_ids),
                database.Usuario.nombre_usuario.in_(USERNAMES_FAKE),
                database.Usuario.email.in_(EMAILS_FAKE),
            )
        )

        await db.commit()

        actividades_borradas = delete_actividades.rowcount or 0
        sesiones_borradas = delete_sesiones.rowcount or 0
        usuarios_borrados = delete_usuarios.rowcount or 0

        print()
        print("Borrado completado:")
        print(f"- Actividades borradas: {actividades_borradas}")
        print(f"- Sesiones refresh borradas: {sesiones_borradas}")
        print(f"- Usuarios borrados: {usuarios_borrados}")


async def main() -> None:
    """Punto de entrada del script."""
    await cleanup_fake_data()


if __name__ == "__main__":
    asyncio.run(main())
