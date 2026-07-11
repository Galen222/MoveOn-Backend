"""Genera usuarios demo y actividades coherentes con su provincia.

Crea 30 usuarios simulados con nombres de usuario realistas, sin número final,
y 4 actividades por usuario. Cada usuario recibe actividades de la provincia
asignada en su perfil. Todas las actividades son idempotentes mediante
``client_local_id`` estable.
"""

from __future__ import annotations

from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import asyncio  # noqa: E402
import math  # noqa: E402
from datetime import date, datetime, timedelta, timezone  # noqa: E402
from collections.abc import Awaitable, Callable  # noqa: E402
from typing import Any, TypedDict, cast  # noqa: E402

from sqlalchemy.ext.asyncio import AsyncSession  # noqa: E402

from pydantic import AnyHttpUrl  # noqa: E402
from sqlalchemy import and_, func, or_, select  # noqa: E402

import database  # noqa: E402
import schemas  # noqa: E402
from domain.enums import GeneroUsuario, ProvinciaEspaña, TipoActividad  # noqa: E402
from services import activities_service, user_service  # noqa: E402
from scripts.seed_catalogo import (  # noqa: E402
    USUARIOS_SEED_USERNAMES,
    USUARIOS_SEED_VERSION,
)


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

VERSION_TERMINOS = "1.0"
SEED_VERSION = USUARIOS_SEED_VERSION
TOTAL_USUARIOS = 30
ACTIVIDADES_POR_USUARIO = 4
UTC = timezone.utc


class RutaSeed(TypedDict):
    """Describe la forma exacta de cada ruta base usada en la semilla."""

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
    """Resuelve una provincia del enum aceptando varios nombres candidatos."""
    for name in names:
        if hasattr(ProvinciaEspaña, name):
            return getattr(ProvinciaEspaña, name)
    raise AttributeError(f"No existe ninguna provincia válida entre: {names}")


# username, nombre_real, genero, provincia, clave de rutas provinciales
USUARIOS_BASE = [
    ('carlosmartin', 'Carlos Martin', GeneroUsuario.HOMBRE, provincia_safe('MADRID'), 'MADRID'),
    ('luciafernandez', 'Lucia Fernandez', GeneroUsuario.MUJER, provincia_safe('BARCELONA'), 'BARCELONA'),
    ('javiersanchez', 'Javier Sanchez', GeneroUsuario.HOMBRE, provincia_safe('VALENCIA'), 'VALENCIA'),
    ('martalopez', 'Marta Lopez', GeneroUsuario.MUJER, provincia_safe('SEVILLA'), 'SEVILLA'),
    ('alejandroruiz', 'Alejandro Ruiz', GeneroUsuario.HOMBRE, provincia_safe('MÁLAGA', 'MALAGA'), 'MALAGA'),
    ('paulagomez', 'Paula Gomez', GeneroUsuario.MUJER, provincia_safe('MURCIA'), 'MURCIA'),
    ('danieltorres', 'Daniel Torres', GeneroUsuario.HOMBRE, provincia_safe('ZARAGOZA'), 'ZARAGOZA'),
    ('elenanavarro', 'Elena Navarro', GeneroUsuario.MUJER, provincia_safe('ALICANTE'), 'ALICANTE'),
    ('sergioromero', 'Sergio Romero', GeneroUsuario.HOMBRE, provincia_safe('CÁDIZ', 'CADIZ'), 'CADIZ'),
    ('claudiacastro', 'Claudia Castro', GeneroUsuario.MUJER, provincia_safe('GRANADA'), 'GRANADA'),
    ('adrianortega', 'Adrian Ortega', GeneroUsuario.HOMBRE, provincia_safe('CÓRDOBA', 'CORDOBA'), 'CORDOBA'),
    ('nereamolina', 'Nerea Molina', GeneroUsuario.MUJER, provincia_safe('VALLADOLID'), 'VALLADOLID'),
    ('ivandelgado', 'Ivan Delgado', GeneroUsuario.HOMBRE, provincia_safe('A_CORUÑA', 'A_CORUNA'), 'A_CORUNA'),
    ('lauravega', 'Laura Vega', GeneroUsuario.MUJER, provincia_safe('TOLEDO'), 'TOLEDO'),
    ('pablogil', 'Pablo Gil', GeneroUsuario.HOMBRE, provincia_safe('GUIPÚZCOA', 'GUIPUZCOA'), 'GUIPUZCOA'),
    ('saraherrera', 'Sara Herrera', GeneroUsuario.MUJER, provincia_safe('LEÓN', 'LEON'), 'LEON'),
    ('rubenleon', 'Ruben Leon', GeneroUsuario.HOMBRE, provincia_safe('TARRAGONA'), 'TARRAGONA'),
    ('andrearios', 'Andrea Rios', GeneroUsuario.MUJER, provincia_safe('BADAJOZ'), 'BADAJOZ'),
    ('davidcruz', 'David Cruz', GeneroUsuario.HOMBRE, provincia_safe('CANTABRIA'), 'CANTABRIA'),
    ('noeliacano', 'Noelia Cano', GeneroUsuario.MUJER, provincia_safe('VIZCAYA', 'BIZKAIA'), 'BIZKAIA'),
    ('miguelcastro', 'Miguel Castro', GeneroUsuario.HOMBRE, provincia_safe('MADRID'), 'MADRID'),
    ('inesmorales', 'Ines Morales', GeneroUsuario.MUJER, provincia_safe('BARCELONA'), 'BARCELONA'),
    ('raulsantos', 'Raul Santos', GeneroUsuario.HOMBRE, provincia_safe('VALENCIA'), 'VALENCIA'),
    ('veronicaperez', 'Veronica Perez', GeneroUsuario.MUJER, provincia_safe('SEVILLA'), 'SEVILLA'),
    ('albertoramos', 'Alberto Ramos', GeneroUsuario.HOMBRE, provincia_safe('MÁLAGA', 'MALAGA'), 'MALAGA'),
    ('beatrizroman', 'Beatriz Roman', GeneroUsuario.MUJER, provincia_safe('MURCIA'), 'MURCIA'),
    ('oscarblanco', 'Oscar Blanco', GeneroUsuario.HOMBRE, provincia_safe('ZARAGOZA'), 'ZARAGOZA'),
    ('patriciagil', 'Patricia Gil', GeneroUsuario.MUJER, provincia_safe('ALICANTE'), 'ALICANTE'),
    ('hectornunez', 'Hector Nunez', GeneroUsuario.HOMBRE, provincia_safe('GRANADA'), 'GRANADA'),
    ('mariacrespo', 'Maria Crespo', GeneroUsuario.MUJER, provincia_safe('VALLADOLID'), 'VALLADOLID'),
]


if tuple(usuario[0] for usuario in USUARIOS_BASE) != USUARIOS_SEED_USERNAMES:
    raise RuntimeError(
        "USUARIOS_BASE no coincide con USUARIOS_SEED_USERNAMES de seed_catalogo.py"
    )

ALTURAS = [178, 165, 182, 168, 176, 163, 180, 170, 183, 167, 179, 164, 181, 169, 177, 166, 184, 171, 175, 168, 180, 166, 177, 169, 182, 164, 179, 167, 181, 165]
PESOS = [78.5, 58.2, 82.0, 61.4, 76.8, 57.9, 80.6, 60.5, 84.1, 59.8, 77.3, 56.7, 79.5, 62.1, 74.9, 58.8, 83.3, 63.0, 75.4, 60.9, 79.2, 59.1, 76.5, 62.4, 81.0, 58.0, 77.8, 60.2, 80.1, 57.6]
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
    date(1992, 8, 4),
    date(1999, 4, 13),
    date(1986, 12, 9),
    date(1993, 6, 24),
    date(1990, 1, 26),
    date(1998, 2, 16),
    date(1987, 10, 2),
    date(1996, 9, 5),
    date(1989, 3, 30),
    date(1995, 11, 12),
]

RUTAS_PROVINCIA_CONFIG = {
    'MADRID': ('Madrid', 40.4168, -3.7038, ['Retiro suave', 'Madrid Río 5K', 'Casa de Campo fondo', 'Castellana control']),
    'BARCELONA': ('Barcelona', 41.3851, 2.1734, ['Ciutadella paseo', 'Diagonal progresivo', 'Montjuïc subida', 'Barceloneta suave']),
    'VALENCIA': ('Valencia', 39.4699, -0.3763, ['Turia 6K', 'Malvarrosa tempo', 'Cabecera suave', 'Ruzafa control']),
    'SEVILLA': ('Sevilla', 37.3891, -5.9845, ['Maria Luisa paseo', 'Guadalquivir 5K', 'Triana control', 'Alamillo fondo']),
    'MALAGA': ('Málaga', 36.7213, -4.4214, ['Malagueta 5K', 'Litoral oeste', 'Gibralfaro suave', 'Huelin tempo']),
    'MURCIA': ('Murcia', 37.9849, -1.128, ['Segura centro', 'Malecón paseo', 'La Fica 5K', 'Ronda Sur suave']),
    'ZARAGOZA': ('Zaragoza', 41.6488, -0.8891, ['Ebro 8K', 'Parque Grande', 'Expo ribera', 'Centro tempo']),
    'ALICANTE': ('Alicante', 38.3452, -0.481, ['Puerto paseo', 'Postiguet 5K', 'Serra Grossa', 'San Juan suave']),
    'CADIZ': ('Cádiz', 36.5271, -6.2886, ['La Caleta paseo', 'Campo del Sur', 'Paseo marítimo', 'Cortadura suave']),
    'GRANADA': ('Granada', 37.1773, -3.5986, ['Genil 5K', 'Albaicín suave', 'Zaidín control', 'Fuentenueva paseo']),
    'CORDOBA': ('Córdoba', 37.8882, -4.7794, ['Ribera 5K', 'Mezquita suave', 'Vial Norte', 'Arenal control']),
    'VALLADOLID': ('Valladolid', 41.6523, -4.7245, ['Pisuerga paseo', 'Campo Grande', 'Ribera 6K', 'Centro control']),
    'A_CORUNA': ('A Coruña', 43.3623, -8.4115, ['Torre de Hércules', 'Riazor 5K', 'Orzán suave', 'Paseo marítimo']),
    'TOLEDO': ('Toledo', 39.8628, -4.0273, ['Ribera Tajo', 'Casco suave', 'Vega baja', 'Miradero control']),
    'GUIPUZCOA': ('Donostia', 43.3183, -1.9812, ['La Concha 5K', 'Urumea suave', 'Ondarreta paseo', 'Gros tempo']),
    'LEON': ('León', 42.5987, -5.5671, ['Bernesga paseo', 'Casco histórico', 'Eras 5K', 'Papallona suave']),
    'TARRAGONA': ('Tarragona', 41.1189, 1.2445, ['Litoral 6K', 'Rambla Nova', 'Arrabassada', 'Francolí suave']),
    'BADAJOZ': ('Badajoz', 38.8794, -6.9707, ['Guadiana 5K', 'Alcazaba suave', 'Valdepasillas', 'Centro control']),
    'CANTABRIA': ('Santander', 43.4623, -3.8099, ['Sardinero paseo', 'Magdalena 5K', 'Bahía suave', 'Mataleñas control']),
    'BIZKAIA': ('Bilbao', 43.263, -2.935, ['Ría Bilbao', 'Doña Casilda', 'Abandoibarra', 'Casco Viejo suave']),
}



def codificar_polilinea(puntos: list[tuple[float, float]]) -> str:
    """Codifica puntos lat/lon al formato Google Encoded Polyline válido."""
    anterior_lat = 0
    anterior_lon = 0
    partes: list[str] = []

    def codificar_valor(valor: int) -> None:
        valor = ~(valor << 1) if valor < 0 else valor << 1
        while valor >= 0x20:
            partes.append(chr((0x20 | (valor & 0x1F)) + 63))
            valor >>= 5
        partes.append(chr(valor + 63))

    for lat, lon in puntos:
        lat_entero = int(round(lat * 100000))
        lon_entero = int(round(lon * 100000))
        codificar_valor(lat_entero - anterior_lat)
        codificar_valor(lon_entero - anterior_lon)
        anterior_lat = lat_entero
        anterior_lon = lon_entero

    return "".join(partes)


def desplazar_coordenada(
    lat: float,
    lon: float,
    norte_metros: float,
    este_metros: float,
) -> tuple[float, float]:
    """Desplaza una coordenada unos metros manteniendo precisión suficiente."""
    nueva_lat = lat + norte_metros / 111_320.0
    nueva_lon = lon + este_metros / (
        111_320.0 * max(0.15, math.cos(math.radians(lat)))
    )
    return round(nueva_lat, 5), round(nueva_lon, 5)


def generar_puntos_ruta(
    lat: float,
    lon: float,
    indice_usuario: int,
    indice_actividad: int,
    total_puntos: int,
    semilla_provincia: int,
) -> list[tuple[float, float]]:
    """Crea una ruta no repetida, dentro de la provincia y con puntos variables."""
    fase = (semilla_provincia % 29) * 0.07 + indice_usuario * 0.19 + indice_actividad * 0.83
    largo = 900 + indice_actividad * 310 + (indice_usuario % 6) * 95 + (semilla_provincia % 7) * 40
    ancho = 210 + indice_actividad * 55 + (indice_usuario % 5) * 26 + (semilla_provincia % 5) * 18
    puntos: list[tuple[float, float]] = []

    for punto in range(total_puntos):
        progreso = punto / max(1, total_puntos - 1)
        norte = (progreso - 0.5) * largo
        norte += math.sin(progreso * math.pi * 2 + fase) * ancho * 0.40
        este = math.sin(progreso * math.pi + fase) * ancho
        este += math.cos(progreso * math.pi * 3 + fase) * ancho * 0.22
        norte += math.sin((punto + 1) * 1.37 + fase) * 22
        este += math.cos((punto + 1) * 1.11 + fase) * 22
        puntos.append(desplazar_coordenada(lat, lon, norte, este))

    return puntos


METRICAS_BASE = (
    {
        "tipo": TipoActividad.CAMINAR,
        "distancia": 4200,
        "duracion_movimiento": 2880,
        "duracion_parado": 180,
        "duracion_pausa_manual": 60,
        "calorias_quemadas": 245,
        "ritmo_medio_movimiento": 686,
        "ritmo_medio_total": 729,
        "ritmo_maximo": 590,
        "velocidad_media_x100": 525,
        "velocidad_max_x100": 690,
        "auto_pausas": 2,
        "pausas_manuales": 1,
        "alertas_velocidad": 0,
    },
    {
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
    },
    {
        "tipo": TipoActividad.CAMINAR,
        "distancia": 6400,
        "duracion_movimiento": 4500,
        "duracion_parado": 240,
        "duracion_pausa_manual": 90,
        "calorias_quemadas": 370,
        "ritmo_medio_movimiento": 703,
        "ritmo_medio_total": 741,
        "ritmo_maximo": 598,
        "velocidad_media_x100": 512,
        "velocidad_max_x100": 685,
        "auto_pausas": 3,
        "pausas_manuales": 1,
        "alertas_velocidad": 0,
    },
    {
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
    },
)


def generar_rutas_provincia(
    clave_provincia: str,
    indice_usuario: int,
) -> list[RutaSeed]:
    """Genera cuatro rutas propias para un usuario dentro de su provincia."""
    nombre_provincia, lat, lon, nombres = RUTAS_PROVINCIA_CONFIG[clave_provincia]
    semilla_provincia = sum(ord(letra) for letra in clave_provincia)
    rutas: list[RutaSeed] = []

    for indice, metricas in enumerate(METRICAS_BASE):
        total_puntos = 14 + ((semilla_provincia + indice_usuario * 4 + indice * 7) % 23)
        puntos = generar_puntos_ruta(
            lat,
            lon,
            indice_usuario,
            indice,
            total_puntos,
            semilla_provincia,
        )

        es_correr = metricas["tipo"] == TipoActividad.CORRER
        variacion_usuario = (indice_usuario % 8) * 85
        variacion_provincia = (semilla_provincia % 10) * 45
        distancia = int(metricas["distancia"] + indice * 230 + variacion_usuario + variacion_provincia)

        if es_correr:
            ritmo_movimiento = int(metricas["ritmo_medio_movimiento"] + (indice_usuario % 5) * 7 + indice * 4)
            ritmo_total = max(ritmo_movimiento + 8, ritmo_movimiento + 14 + indice * 3)
            ritmo_maximo = max(230, ritmo_movimiento - 38 - (indice_usuario % 4) * 3)
            velocidad_maxima = max(1100, int(metricas["velocidad_max_x100"] + indice * 24 + (indice_usuario % 6) * 11))
            auto_pausas = int(metricas["auto_pausas"] + (1 if indice_usuario % 6 == 0 else 0))
            pausas_manuales = int(metricas["pausas_manuales"] + (1 if indice_usuario % 10 == 0 and indice > 0 else 0))
            duracion_pausa_manual = int(metricas["duracion_pausa_manual"] + pausas_manuales * 12)
        else:
            ritmo_movimiento = int(metricas["ritmo_medio_movimiento"] + (indice_usuario % 6) * 11 + indice * 7)
            ritmo_total = max(ritmo_movimiento + 12, ritmo_movimiento + 28 + indice * 4)
            ritmo_maximo = max(480, ritmo_movimiento - 78 - (indice_usuario % 5) * 4)
            velocidad_maxima = max(560, int(metricas["velocidad_max_x100"] + indice * 16 + (indice_usuario % 5) * 9))
            auto_pausas = int(metricas["auto_pausas"] + (1 if indice_usuario % 4 == 0 else 0))
            pausas_manuales = int(metricas["pausas_manuales"] + (1 if indice_usuario % 7 == 0 else 0))
            duracion_pausa_manual = int(metricas["duracion_pausa_manual"] + pausas_manuales * 15)

        duracion_movimiento = int(round(distancia * ritmo_movimiento / 1000))
        duracion_parado = int(metricas["duracion_parado"] + indice * 18 + (indice_usuario % 4) * 12)
        velocidad_media = max(1, int(round(360000 / ritmo_movimiento)))
        calorias = int(metricas["calorias_quemadas"] + distancia * (0.030 if es_correr else 0.018) + indice_usuario * 3)
        punto_mapa = puntos[len(puntos) // 2]

        ruta = dict(metricas)
        ruta.update(
            {
                "nombre": f"{nombre_provincia} {nombres[indice]}",
                "distancia": distancia,
                "duracion_movimiento": duracion_movimiento,
                "duracion_parado": duracion_parado,
                "duracion_pausa_manual": duracion_pausa_manual,
                "calorias_quemadas": calorias,
                "ritmo_medio_movimiento": ritmo_movimiento,
                "ritmo_medio_total": ritmo_total,
                "ritmo_maximo": ritmo_maximo,
                "velocidad_media_x100": velocidad_media,
                "velocidad_max_x100": velocidad_maxima,
                "auto_pausas": auto_pausas,
                "pausas_manuales": pausas_manuales,
                "alertas_velocidad": int(metricas["alertas_velocidad"] if es_correr else 0),
                "ruta_polilinea": codificar_polilinea(puntos),
                "ruta_mapa_url": (
                    f"https://www.openstreetmap.org/?mlat={punto_mapa[0]:.5f}"
                    f"&mlon={punto_mapa[1]:.5f}#map=15/"
                    f"{punto_mapa[0]:.5f}/{punto_mapa[1]:.5f}"
                ),
            }
        )
        rutas.append(ruta)  # type: ignore[arg-type]

    return rutas


def ahora_utc() -> datetime:
    """Devuelve el instante actual con zona horaria UTC."""
    return datetime.now(UTC)


def fecha_aceptacion_base(indice: int) -> datetime:
    """Calcula una fecha de aceptación de términos estable para cada usuario."""
    return datetime(2026, 1, 1, 9, 0, tzinfo=UTC) + timedelta(days=indice)


def fecha_actividad(indice_usuario: int, indice_actividad: int) -> datetime:
    """Distribuye las actividades de un usuario de forma realista y reproducible."""
    base = datetime(2026, 1, 5, 7, 30, tzinfo=UTC)
    return base + timedelta(
        days=(indice_usuario * 3) + indice_actividad,
        minutes=indice_usuario * 7,
    )


def construir_client_local_id(indice_usuario: int, indice_actividad: int) -> str:
    """Construye el identificador estable de una actividad seed de usuarios."""
    return f"{SEED_VERSION}-u{indice_usuario:02d}-a{indice_actividad:02d}"


def generar_password(indice: int) -> str:
    """Genera la contraseña conocida asociada a cada usuario semilla."""
    return f"Prueba{indice:02d}-"


def generar_email(indice: int) -> str:
    """Construye el email único de cada cuenta de prueba a partir del username."""
    username = USUARIOS_BASE[indice - 1][0]
    return f"{username}@prueba.com"


def derivar_objetivo_semanal(
    tipo_preferente: TipoActividad,
    altura: int,
    peso: float,
) -> int:
    """Calcula un objetivo semanal plausible a partir del perfil semilla."""
    base = 45000 if tipo_preferente == TipoActividad.CAMINAR else 60000
    ajuste = ((altura - 160) * 200) + int((peso - 60) * 150)
    return max(10000, min(2000000, base + ajuste))


def derivar_objetivo_mensual(objetivo_semanal: int) -> int:
    """Escala el objetivo semanal a su equivalente mensual orientativo."""
    return max(10000, min(2000000, objetivo_semanal * 4))


def construir_registro(indice: int) -> schemas.Registro:
    """Convierte una entrada base en un ``schemas.Registro`` válido."""
    username, nombre_real, genero, provincia, _clave_rutas = USUARIOS_BASE[indice - 1]

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
    ruta: RutaSeed,
    fecha_ruta: datetime,
    client_local_id: str,
) -> schemas.GuardarActividad:
    """Monta un ``GuardarActividad`` completo a partir de una ruta seed."""
    duracion_total = int(ruta["duracion_movimiento"]) + int(ruta["duracion_parado"])

    ruta_mapa_url: AnyHttpUrl | None = None
    raw_url = ruta.get("ruta_mapa_url")
    if raw_url:
        ruta_mapa_url = AnyHttpUrl(raw_url)

    return schemas.GuardarActividad(
        client_local_id=client_local_id,
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
    """Busca si la cuenta seed ya existe por email o nombre de usuario."""
    result = await db.execute(
        select(database.Usuario).where(
            or_(
                func.lower(database.Usuario.email) == email.lower(),
                func.lower(database.Usuario.nombre_usuario) == username.lower(),
            )
        )
    )
    return result.scalar_one_or_none()


async def obtener_o_crear_usuario(db, indice: int):
    """Recupera un usuario seed o lo registra si aún no está en la base."""
    registro = construir_registro(indice)

    existente = await obtener_usuario_existente(
        db,
        str(registro.email),
        registro.nombre_usuario,
    )
    if existente is not None:
        return existente, False

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


async def actividad_seed_ya_existe(
    db,
    usuario_id: int,
    client_local_id: str,
) -> bool:
    """Comprueba si una actividad seed ya existe por ``client_local_id``."""
    result = await db.execute(
        select(database.Actividad.id).where(
            and_(
                database.Actividad.usuario_id == usuario_id,
                database.Actividad.client_local_id == client_local_id,
            )
        )
    )
    return result.scalar_one_or_none() is not None


async def crear_actividades_faltantes(db, usuario, indice_usuario: int) -> int:
    """Genera solo las actividades seed que todavía faltan para un usuario."""
    *_perfil, clave_rutas = USUARIOS_BASE[indice_usuario - 1]
    rutas = generar_rutas_provincia(clave_rutas, indice_usuario)

    creadas = 0
    for indice_actividad in range(1, ACTIVIDADES_POR_USUARIO + 1):
        client_local_id = construir_client_local_id(indice_usuario, indice_actividad)
        if await actividad_seed_ya_existe(db, usuario.id, client_local_id):
            continue

        ruta = rutas[indice_actividad - 1]
        fecha = fecha_actividad(indice_usuario, indice_actividad)
        payload = construir_actividad(ruta, fecha, client_local_id)

        await crear_actividad_async(db, usuario.id, payload)
        creadas += 1

    return creadas


async def seed_usuarios() -> None:
    """Orquesta la carga completa del dataset demo de usuarios."""
    if database.AsyncSessionLocal is None:
        if hasattr(database, "init_db"):
            await database.init_db()
        elif hasattr(database, "_init_db_objects"):
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
    print("=== Seed usuarios finalizado ===")
    print(f"Seed: {SEED_VERSION}")
    print(f"Usuarios creados: {usuarios_creados}")
    print(f"Actividades creadas: {actividades_creadas}")
    print(f"Usuarios objetivo: {TOTAL_USUARIOS}")
    print(f"Actividades objetivo por usuario: {ACTIVIDADES_POR_USUARIO}")
    print("Emails: <username>@prueba.com")
    print("Passwords: Prueba01- ... Prueba30-")


async def main() -> None:
    """Expone el orquestador del seed como entrada ejecutable por consola."""
    await seed_usuarios()


if __name__ == "__main__":
    asyncio.run(main())
