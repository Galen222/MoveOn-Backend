#
# Tests de integración para routers/users.py usando TestClient.
# Cubre: /registro, /perfil/informacion, /perfil/informacion/{nombre},
#        /perfil/foto, /perfil/actualizar, /perfil/borrar, /perfil/buscar, /ranking/obtener.
#
# Estrategia:
# - dependency_overrides para bypassear obtener_db, verificar_sesion_aplicacion
#   y obtener_usuario_actual.
# - monkeypatch en los servicios para controlar respuestas sin BD real.
# - Los tests de App Session usan el middleware real (sin bypass) para verificar
#   que el router rechaza requests sin token o con token inválido.

import io
from datetime import date, datetime, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.testclient import TestClient
from PIL import Image

import auth
from database import obtener_db
from exceptions import error_response, manejador_http_exception, manejador_validacion_personalizado
from routers.users import router as users_router
from services import file_service, user_service
from services.identity_rate_limit import IdentityRateLimitExceeded


# ─────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────

def _build_app() -> FastAPI:
    app = FastAPI()
    app.include_router(users_router)
    app.add_exception_handler(RequestValidationError, manejador_validacion_personalizado)

    async def http_exc_handler(req: Request, exc: Exception) -> JSONResponse:
        if isinstance(exc, HTTPException):
            return manejador_http_exception(req, exc)
        return JSONResponse(status_code=500, content={"estatus": "error", "mensaje": "Error interno"})

    app.add_exception_handler(HTTPException, http_exc_handler)

    @app.exception_handler(IdentityRateLimitExceeded)
    async def identity_rl_handler(request: Request, exc: IdentityRateLimitExceeded):
        return error_response(status_code=429, mensaje=exc.mensaje)

    return app


async def _fake_db():
    return None


def _app_con_overrides(usuario_actual_id: int = 1) -> FastAPI:
    app = _build_app()
    app.dependency_overrides[obtener_db] = _fake_db
    app.dependency_overrides[auth.verificar_sesion_aplicacion] = lambda: "ok"
    app.dependency_overrides[auth.obtener_usuario_actual] = lambda: usuario_actual_id
    return app


def _make_jpeg_bytes(width: int = 50, height: int = 50) -> bytes:
    img = Image.new("RGB", (width, height), color=(100, 150, 200))
    buf = io.BytesIO()
    img.save(buf, format="JPEG")
    return buf.getvalue()


def _usuario_fake(**kwargs) -> SimpleNamespace:
    defaults = dict(
        id=1,
        nombre_usuario="pepe",
        nombre_real="Pepe García",
        email="pepe@example.com",
        fecha_nacimiento=date(1990, 5, 15),
        genero="Hombre",
        altura=175,
        peso=70.0,
        provincia="Madrid",
        foto_perfil=None,
        foto_fecha_actualizacion=None,
        perfil_visible=True,
        total_metros=5000,
    )
    defaults.update(kwargs)
    return SimpleNamespace(**defaults)


def _payload_registro() -> dict:
    return {
        "nombre_usuario": "nuevousuario",
        "email": "nuevo@example.com",
        "password": "Password1",
        "fecha_nacimiento": "1995-06-20",
        "acepta_terminos": True,
        "fecha_aceptacion_terminos": "2024-01-01T00:00:00Z",
        "version_terminos": "1.0",
    }


# ─────────────────────────────────────────────
# POST /registro — app session
# ─────────────────────────────────────────────

class TestRegistroAppSession:
    def test_sin_app_session_devuelve_403(self):
        client = TestClient(_build_app())
        response = client.post("/registro", json=_payload_registro())
        assert response.status_code == 403
        assert response.headers.get("x-app-session-expired") == "1"


# ─────────────────────────────────────────────
# POST /registro — validación de esquema
# ─────────────────────────────────────────────

class TestRegistroValidacion:
    def test_body_vacio_devuelve_422(self):
        client = TestClient(_app_con_overrides())
        assert client.post("/registro", json={}).status_code == 422

    def test_sin_email_devuelve_422(self):
        payload = _payload_registro()
        del payload["email"]
        client = TestClient(_app_con_overrides())
        assert client.post("/registro", json=payload).status_code == 422

    def test_email_invalido_devuelve_422(self):
        payload = {**_payload_registro(), "email": "no-es-email"}
        client = TestClient(_app_con_overrides())
        assert client.post("/registro", json=payload).status_code == 422

    def test_password_debil_sin_mayuscula_devuelve_422(self):
        payload = {**_payload_registro(), "password": "password1"}
        client = TestClient(_app_con_overrides())
        assert client.post("/registro", json=payload).status_code == 422

    def test_password_debil_sin_numero_devuelve_422(self):
        payload = {**_payload_registro(), "password": "Password"}
        client = TestClient(_app_con_overrides())
        assert client.post("/registro", json=payload).status_code == 422

    def test_nombre_usuario_demasiado_corto_devuelve_422(self):
        payload = {**_payload_registro(), "nombre_usuario": "abc"}
        client = TestClient(_app_con_overrides())
        assert client.post("/registro", json=payload).status_code == 422

    def test_nombre_usuario_con_espacios_devuelve_422(self):
        payload = {**_payload_registro(), "nombre_usuario": "nombre usuario"}
        client = TestClient(_app_con_overrides())
        assert client.post("/registro", json=payload).status_code == 422

    def test_menor_de_edad_devuelve_422(self):
        payload = {**_payload_registro(), "fecha_nacimiento": "2015-01-01"}
        client = TestClient(_app_con_overrides())
        assert client.post("/registro", json=payload).status_code == 422

    def test_sin_acepta_terminos_devuelve_422(self):
        payload = {**_payload_registro(), "acepta_terminos": False}
        client = TestClient(_app_con_overrides())
        assert client.post("/registro", json=payload).status_code == 422


# ─────────────────────────────────────────────
# POST /registro — lógica de negocio
# ─────────────────────────────────────────────

class TestRegistroLogica:
    def test_registro_exitoso_devuelve_201_o_200(self, monkeypatch):
        app = _app_con_overrides()

        async def fake_registrar(db, datos):
            return {"estatus": "success", "mensaje": "Usuario registrado correctamente", "nombre_usuario": "nuevousuario"}

        monkeypatch.setattr(user_service, "registrar_nuevo_usuario", fake_registrar)
        client = TestClient(app)
        response = client.post("/registro", json=_payload_registro())

        assert response.status_code == 200
        body = response.json()
        assert body["estatus"] == "success"
        assert body["nombre_usuario"] == "nuevousuario"

    def test_usuario_duplicado_devuelve_400(self, monkeypatch):
        app = _app_con_overrides()

        async def fake_registrar(db, datos):
            raise HTTPException(status_code=400, detail="Error: El nombre de usuario ya está en uso")

        monkeypatch.setattr(user_service, "registrar_nuevo_usuario", fake_registrar)
        client = TestClient(app)
        response = client.post("/registro", json=_payload_registro())

        assert response.status_code == 400
        assert "nombre de usuario" in response.json()["mensaje"].lower()

    def test_email_duplicado_devuelve_400(self, monkeypatch):
        app = _app_con_overrides()

        async def fake_registrar(db, datos):
            raise HTTPException(status_code=400, detail="Error: El email ya está en uso")

        monkeypatch.setattr(user_service, "registrar_nuevo_usuario", fake_registrar)
        client = TestClient(app)
        response = client.post("/registro", json=_payload_registro())

        assert response.status_code == 400

    def test_registro_dispara_identity_rate_limit_429(self, monkeypatch):
        app = _app_con_overrides()
        monkeypatch.setattr(
            "routers.users.check_identity_limit",
            lambda scope, identity, limit: (_ for _ in ()).throw(IdentityRateLimitExceeded())
        )
        client = TestClient(app)
        response = client.post("/registro", json=_payload_registro())
        assert response.status_code == 429


# ─────────────────────────────────────────────
# GET /perfil/informacion
# ─────────────────────────────────────────────

class TestInformacionPerfil:
    def test_sin_token_acceso_devuelve_401(self):
        """Sin Bearer token JWT el endpoint devuelve 401 (no 403 — ese es de app_session)."""
        app = _build_app()
        app.dependency_overrides[obtener_db] = _fake_db
        app.dependency_overrides[auth.verificar_sesion_aplicacion] = lambda: "ok"
        client = TestClient(app)
        response = client.get("/perfil/informacion")
        assert response.status_code == 401

    def test_devuelve_campos_correctos(self, monkeypatch):
        app = _app_con_overrides()
        usuario = _usuario_fake(total_metros=3000)

        async def fake_obtener(db, usuario_actual_id, for_update=False):
            return usuario

        monkeypatch.setattr(user_service, "obtener_perfil", fake_obtener)
        monkeypatch.setattr(file_service, "construir_url_foto", lambda foto, req: None)

        client = TestClient(app)
        response = client.get("/perfil/informacion")

        assert response.status_code == 200
        body = response.json()
        assert body["nombre_usuario"] == "pepe"
        assert body["email"] == "pepe@example.com"
        assert body["perfil_visible"] is True
        assert "total_puntos" in body

    def test_total_puntos_calculado_correctamente(self, monkeypatch):
        """3000 metros = 3 puntos (1000m = 1 punto)."""
        app = _app_con_overrides()

        async def fake_obtener(db, usuario_actual_id, for_update=False):
            return _usuario_fake(total_metros=3000)

        monkeypatch.setattr(user_service, "obtener_perfil", fake_obtener)
        monkeypatch.setattr(file_service, "construir_url_foto", lambda foto, req: None)

        response = TestClient(app).get("/perfil/informacion")
        assert response.json()["total_puntos"] == 3

    def test_foto_pasa_por_construir_url(self, monkeypatch):
        """El router debe llamar a construir_url_foto y usar su resultado."""
        app = _app_con_overrides()

        async def fake_obtener(db, usuario_actual_id, for_update=False):
            return _usuario_fake(foto_perfil="foto.jpg")

        monkeypatch.setattr(user_service, "obtener_perfil", fake_obtener)
        monkeypatch.setattr(
            file_service, "construir_url_foto",
            lambda foto, req: "http://localhost/imagenes/foto.jpg"
        )

        response = TestClient(app).get("/perfil/informacion")
        assert response.json()["foto_perfil"] == "http://localhost/imagenes/foto.jpg"

    def test_usuario_no_encontrado_devuelve_404(self, monkeypatch):
        app = _app_con_overrides()

        async def fake_obtener(db, usuario_actual_id, for_update=False):
            raise HTTPException(status_code=404, detail="Error: Perfil de usuario no encontrado")

        monkeypatch.setattr(user_service, "obtener_perfil", fake_obtener)
        response = TestClient(app).get("/perfil/informacion")
        assert response.status_code == 404


# ─────────────────────────────────────────────
# GET /perfil/informacion/{nombre_usuario}
# ─────────────────────────────────────────────

class TestInformacionPerfilPublico:
    def test_perfil_publico_devuelve_campos_reducidos(self, monkeypatch):
        app = _app_con_overrides()
        usuario = _usuario_fake(total_metros=10000)

        async def fake_publico(db, nombre):
            return usuario

        monkeypatch.setattr(user_service, "obtener_perfil_publico", fake_publico)
        monkeypatch.setattr(file_service, "construir_url_foto", lambda foto, req: None)

        response = TestClient(app).get("/perfil/informacion/pepe")

        assert response.status_code == 200
        body = response.json()
        assert "nombre_usuario" in body
        assert "total_puntos" in body
        # No debe incluir datos sensibles
        assert "email" not in body
        assert "password" not in body
        assert "fecha_nacimiento" not in body

    def test_perfil_privado_devuelve_403(self, monkeypatch):
        app = _app_con_overrides()

        async def fake_publico(db, nombre):
            raise HTTPException(status_code=403, detail="Error: Este perfil es privado")

        monkeypatch.setattr(user_service, "obtener_perfil_publico", fake_publico)
        response = TestClient(app).get("/perfil/informacion/secreto")
        assert response.status_code == 403

    def test_usuario_inexistente_devuelve_404(self, monkeypatch):
        app = _app_con_overrides()

        async def fake_publico(db, nombre):
            raise HTTPException(status_code=404, detail="Error: Usuario no encontrado")

        monkeypatch.setattr(user_service, "obtener_perfil_publico", fake_publico)
        response = TestClient(app).get("/perfil/informacion/noexiste")
        assert response.status_code == 404

    def test_total_puntos_calculado_de_metros(self, monkeypatch):
        """10000 metros = 10 puntos."""
        app = _app_con_overrides()

        async def fake_publico(db, nombre):
            return _usuario_fake(total_metros=10000)

        monkeypatch.setattr(user_service, "obtener_perfil_publico", fake_publico)
        monkeypatch.setattr(file_service, "construir_url_foto", lambda foto, req: None)

        response = TestClient(app).get("/perfil/informacion/pepe")
        assert response.json()["total_puntos"] == 10


# ─────────────────────────────────────────────
# POST /perfil/foto
# ─────────────────────────────────────────────

class TestFotoPerfil:
    def _post_foto(self, client, jpeg_bytes=None):
        data = jpeg_bytes or _make_jpeg_bytes()
        return client.post(
            "/perfil/foto",
            files={"archivo": ("foto.jpg", data, "image/jpeg")},
        )

    def test_imagen_invalida_validar_seguridad_devuelve_400(self, monkeypatch):
        app = _app_con_overrides()

        def fake_validar(archivo):
            raise HTTPException(status_code=400, detail="Error: Solo imágenes JPG o PNG")

        monkeypatch.setattr(file_service, "validar_seguridad", fake_validar)
        response = self._post_foto(TestClient(app), b"basura")
        assert response.status_code == 400

    def test_usuario_no_encontrado_devuelve_404(self, monkeypatch):
        app = _app_con_overrides()

        monkeypatch.setattr(file_service, "validar_seguridad", lambda a: _make_jpeg_bytes())
        monkeypatch.setattr(file_service, "procesar_subida", lambda a, u, raw, f=None: "temp.jpg")

        async def fake_obtener(db, usuario_actual_id, for_update=False):
            raise HTTPException(status_code=404, detail="Error: Perfil no encontrado")

        monkeypatch.setattr(user_service, "obtener_perfil", fake_obtener)
        response = self._post_foto(TestClient(app))
        assert response.status_code == 404

    def test_subida_exitosa_devuelve_200(self, monkeypatch):
        app = _app_con_overrides()

        monkeypatch.setattr(file_service, "validar_seguridad", lambda a: _make_jpeg_bytes())
        monkeypatch.setattr(file_service, "procesar_subida", lambda a, u, raw, f=None: "nueva_foto.jpg")

        db_mock = MagicMock()
        db_mock.commit = MagicMock(return_value=None)

        async def fake_db_gen():
            return db_mock

        async def fake_obtener(db, usuario_actual_id, for_update=False):
            return _usuario_fake(foto_perfil="foto_vieja.jpg")

        async def fake_commit(db_mock):
            pass

        monkeypatch.setattr(user_service, "obtener_perfil", fake_obtener)

        # Override db to return an async-compatible mock
        async def _fake_db_commit():
            mock = MagicMock()
            mock.commit = _async_noop
            mock.rollback = _async_noop
            return mock

        async def _async_noop(*a, **kw):
            pass

        app.dependency_overrides[obtener_db] = _fake_db_commit
        response = self._post_foto(TestClient(app))
        assert response.status_code == 200
        assert response.json()["estatus"] == "success"

    def test_sin_archivo_devuelve_422(self):
        app = _app_con_overrides()
        response = TestClient(app).post("/perfil/foto")
        assert response.status_code == 422


# ─────────────────────────────────────────────
# PATCH /perfil/actualizar
# ─────────────────────────────────────────────

class TestActualizarPerfil:
    def test_body_vacio_actualiza_nada_y_devuelve_200(self, monkeypatch):
        """PATCH con body vacío es válido: no toca ningún campo."""
        app = _app_con_overrides()

        async def fake_obtener(db, usuario_actual_id, for_update=False):
            return _usuario_fake()

        async def fake_actualizar(db, usuario, datos):
            return {"estatus": "success", "mensaje": "Perfil de usuario actualizado correctamente"}

        monkeypatch.setattr(user_service, "obtener_perfil", fake_obtener)
        monkeypatch.setattr(user_service, "actualizar_perfil_usuario", fake_actualizar)

        response = TestClient(app).patch("/perfil/actualizar", json={})
        assert response.status_code == 200

    def test_email_invalido_devuelve_422(self):
        app = _app_con_overrides()
        response = TestClient(app).patch("/perfil/actualizar", json={"email": "no-es-email"})
        assert response.status_code == 422

    def test_password_debil_devuelve_422(self):
        app = _app_con_overrides()
        response = TestClient(app).patch("/perfil/actualizar", json={"password": "debil"})
        assert response.status_code == 422

    def test_actualizacion_exitosa_devuelve_200(self, monkeypatch):
        app = _app_con_overrides()

        async def fake_obtener(db, usuario_actual_id, for_update=False):
            return _usuario_fake()

        async def fake_actualizar(db, usuario, datos):
            return {"estatus": "success", "mensaje": "Perfil de usuario actualizado correctamente"}

        monkeypatch.setattr(user_service, "obtener_perfil", fake_obtener)
        monkeypatch.setattr(user_service, "actualizar_perfil_usuario", fake_actualizar)

        response = TestClient(app).patch("/perfil/actualizar", json={"provincia": "Madrid"})
        assert response.status_code == 200
        assert response.json()["estatus"] == "success"

    def test_email_duplicado_devuelve_400(self, monkeypatch):
        app = _app_con_overrides()

        async def fake_obtener(db, usuario_actual_id, for_update=False):
            return _usuario_fake()

        async def fake_actualizar(db, usuario, datos):
            raise HTTPException(status_code=400, detail="Error: El email ya está en uso")

        monkeypatch.setattr(user_service, "obtener_perfil", fake_obtener)
        monkeypatch.setattr(user_service, "actualizar_perfil_usuario", fake_actualizar)

        response = TestClient(app).patch(
            "/perfil/actualizar", json={"email": "otro@example.com"}
        )
        assert response.status_code == 400

    def test_usuario_no_encontrado_devuelve_404(self, monkeypatch):
        app = _app_con_overrides()

        async def fake_obtener(db, usuario_actual_id, for_update=False):
            raise HTTPException(status_code=404, detail="Error: Perfil no encontrado")

        monkeypatch.setattr(user_service, "obtener_perfil", fake_obtener)
        response = TestClient(app).patch("/perfil/actualizar", json={})
        assert response.status_code == 404


# ─────────────────────────────────────────────
# DELETE /perfil/borrar
# ─────────────────────────────────────────────

class TestBorrarPerfil:
    def test_borrar_exitoso_devuelve_200(self, monkeypatch):
        app = _app_con_overrides()

        async def fake_obtener(db, usuario_actual_id, for_update=False):
            return _usuario_fake()

        async def fake_eliminar(db, usuario):
            return {"estatus": "success", "mensaje": "Cuenta eliminada correctamente"}

        monkeypatch.setattr(user_service, "obtener_perfil", fake_obtener)
        monkeypatch.setattr(user_service, "eliminar_cuenta", fake_eliminar)
        monkeypatch.setattr(file_service, "borrar_foto", lambda foto, usuario: None)

        response = TestClient(app).delete("/perfil/borrar")
        assert response.status_code == 200
        assert response.json()["estatus"] == "success"

    def test_usuario_no_encontrado_devuelve_404(self, monkeypatch):
        app = _app_con_overrides()

        async def fake_obtener(db, usuario_actual_id, for_update=False):
            raise HTTPException(status_code=404, detail="Error: Perfil no encontrado")

        monkeypatch.setattr(user_service, "obtener_perfil", fake_obtener)
        response = TestClient(app).delete("/perfil/borrar")
        assert response.status_code == 404

    def test_foto_se_pasa_a_background_task(self, monkeypatch):
        """Verifica que el router guarda la foto antes del delete y la pasa al background."""
        app = _app_con_overrides()
        fotos_borradas = []

        async def fake_obtener(db, usuario_actual_id, for_update=False):
            return _usuario_fake(foto_perfil="foto_a_borrar.jpg")

        async def fake_eliminar(db, usuario):
            return {"estatus": "success", "mensaje": "Cuenta eliminada correctamente"}

        def fake_borrar(foto, usuario):
            fotos_borradas.append(foto)

        monkeypatch.setattr(user_service, "obtener_perfil", fake_obtener)
        monkeypatch.setattr(user_service, "eliminar_cuenta", fake_eliminar)
        monkeypatch.setattr(file_service, "borrar_foto", fake_borrar)

        TestClient(app).delete("/perfil/borrar")
        assert "foto_a_borrar.jpg" in fotos_borradas



# ─────────────────────────────────────────────
# GET /perfil/buscar
# ─────────────────────────────────────────────

class TestBuscarPerfil:
    def test_q_demasiado_corto_devuelve_422(self):
        client = TestClient(_app_con_overrides())
        assert client.get("/perfil/buscar", params={"q": "ab"}).status_code == 422

    def test_q_demasiado_largo_devuelve_422(self):
        client = TestClient(_app_con_overrides())
        assert client.get("/perfil/buscar", params={"q": "a" * 51}).status_code == 422

    def test_sin_q_devuelve_422(self):
        client = TestClient(_app_con_overrides())
        assert client.get("/perfil/buscar").status_code == 422

    def test_sin_app_session_devuelve_403_con_cabecera(self):
        app = _build_app()
        client = TestClient(app)
        response = client.get("/perfil/buscar", params={"q": "pep"})
        assert response.status_code == 403
        assert response.headers["x-app-session-expired"] == "1"
        assert "token de sesión" in response.json()["mensaje"].lower()

    def test_app_session_invalido_devuelve_403_con_cabecera(self):
        app = _build_app()
        client = TestClient(app)
        response = client.get(
            "/perfil/buscar",
            params={"q": "pep"},
            headers={"X-App-Session": "token-falso"},
        )
        assert response.status_code == 403
        assert response.headers["x-app-session-expired"] == "1"

    def test_q_valida_devuelve_resultados_paginados(self, monkeypatch):
        from types import SimpleNamespace
        app = _app_con_overrides()

        async def fake_buscar(db, termino, usuario_actual_id, skip, limit):
            return {
                "items": [
                    SimpleNamespace(
                        nombre_usuario="pepe",
                        foto_perfil=None,
                        foto_fecha_actualizacion=None,
                    )
                ],
                "total": 1,
                "skip": skip,
                "limit": limit,
                "has_more": False,
            }

        monkeypatch.setattr(user_service, "buscar_usuario", fake_buscar)
        monkeypatch.setattr(file_service, "construir_url_foto", lambda foto, req: foto)

        response = TestClient(app).get("/perfil/buscar", params={"q": "pep"})
        assert response.status_code == 200
        assert response.json() == {
            "items": [
                {
                    "nombre_usuario": "pepe",
                    "foto_perfil": None,
                    "foto_version": 0,
                }
            ],
            "total": 1,
            "skip": 0,
            "limit": 20,
            "has_more": False,
        }

    def test_excluye_usuario_actual_pasandolo_al_servicio(self, monkeypatch):
        app = _app_con_overrides(usuario_actual_id=99)
        llamada = {}

        async def fake_buscar(db, termino, usuario_actual_id, skip, limit):
            llamada["termino"] = termino
            llamada["usuario_actual_id"] = usuario_actual_id
            llamada["skip"] = skip
            llamada["limit"] = limit
            return {
                "items": [],
                "total": 0,
                "skip": skip,
                "limit": limit,
                "has_more": False,
            }

        monkeypatch.setattr(user_service, "buscar_usuario", fake_buscar)

        TestClient(app).get("/perfil/buscar", params={"q": "miu"})
        assert llamada["termino"] == "miu"
        assert llamada["usuario_actual_id"] == 99
        assert llamada["skip"] == 0
        assert llamada["limit"] == 20

    def test_lista_vacia_devuelve_200(self, monkeypatch):
        app = _app_con_overrides()

        async def fake_buscar(db, termino, usuario_actual_id, skip, limit):
            return {
                "items": [],
                "total": 0,
                "skip": skip,
                "limit": limit,
                "has_more": False,
            }

        monkeypatch.setattr(user_service, "buscar_usuario", fake_buscar)
        response = TestClient(app).get("/perfil/buscar", params={"q": "xyz"})
        assert response.status_code == 200
        assert response.json() == {
            "items": [],
            "total": 0,
            "skip": 0,
            "limit": 20,
            "has_more": False,
        }

    def test_foto_pasa_por_construir_url(self, monkeypatch):
        from types import SimpleNamespace
        app = _app_con_overrides()
        fotos_procesadas = []

        async def fake_buscar(db, termino, usuario_actual_id, skip, limit):
            return {
                "items": [
                    SimpleNamespace(
                        nombre_usuario="ana",
                        foto_perfil="ana.jpg",
                        foto_fecha_actualizacion=None,
                    )
                ],
                "total": 1,
                "skip": skip,
                "limit": limit,
                "has_more": False,
            }

        def fake_construir(foto, req):
            fotos_procesadas.append(foto)
            return f"http://localhost/imagenes/{foto}"

        monkeypatch.setattr(user_service, "buscar_usuario", fake_buscar)
        monkeypatch.setattr(file_service, "construir_url_foto", fake_construir)

        response = TestClient(app).get("/perfil/buscar", params={"q": "ana"})
        assert response.status_code == 200
        assert "ana.jpg" in fotos_procesadas
        assert response.json()["items"][0]["foto_version"] == 0


# ─────────────────────────────────────────────
# GET /ranking/obtener
# ─────────────────────────────────────────────

class TestRankingObtener:
    def _ranking_fake(self):
        return [
            {"nombre_usuario": "pepe", "foto_perfil": None, "total_puntos": 10},
            {"nombre_usuario": "ana", "foto_perfil": "https://cdn.example.com/ana.jpg", "total_puntos": 8},
        ]

    def test_ranking_sin_filtro_devuelve_lista(self, monkeypatch):
        app = _app_con_overrides()

        async def fake_ranking(db, provincia=None):
            return self._ranking_fake()

        monkeypatch.setattr(user_service, "obtener_ranking", fake_ranking)
        monkeypatch.setattr(file_service, "construir_url_foto", lambda foto, req: foto)

        response = TestClient(app).get("/ranking/obtener")
        assert response.status_code == 200
        assert isinstance(response.json(), list)
        assert len(response.json()) == 2

    def test_ranking_tiene_campos_requeridos(self, monkeypatch):
        app = _app_con_overrides()

        async def fake_ranking(db, provincia=None):
            return self._ranking_fake()

        monkeypatch.setattr(user_service, "obtener_ranking", fake_ranking)
        monkeypatch.setattr(file_service, "construir_url_foto", lambda foto, req: foto)

        body = TestClient(app).get("/ranking/obtener").json()
        for item in body:
            assert "nombre_usuario" in item
            assert "foto_perfil" in item
            assert "total_puntos" in item

    def test_ranking_con_provincia_valida_pasa_filtro(self, monkeypatch):
        app = _app_con_overrides()
        provincia_recibida = {}

        async def fake_ranking(db, provincia=None):
            provincia_recibida["valor"] = provincia
            return []

        monkeypatch.setattr(user_service, "obtener_ranking", fake_ranking)

        TestClient(app).get("/ranking/obtener", params={"provincia": "Madrid"})
        assert provincia_recibida.get("valor") == "Madrid"

    def test_ranking_provincia_invalida_devuelve_422(self):
        app = _app_con_overrides()
        response = TestClient(app).get("/ranking/obtener", params={"provincia": "Narnia"})
        assert response.status_code == 422

    def test_foto_ranking_pasa_por_construir_url(self, monkeypatch):
        """El router debe procesar cada foto a través de construir_url_foto."""
        app = _app_con_overrides()
        fotos_procesadas = []

        async def fake_ranking(db, provincia=None):
            return [{"nombre_usuario": "pepe", "foto_perfil": "foto.jpg", "total_puntos": 5}]

        def fake_construir(foto, req):
            fotos_procesadas.append(foto)
            return f"http://localhost/imagenes/{foto}"

        monkeypatch.setattr(user_service, "obtener_ranking", fake_ranking)
        monkeypatch.setattr(file_service, "construir_url_foto", fake_construir)

        TestClient(app).get("/ranking/obtener")
        assert "foto.jpg" in fotos_procesadas

    def test_ranking_vacio_devuelve_lista_vacia(self, monkeypatch):
        app = _app_con_overrides()

        async def fake_ranking(db, provincia=None):
            return []

        monkeypatch.setattr(user_service, "obtener_ranking", fake_ranking)
        response = TestClient(app).get("/ranking/obtener")
        assert response.json() == []


