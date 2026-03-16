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
        assert body["error_code"] == "BAD_REQUEST"
        assert "detail" not in body

    def test_incluye_detail_y_normaliza_error_code(self):
        detalle = [{"columna": "email", "mensaje": "inválido"}]
        resp = error_response(422, "Solicitud inválida", detail=detalle)
        body = _body(resp)

        assert body["error_code"] == "VALIDATION_ERROR"
        assert body["detail"] == [
            {
                "columna": "email",
                "mensaje": "inválido",
                "error_code": "VALIDATION_ERROR",
            }
        ]

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
            assert "error_code" in _body(resp)


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
        assert body["error_code"] == "RESOURCE_NOT_FOUND"
        assert "detail" not in body

    def test_string_detail_400_prioriza_codigo_semantico_sobre_bad_request(self):
        exc = HTTPException(status_code=400, detail="Error: El email ya está en uso")
        resp = manejador_http_exception(_fake_request(), exc)
        body = _body(resp)

        assert resp.status_code == 400
        assert body["mensaje"] == "Error: El email ya está en uso"
        assert body["error_code"] == "BAD_REQUEST"

    def test_list_detail_genera_formato_con_detail(self):
        detalle = [{"columna": "password", "mensaje": "muy corta"}]
        exc = HTTPException(status_code=422, detail=detalle)
        resp = manejador_http_exception(_fake_request(), exc)
        body = _body(resp)

        assert resp.status_code == 422
        assert body["mensaje"] == "Solicitud inválida"
        assert body["error_code"] == "VALIDATION_ERROR"
        assert body["detail"] == [
            {
                "columna": "password",
                "mensaje": "muy corta",
                "error_code": "VALIDATION_ERROR",
            }
        ]

    def test_detail_dict_estructurado_preserva_error_code(self):
        exc = HTTPException(
            status_code=409,
            detail={
                "mensaje": "Error: El email ya está en uso",
                "error_code": "EMAIL_ALREADY_IN_USE",
            },
        )
        resp = manejador_http_exception(_fake_request(), exc)
        body = _body(resp)

        assert resp.status_code == 409
        assert body["mensaje"] == "Error: El email ya está en uso"
        assert body["error_code"] == "EMAIL_ALREADY_IN_USE"

    def test_detail_de_tipo_desconocido_devuelve_mensaje_generico(self):
        exc = HTTPException(status_code=500, detail={"unexpected": "dict"})
        resp = manejador_http_exception(_fake_request(), exc)
        body = _body(resp)

        assert resp.status_code == 500
        assert body["estatus"] == "error"
        assert body["error_code"] == "INTERNAL_SERVER_ERROR"
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
        assert body["error_code"] == "INTERNAL_SERVER_ERROR"
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
        assert body["error_code"] == "VALIDATION_ERROR"

    def test_mensaje_es_solicitud_invalida(self):
        client = TestClient(self._build_app(), raise_server_exceptions=False)
        response = client.post(
            "/test", json={"edad": "no-es-int", "email": "ok@test.com"}
        )

        assert response.json()["mensaje"] == "Solicitud inválida"

    def test_detail_contiene_columna_mensaje_y_error_code(self):
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
        assert "error_code" in primer_error

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
