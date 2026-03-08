from __future__ import annotations

"""
Seeder de actividades fake para los usuarios usuario1@prueba.com ... usuario20@prueba.com.

Características:
- Reutiliza schemas.GuardarActividad + activities_service.crear_actividad()
  para no saltarse validaciones ni la lógica que suma total_metros.
- Crea varias actividades por usuario.
- Pensado para desarrollo.

Uso:
    python scripts/seed_fake_activities.py
"""

from pathlib import Path
import sys

# Permite importar módulos del proyecto al ejecutar el script con:
# python scripts/<nombre_script>.py
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import asyncio
import random
from datetime import datetime, timedelta, timezone

from sqlalchemy import select

import database
import schemas
from domain.enums import TipoActividad
from services import activities_service


TOTAL_USUARIOS = 20
ACTIVIDADES_POR_USUARIO = 6


def ahora_utc() -> datetime:
    """Devuelve la fecha/hora actual en UTC."""
    return datetime.now(timezone.utc)


def construir_actividad(indice_usuario: int, indice_actividad: int) -> schemas.GuardarActividad:
    """
    Construye una actividad válida para el esquema actual.
    """
    tipo = TipoActividad.CAMINAR if (indice_usuario + indice_actividad) % 2 == 0 else TipoActividad.CORRER

    if tipo == TipoActividad.CAMINAR:
        distancia = random.randint(1200, 9000)
        duracion = random.randint(900, 7200)
        calorias = random.randint(90, 500)
    else:
        distancia = random.randint(3000, 18000)
        duracion = random.randint(900, 7200)
        calorias = random.randint(220, 1200)

    # Siempre en el pasado, respetando tu validador de fecha_ruta.
    dias_atras = (indice_usuario * 3 + indice_actividad * 2) % 60 + 1
    horas_atras = (indice_usuario + indice_actividad) % 20
    fecha_ruta = ahora_utc() - timedelta(days=dias_atras, hours=horas_atras, minutes=random.randint(0, 59))

    return schemas.GuardarActividad(
        tipo=tipo,
        distancia=int(distancia),
        duracion=int(duracion),
        calorias_quemadas=int(calorias),
        ruta_polilinea=None,
        ruta_mapa_url=None,
        fecha_ruta=fecha_ruta,
    )


async def obtener_usuarios_objetivo(db) -> list:
    """Recupera los 20 usuarios fake por email exacto."""
    emails = [f"usuario{i}@prueba.com" for i in range(1, TOTAL_USUARIOS + 1)]
    result = await db.execute(
        select(database.Usuario)
        .where(database.Usuario.email.in_(emails))
        .order_by(database.Usuario.id.asc())
    )
    return list(result.scalars().all())


async def crear_actividades() -> None:
    """Crea actividades fake para los usuarios de prueba."""
    total_actividades = 0

    async with database.AsyncSessionLocal() as db:
        usuarios = await obtener_usuarios_objetivo(db)

        if not usuarios:
            print("No se han encontrado usuarios usuario1@prueba.com ... usuario20@prueba.com")
            print("Primero ejecuta el seed de usuarios.")
            return

        for indice_usuario, usuario in enumerate(usuarios, start=1):
            creadas_usuario = 0

            for indice_actividad in range(1, ACTIVIDADES_POR_USUARIO + 1):
                try:
                    datos = construir_actividad(indice_usuario, indice_actividad)
                    respuesta = await activities_service.crear_actividad(db, usuario.id, datos)
                    creadas_usuario += 1
                    total_actividades += 1
                    print(
                        f"[OK] {usuario.nombre_usuario}: actividad {respuesta['id']} "
                        f"{respuesta['tipo']} {respuesta['distancia']}m"
                    )
                except Exception as exc:
                    print(
                        f"[SKIP] {usuario.nombre_usuario}: actividad #{indice_actividad} -> {exc}"
                    )

            print(f"[USER] {usuario.nombre_usuario}: {creadas_usuario} actividades creadas")

    print()
    print(f"Total de actividades creadas: {total_actividades}")


if __name__ == "__main__":
    asyncio.run(crear_actividades())
