# scripts/seed_galen.py

"""Incluye un script de apoyo para tareas del proyecto."""

from __future__ import annotations

from pathlib import Path
import sys

# Añadir la raíz del proyecto ANTES de importar módulos internos.
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import asyncio  # noqa: E402
from datetime import date, datetime, timedelta, timezone  # noqa: E402

from sqlalchemy import func, select  # noqa: E402

import database  # noqa: E402
import schemas  # noqa: E402
from domain.enums import TipoActividad  # noqa: E402
from services import activities_service, user_service  # noqa: E402

"""
Seeder de 57 rutas completas para un usuario de pruebas llamado Galen.

Objetivo:
- Crear el usuario "Galen" si no existe todavía.
- Email: galen2@gmx.net
- Fecha de nacimiento: 1978-11-27
- Contraseña: Prueba123

Importante:
- El script NO guarda la contraseña en claro en la base de datos.
- Para respetar exactamente la misma lógica que usa el backend en producción,
  crea el usuario reutilizando schemas.Registro + user_service.registrar_nuevo_usuario().
- Ese servicio aplica las validaciones y genera el hash de contraseña con
  auth.encriptar_password() antes de persistir el usuario.

Comportamiento:
- Si el usuario ya existe por nombre o email, se reutiliza.
- Después crea 57 actividades con polilíneas válidas (7 base + 50 extra).
- Está pensado para desarrollo y pruebas manuales.

Uso:
    python scripts/seed_galen_real_routes.py
"""

TARGET_USERNAME = "Galen"
TARGET_EMAIL = "galen2@gmx.net"
TARGET_PASSWORD = "Prueba123"
TARGET_BIRTH_DATE = date(1978, 11, 27)
VERSION_TERMINOS = "1.0"

RUTAS_GALEN_BASE = [
    {
        "nombre": "Retiro 3.8K",
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
        "dias_atras": 3,
        "horas_atras": 7,
    },
    {
        "nombre": "Madrid Rio 7.9K",
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
        # Polilínea corregida: la versión anterior estaba truncada.
        "ruta_polilinea": "gfsuFjgrUcGcGkHoPwGoPwBgT~HgOfOgEbQfEnKbQjCfT{E~RsIjMwLzE",
        "ruta_mapa_url": "https://www.openstreetmap.org/?mlat=40.40820&mlon=-3.70310# map=15/40.40820/-3.70310",
        "dias_atras": 5,
        "horas_atras": 19,
    },
    {
        "nombre": "Casa de Campo 9.5K",
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
        # Polilínea corregida: la versión anterior estaba truncada.
        "ruta_polilinea": "_mtuFnowUgJwQgOwLkMgOcL_SnKwQ~RkC~RzE~MnP~HvVoAvVsI~MkH~C",
        "ruta_mapa_url": "https://www.openstreetmap.org/?mlat=40.41440&mlon=-3.73000# map=15/40.41440/-3.73000",
        "dias_atras": 8,
        "horas_atras": 8,
    },
    {
        "nombre": "Dehesa 6.3K",
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
        "dias_atras": 12,
        "horas_atras": 18,
    },
    {
        "nombre": "Juan Carlos I 8.7K",
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
        "ruta_mapa_url": "https://www.openstreetmap.org/?mlat=40.45890&mlon=-3.59890# map=15/40.45890/-3.59890",
        "dias_atras": 16,
        "horas_atras": 7,
    },
    {
        "nombre": "El Capricho 5.1K",
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
        "dias_atras": 21,
        "horas_atras": 20,
    },
    {
        "nombre": "Tio Pio 5.2K",
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
        # Polilínea corregida: la versión anterior estaba truncada.
        "ruta_polilinea": "_houF~sgU_IwL{JwL_IgOrDgT~M_IvQR~MrIvGvQg@~RkHfOgJbGkHR",
        "ruta_mapa_url": "https://www.openstreetmap.org/?mlat=40.38800&mlon=-3.64880# map=15/40.38800/-3.64880",
        "dias_atras": 27,
        "horas_atras": 6,
    },
]

NOMBRES_ZONA_EXTRA = [
    "Castellana",
    "Salamanca",
    "Chamberi",
    "Lavapies",
    "Moncloa",
    "Arganzuela",
    "Principe Pio",
    "Atocha",
    "Usera",
    "Valdebebas",
]


def generar_rutas_extra(total_extra: int = 50) -> list[dict]:
    """
    Genera rutas adicionales consistentes a partir de las 7 rutas base.

    - Mantiene polilíneas y URLs válidas reutilizando plantillas reales.
    - Ajusta distancia, tiempos y métricas para que sigan siendo coherentes.
    - Asigna fechas más antiguas que las rutas originales para no solaparlas.
    """
    # Genera rutas extra.
    extras: list[dict] = []

    for i in range(total_extra):
        base = dict(RUTAS_GALEN_BASE[i % len(RUTAS_GALEN_BASE)])
        ciclo = i // len(RUTAS_GALEN_BASE)
        factor = 0.92 + ((i % 9) * 0.03)

        distancia = int(
            round(base["distancia"] * factor + (ciclo * 115) + ((i % 5) * 37))
        )
        distancia = max(distancia, 2500)

        duracion_movimiento = int(
            round(base["duracion_movimiento"] * (distancia / base["distancia"]))
        )
        duracion_movimiento += (i % 4) * 9 + ciclo * 11

        duracion_parado = max(
            20, int(round(base["duracion_parado"] * (0.85 + (i % 4) * 0.12)))
        )
        duracion_pausa_manual = max(
            0, int(round(base["duracion_pausa_manual"] * (0.75 + (i % 3) * 0.2)))
        )

        calorias_por_metro = base["calorias_quemadas"] / base["distancia"]
        calorias_quemadas = max(110, int(round(calorias_por_metro * distancia)))

        ritmo_medio_movimiento = int(round((duracion_movimiento / distancia) * 1000))
        ritmo_medio_total = int(
            round(((duracion_movimiento + duracion_parado) / distancia) * 1000)
        )
        velocidad_media_x100 = int(round((distancia / duracion_movimiento) * 360))
        velocidad_max_x100 = int(
            round(velocidad_media_x100 * (1.18 + ((i % 5) * 0.025)))
        )

        auto_pausas = min(3, 1 if duracion_parado >= 70 else 0)
        if base["tipo"] == TipoActividad.CAMINAR and duracion_parado >= 100:
            auto_pausas = min(3, auto_pausas + 1)

        pausas_manuales = 1 if duracion_pausa_manual >= 30 else 0
        if duracion_pausa_manual >= 75:
            pausas_manuales = 2

        alertas_velocidad = (
            1 if base["tipo"] == TipoActividad.CORRER and (i % 4 == 0) else 0
        )
        zona = NOMBRES_ZONA_EXTRA[i % len(NOMBRES_ZONA_EXTRA)]
        km = f"{distancia / 1000:.1f}K"

        base.update(
            {
                "nombre": f"{zona} # {i + 1} {km}",
                "distancia": distancia,
                "duracion_movimiento": duracion_movimiento,
                "duracion_parado": duracion_parado,
                "duracion_pausa_manual": duracion_pausa_manual,
                "calorias_quemadas": calorias_quemadas,
                "ritmo_medio_movimiento": ritmo_medio_movimiento,
                "ritmo_medio_total": ritmo_medio_total,
                "velocidad_media_x100": velocidad_media_x100,
                "velocidad_max_x100": velocidad_max_x100,
                "auto_pausas": auto_pausas,
                "pausas_manuales": pausas_manuales,
                "alertas_velocidad": alertas_velocidad,
                "dias_atras": 31 + (i * 2) + ciclo,
                "horas_atras": (3 + i * 7) % 24,
            }
        )

        extras.append(base)

    return extras


RUTAS_GALEN = RUTAS_GALEN_BASE + generar_rutas_extra(50)


def ahora_utc() -> datetime:
    """Devuelve la fecha/hora actual en UTC."""
    return datetime.now(timezone.utc)


async def obtener_usuario_existente(db):
    """
    Busca un usuario existente por nombre de usuario o email.

    Se usa para hacer el semilla idempotente y evitar errores por duplicados
    si el script se ejecuta varias veces.
    """
    result = await db.execute(
        select(database.Usuario).where(
            (func.lower(database.Usuario.nombre_usuario) == TARGET_USERNAME.lower())
            | (database.Usuario.email == TARGET_EMAIL.lower())
        )
    )
    return result.scalar_one_or_none()


async def obtener_o_crear_usuario_galen(db):
    """
    Obtiene el usuario Galen si ya existe; si no, lo crea usando el
    servicio real de registro para que el hash de contraseña se genere
    igual que en producción.
    """
    # Obtiene o crear usuario galen.
    usuario = await obtener_usuario_existente(db)
    if usuario:
        print(
            f"[USER] Reutilizando usuario existente: {usuario.nombre_usuario} <{usuario.email}>"
        )
        return usuario

    datos_registro = schemas.Registro(
        nombre_usuario=TARGET_USERNAME,
        email=TARGET_EMAIL,
        password=TARGET_PASSWORD,
        nombre_real="Galen",
        fecha_nacimiento=TARGET_BIRTH_DATE,
        perfil_visible=True,
        acepta_terminos=True,
        fecha_aceptacion_terminos=ahora_utc() - timedelta(minutes=5),
        version_terminos=VERSION_TERMINOS,
    )

    respuesta = await user_service.registrar_nuevo_usuario(db, datos_registro)
    print(f"[USER] Creado usuario: {respuesta['nombre_usuario']} <{TARGET_EMAIL}>")

    usuario = await obtener_usuario_existente(db)
    if not usuario:
        raise RuntimeError(
            "El usuario se registró pero no se pudo recuperar desde la base de datos."
        )

    return usuario


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
    """Construye la carga útil validada de una actividad a partir del diccionario de la semilla."""
    # Construye actividad.
    fecha_ruta = ahora_utc() - timedelta(
        days=ruta["dias_atras"],
        hours=ruta["horas_atras"],
        minutes=17,
    )

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
        fecha_ruta=fecha_ruta,
    )


async def crear_rutas_galen() -> None:
    """Inicializa la BD, garantiza el usuario Galen y crea las 57 rutas de prueba."""
    # Construye rutas galen.
    await database.init_db()

    if database.AsyncSessionLocal is None:
        print("No se ha podido inicializar AsyncSessionLocal.")
        return

    total_creadas = 0

    async with database.AsyncSessionLocal() as db:
        usuario = await obtener_o_crear_usuario_galen(db)

        for indice, ruta in enumerate(RUTAS_GALEN, start=1):
            try:
                datos = construir_actividad(ruta)
                respuesta = await activities_service.crear_actividad(
                    db, usuario.id, datos
                )
                total_creadas += 1
                print(
                    f"[OK] {usuario.nombre_usuario}: actividad {respuesta['id']} "
                    f"- {ruta['nombre']} - {respuesta['tipo']} - {respuesta['distancia']}m"
                )
            except Exception as exc:
                print(
                    f"[SKIP] {usuario.nombre_usuario}: ruta # {indice} "
                    f"({ruta['nombre']}) -> {exc}"
                )

    print()
    print(f"Usuario objetivo: {TARGET_USERNAME} <{TARGET_EMAIL}>")
    print(f"Fecha de nacimiento: {TARGET_BIRTH_DATE.isoformat()}")
    print(f"Contraseña de pruebas: {TARGET_PASSWORD}")
    print(f"Total de rutas creadas: {total_creadas}")
    print(f"Total configuradas en el seed: {len(RUTAS_GALEN)}")


if __name__ == "__main__":
    asyncio.run(crear_rutas_galen())
