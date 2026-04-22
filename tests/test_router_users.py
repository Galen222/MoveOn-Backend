# tests/test_router_users.py

"""Ejercita el router de usuarios en registro, perfil, foto, búsqueda y ranking.

Las pruebas protegen tanto la validación HTTP como la integración ligera con
los servicios que sostienen cada endpoint.
"""

# Pruebas de integración para routers/users.py usando TestClient.
# Cubre: /registro, /perfil/informacion, /perfil/informacion/{nombre},
# /perfil/foto, /perfil/actualizar, /perfil/borrar, /perfil/buscar, /ranking/obtener.

# Estrategia:
# - dependency_overrides para omitir de forma controlada obtener_db y verificar_sesion_aplicacion
# y obtener_usuario_actual.
# - monkeypatch en los servicios para controlar respuestas sin BD real.
# - Las pruebas de sesión de aplicación usan el middleware real (sin atajos) para verificar
# que el router rechaza peticiones sin token o con token inválido.

import io
from datetime import date
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.testclient import TestClient
from PIL import Image

import auth
from database import obtener_db
from exceptions import (
    error_response,
    manejador_http_exception,
    manejador_validacion_personalizado,
)
from routers.users import router as users_router
from services import file_service, user_service
from services.identity_rate_limit import IdentityRateLimitExceeded

# ─────────────────────────────────────────────
# Ayudantes
# ─────────────────────────────────────────────


def _build_app() -> FastAPI:
    """Construye la aplicación de prueba."""
    # Crear la aplicación de prueba y registrar sus manejadores.
    app = FastAPI()
    app.include_router(users_router)
    app.add_exception_handler(
        RequestValidationError, manejador_validacion_personalizado
    )

    async def http_exc_handler(req: Request, exc: Exception) -> JSONResponse:
        """Gestiona el manejador HTTP de excepciones."""
        if isinstance(exc, HTTPException):
            return manejador_http_exception(req, exc)
        return JSONResponse(
            status_code=500, content={"estatus": "error", "mensaje": "Error interno"}
        )

    app.add_exception_handler(HTTPException, http_exc_handler)

    @app.exception_handler(IdentityRateLimitExceeded)
    async def identity_rl_handler(request: Request, exc: IdentityRateLimitExceeded):
        """Gestiona el manejador del límite de tasa por identidad."""
        return error_response(status_code=429, mensaje=exc.mensaje)

    return app


async def _fake_db():
    """Crea un simulacro de base de datos."""
    return None


def _app_con_overrides(usuario_actual_id: int = 1) -> FastAPI:
    """Crea la aplicación con dependencias sobrescritas."""
    app = _build_app()
    app.dependency_overrides[obtener_db] = _fake_db
    app.dependency_overrides[auth.verificar_sesion_aplicacion] = lambda: "ok"
    app.dependency_overrides[auth.obtener_usuario_actual] = lambda: usuario_actual_id
    return app


def _make_jpeg_bytes(width: int = 50, height: int = 50) -> bytes:
    """Construye bytes JPEG."""
    img = Image.new("RGB", (width, height), color=(100, 150, 200))
    buf = io.BytesIO()
    img.save(buf, format="JPEG")
    return buf.getvalue()


def _usuario_fake(**kwargs) -> SimpleNamespace:
    """Crea un usuario simulado."""
    # Preparar un usuario simulado con valores por defecto.
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
        total_calorias=0,
        objetivo_semanal_metros=50000,
        objetivo_mensual_metros=150000,
    )
    defaults.update(kwargs)
    return SimpleNamespace(**defaults)


def _payload_registro() -> dict:
    """Gestiona payload registro."""
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
    """Agrupa pruebas relacionadas con registro app session."""

    def test_sin_app_session_devuelve_403(self):
        """Verifica que sin app session devuelve 403."""
        client = TestClient(_build_app())
        response = client.post("/registro", json=_payload_registro())
        assert response.status_code == 403
        assert response.headers.get("x-app-session-expired") == "1"


# ─────────────────────────────────────────────
# POST /registro — validación de esquema
# ─────────────────────────────────────────────


class TestRegistroValidacion:
    """Agrupa pruebas relacionadas con registro validacion."""

    def test_body_vacio_devuelve_422(self):
        """Verifica que body vacio devuelve 422."""
        client = TestClient(_app_con_overrides())
        assert client.post("/registro", json={}).status_code == 422

    def test_sin_email_devuelve_422(self):
        """Verifica que sin correo electrónico devuelve 422."""
        payload = _payload_registro()
        del payload["email"]
        client = TestClient(_app_con_overrides())
        assert client.post("/registro", json=payload).status_code == 422

    def test_email_invalido_devuelve_422(self):
        """Verifica que correo electrónico invalido devuelve 422."""
        payload = {**_payload_registro(), "email": "no-es-email"}
        client = TestClient(_app_con_overrides())
        assert client.post("/registro", json=payload).status_code == 422

    def test_password_debil_sin_mayuscula_devuelve_422(self):
        """Verifica que password debil sin mayuscula devuelve 422."""
        payload = {**_payload_registro(), "password": "password1"}
        client = TestClient(_app_con_overrides())
        assert client.post("/registro", json=payload).status_code == 422

    def test_password_debil_sin_numero_devuelve_422(self):
        """Verifica que password debil sin numero devuelve 422."""
        payload = {**_payload_registro(), "password": "Password"}
        client = TestClient(_app_con_overrides())
        assert client.post("/registro", json=payload).status_code == 422

    def test_nombre_usuario_demasiado_corto_devuelve_422(self):
        """Verifica que nombre usuario demasiado corto devuelve 422."""
        payload = {**_payload_registro(), "nombre_usuario": "abc"}
        client = TestClient(_app_con_overrides())
        assert client.post("/registro", json=payload).status_code == 422

    def test_nombre_usuario_con_espacios_devuelve_422(self):
        """Verifica que nombre usuario con espacios devuelve 422."""
        payload = {**_payload_registro(), "nombre_usuario": "nombre usuario"}
        client = TestClient(_app_con_overrides())
        assert client.post("/registro", json=payload).status_code == 422

    def test_menor_de_edad_devuelve_422(self):
        """Verifica que menor de edad devuelve 422."""
        payload = {**_payload_registro(), "fecha_nacimiento": "2015-01-01"}
        client = TestClient(_app_con_overrides())
        assert client.post("/registro", json=payload).status_code == 422

    def test_sin_acepta_terminos_devuelve_422(self):
        """Verifica que sin acepta terminos devuelve 422."""
        payload = {**_payload_registro(), "acepta_terminos": False}
        client = TestClient(_app_con_overrides())
        assert client.post("/registro", json=payload).status_code == 422


# ─────────────────────────────────────────────
# POST /registro — lógica de negocio
# ─────────────────────────────────────────────


class TestRegistroLogica:
    """Agrupa pruebas relacionadas con registro logica."""

    def test_registro_exitoso_devuelve_201_o_200(self, monkeypatch):
        """Verifica que registro exitoso devuelve 201 o 200."""
        # Verifica que registro exitoso devuelve 201 o 200.
        app = _app_con_overrides()

        async def fake_registrar(db, datos):
            """Crea un simulacro de registrar."""
            return {
                "estatus": "success",
                "mensaje": "Usuario registrado correctamente",
                "nombre_usuario": "nuevousuario",
            }

        monkeypatch.setattr(user_service, "registrar_nuevo_usuario", fake_registrar)
        client = TestClient(app)
        response = client.post("/registro", json=_payload_registro())

        assert response.status_code == 200
        body = response.json()
        assert body["estatus"] == "success"
        assert body["nombre_usuario"] == "nuevousuario"

    def test_usuario_duplicado_devuelve_400(self, monkeypatch):
        """Verifica que usuario duplicado devuelve 400."""
        # Verifica que usuario duplicado devuelve 400.
        app = _app_con_overrides()

        async def fake_registrar(db, datos):
            """Crea un simulacro de registrar."""
            raise HTTPException(
                status_code=400, detail="Error: El nombre de usuario ya está en uso"
            )

        monkeypatch.setattr(user_service, "registrar_nuevo_usuario", fake_registrar)
        client = TestClient(app)
        response = client.post("/registro", json=_payload_registro())

        assert response.status_code == 400
        assert "nombre de usuario" in response.json()["mensaje"].lower()

    def test_email_duplicado_devuelve_400(self, monkeypatch):
        """Verifica que correo electrónico duplicado devuelve 400."""
        app = _app_con_overrides()

        async def fake_registrar(db, datos):
            """Crea un simulacro de registrar."""
            raise HTTPException(
                status_code=400, detail="Error: El email ya está en uso"
            )

        monkeypatch.setattr(user_service, "registrar_nuevo_usuario", fake_registrar)
        client = TestClient(app)
        response = client.post("/registro", json=_payload_registro())

        assert response.status_code == 400

    def test_registro_dispara_identity_rate_limit_429(self, monkeypatch):
        """Verifica que registro dispara identidad rate limit 429."""
        app = _app_con_overrides()
        monkeypatch.setattr(
            "routers.users.check_identity_limit",
            lambda scope, identity, limit: (_ for _ in ()).throw(
                IdentityRateLimitExceeded()
            ),
        )
        client = TestClient(app)
        response = client.post("/registro", json=_payload_registro())
        assert response.status_code == 429


# ─────────────────────────────────────────────
# GET /perfil/informacion
# ─────────────────────────────────────────────


class TestInformacionPerfil:
    """Agrupa pruebas relacionadas con informacion perfil."""

    def test_sin_token_acceso_devuelve_401(self):
        """Sin Bearer token JWT el endpoint devuelve 401 (no 403 — ese es de app_session)."""
        app = _build_app()
        app.dependency_overrides[obtener_db] = _fake_db
        app.dependency_overrides[auth.verificar_sesion_aplicacion] = lambda: "ok"
        client = TestClient(app)
        response = client.get("/perfil/informacion")
        assert response.status_code == 401

    def test_devuelve_campos_correctos(self, monkeypatch):
        """Verifica que devuelve campos correctos."""
        # Verifica que devuelve campos correctos.
        app = _app_con_overrides()
        usuario = _usuario_fake(total_metros=3000)

        async def fake_obtener(db, usuario_actual_id, for_update=False):
            """Crea un simulacro de obtener."""
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
            """Crea un simulacro de obtener."""
            return _usuario_fake(total_metros=3000)

        monkeypatch.setattr(user_service, "obtener_perfil", fake_obtener)
        monkeypatch.setattr(file_service, "construir_url_foto", lambda foto, req: None)

        response = TestClient(app).get("/perfil/informacion")
        assert response.json()["total_puntos"] == 3

    def test_foto_pasa_por_construir_url(self, monkeypatch):
        """El router debe llamar a construir_url_foto y usar su resultado."""
        # Verifica que foto pasa por construir URL.
        app = _app_con_overrides()

        async def fake_obtener(db, usuario_actual_id, for_update=False):
            """Crea un simulacro de obtener."""
            return _usuario_fake(foto_perfil="foto.jpg")

        monkeypatch.setattr(user_service, "obtener_perfil", fake_obtener)
        monkeypatch.setattr(
            file_service,
            "construir_url_foto",
            lambda foto, req: "http://localhost/imagenes/foto.jpg",
        )

        response = TestClient(app).get("/perfil/informacion")
        assert response.json()["foto_perfil"] == "http://localhost/imagenes/foto.jpg"

    def test_usuario_no_encontrado_devuelve_404(self, monkeypatch):
        """Verifica que usuario no encontrado devuelve 404."""
        app = _app_con_overrides()

        async def fake_obtener(db, usuario_actual_id, for_update=False):
            """Crea un simulacro de obtener."""
            raise HTTPException(
                status_code=404, detail="Error: Perfil de usuario no encontrado"
            )

        monkeypatch.setattr(user_service, "obtener_perfil", fake_obtener)
        response = TestClient(app).get("/perfil/informacion")
        assert response.status_code == 404


# ─────────────────────────────────────────────
# GET /perfil/informacion/{nombre_usuario}
# ─────────────────────────────────────────────


class TestInformacionPerfilPublico:
    """Agrupa pruebas relacionadas con informacion perfil publico."""

    def test_perfil_publico_devuelve_campos_reducidos(self, monkeypatch):
        """Verifica que perfil publico devuelve campos reducidos."""
        app = _app_con_overrides()
        usuario = _usuario_fake(total_metros=10000)

        async def fake_publico(db, nombre):
            """Crea un simulacro de publico."""
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
        """Verifica que perfil privado devuelve 403."""
        app = _app_con_overrides()

        async def fake_publico(db, nombre):
            """Crea un simulacro de publico."""
            raise HTTPException(status_code=403, detail="Error: Este perfil es privado")

        monkeypatch.setattr(user_service, "obtener_perfil_publico", fake_publico)
        response = TestClient(app).get("/perfil/informacion/secreto")
        assert response.status_code == 403

    def test_usuario_inexistente_devuelve_404(self, monkeypatch):
        """Verifica que usuario inexistente devuelve 404."""
        app = _app_con_overrides()

        async def fake_publico(db, nombre):
            """Crea un simulacro de publico."""
            raise HTTPException(status_code=404, detail="Error: Usuario no encontrado")

        monkeypatch.setattr(user_service, "obtener_perfil_publico", fake_publico)
        response = TestClient(app).get("/perfil/informacion/noexiste")
        assert response.status_code == 404

    def test_total_puntos_calculado_de_metros(self, monkeypatch):
        """10000 metros = 10 puntos."""
        app = _app_con_overrides()

        async def fake_publico(db, nombre):
            """Crea un simulacro de publico."""
            return _usuario_fake(total_metros=10000)

        monkeypatch.setattr(user_service, "obtener_perfil_publico", fake_publico)
        monkeypatch.setattr(file_service, "construir_url_foto", lambda foto, req: None)

        response = TestClient(app).get("/perfil/informacion/pepe")
        assert response.json()["total_puntos"] == 10


# ─────────────────────────────────────────────
# POST /perfil/foto
# ─────────────────────────────────────────────


class TestFotoPerfil:
    """Agrupa pruebas relacionadas con foto perfil."""

    def _post_foto(self, client, jpeg_bytes=None):
        """Gestiona post foto."""
        data = jpeg_bytes or _make_jpeg_bytes()
        return client.post(
            "/perfil/foto",
            files={"archivo": ("foto.jpg", data, "image/jpeg")},
        )

    def test_imagen_invalida_validar_seguridad_devuelve_400(self, monkeypatch):
        """Verifica que imagen invalida validar seguridad devuelve 400."""
        app = _app_con_overrides()

        def fake_validar(archivo):
            """Crea un simulacro de validar."""
            raise HTTPException(
                status_code=400, detail="Error: Solo imágenes JPG o PNG"
            )

        db_mock = AsyncMock()
        db_mock.commit = AsyncMock()
        db_mock.rollback = AsyncMock()

        async def _fake_db_error_validacion():
            """Crea un simulacro de base de datos para errores de validación."""
            return db_mock

        app.dependency_overrides[obtener_db] = _fake_db_error_validacion
        monkeypatch.setattr(file_service, "validar_seguridad", fake_validar)
        response = self._post_foto(TestClient(app), b"basura")
        assert response.status_code == 400

    def test_usuario_no_encontrado_devuelve_404(self, monkeypatch):
        """Verifica que usuario no encontrado devuelve 404."""
        # Verifica que usuario no encontrado devuelve 404.
        app = _app_con_overrides()

        monkeypatch.setattr(
            file_service, "validar_seguridad", lambda a: _make_jpeg_bytes()
        )
        monkeypatch.setattr(
            file_service, "procesar_subida", lambda a, u, raw, f=None: "temp.jpg"
        )

        db_mock = AsyncMock()
        db_mock.commit = AsyncMock()
        db_mock.rollback = AsyncMock()

        async def _fake_db_usuario_no_encontrado():
            """Crea un simulacro de base de datos para usuario no encontrado."""
            return db_mock

        async def fake_obtener(db, usuario_actual_id, for_update=False):
            """Crea un simulacro de obtener."""
            raise HTTPException(
                status_code=404, detail="Error: Perfil de usuario no encontrado"
            )

        app.dependency_overrides[obtener_db] = _fake_db_usuario_no_encontrado
        monkeypatch.setattr(user_service, "obtener_perfil", fake_obtener)
        response = self._post_foto(TestClient(app))
        assert response.status_code == 404

    def test_subida_exitosa_devuelve_200(self, monkeypatch):
        """Verifica que subida exitosa devuelve 200."""
        app = _app_con_overrides()

        monkeypatch.setattr(
            file_service, "validar_seguridad", lambda a: _make_jpeg_bytes()
        )
        monkeypatch.setattr(
            file_service, "procesar_subida", lambda a, u, raw, f=None: "nueva_foto.jpg"
        )

        db_mock = MagicMock()
        db_mock.commit = MagicMock(return_value=None)

        async def fake_db_gen():
            """Crea un simulacro de base de datos gen."""
            return db_mock

        async def fake_obtener(db, usuario_actual_id, for_update=False):
            """Crea un simulacro de obtener."""
            return _usuario_fake(foto_perfil="foto_vieja.jpg")

        async def fake_commit(db_mock):
            """Crea un simulacro de commit."""
            pass

        monkeypatch.setattr(user_service, "obtener_perfil", fake_obtener)

        # Sobrescribe la base de datos para devolver un simulacro compatible con async
        async def _fake_db_commit():
            """Crea un simulacro de base de datos commit."""
            mock = MagicMock()
            mock.commit = _async_noop
            mock.rollback = _async_noop
            return mock

        async def _async_noop(*a, **kw):
            """Gestiona async noop."""
            pass

        app.dependency_overrides[obtener_db] = _fake_db_commit
        response = self._post_foto(TestClient(app))
        assert response.status_code == 200
        assert response.json()["estatus"] == "success"

    def test_sin_archivo_devuelve_422(self):
        """Verifica que sin archivo devuelve 422."""
        app = _app_con_overrides()
        response = TestClient(app).post("/perfil/foto")
        assert response.status_code == 422


# ─────────────────────────────────────────────
# PATCH /perfil/actualizar
# ─────────────────────────────────────────────


class TestActualizarPerfil:
    """Agrupa pruebas relacionadas con actualizar perfil."""

    def test_body_vacio_actualiza_nada_y_devuelve_200(self, monkeypatch):
        """PATCH con body vacío es válido: no toca ningún campo."""
        # Verifica que cuerpo vacio actualiza nada y devuelve 200.
        app = _app_con_overrides()

        async def fake_obtener(db, usuario_actual_id, for_update=False):
            """Crea un simulacro de obtener."""
            return _usuario_fake()

        async def fake_actualizar(db, usuario, datos):
            """Crea un simulacro de actualizar."""
            return {
                "estatus": "success",
                "mensaje": "Perfil de usuario actualizado correctamente",
            }

        monkeypatch.setattr(user_service, "obtener_perfil", fake_obtener)
        monkeypatch.setattr(user_service, "actualizar_perfil_usuario", fake_actualizar)

        response = TestClient(app).patch("/perfil/actualizar", json={})
        assert response.status_code == 200

    def test_email_invalido_devuelve_422(self):
        """Verifica que correo electrónico invalido devuelve 422."""
        app = _app_con_overrides()
        response = TestClient(app).patch(
            "/perfil/actualizar", json={"email": "no-es-email"}
        )
        assert response.status_code == 422

    def test_password_debil_devuelve_422(self):
        """Verifica que password debil devuelve 422."""
        app = _app_con_overrides()
        response = TestClient(app).patch(
            "/perfil/actualizar", json={"password": "debil"}
        )
        assert response.status_code == 422

    def test_actualizacion_exitosa_devuelve_200(self, monkeypatch):
        """Verifica que actualizacion exitosa devuelve 200."""
        # Verifica que actualizacion exitosa devuelve 200.
        app = _app_con_overrides()

        async def fake_obtener(db, usuario_actual_id, for_update=False):
            """Crea un simulacro de obtener."""
            return _usuario_fake()

        async def fake_actualizar(db, usuario, datos):
            """Crea un simulacro de actualizar."""
            return {
                "estatus": "success",
                "mensaje": "Perfil de usuario actualizado correctamente",
            }

        monkeypatch.setattr(user_service, "obtener_perfil", fake_obtener)
        monkeypatch.setattr(user_service, "actualizar_perfil_usuario", fake_actualizar)

        response = TestClient(app).patch(
            "/perfil/actualizar", json={"provincia": "Madrid"}
        )
        assert response.status_code == 200
        assert response.json()["estatus"] == "success"

    def test_email_duplicado_devuelve_400(self, monkeypatch):
        """Verifica que correo electrónico duplicado devuelve 400."""
        # Verifica que correo electrónico duplicado devuelve 400.
        app = _app_con_overrides()

        async def fake_obtener(db, usuario_actual_id, for_update=False):
            """Crea un simulacro de obtener."""
            return _usuario_fake()

        async def fake_actualizar(db, usuario, datos):
            """Crea un simulacro de actualizar."""
            raise HTTPException(
                status_code=400, detail="Error: El email ya está en uso"
            )

        monkeypatch.setattr(user_service, "obtener_perfil", fake_obtener)
        monkeypatch.setattr(user_service, "actualizar_perfil_usuario", fake_actualizar)

        response = TestClient(app).patch(
            "/perfil/actualizar", json={"email": "otro@example.com"}
        )
        assert response.status_code == 400

    def test_usuario_no_encontrado_devuelve_404(self, monkeypatch):
        """Verifica que usuario no encontrado devuelve 404."""
        app = _app_con_overrides()

        async def fake_obtener(db, usuario_actual_id, for_update=False):
            """Crea un simulacro de obtener."""
            raise HTTPException(
                status_code=404, detail="Error: Perfil de usuario no encontrado"
            )

        monkeypatch.setattr(user_service, "obtener_perfil", fake_obtener)
        response = TestClient(app).patch("/perfil/actualizar", json={})
        assert response.status_code == 404


# ─────────────────────────────────────────────
# DELETE /perfil/borrar
# ─────────────────────────────────────────────


class TestBorrarPerfil:
    """Agrupa pruebas relacionadas con borrar perfil."""

    def test_borrar_exitoso_devuelve_200(self, monkeypatch):
        """Verifica que borrar exitoso devuelve 200."""
        # Verifica que borrar exitoso devuelve 200.
        app = _app_con_overrides()

        async def fake_obtener(db, usuario_actual_id, for_update=False):
            """Crea un simulacro de obtener."""
            return _usuario_fake()

        async def fake_eliminar(db, usuario):
            """Crea un simulacro de eliminar."""
            return {"estatus": "success", "mensaje": "Cuenta eliminada correctamente"}

        monkeypatch.setattr(user_service, "obtener_perfil", fake_obtener)
        monkeypatch.setattr(user_service, "eliminar_cuenta", fake_eliminar)
        monkeypatch.setattr(file_service, "borrar_foto", lambda foto, usuario: None)

        response = TestClient(app).delete("/perfil/borrar")
        assert response.status_code == 200
        assert response.json()["estatus"] == "success"

    def test_usuario_no_encontrado_devuelve_404(self, monkeypatch):
        """Verifica que usuario no encontrado devuelve 404."""
        app = _app_con_overrides()

        async def fake_obtener(db, usuario_actual_id, for_update=False):
            """Crea un simulacro de obtener."""
            raise HTTPException(
                status_code=404, detail="Error: Perfil de usuario no encontrado"
            )

        monkeypatch.setattr(user_service, "obtener_perfil", fake_obtener)
        response = TestClient(app).delete("/perfil/borrar")
        assert response.status_code == 404

    def test_foto_se_pasa_a_background_task(self, monkeypatch):
        """Verifica que el router guarda la foto antes del delete y la pasa al background."""
        # Verifica que foto se pasa a background task.
        app = _app_con_overrides()
        fotos_borradas = []

        async def fake_obtener(db, usuario_actual_id, for_update=False):
            """Crea un simulacro de obtener."""
            return _usuario_fake(foto_perfil="foto_a_borrar.jpg")

        async def fake_eliminar(db, usuario):
            """Crea un simulacro de eliminar."""
            return {"estatus": "success", "mensaje": "Cuenta eliminada correctamente"}

        def fake_borrar(foto, usuario):
            """Crea un simulacro de borrar."""
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
    """Agrupa pruebas relacionadas con buscar perfil."""

    def test_q_demasiado_corto_devuelve_422(self):
        """Verifica que q demasiado corto devuelve 422."""
        client = TestClient(_app_con_overrides())
        assert client.get("/perfil/buscar", params={"q": "ab"}).status_code == 422

    def test_q_demasiado_largo_devuelve_422(self):
        """Verifica que q demasiado largo devuelve 422."""
        client = TestClient(_app_con_overrides())
        assert client.get("/perfil/buscar", params={"q": "a" * 51}).status_code == 422

    def test_sin_q_devuelve_422(self):
        """Verifica que sin q devuelve 422."""
        client = TestClient(_app_con_overrides())
        assert client.get("/perfil/buscar").status_code == 422

    def test_sin_app_session_devuelve_403_con_cabecera(self):
        """Verifica que sin app session devuelve 403 con cabecera."""
        app = _build_app()
        client = TestClient(app)
        response = client.get("/perfil/buscar", params={"q": "pep"})
        assert response.status_code == 403
        assert response.headers["x-app-session-expired"] == "1"
        assert "token de sesión" in response.json()["mensaje"].lower()

    def test_app_session_invalido_devuelve_403_con_cabecera(self):
        """Verifica que app session invalido devuelve 403 con cabecera."""
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
        """Verifica que q valida devuelve resultados paginados."""
        # Verifica que q valida devuelve resultados paginados.
        from types import SimpleNamespace

        app = _app_con_overrides()

        async def fake_buscar(db, termino, usuario_actual_id, skip, limit):
            """Crea un simulacro de buscar."""
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
        """Verifica que excluye usuario actual pasandolo al servicio."""
        # Verifica que excluye usuario actual pasandolo al servicio.
        app = _app_con_overrides(usuario_actual_id=99)
        llamada = {}

        async def fake_buscar(db, termino, usuario_actual_id, skip, limit):
            """Crea un simulacro de buscar."""
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
        """Verifica que lista vacia devuelve 200."""
        # Verifica que lista vacia devuelve 200.
        app = _app_con_overrides()

        async def fake_buscar(db, termino, usuario_actual_id, skip, limit):
            """Crea un simulacro de buscar."""
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
        """Verifica que foto pasa por construir URL."""
        # Verifica que foto pasa por construir URL.
        from types import SimpleNamespace

        app = _app_con_overrides()
        fotos_procesadas = []

        async def fake_buscar(db, termino, usuario_actual_id, skip, limit):
            """Crea un simulacro de buscar."""
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
            """Crea un simulacro de construir."""
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
    """Agrupa pruebas relacionadas con ranking obtener."""

    def _ranking_fake(self):
        """Crea un ranking simulado."""
        # Construir un ranking simulado para las pruebas.
        return [
            {
                "posicion": 1,
                "nombre_usuario": "pepe",
                "foto_perfil": None,
                "foto_version": 0,
                "total_puntos": 10,
                "total_metros": 10_000,
            },
            {
                "posicion": 2,
                "nombre_usuario": "ana",
                "foto_perfil": "https://cdn.example.com/ana.jpg",
                "foto_version": 1717236000,
                "total_puntos": 8,
                "total_metros": 8_000,
            },
        ]

    def test_ranking_sin_filtro_devuelve_lista(self, monkeypatch):
        """Verifica que ranking sin filtro devuelve lista."""
        app = _app_con_overrides()

        async def fake_ranking(db, provincia=None):
            """Crea un simulacro de ranking."""
            return self._ranking_fake()

        monkeypatch.setattr(user_service, "obtener_ranking", fake_ranking)
        monkeypatch.setattr(file_service, "construir_url_foto", lambda foto, req: foto)

        response = TestClient(app).get("/ranking/obtener")
        assert response.status_code == 200
        assert isinstance(response.json(), list)
        assert len(response.json()) == 2

    def test_ranking_tiene_campos_requeridos(self, monkeypatch):
        """Verifica que ranking tiene campos requeridos."""
        # Verifica que ranking tiene campos requeridos.
        app = _app_con_overrides()

        async def fake_ranking(db, provincia=None):
            """Crea un simulacro de ranking."""
            return self._ranking_fake()

        monkeypatch.setattr(user_service, "obtener_ranking", fake_ranking)
        monkeypatch.setattr(file_service, "construir_url_foto", lambda foto, req: foto)

        body = TestClient(app).get("/ranking/obtener").json()
        for item in body:
            assert "posicion" in item
            assert "nombre_usuario" in item
            assert "foto_perfil" in item
            assert "foto_version" in item
            assert "total_puntos" in item

    def test_ranking_devuelve_posicion_calculada(self, monkeypatch):
        """Verifica que ranking devuelve posicion calculada."""
        app = _app_con_overrides()

        async def fake_ranking(db, provincia=None):
            """Crea un simulacro de ranking."""
            return self._ranking_fake()

        monkeypatch.setattr(user_service, "obtener_ranking", fake_ranking)
        monkeypatch.setattr(file_service, "construir_url_foto", lambda foto, req: foto)

        body = TestClient(app).get("/ranking/obtener").json()
        assert body[0]["posicion"] == 1
        assert body[1]["posicion"] == 2

    def test_ranking_con_provincia_valida_pasa_filtro(self, monkeypatch):
        """Verifica que ranking con provincia valida pasa filtro."""
        app = _app_con_overrides()
        provincia_recibida = {}

        async def fake_ranking(db, provincia=None):
            """Crea un simulacro de ranking."""
            provincia_recibida["valor"] = provincia
            return []

        monkeypatch.setattr(user_service, "obtener_ranking", fake_ranking)

        TestClient(app).get("/ranking/obtener", params={"provincia": "Madrid"})
        assert provincia_recibida.get("valor") == "Madrid"

    def test_ranking_provincia_invalida_devuelve_422(self):
        """Verifica que ranking provincia invalida devuelve 422."""
        app = _app_con_overrides()
        response = TestClient(app).get(
            "/ranking/obtener", params={"provincia": "Narnia"}
        )
        assert response.status_code == 422

    def test_foto_ranking_pasa_por_construir_url(self, monkeypatch):
        """El router debe procesar cada foto a través de construir_url_foto."""
        # Verifica que foto ranking pasa por construir URL.
        app = _app_con_overrides()
        fotos_procesadas = []

        async def fake_ranking(db, provincia=None):
            """Crea un simulacro de ranking."""
            return [
                {
                    "posicion": 1,
                    "nombre_usuario": "pepe",
                    "foto_perfil": "foto.jpg",
                    "foto_version": 1717236000,
                    "total_puntos": 5,
                    "total_metros": 5_000,
                }
            ]

        def fake_construir(foto, req):
            """Crea un simulacro de construir."""
            fotos_procesadas.append(foto)
            return f"http://localhost/imagenes/{foto}"

        monkeypatch.setattr(user_service, "obtener_ranking", fake_ranking)
        monkeypatch.setattr(file_service, "construir_url_foto", fake_construir)

        TestClient(app).get("/ranking/obtener")
        assert "foto.jpg" in fotos_procesadas

    def test_ranking_vacio_devuelve_lista_vacia(self, monkeypatch):
        """Verifica que ranking vacio devuelve lista vacia."""
        app = _app_con_overrides()

        async def fake_ranking(db, provincia=None):
            """Crea un simulacro de ranking."""
            return []

        monkeypatch.setattr(user_service, "obtener_ranking", fake_ranking)
        response = TestClient(app).get("/ranking/obtener")
        assert response.json() == []
