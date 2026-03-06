# tests/test_schemas_actualizar_perfil.py

import pytest
from pydantic import ValidationError

from schemas import ActualizarPerfil


def test_actualizar_perfil_rechaza_password_debil():
    with pytest.raises(ValidationError):
        ActualizarPerfil(password="1")


def test_actualizar_perfil_acepta_password_valida():
    datos = ActualizarPerfil(password="Password1")
    assert datos.password == "Password1"