from __future__ import annotations

from typing import Any

import pytest
from fastapi import FastAPI, Request
from fastapi.testclient import TestClient
from fastapi.responses import JSONResponse


# Doble minimalista de exceptions.error_response para ejecutar el test de forma aislada.
def error_response(status_code: int, mensaje: str, detail=None, headers=None) -> JSONResponse:
    content: dict[str, Any] = {"estatus": "error", "mensaje": mensaje}
    if detail is not None:
        content["detail"] = detail
    return JSONResponse(status_code=status_code, content=content, headers=headers)


class RequestSizeLimitMiddleware:
    def __init__(self, app, route_limits=None, error_message="El cuerpo de la solicitud supera el tamaño máximo permitido"):
        self.app = app
        self.route_limits = {
            (method.upper(), path): int(limit)
            for (method, path), limit in (route_limits or {}).items()
            if int(limit) > 0
        }
        self.error_message = error_message

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        method = scope.get("method", "").upper()
        path = scope.get("path", "")
        limit = self.route_limits.get((method, path))

        if not limit:
            await self.app(scope, receive, send)
            return

        headers = {
            key.decode("latin-1").lower(): value.decode("latin-1")
            for key, value in scope.get("headers", [])
        }

        content_length = headers.get("content-length")
        if content_length:
            try:
                if int(content_length) > limit:
                    response = error_response(status_code=413, mensaje=self.error_message)
                    await response(scope, receive, send)
                    return
            except ValueError:
                pass

        body_chunks = []
        total = 0
        more_body = True

        while more_body:
            message = await receive()
            if message["type"] != "http.request":
                body_chunks.append(message)
                continue

            chunk = message.get("body", b"")
            total += len(chunk)
            if total > limit:
                response = error_response(status_code=413, mensaje=self.error_message)
                await response(scope, receive, send)
                return

            body_chunks.append(message)
            more_body = bool(message.get("more_body", False))

        replay = _ReplayReceive(body_chunks)
        await self.app(scope, replay, send)


class _ReplayReceive:
    def __init__(self, messages):
        self._messages = list(messages)
        self._index = 0

    async def __call__(self):
        if self._index < len(self._messages):
            message = self._messages[self._index]
            self._index += 1
            return message
        return {"type": "http.request", "body": b"", "more_body": False}


def _build_app() -> FastAPI:
    app = FastAPI()
    app.add_middleware(
        RequestSizeLimitMiddleware,
        route_limits={
            ("POST", "/login"): 128,
            ("POST", "/registro"): 256,
            ("POST", "/password/solicitar"): 64,
            ("POST", "/password/confirmar"): 128,
        },
    )

    @app.post("/login")
    async def login(request: Request):
        return {"ok": True, "body": await request.json()}

    @app.post("/registro")
    async def registro(request: Request):
        return {"ok": True, "body": await request.json()}

    @app.post("/password/solicitar")
    async def solicitar(request: Request):
        return {"ok": True, "body": await request.json()}

    @app.post("/password/confirmar")
    async def confirmar(request: Request):
        return {"ok": True, "body": await request.json()}

    @app.post("/perfil/foto")
    async def foto(request: Request):
        return {"ok": True, "size": len(await request.body())}

    return app


class TestRequestSizeLimitMiddleware:
    def test_login_pequeno_pasa_y_body_llega_intacto(self):
        client = TestClient(_build_app())
        payload = {"identificador": "pepe", "password": "Pass1234"}

        response = client.post("/login", json=payload)

        assert response.status_code == 200
        assert response.json()["body"] == payload

    def test_login_grande_devuelve_413(self):
        client = TestClient(_build_app())
        payload = {"identificador": "pepe", "password": "x" * 500}

        response = client.post("/login", json=payload)

        assert response.status_code == 413
        assert response.json()["estatus"] == "error"
        assert "tamaño máximo" in response.json()["mensaje"]

    def test_registro_tiene_limite_distinto(self):
        client = TestClient(_build_app())
        payload = {"email": "pepe@example.com", "nombre_usuario": "pepe", "bio": "x" * 150}

        response = client.post("/registro", json=payload)

        assert response.status_code == 200

    def test_ruta_no_configurada_no_se_limita_con_este_middleware(self):
        client = TestClient(_build_app())
        response = client.post("/perfil/foto", content=b"x" * 5000, headers={"content-type": "application/octet-stream"})

        assert response.status_code == 200
        assert response.json()["size"] == 5000


@pytest.mark.asyncio
async def test_limitacion_streaming_sin_content_length():
    app = _build_app()

    messages = [
        {"type": "http.request", "body": b'{"identificador":"pe', "more_body": True},
        {"type": "http.request", "body": b'pe","password":"' + (b'x' * 200) + b'"}', "more_body": False},
    ]

    async def receive():
        if messages:
            return messages.pop(0)
        return {"type": "http.request", "body": b"", "more_body": False}

    sent = []

    async def send(message):
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

    assert start["status"] == 413
    assert b"tama" in body["body"] or b"m\xc3\xa1ximo" in body["body"]
