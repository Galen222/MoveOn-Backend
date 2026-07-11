"""Pruebas de seguridad para scripts.seed_limpieza."""

from types import SimpleNamespace

import pytest

from scripts import seed_limpieza


@pytest.mark.parametrize("valor", ["s", "S", "si", "Sí", "YES", " y "])
def test_respuesta_afirmativa_acepta_variantes(valor):
    assert seed_limpieza.respuesta_afirmativa(valor) is True


@pytest.mark.parametrize("valor", ["", "n", "no", "0", "otra cosa"])
def test_respuesta_afirmativa_rechaza_resto(valor):
    assert seed_limpieza.respuesta_afirmativa(valor) is False


def test_prefijos_seleccionados_solo_incluye_grupos_elegidos():
    seleccion = seed_limpieza.SeleccionLimpieza(
        usuarios=True,
        aportillo=False,
        galen=True,
    )

    assert seed_limpieza.prefijos_seleccionados(seleccion) == (
        "usuarios-v2-30-",
        "galen-v3-60-",
    )



def test_seleccionar_usuarios_no_incluye_actividades_galen():
    seleccion = seed_limpieza.SeleccionLimpieza(usuarios=True)

    assert seed_limpieza.prefijos_seleccionados(seleccion) == (
        "usuarios-v2-30-",
    )
    assert "galen-v3-60-" not in seed_limpieza.prefijos_seleccionados(seleccion)

def test_catalogo_demo_no_incluye_galen_ni_galeng():
    usernames = {username for username, _email in seed_limpieza.identidades_usuarios_seed()}

    assert "galen" not in usernames
    assert "galeng" not in usernames


def test_usuario_demo_exige_username_y_email_exactos():
    username, email = seed_limpieza.identidades_usuarios_seed()[0]

    exacto = SimpleNamespace(nombre_usuario=username, email=email)
    username_distinto = SimpleNamespace(nombre_usuario="otrousuario", email=email)
    email_distinto = SimpleNamespace(
        nombre_usuario=username,
        email="otro@prueba.com",
    )

    assert seed_limpieza.es_usuario_seed_eliminable(exacto) is True
    assert seed_limpieza.es_usuario_seed_eliminable(username_distinto) is False
    assert seed_limpieza.es_usuario_seed_eliminable(email_distinto) is False


def test_detectar_grupo_no_confunde_actividad_real():
    assert seed_limpieza.detectar_grupo("galen-v3-60-001") == "galen"
    assert seed_limpieza.detectar_grupo("actividad-real-001") == "otro"
    assert seed_limpieza.detectar_grupo(None) == "sin-client-local-id"


def test_cuenta_galen_es_una_seleccion_independiente():
    seleccion = seed_limpieza.SeleccionLimpieza(cuenta_galen=True)

    assert seleccion.hay_algo is True
    assert seleccion.grupos == ()
    assert seed_limpieza.prefijos_seleccionados(seleccion) == ()


def test_objetivo_cuenta_galen_no_confunde_galeng():
    galen = SimpleNamespace(nombre_usuario="Galen")
    galen_minusculas = SimpleNamespace(nombre_usuario=" galen ")
    galeng = SimpleNamespace(nombre_usuario="GalenG")
    otro = SimpleNamespace(nombre_usuario="carlosmartin")

    assert seed_limpieza.es_cuenta_galen_objetivo(galen) is True
    assert seed_limpieza.es_cuenta_galen_objetivo(galen_minusculas) is True
    assert seed_limpieza.es_cuenta_galen_objetivo(galeng) is False
    assert seed_limpieza.es_cuenta_galen_objetivo(otro) is False
