# tests/test_request_size.py

"""Valida el middleware que limita el tamaño de los cuerpos HTTP entrantes.

La suite comprueba respuestas tempranas, streaming sin ``Content-Length`` y
casos de desconexión del cliente sin bucles ni fugas de estado.
"""

from __future__ import annotations

import pytest
from fastapi import FastAPI, Request
from fastapi.testclient import TestClient

from middlewares.request_size import RequestSizeLimitMiddleware


def _build_app() -> FastAPI:
    """Construye la aplicación de prueba."""
    # Crear la aplicación de prueba y registrar sus manejadores.
    app = FastAPI()
    app.add_middleware(
        RequestSizeLimitMiddleware,
        route_limits={
            ("POST", "/login"): 128,
            ("POST", "/registro"): 256,
            ("POST", "/password/solicitar"): 64,
            ("POST", "/password/confirmar"): 128,
            ("POST", "/stream-body"): 128,
        },
    )

    @app.post("/login")
    async def login(request: Request):
        """Gestiona el inicio de sesión del usuario."""
        return {"ok": True, "body": await request.json()}

    @app.post("/registro")
    async def registro(request: Request):
        """Gestiona registro."""
        return {"ok": True, "body": await request.json()}

    @app.post("/password/solicitar")
    async def solicitar(request: Request):
        """Gestiona solicitar."""
        return {"ok": True, "body": await request.json()}

    @app.post("/password/confirmar")
    async def confirmar(request: Request):
        """Gestiona confirmar."""
        return {"ok": True, "body": await request.json()}

    @app.post("/perfil/foto")
    async def foto(request: Request):
        """Gestiona foto."""
        return {"ok": True, "size": len(await request.body())}

    @app.post("/stream-body")
    async def stream_body(request: Request):
        """Gestiona stream body."""
        return {"ok": True, "size": len(await request.body())}

    return app


class TestRequestSizeLimitMiddleware:
    """Agrupa pruebas relacionadas con request size limit middleware."""

    def test_login_pequeno_pasa_y_body_llega_intacto(self):
        """Verifica que login pequeno pasa y body llega intacto."""
        client = TestClient(_build_app())
        payload = {"identificador": "pepe", "password": "Pass1234"}

        response = client.post("/login", json=payload)

        assert response.status_code == 200
        assert response.json()["body"] == payload

    def test_login_grande_devuelve_413_con_json_y_no_store(self):
        """Verifica que login grande devuelve 413 con JSON y no store."""
        client = TestClient(_build_app())
        payload = {"identificador": "pepe", "password": "x" * 500}

        response = client.post("/login", json=payload)

        assert response.status_code == 413
        assert response.json()["estatus"] == "error"
        assert "tamaño máximo" in response.json()["mensaje"]
        assert response.headers["content-type"].startswith("application/json")
        assert response.headers["cache-control"] == "no-store"
        assert response.headers["pragma"] == "no-cache"

    def test_registro_tiene_limite_distinto(self):
        """Verifica que registro tiene limite distinto."""
        client = TestClient(_build_app())
        payload = {
            "email": "pepe@example.com",
            "nombre_usuario": "pepe",
            "bio": "x" * 150,
        }

        response = client.post("/registro", json=payload)

        assert response.status_code == 200

    def test_ruta_no_configurada_no_se_limita_con_este_middleware(self):
        """Verifica que ruta no configurada no se limita con este middleware."""
        client = TestClient(_build_app())
        response = client.post(
            "/perfil/foto",
            content=b"x" * 5000,
            headers={"content-type": "application/octet-stream"},
        )

        assert response.status_code == 200
        assert response.json()["size"] == 5000


@pytest.mark.asyncio
async def test_limitacion_streaming_sin_content_length_devuelve_413_y_no_store():
    """Verifica que limitacion streaming sin content length devuelve 413 y no store."""
    # Verifica que limitacion streaming sin content length devuelve 413 y no store.
    app = _build_app()

    messages = [
        {"type": "http.request", "body": b'{"identificador":"pe', "more_body": True},
        {
            "type": "http.request",
            "body": b'pe","password":"' + (b"x" * 200) + b'"}',
            "more_body": False,
        },
    ]

    async def receive():
        """Gestiona receive."""
        if messages:
            return messages.pop(0)
        return {"type": "http.request", "body": b"", "more_body": False}

    sent = []

    async def send(message):
        """Gestiona send."""
        sent.append(message)

    scope = {
        "type": "http",
        "asgi": {"version": "3.0"},
        "http_version": "1.1",
        "method": "POST",
        "scheme": "http",
        "path": "/login",
        "raw_path": b"/login",
        "query_string": b"",
        "root_path": "",
        "headers": [(b"content-type", b"application/json")],
        "client": ("127.0.0.1", 12345),
        "server": ("testserver", 80),
    }

    await app(scope, receive, send)

    start = next(m for m in sent if m["type"] == "http.response.start")
    body = next(m for m in sent if m["type"] == "http.response.body")

    headers = {
        k.decode("latin-1").lower(): v.decode("latin-1")
        for k, v in start.get("headers", [])
    }

    assert start["status"] == 413
    assert headers["content-type"].startswith("application/json")
    assert headers["cache-control"] == "no-store"
    assert headers["pragma"] == "no-cache"
    assert b"tama" in body["body"] or b"m\xc3\xa1ximo" in body["body"]


@pytest.mark.asyncio
async def test_disconnect_no_entra_en_bucle_y_reinyecta_mensajes():
    """Verifica que disconnect no entra en bucle y reinyecta mensajes."""
    # Verifica que disconnect no entra en bucle y reinyecta mensajes.
    recibidos = []

    async def downstream(scope, receive, send):
        """Gestiona downstream."""
        recibidos.append(await receive())
        recibidos.append(await receive())
        await send({"type": "http.response.start", "status": 204, "headers": []})
        await send({"type": "http.response.body", "body": b"", "more_body": False})

    app = RequestSizeLimitMiddleware(
        downstream,
        route_limits={("POST", "/stream-body"): 128},
    )

    messages = [
        {"type": "http.request", "body": b"abc", "more_body": True},
        {"type": "http.disconnect"},
    ]

    async def receive():
        """Gestiona receive."""
        if messages:
            return messages.pop(0)
        pytest.fail("El middleware siguió leyendo tras http.disconnect")

    sent = []

    async def send(message):
        """Gestiona send."""
        sent.append(message)

    scope = {
        "type": "http",
        "asgi": {"version": "3.0"},
        "http_version": "1.1",
        "method": "POST",
        "scheme": "http",
        "path": "/stream-body",
        "raw_path": b"/stream-body",
        "query_string": b"",
        "root_path": "",
        "headers": [(b"content-type", b"application/octet-stream")],
        "client": ("127.0.0.1", 12345),
        "server": ("testserver", 80),
    }

    await app(scope, receive, send)

    start = next(m for m in sent if m["type"] == "http.response.start")

    assert start["status"] == 204
    assert recibidos == [
        {"type": "http.request", "body": b"abc", "more_body": True},
        {"type": "http.disconnect"},
    ]
