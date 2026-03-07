# tests/test_identity_rate_limit.py

import time
import pytest
from unittest.mock import patch

from services.identity_rate_limit import (
    IdentityRateLimitExceeded,
    _BUCKETS,
    _parse_limit,
    _purge_old,
    check_identity_limit,
)
from services import identity_rate_limit


def _limpiar_buckets():
    _BUCKETS.clear()


class TestParseLimit:
    def test_minutos(self):
        assert _parse_limit("10/minute") == (10, 60)

    def test_minutos_plural(self):
        assert _parse_limit("5/minutes") == (5, 60)

    def test_segundos(self):
        assert _parse_limit("3/second") == (3, 1)

    def test_segundos_plural(self):
        assert _parse_limit("3/seconds") == (3, 1)

    def test_horas(self):
        assert _parse_limit("100/hour") == (100, 3600)

    def test_horas_plural(self):
        assert _parse_limit("100/hours") == (100, 3600)

    def test_dias(self):
        assert _parse_limit("1000/day") == (1000, 86400)

    def test_dias_plural(self):
        assert _parse_limit("1000/days") == (1000, 86400)

    def test_cadena_vacia_devuelve_none(self):
        assert _parse_limit("") is None

    def test_none_devuelve_none(self):
        assert _parse_limit(None) is None  # type: ignore[arg-type]

    def test_formato_invalido_sin_barra_devuelve_none(self):
        assert _parse_limit("10minute") is None

    def test_unidad_desconocida_devuelve_none(self):
        assert _parse_limit("10/week") is None

    def test_n_cero_devuelve_none(self):
        assert _parse_limit("0/minute") is None

    def test_n_negativo_devuelve_none(self):
        assert _parse_limit("-5/minute") is None

    def test_n_no_entero_devuelve_none(self):
        assert _parse_limit("abc/minute") is None

    def test_espacios_alrededor_se_toleran(self):
        assert _parse_limit("  10 / minute ") == (10, 60)


class TestPurgeOld:
    def setup_method(self):
        _limpiar_buckets()

    def test_expire_borra_buckets_caducados(self):
        now = time.time()

        # Simulamos un bucket antiguo
        _BUCKETS[("scope", "id1")] = (now - 10, 1)

        # Forzamos expiración "en el futuro" para el test
        _purge_old(now + (24 * 3600) + 1)

        assert ("scope", "id1") not in _BUCKETS

    def test_expire_no_borra_buckets_recientes(self):
        now = time.time()
        _BUCKETS[("scope", "id1")] = (now, 1)

        _purge_old(now + 10)

        assert ("scope", "id1") in _BUCKETS


class TestCheckIdentityLimitFeatureFlag:
    def setup_method(self):
        _limpiar_buckets()

    def test_desactivado_nunca_lanza(self):
        with patch.object(identity_rate_limit.settings, "ENABLE_RATE_LIMIT_ID", False):
            for _ in range(100):
                check_identity_limit("login", "test@test.com", "1/minute")

    def test_limite_invalido_nunca_lanza(self):
        with patch.object(identity_rate_limit.settings, "ENABLE_RATE_LIMIT_ID", True):
            for _ in range(100):
                check_identity_limit("login", "test@test.com", "formato_invalido")

    def test_identidad_vacia_nunca_lanza(self):
        with patch.object(identity_rate_limit.settings, "ENABLE_RATE_LIMIT_ID", True):
            for _ in range(100):
                check_identity_limit("login", "", "1/minute")


class TestCheckIdentityLimitVentana:
    def setup_method(self):
        _limpiar_buckets()

    def test_dentro_del_limite_no_lanza(self):
        with patch.object(identity_rate_limit.settings, "ENABLE_RATE_LIMIT_ID", True):
            for _ in range(5):
                check_identity_limit("login", "user@test.com", "10/minute")

    def test_superar_limite_lanza_excepcion(self):
        with patch.object(identity_rate_limit.settings, "ENABLE_RATE_LIMIT_ID", True):
            with pytest.raises(IdentityRateLimitExceeded):
                for _ in range(20):
                    check_identity_limit("login", "user@test.com", "5/minute")

    def test_ventana_expirada_resetea_contador(self):
        key = ("registro", "reset@test.com")
        now = time.time()
        _BUCKETS[key] = (now - 120, 99)

        with patch.object(identity_rate_limit.settings, "ENABLE_RATE_LIMIT_ID", True):
            check_identity_limit("registro", "reset@test.com", "1/minute")

        window_start, count = _BUCKETS[key]
        assert count == 1

    def test_identidad_se_normaliza_a_minusculas(self):
        with patch.object(identity_rate_limit.settings, "ENABLE_RATE_LIMIT_ID", True):
            check_identity_limit("login", "USER@TEST.COM", "3/minute")
            check_identity_limit("login", "user@test.com", "3/minute")
            check_identity_limit("login", "User@Test.Com", "3/minute")

        key = ("login", "user@test.com")
        assert _BUCKETS[key][1] == 3


class TestCheckIdentityLimitScopes:
    def setup_method(self):
        _limpiar_buckets()

    def test_scopes_distintos_no_se_mezclan(self):
        identidad = "shared@test.com"

        with patch.object(identity_rate_limit.settings, "ENABLE_RATE_LIMIT_ID", True):
            with pytest.raises(IdentityRateLimitExceeded):
                for _ in range(10):
                    check_identity_limit("login", identidad, "3/minute")

        with patch.object(identity_rate_limit.settings, "ENABLE_RATE_LIMIT_ID", True):
            check_identity_limit("registro", identidad, "3/minute")

    def test_identidades_distintas_no_se_mezclan(self):
        with patch.object(identity_rate_limit.settings, "ENABLE_RATE_LIMIT_ID", True):
            with pytest.raises(IdentityRateLimitExceeded):
                for _ in range(10):
                    check_identity_limit("login", "user_a@test.com", "3/minute")

        with patch.object(identity_rate_limit.settings, "ENABLE_RATE_LIMIT_ID", True):
            check_identity_limit("login", "user_b@test.com", "3/minute")

    def test_password_solicitar_y_confirmar_son_scopes_distintos(self):
        identidad = "recovery@test.com"

        with patch.object(identity_rate_limit.settings, "ENABLE_RATE_LIMIT_ID", True):
            with pytest.raises(IdentityRateLimitExceeded):
                for _ in range(10):
                    check_identity_limit("password_solicitar", identidad, "2/hour")

        with patch.object(identity_rate_limit.settings, "ENABLE_RATE_LIMIT_ID", True):
            check_identity_limit("password_confirmar", identidad, "2/hour")
            