# domain/enums.py

from enum import Enum


class ProvinciaEspaña(str, Enum):
    # Andalucía
    ALMERIA = "Almería"
    CADIZ = "Cádiz"
    CORDOBA = "Córdoba"
    GRANADA = "Granada"
    HUELVA = "Huelva"
    JAEN = "Jaén"
    MALAGA = "Málaga"
    SEVILLA = "Sevilla"

    # Aragón
    HUESCA = "Huesca"
    TERUEL = "Teruel"
    ZARAGOZA = "Zaragoza"

    # Asturias
    ASTURIAS = "Asturias"

    # Baleares
    BALEARES = "Islas Baleares"

    # Canarias
    LAS_PALMAS = "Las Palmas"
    SANTA_CRUZ_TENERIFE = "Santa Cruz de Tenerife"

    # Cantabria
    CANTABRIA = "Cantabria"

    # Castilla-La Mancha
    ALBACETE = "Albacete"
    CIUDAD_REAL = "Ciudad Real"
    CUENCA = "Cuenca"
    GUADALAJARA = "Guadalajara"
    TOLEDO = "Toledo"

    # Castilla y León
    AVILA = "Ávila"
    BURGOS = "Burgos"
    LEON = "León"
    PALENCIA = "Palencia"
    SALAMANCA = "Salamanca"
    SEGOVIA = "Segovia"
    SORIA = "Soria"
    VALLADOLID = "Valladolid"
    ZAMORA = "Zamora"

    # Cataluña
    BARCELONA = "Barcelona"
    GIRONA = "Girona"
    LLEIDA = "Lleida"
    TARRAGONA = "Tarragona"

    # Extremadura
    BADAJOZ = "Badajoz"
    CACERES = "Cáceres"

    # Galicia
    A_CORUNA = "A Coruña"
    LUGO = "Lugo"
    OURENSE = "Ourense"
    PONTEVEDRA = "Pontevedra"

    # Madrid
    MADRID = "Madrid"

    # Murcia
    MURCIA = "Murcia"

    # Navarra
    NAVARRA = "Navarra"

    # País Vasco
    ALAVA = "Álava"
    GUIPUZCOA = "Guipúzcoa"
    VIZCAYA = "Vizcaya"

    # La Rioja
    RIOJA = "La Rioja"

    # Comunidad Valenciana
    ALICANTE = "Alicante"
    CASTELLON = "Castellón"
    VALENCIA = "Valencia"

    # Ciudades Autónomas
    CEUTA = "Ceuta"
    MELILLA = "Melilla"


class GeneroUsuario(str, Enum):
    HOMBRE = "Hombre"
    MUJER = "Mujer"
    OTRO = "Otro"


class TipoActividad(str, Enum):
    CAMINAR = "Caminar"
    CORRER = "Correr"


PROVINCIAS_ESPANA = tuple(item.value for item in ProvinciaEspaña)
GENEROS_USUARIO = tuple(item.value for item in GeneroUsuario)
TIPOS_ACTIVIDAD = tuple(item.value for item in TipoActividad)
