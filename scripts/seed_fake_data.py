# scripts/seed_fake_data.py

"""Genera un conjunto amplio e idempotente de usuarios y actividades demo.

Se usa para poblar entornos locales con registros verosímiles, pasando por
los mismos servicios y validaciones del backend para detectar regresiones
en esquemas, moderación, cálculos y persistencia.
"""

from __future__ import annotations

from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import asyncio  # noqa: E402
import random  # noqa: E402
from datetime import date, datetime, timedelta, timezone  # noqa: E402
from collections.abc import Awaitable, Callable  # noqa: E402
from typing import Any, TypedDict, cast  # noqa: E402

from sqlalchemy.ext.asyncio import AsyncSession  # noqa: E402

from pydantic import AnyHttpUrl  # noqa: E402
from sqlalchemy import and_, func, select  # noqa: E402

import database  # noqa: E402
import schemas  # noqa: E402
from domain.enums import GeneroUsuario, ProvinciaEspaña, TipoActividad  # noqa: E402
from services import activities_service, user_service  # noqa: E402


RegistrarNuevoUsuarioAsync = Callable[
    [AsyncSession, schemas.Registro],
    Awaitable[dict[str, Any]],
]
CrearActividadAsync = Callable[
    [AsyncSession, int, schemas.GuardarActividad],
    Awaitable[dict[str, Any]],
]

registrar_nuevo_usuario_async = cast(
    RegistrarNuevoUsuarioAsync,
    user_service.registrar_nuevo_usuario,
)
crear_actividad_async = cast(
    CrearActividadAsync,
    activities_service.crear_actividad,
)

"""
Semilla de datos simulados para MoveOn.

Crea:
- 20 usuarios simulados:
  prueba01@prueba.com ... prueba20@prueba.com
  password: Prueba01- ... Prueba20-
- 15 actividades base completas con todos los campos del esquema actual
- 4 actividades aleatorias por usuario
- Sin foto de perfil
- Nombres reales ajustados para no chocar con la moderación local
- Idempotente: si ya existe un usuario o actividad seed, no la duplica
"""

VERSION_TERMINOS = "1.0"
TOTAL_USUARIOS = 20
TOTAL_RUTAS_BASE = 15
ACTIVIDADES_POR_USUARIO = 4
UTC = timezone.utc
SEED = 20260331

random.seed(SEED)


class RutaSeed(TypedDict):
    """Describe la forma exacta de cada ruta base usada en la semilla.

    El ``TypedDict`` obliga a que cada plantilla incluya todas las métricas que
    exige ``GuardarActividad``, evitando olvidar campos al ampliar el seed.
    """

    nombre: str
    tipo: TipoActividad
    distancia: int
    duracion_movimiento: int
    duracion_parado: int
    duracion_pausa_manual: int
    calorias_quemadas: int
    ritmo_medio_movimiento: int
    ritmo_medio_total: int
    ritmo_maximo: int
    velocidad_media_x100: int
    velocidad_max_x100: int
    auto_pausas: int
    pausas_manuales: int
    alertas_velocidad: int
    ruta_polilinea: str
    ruta_mapa_url: str | None


def provincia_safe(*names: str) -> ProvinciaEspaña:
    """Resuelve una provincia del enum aceptando varios nombres candidatos.

    Se usa para absorber diferencias de acentos o alias históricos del enum sin
    romper la semilla cuando cambia la representación textual de una provincia.
    """
    for name in names:
        if hasattr(ProvinciaEspaña, name):
            return getattr(ProvinciaEspaña, name)
    raise AttributeError(f"No existe ninguna provincia válida entre: {names}")


USUARIOS_BASE = [
    ("carlosmartin01", "Carlos Martin", GeneroUsuario.HOMBRE, provincia_safe("MADRID")),
    (
        "luciafernandez02",
        "Lucia Fernandez",
        GeneroUsuario.MUJER,
        provincia_safe("BARCELONA"),
    ),
    (
        "javiersanchez03",
        "Javier Sanchez",
        GeneroUsuario.HOMBRE,
        provincia_safe("VALENCIA"),
    ),
    ("martalopez04", "Marta Lopez", GeneroUsuario.MUJER, provincia_safe("SEVILLA")),
    (
        "alejandroruiz05",
        "Alejandro Ruiz",
        GeneroUsuario.HOMBRE,
        provincia_safe("MÁLAGA", "MALAGA"),
    ),
    ("paulagomez06", "Paula Gomez", GeneroUsuario.MUJER, provincia_safe("MURCIA")),
    (
        "danieltorres07",
        "Daniel Torres",
        GeneroUsuario.HOMBRE,
        provincia_safe("ZARAGOZA"),
    ),
    (
        "elenanavarro08",
        "Elena Navarro",
        GeneroUsuario.MUJER,
        provincia_safe("ALICANTE"),
    ),
    (
        "sergioromero09",
        "Sergio Romero",
        GeneroUsuario.HOMBRE,
        provincia_safe("CÁDIZ", "CADIZ"),
    ),
    (
        "claudiacastro10",
        "Claudia Castro",
        GeneroUsuario.MUJER,
        provincia_safe("GRANADA"),
    ),
    (
        "adrianortega11",
        "Adrian Ortega",
        GeneroUsuario.HOMBRE,
        provincia_safe("CÓRDOBA", "CORDOBA"),
    ),
    (
        "nereamolina12",
        "Nerea Molina",
        GeneroUsuario.MUJER,
        provincia_safe("VALLADOLID"),
    ),
    (
        "ivandelgado13",
        "Ivan Delgado",
        GeneroUsuario.HOMBRE,
        provincia_safe("A_CORUÑA", "A_CORUNA"),
    ),
    ("lauravega14", "Laura Vega", GeneroUsuario.MUJER, provincia_safe("TOLEDO")),
    (
        "pablogil15",
        "Pablo Gil",
        GeneroUsuario.HOMBRE,
        provincia_safe("GUIPÚZCOA", "GUIPUZCOA"),
    ),
    (
        "saraherrera16",
        "Sara Herrera",
        GeneroUsuario.MUJER,
        provincia_safe("LEÓN", "LEON"),
    ),
    ("rubenleon17", "Ruben Leon", GeneroUsuario.HOMBRE, provincia_safe("TARRAGONA")),
    ("andrearios18", "Andrea Rios", GeneroUsuario.MUJER, provincia_safe("BADAJOZ")),
    ("davidcruz19", "David Cruz", GeneroUsuario.HOMBRE, provincia_safe("CANTABRIA")),
    (
        "noeliacano20",
        "Noelia Cano",
        GeneroUsuario.MUJER,
        provincia_safe("VIZCAYA", "BIZKAIA"),
    ),
]

ALTURAS = [
    178,
    165,
    182,
    168,
    176,
    163,
    180,
    170,
    183,
    167,
    179,
    164,
    181,
    169,
    177,
    166,
    184,
    171,
    175,
    168,
]
PESOS = [
    78.5,
    58.2,
    82.0,
    61.4,
    76.8,
    57.9,
    80.6,
    60.5,
    84.1,
    59.8,
    77.3,
    56.7,
    79.5,
    62.1,
    74.9,
    58.8,
    83.3,
    63.0,
    75.4,
    60.9,
]
FECHAS_NACIMIENTO = [
    date(1991, 2, 14),
    date(1994, 7, 3),
    date(1989, 11, 9),
    date(1996, 4, 22),
    date(1990, 9, 18),
    date(1995, 1, 30),
    date(1988, 6, 12),
    date(1997, 8, 25),
    date(1992, 3, 7),
    date(1993, 12, 1),
    date(1987, 5, 19),
    date(1998, 10, 11),
    date(1991, 1, 8),
    date(1994, 5, 27),
    date(1989, 7, 14),
    date(1996, 2, 2),
    date(1990, 11, 21),
    date(1995, 6, 6),
    date(1988, 9, 29),
    date(1997, 3, 17),
]

RUTAS_BASE: list[RutaSeed] = [
    {
        "nombre": "Retiro 4.2K suave",
        "tipo": TipoActividad.CAMINAR,
        "distancia": 4200,
        "duracion_movimiento": 2880,
        "duracion_parado": 240,
        "duracion_pausa_manual": 60,
        "calorias_quemadas": 245,
        "ritmo_medio_movimiento": 686,
        "ritmo_medio_total": 743,
        "ritmo_maximo": 590,
        "velocidad_media_x100": 525,
        "velocidad_max_x100": 690,
        "auto_pausas": 2,
        "pausas_manuales": 1,
        "alertas_velocidad": 0,
        "ruta_polilinea": "}_ilFf}qUe@qA_A_Bg@q@w@qA_AiAw@w@q@e@u@_Ay@uA_AuAe@q@",
        "ruta_mapa_url": "https://www.openstreetmap.org/?mlat=40.4153&mlon=-3.6844# map=15/40.4153/-3.6844",
    },
    {
        "nombre": "Madrid Río 5K",
        "tipo": TipoActividad.CORRER,
        "distancia": 5000,
        "duracion_movimiento": 1575,
        "duracion_parado": 75,
        "duracion_pausa_manual": 0,
        "calorias_quemadas": 355,
        "ritmo_medio_movimiento": 315,
        "ritmo_medio_total": 330,
        "ritmo_maximo": 268,
        "velocidad_media_x100": 1143,
        "velocidad_max_x100": 1345,
        "auto_pausas": 1,
        "pausas_manuales": 0,
        "alertas_velocidad": 1,
        "ruta_polilinea": "u_thFzvtUe@w@i@cAq@oAw@cBy@qA_@u@q@aA_AkAu@{Aq@cA",
        "ruta_mapa_url": "https://www.openstreetmap.org/?mlat=40.4038&mlon=-3.7223# map=15/40.4038/-3.7223",
    },
    {
        "nombre": "Turia 6.4K",
        "tipo": TipoActividad.CAMINAR,
        "distancia": 6400,
        "duracion_movimiento": 4500,
        "duracion_parado": 300,
        "duracion_pausa_manual": 120,
        "calorias_quemadas": 370,
        "ritmo_medio_movimiento": 703,
        "ritmo_medio_total": 750,
        "ritmo_maximo": 598,
        "velocidad_media_x100": 512,
        "velocidad_max_x100": 685,
        "auto_pausas": 3,
        "pausas_manuales": 1,
        "alertas_velocidad": 0,
        "ruta_polilinea": "gq{hFf`zVe@u@i@w@k@cAc@u@w@oA_AqAq@kAg@u@u@cAi@w@",
        "ruta_mapa_url": "https://www.openstreetmap.org/?mlat=39.4746&mlon=-0.3860# map=15/39.4746/-0.3860",
    },
    {
        "nombre": "Playa Málaga 7K",
        "tipo": TipoActividad.CORRER,
        "distancia": 7000,
        "duracion_movimiento": 2580,
        "duracion_parado": 120,
        "duracion_pausa_manual": 30,
        "calorias_quemadas": 510,
        "ritmo_medio_movimiento": 369,
        "ritmo_medio_total": 386,
        "ritmo_maximo": 305,
        "velocidad_media_x100": 977,
        "velocidad_max_x100": 1220,
        "auto_pausas": 1,
        "pausas_manuales": 1,
        "alertas_velocidad": 2,
        "ruta_polilinea": "okbpF|~nUg@u@u@_Aw@kA_AiAw@qAe@w@a@u@c@w@u@_A_AgB",
        "ruta_mapa_url": "https://www.openstreetmap.org/?mlat=36.7197&mlon=-4.4106# map=15/36.7197/-4.4106",
    },
    {
        "nombre": "Murcia centro 3.6K",
        "tipo": TipoActividad.CAMINAR,
        "distancia": 3600,
        "duracion_movimiento": 2460,
        "duracion_parado": 180,
        "duracion_pausa_manual": 60,
        "calorias_quemadas": 210,
        "ritmo_medio_movimiento": 683,
        "ritmo_medio_total": 733,
        "ritmo_maximo": 585,
        "velocidad_media_x100": 527,
        "velocidad_max_x100": 705,
        "auto_pausas": 2,
        "pausas_manuales": 1,
        "alertas_velocidad": 0,
        "ruta_polilinea": "gwjkFjykWi@w@u@aA_AiAq@w@w@aAc@u@i@w@q@aA",
        "ruta_mapa_url": "https://www.openstreetmap.org/?mlat=37.9849&mlon=-1.1280# map=15/37.9849/-1.1280",
    },
    {
        "nombre": "Ebro 8.1K",
        "tipo": TipoActividad.CORRER,
        "distancia": 8100,
        "duracion_movimiento": 3150,
        "duracion_parado": 150,
        "duracion_pausa_manual": 30,
        "calorias_quemadas": 590,
        "ritmo_medio_movimiento": 389,
        "ritmo_medio_total": 407,
        "ritmo_maximo": 320,
        "velocidad_media_x100": 925,
        "velocidad_max_x100": 1185,
        "auto_pausas": 1,
        "pausas_manuales": 1,
        "alertas_velocidad": 2,
        "ruta_polilinea": "wjjsFf`oXg@u@q@_Aa@u@u@aA_AiAq@w@i@u@o@aA_AiA",
        "ruta_mapa_url": "https://www.openstreetmap.org/?mlat=41.6561&mlon=-0.8773# map=15/41.6561/-0.8773",
    },
    {
        "nombre": "Alicante puerto 4.8K",
        "tipo": TipoActividad.CAMINAR,
        "distancia": 4800,
        "duracion_movimiento": 3300,
        "duracion_parado": 180,
        "duracion_pausa_manual": 60,
        "calorias_quemadas": 275,
        "ritmo_medio_movimiento": 688,
        "ritmo_medio_total": 725,
        "ritmo_maximo": 592,
        "velocidad_media_x100": 523,
        "velocidad_max_x100": 698,
        "auto_pausas": 2,
        "pausas_manuales": 1,
        "alertas_velocidad": 0,
        "ruta_polilinea": "i}yrEtofYc@u@o@aA_AiAq@w@w@aAc@u@q@aAc@u@",
        "ruta_mapa_url": "https://www.openstreetmap.org/?mlat=38.3452&mlon=-0.4810# map=15/38.3452/-0.4810",
    },
    {
        "nombre": "Granada 5.5K",
        "tipo": TipoActividad.CORRER,
        "distancia": 5500,
        "duracion_movimiento": 2040,
        "duracion_parado": 120,
        "duracion_pausa_manual": 0,
        "calorias_quemadas": 402,
        "ritmo_medio_movimiento": 371,
        "ritmo_medio_total": 393,
        "ritmo_maximo": 301,
        "velocidad_media_x100": 971,
        "velocidad_max_x100": 1248,
        "auto_pausas": 1,
        "pausas_manuales": 0,
        "alertas_velocidad": 1,
        "ruta_polilinea": "eulkFjzzUc@u@w@_Am@w@u@aA_AkAq@w@i@u@w@aA",
        "ruta_mapa_url": "https://www.openstreetmap.org/?mlat=37.1765&mlon=-3.5986# map=15/37.1765/-3.5986",
    },
    {
        "nombre": "Valladolid 6K",
        "tipo": TipoActividad.CAMINAR,
        "distancia": 6000,
        "duracion_movimiento": 4140,
        "duracion_parado": 240,
        "duracion_pausa_manual": 90,
        "calorias_quemadas": 340,
        "ritmo_medio_movimiento": 690,
        "ritmo_medio_total": 730,
        "ritmo_maximo": 600,
        "velocidad_media_x100": 522,
        "velocidad_max_x100": 690,
        "auto_pausas": 2,
        "pausas_manuales": 1,
        "alertas_velocidad": 0,
        "ruta_polilinea": "sxbmFj~kYe@u@i@w@u@aA_AiAq@w@i@u@w@aAq@w@",
        "ruta_mapa_url": "https://www.openstreetmap.org/?mlat=41.6523&mlon=-4.7245# map=15/41.6523/-4.7245",
    },
    {
        "nombre": "Coruña 9K",
        "tipo": TipoActividad.CORRER,
        "distancia": 9000,
        "duracion_movimiento": 3690,
        "duracion_parado": 210,
        "duracion_pausa_manual": 60,
        "calorias_quemadas": 655,
        "ritmo_medio_movimiento": 410,
        "ritmo_medio_total": 433,
        "ritmo_maximo": 330,
        "velocidad_media_x100": 878,
        "velocidad_max_x100": 1110,
        "auto_pausas": 2,
        "pausas_manuales": 1,
        "alertas_velocidad": 2,
        "ruta_polilinea": "ixnjFz~aZa@u@u@aA_AiAq@w@w@aAa@u@u@aA_AiAw@aA",
        "ruta_mapa_url": "https://www.openstreetmap.org/?mlat=43.3623&mlon=-8.4115# map=15/43.3623/-8.4115",
    },
    {
        "nombre": "Toledo ribera 4.4K",
        "tipo": TipoActividad.CAMINAR,
        "distancia": 4400,
        "duracion_movimiento": 3000,
        "duracion_parado": 180,
        "duracion_pausa_manual": 60,
        "calorias_quemadas": 255,
        "ritmo_medio_movimiento": 682,
        "ritmo_medio_total": 723,
        "ritmo_maximo": 588,
        "velocidad_media_x100": 528,
        "velocidad_max_x100": 702,
        "auto_pausas": 2,
        "pausas_manuales": 1,
        "alertas_velocidad": 0,
        "ruta_polilinea": "m_xiFjxzVe@u@q@aA_AiAw@aAq@w@i@u@u@aAq@w@",
        "ruta_mapa_url": "https://www.openstreetmap.org/?mlat=39.8628&mlon=-4.0273# map=15/39.8628/-4.0273",
    },
    {
        "nombre": "Donostia 7.4K",
        "tipo": TipoActividad.CORRER,
        "distancia": 7400,
        "duracion_movimiento": 2820,
        "duracion_parado": 180,
        "duracion_pausa_manual": 30,
        "calorias_quemadas": 540,
        "ritmo_medio_movimiento": 381,
        "ritmo_medio_total": 405,
        "ritmo_maximo": 309,
        "velocidad_media_x100": 945,
        "velocidad_max_x100": 1218,
        "auto_pausas": 1,
        "pausas_manuales": 1,
        "alertas_velocidad": 2,
        "ruta_polilinea": "wqmoFnyqYg@u@u@aA_AiAq@w@q@aAe@u@u@aA_AiA",
        "ruta_mapa_url": "https://www.openstreetmap.org/?mlat=43.3183&mlon=-1.9812# map=15/43.3183/-1.9812",
    },
    {
        "nombre": "León casco 3.9K",
        "tipo": TipoActividad.CAMINAR,
        "distancia": 3900,
        "duracion_movimiento": 2670,
        "duracion_parado": 150,
        "duracion_pausa_manual": 45,
        "calorias_quemadas": 226,
        "ritmo_medio_movimiento": 685,
        "ritmo_medio_total": 723,
        "ritmo_maximo": 590,
        "velocidad_media_x100": 526,
        "velocidad_max_x100": 700,
        "auto_pausas": 1,
        "pausas_manuales": 1,
        "alertas_velocidad": 0,
        "ruta_polilinea": "iuhmFf`rXe@u@q@aA_AiAw@aAe@u@q@aAc@u@",
        "ruta_mapa_url": "https://www.openstreetmap.org/?mlat=42.5987&mlon=-5.5671# map=15/42.5987/-5.5671",
    },
    {
        "nombre": "Tarragona litoral 6.8K",
        "tipo": TipoActividad.CORRER,
        "distancia": 6800,
        "duracion_movimiento": 2610,
        "duracion_parado": 150,
        "duracion_pausa_manual": 30,
        "calorias_quemadas": 495,
        "ritmo_medio_movimiento": 384,
        "ritmo_medio_total": 406,
        "ritmo_maximo": 312,
        "velocidad_media_x100": 938,
        "velocidad_max_x100": 1195,
        "auto_pausas": 1,
        "pausas_manuales": 1,
        "alertas_velocidad": 2,
        "ruta_polilinea": "sllnF~qgYg@u@u@_Aa@u@w@aA_AiAq@w@w@aAq@w@",
        "ruta_mapa_url": "https://www.openstreetmap.org/?mlat=41.1189&mlon=1.2445# map=15/41.1189/1.2445",
    },
    {
        "nombre": "Santander 5.2K",
        "tipo": TipoActividad.CAMINAR,
        "distancia": 5200,
        "duracion_movimiento": 3540,
        "duracion_parado": 180,
        "duracion_pausa_manual": 60,
        "calorias_quemadas": 298,
        "ritmo_medio_movimiento": 681,
        "ritmo_medio_total": 715,
        "ritmo_maximo": 586,
        "velocidad_media_x100": 529,
        "velocidad_max_x100": 708,
        "auto_pausas": 2,
        "pausas_manuales": 1,
        "alertas_velocidad": 0,
        "ruta_polilinea": "qjcnFnlqYe@u@u@aA_AkAw@aAq@w@e@u@u@aAq@w@",
        "ruta_mapa_url": "https://www.openstreetmap.org/?mlat=43.4623&mlon=-3.8099# map=15/43.4623/-3.8099",
    },
]


def ahora_utc() -> datetime:
    """Devuelve el instante actual con zona horaria UTC.

    Centraliza la obtención de tiempo para que todas las fechas derivadas del
    seed partan de la misma convención temporal.
    """
    return datetime.now(UTC)


def fecha_aceptacion_base(indice: int) -> datetime:
    """Calcula una fecha de aceptación de términos estable para cada usuario.

    Escalona ligeramente las marcas temporales para que el dataset no quede con
    veinte aceptaciones idénticas a la vez.
    """
    return datetime(2026, 1, 1, 9, 0, tzinfo=UTC) + timedelta(days=indice)


def fecha_actividad(indice_usuario: int, indice_actividad: int) -> datetime:
    """Distribuye las actividades de un usuario a lo largo del tiempo.

    Combina índice de usuario e índice de actividad para repartir el histórico
    de forma realista y reproducible entre distintos perfiles seed.
    """
    base = datetime(2026, 1, 5, 7, 30, tzinfo=UTC)
    return base + timedelta(
        days=(indice_usuario * 3) + indice_actividad,
        minutes=indice_usuario * 7,
    )


def generar_password(indice: int) -> str:
    """Genera la contraseña conocida asociada a cada usuario semilla.

    El formato permanece determinista para facilitar pruebas manuales y acceso
    rápido a cualquier cuenta demo del entorno local.
    """
    return f"Prueba{indice:02d}-"


def generar_email(indice: int) -> str:
    """Construye el email único de cada cuenta de prueba.

    Mantiene el patrón ``pruebaNN@prueba.com`` para que el cleanup pueda
    identificar fácilmente los registros que debe eliminar.
    """
    return f"prueba{indice:02d}@prueba.com"


def derivar_objetivo_semanal(
    tipo_preferente: TipoActividad,
    altura: int,
    peso: float,
) -> int:
    """Calcula un objetivo semanal plausible a partir del perfil semilla.

    La función introduce variedad entre usuarios sin salir de rangos coherentes
    con el tipo de actividad dominante y el nivel esperado.
    """
    base = 45000 if tipo_preferente == TipoActividad.CAMINAR else 60000
    ajuste = ((altura - 160) * 200) + int((peso - 60) * 150)
    return max(10000, min(2000000, base + ajuste))


def derivar_objetivo_mensual(objetivo_semanal: int) -> int:
    """Escala el objetivo semanal a su equivalente mensual orientativo.

    Se usa para poblar el perfil con metas consistentes entre sí sin duplicar la
    lógica de cálculo en varios puntos del script.
    """
    return max(10000, min(2000000, objetivo_semanal * 4))


def construir_registro(indice: int) -> schemas.Registro:
    """Convierte una entrada base en un ``schemas.Registro`` válido.

    Aplica todos los campos exigidos por el flujo real de alta para que los
    usuarios seed recorran las mismas validaciones que un registro normal.
    """
    # Construye registro.
    username, nombre_real, genero, provincia = USUARIOS_BASE[indice - 1]

    return schemas.Registro(
        nombre_usuario=username,
        email=generar_email(indice),
        password=generar_password(indice),
        nombre_real=nombre_real,
        fecha_nacimiento=FECHAS_NACIMIENTO[indice - 1],
        genero=genero,
        altura=ALTURAS[indice - 1],
        peso=PESOS[indice - 1],
        provincia=provincia,
        perfil_visible=True,
        acepta_terminos=True,
        fecha_aceptacion_terminos=fecha_aceptacion_base(indice),
        version_terminos=VERSION_TERMINOS,
    )


def construir_actividad(
    ruta: RutaSeed, fecha_ruta: datetime
) -> schemas.GuardarActividad:
    """Monta un ``GuardarActividad`` completo a partir de una ruta seed.

    Normaliza tipos, calcula la duración total y rellena las métricas derivadas
    que el servicio de actividades espera recibir ya validadas.
    """
    # Construye actividad.
    duracion_total = int(ruta["duracion_movimiento"]) + int(ruta["duracion_parado"])

    ruta_mapa_url: AnyHttpUrl | None = None
    raw_url = ruta.get("ruta_mapa_url")
    if raw_url:
        ruta_mapa_url = AnyHttpUrl(raw_url)

    return schemas.GuardarActividad(
        client_local_id=None,
        tipo=ruta["tipo"],
        distancia=int(ruta["distancia"]),
        duracion_total=duracion_total,
        duracion_movimiento=int(ruta["duracion_movimiento"]),
        duracion_parado=int(ruta["duracion_parado"]),
        duracion_pausa_manual=int(ruta["duracion_pausa_manual"]),
        calorias_quemadas=int(ruta["calorias_quemadas"]),
        ritmo_medio_movimiento=int(ruta["ritmo_medio_movimiento"]),
        ritmo_medio_total=int(ruta["ritmo_medio_total"]),
        ritmo_maximo=int(ruta["ritmo_maximo"]),
        velocidad_media_x100=int(ruta["velocidad_media_x100"]),
        velocidad_max_x100=int(ruta["velocidad_max_x100"]),
        auto_pausas=int(ruta["auto_pausas"]),
        pausas_manuales=int(ruta["pausas_manuales"]),
        alertas_velocidad=int(ruta["alertas_velocidad"]),
        ruta_polilinea=ruta["ruta_polilinea"],
        ruta_mapa_url=ruta_mapa_url,
        fecha_ruta=fecha_ruta,
    )


async def obtener_usuario_existente(db, email: str, username: str):
    """Busca si la cuenta seed ya existe por email o nombre de usuario.

    Permite que el script sea idempotente y reutilice usuarios previamente
    creados en vez de fallar por duplicados al reejecutarse.
    """
    result = await db.execute(
        select(database.Usuario).where(
            and_(
                func.lower(database.Usuario.email) == email.lower(),
                func.lower(database.Usuario.nombre_usuario) == username.lower(),
            )
        )
    )
    return result.scalar_one_or_none()


async def obtener_o_crear_usuario(db, indice: int):
    """Recupera un usuario seed o lo registra si aún no está en la base.

    La creación se delega al servicio real de usuarios para conservar hashing,
    moderación y comprobaciones de duplicidad.
    """
    registro = construir_registro(indice)

    existente = await obtener_usuario_existente(
        db,
        str(registro.email),
        registro.nombre_usuario,
    )
    if existente is not None:
        return existente, False

    # Firma correcta del servicio actual:
    # registrar_nuevo_usuario(db, datos)
    await registrar_nuevo_usuario_async(db, registro)

    usuario = await obtener_usuario_existente(
        db,
        str(registro.email),
        registro.nombre_usuario,
    )
    if usuario is None:
        raise RuntimeError(
            f"No se pudo recuperar el usuario recién creado: {registro.nombre_usuario}"
        )

    tipo_preferente = TipoActividad.CAMINAR if indice % 2 else TipoActividad.CORRER
    usuario.objetivo_semanal_metros = derivar_objetivo_semanal(
        tipo_preferente,
        ALTURAS[indice - 1],
        PESOS[indice - 1],
    )
    usuario.objetivo_mensual_metros = derivar_objetivo_mensual(
        int(usuario.objetivo_semanal_metros)
    )

    await db.commit()
    await db.refresh(usuario)
    return usuario, True


async def contar_actividades_usuario(db, usuario_id: int) -> int:
    """Cuenta cuántas actividades tiene actualmente un usuario seed.

    Se usa para saber si faltan registros por crear y evitar inserciones ciegas
    cuando el entorno ya fue poblado parcialmente.
    """
    result = await db.execute(
        select(database.Actividad.id).where(database.Actividad.usuario_id == usuario_id)
    )
    return len(result.scalars().all())


async def actividad_ya_existe(
    db,
    usuario_id: int,
    tipo: TipoActividad,
    distancia: int,
    fecha_ruta: datetime,
) -> bool:
    """Comprueba si una actividad equivalente ya fue persistida para el usuario.

    La deduplicación se basa en fecha, tipo y distancia, suficientes para no
    repetir entradas del seed al relanzar el script.
    """
    result = await db.execute(
        select(database.Actividad.id).where(
            and_(
                database.Actividad.usuario_id == usuario_id,
                database.Actividad.tipo == tipo.value,
                database.Actividad.distancia == distancia,
                database.Actividad.fecha_ruta == fecha_ruta,
            )
        )
    )
    return result.scalar_one_or_none() is not None


async def crear_actividades_faltantes(db, usuario, indice_usuario: int) -> int:
    """Genera solo las actividades que todavía faltan para un usuario concreto.

    Recorre el plan previsto para ese perfil, salta duplicados detectados y
    devuelve cuántas inserciones nuevas se realizaron realmente.
    """
    total_actual = await contar_actividades_usuario(db, usuario.id)
    faltan = max(0, ACTIVIDADES_POR_USUARIO - total_actual)
    if faltan == 0:
        return 0

    rng = random.Random(1000 + indice_usuario)
    rutas = RUTAS_BASE.copy()
    rng.shuffle(rutas)
    seleccionadas = rutas[:faltan]

    creadas = 0
    for idx, ruta in enumerate(seleccionadas, start=1):
        fecha = fecha_actividad(indice_usuario, idx)

        if await actividad_ya_existe(
            db,
            usuario.id,
            ruta["tipo"],
            ruta["distancia"],
            fecha,
        ):
            continue

        payload = construir_actividad(ruta, fecha)

        # Firma correcta del servicio actual:
        # crear_actividad(db, usuario_actual_id, datos)
        await crear_actividad_async(db, usuario.id, payload)
        creadas += 1

    return creadas


async def seed_fake_data() -> None:
    """Orquesta la carga completa del dataset demo del backend.

    Inicializa la base de datos, asegura la presencia de las veinte cuentas seed
    y completa para cada una el número objetivo de actividades.
    """
    # Poblar la base de datos con datos simulados de prueba.
    if database.AsyncSessionLocal is None:
        database._init_db_objects()

    if database.AsyncSessionLocal is None:
        raise RuntimeError("No se pudo inicializar AsyncSessionLocal")

    usuarios_creados = 0
    actividades_creadas = 0

    async with database.AsyncSessionLocal() as db:
        for indice in range(1, TOTAL_USUARIOS + 1):
            usuario, creado = await obtener_o_crear_usuario(db, indice)
            if creado:
                usuarios_creados += 1

            actividades_creadas += await crear_actividades_faltantes(
                db,
                usuario,
                indice,
            )

    print()
    print("=== Seed finalizado ===")
    print(f"Usuarios creados: {usuarios_creados}")
    print(f"Actividades creadas: {actividades_creadas}")
    print(f"Usuarios objetivo: {TOTAL_USUARIOS}")
    print(f"Actividades objetivo por usuario: {ACTIVIDADES_POR_USUARIO}")
    print("Emails: prueba01@prueba.com ... prueba20@prueba.com")
    print("Passwords: Prueba01- ... Prueba20-")


async def main() -> None:
    """Expone el orquestador del seed como entrada ejecutable por consola.

    Mantiene el punto de entrada separado para facilitar importaciones desde
    otros scripts o desde futuras pruebas de integración.
    """
    await seed_fake_data()


if __name__ == "__main__":
    asyncio.run(main())
