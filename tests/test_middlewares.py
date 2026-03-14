# tests/test_middlewares.py
#
# Sustituye a: test_middlewares_request_id_security.py
#
# Cubre los dos middlewares de infraestructura:
#   - RequestContextMiddleware  (middlewares/request_context.py)
#   - SecurityHeadersMiddleware (middlewares/security_headers.py)

import logging
import uuid
from contextlib import contextmanager

import middlewares.security_headers as security_headers_module
from fastapi import FastAPI
from fastapi.testclient import TestClient
from middlewares.request_context import RequestContextMiddleware
from middlewares.security_headers import SecurityHeadersMiddleware


# ─────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────


def _build_request_id_app() -> FastAPI:
    app = FastAPI()
    app.add_middleware(RequestContextMiddleware)

    @app.get("/ping")
    async def ping():
        return {"ok": True}

    return app


def _build_request_id_error_app() -> FastAPI:
    app = FastAPI()
    app.add_middleware(RequestContextMiddleware)

    @app.get("/boom")
    async def boom():
        raise RuntimeError("boom")

    return app


def _build_security_headers_app() -> FastAPI:
    app = FastAPI()
    app.add_middleware(SecurityHeadersMiddleware)

    @app.get("/ping")
    async def ping():
        return {"ok": True}

    return app


def _sec_monkeypatch(monkeypatch, **overrides):
    """Aplica valores por defecto razonables y sobreescribe los indicados."""
    defaults = {
        "ENABLE_SECURITY_HEADERS": True,
        "SEC_HEADERS_RESPECT_X_FORWARDED_PROTO": False,
        "SEC_HEADERS_HSTS_SECONDS": 3600,
        "SEC_HEADERS_HSTS_INCLUDE_SUBDOMAINS": True,
        "SEC_HEADERS_HSTS_PRELOAD": False,
        "SEC_HEADERS_X_FRAME_OPTIONS": "DENY",
        "SEC_HEADERS_REFERRER_POLICY": "no-referrer",
        "SEC_HEADERS_PERMISSIONS_POLICY": "geolocation=()",
        "SEC_HEADERS_CONTENT_SECURITY_POLICY": "",
    }
    defaults.update(overrides)
    for key, value in defaults.items():
        monkeypatch.setattr(security_headers_module.settings, key, value)


@contextmanager
def _capture_logger(caplog, logger_name: str, level: int):
    logger = logging.getLogger(logger_name)
    old_level = logger.level

    caplog.clear()
    logger.addHandler(caplog.handler)
    logger.setLevel(level)

    try:
        yield logger
    finally:
        logger.removeHandler(caplog.handler)
        logger.setLevel(old_level)


# ─────────────────────────────────────────────
# RequestContextMiddleware
# ─────────────────────────────────────────────


class TestRequestIdMiddleware:
    def test_inyecta_x_request_id_si_no_llega(self):
        client = TestClient(_build_request_id_app())
        response = client.get("/ping")

        assert response.status_code == 200
        assert "X-Request-ID" in response.headers
        assert response.headers["X-Request-ID"]

    def test_respeta_x_request_id_si_llega_en_request(self):
        client = TestClient(_build_request_id_app())
        response = client.get("/ping", headers={"X-Request-ID": "req-123"})

        assert response.status_code == 200
        assert response.headers["X-Request-ID"] == "req-123"

    def test_x_request_id_generado_es_uuid_valido(self):
        """Cuando no se envía cabecera, el ID generado debe ser un UUID válido."""
        client = TestClient(_build_request_id_app())
        response = client.get("/ping")

        request_id = response.headers["X-Request-ID"]
        parsed = uuid.UUID(request_id)
        assert str(parsed) == request_id

    def test_requests_distintos_generan_ids_distintos(self):
        """Cada request sin X-Request-ID debe recibir un ID único."""
        client = TestClient(_build_request_id_app())
        ids = {client.get("/ping").headers["X-Request-ID"] for _ in range(5)}
        assert len(ids) == 5

    def test_x_request_id_se_devuelve_en_cabecera_respuesta(self):
        """El ID proporcionado por el cliente debe aparecer en la respuesta."""
        client = TestClient(_build_request_id_app())
        response = client.get("/ping", headers={"X-Request-ID": "mi-id-custom"})

        assert response.headers["X-Request-ID"] == "mi-id-custom"


class TestRequestIdMiddlewareLogging:
    def test_loggea_request_completed_con_campos_estructurados(self, caplog):
        client = TestClient(_build_request_id_app())

        with _capture_logger(caplog, "app.request", logging.INFO):
            response = client.get("/ping", headers={"X-Request-ID": "req-123"})

        assert response.status_code == 200

        record = next(r for r in caplog.records if r.name == "app.request")
        assert record.getMessage() == "peticion_completada"
        assert record.request_id == "req-123"
        assert record.method == "GET"
        assert record.path == "/ping"
        assert record.status_code == 200
        assert isinstance(record.duration_ms, int)

    def test_loggea_request_failed_con_campos_estructurados(self, caplog):
        client = TestClient(
            _build_request_id_error_app(), raise_server_exceptions=False
        )

        with _capture_logger(caplog, "app.request", logging.ERROR):
            response = client.get("/boom", headers={"X-Request-ID": "req-err"})

        assert response.status_code == 500

        record = next(r for r in caplog.records if r.name == "app.request")
        assert record.getMessage() == "peticion_fallida"
        assert record.request_id == "req-err"
        assert record.method == "GET"
        assert record.path == "/boom"
        assert record.status_code == 500
        assert isinstance(record.duration_ms, int)


# ─────────────────────────────────────────────
# SecurityHeadersMiddleware — desactivado
# ─────────────────────────────────────────────


class TestSecurityHeadersDesactivado:
    def test_no_añade_headers_cuando_desactivado(self, monkeypatch):
        _sec_monkeypatch(monkeypatch, ENABLE_SECURITY_HEADERS=False)

        client = TestClient(
            _build_security_headers_app(), base_url="https://testserver"
        )
        response = client.get("/ping")

        assert response.status_code == 200
        assert "X-Content-Type-Options" not in response.headers
        assert "X-Frame-Options" not in response.headers
        assert "Strict-Transport-Security" not in response.headers


# ─────────────────────────────────────────────
# SecurityHeadersMiddleware — headers base
# ─────────────────────────────────────────────


class TestSecurityHeadersBase:
    def test_añade_headers_y_hsts_en_https(self, monkeypatch):
        _sec_monkeypatch(monkeypatch)

        client = TestClient(
            _build_security_headers_app(), base_url="https://testserver"
        )
        response = client.get("/ping")

        assert response.status_code == 200
        assert response.headers["X-Content-Type-Options"] == "nosniff"
        assert response.headers["X-Frame-Options"] == "DENY"
        assert response.headers["Referrer-Policy"] == "no-referrer"
        assert response.headers["Permissions-Policy"] == "geolocation=()"
        assert "Strict-Transport-Security" in response.headers

    def test_no_añade_hsts_en_http(self, monkeypatch):
        _sec_monkeypatch(monkeypatch)

        client = TestClient(_build_security_headers_app(), base_url="http://testserver")
        response = client.get("/ping")

        assert response.status_code == 200
        assert "Strict-Transport-Security" not in response.headers
        assert response.headers["X-Content-Type-Options"] == "nosniff"

    def test_x_frame_options_configurable(self, monkeypatch):
        _sec_monkeypatch(monkeypatch, SEC_HEADERS_X_FRAME_OPTIONS="SAMEORIGIN")

        client = TestClient(
            _build_security_headers_app(), base_url="https://testserver"
        )
        response = client.get("/ping")

        assert response.headers["X-Frame-Options"] == "SAMEORIGIN"

    def test_referrer_policy_configurable(self, monkeypatch):
        _sec_monkeypatch(monkeypatch, SEC_HEADERS_REFERRER_POLICY="strict-origin")

        client = TestClient(
            _build_security_headers_app(), base_url="https://testserver"
        )
        response = client.get("/ping")

        assert response.headers["Referrer-Policy"] == "strict-origin"


# ─────────────────────────────────────────────
# SecurityHeadersMiddleware — HSTS variantes
# ─────────────────────────────────────────────


class TestSecurityHeadersHSTS:
    def test_hsts_incluye_max_age(self, monkeypatch):
        _sec_monkeypatch(monkeypatch, SEC_HEADERS_HSTS_SECONDS=31536000)

        client = TestClient(
            _build_security_headers_app(), base_url="https://testserver"
        )
        hsts = client.get("/ping").headers["Strict-Transport-Security"]

        assert "max-age=31536000" in hsts

    def test_hsts_include_subdomains(self, monkeypatch):
        _sec_monkeypatch(monkeypatch, SEC_HEADERS_HSTS_INCLUDE_SUBDOMAINS=True)

        client = TestClient(
            _build_security_headers_app(), base_url="https://testserver"
        )
        hsts = client.get("/ping").headers["Strict-Transport-Security"]

        assert "includeSubDomains" in hsts

    def test_hsts_sin_include_subdomains(self, monkeypatch):
        _sec_monkeypatch(monkeypatch, SEC_HEADERS_HSTS_INCLUDE_SUBDOMAINS=False)

        client = TestClient(
            _build_security_headers_app(), base_url="https://testserver"
        )
        hsts = client.get("/ping").headers["Strict-Transport-Security"]

        assert "includeSubDomains" not in hsts

    def test_hsts_con_preload(self, monkeypatch):
        _sec_monkeypatch(monkeypatch, SEC_HEADERS_HSTS_PRELOAD=True)

        client = TestClient(
            _build_security_headers_app(), base_url="https://testserver"
        )
        hsts = client.get("/ping").headers["Strict-Transport-Security"]

        assert "preload" in hsts

    def test_hsts_sin_preload(self, monkeypatch):
        _sec_monkeypatch(monkeypatch, SEC_HEADERS_HSTS_PRELOAD=False)

        client = TestClient(
            _build_security_headers_app(), base_url="https://testserver"
        )
        hsts = client.get("/ping").headers["Strict-Transport-Security"]

        assert "preload" not in hsts

    def test_hsts_no_aparece_si_seconds_es_cero(self, monkeypatch):
        _sec_monkeypatch(monkeypatch, SEC_HEADERS_HSTS_SECONDS=0)

        client = TestClient(
            _build_security_headers_app(), base_url="https://testserver"
        )
        response = client.get("/ping")

        assert "Strict-Transport-Security" not in response.headers


# ─────────────────────────────────────────────
# SecurityHeadersMiddleware — Content-Security-Policy
# ─────────────────────────────────────────────


class TestSecurityHeadersCSP:
    def test_csp_no_aparece_si_vacio(self, monkeypatch):
        _sec_monkeypatch(monkeypatch, SEC_HEADERS_CONTENT_SECURITY_POLICY="")

        client = TestClient(
            _build_security_headers_app(), base_url="https://testserver"
        )
        response = client.get("/ping")

        assert "Content-Security-Policy" not in response.headers

    def test_csp_aparece_cuando_configurado(self, monkeypatch):
        politica = "default-src 'self'; img-src *"
        _sec_monkeypatch(monkeypatch, SEC_HEADERS_CONTENT_SECURITY_POLICY=politica)

        client = TestClient(
            _build_security_headers_app(), base_url="https://testserver"
        )
        response = client.get("/ping")

        assert response.headers["Content-Security-Policy"] == politica
