# scripts/seed_aportillo.py

"""Incluye un script de apoyo para tareas del proyecto."""

from __future__ import annotations

from pathlib import Path
import sys

# Añadir la raíz del proyecto ANTES de importar módulos internos.
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import asyncio  # noqa: E402
from datetime import datetime, timezone  # noqa: E402

from sqlalchemy import and_, func, select  # noqa: E402

import database  # noqa: E402
import schemas  # noqa: E402
from domain.enums import TipoActividad  # noqa: E402
from services import activities_service  # noqa: E402

"""
Seeder de 30 actividades completas para el usuario existente "aportillo".

Objetivo:
- NO crea el usuario; exige que ya exista en la base de datos.
- Inserta 30 actividades completas y coherentes para pruebas manuales.
- Las fechas están repartidas entre enero de 2026 y el 20 de marzo de 2026.
- Reutiliza schemas.GuardarActividad + activities_service.crear_actividad()
  para respetar validaciones, métricas y acumulados.
- Intenta ser idempotente: si ya existe una actividad del mismo usuario con
  la misma fecha, tipo y distancia, la omite.

Uso:
    python scripts/seed_aportillo_activities_2026.py
"""

TARGET_USERNAME = "aportillo"
TOTAL_ACTIVIDADES = 30

# 30 fechas fijas dentro del rango pedido por el usuario.
FECHAS_SEED = [
    datetime(2026, 1, 2, 7, 15, tzinfo=timezone.utc),
    datetime(2026, 1, 4, 18, 5, tzinfo=timezone.utc),
    datetime(2026, 1, 6, 7, 25, tzinfo=timezone.utc),
    datetime(2026, 1, 8, 19, 10, tzinfo=timezone.utc),
    datetime(2026, 1, 10, 8, 0, tzinfo=timezone.utc),
    datetime(2026, 1, 12, 18, 40, tzinfo=timezone.utc),
    datetime(2026, 1, 14, 7, 35, tzinfo=timezone.utc),
    datetime(2026, 1, 16, 19, 0, tzinfo=timezone.utc),
    datetime(2026, 1, 18, 8, 20, tzinfo=timezone.utc),
    datetime(2026, 1, 21, 18, 25, tzinfo=timezone.utc),
    datetime(2026, 1, 24, 7, 10, tzinfo=timezone.utc),
    datetime(2026, 1, 27, 19, 5, tzinfo=timezone.utc),
    datetime(2026, 1, 30, 8, 15, tzinfo=timezone.utc),
    datetime(2026, 2, 2, 18, 30, tzinfo=timezone.utc),
    datetime(2026, 2, 5, 7, 45, tzinfo=timezone.utc),
    datetime(2026, 2, 8, 18, 15, tzinfo=timezone.utc),
    datetime(2026, 2, 11, 7, 20, tzinfo=timezone.utc),
    datetime(2026, 2, 14, 18, 50, tzinfo=timezone.utc),
    datetime(2026, 2, 17, 8, 10, tzinfo=timezone.utc),
    datetime(2026, 2, 20, 19, 20, tzinfo=timezone.utc),
    datetime(2026, 2, 23, 7, 5, tzinfo=timezone.utc),
    datetime(2026, 2, 26, 18, 45, tzinfo=timezone.utc),
    datetime(2026, 3, 1, 8, 5, tzinfo=timezone.utc),
    datetime(2026, 3, 4, 19, 15, tzinfo=timezone.utc),
    datetime(2026, 3, 7, 7, 40, tzinfo=timezone.utc),
    datetime(2026, 3, 10, 18, 35, tzinfo=timezone.utc),
    datetime(2026, 3, 13, 7, 30, tzinfo=timezone.utc),
    datetime(2026, 3, 16, 19, 25, tzinfo=timezone.utc),
    datetime(2026, 3, 18, 8, 0, tzinfo=timezone.utc),
    datetime(2026, 3, 20, 18, 10, tzinfo=timezone.utc),
]

# Plantillas base con polilíneas válidas ya probadas en el backend.
PLANTILLAS = [
    {
        "nombre": "Retiro tempo",
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
        "ruta_mapa_url": "https://www.openstreetmap.org/?mlat=40.41430&mlon=-3.68490# map=15/40.41430/-3.68490",
    },
    {
        "nombre": "Madrid Río progresivo",
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
        "ruta_polilinea": "gfsuFjgrUcGcGkHoPwGoPwBgT~HgOfOgEbQfEnKbQjCfT{E~RsIjMwLzE",
        "ruta_mapa_url": "https://www.openstreetmap.org/?mlat=40.40820&mlon=-3.70310# map=15/40.40820/-3.70310",
    },
    {
        "nombre": "Casa de Campo fondo",
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
        "ruta_polilinea": "_mtuFnowUgJwQgOwLkMgOcL_SnKwQ~RkC~RzE~MnP~HvVoAvVsI~MkH~C",
        "ruta_mapa_url": "https://www.openstreetmap.org/?mlat=40.41440&mlon=-3.73000# map=15/40.41440/-3.73000",
    },
    {
        "nombre": "Dehesa recovery walk",
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
        "ruta_mapa_url": "https://www.openstreetmap.org/?mlat=40.46070&mlon=-3.70750# map=15/40.46070/-3.70750",
    },
    {
        "nombre": "Capricho paseo largo",
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
        "ruta_mapa_url": "https://www.openstreetmap.org/?mlat=40.44990&mlon=-3.58640# map=15/40.44990/-3.58640",
    },
    {
        "nombre": "Tío Pío series",
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
        "ruta_polilinea": "_houF~sgU_IwL{JwL_IgOrDgT~M_IvQR~MrIvGvQg@~RkHfOgJbGkHR",
        "ruta_mapa_url": "https://www.openstreetmap.org/?mlat=40.38800&mlon=-3.64880# map=15/40.38800/-3.64880",
    },
]


def _aplicar_variacion(base: dict, indice: int, fecha_ruta: datetime) -> dict:
    """
    Construye una actividad completa a partir de una plantilla base.

    Se añaden pequeñas variaciones deterministas para que no salgan 30 copias
    idénticas, pero manteniendo métricas coherentes con las validaciones del
    backend.
    """
    ciclo = indice // len(PLANTILLAS)
    offset = (indice % 5) - 2  # -2, -1, 0, 1, 2

    distancia = int(base["distancia"] + (offset * 55) + (ciclo * 35))

    if base["tipo"] == TipoActividad.CORRER:
        ritmo_mov = max(
            300, int(base["ritmo_medio_movimiento"] + offset * 6 + ciclo * 3)
        )
        ritmo_total = max(
            ritmo_mov + 6, int(base["ritmo_medio_total"] + offset * 6 + ciclo * 3)
        )
        velocidad_media = max(800, int(360000 / ritmo_mov))
        velocidad_max = max(
            velocidad_media + 180,
            int(base["velocidad_max_x100"] + offset * 12 + ciclo * 10),
        )
        pausas = max(0, int(base["pausas_manuales"] + (1 if offset > 1 else 0)))
        auto_pausas = max(
            0, int(base["auto_pausas"] + (1 if ciclo >= 3 and offset < 0 else 0))
        )
        duracion_mov = max(900, int(round(distancia * ritmo_mov / 1000)))
        duracion_parado = max(
            20, int(base["duracion_parado"] + (offset * 8) + (ciclo * 5))
        )
        duracion_pausa_manual = max(
            0,
            int(
                base["duracion_pausa_manual"]
                + (10 if pausas > base["pausas_manuales"] else 0)
            ),
        )
        calorias = max(
            180,
            int(
                base["calorias_quemadas"]
                + (distancia - base["distancia"]) * 0.06
                + ciclo * 8
            ),
        )
        alertas = (
            1
            if velocidad_max >= 1350 and (indice % 3 == 0)
            else int(base["alertas_velocidad"])
        )
    else:
        ritmo_mov = max(
            540, int(base["ritmo_medio_movimiento"] + offset * 10 + ciclo * 8)
        )
        ritmo_total = max(
            ritmo_mov + 10, int(base["ritmo_medio_total"] + offset * 11 + ciclo * 8)
        )
        velocidad_media = max(420, int(360000 / ritmo_mov))
        velocidad_max = max(
            velocidad_media + 60,
            int(base["velocidad_max_x100"] + offset * 8 + ciclo * 6),
        )
        pausas = max(1, int(base["pausas_manuales"] + (1 if indice % 4 == 0 else 0)))
        auto_pausas = max(
            1, int(base["auto_pausas"] + (1 if ciclo >= 2 and indice % 5 == 0 else 0))
        )
        duracion_mov = max(1800, int(round(distancia * ritmo_mov / 1000)))
        duracion_parado = max(
            60, int(base["duracion_parado"] + (offset * 12) + (ciclo * 7))
        )
        duracion_pausa_manual = max(
            30,
            int(
                base["duracion_pausa_manual"]
                + (15 if pausas > base["pausas_manuales"] else 0)
            ),
        )
        calorias = max(
            150,
            int(
                base["calorias_quemadas"]
                + (distancia - base["distancia"]) * 0.04
                + ciclo * 6
            ),
        )
        alertas = 0

    return {
        "nombre": f"{base['nombre']} # {indice + 1}",
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


def derivar_ritmo_maximo(
    ritmo_medio_movimiento: int,
    velocidad_max_x100: int,
    tipo: TipoActividad,
) -> int:
    """Deriva un ritmo máximo razonable para datos semilla.

    El backend persistente ahora guarda ritmo máximo además del ritmo medio.
    En los semillas evitamos valores imposibles partiendo de la velocidad máxima
    y acotando el resultado para que sea mejor que el ritmo medio en movimiento,
    pero sin producir picos absurdos por ruido.
    """
    # Gestiona derivar ritmo maximo.
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
    """Convierte el diccionario de la semilla en una carga útil validada."""
    # Construye actividad.
    duracion_total = int(ruta["duracion_movimiento"]) + int(ruta["duracion_parado"])

    return schemas.GuardarActividad(
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


async def obtener_usuario_aportillo(db):
    """Busca el usuario existente 'aportillo' de forma case-insensitive."""
    result = await db.execute(
        select(database.Usuario).where(
            func.lower(database.Usuario.nombre_usuario) == TARGET_USERNAME.lower()
        )
    )
    return result.scalar_one_or_none()


async def actividad_ya_existe(db, usuario_id: int, ruta: dict) -> bool:
    """Evita duplicados obvios cuando se relanza el seed."""
    existente = await db.execute(
        select(database.Actividad.id).where(
            and_(
                database.Actividad.usuario_id == usuario_id,
                database.Actividad.fecha_ruta == ruta["fecha_ruta"],
                database.Actividad.tipo == ruta["tipo"].value,
                database.Actividad.distancia == ruta["distancia"],
            )
        )
    )
    return existente.scalar_one_or_none() is not None


async def crear_actividades_aportillo() -> None:
    """Inicializa la BD y crea 30 actividades completas para aportillo."""
    # Construye actividades aportillo.
    await database.init_db()

    if database.AsyncSessionLocal is None:
        print("No se ha podido inicializar AsyncSessionLocal.")
        return

    async with database.AsyncSessionLocal() as db:
        usuario = await obtener_usuario_aportillo(db)
        if not usuario:
            print("No se ha encontrado el usuario 'aportillo'.")
            print("Crea primero esa cuenta y vuelve a ejecutar este seed.")
            return

        plan = [
            _aplicar_variacion(PLANTILLAS[i % len(PLANTILLAS)], i, FECHAS_SEED[i])
            for i in range(TOTAL_ACTIVIDADES)
        ]

        total_creadas = 0
        total_omitidas = 0

        for indice, ruta in enumerate(plan, start=1):
            try:
                if await actividad_ya_existe(db, usuario.id, ruta):
                    print(
                        f"[SKIP] {usuario.nombre_usuario}: actividad # {indice} ya existe "
                        f"({ruta['nombre']} - {ruta['fecha_ruta'].isoformat()})"
                    )
                    total_omitidas += 1
                    continue

                datos = construir_actividad(ruta)
                respuesta = await activities_service.crear_actividad(
                    db, usuario.id, datos
                )
                total_creadas += 1
                print(
                    f"[OK] {usuario.nombre_usuario}: actividad {respuesta['id']} "
                    f"- {ruta['nombre']} - {respuesta['tipo']} - {respuesta['distancia']}m "
                    f"- {ruta['fecha_ruta'].date().isoformat()}"
                )
            except Exception as exc:
                total_omitidas += 1
                print(
                    f"[SKIP] {usuario.nombre_usuario}: actividad # {indice} "
                    f"({ruta['nombre']}) -> {exc}"
                )

    print()
    print(f"Usuario objetivo: {TARGET_USERNAME}")
    print(
        f"Rango de fechas: {FECHAS_SEED[0].date().isoformat()} -> {FECHAS_SEED[-1].date().isoformat()}"
    )
    print(f"Actividades planificadas: {TOTAL_ACTIVIDADES}")
    print(f"Actividades creadas: {total_creadas}")
    print(f"Actividades omitidas: {total_omitidas}")


if __name__ == "__main__":
    asyncio.run(crear_actividades_aportillo())
