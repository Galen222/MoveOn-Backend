"""Pruebas de utilidades de cálculo compartidas."""

from domain.enums import TipoActividad
from utils import calculos


def test_resolver_ritmo_maximo_preserva_valor_del_cliente():
    assert calculos.resolver_ritmo_maximo(290, 336, 1840, TipoActividad.CORRER) == 290


def test_resolver_ritmo_maximo_deriva_carrera_sin_creer_pico_gps():
    assert calculos.resolver_ritmo_maximo(0, 360, 2400, TipoActividad.CORRER) == 300


def test_resolver_ritmo_maximo_deriva_caminata():
    assert calculos.resolver_ritmo_maximo(0, 720, 700, TipoActividad.CAMINAR) == 630


def test_resolver_ritmo_maximo_sin_metricas_devuelve_cero():
    assert calculos.resolver_ritmo_maximo(0, 0, 0, TipoActividad.CORRER) == 0
