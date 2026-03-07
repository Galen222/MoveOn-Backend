# tests/test_schemas.py
#
# Sustituye y amplía: test_schemas_actualizar_perfil.py
# Cubre: Registro, Login, ConfirmarPassword, GuardarActividad, ActualizarPerfil.
# Estrategia: instanciar schemas directamente con Pydantic (ValidationError si falla).

import pytest
from datetime import date, datetime, timedelta, timezone
from pydantic import ValidationError

import schemas
from schemas import (
    ActualizarPerfil, ConfirmarPassword, GeneroUsuario,
    GuardarActividad, Login, Registro, TipoActividad,
)


# ─────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────

def _ahora_utc() -> datetime:
    return datetime.now(timezone.utc)


def _datos_registro_validos() -> dict:
    return {
        "nombre_usuario": "GalenTest",
        "email": "galen@test.com",
        "password": "Password123!",
        "fecha_nacimiento": date(1990, 5, 15),
        "acepta_terminos": True,
        "fecha_aceptacion_terminos": _ahora_utc() - timedelta(seconds=10),
        "version_terminos": "1.0",
    }


def _datos_actividad_validos() -> dict:
    return {
        "tipo": TipoActividad.CORRER,
        "distancia": 5000,
        "duracion": 1800,
        "calorias_quemadas": 300,
        "fecha_ruta": _ahora_utc() - timedelta(minutes=30),
    }


# ─────────────────────────────────────────────
# Registro
# ─────────────────────────────────────────────

class TestRegistro:
    def test_datos_validos_pasan(self):
        r = Registro(**_datos_registro_validos())
        assert r.nombre_usuario == "GalenTest"

    def test_nombre_usuario_muy_corto_falla(self):
        datos = {**_datos_registro_validos(), "nombre_usuario": "abc"}
        with pytest.raises(ValidationError):
            Registro(**datos)

    def test_nombre_usuario_con_espacios_falla(self):
        datos = {**_datos_registro_validos(), "nombre_usuario": "galen test"}
        with pytest.raises(ValidationError):
            Registro(**datos)

    def test_nombre_usuario_con_caracteres_especiales_falla(self):
        datos = {**_datos_registro_validos(), "nombre_usuario": "galen@test"}
        with pytest.raises(ValidationError):
            Registro(**datos)

    def test_email_invalido_falla(self):
        datos = {**_datos_registro_validos(), "email": "no-es-un-email"}
        with pytest.raises(ValidationError):
            Registro(**datos)

    def test_email_se_normaliza_a_minusculas(self):
        datos = {**_datos_registro_validos(), "email": "GALEN@TEST.COM"}
        r = Registro(**datos)
        assert r.email == "galen@test.com"  # type: ignore[comparison-overlap]

    def test_password_debil_falla(self):
        datos = {**_datos_registro_validos(), "password": "1234"}
        with pytest.raises(ValidationError):
            Registro(**datos)

    def test_acepta_terminos_false_falla(self):
        datos = {**_datos_registro_validos(), "acepta_terminos": False}
        with pytest.raises(ValidationError):
            Registro(**datos)

    def test_fecha_aceptacion_terminos_futura_falla(self):
        datos = {**_datos_registro_validos(),
                 "fecha_aceptacion_terminos": _ahora_utc() + timedelta(hours=1)}
        with pytest.raises(ValidationError):
            Registro(**datos)

    def test_fecha_aceptacion_terminos_con_5_min_margen_pasa(self):
        """El validador permite hasta 5 minutos de margen futuro."""
        datos = {**_datos_registro_validos(),
                 "fecha_aceptacion_terminos": _ahora_utc() + timedelta(minutes=4)}
        r = Registro(**datos)
        assert r is not None

    def test_version_terminos_vacia_falla(self):
        datos = {**_datos_registro_validos(), "version_terminos": "  "}
        with pytest.raises(ValidationError):
            Registro(**datos)

    def test_altura_negativa_falla(self):
        datos = {**_datos_registro_validos(), "altura": -5}
        with pytest.raises(ValidationError):
            Registro(**datos)

    def test_altura_excesiva_falla(self):
        datos = {**_datos_registro_validos(), "altura": 999}
        with pytest.raises(ValidationError):
            Registro(**datos)

    def test_peso_negativo_falla(self):
        datos = {**_datos_registro_validos(), "peso": -1.0}
        with pytest.raises(ValidationError):
            Registro(**datos)

    def test_nombre_usuario_faltante_falla(self):
        datos = _datos_registro_validos()
        datos.pop("nombre_usuario")
        with pytest.raises(ValidationError):
            Registro(**datos)

    def test_genero_invalido_falla(self):
        datos = {**_datos_registro_validos(), "genero": "Extraterrestre"}
        with pytest.raises(ValidationError):
            Registro(**datos)

    def test_provincia_invalida_falla(self):
        datos = {**_datos_registro_validos(), "provincia": "Mordor"}
        with pytest.raises(ValidationError):
            Registro(**datos)

    def test_campos_opcionales_pueden_omitirse(self):
        r = Registro(**_datos_registro_validos())
        assert r.nombre_real is None
        assert r.genero is None
        assert r.altura is None
        assert r.peso is None
        assert r.provincia is None


# ─────────────────────────────────────────────
# Login
# ─────────────────────────────────────────────

class TestLogin:
    def test_datos_validos_pasan(self):
        l = Login(identificador="pepe", password="Password123!")
        assert l.identificador == "pepe"

    def test_identificador_con_espacios_se_limpia(self):
        l = Login(identificador="  pepe  ", password="Password123!")
        assert l.identificador == "pepe"

    def test_identificador_vacio_falla(self):
        with pytest.raises(ValidationError):
            Login(identificador="   ", password="Password123!")

    def test_identificador_faltante_falla(self):
        with pytest.raises(ValidationError):
            Login(identificador="", password="Password123!")

    def test_password_faltante_falla(self):
        with pytest.raises(ValidationError):
            Login(identificador="pepe", password="")


# ─────────────────────────────────────────────
# ConfirmarPassword
# ─────────────────────────────────────────────

class TestConfirmarPassword:
    def _valido(self) -> dict:
        return {
            "email": "test@test.com",
            "codigo": "123456",
            "nueva_password": "NuevaPass1!",
        }

    def test_datos_validos_pasan(self):
        c = ConfirmarPassword(**self._valido())
        assert c.codigo == "123456"

    def test_codigo_con_5_digitos_falla(self):
        with pytest.raises(ValidationError):
            ConfirmarPassword(**{**self._valido(), "codigo": "12345"})

    def test_codigo_con_7_digitos_falla(self):
        with pytest.raises(ValidationError):
            ConfirmarPassword(**{**self._valido(), "codigo": "1234567"})

    def test_codigo_con_letras_falla(self):
        with pytest.raises(ValidationError):
            ConfirmarPassword(**{**self._valido(), "codigo": "12345a"})

    def test_codigo_vacio_falla(self):
        with pytest.raises(ValidationError):
            ConfirmarPassword(**{**self._valido(), "codigo": ""})

    def test_codigo_con_espacios_se_limpia_y_valida(self):
        c = ConfirmarPassword(**{**self._valido(), "codigo": " 123456 "})
        assert c.codigo == "123456"

    def test_email_invalido_falla(self):
        with pytest.raises(ValidationError):
            ConfirmarPassword(**{**self._valido(), "email": "no-email"})

    def test_nueva_password_debil_falla(self):
        with pytest.raises(ValidationError):
            ConfirmarPassword(**{**self._valido(), "nueva_password": "1234"})

    def test_email_faltante_falla(self):
        datos = self._valido()
        datos.pop("email")
        with pytest.raises(ValidationError):
            ConfirmarPassword(**datos)


# ─────────────────────────────────────────────
# GuardarActividad
# ─────────────────────────────────────────────

class TestGuardarActividad:
    def test_datos_validos_pasan(self):
        a = GuardarActividad(**_datos_actividad_validos())
        assert a.tipo == TipoActividad.CORRER

    def test_tipo_caminar_valido(self):
        datos = {**_datos_actividad_validos(), "tipo": TipoActividad.CAMINAR}
        a = GuardarActividad(**datos)
        assert a.tipo == TipoActividad.CAMINAR

    def test_tipo_invalido_falla(self):
        datos = {**_datos_actividad_validos(), "tipo": "Nadar"}
        with pytest.raises(ValidationError):
            GuardarActividad(**datos)

    def test_distancia_float_falla_strict(self):
        """distancia es StrictInt: un float debe fallar."""
        datos = {**_datos_actividad_validos(), "distancia": 5000.5}
        with pytest.raises(ValidationError):
            GuardarActividad(**datos)

    def test_distancia_negativa_falla(self):
        datos = {**_datos_actividad_validos(), "distancia": -1}
        with pytest.raises(ValidationError):
            GuardarActividad(**datos)

    def test_duracion_negativa_falla(self):
        datos = {**_datos_actividad_validos(), "duracion": -100}
        with pytest.raises(ValidationError):
            GuardarActividad(**datos)

    def test_calorias_negativas_fallan(self):
        datos = {**_datos_actividad_validos(), "calorias_quemadas": -50}
        with pytest.raises(ValidationError):
            GuardarActividad(**datos)

    def test_ruta_mapa_url_valida_pasa(self):
        datos = {**_datos_actividad_validos(),
                 "ruta_mapa_url": "https://maps.example.com/ruta?id=123"}
        a = GuardarActividad(**datos)
        assert a.ruta_mapa_url is not None

    def test_ruta_mapa_url_sin_http_falla(self):
        datos = {**_datos_actividad_validos(), "ruta_mapa_url": "no-es-url"}
        with pytest.raises(ValidationError):
            GuardarActividad(**datos)

    def test_ruta_mapa_url_none_pasa(self):
        datos = {**_datos_actividad_validos(), "ruta_mapa_url": None}
        a = GuardarActividad(**datos)
        assert a.ruta_mapa_url is None

    def test_tipo_faltante_falla(self):
        datos = _datos_actividad_validos()
        datos.pop("tipo")
        with pytest.raises(ValidationError):
            GuardarActividad(**datos)

    def test_distancia_faltante_falla(self):
        datos = _datos_actividad_validos()
        datos.pop("distancia")
        with pytest.raises(ValidationError):
            GuardarActividad(**datos)


# ─────────────────────────────────────────────
# ActualizarPerfil
# ─────────────────────────────────────────────

class TestActualizarPerfil:
    def test_objeto_vacio_es_valido(self):
        """PATCH real: todos los campos son opcionales."""
        a = ActualizarPerfil()
        assert a.model_dump(exclude_unset=True) == {}

    def test_solo_email_se_incluye_en_payload(self):
        a = ActualizarPerfil(email="nuevo@test.com")
        payload = a.model_dump(exclude_unset=True)
        assert "email" in payload
        assert "nombre_real" not in payload

    def test_email_invalido_falla(self):
        with pytest.raises(ValidationError):
            ActualizarPerfil(email="no-es-email")

    def test_email_se_normaliza_a_minusculas(self):
        a = ActualizarPerfil(email="NUEVO@TEST.COM")
        assert str(a.email).lower() == "nuevo@test.com"

    def test_password_debil_falla(self):
        with pytest.raises(ValidationError):
            ActualizarPerfil(password="1234")

    def test_genero_invalido_falla(self):
        with pytest.raises(ValidationError):
            ActualizarPerfil(genero="Nave")  # type: ignore[arg-type]

    def test_altura_fuera_de_rango_falla(self):
        with pytest.raises(ValidationError):
            ActualizarPerfil(altura=999)

    def test_peso_negativo_falla(self):
        with pytest.raises(ValidationError):
            ActualizarPerfil(peso=-5.0)

    def test_exclude_unset_distingue_null_de_omitido(self):
        """
        nombre_real=None explícito aparece en el payload;
        altura omitida no aparece.
        """
        a = ActualizarPerfil(nombre_real=None)
        payload = a.model_dump(exclude_unset=True)

        assert "nombre_real" in payload
        assert payload["nombre_real"] is None
        assert "altura" not in payload
        