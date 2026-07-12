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


def test_aplicar_totales_recalculados_reemplaza_valores_desincronizados():
    usuario = SimpleNamespace(
        total_metros=424_905,
        total_calorias=29_680,
        total_duracion_segundos=189_359,
        total_actividades=3,
    )
    totales = seed_limpieza.TotalesActividades(
        actividades=3,
        metros=6_305,
        calorias=746,
        duracion=4_657,
    )

    seed_limpieza.aplicar_totales_recalculados(usuario, totales)

    assert usuario.total_metros == 6_305
    assert usuario.total_calorias == 746
    assert usuario.total_duracion_segundos == 4_657
    assert usuario.total_actividades == 3


def test_aplicar_totales_recalculados_pone_cero_si_no_quedan_actividades():
    usuario = SimpleNamespace(
        total_metros=10_000,
        total_calorias=700,
        total_duracion_segundos=3_600,
        total_actividades=2,
    )

    seed_limpieza.aplicar_totales_recalculados(
        usuario,
        seed_limpieza.TotalesActividades(),
    )

    assert usuario.total_metros == 0
    assert usuario.total_calorias == 0
    assert usuario.total_duracion_segundos == 0
    assert usuario.total_actividades == 0


class _ResultadoEscalares:
    def __init__(self, valores):
        self._valores = valores

    def scalars(self):
        return self

    def all(self):
        return self._valores


class _ResultadoFilas:
    def __init__(self, filas):
        self._filas = filas

    def all(self):
        return self._filas


class _DbRecalculoFake:
    def __init__(self, usuarios, filas):
        self._resultados = [
            _ResultadoEscalares(usuarios),
            _ResultadoFilas(filas),
        ]

    async def execute(self, _consulta):
        return self._resultados.pop(0)


@pytest.mark.asyncio
async def test_recalcular_acumulados_usa_suma_real_y_pone_cero_sin_filas():
    galen = SimpleNamespace(
        id=22,
        total_metros=424_905,
        total_calorias=29_680,
        total_duracion_segundos=189_359,
        total_actividades=3,
    )
    sin_actividades = SimpleNamespace(
        id=23,
        total_metros=5_000,
        total_calorias=300,
        total_duracion_segundos=2_000,
        total_actividades=1,
    )
    fila_galen = SimpleNamespace(
        usuario_id=22,
        actividades=3,
        metros=6_305,
        calorias=746,
        duracion=4_657,
    )
    db = _DbRecalculoFake([galen, sin_actividades], [fila_galen])

    await seed_limpieza.recalcular_acumulados_usuarios(
        db,
        usuario_ids={22, 23},
        usuarios_que_se_borraran=set(),
    )

    assert (
        galen.total_metros,
        galen.total_calorias,
        galen.total_duracion_segundos,
        galen.total_actividades,
    ) == (6_305, 746, 4_657, 3)
    assert (
        sin_actividades.total_metros,
        sin_actividades.total_calorias,
        sin_actividades.total_duracion_segundos,
        sin_actividades.total_actividades,
    ) == (0, 0, 0, 0)
