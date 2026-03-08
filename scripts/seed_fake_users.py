from __future__ import annotations

"""
Seeder de 20 usuarios fake para MoveOn V30.

Reglas pedidas:
- Contraseña fija para todos: Prueba123
- Emails: usuario1@prueba.com ... usuario20@prueba.com

Características:
- Reutiliza schemas.Registro + user_service.registrar_nuevo_usuario()
  para no saltarse validaciones ni el hash de contraseña.
- Si lo ejecutas varias veces, los usuarios ya existentes se omiten.
- Pensado para desarrollo.

Uso:
    python scripts/seed_fake_users.py
"""

from pathlib import Path
import sys

# Permite importar módulos del proyecto al ejecutar el script con:
# python scripts/<nombre_script>.py
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import asyncio
from datetime import date, datetime, timedelta, timezone

import schemas
import database
from domain.enums import ProvinciaEspaña, GeneroUsuario
from services import user_service


PASSWORD_FIJA = "Prueba123"
VERSION_TERMINOS = "1.0"
TOTAL_USUARIOS = 20

# 20 nombres válidos (sin números para respetar validar_nombre_real_logica)
DATOS_USUARIOS = [
    ("usuario1", "Carlos Martin", ProvinciaEspaña.MADRID, GeneroUsuario.HOMBRE),
    ("usuario2", "Laura Garcia", ProvinciaEspaña.BARCELONA, GeneroUsuario.MUJER),
    ("usuario3", "Diego Perez", ProvinciaEspaña.VALENCIA, GeneroUsuario.HOMBRE),
    ("usuario4", "Marta Lopez", ProvinciaEspaña.SEVILLA, GeneroUsuario.MUJER),
    ("usuario5", "Pablo Sanchez", ProvinciaEspaña.MALAGA, GeneroUsuario.HOMBRE),
    ("usuario6", "Elena Romero", ProvinciaEspaña.MURCIA, GeneroUsuario.MUJER),
    ("usuario7", "Javier Torres", ProvinciaEspaña.ZARAGOZA, GeneroUsuario.HOMBRE),
    ("usuario8", "Sara Navarro", ProvinciaEspaña.A_CORUNA, GeneroUsuario.MUJER),
    ("usuario9", "Hugo Diaz", ProvinciaEspaña.VALLADOLID, GeneroUsuario.HOMBRE),
    ("usuario10", "Paula Moreno", ProvinciaEspaña.ALICANTE, GeneroUsuario.MUJER),
    ("usuario11", "Mario Ruiz", ProvinciaEspaña.GRANADA, GeneroUsuario.HOMBRE),
    ("usuario12", "Nora Jimenez", ProvinciaEspaña.TARRAGONA, GeneroUsuario.MUJER),
    ("usuario13", "Victor Gil", ProvinciaEspaña.BURGOS, GeneroUsuario.HOMBRE),
    ("usuario14", "Lucia Ramos", ProvinciaEspaña.GIRONA, GeneroUsuario.MUJER),
    ("usuario15", "Raul Dominguez", ProvinciaEspaña.LEON, GeneroUsuario.HOMBRE),
    ("usuario16", "Irene Alvarez", ProvinciaEspaña.CADIZ, GeneroUsuario.MUJER),
    ("usuario17", "Tomas Hernandez", ProvinciaEspaña.NAVARRA, GeneroUsuario.HOMBRE),
    ("usuario18", "Sonia Gomez", ProvinciaEspaña.SALAMANCA, GeneroUsuario.MUJER),
    ("usuario19", "Alex Vazquez", ProvinciaEspaña.CANTABRIA, GeneroUsuario.OTRO),
    ("usuario20", "Eva Martin", ProvinciaEspaña.ASTURIAS, GeneroUsuario.MUJER),
]


def ahora_utc() -> datetime:
    """Devuelve la fecha/hora actual en UTC."""
    return datetime.now(timezone.utc)


async def crear_usuarios() -> None:
    """Crea 20 usuarios fake fijos para la base de datos de desarrollo."""
    creados = 0
    omitidos = 0

    async with database.AsyncSessionLocal() as db:
        for indice, (nombre_usuario, nombre_real, provincia, genero) in enumerate(DATOS_USUARIOS, start=1):
            email = f"usuario{indice}@prueba.com"

            datos = schemas.Registro(
                nombre_usuario=nombre_usuario,
                email=email,
                password=PASSWORD_FIJA,
                nombre_real=nombre_real,
                fecha_nacimiento=date(1990, 1, min(indice, 28)),
                genero=genero,
                altura=165 + (indice % 16),
                peso=round(60 + (indice * 1.7), 1),
                provincia=provincia,
                perfil_visible=True,
                acepta_terminos=True,
                fecha_aceptacion_terminos=ahora_utc() - timedelta(minutes=5),
                version_terminos=VERSION_TERMINOS,
            )

            try:
                respuesta = await user_service.registrar_nuevo_usuario(db, datos)
                print(f"[OK] Creado {respuesta['nombre_usuario']} -> {email}")
                creados += 1
            except Exception as exc:
                # En desarrollo es normal relanzar el seed y encontrarse duplicados.
                print(f"[SKIP] {nombre_usuario} ({email}) -> {exc}")
                omitidos += 1

    print()
    print(f"Usuarios creados: {creados}")
    print(f"Usuarios omitidos: {omitidos}")
    print(f"Contraseña común: {PASSWORD_FIJA}")


if __name__ == "__main__":
    asyncio.run(crear_usuarios())
