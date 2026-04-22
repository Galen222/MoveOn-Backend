# tests/test_ip_rate_limit.py

"""Valida la extracción robusta de IP cliente detrás de proxies de confianza.

Se cubren cabeceras reenviadas, conexiones directas y casos ambiguos para
que el rate limit no dependa de entradas mal formadas.
"""

# Pruebas para ip_rate_limit.py.
# Cubre: detección de proxy confiable (LAN/WAN), extracción de IP
# desde headers y resolución final de get_client_ip.

# Estrategia: parchear los módulo-level globals (LAN_NETS, WAN_NETS, WAN_IPS)
# y settings en lugar de importar con variables de entorno alternativas,
# para no depender del orden de importación de pytest.

from ipaddress import ip_network
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import ip_rate_limit

# ─────────────────────────────────────────────
# Ayudante
# ─────────────────────────────────────────────


class FakeRequest:
    """
    Simulacro mínimo de Starlette Request para ip_rate_limit.
    Solo necesita .client.host y .headers (dict con .get).
    """

    def __init__(self, host: str, headers: dict | None = None):
        """Inicializa la instancia."""
        self.client = SimpleNamespace(host=host)
        self.headers = headers or {}


# ─────────────────────────────────────────────
# conn_from_trusted_proxy
# ─────────────────────────────────────────────


class TestConnFromTrustedProxy:
    """Agrupa pruebas relacionadas con conn from trusted proxy."""

    def test_sin_proxy_configurado_retorna_false(self):
        """Verifica que sin proxy configurado retorna false."""
        request = FakeRequest("1.2.3.4")
        with patch.object(
            ip_rate_limit.settings, "TRUST_PROXY_LAN", False
        ), patch.object(ip_rate_limit.settings, "TRUST_PROXY_WAN", False):
            assert ip_rate_limit.conn_from_trusted_proxy(request) is False  # type: ignore[arg-type]

    def test_ip_en_red_lan_confiable_retorna_true(self):
        """Verifica que IP en red lan confiable retorna true."""
        request = FakeRequest("192.168.1.50")
        with patch.object(ip_rate_limit.settings, "TRUST_PROXY_LAN", True), patch(
            "ip_rate_limit.LAN_NETS", [ip_network("192.168.0.0/16")]
        ), patch.object(ip_rate_limit.settings, "TRUST_PROXY_WAN", False):
            assert ip_rate_limit.conn_from_trusted_proxy(request) is True  # type: ignore[arg-type]

    def test_ip_fuera_de_red_lan_retorna_false(self):
        """Verifica que IP fuera de red lan retorna false."""
        request = FakeRequest("10.0.0.1")
        with patch.object(ip_rate_limit.settings, "TRUST_PROXY_LAN", True), patch(
            "ip_rate_limit.LAN_NETS", [ip_network("192.168.0.0/16")]
        ), patch.object(ip_rate_limit.settings, "TRUST_PROXY_WAN", False):
            assert ip_rate_limit.conn_from_trusted_proxy(request) is False  # type: ignore[arg-type]

    def test_ip_wan_exacta_en_whitelist_retorna_true(self):
        """Verifica que IP wan exacta en whitelist retorna true."""
        request = FakeRequest("203.0.113.10")
        with patch.object(
            ip_rate_limit.settings, "TRUST_PROXY_LAN", False
        ), patch.object(ip_rate_limit.settings, "TRUST_PROXY_WAN", True), patch(
            "ip_rate_limit.WAN_IPS", {"203.0.113.10"}
        ), patch(
            "ip_rate_limit.WAN_NETS", []
        ):
            assert ip_rate_limit.conn_from_trusted_proxy(request) is True  # type: ignore[arg-type]

    def test_ip_wan_en_cidr_retorna_true(self):
        """Verifica que IP wan en cidr retorna true."""
        request = FakeRequest("198.51.100.5")
        with patch.object(
            ip_rate_limit.settings, "TRUST_PROXY_LAN", False
        ), patch.object(ip_rate_limit.settings, "TRUST_PROXY_WAN", True), patch(
            "ip_rate_limit.WAN_IPS", set()
        ), patch(
            "ip_rate_limit.WAN_NETS", [ip_network("198.51.100.0/24")]
        ):
            assert ip_rate_limit.conn_from_trusted_proxy(request) is True  # type: ignore[arg-type]

    def test_ip_wan_fuera_de_cidr_retorna_false(self):
        """Verifica que IP wan fuera de cidr retorna false."""
        request = FakeRequest("1.1.1.1")
        with patch.object(
            ip_rate_limit.settings, "TRUST_PROXY_LAN", False
        ), patch.object(ip_rate_limit.settings, "TRUST_PROXY_WAN", True), patch(
            "ip_rate_limit.WAN_IPS", set()
        ), patch(
            "ip_rate_limit.WAN_NETS", [ip_network("198.51.100.0/24")]
        ):
            assert ip_rate_limit.conn_from_trusted_proxy(request) is False  # type: ignore[arg-type]

    def test_sin_client_retorna_false(self):
        """Si request.client es None (conexión rara), no debe explotar."""
        request = MagicMock()
        request.client = None
        with patch.object(ip_rate_limit.settings, "TRUST_PROXY_LAN", True):
            assert ip_rate_limit.conn_from_trusted_proxy(request) is False  # type: ignore[arg-type]

    def test_ip_invalida_en_client_retorna_false(self):
        """Si request.client.host no es una IP válida, no debe explotar."""
        request = FakeRequest("no-es-una-ip")
        with patch.object(ip_rate_limit.settings, "TRUST_PROXY_LAN", True), patch(
            "ip_rate_limit.LAN_NETS", [ip_network("192.168.0.0/16")]
        ):
            assert ip_rate_limit.conn_from_trusted_proxy(request) is False  # type: ignore[arg-type]


# ─────────────────────────────────────────────
# _extract_ip_from_headers
# ─────────────────────────────────────────────


class TestExtractIpFromHeaders:
    """Agrupa pruebas relacionadas con extract IP from headers."""

    def test_extrae_primera_ip_de_x_forwarded_for_lista(self):
        """X-Forwarded-For puede llegar con múltiples IPs separadas por coma."""
        request = FakeRequest(
            "proxy", headers={"x-forwarded-for": "1.2.3.4, 5.6.7.8, 9.9.9.9"}
        )
        with patch("ip_rate_limit.HEADER_ORDER", ["x-forwarded-for"]):
            ip = ip_rate_limit._extract_ip_from_headers(request)  # type: ignore[arg-type]
        assert ip == "1.2.3.4"

    def test_extrae_ip_de_x_real_ip(self):
        """Verifica que extrae IP de x real IP."""
        request = FakeRequest("proxy", headers={"x-real-ip": "9.9.9.9"})
        with patch("ip_rate_limit.HEADER_ORDER", ["x-real-ip"]):
            ip = ip_rate_limit._extract_ip_from_headers(request)  # type: ignore[arg-type]
        assert ip == "9.9.9.9"

    def test_prioridad_sigue_el_orden_configurado(self):
        """Si hay dos headers, usa el primero en HEADER_ORDER."""
        headers = {
            "x-forwarded-for": "1.1.1.1",
            "x-real-ip": "2.2.2.2",
        }
        request = FakeRequest("proxy", headers=headers)
        with patch("ip_rate_limit.HEADER_ORDER", ["x-real-ip", "x-forwarded-for"]):
            ip = ip_rate_limit._extract_ip_from_headers(request)  # type: ignore[arg-type]
        assert ip == "2.2.2.2"

    def test_sin_headers_retorna_none(self):
        """Verifica que sin headers retorna none."""
        request = FakeRequest("proxy", headers={})
        with patch("ip_rate_limit.HEADER_ORDER", ["x-forwarded-for", "x-real-ip"]):
            ip = ip_rate_limit._extract_ip_from_headers(request)  # type: ignore[arg-type]
        assert ip is None

    def test_ip_invalida_en_header_la_ignora_y_prueba_siguiente(self):
        """Si el primer header tiene IP inválida, debe probar el siguiente."""
        headers = {
            "x-forwarded-for": "no-es-ip",
            "x-real-ip": "5.5.5.5",
        }
        request = FakeRequest("proxy", headers=headers)
        with patch("ip_rate_limit.HEADER_ORDER", ["x-forwarded-for", "x-real-ip"]):
            ip = ip_rate_limit._extract_ip_from_headers(request)  # type: ignore[arg-type]
        assert ip == "5.5.5.5"

    def test_todos_los_headers_invalidos_retorna_none(self):
        """Verifica que todos los headers invalidos retorna none."""
        request = FakeRequest("proxy", headers={"x-forwarded-for": "basura"})
        with patch("ip_rate_limit.HEADER_ORDER", ["x-forwarded-for"]):
            ip = ip_rate_limit._extract_ip_from_headers(request)  # type: ignore[arg-type]
        assert ip is None


# ─────────────────────────────────────────────
# get_client_ip
# ─────────────────────────────────────────────


class TestGetClientIp:
    """Agrupa pruebas relacionadas con get client IP."""

    def test_sin_proxy_usa_ip_del_socket(self):
        """Si no es proxy confiable, se ignoran los headers y se usa el socket."""
        request = FakeRequest("1.2.3.4", headers={"x-forwarded-for": "5.5.5.5"})
        with patch("ip_rate_limit.conn_from_trusted_proxy", return_value=False):
            ip = ip_rate_limit.get_client_ip(request)  # type: ignore[arg-type]
        assert ip == "1.2.3.4"

    def test_con_proxy_confiable_usa_header(self):
        """Si la conexión viene de un proxy de confianza, usa XFF."""
        request = FakeRequest("10.0.0.1", headers={"x-forwarded-for": "5.5.5.5"})
        with patch("ip_rate_limit.conn_from_trusted_proxy", return_value=True), patch(
            "ip_rate_limit.HEADER_ORDER", ["x-forwarded-for"]
        ):
            ip = ip_rate_limit.get_client_ip(request)  # type: ignore[arg-type]
        assert ip == "5.5.5.5"

    def test_con_proxy_sin_header_cae_a_socket(self):
        """
        Si la conexión es de proxy confiable pero no hay headers XFF,
        se usa la IP del socket (fallback seguro).
        """
        request = FakeRequest("10.0.0.1", headers={})
        with patch("ip_rate_limit.conn_from_trusted_proxy", return_value=True), patch(
            "ip_rate_limit.HEADER_ORDER", ["x-forwarded-for"]
        ):
            ip = ip_rate_limit.get_client_ip(request)  # type: ignore[arg-type]
        assert ip == "10.0.0.1"
