#
# Sustituye a: test_auth_tokens.py + test_auth_tokens_hardening.py
# Cubre: creación/validación de tokens, hardening JWT (iss/aud/typ),
# y extracción del usuario actual desde credenciales Bearer.

import pytest
from datetime import timedelta
from fastapi import HTTPException
from fastapi.security import HTTPAuthorizationCredentials

import auth


# ─────────────────────────────────────────────
# Tipos de token (typ claim)
# ─────────────────────────────────────────────


class TestTiposDeToken:
    def test_access_token_tiene_typ_access(self):
        token = auth.crear_token_acceso({"sub": "123"})
        payload = auth.decodifica_jwt(token, auth.ACCESS_TOKEN_SECRET, "access")

        assert payload["sub"] == "123"
        assert payload["typ"] == "access"

    def test_refresh_token_tiene_typ_refresh(self):
        token = auth.crear_token_refresh(123, "jti-1", "fam-1")
        payload = auth.decodifica_jwt(token, auth.REFRESH_TOKEN_SECRET, "refresh")

        assert payload["sub"] == "123"
        assert payload["typ"] == "refresh"

    def test_refresh_token_rechazado_como_access(self):
        token = auth.crear_token_refresh(123, "jti-1", "familia-1")
        with pytest.raises(HTTPException):
            auth.decodifica_jwt(token, auth.REFRESH_TOKEN_SECRET, "access")

    def test_access_token_rechazado_como_refresh(self):
        token = auth.crear_token_acceso({"sub": "123"})
        with pytest.raises(HTTPException):
            auth.decodifica_jwt(token, auth.ACCESS_TOKEN_SECRET, "refresh")

    def test_app_session_token_tiene_typ_correcto(self):
        token = auth.crear_token_aplicacion()
        payload = auth.decodifica_jwt(token, auth.APP_SESSION_SECRET, "app_session")
        assert payload["typ"] == "app_session"

    def test_app_session_rechazado_como_access(self):
        token = auth.crear_token_aplicacion()
        with pytest.raises((HTTPException, Exception)):
            auth.decodifica_jwt(token, auth.APP_SESSION_SECRET, "access")


# ─────────────────────────────────────────────
# Hardening: issuer, audience, secreto, manipulación
# ─────────────────────────────────────────────


class TestHardeningJWT:
    def test_audience_incorrecta_falla(self, monkeypatch):
        audience_buena = auth.JWT_AUDIENCE
        monkeypatch.setattr(auth, "JWT_AUDIENCE", "audiencia-incorrecta")
        token = auth.codifica_jwt(
            {"sub": "123"}, auth.ACCESS_TOKEN_SECRET, timedelta(minutes=5), "access"
        )
        monkeypatch.setattr(auth, "JWT_AUDIENCE", audience_buena)

        with pytest.raises(Exception):
            auth.decodifica_jwt(token, auth.ACCESS_TOKEN_SECRET, "access")

    def test_issuer_incorrecto_falla(self, monkeypatch):
        issuer_bueno = auth.JWT_ISSUER
        monkeypatch.setattr(auth, "JWT_ISSUER", "issuer-incorrecto")
        token = auth.codifica_jwt(
            {"sub": "123"}, auth.ACCESS_TOKEN_SECRET, timedelta(minutes=5), "access"
        )
        monkeypatch.setattr(auth, "JWT_ISSUER", issuer_bueno)

        with pytest.raises(Exception):
            auth.decodifica_jwt(token, auth.ACCESS_TOKEN_SECRET, "access")

    def test_secreto_erroneo_falla(self):
        token = auth.codifica_jwt(
            {"sub": "pepe"},
            "secreto-equivocado-12345678901234567890",
            timedelta(minutes=5),
            "access",
        )
        with pytest.raises(Exception):
            auth.decodifica_jwt(token, auth.ACCESS_TOKEN_SECRET, "access")

    def test_token_manipulado_falla(self):
        token = auth.crear_token_acceso({"sub": "123"})
        partes = token.split(".")
        partes[1] = partes[1][:-2] + "ZZ"
        token_manipulado = ".".join(partes)

        with pytest.raises(Exception):
            auth.decodifica_jwt(token_manipulado, auth.ACCESS_TOKEN_SECRET, "access")

    def test_claims_iss_y_aud_presentes(self):
        token = auth.crear_token_acceso({"sub": "123"})
        payload = auth.decodifica_jwt(token, auth.ACCESS_TOKEN_SECRET, "access")

        assert payload["iss"] == auth.JWT_ISSUER
        assert payload["aud"] == auth.JWT_AUDIENCE

    def test_claims_exp_e_iat_presentes(self):
        token = auth.crear_token_acceso({"sub": "123"})
        payload = auth.decodifica_jwt(token, auth.ACCESS_TOKEN_SECRET, "access")

        assert "exp" in payload
        assert "iat" in payload
        assert payload["exp"] > payload["iat"]

    def test_refresh_token_incluye_jti_y_familia(self):
        token = auth.crear_token_refresh(123, "jti-test", "fam-test")
        payload = auth.decodifica_jwt(token, auth.REFRESH_TOKEN_SECRET, "refresh")

        assert payload["jti"] == "jti-test"
        assert payload["fam"] == "fam-test"

    def test_dos_refresh_con_jti_distinto_son_tokens_distintos(self):
        t1 = auth.crear_token_refresh(123, "jti-a", "fam-1")
        t2 = auth.crear_token_refresh(123, "jti-b", "fam-1")
        assert t1 != t2


# ─────────────────────────────────────────────
# obtener_usuario_actual
# ─────────────────────────────────────────────


class TestObtenerUsuarioActual:
    def test_token_valido_devuelve_usuario_id(self):
        token = auth.crear_token_acceso({"sub": "123"})
        creds = HTTPAuthorizationCredentials(scheme="Bearer", credentials=token)

        assert auth.obtener_usuario_actual(creds) == 123

    def test_rechaza_token_sin_sub(self):
        token = auth.codifica_jwt(
            {}, auth.ACCESS_TOKEN_SECRET, timedelta(minutes=5), "access"
        )
        creds = HTTPAuthorizationCredentials(scheme="Bearer", credentials=token)

        with pytest.raises(HTTPException) as exc:
            auth.obtener_usuario_actual(creds)

        assert exc.value.status_code == 401
        assert "usuario válido" in exc.value.detail.lower()

    def test_rechaza_token_con_sub_no_string(self):
        token = auth.codifica_jwt(
            {"sub": 99999}, auth.ACCESS_TOKEN_SECRET, timedelta(minutes=5), "access"
        )
        creds = HTTPAuthorizationCredentials(scheme="Bearer", credentials=token)

        with pytest.raises(HTTPException) as exc:
            auth.obtener_usuario_actual(creds)

        assert exc.value.status_code == 401

    def test_token_de_refresh_rechazado_en_endpoint(self):
        token = auth.crear_token_refresh(123, "jti-x", "fam-x")
        creds = HTTPAuthorizationCredentials(scheme="Bearer", credentials=token)

        with pytest.raises(HTTPException) as exc:
            auth.obtener_usuario_actual(creds)

        assert exc.value.status_code == 401

    def test_token_completamente_invalido_rechazado(self):
        creds = HTTPAuthorizationCredentials(
            scheme="Bearer", credentials="token.basura.fake"
        )

        with pytest.raises(HTTPException) as exc:
            auth.obtener_usuario_actual(creds)

        assert exc.value.status_code == 401
