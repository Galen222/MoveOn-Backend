# tests/test_router_activities.py

"""Contiene pruebas automatizadas de este módulo."""

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


def _build_app() -> FastAPI:
    """Construye la aplicación de prueba."""
    app = FastAPI()
    app.include_router(activities_router)
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
    return app


async def _fake_db():
    """Crea un simulacro de base de datos."""
    return None


def _app() -> FastAPI:
    """Gestiona app."""
    app = _build_app()
    app.dependency_overrides[obtener_db] = _fake_db
    app.dependency_overrides[auth.verificar_sesion_aplicacion] = lambda: "ok"
    app.dependency_overrides[auth.obtener_usuario_actual] = lambda: 1
    return app


def _payload(**kwargs):
    """Gestiona payload."""
    # Gestiona carga útil.
    base = {
        "tipo": "Correr",
        "distancia": 5000,
        "duracion_total": 1800,
        "duracion_movimiento": 1680,
        "duracion_parado": 120,
        "duracion_pausa_manual": 60,
        "calorias_quemadas": 350,
        "ritmo_medio_movimiento": 336,
        "ritmo_medio_total": 360,
        "ritmo_maximo": 290,
        "velocidad_media_x100": 1071,
        "velocidad_max_x100": 1840,
        "auto_pausas": 1,
        "pausas_manuales": 1,
        "alertas_velocidad": 0,
        "fecha_ruta": "2024-06-01T10:00:00Z",
    }
    base.update(kwargs)
    return base


def _actividad_fake(**kwargs):
    """Gestiona actividad fake."""
    # Gestiona actividad fake.
    base = {
        "id": 1,
        "tipo": "Correr",
        "distancia": 5000,
        "duracion_total": 1800,
        "duracion_movimiento": 1680,
        "duracion_parado": 120,
        "duracion_pausa_manual": 60,
        "calorias_quemadas": 350,
        "ritmo_medio_movimiento": 336,
        "ritmo_medio_total": 360,
        "ritmo_maximo": 290,
        "velocidad_media_x100": 1071,
        "velocidad_max_x100": 1840,
        "auto_pausas": 1,
        "pausas_manuales": 1,
        "alertas_velocidad": 0,
        "ruta_polilinea": None,
        "ruta_mapa_url": None,
        "fecha_ruta": datetime(2024, 6, 1, 10, 0, 0, tzinfo=timezone.utc),
        "nuevo_total_puntos": 25,
    }
    base.update(kwargs)
    return SimpleNamespace(**base)


class TestGuardarActividadRouter:
    """Agrupa pruebas relacionadas con guardar actividad router."""

    def test_validacion_breakdown_422(self):
        """Verifica que validacion breakdown 422."""
        client = TestClient(_app())
        response = client.post("/actividad/guardar", json=_payload(duracion_parado=100))
        assert response.status_code == 422

    def test_guardar_ok_expone_nuevos_campos(self, monkeypatch):
        """Verifica que guardar ok expone nuevos campos."""

        # Verifica que guardar ok expone nuevos campos.
        async def _fake_guardar(db, usuario_id, datos):
            """Crea un simulacro de guardar."""
            return _actividad_fake().__dict__

        monkeypatch.setattr(activities_service, "crear_actividad", _fake_guardar)
        client = TestClient(_app())
        response = client.post("/actividad/guardar", json=_payload())
        assert response.status_code == 200
        body = response.json()
        assert body["duracion_total"] == 1800
        assert body["duracion_movimiento"] == 1680
        assert body["ritmo_medio_total"] == 360
        assert body["ritmo_maximo"] == 290
        assert body["velocidad_max_x100"] == 1840
