# tests/test_auth_tokens.py

import pytest
from fastapi import HTTPException

import auth


def test_access_token_tiene_typ_access():
    token = auth.crear_token_acceso({"sub": "pepe"})
    payload = auth.decodifica_jwt(token, auth.ACCESS_TOKEN_SECRET, "access")

    assert payload["sub"] == "pepe"
    assert payload["typ"] == "access"


def test_refresh_token_no_vale_como_access():
    token = auth.crear_token_refresh("pepe", "jti-1", "familia-1")

    with pytest.raises(HTTPException):
        auth.decodifica_jwt(token, auth.REFRESH_TOKEN_SECRET, "access")