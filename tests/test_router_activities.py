#
# Tests de integración para routers/activities.py usando TestClient.
# Cubre: /actividad/guardar, /actividad/obtener/{id},
#        /actividad/obtener_todas, /actividad/borrar/{id}, /actividad/borrar_todas.
#
# Estrategia:
# - dependency_overrides para bypassear obtener_db, verificar_sesion_aplicacion
#   y obtener_usuario_actual.
# - monkeypatch en activities_service para controlar respuestas sin BD real.

from datetime import datetime, timezone
from types import SimpleNamespace

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.testclient import TestClient

import auth
from database import obtener_db
from exceptions import manejador_http_exception, manejador_validacion_personalizado
from routers.activities import router as activities_router
from services import activities_service


# ─────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────


def _build_app() -> FastAPI:
    app = FastAPI()
    app.include_router(activities_router)
    app.add_exception_handler(
        RequestValidationError, manejador_validacion_personalizado
    )

    async def http_exc_handler(req: Request, exc: Exception) -> JSONResponse:
        if isinstance(exc, HTTPException):
            return manejador_http_exception(req, exc)
        return JSONResponse(
            status_code=500, content={"estatus": "error", "mensaje": "Error interno"}
        )

    app.add_exception_handler(HTTPException, http_exc_handler)
    return app


async def _fake_db():
    return None


def _app_con_overrides(usuario_actual_id: int = 1) -> FastAPI:
    app = _build_app()
    app.dependency_overrides[obtener_db] = _fake_db
    app.dependency_overrides[auth.verificar_sesion_aplicacion] = lambda: "ok"
    app.dependency_overrides[auth.obtener_usuario_actual] = lambda: usuario_actual_id
    return app


def _payload_actividad(**kwargs) -> dict:
    defaults = {
        "tipo": "Correr",
        "distancia": 5000,
        "duracion": 1800,
        "calorias_quemadas": 350,
        "fecha_ruta": "2024-06-01T10:00:00Z",
    }
    defaults.update(kwargs)
    return defaults


def _actividad_fake(**kwargs) -> SimpleNamespace:
    defaults = dict(
        id=1,
        tipo="Correr",
        distancia=5000,
        duracion=1800,
        calorias_quemadas=350,
        ruta_polilinea=None,
        ruta_mapa_url=None,
        fecha_ruta=datetime(2024, 6, 1, 10, 0, 0, tzinfo=timezone.utc),
        nuevo_total_puntos=None,
    )
    defaults.update(kwargs)
    return SimpleNamespace(**defaults)


# ─────────────────────────────────────────────
# POST /actividad/guardar — app session
# ─────────────────────────────────────────────


class TestGuardarActividadAppSession:
    def test_sin_app_session_devuelve_403(self):
        client = TestClient(_build_app())
        response = client.post("/actividad/guardar", json=_payload_actividad())
        assert response.status_code == 403
        assert response.headers.get("x-app-session-expired") == "1"


# ─────────────────────────────────────────────
# POST /actividad/guardar — validación de esquema
# ─────────────────────────────────────────────


class TestGuardarActividadValidacion:
    def test_body_vacio_devuelve_422(self):
        client = TestClient(_app_con_overrides())
        assert client.post("/actividad/guardar", json={}).status_code == 422

    def test_sin_tipo_devuelve_422(self):
        payload = _payload_actividad()
        del payload["tipo"]
        assert (
            TestClient(_app_con_overrides())
            .post("/actividad/guardar", json=payload)
            .status_code
            == 422
        )

    def test_tipo_invalido_devuelve_422(self):
        payload = {**_payload_actividad(), "tipo": "Nadar"}
        assert (
            TestClient(_app_con_overrides())
            .post("/actividad/guardar", json=payload)
            .status_code
            == 422
        )

    def test_distancia_negativa_devuelve_422(self):
        payload = {**_payload_actividad(), "distancia": -100}
        assert (
            TestClient(_app_con_overrides())
            .post("/actividad/guardar", json=payload)
            .status_code
            == 422
        )

    def test_distancia_cero_devuelve_422(self):
        payload = {**_payload_actividad(), "distancia": 0}
        assert (
            TestClient(_app_con_overrides())
            .post("/actividad/guardar", json=payload)
            .status_code
            == 422
        )

    def test_distancia_float_devuelve_422(self):
        """StrictInt rechaza flotantes aunque sean enteros."""
        payload = {**_payload_actividad(), "distancia": 5000.0}
        assert (
            TestClient(_app_con_overrides())
            .post("/actividad/guardar", json=payload)
            .status_code
            == 422
        )

    def test_distancia_superior_a_300km_devuelve_422(self):
        payload = {**_payload_actividad(), "distancia": 300001}
        assert (
            TestClient(_app_con_overrides())
            .post("/actividad/guardar", json=payload)
            .status_code
            == 422
        )

    def test_duracion_negativa_devuelve_422(self):
        payload = {**_payload_actividad(), "duracion": -1}
        assert (
            TestClient(_app_con_overrides())
            .post("/actividad/guardar", json=payload)
            .status_code
            == 422
        )

    def test_duracion_superior_a_24h_devuelve_422(self):
        payload = {**_payload_actividad(), "duracion": 86401}
        assert (
            TestClient(_app_con_overrides())
            .post("/actividad/guardar", json=payload)
            .status_code
            == 422
        )

    def test_calorias_negativas_devuelve_422(self):
        payload = {**_payload_actividad(), "calorias_quemadas": 0}
        assert (
            TestClient(_app_con_overrides())
            .post("/actividad/guardar", json=payload)
            .status_code
            == 422
        )

    def test_calorias_superiores_a_10000_devuelve_422(self):
        payload = {**_payload_actividad(), "calorias_quemadas": 10001}
        assert (
            TestClient(_app_con_overrides())
            .post("/actividad/guardar", json=payload)
            .status_code
            == 422
        )

    def test_ruta_mapa_url_invalida_devuelve_422(self):
        payload = {**_payload_actividad(), "ruta_mapa_url": "no-es-una-url"}
        assert (
            TestClient(_app_con_overrides())
            .post("/actividad/guardar", json=payload)
            .status_code
            == 422
        )

    def test_fecha_futura_devuelve_422(self):
        payload = {**_payload_actividad(), "fecha_ruta": "2099-01-01T00:00:00Z"}
        assert (
            TestClient(_app_con_overrides())
            .post("/actividad/guardar", json=payload)
            .status_code
            == 422
        )

    def test_sin_fecha_ruta_devuelve_422(self):
        payload = _payload_actividad()
        del payload["fecha_ruta"]
        assert (
            TestClient(_app_con_overrides())
            .post("/actividad/guardar", json=payload)
            .status_code
            == 422
        )


# ─────────────────────────────────────────────
# POST /actividad/guardar — lógica de negocio
# ─────────────────────────────────────────────


class TestGuardarActividadLogica:
    def test_guardar_exitoso_devuelve_200_con_campos(self, monkeypatch):
        app = _app_con_overrides()

        async def fake_crear(db, usuario_actual_id, datos):
            return {
                "id": 42,
                "tipo": "Correr",
                "distancia": 5000,
                "duracion": 1800,
                "calorias_quemadas": 350,
                "ruta_polilinea": None,
                "ruta_mapa_url": None,
                "fecha_ruta": "2024-06-01T10:00:00Z",
                "nuevo_total_puntos": 5,
            }

        monkeypatch.setattr(activities_service, "crear_actividad", fake_crear)
        response = TestClient(app).post("/actividad/guardar", json=_payload_actividad())

        assert response.status_code == 200
        body = response.json()
        assert body["id"] == 42
        assert body["tipo"] == "Correr"
        assert body["nuevo_total_puntos"] == 5

    def test_usuario_no_encontrado_devuelve_404(self, monkeypatch):
        app = _app_con_overrides()

        async def fake_crear(db, usuario_actual_id, datos):
            raise HTTPException(status_code=404, detail="Error: Usuario no encontrado")

        monkeypatch.setattr(activities_service, "crear_actividad", fake_crear)
        response = TestClient(app).post("/actividad/guardar", json=_payload_actividad())
        assert response.status_code == 404

    def test_caminar_es_tipo_valido(self, monkeypatch):
        app = _app_con_overrides()

        async def fake_crear(db, usuario_actual_id, datos):
            return _actividad_fake(tipo="Caminar", nuevo_total_puntos=2).__dict__

        monkeypatch.setattr(activities_service, "crear_actividad", fake_crear)
        payload = {**_payload_actividad(), "tipo": "Caminar"}
        response = TestClient(app).post("/actividad/guardar", json=payload)
        assert response.status_code == 200


# ─────────────────────────────────────────────
# GET /actividad/obtener/{id_actividad}
# ─────────────────────────────────────────────


class TestObtenerActividadAppSession:
    def test_sin_app_session_devuelve_403(self):
        client = TestClient(_build_app())
        assert client.get("/actividad/obtener/1").status_code == 403


class TestObtenerActividadValidacion:
    def test_id_no_numerico_devuelve_422(self):
        client = TestClient(_app_con_overrides())
        assert client.get("/actividad/obtener/abc").status_code == 422

    def test_id_float_devuelve_422(self):
        client = TestClient(_app_con_overrides())
        assert client.get("/actividad/obtener/1.5").status_code == 422


class TestObtenerActividadLogica:
    def test_actividad_encontrada_devuelve_200(self, monkeypatch):
        app = _app_con_overrides()

        async def fake_obtener(db, usuario_actual_id, id_actividad):
            return _actividad_fake(id=id_actividad)

        monkeypatch.setattr(activities_service, "obtener_actividad", fake_obtener)
        response = TestClient(app).get("/actividad/obtener/1")
        assert response.status_code == 200
        assert response.json()["id"] == 1

    def test_actividad_no_encontrada_devuelve_404(self, monkeypatch):
        app = _app_con_overrides()

        async def fake_obtener(db, usuario_actual_id, id_actividad):
            raise HTTPException(
                status_code=404, detail="Error: Actividad no encontrada"
            )

        monkeypatch.setattr(activities_service, "obtener_actividad", fake_obtener)
        response = TestClient(app).get("/actividad/obtener/999")
        assert response.status_code == 404

    def test_actividad_de_otro_usuario_devuelve_404(self, monkeypatch):
        """El servicio ya filtra por usuario_id, el router no debe bypassear esto."""
        app = _app_con_overrides(usuario_actual_id=1)

        async def fake_obtener(db, usuario_actual_id, id_actividad):
            # El servicio lanza 404 si la actividad no pertenece al usuario
            raise HTTPException(
                status_code=404, detail="Error: Actividad no encontrada"
            )

        monkeypatch.setattr(activities_service, "obtener_actividad", fake_obtener)
        response = TestClient(app).get("/actividad/obtener/99")
        assert response.status_code == 404


# ─────────────────────────────────────────────
# GET /actividad/obtener_todas
# ─────────────────────────────────────────────


class TestObtenerTodasAppSession:
    def test_sin_app_session_devuelve_403(self):
        assert (
            TestClient(_build_app()).get("/actividad/obtener_todas").status_code == 403
        )


class TestObtenerTodasValidacion:
    def test_skip_negativo_devuelve_422(self):
        client = TestClient(_app_con_overrides())
        assert (
            client.get("/actividad/obtener_todas", params={"skip": -1}).status_code
            == 422
        )

    def test_limit_cero_devuelve_422(self):
        client = TestClient(_app_con_overrides())
        assert (
            client.get("/actividad/obtener_todas", params={"limit": 0}).status_code
            == 422
        )

    def test_limit_superior_a_100_devuelve_422(self):
        client = TestClient(_app_con_overrides())
        assert (
            client.get("/actividad/obtener_todas", params={"limit": 101}).status_code
            == 422
        )


class TestObtenerTodasLogica:
    def test_devuelve_lista_paginada_de_actividades(self, monkeypatch):
        app = _app_con_overrides()

        async def fake_obtener(db, usuario_actual_id, skip, limit):
            return {
                "items": [_actividad_fake(id=1), _actividad_fake(id=2)],
                "total": 2,
                "skip": skip,
                "limit": limit,
                "has_more": False,
            }

        monkeypatch.setattr(activities_service, "obtener_actividades", fake_obtener)
        response = TestClient(app).get("/actividad/obtener_todas")
        assert response.status_code == 200

        body = response.json()
        assert len(body["items"]) == 2
        assert body["total"] == 2
        assert body["skip"] == 0
        assert body["limit"] == 20
        assert body["has_more"] is False

    def test_lista_vacia_devuelve_200_con_metadata(self, monkeypatch):
        app = _app_con_overrides()

        async def fake_obtener(db, usuario_actual_id, skip, limit):
            return {
                "items": [],
                "total": 0,
                "skip": skip,
                "limit": limit,
                "has_more": False,
            }

        monkeypatch.setattr(activities_service, "obtener_actividades", fake_obtener)
        response = TestClient(app).get("/actividad/obtener_todas")
        assert response.status_code == 200
        assert response.json() == {
            "items": [],
            "total": 0,
            "skip": 0,
            "limit": 20,
            "has_more": False,
        }

    def test_skip_y_limit_se_pasan_al_servicio(self, monkeypatch):
        app = _app_con_overrides()
        capturado = {}

        async def fake_obtener(db, usuario_actual_id, skip, limit):
            capturado["skip"] = skip
            capturado["limit"] = limit
            return {
                "items": [],
                "total": 0,
                "skip": skip,
                "limit": limit,
                "has_more": False,
            }

        monkeypatch.setattr(activities_service, "obtener_actividades", fake_obtener)
        TestClient(app).get(
            "/actividad/obtener_todas", params={"skip": 20, "limit": 10}
        )
        assert capturado == {"skip": 20, "limit": 10}

    def test_valores_por_defecto_skip_0_limit_20(self, monkeypatch):
        app = _app_con_overrides()
        capturado = {}

        async def fake_obtener(db, usuario_actual_id, skip, limit):
            capturado["skip"] = skip
            capturado["limit"] = limit
            return {
                "items": [],
                "total": 0,
                "skip": skip,
                "limit": limit,
                "has_more": False,
            }

        monkeypatch.setattr(activities_service, "obtener_actividades", fake_obtener)
        TestClient(app).get("/actividad/obtener_todas")
        assert capturado["skip"] == 0
        assert capturado["limit"] == 20

    def test_has_more_true_se_refleja_en_la_respuesta(self, monkeypatch):
        app = _app_con_overrides()

        async def fake_obtener(db, usuario_actual_id, skip, limit):
            return {
                "items": [_actividad_fake(id=1), _actividad_fake(id=2)],
                "total": 5,
                "skip": skip,
                "limit": limit,
                "has_more": True,
            }

        monkeypatch.setattr(activities_service, "obtener_actividades", fake_obtener)
        response = TestClient(app).get(
            "/actividad/obtener_todas", params={"skip": 0, "limit": 2}
        )
        assert response.status_code == 200
        assert response.json()["has_more"] is True


# ─────────────────────────────────────────────
# DELETE /actividad/borrar/{id_actividad}
# ─────────────────────────────────────────────


class TestBorrarActividadAppSession:
    def test_sin_app_session_devuelve_403(self):
        assert TestClient(_build_app()).delete("/actividad/borrar/1").status_code == 403


class TestBorrarActividadValidacion:
    def test_id_no_numerico_devuelve_422(self):
        assert (
            TestClient(_app_con_overrides()).delete("/actividad/borrar/abc").status_code
            == 422
        )


class TestBorrarActividadLogica:
    def test_borrar_exitoso_devuelve_200(self, monkeypatch):
        app = _app_con_overrides()

        async def fake_eliminar(db, usuario_actual_id, id_actividad):
            return {
                "estatus": "success",
                "mensaje": "Actividad eliminada",
                "nuevo_total_puntos": 3,
            }

        monkeypatch.setattr(activities_service, "eliminar_actividad", fake_eliminar)
        response = TestClient(app).delete("/actividad/borrar/1")
        assert response.status_code == 200
        body = response.json()
        assert body["estatus"] == "success"
        assert "nuevo_total_puntos" in body

    def test_actividad_no_encontrada_devuelve_404(self, monkeypatch):
        app = _app_con_overrides()

        async def fake_eliminar(db, usuario_actual_id, id_actividad):
            raise HTTPException(
                status_code=404, detail="Error: Actividad no encontrada"
            )

        monkeypatch.setattr(activities_service, "eliminar_actividad", fake_eliminar)
        response = TestClient(app).delete("/actividad/borrar/999")
        assert response.status_code == 404

    def test_id_se_pasa_correctamente_al_servicio(self, monkeypatch):
        app = _app_con_overrides()
        capturado = {}

        async def fake_eliminar(db, usuario_actual_id, id_actividad):
            capturado["id"] = id_actividad
            return {
                "estatus": "success",
                "mensaje": "Actividad eliminada",
                "nuevo_total_puntos": 0,
            }

        monkeypatch.setattr(activities_service, "eliminar_actividad", fake_eliminar)
        TestClient(app).delete("/actividad/borrar/42")
        assert capturado["id"] == 42


# ─────────────────────────────────────────────
# DELETE /actividad/borrar_todas
# ─────────────────────────────────────────────


class TestBorrarTodasAppSession:
    def test_sin_app_session_devuelve_403(self):
        assert (
            TestClient(_build_app()).delete("/actividad/borrar_todas").status_code
            == 403
        )


class TestBorrarTodasLogica:
    def test_borrar_todas_exitoso_devuelve_200(self, monkeypatch):
        app = _app_con_overrides()

        async def fake_eliminar(db, usuario_actual_id):
            return {
                "estatus": "success",
                "mensaje": "Historial de actividades eliminado correctamente. Se han borrado 5 actividades.",
            }

        monkeypatch.setattr(activities_service, "eliminar_actividades", fake_eliminar)
        response = TestClient(app).delete("/actividad/borrar_todas")
        assert response.status_code == 200
        assert response.json()["estatus"] == "success"

    def test_mensaje_incluye_numero_borradas(self, monkeypatch):
        app = _app_con_overrides()

        async def fake_eliminar(db, usuario_actual_id):
            return {
                "estatus": "success",
                "mensaje": "Historial de actividades eliminado correctamente. Se han borrado 3 actividades.",
            }

        monkeypatch.setattr(activities_service, "eliminar_actividades", fake_eliminar)
        response = TestClient(app).delete("/actividad/borrar_todas")
        assert "3" in response.json()["mensaje"]

    def test_sin_actividades_devuelve_cero_borradas(self, monkeypatch):
        app = _app_con_overrides()

        async def fake_eliminar(db, usuario_actual_id):
            return {
                "estatus": "success",
                "mensaje": "Historial de actividades eliminado correctamente. Se han borrado 0 actividades.",
            }

        monkeypatch.setattr(activities_service, "eliminar_actividades", fake_eliminar)
        response = TestClient(app).delete("/actividad/borrar_todas")
        assert "0" in response.json()["mensaje"]

    def test_usuario_no_encontrado_devuelve_404(self, monkeypatch):
        app = _app_con_overrides()

        async def fake_eliminar(db, usuario_actual_id):
            raise HTTPException(status_code=404, detail="Error: Usuario no encontrado")

        monkeypatch.setattr(activities_service, "eliminar_actividades", fake_eliminar)
        response = TestClient(app).delete("/actividad/borrar_todas")
        assert response.status_code == 404
