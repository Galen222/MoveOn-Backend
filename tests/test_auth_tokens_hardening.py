import pytest
from datetime import timedelta
from fastapi import HTTPException
from fastapi.security import HTTPAuthorizationCredentials

import auth


def test_access_token_con_audience_incorrecta_falla(monkeypatch):
    audience_buena = auth.JWT_AUDIENCE
    monkeypatch.setattr(auth, "JWT_AUDIENCE", "audiencia-incorrecta")
    token = auth.codifica_jwt(
        {"sub": "pepe"},
        auth.ACCESS_TOKEN_SECRET,
        timedelta(minutes=5),
        "access",
    )
    monkeypatch.setattr(auth, "JWT_AUDIENCE", audience_buena)

    with pytest.raises(Exception):
        auth.decodifica_jwt(token, auth.ACCESS_TOKEN_SECRET, "access")


def test_access_token_con_issuer_incorrecto_falla(monkeypatch):
    issuer_bueno = auth.JWT_ISSUER
    monkeypatch.setattr(auth, "JWT_ISSUER", "issuer-incorrecto")
    token = auth.codifica_jwt(
        {"sub": "pepe"},
        auth.ACCESS_TOKEN_SECRET,
        timedelta(minutes=5),
        "access",
    )
    monkeypatch.setattr(auth, "JWT_ISSUER", issuer_bueno)

    with pytest.raises(Exception):
        auth.decodifica_jwt(token, auth.ACCESS_TOKEN_SECRET, "access")


def test_access_token_con_secret_erroneo_falla():
    token = auth.codifica_jwt(
        {"sub": "pepe"},
        "secreto-equivocado-12345678901234567890",
        timedelta(minutes=5),
        "access",
    )

    with pytest.raises(Exception):
        auth.decodifica_jwt(token, auth.ACCESS_TOKEN_SECRET, "access")


def test_obtener_usuario_actual_rechaza_token_sin_sub():
    token = auth.codifica_jwt(
        {},
        auth.ACCESS_TOKEN_SECRET,
        timedelta(minutes=5),
        "access",
    )
    credenciales = HTTPAuthorizationCredentials(scheme="Bearer", credentials=token)

    with pytest.raises(HTTPException) as exc:
        auth.obtener_usuario_actual(credenciales)

    assert exc.value.status_code == 401
    assert "usuario válido" in exc.value.detail.lower()
