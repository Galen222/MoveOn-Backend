from __future__ import annotations

from pathlib import Path
import sys

# Permite importar módulos internos al ejecutar:
# python scripts/seed_fake_data.py
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import asyncio
from datetime import date, datetime, timedelta, timezone
from typing import Iterable

from sqlalchemy import func, select

import database
import schemas
from domain.enums import GeneroUsuario, ProvinciaEspaña, TipoActividad
from services import activities_service, user_service

"""
Seeder unificado de datos fake para MoveOn.

Qué hace:
- Crea 20 usuarios de prueba distribuidos en distintas provincias.
- Reutiliza schemas.Registro + user_service.registrar_nuevo_usuario()
  para respetar validaciones y hash de contraseña.
- Genera hasta 6 actividades completas por usuario con datos coherentes:
  distancia, duraciones, ritmos, velocidades, pausas, calorías,
  URL de mapa, polilínea y fecha.
- Es idempotente: si relanzas el seed, reutiliza usuarios existentes
  y solo crea actividades hasta llegar al objetivo por usuario.

Uso:
    python scripts/seed_fake_data.py
"""

PASSWORD_FIJA = "Prueba123"
VERSION_TERMINOS = "1.0"
TOTAL_USUARIOS = 20
ACTIVIDADES_POR_USUARIO = 6

USUARIOS = [
    ("usuario1", "Carlos Martin", "usuario1@prueba.com", ProvinciaEspaña.MADRID, GeneroUsuario.HOMBRE),
    ("usuario2", "Laura Garcia", "usuario2@prueba.com", ProvinciaEspaña.BARCELONA, GeneroUsuario.MUJER),
    ("usuario3", "Diego Perez", "usuario3@prueba.com", ProvinciaEspaña.VALENCIA, GeneroUsuario.HOMBRE),
    ("usuario4", "Marta Lopez", "usuario4@prueba.com", ProvinciaEspaña.SEVILLA, GeneroUsuario.MUJER),
    ("usuario5", "Pablo Sanchez", "usuario5@prueba.com", ProvinciaEspaña.MALAGA, GeneroUsuario.HOMBRE),
    ("usuario6", "Elena Romero", "usuario6@prueba.com", ProvinciaEspaña.MURCIA, GeneroUsuario.MUJER),
    ("usuario7", "Javier Torres", "usuario7@prueba.com", ProvinciaEspaña.ZARAGOZA, GeneroUsuario.HOMBRE),
    ("usuario8", "Sara Navarro", "usuario8@prueba.com", ProvinciaEspaña.A_CORUNA, GeneroUsuario.MUJER),
    ("usuario9", "Hugo Diaz", "usuario9@prueba.com", ProvinciaEspaña.VALLADOLID, GeneroUsuario.HOMBRE),
    ("usuario10", "Paula Moreno", "usuario10@prueba.com", ProvinciaEspaña.ALICANTE, GeneroUsuario.MUJER),
    ("usuario11", "Mario Ruiz", "usuario11@prueba.com", ProvinciaEspaña.GRANADA, GeneroUsuario.HOMBRE),
    ("usuario12", "Nora Jimenez", "usuario12@prueba.com", ProvinciaEspaña.TARRAGONA, GeneroUsuario.MUJER),
    ("usuario13", "Victor Gil", "usuario13@prueba.com", ProvinciaEspaña.BURGOS, GeneroUsuario.HOMBRE),
    ("usuario14", "Lucia Ramos", "usuario14@prueba.com", ProvinciaEspaña.GIRONA, GeneroUsuario.MUJER),
    ("usuario15", "Raul Dominguez", "usuario15@prueba.com", ProvinciaEspaña.LEON, GeneroUsuario.HOMBRE),
    ("usuario16", "Irene Alvarez", "usuario16@prueba.com", ProvinciaEspaña.CADIZ, GeneroUsuario.MUJER),
    ("usuario17", "Tomas Hernandez", "usuario17@prueba.com", ProvinciaEspaña.NAVARRA, GeneroUsuario.HOMBRE),
    ("usuario18", "Sonia Gomez", "usuario18@prueba.com", ProvinciaEspaña.SALAMANCA, GeneroUsuario.MUJER),
    ("usuario19", "Alex Vazquez", "usuario19@prueba.com", ProvinciaEspaña.CANTABRIA, GeneroUsuario.OTRO),
    ("usuario20", "Eva Martin", "usuario20@prueba.com", ProvinciaEspaña.ASTURIAS, GeneroUsuario.MUJER),
]

# Plantillas completas y válidas de actividades.
# Todas usan el esquema enriquecido actual del backend.
RUTA_TEMPLATES = [
    {
        "nombre": "Parque Central 3.8K",
        "tipo": TipoActividad.CORRER,
        "distancia": 3781,
        "duracion_movimiento": 1267,
        "duracion_parado": 45,
        "duracion_pausa_manual": 0,
        "calorias_quemadas": 272,
        "ritmo_medio_movimiento": 335,
        "ritmo_medio_total": 347,
        "velocidad_media_x100": 1074,
        "velocidad_max_x100": 1332,
        "auto_pausas": 0,
        "pausas_manuales": 0,
        "alertas_velocidad": 0,
        "ruta_polilinea": "skuuFvgoUfEcQzE{T~HoQjQgPjZoNjWoI~AgBfRcHnFiLo@sNgG{MiJwG{EsS",
        "ruta_mapa_url": "https://www.openstreetmap.org/?mlat=40.41430&mlon=-3.68490#map=15/40.41430/-3.68490",
    },
    {
        "nombre": "Ribera 7.9K",
        "tipo": TipoActividad.CORRER,
        "distancia": 7935,
        "duracion_movimiento": 2698,
        "duracion_parado": 80,
        "duracion_pausa_manual": 30,
        "calorias_quemadas": 571,
        "ritmo_medio_movimiento": 340,
        "ritmo_medio_total": 350,
        "velocidad_media_x100": 1059,
        "velocidad_max_x100": 1377,
        "auto_pausas": 1,
        "pausas_manuales": 1,
        "alertas_velocidad": 0,
        "ruta_polilinea": "kkruFj_vUbG{T~HsXnF_XdBv\\oG|YkLs\\kQxPqQfIuPjAo]gGkXkLwUoQmM_HoL}IyGyRcBaZaJ~^uMb\\oQ~XwQjRvVbQrb@eJ",
        "ruta_mapa_url": "https://www.openstreetmap.org/?mlat=40.40820&mlon=-3.70310#map=15/40.40820/-3.70310",
    },
    {
        "nombre": "Bosque 9.5K",
        "tipo": TipoActividad.CORRER,
        "distancia": 9543,
        "duracion_movimiento": 3388,
        "duracion_parado": 95,
        "duracion_pausa_manual": 45,
        "calorias_quemadas": 687,
        "ritmo_medio_movimiento": 355,
        "ritmo_medio_total": 365,
        "velocidad_media_x100": 1014,
        "velocidad_max_x100": 1369,
        "auto_pausas": 1,
        "pausas_manuales": 1,
        "alertas_velocidad": 1,
        "ruta_polilinea": "sauuFfz{UwLwVwLsXkM_VuJz^cChb@fEh`@jOt^nZxQ|\\~Ff\\eInZsOvQwXjHkY_Cu]mMmXsTgSiYoU{Tq`@oNaUgJsNrSgH",
        "ruta_mapa_url": "https://www.openstreetmap.org/?mlat=40.41440&mlon=-3.73000#map=15/40.41440/-3.73000",
    },
    {
        "nombre": "Vía Verde 6.3K",
        "tipo": TipoActividad.CAMINAR,
        "distancia": 6288,
        "duracion_movimiento": 4244,
        "duracion_parado": 120,
        "duracion_pausa_manual": 60,
        "calorias_quemadas": 302,
        "ritmo_medio_movimiento": 675,
        "ritmo_medio_total": 694,
        "velocidad_media_x100": 533,
        "velocidad_max_x100": 629,
        "auto_pausas": 2,
        "pausas_manuales": 1,
        "alertas_velocidad": 0,
        "ruta_polilinea": "oo~uFvouUgJcVcGgYg@k[~DaYzJwVmFsLaQ_CoTuImPeRkEmUw@qYfGaY~QmPvUmGjWbLrTfU|QhYdBxZgI~XqOzToVjNmVfGkR{DcNqIgP}A_N{@",
        "ruta_mapa_url": "https://www.openstreetmap.org/?mlat=40.46070&mlon=-3.70750#map=15/40.46070/-3.70750",
    },
    {
        "nombre": "Anillo 8.7K",
        "tipo": TipoActividad.CORRER,
        "distancia": 8678,
        "duracion_movimiento": 3037,
        "duracion_parado": 75,
        "duracion_pausa_manual": 30,
        "calorias_quemadas": 625,
        "ritmo_medio_movimiento": 350,
        "ritmo_medio_total": 359,
        "velocidad_media_x100": 1029,
        "velocidad_max_x100": 1358,
        "auto_pausas": 1,
        "pausas_manuales": 1,
        "alertas_velocidad": 1,
        "ruta_polilinea": "ot~uFrx`U{Jo_@wG_b@?_b@vGg^nNo\\vWmRj_@uDj_@eCz]mGhZoNpSsUhLgYfEaZqC{Y}J{ViQyQqWwIe\\?w\\vGqZrNoVnWoQl_@cDz^?~HgYf@{TsI",
        "ruta_mapa_url": "https://www.openstreetmap.org/?mlat=40.45890&mlon=-3.59890#map=15/40.45890/-3.59890",
    },
    {
        "nombre": "Jardines 5.1K",
        "tipo": TipoActividad.CAMINAR,
        "distancia": 5069,
        "duracion_movimiento": 3548,
        "duracion_parado": 150,
        "duracion_pausa_manual": 90,
        "calorias_quemadas": 243,
        "ritmo_medio_movimiento": 700,
        "ritmo_medio_total": 730,
        "velocidad_media_x100": 514,
        "velocidad_max_x100": 596,
        "auto_pausas": 2,
        "pausas_manuales": 2,
        "alertas_velocidad": 0,
        "ruta_polilinea": "wj|uFvc}ToFwQkCgT?gTbEuRnJmOtPuHpXeA|XcFjUcKjNuOjGqQ~@oR_DgQiJmNmPcIvUcD|W~@vWbEyT~HoP|LmJpQeCxQ?lQeDzEoP{@wLwG",
        "ruta_mapa_url": "https://www.openstreetmap.org/?mlat=40.44990&mlon=-3.58640#map=15/40.44990/-3.58640",
    },
    {
        "nombre": "Mirador 5.2K",
        "tipo": TipoActividad.CORRER,
        "distancia": 5216,
        "duracion_movimiento": 1721,
        "duracion_parado": 40,
        "duracion_pausa_manual": 0,
        "calorias_quemadas": 376,
        "ritmo_medio_movimiento": 330,
        "ritmo_medio_total": 338,
        "velocidad_media_x100": 1091,
        "velocidad_max_x100": 1386,
        "auto_pausas": 0,
        "pausas_manuales": 0,
        "alertas_velocidad": 0,
        "ruta_polilinea": "_apuFfliUgJ{OcG_S{@cVvDgUlJkQfPoJpZgBzZaFvWkKrPoO~IuQbBwR{DqPiJuLqP{FqSf@qSxDqP`KoJlQeCrQbBwQfJmL|OkGdU?fJkRvB{T{@eG",
        "ruta_mapa_url": "https://www.openstreetmap.org/?mlat=40.38800&mlon=-3.64880#map=15/40.38800/-3.64880",
    },
]

# Nombres de ruta personalizados por provincia para que los datos se vean
# más realistas al inspeccionarlos.
NOMBRE_PREFIJO_PROVINCIA = {
    ProvinciaEspaña.MADRID: "Madrid",
    ProvinciaEspaña.BARCELONA: "Barcelona",
    ProvinciaEspaña.VALENCIA: "Valencia",
    ProvinciaEspaña.SEVILLA: "Sevilla",
    ProvinciaEspaña.MALAGA: "Málaga",
    ProvinciaEspaña.MURCIA: "Murcia",
    ProvinciaEspaña.ZARAGOZA: "Zaragoza",
    ProvinciaEspaña.A_CORUNA: "A Coruña",
    ProvinciaEspaña.VALLADOLID: "Valladolid",
    ProvinciaEspaña.ALICANTE: "Alicante",
    ProvinciaEspaña.GRANADA: "Granada",
    ProvinciaEspaña.TARRAGONA: "Tarragona",
    ProvinciaEspaña.BURGOS: "Burgos",
    ProvinciaEspaña.GIRONA: "Girona",
    ProvinciaEspaña.LEON: "León",
    ProvinciaEspaña.CADIZ: "Cádiz",
    ProvinciaEspaña.NAVARRA: "Navarra",
    ProvinciaEspaña.SALAMANCA: "Salamanca",
    ProvinciaEspaña.CANTABRIA: "Cantabria",
    ProvinciaEspaña.ASTURIAS: "Asturias",
}


def ahora_utc() -> datetime:
    """Devuelve la fecha/hora actual en UTC."""
    return datetime.now(timezone.utc)


def actividad_count_query(usuario_id: int):
    return select(func.count(database.Actividad.id)).where(
        database.Actividad.usuario_id == usuario_id
    )


async def obtener_usuario_existente(db, nombre_usuario: str, email: str):
    """Busca usuario por nombre o email en modo case-insensitive."""
    result = await db.execute(
        select(database.Usuario).where(
            (func.lower(database.Usuario.nombre_usuario) == nombre_usuario.lower())
            | (func.lower(database.Usuario.email) == email.lower())
        )
    )
    return result.scalar_one_or_none()


async def obtener_o_crear_usuario(
    db,
    indice: int,
    nombre_usuario: str,
    nombre_real: str,
    email: str,
    provincia: ProvinciaEspaña,
    genero: GeneroUsuario,
):
    """Crea el usuario si no existe; si existe, lo reutiliza."""
    existente = await obtener_usuario_existente(db, nombre_usuario, email)
    if existente is not None:
        print(f"[SKIP] {nombre_usuario} -> ya existe")
        return existente, False

    fecha_aceptacion = ahora_utc() - timedelta(minutes=5 + indice)
    fecha_nacimiento = date(1982 + (indice % 12), ((indice % 12) + 1), min(10 + indice, 28))

    datos = schemas.Registro(
        nombre_usuario=nombre_usuario,
        email=email,
        password=PASSWORD_FIJA,
        nombre_real=nombre_real,
        fecha_nacimiento=fecha_nacimiento,
        genero=genero,
        altura=160 + (indice % 24),
        peso=round(55.0 + (indice * 1.85), 1),
        provincia=provincia,
        perfil_visible=True,
        acepta_terminos=True,
        fecha_aceptacion_terminos=fecha_aceptacion,
        version_terminos=VERSION_TERMINOS,
    )

    respuesta = await user_service.registrar_nuevo_usuario(db, datos)
    usuario = await obtener_usuario_existente(db, nombre_usuario, email)
    print(f"[OK] Creado {respuesta['nombre_usuario']} -> {email}")
    return usuario, True


def _clamp(value: int, minimum: int, maximum: int) -> int:
    return max(minimum, min(maximum, value))


def construir_actividad(
    indice_usuario: int,
    indice_actividad: int,
    provincia: ProvinciaEspaña,
) -> schemas.GuardarActividad:
    """
    Construye una actividad completa y coherente con el schema actual.

    Se parte de una plantilla válida y se aplican ligeras variaciones
    deterministas para que no todos los usuarios tengan exactamente
    las mismas métricas.
    """
    base = dict(RUTA_TEMPLATES[(indice_usuario + indice_actividad - 2) % len(RUTA_TEMPLATES)])

    # Ajustes pequeños y deterministas por usuario/actividad.
    delta_distancia = ((indice_usuario * 37 + indice_actividad * 19) % 241) - 120
    delta_mov = ((indice_usuario * 13 + indice_actividad * 17) % 91) - 45
    delta_stop = ((indice_usuario + indice_actividad * 3) % 31) - 10

    distancia = _clamp(int(base["distancia"]) + delta_distancia, 1200, 25000)
    duracion_movimiento = _clamp(int(base["duracion_movimiento"]) + delta_mov, 600, 20000)
    duracion_parado = _clamp(int(base["duracion_parado"]) + delta_stop, 0, 2400)
    duracion_total = duracion_movimiento + duracion_parado

    tipo = base["tipo"]
    if tipo == TipoActividad.CORRER:
        # Mantiene ritmos de running realistas.
        ritmo_medio_movimiento = _clamp(round(duracion_movimiento / (distancia / 1000)), 240, 480)
        ritmo_medio_total = _clamp(round(duracion_total / (distancia / 1000)), 250, 520)
    else:
        # Mantiene ritmos de caminata realistas.
        ritmo_medio_movimiento = _clamp(round(duracion_movimiento / (distancia / 1000)), 520, 950)
        ritmo_medio_total = _clamp(round(duracion_total / (distancia / 1000)), 540, 1000)

    velocidad_media_x100 = _clamp(round((distancia / duracion_movimiento) * 360), 300, 1800)
    velocidad_max_x100 = _clamp(
        velocidad_media_x100 + 120 + ((indice_usuario + indice_actividad) % 180),
        velocidad_media_x100,
        3000,
    )

    if tipo == TipoActividad.CORRER:
        calorias = _clamp(round(distancia * 0.072), 150, 1600)
        auto_pausas = (indice_usuario + indice_actividad) % 2
        pausas_manuales = 1 if (indice_usuario + indice_actividad) % 5 == 0 else 0
        alertas_velocidad = 1 if indice_actividad % 3 == 0 else 0
        duracion_pausa_manual = 20 if pausas_manuales else 0
    else:
        calorias = _clamp(round(distancia * 0.040), 80, 900)
        auto_pausas = 1 + ((indice_usuario + indice_actividad) % 2)
        pausas_manuales = 1 if indice_actividad % 2 == 0 else 0
        alertas_velocidad = 0
        duracion_pausa_manual = 45 if pausas_manuales else 0

    # Garantiza coherencia adicional.
    duracion_pausa_manual = min(duracion_pausa_manual, duracion_total)

    dias_atras = (indice_usuario * 4 + indice_actividad * 3) % 75 + 1
    horas_atras = (indice_usuario * 2 + indice_actividad) % 20
    minutos_atras = (indice_usuario * 7 + indice_actividad * 11) % 60

    fecha_ruta = ahora_utc() - timedelta(
        days=dias_atras,
        hours=horas_atras,
        minutes=minutos_atras,
    )

    prefijo = NOMBRE_PREFIJO_PROVINCIA.get(provincia, provincia.value)
    nombre_ruta = f"{prefijo} · {base['nombre']}"

    return schemas.GuardarActividad(
        tipo=tipo,
        distancia=distancia,
        duracion_total=duracion_total,
        duracion_movimiento=duracion_movimiento,
        duracion_parado=duracion_parado,
        duracion_pausa_manual=duracion_pausa_manual,
        calorias_quemadas=calorias,
        ritmo_medio_movimiento=ritmo_medio_movimiento,
        ritmo_medio_total=ritmo_medio_total,
        velocidad_media_x100=velocidad_media_x100,
        velocidad_max_x100=velocidad_max_x100,
        auto_pausas=auto_pausas,
        pausas_manuales=pausas_manuales,
        alertas_velocidad=alertas_velocidad,
        ruta_polilinea=base["ruta_polilinea"],
        ruta_mapa_url=base["ruta_mapa_url"],
        fecha_ruta=fecha_ruta,
    )


async def contar_actividades_usuario(db, usuario_id: int) -> int:
    """Cuenta cuántas actividades tiene ya el usuario."""
    result = await db.execute(actividad_count_query(usuario_id))
    return int(result.scalar_one() or 0)


async def crear_actividades_faltantes(
    db,
    usuario,
    indice_usuario: int,
    provincia: ProvinciaEspaña,
) -> int:
    """Crea solo las actividades necesarias hasta llegar al objetivo."""
    existentes = await contar_actividades_usuario(db, usuario.id)
    if existentes >= ACTIVIDADES_POR_USUARIO:
        print(
            f"[SKIP] {usuario.nombre_usuario}: ya tiene {existentes} actividades"
        )
        return 0

    creadas = 0
    for indice_actividad in range(existentes + 1, ACTIVIDADES_POR_USUARIO + 1):
        try:
            datos = construir_actividad(indice_usuario, indice_actividad, provincia)
            respuesta = await activities_service.crear_actividad(db, usuario.id, datos)
            creadas += 1
            print(
                f"[OK] {usuario.nombre_usuario}: actividad {respuesta['id']} "
                f"{respuesta['tipo']} {respuesta['distancia']}m"
            )
        except Exception as exc:
            print(
                f"[SKIP] {usuario.nombre_usuario}: actividad #{indice_actividad} -> {exc}"
            )

    return creadas


async def seed_fake_data() -> None:
    """Punto de entrada del seed unificado."""
    await database.init_db()

    if database.AsyncSessionLocal is None:
        print("No se ha podido inicializar AsyncSessionLocal.")
        return

    usuarios_creados = 0
    actividades_creadas = 0

    async with database.AsyncSessionLocal() as db:
        for indice, (nombre_usuario, nombre_real, email, provincia, genero) in enumerate(
            USUARIOS, start=1
        ):
            usuario, creado = await obtener_o_crear_usuario(
                db=db,
                indice=indice,
                nombre_usuario=nombre_usuario,
                nombre_real=nombre_real,
                email=email,
                provincia=provincia,
                genero=genero,
            )

            if usuario is None:
                print(f"[ERROR] No se pudo recuperar el usuario {nombre_usuario}")
                continue

            if creado:
                usuarios_creados += 1

            actividades_creadas += await crear_actividades_faltantes(
                db=db,
                usuario=usuario,
                indice_usuario=indice,
                provincia=provincia,
            )

    print()
    print("=== Seed finalizado ===")
    print(f"Usuarios creados: {usuarios_creados}")
    print(f"Actividades creadas: {actividades_creadas}")
    print(f"Usuarios objetivo: {TOTAL_USUARIOS}")
    print(f"Actividades objetivo por usuario: {ACTIVIDADES_POR_USUARIO}")
    print(f"Contraseña común: {PASSWORD_FIJA}")


if __name__ == "__main__":
    asyncio.run(seed_fake_data())
