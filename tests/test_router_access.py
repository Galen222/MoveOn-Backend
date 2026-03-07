# tests/test_router_access.py
#
# Tests de integración para routers/access.py usando TestClient.
# Cubre: /handshake, /login, /token/refresh, /logout, /password/solicitar, /password/confirmar.
#
# Estrategia:
# - dependency_overrides para bypassear obtener_db y verificar_sesion_aplicacion.
# - monkeypatch en los servicios para controlar respuestas sin BD real.
# - Tests de seguridad usan el app_session real (sin bypass) para verificar que
#   el middleware rechaza correctamente requests sin token o con token inválido.

from fastapi import FastAPI, HTTPException
from fastapi.responses import JSONResponse
from fastapi.testclient import TestClient

import auth
import pytest
from config import settings
from database import obtener_db
from routers.access import router as access_router
from services import access_service
from services.identity_rate_limit import IdentityRateLimitExceeded


# ─────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────

def _build_app() -> FastAPI:
    """App mínima con solo el router de acceso y los exception handlers relevantes."""
    from exceptions import manejador_http_exception, manejador_validacion_personalizado
    from fastapi.exceptions import RequestValidationError
    from services.identity_rate_limit import IdentityRateLimitExceeded
    from exceptions import error_response
    from fastapi import Request

    app = FastAPI()
    app.include_router(access_router)
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


def _bypass_app_session():
    """Override que deja pasar la verificación de sesión de app."""
    return "ok"


def _app_with_overrides(monkeypatch=None) -> FastAPI:
    """App con DB y app_session bypasseados. Listo para mockear servicios."""
    app = _build_app()
    app.dependency_overrides[obtener_db] = _fake_db
    app.dependency_overrides[auth.verificar_sesion_aplicacion] = _bypass_app_session
    return app


def _valid_app_session_header() -> dict:
    """Cabecera con un token de app_session real y válido."""
    token = auth.crear_token_aplicacion()
    return {"X-App-Session": token}


# ─────────────────────────────────────────────
# GET /handshake
# ─────────────────────────────────────────────

class TestHandshake:
    def test_sin_x_app_id_devuelve_403(self):
        client = TestClient(_build_app())
        response = client.get("/handshake")
        assert response.status_code == 403
        assert "MoveOn" in response.json()["mensaje"]

    def test_x_app_id_incorrecto_devuelve_403(self):
        client = TestClient(_build_app())
        response = client.get("/handshake", headers={"X-App-Id": "incorrecto"})
        assert response.status_code == 403
        assert "MoveOn" in response.json()["mensaje"]

    def test_x_app_id_correcto_devuelve_app_session_token(self):
        client = TestClient(_build_app())
        response = client.get("/handshake", headers={"X-App-Id": settings.APP_ID})
        assert response.status_code == 200
        body = response.json()
        assert "app_session_token" in body
        assert isinstance(body["app_session_token"], str)
        assert body["app_session_token"]

    def test_token_devuelto_es_verificable(self, monkeypatch):
        """El app_session_token devuelto debe ser verificable por el middleware."""
        app = _build_app()
        app.dependency_overrides[obtener_db] = _fake_db

        # Mockear el servicio para evitar acceso real a BD
        async def fake_buscar(db, identificador):
            return None

        monkeypatch.setattr(access_service, "buscar_por_identificador", fake_buscar)

        client = TestClient(app)
        token = client.get(
            "/handshake", headers={"X-App-Id": settings.APP_ID}
        ).json()["app_session_token"]

        # 401 (credenciales inválidas) confirma que pasó la barrera de app_session (no 403)
        response = client.post(
            "/login",
            json={"identificador": "pepe", "password": "Pass1234"},
            headers={"X-App-Session": token},
        )
        assert response.status_code == 401


# ─────────────────────────────────────────────
# POST /login — seguridad de sesión de app
# ─────────────────────────────────────────────

class TestLoginAppSession:
    """Verifica que /login exige X-App-Session válido."""

    def test_sin_app_session_devuelve_403(self):
        client = TestClient(_build_app())
        response = client.post("/login", json={"identificador": "pepe", "password": "Pass1234"})
        assert response.status_code == 403
        assert response.headers.get("x-app-session-expired") == "1"

    def test_app_session_invalido_devuelve_403(self):
        client = TestClient(_build_app())
        response = client.post(
            "/login",
            json={"identificador": "pepe", "password": "Pass1234"},
            headers={"X-App-Session": "token-falso"},
        )
        assert response.status_code == 403
        assert response.headers.get("x-app-session-expired") == "1"

    def test_app_session_valido_pasa_la_barrera(self, monkeypatch):
        """Con app_session real y credenciales malas obtenemos 401, no 403."""
        app = _build_app()
        app.dependency_overrides[obtener_db] = _fake_db

        async def fake_buscar(db, identificador):
            return None

        monkeypatch.setattr(access_service, "buscar_por_identificador", fake_buscar)
        client = TestClient(app)
        response = client.post(
            "/login",
            json={"identificador": "pepe", "password": "Pass1234"},
            headers=_valid_app_session_header(),
        )
        assert response.status_code == 401


# ─────────────────────────────────────────────
# POST /login — validación de esquema
# ─────────────────────────────────────────────

class TestLoginValidacion:
    def test_body_vacio_devuelve_422(self):
        app = _app_with_overrides()
        client = TestClient(app)
        response = client.post("/login", json={})
        assert response.status_code == 422

    def test_sin_identificador_devuelve_422(self):
        app = _app_with_overrides()
        client = TestClient(app)
        response = client.post("/login", json={"password": "Pass1234"})
        assert response.status_code == 422

    def test_sin_password_devuelve_422(self):
        app = _app_with_overrides()
        client = TestClient(app)
        response = client.post("/login", json={"identificador": "pepe"})
        assert response.status_code == 422

    def test_identificador_vacio_devuelve_422(self):
        app = _app_with_overrides()
        client = TestClient(app)
        response = client.post("/login", json={"identificador": "", "password": "Pass1234"})
        assert response.status_code == 422


# ─────────────────────────────────────────────
# POST /login — lógica de negocio
# ─────────────────────────────────────────────

class TestLoginLogica:
    def test_usuario_no_encontrado_devuelve_401(self, monkeypatch):
        app = _app_with_overrides()

        async def fake_buscar(db, identificador):
            return None

        monkeypatch.setattr(access_service, "buscar_por_identificador", fake_buscar)
        client = TestClient(app)
        response = client.post("/login", json={"identificador": "noexiste", "password": "Pass1234"})
        assert response.status_code == 401
        assert "credenciales" in response.json()["mensaje"].lower()

    def test_password_incorrecta_devuelve_401(self, monkeypatch):
        from types import SimpleNamespace

        app = _app_with_overrides()

        async def fake_buscar(db, identificador):
            return SimpleNamespace(
                id=1,
                nombre_usuario="pepe",
                password_encriptada="$2b$12$hashfake"
            )

        monkeypatch.setattr(access_service, "buscar_por_identificador", fake_buscar)
        monkeypatch.setattr(auth, "comprobar_password", lambda plain, hashed: False)

        client = TestClient(app)
        response = client.post("/login", json={"identificador": "pepe", "password": "WrongPass1"})
        assert response.status_code == 401
        assert "credenciales" in response.json()["mensaje"].lower()

    def test_login_exitoso_devuelve_tokens(self, monkeypatch):
        from types import SimpleNamespace

        app = _app_with_overrides()

        async def fake_buscar(db, identificador):
            return SimpleNamespace(
                id=1,
                nombre_usuario="pepe",
                password_encriptada="$2b$12$hashfake"
            )

        async def fake_crear_sesion(db, usuario):
            return {
                "estatus": "success",
                "nombre_usuario": "pepe",
                "token_acceso": "fake-access",
                "refresh_token": "fake-refresh",
            }

        monkeypatch.setattr(access_service, "buscar_por_identificador", fake_buscar)
        monkeypatch.setattr(auth, "comprobar_password", lambda plain, hashed: True)
        monkeypatch.setattr(access_service, "crear_sesion_login", fake_crear_sesion)

        client = TestClient(app)
        response = client.post("/login", json={"identificador": "pepe", "password": "Pass1234"})

        assert response.status_code == 200
        body = response.json()
        assert body["estatus"] == "success"
        assert body["nombre_usuario"] == "pepe"
        assert "token_acceso" in body
        assert "refresh_token" in body

    def test_login_dispara_identity_rate_limit_429(self, monkeypatch):
        app = _app_with_overrides()

        monkeypatch.setattr(
            "routers.access.check_identity_limit",
            lambda scope, identity, limit: (_ for _ in ()).throw(IdentityRateLimitExceeded())
        )

        client = TestClient(app)
        response = client.post("/login", json={"identificador": "pepe", "password": "Pass1234"})
        assert response.status_code == 429

    def test_login_respuesta_no_revela_si_es_usuario_o_password(self, monkeypatch):
        """
        Ambos errores (usuario no existe / password incorrecta) deben
        devolver el mismo mensaje para no dar pistas al atacante.
        """
        from types import SimpleNamespace
        app = _app_with_overrides()

        async def fake_buscar_ninguno(db, identificador):
            return None

        async def fake_buscar_encontrado(db, identificador):
            return SimpleNamespace(id=1, nombre_usuario="pepe", password_encriptada="hash")

        monkeypatch.setattr(auth, "comprobar_password", lambda p, h: False)

        client = TestClient(app)

        monkeypatch.setattr(access_service, "buscar_por_identificador", fake_buscar_ninguno)
        r1 = client.post("/login", json={"identificador": "noexiste", "password": "Pass1234"})

        monkeypatch.setattr(access_service, "buscar_por_identificador", fake_buscar_encontrado)
        r2 = client.post("/login", json={"identificador": "pepe", "password": "WrongPass1"})

        assert r1.status_code == r2.status_code == 401
        assert r1.json()["mensaje"] == r2.json()["mensaje"]


# ─────────────────────────────────────────────
# POST /token/refresh — seguridad de sesión de app
# ─────────────────────────────────────────────

class TestRefreshAppSession:
    def test_sin_app_session_devuelve_403(self):
        client = TestClient(_build_app())
        response = client.post("/token/refresh", json={"refresh_token": "tok"})
        assert response.status_code == 403
        assert response.headers.get("x-app-session-expired") == "1"


# ─────────────────────────────────────────────
# POST /token/refresh — validación de esquema
# ─────────────────────────────────────────────

class TestRefreshValidacion:
    def test_body_vacio_devuelve_422(self):
        app = _app_with_overrides()
        client = TestClient(app)
        response = client.post("/token/refresh", json={})
        assert response.status_code == 422

    def test_refresh_token_vacio_devuelve_422(self):
        app = _app_with_overrides()
        client = TestClient(app)
        response = client.post("/token/refresh", json={"refresh_token": ""})
        assert response.status_code == 422


# ─────────────────────────────────────────────
# POST /token/refresh — lógica de negocio
# ─────────────────────────────────────────────

class TestRefreshLogica:
    def test_token_invalido_devuelve_401(self, monkeypatch):
        app = _app_with_overrides()

        async def fake_refrescar(db, token):
            raise HTTPException(status_code=401, detail="Error: Refresh token inválido")

        monkeypatch.setattr(access_service, "refrescar_sesion", fake_refrescar)
        client = TestClient(app)
        response = client.post("/token/refresh", json={"refresh_token": "token-manipulado"})
        assert response.status_code == 401

    def test_token_reutilizado_devuelve_401(self, monkeypatch):
        app = _app_with_overrides()

        async def fake_refrescar(db, token):
            raise HTTPException(status_code=401, detail="Error: Refresh token reutilizado")

        monkeypatch.setattr(access_service, "refrescar_sesion", fake_refrescar)
        client = TestClient(app)
        response = client.post("/token/refresh", json={"refresh_token": "tok-reutilizado"})
        assert response.status_code == 401
        assert "reutilizado" in response.json()["mensaje"].lower()

    def test_refresh_exitoso_devuelve_nuevos_tokens(self, monkeypatch):
        app = _app_with_overrides()

        async def fake_refrescar(db, token):
            return {
                "estatus": "success",
                "nombre_usuario": "pepe",
                "token_acceso": "nuevo-access",
                "refresh_token": "nuevo-refresh",
            }

        monkeypatch.setattr(access_service, "refrescar_sesion", fake_refrescar)
        client = TestClient(app)
        response = client.post("/token/refresh", json={"refresh_token": "tok-valido"})

        assert response.status_code == 200
        body = response.json()
        assert body["estatus"] == "success"
        assert body["token_acceso"] == "nuevo-access"
        assert body["refresh_token"] == "nuevo-refresh"

    def test_refresh_devuelve_token_distinto_al_enviado(self, monkeypatch):
        """El token de respuesta debe ser diferente al enviado (rotación real)."""
        app = _app_with_overrides()
        token_enviado = "tok-original"

        async def fake_refrescar(db, token):
            return {
                "estatus": "success",
                "nombre_usuario": "pepe",
                "token_acceso": "nuevo-access",
                "refresh_token": "tok-rotado-nuevo",
            }

        monkeypatch.setattr(access_service, "refrescar_sesion", fake_refrescar)
        client = TestClient(app)
        response = client.post("/token/refresh", json={"refresh_token": token_enviado})

        assert response.json()["refresh_token"] != token_enviado


# ─────────────────────────────────────────────
# POST /logout — seguridad de sesión de app
# ─────────────────────────────────────────────

class TestLogoutAppSession:
    def test_sin_app_session_devuelve_403(self):
        client = TestClient(_build_app())
        response = client.post("/logout", json={"refresh_token": "tok"})
        assert response.status_code == 403
        assert response.headers.get("x-app-session-expired") == "1"


# ─────────────────────────────────────────────
# POST /logout — validación de esquema
# ─────────────────────────────────────────────

class TestLogoutValidacion:
    def test_body_vacio_devuelve_422(self):
        app = _app_with_overrides()
        client = TestClient(app)
        response = client.post("/logout", json={})
        assert response.status_code == 422

    def test_refresh_token_vacio_devuelve_422(self):
        app = _app_with_overrides()
        client = TestClient(app)
        response = client.post("/logout", json={"refresh_token": ""})
        assert response.status_code == 422


# ─────────────────────────────────────────────
# POST /logout — lógica de negocio
# ─────────────────────────────────────────────

class TestLogoutLogica:
    def test_logout_exitoso_devuelve_200(self, monkeypatch):
        app = _app_with_overrides()

        async def fake_cerrar(db, token):
            return {"estatus": "success", "mensaje": "Sesión cerrada"}

        monkeypatch.setattr(access_service, "cerrar_sesion", fake_cerrar)
        client = TestClient(app)
        response = client.post("/logout", json={"refresh_token": "tok-valido"})

        assert response.status_code == 200
        assert response.json()["estatus"] == "success"

    def test_logout_idempotente_con_token_invalido(self, monkeypatch):
        """Logout con token inválido/expirado debe devolver 200 igualmente."""
        app = _app_with_overrides()

        async def fake_cerrar(db, token):
            # El servicio atrapa el error internamente y devuelve success
            return {"estatus": "success", "mensaje": "Sesión cerrada"}

        monkeypatch.setattr(access_service, "cerrar_sesion", fake_cerrar)
        client = TestClient(app)
        response = client.post("/logout", json={"refresh_token": "tok-invalido-o-expirado"})

        assert response.status_code == 200

    def test_logout_idempotente_con_token_ya_revocado(self, monkeypatch):
        """Logout doble (ya revocado) debe devolver 200, no 4xx."""
        app = _app_with_overrides()

        async def fake_cerrar_ya_revocado(db, token):
            return {"estatus": "success", "mensaje": "Sesión cerrada"}

        monkeypatch.setattr(access_service, "cerrar_sesion", fake_cerrar_ya_revocado)
        client = TestClient(app)

        for _ in range(2):
            response = client.post("/logout", json={"refresh_token": "tok-ya-revocado"})
            assert response.status_code == 200


# ─────────────────────────────────────────────
# POST /password/solicitar — seguridad de sesión de app
# ─────────────────────────────────────────────

class TestSolicitarPasswordAppSession:
    def test_sin_app_session_devuelve_403(self):
        client = TestClient(_build_app())
        response = client.post("/password/solicitar", json={"email": "a@a.com"})
        assert response.status_code == 403
        assert response.headers.get("x-app-session-expired") == "1"


# ─────────────────────────────────────────────
# POST /password/solicitar — validación de esquema
# ─────────────────────────────────────────────

class TestSolicitarPasswordValidacion:
    def test_body_vacio_devuelve_422(self):
        app = _app_with_overrides()
        client = TestClient(app)
        response = client.post("/password/solicitar", json={})
        assert response.status_code == 422

    def test_email_formato_invalido_devuelve_422(self):
        app = _app_with_overrides()
        client = TestClient(app)
        response = client.post("/password/solicitar", json={"email": "no-es-un-email"})
        assert response.status_code == 422

    def test_email_vacio_devuelve_422(self):
        app = _app_with_overrides()
        client = TestClient(app)
        response = client.post("/password/solicitar", json={"email": ""})
        assert response.status_code == 422


# ─────────────────────────────────────────────
# POST /password/solicitar — lógica de negocio
# ─────────────────────────────────────────────

class TestSolicitarPasswordLogica:
    def test_email_existente_devuelve_200_con_mensaje_generico(self, monkeypatch):
        app = _app_with_overrides()

        async def fake_generar(db, email, bg):
            return {"estatus": "success", "mensaje": "Si el email corresponde a un usuario recibirá un código"}

        monkeypatch.setattr(access_service, "generar_codigo_recuperacion", fake_generar)
        client = TestClient(app)
        response = client.post("/password/solicitar", json={"email": "pepe@example.com"})

        assert response.status_code == 200
        assert response.json()["estatus"] == "success"

    def test_email_inexistente_devuelve_mismo_200_que_existente(self, monkeypatch):
        """
        El endpoint no debe revelar si el email existe o no.
        Ambos casos devuelven exactamente el mismo mensaje.
        """
        app = _app_with_overrides()

        async def fake_generar(db, email, bg):
            return {"estatus": "success", "mensaje": "Si el email corresponde a un usuario recibirá un código"}

        monkeypatch.setattr(access_service, "generar_codigo_recuperacion", fake_generar)
        client = TestClient(app)

        r1 = client.post("/password/solicitar", json={"email": "existe@example.com"})
        r2 = client.post("/password/solicitar", json={"email": "noexiste@example.com"})

        assert r1.status_code == r2.status_code == 200
        assert r1.json()["mensaje"] == r2.json()["mensaje"]

    def test_solicitar_dispara_identity_rate_limit_429(self, monkeypatch):
        app = _app_with_overrides()

        monkeypatch.setattr(
            "routers.access.check_identity_limit",
            lambda scope, identity, limit: (_ for _ in ()).throw(IdentityRateLimitExceeded())
        )

        client = TestClient(app)
        response = client.post("/password/solicitar", json={"email": "pepe@example.com"})
        assert response.status_code == 429


# ─────────────────────────────────────────────
# POST /password/confirmar — seguridad de sesión de app
# ─────────────────────────────────────────────

class TestConfirmarPasswordAppSession:
    def test_sin_app_session_devuelve_403(self):
        client = TestClient(_build_app())
        response = client.post(
            "/password/confirmar",
            json={"email": "a@a.com", "codigo": "123456", "nueva_password": "Nueva1234"}
        )
        assert response.status_code == 403
        assert response.headers.get("x-app-session-expired") == "1"


# ─────────────────────────────────────────────
# POST /password/confirmar — validación de esquema
# ─────────────────────────────────────────────

class TestConfirmarPasswordValidacion:
    def test_body_vacio_devuelve_422(self):
        app = _app_with_overrides()
        client = TestClient(app)
        response = client.post("/password/confirmar", json={})
        assert response.status_code == 422

    def test_email_invalido_devuelve_422(self):
        app = _app_with_overrides()
        client = TestClient(app)
        response = client.post(
            "/password/confirmar",
            json={"email": "no-email", "codigo": "123456", "nueva_password": "Nueva1234"}
        )
        assert response.status_code == 422

    def test_sin_codigo_devuelve_422(self):
        app = _app_with_overrides()
        client = TestClient(app)
        response = client.post(
            "/password/confirmar",
            json={"email": "pepe@example.com", "nueva_password": "Nueva1234"}
        )
        assert response.status_code == 422

    def test_sin_nueva_password_devuelve_422(self):
        app = _app_with_overrides()
        client = TestClient(app)
        response = client.post(
            "/password/confirmar",
            json={"email": "pepe@example.com", "codigo": "123456"}
        )
        assert response.status_code == 422

    def test_codigo_de_5_digitos_devuelve_422(self):
        """ConfirmarPassword valida que el código tenga exactamente 6 dígitos."""
        app = _app_with_overrides()
        client = TestClient(app)
        response = client.post(
            "/password/confirmar",
            json={"email": "pepe@example.com", "codigo": "12345", "nueva_password": "Nueva1234"}
        )
        assert response.status_code == 422

    def test_codigo_de_7_digitos_devuelve_422(self):
        app = _app_with_overrides()
        client = TestClient(app)
        response = client.post(
            "/password/confirmar",
            json={"email": "pepe@example.com", "codigo": "1234567", "nueva_password": "Nueva1234"}
        )
        assert response.status_code == 422

    def test_codigo_con_letras_devuelve_422(self):
        app = _app_with_overrides()
        client = TestClient(app)
        response = client.post(
            "/password/confirmar",
            json={"email": "pepe@example.com", "codigo": "12345A", "nueva_password": "Nueva1234"}
        )
        assert response.status_code == 422

    def test_password_debil_devuelve_422(self):
        """La nueva contraseña debe pasar las mismas reglas que en registro."""
        app = _app_with_overrides()
        client = TestClient(app)
        response = client.post(
            "/password/confirmar",
            json={"email": "pepe@example.com", "codigo": "123456", "nueva_password": "debil"}
        )
        assert response.status_code == 422


# ─────────────────────────────────────────────
# POST /password/confirmar — lógica de negocio
# ─────────────────────────────────────────────

class TestConfirmarPasswordLogica:
    _payload = {
        "email": "pepe@example.com",
        "codigo": "123456",
        "nueva_password": "Nueva1234"
    }

    def test_codigo_incorrecto_devuelve_400(self, monkeypatch):
        app = _app_with_overrides()

        async def fake_resetear(db, datos):
            raise HTTPException(status_code=400, detail="Error: Código o email inválidos")

        monkeypatch.setattr(access_service, "resetear_password", fake_resetear)
        client = TestClient(app)
        response = client.post("/password/confirmar", json=self._payload)

        assert response.status_code == 400
        assert "inválidos" in response.json()["mensaje"].lower()

    def test_codigo_expirado_devuelve_400(self, monkeypatch):
        app = _app_with_overrides()

        async def fake_resetear(db, datos):
            raise HTTPException(status_code=400, detail="Error: El código ha expirado")

        monkeypatch.setattr(access_service, "resetear_password", fake_resetear)
        client = TestClient(app)
        response = client.post("/password/confirmar", json=self._payload)

        assert response.status_code == 400
        assert "expirado" in response.json()["mensaje"].lower()

    def test_confirmar_exitoso_devuelve_200(self, monkeypatch):
        app = _app_with_overrides()

        async def fake_resetear(db, datos):
            return {"estatus": "success", "mensaje": "Contraseña actualizada correctamente"}

        monkeypatch.setattr(access_service, "resetear_password", fake_resetear)
        client = TestClient(app)
        response = client.post("/password/confirmar", json=self._payload)

        assert response.status_code == 200
        assert response.json()["estatus"] == "success"

    def test_confirmar_dispara_identity_rate_limit_429(self, monkeypatch):
        app = _app_with_overrides()

        monkeypatch.setattr(
            "routers.access.check_identity_limit",
            lambda scope, identity, limit: (_ for _ in ()).throw(IdentityRateLimitExceeded())
        )

        client = TestClient(app)
        response = client.post("/password/confirmar", json=self._payload)
        assert response.status_code == 429

    def test_confirmar_recibe_datos_correctos_en_servicio(self, monkeypatch):
        """Verifica que el router pasa los datos al servicio sin modificarlos."""
        app = _app_with_overrides()
        capturado = {}

        async def fake_resetear(db, datos):
            capturado["email"] = datos.email
            capturado["codigo"] = datos.codigo
            return {"estatus": "success", "mensaje": "Contraseña actualizada correctamente"}

        monkeypatch.setattr(access_service, "resetear_password", fake_resetear)
        client = TestClient(app)
        client.post("/password/confirmar", json=self._payload)

        assert str(capturado["email"]).lower() == "pepe@example.com"
        assert capturado["codigo"] == "123456"
        