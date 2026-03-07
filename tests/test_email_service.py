# tests/test_email_service.py
#
# Tests para services/email_service.py.
# Mockeamos aiosmtplib.send para no necesitar un servidor SMTP real.
# Verificamos: construcción del mensaje, envío exitoso, fallo silencioso.

import pytest
from unittest.mock import patch, AsyncMock, MagicMock

from services import email_service


# ─────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────

def _patch_logo_no_existe():
    """Simula que el logo NO existe en disco para simplificar los tests."""
    return patch("services.email_service.Path.exists", return_value=False)


def _patch_logo_existe(contenido: bytes = b"\x89PNG\r\n"):
    """Simula que el logo SÍ existe y devuelve bytes fake."""
    mock_open = MagicMock()
    mock_open.return_value.__enter__ = MagicMock(
        return_value=MagicMock(read=MagicMock(return_value=contenido))
    )
    mock_open.return_value.__exit__ = MagicMock(return_value=False)

    return (
        patch("services.email_service.Path.exists", return_value=True),
        patch("builtins.open", mock_open),
    )


# ─────────────────────────────────────────────
# Envío exitoso
# ─────────────────────────────────────────────

class TestEnvioExitoso:
    @pytest.mark.asyncio
    async def test_retorna_true_si_envio_ok(self):
        with _patch_logo_no_existe(), \
             patch("aiosmtplib.send", new_callable=AsyncMock) as mock_send:
            resultado = await email_service.enviar_codigo_recuperacion(
                "user@example.com", "123456", 15
            )
        assert resultado is True
        mock_send.assert_called_once()

    @pytest.mark.asyncio
    async def test_mensaje_contiene_destinatario(self):
        mensajes_enviados = []

        async def capturar_send(msg, **kwargs):
            mensajes_enviados.append(msg)

        with _patch_logo_no_existe(), \
             patch("aiosmtplib.send", side_effect=capturar_send):
            await email_service.enviar_codigo_recuperacion(
                "victima@test.com", "999999", 10
            )

        assert len(mensajes_enviados) == 1
        msg = mensajes_enviados[0]
        assert msg["To"] == "victima@test.com"

    @pytest.mark.asyncio
    async def test_mensaje_contiene_subject_correcto(self):
        mensajes_enviados = []

        async def capturar_send(msg, **kwargs):
            mensajes_enviados.append(msg)

        with _patch_logo_no_existe(), \
             patch("aiosmtplib.send", side_effect=capturar_send):
            await email_service.enviar_codigo_recuperacion(
                "user@test.com", "123456", 15
            )

        msg = mensajes_enviados[0]
        assert "recuperación" in msg["Subject"].lower() or "MoveOn" in msg["Subject"]

    @pytest.mark.asyncio
    async def test_mensaje_contiene_from_con_moveon(self):
        mensajes_enviados = []

        async def capturar_send(msg, **kwargs):
            mensajes_enviados.append(msg)

        with _patch_logo_no_existe(), \
             patch("aiosmtplib.send", side_effect=capturar_send):
            await email_service.enviar_codigo_recuperacion(
                "user@test.com", "123456", 15
            )

        msg = mensajes_enviados[0]
        assert "MoveOn" in msg["From"]

    @pytest.mark.asyncio
    async def test_cuerpo_texto_plano_contiene_codigo(self):
        mensajes_enviados = []

        async def capturar_send(msg, **kwargs):
            mensajes_enviados.append(msg)

        with _patch_logo_no_existe(), \
             patch("aiosmtplib.send", side_effect=capturar_send):
            await email_service.enviar_codigo_recuperacion(
                "user@test.com", "654321", 15
            )

        msg = mensajes_enviados[0]
        # get_body con preferencelist=("plain",) devuelve la parte de texto plano
        texto_plano = msg.get_body(preferencelist=("plain",))
        assert texto_plano is not None
        contenido = texto_plano.get_content()
        assert "654321" in contenido

    @pytest.mark.asyncio
    async def test_mensaje_tiene_parte_html(self):
        mensajes_enviados = []

        async def capturar_send(msg, **kwargs):
            mensajes_enviados.append(msg)

        with _patch_logo_no_existe(), \
             patch("aiosmtplib.send", side_effect=capturar_send):
            await email_service.enviar_codigo_recuperacion(
                "user@test.com", "123456", 15
            )

        msg = mensajes_enviados[0]
        html_part = msg.get_body(preferencelist=("html",))
        assert html_part is not None

    @pytest.mark.asyncio
    async def test_smtp_recibe_start_tls_true(self):
        kwargs_capturados = {}

        async def capturar_send(msg, **kwargs):
            kwargs_capturados.update(kwargs)

        with _patch_logo_no_existe(), \
             patch("aiosmtplib.send", side_effect=capturar_send):
            await email_service.enviar_codigo_recuperacion(
                "user@test.com", "123456", 15
            )

        assert kwargs_capturados.get("start_tls") is True


# ─────────────────────────────────────────────
# Fallo de envío
# ─────────────────────────────────────────────

class TestFalloEnvio:
    @pytest.mark.asyncio
    async def test_retorna_false_si_smtp_falla(self):
        with _patch_logo_no_existe(), \
             patch("aiosmtplib.send", new_callable=AsyncMock, side_effect=Exception("timeout")):
            resultado = await email_service.enviar_codigo_recuperacion(
                "user@example.com", "123456", 15
            )
        assert resultado is False

    @pytest.mark.asyncio
    async def test_no_propaga_excepcion_smtp(self):
        """El fallo SMTP no debe propagarse al caller (se usa en background_task)."""
        with _patch_logo_no_existe(), \
             patch("aiosmtplib.send", new_callable=AsyncMock, side_effect=ConnectionRefusedError()):
            resultado = await email_service.enviar_codigo_recuperacion(
                "user@example.com", "123456", 15
            )
        assert resultado is False


# ─────────────────────────────────────────────
# Logo inline
# ─────────────────────────────────────────────

class TestLogoInline:
    @pytest.mark.asyncio
    async def test_sin_logo_no_explota(self):
        """Si el logo no existe en disco, el email se envía igual sin imagen inline."""
        with _patch_logo_no_existe(), \
             patch("aiosmtplib.send", new_callable=AsyncMock):
            resultado = await email_service.enviar_codigo_recuperacion(
                "user@test.com", "123456", 15
            )
        assert resultado is True

    @pytest.mark.asyncio
    async def test_con_logo_se_envia_ok(self):
        """Si el logo existe, se adjunta como related y el envío funciona."""
        ctx_exists, ctx_open = _patch_logo_existe(b"\x89PNG\r\nfake_image_data")

        with ctx_exists, ctx_open, \
             patch("aiosmtplib.send", new_callable=AsyncMock):
            resultado = await email_service.enviar_codigo_recuperacion(
                "user@test.com", "123456", 15
            )
        assert resultado is True
        