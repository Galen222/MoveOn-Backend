# tests/test_config.py
#
# Tests para los validators de config.py (Settings).
# Cubre: parse_cors_origins, validar_public_base_url,
#        validar_secretos_fuertes, validar_secretos_distintos.
#
# Estrategia:
# - Los validators se testean DIRECTAMENTE (son classmethods) para cubrir
#   todos los tipos de entrada (None, list, int, etc.), ya que os.environ
#   solo acepta strings y pydantic-settings intenta JSON-decodear tipos complejos.
# - Settings se construye solo para tests de integración con valores string-compatibles.

import os
import pytest
from unittest.mock import patch, MagicMock
from pydantic import ValidationError, ValidationInfo

from config import Settings


# ─────────────────────────────────────────────
# Helper: entorno mínimo válido
# ─────────────────────────────────────────────

def _env(**overrides) -> dict:
    """Devuelve un dict con todos los campos requeridos válidos (solo strings)."""
    base = {
        "DB_USER": "test",
        "DB_PASSWORD": "test",
        "DB_HOST": "localhost",
        "DB_PORT": "5432",
        "DB_NAME": "test",
        "APP_ID": "test-app-id",
        "APP_SESSION_SECRET":   "secret-app-session-unique-00001-pad",
        "ACCESS_TOKEN_SECRET":  "secret-access-token-unique-00002-pad",
        "REFRESH_TOKEN_SECRET": "secret-refresh-token-unique-00003-pad",
        "REFRESH_HASH_SECRET":  "secret-refresh-hash-unique-000004-pad",
        "CODE_HASH_SECRET":     "secret-code-hash-unique-0000005-pad",
        "EMAIL_HOST": "smtp.test.com",
        "EMAIL_USER": "noreply@test.com",
        "EMAIL_PASS": "test-pass",
        "STORAGE_TYPE": "local",
    }
    base.update(overrides)
    return base


def _build_settings(**overrides) -> Settings:
    """Construye un Settings válido con env_file desactivado."""
    env = _env(**overrides)
    with patch.dict(os.environ, env, clear=False):
        return Settings(_env_file=None, **env) # type: ignore


def _fake_info(field_name: str) -> ValidationInfo:
    """Crea un ValidationInfo fake para los validators que lo requieren."""
    info = MagicMock(spec=ValidationInfo)
    info.field_name = field_name
    return info


# ─────────────────────────────────────────────
# parse_cors_origins (validator directo)
# ─────────────────────────────────────────────

class TestParseCorsOrigins:
    def test_string_csv_se_parsea_a_lista(self):
        resultado = Settings.parse_cors_origins("https://a.com, https://b.com")
        assert resultado == ["https://a.com", "https://b.com"]

    def test_string_vacio_devuelve_lista_vacia(self):
        resultado = Settings.parse_cors_origins("")
        assert resultado == []

    def test_none_devuelve_lista_vacia(self):
        resultado = Settings.parse_cors_origins(None)
        assert resultado == []

    def test_lista_pasa_tal_cual(self):
        resultado = Settings.parse_cors_origins(["https://x.com"])
        assert resultado == ["https://x.com"]

    def test_ignora_entradas_vacias_entre_comas(self):
        resultado = Settings.parse_cors_origins("https://a.com,,, ,https://b.com")
        assert resultado == ["https://a.com", "https://b.com"]

    def test_tipo_invalido_lanza_error(self):
        with pytest.raises(ValueError, match="CORS_ORIGINS"):
            Settings.parse_cors_origins(12345)

    def test_lista_con_espacios_se_limpia(self):
        resultado = Settings.parse_cors_origins(["  https://a.com  ", " https://b.com "])
        assert resultado == ["https://a.com", "https://b.com"]

    def test_string_un_solo_origen(self):
        resultado = Settings.parse_cors_origins("https://miapp.com")
        assert resultado == ["https://miapp.com"]


# ─────────────────────────────────────────────
# validar_public_base_url (validator directo)
# ─────────────────────────────────────────────

class TestValidarPublicBaseUrl:
    def test_vacio_devuelve_string_vacio(self):
        resultado = Settings.validar_public_base_url("")
        assert resultado == ""

    def test_none_devuelve_string_vacio(self):
        resultado = Settings.validar_public_base_url(None)
        assert resultado == ""

    def test_url_https_valida_se_acepta(self):
        resultado = Settings.validar_public_base_url("https://api.moveon.com")
        assert resultado == "https://api.moveon.com"

    def test_url_http_valida_se_acepta(self):
        resultado = Settings.validar_public_base_url("http://localhost:8000")
        assert resultado == "http://localhost:8000"

    def test_elimina_barra_final(self):
        resultado = Settings.validar_public_base_url("https://api.moveon.com/")
        assert resultado == "https://api.moveon.com"

    def test_elimina_multiples_barras_finales(self):
        resultado = Settings.validar_public_base_url("https://api.moveon.com///")
        assert not resultado.endswith("/")

    def test_sin_esquema_lanza_error(self):
        with pytest.raises(ValueError, match="http://"):
            Settings.validar_public_base_url("api.moveon.com")

    def test_tipo_no_string_lanza_error(self):
        with pytest.raises(ValueError, match="string"):
            Settings.validar_public_base_url(12345)

    def test_integra_con_settings(self):
        """Verifica que funciona a través del constructor de Settings."""
        s = _build_settings(PUBLIC_BASE_URL="https://api.moveon.com/")
        assert s.PUBLIC_BASE_URL == "https://api.moveon.com"


# ─────────────────────────────────────────────
# validar_secretos_fuertes (validator directo + integración)
# ─────────────────────────────────────────────

class TestValidarSecretosFuertes:
    def test_secreto_de_32_chars_se_acepta(self):
        secreto = "abcdefghijklmnopqrstuvwxyz123456"  # 32 chars, >8 únicos
        resultado = Settings.validar_secretos_fuertes(secreto, _fake_info("APP_SESSION_SECRET"))
        assert resultado == secreto

    def test_secreto_corto_lanza_error(self):
        with pytest.raises(ValueError, match="32 caracteres"):
            Settings.validar_secretos_fuertes("corto", _fake_info("APP_SESSION_SECRET"))

    def test_secreto_con_poca_entropia_lanza_error(self):
        """Un secreto de 32 chars pero con <8 chars únicos es rechazado."""
        with pytest.raises(ValueError, match="entropía"):
            Settings.validar_secretos_fuertes("a" * 32, _fake_info("APP_SESSION_SECRET"))

    def test_secreto_7_chars_unicos_lanza_error(self):
        secreto = "abcdefg" * 5  # 35 chars, 7 únicos
        with pytest.raises(ValueError, match="entropía"):
            Settings.validar_secretos_fuertes(secreto, _fake_info("APP_SESSION_SECRET"))

    def test_secreto_8_chars_unicos_se_acepta(self):
        secreto = "abcdefgh" * 4  # 32 chars, 8 únicos
        resultado = Settings.validar_secretos_fuertes(secreto, _fake_info("APP_SESSION_SECRET"))
        assert resultado == secreto

    def test_valor_trivial_changeme_lanza_error(self):
        """'changeme' falla por longitud (<32), no por lista negra."""
        with pytest.raises(ValueError, match="32 caracteres"):
            Settings.validar_secretos_fuertes("changeme", _fake_info("APP_SESSION_SECRET"))

    def test_tipo_no_string_lanza_error(self):
        with pytest.raises(ValueError, match="string"):
            Settings.validar_secretos_fuertes(12345, _fake_info("APP_SESSION_SECRET"))

    def test_aplica_a_todos_los_secretos_via_settings(self):
        """Cada uno de los 5 secretos pasa por el validador al construir Settings."""
        campos_secretos = [
            "APP_SESSION_SECRET",
            "ACCESS_TOKEN_SECRET",
            "REFRESH_TOKEN_SECRET",
            "REFRESH_HASH_SECRET",
            "CODE_HASH_SECRET",
        ]
        for campo in campos_secretos:
            with pytest.raises((ValidationError, ValueError)):
                _build_settings(**{campo: "corto"})

    def test_integra_secreto_valido_con_settings(self):
        """Un secreto válido pasa la construcción de Settings sin error."""
        s = _build_settings()
        assert len(s.APP_SESSION_SECRET) >= 32


# ─────────────────────────────────────────────
# validar_secretos_distintos (requiere Settings completo)
# ─────────────────────────────────────────────

class TestValidarSecretosDistintos:
    def test_secretos_identicos_lanza_error(self):
        mismo = "secreto-identico-para-todos-los-campos!"
        with pytest.raises(ValidationError, match="distintos"):
            _build_settings(
                APP_SESSION_SECRET=mismo,
                ACCESS_TOKEN_SECRET=mismo,
                REFRESH_TOKEN_SECRET=mismo,
                REFRESH_HASH_SECRET=mismo,
                CODE_HASH_SECRET=mismo,
            )

    def test_dos_secretos_iguales_lanza_error(self):
        duplicado = "secreto-duplicado-entre-dos-campos!!"
        with pytest.raises(ValidationError, match="distintos"):
            _build_settings(
                APP_SESSION_SECRET=duplicado,
                ACCESS_TOKEN_SECRET=duplicado,
            )

    def test_todos_distintos_se_acepta(self):
        """El caso normal: cada secreto es diferente."""
        s = _build_settings()
        secretos = [
            s.APP_SESSION_SECRET,
            s.ACCESS_TOKEN_SECRET,
            s.REFRESH_TOKEN_SECRET,
            s.REFRESH_HASH_SECRET,
            s.CODE_HASH_SECRET,
        ]
        assert len(set(secretos)) == 5
        