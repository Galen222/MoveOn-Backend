from fastapi import FastAPI
from fastapi.testclient import TestClient

from middlewares.request_context import RequestContextMiddleware
import middlewares.security_headers as security_headers_module
from middlewares.security_headers import SecurityHeadersMiddleware



def _build_request_id_app() -> FastAPI:
    app = FastAPI()
    app.add_middleware(RequestContextMiddleware)

    @app.get("/ping")
    async def ping():
        return {"ok": True}

    return app



def _build_security_headers_app() -> FastAPI:
    app = FastAPI()
    app.add_middleware(SecurityHeadersMiddleware)

    @app.get("/ping")
    async def ping():
        return {"ok": True}

    return app


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


class TestSecurityHeadersMiddleware:
    def test_añade_headers_y_hsts_en_https(self, monkeypatch):
        monkeypatch.setattr(security_headers_module.settings, "ENABLE_SECURITY_HEADERS", True)
        monkeypatch.setattr(security_headers_module.settings, "SEC_HEADERS_RESPECT_X_FORWARDED_PROTO", False)
        monkeypatch.setattr(security_headers_module.settings, "SEC_HEADERS_HSTS_SECONDS", 3600)
        monkeypatch.setattr(security_headers_module.settings, "SEC_HEADERS_HSTS_INCLUDE_SUBDOMAINS", True)
        monkeypatch.setattr(security_headers_module.settings, "SEC_HEADERS_HSTS_PRELOAD", False)
        monkeypatch.setattr(security_headers_module.settings, "SEC_HEADERS_X_FRAME_OPTIONS", "DENY")
        monkeypatch.setattr(security_headers_module.settings, "SEC_HEADERS_REFERRER_POLICY", "no-referrer")
        monkeypatch.setattr(security_headers_module.settings, "SEC_HEADERS_PERMISSIONS_POLICY", "geolocation=()")
        monkeypatch.setattr(security_headers_module.settings, "SEC_HEADERS_CONTENT_SECURITY_POLICY", "")

        client = TestClient(_build_security_headers_app(), base_url="https://testserver")
        response = client.get("/ping")

        assert response.status_code == 200
        assert response.headers["X-Content-Type-Options"] == "nosniff"
        assert response.headers["X-Frame-Options"] == "DENY"
        assert response.headers["Referrer-Policy"] == "no-referrer"
        assert response.headers["Permissions-Policy"] == "geolocation=()"
        assert "Strict-Transport-Security" in response.headers
        assert response.headers["Strict-Transport-Security"].startswith("max-age=3600")

    def test_no_añade_hsts_en_http(self, monkeypatch):
        monkeypatch.setattr(security_headers_module.settings, "ENABLE_SECURITY_HEADERS", True)
        monkeypatch.setattr(security_headers_module.settings, "SEC_HEADERS_RESPECT_X_FORWARDED_PROTO", False)
        monkeypatch.setattr(security_headers_module.settings, "SEC_HEADERS_HSTS_SECONDS", 3600)
        monkeypatch.setattr(security_headers_module.settings, "SEC_HEADERS_HSTS_INCLUDE_SUBDOMAINS", True)
        monkeypatch.setattr(security_headers_module.settings, "SEC_HEADERS_HSTS_PRELOAD", False)
        monkeypatch.setattr(security_headers_module.settings, "SEC_HEADERS_X_FRAME_OPTIONS", "DENY")
        monkeypatch.setattr(security_headers_module.settings, "SEC_HEADERS_REFERRER_POLICY", "no-referrer")
        monkeypatch.setattr(security_headers_module.settings, "SEC_HEADERS_PERMISSIONS_POLICY", "geolocation=()")
        monkeypatch.setattr(security_headers_module.settings, "SEC_HEADERS_CONTENT_SECURITY_POLICY", "")

        client = TestClient(_build_security_headers_app(), base_url="http://testserver")
        response = client.get("/ping")

        assert response.status_code == 200
        assert "Strict-Transport-Security" not in response.headers
        assert response.headers["X-Content-Type-Options"] == "nosniff"
