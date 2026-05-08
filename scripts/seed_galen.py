"""Genera 60 actividades madrileñas para cuentas existentes de ``Galen``.

Configuración principal:
- Edita ``TARGET_USERNAMES`` para poner una o varias cuentas.
- El script NO crea usuarios; si una cuenta no existe, la omite.
- Si una cuenta ya tiene estas seeds, no las vuelve a insertar.

El seeder construye actividades completas y las persiste mediante
``activities_service`` para pasar por las mismas validaciones y actualizaciones
que la aplicación real.
"""

from __future__ import annotations

from pathlib import Path
import sys

# Añadir la raíz del proyecto ANTES de importar módulos internos.
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import asyncio  # noqa: E402
from datetime import datetime, timedelta, timezone  # noqa: E402

from sqlalchemy import and_, or_, select  # noqa: E402

import database  # noqa: E402
import schemas  # noqa: E402
from domain.enums import TipoActividad  # noqa: E402
from services import activities_service  # noqa: E402

SEED_NAME = 'Galen'
SEED_VERSION = 'galen-v2-60'
TOTAL_ACTIVIDADES = 60

# Edita esta lista para sembrar una o varias cuentas.
# La búsqueda es EXACTA por nombre_usuario.
TARGET_USERNAMES = ['Galen', 'GalenG']

ACTIVIDADES_BASE = [
    {
        "nombre": 'Retiro tempo',
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
        "ruta_polilinea": 'skuuFvgoUfEcQzE{T~HoQjQgPjZoNjWoI~AgBfRcHnFiLo@sNgG{MiJwG{EsS',
        "ruta_mapa_url": 'https://www.openstreetmap.org/?mlat=40.41430&mlon=-3.68490# map=15/40.41430/-3.68490',
    },
    {
        "nombre": 'Madrid Río progresivo',
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
        "ruta_polilinea": 'gfsuFjgrUcGcGkHoPwGoPwBgT~HgOfOgEbQfEnKbQjCfT{E~RsIjMwLzE',
        "ruta_mapa_url": 'https://www.openstreetmap.org/?mlat=40.40820&mlon=-3.70310# map=15/40.40820/-3.70310',
    },
    {
        "nombre": 'Casa de Campo fondo',
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
        "ruta_polilinea": '_mtuFnowUgJwQgOwLkMgOcL_SnKwQ~RkC~RzE~MnP~HvVoAvVsI~MkH~C',
        "ruta_mapa_url": 'https://www.openstreetmap.org/?mlat=40.41440&mlon=-3.73000# map=15/40.41440/-3.73000',
    },
    {
        "nombre": 'Dehesa recovery walk',
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
        "ruta_polilinea": 'oo~uFvouUgJcVcGgYg@k[~DaYzJwVmFsLaQ_CoTuImPeRkEmUw@qYfGaY~QmPvUmGjWbLrTfU|QhYdBxZgI~XqOzToVjNmVfGkR{DcNqIgP}A_N{@',
        "ruta_mapa_url": 'https://www.openstreetmap.org/?mlat=40.46070&mlon=-3.70750# map=15/40.46070/-3.70750',
    },
    {
        "nombre": 'Juan Carlos I controlado',
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
        "ruta_polilinea": 'ot~uFrx`U{Jo_@wG_b@?_b@vGg^nNo\\vWmRj_@uDj_@eCz]mGhZoNpSsUhLgYfEaZqC{Y}J{ViQyQqWwIe\\?w\\vGqZrNoVnWoQl_@cDz^?~HgYf@{TsI',
        "ruta_mapa_url": 'https://www.openstreetmap.org/?mlat=40.45890&mlon=-3.59890# map=15/40.45890/-3.59890',
    },
    {
        "nombre": 'Capricho paseo largo',
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
        "ruta_polilinea": 'wj|uFvc}ToFwQkCgT?gTbEuRnJmOtPuHpXeA|XcFjUcKjNuOjGqQ~@oR_DgQiJmNmPcIvUcD|W~@vWbEyT~HoP|LmJpQeCxQ?lQeDzEoP{@wLwG',
        "ruta_mapa_url": 'https://www.openstreetmap.org/?mlat=40.44990&mlon=-3.58640# map=15/40.44990/-3.58640',
    },
    {
        "nombre": 'Tío Pío series',
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
        "ruta_polilinea": '_houF~sgU_IwL{JwL_IgOrDgT~M_IvQR~MrIvGvQg@~RkHfOgJbGkHR',
        "ruta_mapa_url": 'https://www.openstreetmap.org/?mlat=40.38800&mlon=-3.64880# map=15/40.38800/-3.64880',
    },
    {
        "nombre": 'Castellana control',
        "tipo": TipoActividad.CORRER,
        "distancia": 6420,
        "duracion_movimiento": 2183,
        "duracion_parado": 55,
        "duracion_pausa_manual": 0,
        "calorias_quemadas": 462,
        "ritmo_medio_movimiento": 340,
        "ritmo_medio_total": 349,
        "velocidad_media_x100": 1059,
        "velocidad_max_x100": 1325,
        "auto_pausas": 0,
        "pausas_manuales": 0,
        "alertas_velocidad": 0,
        "ruta_polilinea": '_xguF|aoUcEwNgHeMoLgHwOa@qM~DuHjIiDpLc@pMa',
        "ruta_mapa_url": 'https://www.openstreetmap.org/?mlat=40.43810&mlon=-3.69190# map=15/40.43810/-3.69190',
    },
]

ZONAS_EXTRA = ['Retiro', 'Madrid Río', 'Casa de Campo', 'Dehesa', 'Juan Carlos I', 'El Capricho', 'Tío Pío', 'Castellana', 'Salamanca', 'Chamberí', 'Lavapiés', 'Moncloa']


def ahora_utc() -> datetime:
    """Devuelve una referencia horaria UTC consciente de zona."""
    return datetime.now(timezone.utc)


def obtener_usernames_objetivo() -> tuple[str, ...]:
    """Obtiene las cuentas objetivo desde ``TARGET_USERNAMES``.

    La búsqueda en base de datos será exacta por ``nombre_usuario``. Se eliminan
    espacios y duplicados manteniendo el orden definido en la lista editable.
    """
    usernames: list[str] = []
    seen: set[str] = set()

    for value in TARGET_USERNAMES:
        username = str(value).strip()
        if username and username not in seen:
            usernames.append(username)
            seen.add(username)

    return tuple(usernames)


def generar_fechas_seed(
    total: int = TOTAL_ACTIVIDADES,
    referencia: datetime | None = None,
) -> list[datetime]:
    """Genera una fecha por día desde hace ``total`` días hasta ayer."""
    ref = referencia or ahora_utc()
    medianoche_utc = ref.astimezone(timezone.utc).replace(
        hour=0,
        minute=0,
        second=0,
        microsecond=0,
    )
    horas_plan = (6, 7, 18, 19, 8, 20, 7, 18, 6, 19)
    minutos_plan = (5, 15, 25, 35, 45, 10, 20, 30, 40, 50)

    fechas: list[datetime] = []
    for indice in range(total):
        dias_atras = total - indice
        dia = medianoche_utc - timedelta(days=dias_atras)
        fechas.append(
            dia
            + timedelta(
                hours=horas_plan[indice % len(horas_plan)],
                minutes=minutos_plan[(indice * 3) % len(minutos_plan)],
            )
        )

    return fechas


def aplicar_variacion(base: dict, indice: int, fecha_ruta: datetime) -> dict:
    """Construye una actividad completa y coherente a partir de una plantilla."""
    ciclo = indice // len(ACTIVIDADES_BASE)
    offset = (indice % 7) - 3  # -3, -2, -1, 0, 1, 2, 3
    factor = 0.94 + ((indice % 11) * 0.018) + (ciclo * 0.004)

    distancia = int(round(base["distancia"] * factor + (offset * 42) + ciclo * 28))
    distancia = max(2400, distancia)

    if base["tipo"] == TipoActividad.CORRER:
        ritmo_mov = max(
            295,
            int(base["ritmo_medio_movimiento"] + offset * 5 + ciclo * 2),
        )
        ritmo_total = max(
            ritmo_mov + 6,
            int(base["ritmo_medio_total"] + offset * 6 + ciclo * 2),
        )
        velocidad_media = max(800, int(round(360000 / ritmo_mov)))
        velocidad_max = max(
            velocidad_media + 170,
            int(base["velocidad_max_x100"] + offset * 10 + ciclo * 9),
        )
        pausas = max(0, int(base["pausas_manuales"] + (1 if offset >= 3 else 0)))
        auto_pausas = max(
            0,
            int(base["auto_pausas"] + (1 if ciclo >= 4 and offset < 0 else 0)),
        )
        duracion_mov = max(900, int(round(distancia * ritmo_mov / 1000)))
        duracion_parado = max(
            20,
            int(base["duracion_parado"] + offset * 7 + ciclo * 4),
        )
        duracion_pausa_manual = max(
            0,
            int(
                base["duracion_pausa_manual"]
                + (12 if pausas > base["pausas_manuales"] else 0)
            ),
        )
        calorias = max(
            170,
            int(
                base["calorias_quemadas"]
                + (distancia - base["distancia"]) * 0.058
                + ciclo * 7
            ),
        )
        alertas = (
            1
            if velocidad_max >= 1350 and indice % 4 == 0
            else int(base["alertas_velocidad"])
        )
    else:
        ritmo_mov = max(
            540,
            int(base["ritmo_medio_movimiento"] + offset * 9 + ciclo * 6),
        )
        ritmo_total = max(
            ritmo_mov + 10,
            int(base["ritmo_medio_total"] + offset * 10 + ciclo * 6),
        )
        velocidad_media = max(420, int(round(360000 / ritmo_mov)))
        velocidad_max = max(
            velocidad_media + 60,
            int(base["velocidad_max_x100"] + offset * 7 + ciclo * 5),
        )
        pausas = max(1, int(base["pausas_manuales"] + (1 if indice % 6 == 0 else 0)))
        auto_pausas = max(
            1,
            int(base["auto_pausas"] + (1 if ciclo >= 3 and indice % 5 == 0 else 0)),
        )
        duracion_mov = max(1800, int(round(distancia * ritmo_mov / 1000)))
        duracion_parado = max(
            60,
            int(base["duracion_parado"] + offset * 10 + ciclo * 6),
        )
        duracion_pausa_manual = max(
            30,
            int(
                base["duracion_pausa_manual"]
                + (15 if pausas > base["pausas_manuales"] else 0)
            ),
        )
        calorias = max(
            140,
            int(
                base["calorias_quemadas"]
                + (distancia - base["distancia"]) * 0.038
                + ciclo * 5
            ),
        )
        alertas = 0

    zona = ZONAS_EXTRA[indice % len(ZONAS_EXTRA)]
    km = f"{distancia / 1000:.1f}K"

    return {
        "client_local_id": f"{SEED_VERSION}-{indice + 1:03d}",
        "nombre": f"{zona} {base['nombre']} #{indice + 1:02d} {km}",
        "tipo": base["tipo"],
        "distancia": distancia,
        "duracion_movimiento": duracion_mov,
        "duracion_parado": duracion_parado,
        "duracion_pausa_manual": duracion_pausa_manual,
        "calorias_quemadas": calorias,
        "ritmo_medio_movimiento": ritmo_mov,
        "ritmo_medio_total": ritmo_total,
        "velocidad_media_x100": velocidad_media,
        "velocidad_max_x100": velocidad_max,
        "auto_pausas": auto_pausas,
        "pausas_manuales": pausas,
        "alertas_velocidad": alertas,
        "ruta_polilinea": base["ruta_polilinea"],
        "ruta_mapa_url": base["ruta_mapa_url"],
        "fecha_ruta": fecha_ruta,
    }


def generar_plan_actividades(
    total: int = TOTAL_ACTIVIDADES,
    referencia: datetime | None = None,
) -> list[dict]:
    """Genera el mismo plan de actividades para todas las cuentas objetivo."""
    fechas = generar_fechas_seed(total=total, referencia=referencia)
    return [
        aplicar_variacion(ACTIVIDADES_BASE[i % len(ACTIVIDADES_BASE)], i, fechas[i])
        for i in range(total)
    ]


def derivar_ritmo_maximo(
    ritmo_medio_movimiento: int,
    velocidad_max_x100: int,
    tipo: TipoActividad,
) -> int:
    """Calcula un ritmo máximo plausible a partir del ritmo medio y velocidad pico."""
    ritmo_medio_movimiento = max(1, int(ritmo_medio_movimiento))
    velocidad_max_x100 = max(1, int(velocidad_max_x100))

    velocidad_max_kmh = velocidad_max_x100 / 100.0
    pace_desde_velocidad_max = max(1, int(round(3600.0 / velocidad_max_kmh)))

    es_correr = tipo == TipoActividad.CORRER
    mejora_maxima = 60 if es_correr else 90
    ratio_minimo = 0.72 if es_correr else 0.80
    suelo = max(
        int(round(ritmo_medio_movimiento * ratio_minimo)),
        ritmo_medio_movimiento - mejora_maxima,
    )
    techo = max(1, ritmo_medio_movimiento - (15 if es_correr else 10))

    candidato = min(pace_desde_velocidad_max, techo)
    return max(1, min(candidato, techo) if candidato >= suelo else suelo)


def construir_actividad(ruta: dict) -> schemas.GuardarActividad:
    """Transforma un diccionario del plan en un payload ``GuardarActividad`` válido."""
    duracion_total = int(ruta["duracion_movimiento"]) + int(ruta["duracion_parado"])

    return schemas.GuardarActividad(
        client_local_id=ruta["client_local_id"],
        tipo=ruta["tipo"],
        distancia=int(ruta["distancia"]),
        duracion_total=duracion_total,
        duracion_movimiento=int(ruta["duracion_movimiento"]),
        duracion_parado=int(ruta["duracion_parado"]),
        duracion_pausa_manual=int(ruta["duracion_pausa_manual"]),
        calorias_quemadas=int(ruta["calorias_quemadas"]),
        ritmo_medio_movimiento=int(ruta["ritmo_medio_movimiento"]),
        ritmo_medio_total=int(ruta["ritmo_medio_total"]),
        ritmo_maximo=int(
            ruta.get("ritmo_maximo")
            or derivar_ritmo_maximo(
                int(ruta["ritmo_medio_movimiento"]),
                int(ruta["velocidad_max_x100"]),
                ruta["tipo"],
            )
        ),
        velocidad_media_x100=int(ruta["velocidad_media_x100"]),
        velocidad_max_x100=int(ruta["velocidad_max_x100"]),
        auto_pausas=int(ruta["auto_pausas"]),
        pausas_manuales=int(ruta["pausas_manuales"]),
        alertas_velocidad=int(ruta["alertas_velocidad"]),
        ruta_polilinea=ruta["ruta_polilinea"],
        ruta_mapa_url=ruta["ruta_mapa_url"],
        fecha_ruta=ruta["fecha_ruta"],
    )


async def obtener_usuarios_objetivo(
    db,
    usernames: tuple[str, ...],
) -> tuple[list[database.Usuario], list[str]]:
    """Localiza las cuentas por nombre exacto y devuelve también las faltantes."""
    if not usernames:
        return [], []

    result = await db.execute(
        select(database.Usuario).where(database.Usuario.nombre_usuario.in_(usernames))
    )
    encontrados = list(result.scalars().all())
    por_username = {usuario.nombre_usuario: usuario for usuario in encontrados}

    usuarios_ordenados = [
        por_username[username] for username in usernames if username in por_username
    ]
    faltantes = [username for username in usernames if username not in por_username]

    return usuarios_ordenados, faltantes


async def obtener_seed_client_local_ids_existentes(
    db,
    usuario_id: int,
    plan: list[dict],
) -> set[str]:
    """Devuelve las seeds de este plan que ya existen para el usuario."""
    client_local_ids = [ruta["client_local_id"] for ruta in plan]
    if not client_local_ids:
        return set()

    result = await db.execute(
        select(database.Actividad.client_local_id).where(
            database.Actividad.usuario_id == usuario_id,
            database.Actividad.client_local_id.in_(client_local_ids),
        )
    )
    return {value for value in result.scalars().all() if value}


async def actividad_ya_existe(
    db,
    usuario_id: int,
    ruta: dict,
    client_local_ids_existentes: set[str],
) -> bool:
    """Detecta si ya hay una actividad equivalente en la cuenta objetivo.

    Prioriza ``client_local_id`` para que el seed sea idempotente aunque se
    ejecute otro día. Mantiene una segunda huella por fecha, tipo y distancia
    para evitar duplicados si alguna carga previa no tenía ``client_local_id``.
    """
    if ruta["client_local_id"] in client_local_ids_existentes:
        return True

    existente = await db.execute(
        select(database.Actividad.id).where(
            and_(
                database.Actividad.usuario_id == usuario_id,
                or_(
                    database.Actividad.client_local_id == ruta["client_local_id"],
                    and_(
                        database.Actividad.fecha_ruta == ruta["fecha_ruta"],
                        database.Actividad.tipo == ruta["tipo"].value,
                        database.Actividad.distancia == ruta["distancia"],
                    ),
                ),
            )
        )
    )
    return existente.scalar_one_or_none() is not None


async def sembrar_plan_en_usuario(
    db,
    usuario: database.Usuario,
    plan: list[dict],
) -> tuple[int, int]:
    """Inserta el plan completo en una cuenta concreta si todavía no existe."""
    total_creadas = 0
    total_omitidas = 0
    client_local_ids_existentes = await obtener_seed_client_local_ids_existentes(
        db,
        usuario.id,
        plan,
    )

    if len(client_local_ids_existentes) == len(plan):
        print(
            f"[SKIP] {usuario.nombre_usuario}: ya tiene las {len(plan)} seeds "
            f"de {SEED_VERSION}. No se inserta nada."
        )
        return 0, len(plan)

    for indice, ruta in enumerate(plan, start=1):
        try:
            if await actividad_ya_existe(
                db,
                usuario.id,
                ruta,
                client_local_ids_existentes,
            ):
                print(
                    f"[SKIP] {usuario.nombre_usuario}: actividad # {indice} ya existe "
                    f"({ruta['client_local_id']} - {ruta['fecha_ruta'].date().isoformat()})"
                )
                total_omitidas += 1
                continue

            datos = construir_actividad(ruta)
            respuesta = await activities_service.crear_actividad(db, usuario.id, datos)
            client_local_ids_existentes.add(ruta["client_local_id"])
            total_creadas += 1
            print(
                f"[OK] {usuario.nombre_usuario}: actividad {respuesta['id']} "
                f"- {ruta['nombre']} - {respuesta['tipo']} - {respuesta['distancia']}m "
                f"- {ruta['fecha_ruta'].date().isoformat()}"
            )
        except Exception as exc:
            await db.rollback()
            total_omitidas += 1
            print(
                f"[SKIP] {usuario.nombre_usuario}: actividad # {indice} "
                f"({ruta['nombre']}) -> {exc}"
            )

    return total_creadas, total_omitidas


async def crear_actividades_seed() -> None:
    """Genera actividades recientes para una o varias cuentas existentes."""
    await database.init_db()

    if database.AsyncSessionLocal is None:
        print("No se ha podido inicializar AsyncSessionLocal.")
        return

    usernames = obtener_usernames_objetivo()
    referencia = ahora_utc()
    plan = generar_plan_actividades(referencia=referencia)

    async with database.AsyncSessionLocal() as db:
        usuarios, faltantes = await obtener_usuarios_objetivo(db, usernames)

        for username in faltantes:
            print(f"[MISS] No se ha encontrado el usuario exacto '{username}'.")

        if not usuarios:
            print("No hay cuentas objetivo disponibles para sembrar.")
            print("Crea primero las cuentas o edita TARGET_USERNAMES en este archivo.")
            return

        total_creadas_global = 0
        total_omitidas_global = 0

        for usuario in usuarios:
            print()
            print(f"== Sembrando actividades {SEED_NAME} para {usuario.nombre_usuario} ==")
            creadas, omitidas = await sembrar_plan_en_usuario(db, usuario, plan)
            total_creadas_global += creadas
            total_omitidas_global += omitidas

    print()
    print(f"Seed: {SEED_NAME} ({SEED_VERSION})")
    print(f"Usuarios configurados: {', '.join(usernames)}")
    print(
        f"Rango de fechas: {plan[0]['fecha_ruta'].date().isoformat()} -> "
        f"{plan[-1]['fecha_ruta'].date().isoformat()}"
    )
    print(f"Actividades planificadas por usuario: {TOTAL_ACTIVIDADES}")
    print(f"Actividades creadas en total: {total_creadas_global}")
    print(f"Actividades omitidas en total: {total_omitidas_global}")


if __name__ == "__main__":
    asyncio.run(crear_actividades_seed())
