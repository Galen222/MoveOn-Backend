# tests/test_exceptions.py
#
# Tests para exceptions.py.
# Cubre: error_response, manejador_http_exception,
# manejador_excepcion_no_controlada y manejador_validacion_personalizado.
#
# Para el manejador de validación usamos una app FastAPI real con TestClient,
# que es la forma más fiable de disparar un RequestValidationError real.

import json
from unittest.mock import MagicMock, patch

from fastapi import FastAPI, HTTPException
from fastapi.exceptions import RequestValidationError
from fastapi.testclient import TestClient
from pydantic import BaseModel

from exceptions import (
    error_response,
    manejador_http_exception,
    manejador_excepcion_no_controlada,
    manejador_validacion_personalizado,
)


# ─────────────────────────────────────────────
# Helper
# ─────────────────────────────────────────────


def _fake_request():
    req = MagicMock()
    req.method = "GET"
    req.url.path = "/test"
    return req


def _body(resp) -> dict:
    return json.loads(resp.body)


# ─────────────────────────────────────────────
# error_response
# ─────────────────────────────────────────────


class TestErrorResponse:
    def test_formato_basico_sin_detail(self):
        resp = error_response(400, "algo malo")
        body = _body(resp)

        assert resp.status_code == 400
        assert body["estatus"] == "error"
        assert body["mensaje"] == "algo malo"
        assert "detail" not in body

    def test_incluye_detail_cuando_se_pasa(self):
        detalle = [{"columna": "email", "mensaje": "inválido"}]
        resp = error_response(422, "Solicitud inválida", detail=detalle)
        body = _body(resp)

        assert body["detail"] == detalle

    def test_no_incluye_detail_cuando_es_none(self):
        resp = error_response(400, "error", detail=None)
        body = _body(resp)
        assert "detail" not in body

    def test_propaga_headers_personalizados(self):
        headers = {"x-app-session-expired": "1"}
        resp = error_response(403, "token expirado", headers=headers)

        assert resp.headers.get("x-app-session-expired") == "1"

    def test_distintos_status_codes(self):
        for code in [400, 401, 403, 404, 429, 500]:
            resp = error_response(code, "mensaje")
            assert resp.status_code == code


# ─────────────────────────────────────────────
# manejador_http_exception
# ─────────────────────────────────────────────


class TestManejadorHttpException:
    def test_string_detail_se_convierte_a_mensaje(self):
        exc = HTTPException(status_code=404, detail="Error: recurso no encontrado")
        resp = manejador_http_exception(_fake_request(), exc)
        body = _body(resp)

        assert resp.status_code == 404
        assert body["estatus"] == "error"
        assert body["mensaje"] == "Error: recurso no encontrado"
        assert "detail" not in body

    def test_list_detail_genera_formato_con_detail(self):
        detalle = [{"columna": "password", "mensaje": "muy corta"}]
        exc = HTTPException(status_code=422, detail=detalle)
        resp = manejador_http_exception(_fake_request(), exc)
        body = _body(resp)

        assert resp.status_code == 422
        assert body["mensaje"] == "Solicitud inválida"
        assert body["detail"] == detalle

    def test_detail_de_tipo_desconocido_devuelve_mensaje_generico(self):
        exc = HTTPException(status_code=500, detail={"unexpected": "dict"})
        resp = manejador_http_exception(_fake_request(), exc)
        body = _body(resp)

        assert resp.status_code == 500
        assert body["estatus"] == "error"
        assert "unexpected" not in body.get("mensaje", "")

    def test_propaga_headers_de_la_excepcion(self):
        """Headers como x-app-session-expired deben llegar al cliente."""
        exc = HTTPException(
            status_code=403,
            detail="token expirado",
            headers={"x-app-session-expired": "1"},
        )
        resp = manejador_http_exception(_fake_request(), exc)
        assert resp.headers.get("x-app-session-expired") == "1"

    def test_401_preserva_status_code(self):
        exc = HTTPException(status_code=401, detail="Error: no autorizado")
        resp = manejador_http_exception(_fake_request(), exc)
        assert resp.status_code == 401


# ─────────────────────────────────────────────
# manejador_excepcion_no_controlada
# ─────────────────────────────────────────────


class TestManejadorExcepcionNoControlada:
    def test_devuelve_500_con_mensaje_generico(self):
        resp = manejador_excepcion_no_controlada(
            _fake_request(), ValueError("algo interno")
        )
        body = _body(resp)

        assert resp.status_code == 500
        assert body["estatus"] == "error"
        assert "interno" in body["mensaje"].lower()
        assert "ValueError" not in body["mensaje"]
        assert "algo interno" not in body["mensaje"]

    def test_funciona_con_distintos_tipos_de_excepcion(self):
        for exc in [RuntimeError("x"), KeyError("k"), Exception("genérica")]:
            resp = manejador_excepcion_no_controlada(_fake_request(), exc)
            assert resp.status_code == 500

    def test_loggea_error_global_con_campos_estructurados(self):
        fake_logger = MagicMock()

        with patch(
            "exceptions.logging.getLogger", return_value=fake_logger
        ) as mock_get_logger:
            resp = manejador_excepcion_no_controlada(
                _fake_request(), RuntimeError("boom")
            )

        assert resp.status_code == 500
        mock_get_logger.assert_called_once_with("app.error")
        fake_logger.exception.assert_called_once()

        args, kwargs = fake_logger.exception.call_args
        assert args[0] == "excepcion_no_controlada"
        assert kwargs["extra"] == {
            "method": "GET",
            "path": "/test",
        }


# ─────────────────────────────────────────────
# manejador_validacion_personalizado
# ─────────────────────────────────────────────


class TestManejadorValidacionPersonalizado:
    """
    Usa TestClient con una app real para disparar RequestValidationError
    de Pydantic y verificar que el manejador produce el formato estándar.
    """

    def _build_app(self):
        app = FastAPI()
        app.add_exception_handler(
            RequestValidationError, manejador_validacion_personalizado
        )

        class Payload(BaseModel):
            edad: int
            email: str

        @app.post("/test")
        async def endpoint(datos: Payload):
            return datos

        return app

    def test_error_pydantic_devuelve_422_con_estatus_error(self):
        client = TestClient(self._build_app(), raise_server_exceptions=False)
        response = client.post(
            "/test", json={"edad": "no-es-int", "email": "ok@test.com"}
        )

        assert response.status_code == 422
        body = response.json()
        assert body["estatus"] == "error"

    def test_mensaje_es_solicitud_invalida(self):
        client = TestClient(self._build_app(), raise_server_exceptions=False)
        response = client.post(
            "/test", json={"edad": "no-es-int", "email": "ok@test.com"}
        )

        assert response.json()["mensaje"] == "Solicitud inválida"

    def test_detail_contiene_columna_y_mensaje(self):
        client = TestClient(self._build_app(), raise_server_exceptions=False)
        response = client.post(
            "/test", json={"edad": "no-es-int", "email": "ok@test.com"}
        )

        body = response.json()
        assert "detail" in body
        errores = body["detail"]
        assert isinstance(errores, list)
        assert len(errores) >= 1

        primer_error = errores[0]
        assert "columna" in primer_error
        assert "mensaje" in primer_error

    def test_columna_identifica_el_campo_correcto(self):
        client = TestClient(self._build_app(), raise_server_exceptions=False)
        response = client.post(
            "/test", json={"edad": "no-es-int", "email": "ok@test.com"}
        )

        columnas = [e["columna"] for e in response.json()["detail"]]
        assert "edad" in columnas

    def test_mensaje_no_incluye_prefijos_tecnicos_de_pydantic(self):
        """
        Pydantic v2 prefixa los mensajes con 'Value error, ', 'Input should be...', etc.
        El manejador debe limpiarlos.
        """
        client = TestClient(self._build_app(), raise_server_exceptions=False)
        response = client.post(
            "/test", json={"edad": "no-es-int", "email": "ok@test.com"}
        )

        for error in response.json()["detail"]:
            msg = error["mensaje"]
            assert not msg.startswith("Value error,"), f"Prefijo no limpiado: {msg}"
            assert not msg.startswith("value error,"), f"Prefijo no limpiado: {msg}"

    def test_mensaje_empieza_con_mayuscula(self):
        """El manejador capitaliza el primer carácter del mensaje."""
        client = TestClient(self._build_app(), raise_server_exceptions=False)
        response = client.post(
            "/test", json={"edad": "no-es-int", "email": "ok@test.com"}
        )

        for error in response.json()["detail"]:
            msg = error["mensaje"]
            if msg:
                assert msg[0].isupper(), f"Mensaje no capitalizado: {msg}"

    def test_campo_faltante_tambien_genera_error_con_formato_correcto(self):
        """Enviar un JSON vacío debe producir errores para todos los campos requeridos."""
        client = TestClient(self._build_app(), raise_server_exceptions=False)
        response = client.post("/test", json={})

        assert response.status_code == 422
        errores = response.json()["detail"]
        columnas = {e["columna"] for e in errores}
        assert "edad" in columnas
        assert "email" in columnas
