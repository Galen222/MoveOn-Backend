# tests/test_main.py

"""Comprueba los endpoints de salud y arranque expuestos por FastAPI.

La suite protege la disponibilidad mínima del servicio, incluyendo root,
favicon y checks ``healthz``/``readyz``.
"""

import pytest
from fastapi.testclient import TestClient

from main import app
import database
from config import settings


async def _async_noop(*args, **kwargs):
    """Gestiona async noop."""
    return None


@pytest.fixture
def client(monkeypatch):
    """Gestiona client."""
    monkeypatch.setattr(database, "init_db", _async_noop)
    monkeypatch.setattr(database, "close_db", _async_noop)
    monkeypatch.setattr(settings, "AUTO_CREATE_TABLES", False)

    # Evita que el lifespan vuelva a montar /imagenes en cada test
    monkeypatch.setattr(settings, "STORAGE_TYPE", "cloudinary")

    app.dependency_overrides.clear()
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


def test_root_devuelve_200_y_estado_en_linea(client):
    """Verifica que root devuelve 200 y estado en linea."""
    response = client.get("/")
    assert response.status_code == 200
    assert response.json() == {
        "estado": "en linea",
        "aplicacion": "MoveOn API",
    }


def test_favicon_devuelve_200_si_existe(client, tmp_path, monkeypatch):
    """Verifica que favicon devuelve 200 si existe."""
    favicon_path = tmp_path / "favicon.ico"
    favicon_path.write_bytes(b"\x00\x00\x01\x00")

    monkeypatch.chdir(tmp_path)

    response = client.get("/favicon.ico")
    assert response.status_code == 200


def test_healthz_devuelve_200(client):
    """Verifica que healthz devuelve 200."""
    response = client.get("/healthz")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_readyz_devuelve_200_si_bd_ok(client):
    """Verifica que readyz devuelve 200 si bd ok."""

    class FakeDB:
        """Representa fake base de datos."""

        async def execute(self, query):
            """Gestiona execute."""
            return 1

    app.dependency_overrides[database.obtener_db] = lambda: FakeDB()

    response = client.get("/readyz")
    assert response.status_code == 200
    assert response.json() == {"status": "ready", "database": "ok"}


def test_readyz_devuelve_503_si_bd_falla(client):
    """Verifica que readyz devuelve 503 si bd falla."""

    class FakeDB:
        """Representa fake base de datos."""

        async def execute(self, query):
            """Gestiona execute."""
            raise Exception("db down")

    app.dependency_overrides[database.obtener_db] = lambda: FakeDB()

    response = client.get("/readyz")
    assert response.status_code == 503
    assert response.json() == {"status": "not_ready", "database": "error"}
