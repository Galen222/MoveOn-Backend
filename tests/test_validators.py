
# tests/test_validators.py
#
# Tests unitarios para utils/validators.py.
# Son tests puros: sin BD, sin red, sin fixtures async.
# Cubren los límites de cada validador para detectar regresiones.

import pytest
from datetime import date, datetime, timezone, timedelta

from exceptions import AppValidationError
from utils import validators


# ─────────────────────────────────────────────
# PASSWORD
# ─────────────────────────────────────────────


class TestValidarPassword:
    def test_rechaza_password_muy_corta(self):
        with pytest.raises(ValueError, match="8 caracteres"):
            validators.validar_password_logica("Ab1")

    def test_rechaza_password_sin_mayuscula(self):
        with pytest.raises(ValueError, match="mayúscula"):
            validators.validar_password_logica("abcde123")

    def test_rechaza_password_sin_numero(self):
        with pytest.raises(ValueError, match="número"):
            validators.validar_password_logica("Abcdefgh")

    def test_rechaza_password_si_supera_72_bytes_utf8(self):
        pwd = "Á1" + ("ñ" * 36)  # 2 + 1 + (36*2) = 75 bytes
        with pytest.raises(ValueError, match="72 bytes"):
            validators.validar_password_logica(pwd)

    def test_acepta_password_valida_en_limite_ascii(self):
        pwd = "A1" + ("b" * 68)  # 70 bytes total
        resultado = validators.validar_password_logica(pwd)
        assert resultado == pwd

    def test_acepta_password_valida_con_simbolos(self):
        resultado = validators.validar_password_logica("MiPass1!")
        assert resultado == "MiPass1!"


# ─────────────────────────────────────────────
# NOMBRE REAL
# ─────────────────────────────────────────────


class TestValidarNombreReal:
    def test_rechaza_nombre_muy_corto(self):
        with pytest.raises(ValueError, match="corto"):
            validators.validar_nombre_real_logica("Jo")

    def test_rechaza_nombre_demasiado_largo(self):
        with pytest.raises(ValueError, match="80 caracteres"):
            validators.validar_nombre_real_logica("A" * 81)

    def test_rechaza_nombre_con_numeros(self):
        with pytest.raises(ValueError, match="números"):
            validators.validar_nombre_real_logica("Juan123")

    def test_rechaza_nombre_con_simbolos_invalidos(self):
        with pytest.raises(ValueError, match="números"):
            validators.validar_nombre_real_logica("Juan@Pérez")

    def test_acepta_nombre_con_acento(self):
        resultado = validators.validar_nombre_real_logica("María José")
        assert resultado == "María José"

    def test_acepta_nombre_con_enye(self):
        resultado = validators.validar_nombre_real_logica("Ñoño García")
        assert resultado == "Ñoño García"

    def test_acepta_nombre_con_apostrofe_y_guion(self):
        # "O'Brien-García" es un nombre válido
        resultado = validators.validar_nombre_real_logica("O'Brien-García")
        assert resultado == "O'Brien-García"

    def test_acepta_nombre_exactamente_3_chars(self):
        resultado = validators.validar_nombre_real_logica("Ana")
        assert resultado == "Ana"


# ─────────────────────────────────────────────
# FECHA DE NACIMIENTO
# ─────────────────────────────────────────────


class TestValidarFechaNacimiento:
    def test_rechaza_fecha_futura(self):
        manana = date.today() + timedelta(days=1)
        with pytest.raises(ValueError, match="futuro"):
            validators.validar_fecha_nacimiento_logica(manana)

    def test_rechaza_menor_de_18(self):
        # 17 años exactos
        hoy = date.today()
        fecha_17 = date(hoy.year - 17, hoy.month, hoy.day)
        with pytest.raises(ValueError, match="18 años"):
            validators.validar_fecha_nacimiento_logica(fecha_17)

    def test_acepta_exactamente_18_anos(self):
        hoy = date.today()
        fecha_18 = date(hoy.year - 18, hoy.month, hoy.day)
        resultado = validators.validar_fecha_nacimiento_logica(fecha_18)
        assert resultado == fecha_18

    def test_acepta_adulto_normal(self):
        resultado = validators.validar_fecha_nacimiento_logica(date(1990, 6, 15))
        assert resultado == date(1990, 6, 15)


# ─────────────────────────────────────────────
# ALTURA y PESO
# ─────────────────────────────────────────────


class TestValidarAltura:
    def test_rechaza_altura_cero(self):
        with pytest.raises(ValueError, match="50cm"):
            validators.validar_altura_logica(0)

    def test_rechaza_altura_por_debajo_de_minimo(self):
        with pytest.raises(ValueError, match="50cm"):
            validators.validar_altura_logica(49)

    def test_rechaza_altura_por_encima_de_maximo(self):
        with pytest.raises(ValueError, match="300cm"):
            validators.validar_altura_logica(301)

    def test_acepta_altura_en_rango(self):
        assert validators.validar_altura_logica(175) == 175

    def test_acepta_altura_en_limites(self):
        assert validators.validar_altura_logica(50) == 50
        assert validators.validar_altura_logica(300) == 300

    def test_acepta_none(self):
        assert validators.validar_altura_logica(None) is None  # type: ignore[arg-type]


class TestValidarPeso:
    def test_rechaza_peso_por_debajo_de_minimo(self):
        with pytest.raises(ValueError, match="20kg"):
            validators.validar_peso_logica(19.9)

    def test_rechaza_peso_por_encima_de_maximo(self):
        with pytest.raises(ValueError, match="300kg"):
            validators.validar_peso_logica(300.1)

    def test_acepta_peso_en_rango(self):
        assert validators.validar_peso_logica(70.5) == 70.5

    def test_acepta_none(self):
        assert validators.validar_peso_logica(None) is None  # type: ignore[arg-type]


# ─────────────────────────────────────────────
# ACTIVIDAD: distancia, duración, calorías
# ─────────────────────────────────────────────


class TestValidarDistancia:
    def test_rechaza_distancia_cero(self):
        with pytest.raises(ValueError, match="mayor a 0"):
            validators.validar_distancia_logica(0)

    def test_rechaza_distancia_negativa(self):
        with pytest.raises(ValueError, match="mayor a 0"):
            validators.validar_distancia_logica(-1)

    def test_rechaza_distancia_sobre_300km(self):
        with pytest.raises(ValueError, match="300km"):
            validators.validar_distancia_logica(300_001)

    def test_acepta_exactamente_300km(self):
        assert validators.validar_distancia_logica(300_000) == 300_000

    def test_acepta_distancia_normal(self):
        assert validators.validar_distancia_logica(5_000) == 5_000


class TestValidarDuracion:
    def test_rechaza_duracion_cero(self):
        with pytest.raises(ValueError, match="mayor a 0"):
            validators.validar_duracion_logica(0)

    def test_rechaza_duracion_sobre_24h(self):
        # 86401 segundos = 24h + 1s
        with pytest.raises(ValueError, match="24 horas"):
            validators.validar_duracion_logica(86_401)

    def test_acepta_exactamente_24h(self):
        assert validators.validar_duracion_logica(86_400) == 86_400

    def test_acepta_duracion_normal(self):
        assert validators.validar_duracion_logica(3_600) == 3_600  # 1 hora


class TestValidarCalorias:
    def test_rechaza_calorias_cero(self):
        with pytest.raises(ValueError, match="mayor a 0"):
            validators.validar_calorias_logica(0)

    def test_rechaza_calorias_sobre_10000(self):
        with pytest.raises(ValueError, match="10.000"):
            validators.validar_calorias_logica(10_001)

    def test_acepta_exactamente_10000(self):
        assert validators.validar_calorias_logica(10_000) == 10_000

    def test_acepta_calorias_normales(self):
        assert validators.validar_calorias_logica(500) == 500


# ─────────────────────────────────────────────
# POLILÍNEA
# ─────────────────────────────────────────────


class TestValidarPolilinea:
    def test_rechaza_polilinea_demasiado_corta(self):
        # Menos de 5 caracteres
        with pytest.raises(ValueError, match="inválida"):
            validators.validar_polilinea_logica("ab_c")

    def test_acepta_polilinea_de_5_o_mas_chars(self):
        resultado = validators.validar_polilinea_logica("abcde")
        assert resultado == "abcde"

    def test_acepta_none(self):
        assert validators.validar_polilinea_logica(None) is None  # type: ignore[arg-type]


# ─────────────────────────────────────────────
# FECHA DE RUTA (actividad)
# ─────────────────────────────────────────────


class TestValidarFechaRuta:
    def test_rechaza_fecha_en_el_futuro_lejano(self):
        futuro = datetime.now(timezone.utc) + timedelta(hours=1)
        with pytest.raises(ValueError, match="futuro"):
            validators.validar_fecha_ruta_logica(futuro)

    def test_acepta_fecha_dentro_del_margen_de_10_minutos(self):
        # El validador permite hasta 10 min de margen (reloj del móvil)
        casi_ahora = datetime.now(timezone.utc) + timedelta(minutes=5)
        resultado = validators.validar_fecha_ruta_logica(casi_ahora)
        assert resultado is not None

    def test_acepta_fecha_pasada(self):
        ayer = datetime.now(timezone.utc) - timedelta(days=1)
        resultado = validators.validar_fecha_ruta_logica(ayer)
        assert resultado is not None

    def test_acepta_none(self):
        # Si se pasa None, el validador devuelve None sin error
        assert validators.validar_fecha_ruta_logica(None) is None  # type: ignore[arg-type]


# ─────────────────────────────────────────────
# INTERCEPTAR ERROR PYDANTIC
# ─────────────────────────────────────────────


class TestInterceptarErrorPydantic:
    def test_handler_ok_devuelve_resultado(self):
        """Si el handler no lanza excepción, devuelve su resultado."""

        def handler(v):
            return v.upper()

        resultado = validators.interceptar_error_pydantic(
            "hola",
            handler,
            "CUSTOM_VALIDATION_ERROR",
            "Error custom",
        )
        assert resultado == "HOLA"

    def test_handler_falla_lanza_appvalidationerror_con_mensaje_y_codigo(self):
        """Si el handler lanza cualquier excepción, se reemplaza por AppValidationError con mensaje y error_code."""

        def handler_que_falla(v):
            raise TypeError("error interno de pydantic")

        with pytest.raises(AppValidationError) as exc_info:
            validators.interceptar_error_pydantic(
                "dato",
                handler_que_falla,
                "CUSTOM_VALIDATION_ERROR",
                "Mi mensaje personalizado",
            )

        assert str(exc_info.value) == "Mi mensaje personalizado"
        assert exc_info.value.error_code == "CUSTOM_VALIDATION_ERROR"

    def test_captura_cualquier_tipo_de_excepcion(self):
        """No solo TypeError: cualquier Exception se intercepta."""

        def handler_runtime(v):
            raise RuntimeError("algo raro")

        with pytest.raises(AppValidationError) as exc_info:
            validators.interceptar_error_pydantic(
                42,
                handler_runtime,
                "RUNTIME_VALIDATION_ERROR",
                "Error capturado",
            )

        assert str(exc_info.value) == "Error capturado"
        assert exc_info.value.error_code == "RUNTIME_VALIDATION_ERROR"

    def test_handler_con_none_funciona(self):
        """Si el valor es None y el handler lo acepta, devuelve None."""

        def handler(v):
            return v

        resultado = validators.interceptar_error_pydantic(
            None,
            handler,
            "NONE_VALIDATION_ERROR",
            "Error",
        )
        assert resultado is None

    def test_handler_con_valueerror_tambien_se_intercepta(self):
        """Un ValueError del handler se reemplaza por AppValidationError con el mensaje limpio."""

        def handler_value_error(v):
            raise ValueError("mensaje original de pydantic")

        with pytest.raises(AppValidationError) as exc_info:
            validators.interceptar_error_pydantic(
                "x",
                handler_value_error,
                "VALUE_ERROR_INTERCEPTED",
                "Mensaje limpio",
            )

        assert str(exc_info.value) == "Mensaje limpio"
        assert exc_info.value.error_code == "VALUE_ERROR_INTERCEPTED"


