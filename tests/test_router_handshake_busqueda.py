# tests/test_router_handshake_busqueda.py

from types import SimpleNamespace

from fastapi import FastAPI
from fastapi.testclient import TestClient

import auth
from config import settings
from database import obtener_db
from routers.access import router as access_router
from routers.users import router as users_router
from services import file_service, user_service


async def _fake_db():
    return None


def _build_app() -> FastAPI:
    app = FastAPI()
    app.include_router(access_router)
    app.include_router(users_router)
    return app


class TestHandshake:
    def test_handshake_sin_x_app_id_devuelve_403(self):
        client = TestClient(_build_app())

        response = client.get("/handshake")

        assert response.status_code == 403
        assert "MoveOn" in response.json()["detail"]

    def test_handshake_x_app_id_incorrecto_devuelve_403(self):
        client = TestClient(_build_app())

        response = client.get("/handshake", headers={"X-App-Id": "incorrecto"})

        assert response.status_code == 403
        assert "MoveOn" in response.json()["detail"]

    def test_handshake_x_app_id_correcto_devuelve_token(self):
        client = TestClient(_build_app())

        response = client.get("/handshake", headers={"X-App-Id": settings.APP_ID})

        assert response.status_code == 200
        body = response.json()
        assert "app_session_token" in body
        assert isinstance(body["app_session_token"], str)
        assert body["app_session_token"]


class TestBuscarPerfil:
    def test_perfil_buscar_q_demasiado_corto_devuelve_422(self):
        app = _build_app()
        app.dependency_overrides[obtener_db] = _fake_db
        app.dependency_overrides[auth.verificar_sesion_aplicacion] = lambda: "ok"
        app.dependency_overrides[auth.obtener_usuario_actual] = lambda: "tester"

        client = TestClient(app)
        response = client.get("/perfil/buscar", params={"q": "ab"})

        assert response.status_code == 422

    def test_perfil_buscar_q_demasiado_largo_devuelve_422(self):
        app = _build_app()
        app.dependency_overrides[obtener_db] = _fake_db
        app.dependency_overrides[auth.verificar_sesion_aplicacion] = lambda: "ok"
        app.dependency_overrides[auth.obtener_usuario_actual] = lambda: "tester"

        client = TestClient(app)
        response = client.get("/perfil/buscar", params={"q": "a" * 51})

        assert response.status_code == 422

    def test_perfil_buscar_q_valida_devuelve_resultados(self, monkeypatch):
        app = _build_app()
        app.dependency_overrides[obtener_db] = _fake_db
        app.dependency_overrides[auth.verificar_sesion_aplicacion] = lambda: "ok"
        app.dependency_overrides[auth.obtener_usuario_actual] = lambda: "tester"

        async def fake_buscar_usuario(db, termino, usuario_actual):
            assert db is None
            assert termino == "pep"
            assert usuario_actual == "tester"
            return [
                SimpleNamespace(
                    nombre_usuario="pepe",
                    foto_perfil=None,
                )
            ]

        monkeypatch.setattr(user_service, "buscar_usuario", fake_buscar_usuario)
        monkeypatch.setattr(
            file_service,
            "construir_url_foto",
            lambda foto_perfil, request: foto_perfil,
        )

        client = TestClient(app)
        response = client.get("/perfil/buscar", params={"q": "pep"})

        assert response.status_code == 200
        assert response.json() == [
            {
                "nombre_usuario": "pepe",
                "foto_perfil": None,
            }
        ]

    def test_perfil_buscar_excluye_usuario_actual_pasandolo_al_servicio(self, monkeypatch):
        app = _build_app()
        app.dependency_overrides[obtener_db] = _fake_db
        app.dependency_overrides[auth.verificar_sesion_aplicacion] = lambda: "ok"
        app.dependency_overrides[auth.obtener_usuario_actual] = lambda: "mi_usuario"

        llamada = {}

        async def fake_buscar_usuario(db, termino, usuario_actual):
            llamada["db"] = db
            llamada["termino"] = termino
            llamada["usuario_actual"] = usuario_actual
            return []

        monkeypatch.setattr(user_service, "buscar_usuario", fake_buscar_usuario)

        client = TestClient(app)
        response = client.get("/perfil/buscar", params={"q": "miu"})

        assert response.status_code == 200
        assert response.json() == []
        assert llamada == {
            "db": None,
            "termino": "miu",
            "usuario_actual": "mi_usuario",
        }
            
    def test_ruta_protegida_sin_x_app_session_devuelve_403_y_cabecera(self):
        app = _build_app()
        client = TestClient(app)

        response = client.get("/perfil/buscar", params={"q": "pep"})

        assert response.status_code == 403
        assert response.headers["x-app-session-expired"] == "1"
        assert "token de sesión" in response.json()["detail"].lower()


    def test_ruta_protegida_con_x_app_session_invalido_devuelve_403_y_cabecera(self):
        app = _build_app()
        client = TestClient(app)

        response = client.get(
            "/perfil/buscar",
            params={"q": "pep"},
            headers={"X-App-Session": "token-falso"},
    )

        assert response.status_code == 403
        assert response.headers["x-app-session-expired"] == "1"
        assert "inválido" in response.json()["detail"].lower() or "expirado" in response.json()["detail"].lower()   
            
            
            
        