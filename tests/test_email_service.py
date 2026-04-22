# tests/test_email_service.py

"""Cubre la construcción y el envío de correos transaccionales del backend.

Revisa clasificación de errores SMTP, composición de mensajes y flujos de
recuperación tanto clásica como asociada a inicio de sesión con Google.
"""

import logging
from contextlib import contextmanager
from email.message import EmailMessage
from unittest.mock import AsyncMock, mock_open, patch

import pytest
from aiosmtplib.errors import (
    SMTPAuthenticationError,
    SMTPConnectError,
    SMTPRecipientRefused,
    SMTPRecipientsRefused,
    SMTPResponseException,
    SMTPServerDisconnected,
    SMTPTimeoutError,
)

from services import email_service


def _configurar_settings(monkeypatch):
    """Gestiona configurar configuración."""
    monkeypatch.setattr(email_service.settings, "EMAIL_HOST", "smtp.example.com")
    monkeypatch.setattr(email_service.settings, "EMAIL_PORT", 587)
    monkeypatch.setattr(email_service.settings, "EMAIL_USER", "test@example.com")
    monkeypatch.setattr(email_service.settings, "EMAIL_PASS", "test-pass")
    monkeypatch.setattr(email_service.settings, "EMAIL_TIMEOUT_SECONDS", 10.0)
    monkeypatch.setattr(email_service.settings, "EMAIL_MAX_RETRIES", 3)
    monkeypatch.setattr(
        email_service.settings,
        "EMAIL_RETRY_BASE_DELAY_SECONDS",
        1.0,
    )


def _extraer_html(msg: EmailMessage) -> str:
    """Gestiona extraer html."""
    html_part = msg.get_body(preferencelist=("html",))
    assert html_part is not None
    html = html_part.get_content()
    assert isinstance(html, str)
    return html


@contextmanager
def _capture_logger(caplog, logger_name: str, level: int):
    """Gestiona capture logger."""
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


class TestEsErrorTransitorio:
    """Agrupa pruebas relacionadas con es error transitorio."""

    def test_timeout_es_transitorio(self):
        """Verifica que timeout es transitorio."""
        assert email_service._es_error_transitorio(SMTPTimeoutError("timeout")) is True

    def test_connect_error_es_transitorio(self):
        """Verifica que connect error es transitorio."""
        assert (
            email_service._es_error_transitorio(SMTPConnectError("connect error"))
            is True
        )

    def test_disconnect_es_transitorio(self):
        """Verifica que disconnect es transitorio."""
        assert (
            email_service._es_error_transitorio(SMTPServerDisconnected("disconnect"))
            is True
        )

    def test_auth_error_no_es_transitorio(self):
        """Verifica que autenticación error no es transitorio."""
        exc = SMTPAuthenticationError(535, "auth failed")
        assert email_service._es_error_transitorio(exc) is False

    def test_recipients_refused_no_es_transitorio(self):
        """Verifica que recipients refused no es transitorio."""
        exc = SMTPRecipientsRefused(
            [SMTPRecipientRefused(550, "refused", "dest@test.com")]
        )
        assert email_service._es_error_transitorio(exc) is False

    def test_smtp_4xx_es_transitorio(self):
        """Verifica que smtp 4xx es transitorio."""
        exc = SMTPResponseException(421, "temporary failure")
        assert email_service._es_error_transitorio(exc) is True

    def test_smtp_5xx_no_es_transitorio(self):
        """Verifica que smtp 5xx no es transitorio."""
        exc = SMTPResponseException(550, "permanent failure")
        assert email_service._es_error_transitorio(exc) is False


class TestConstruirMensajeRecuperacion:
    """Agrupa pruebas relacionadas con construir mensaje recuperacion."""

    def test_construye_subject_from_to_y_cuerpos(self, monkeypatch):
        """Verifica que construye subject from to y cuerpos."""
        # Verifica que construye subject from to y cuerpos.
        _configurar_settings(monkeypatch)

        with patch.object(
            email_service.Path, "exists", return_value=False
        ), patch.object(
            email_service.email_templates,
            "recuperacion_password_template",
            return_value="<html><body>HTML TEST</body></html>",
        ):
            msg = email_service._construir_mensaje_recuperacion(
                "pepe@test.com",
                "123456",
                15,
                "test@example.com",
                "es",
            )

        assert msg["Subject"] == "Código de recuperación"
        assert msg["From"] is not None
        assert "MoveOn App" in msg["From"]
        assert "test@example.com" in msg["From"]
        assert msg["To"] == "pepe@test.com"

        texto = msg.get_body(preferencelist=("plain",))
        assert texto is not None
        assert "123456" in texto.get_content()
        assert "15" in texto.get_content()

        html = _extraer_html(msg)
        assert "HTML TEST" in html

    def test_si_logo_existe_lo_adjunta_inline(self, monkeypatch):
        """Verifica que si logo existe lo adjunta embebido."""
        # Verifica que si logo existe lo adjunta embebido.
        _configurar_settings(monkeypatch)

        with patch.object(email_service.Path, "exists", return_value=True), patch(
            "builtins.open",
            mock_open(read_data=b"fake-png-data"),
        ), patch.object(
            email_service.email_templates,
            "recuperacion_password_template",
            return_value="<html><body><img src='cid:moveon_logo'></body></html>",
        ):
            msg = email_service._construir_mensaje_recuperacion(
                "pepe@test.com",
                "123456",
                15,
                "test@example.com",
                "es",
            )

        html = _extraer_html(msg)
        assert "cid:moveon_logo" in html

        partes_imagen = [
            part for part in msg.walk() if part.get_content_maintype() == "image"
        ]

        assert len(partes_imagen) == 1
        assert partes_imagen[0].get_content_subtype() == "png"
        assert partes_imagen[0]["Content-ID"] == "<moveon_logo>"
        assert partes_imagen[0].get_filename() == "moveon.png"

    def test_si_logo_no_existe_loggea_warning(self, monkeypatch, caplog):
        """Verifica que si logo no existe loggea warning."""
        # Verifica que si logo no existe loggea warning.
        _configurar_settings(monkeypatch)

        with _capture_logger(caplog, "app.email", logging.WARNING):
            with patch.object(
                email_service.Path, "exists", return_value=False
            ), patch.object(
                email_service.email_templates,
                "recuperacion_password_template",
                return_value="<html><body>sin logo</body></html>",
            ):
                msg = email_service._construir_mensaje_recuperacion(
                    "pepe@test.com",
                    "123456",
                    15,
                    "test@example.com",
                    "es",
                )

        assert msg["To"] == "pepe@test.com"
        record = next(r for r in caplog.records if r.name == "app.email")
        assert record.getMessage() == "logo_correo_no_encontrado"
        assert record.email_destino == "pepe@test.com"


class TestConstruirMensajeAvisoGoogle:
    """Agrupa pruebas relacionadas con construir mensaje aviso google."""

    def test_construye_subject_en_y_html(self, monkeypatch):
        """Verifica que construye subject en y html."""
        # Verifica que construye subject en y html.
        _configurar_settings(monkeypatch)

        with patch.object(
            email_service.Path, "exists", return_value=False
        ), patch.object(
            email_service.email_templates,
            "aviso_recuperacion_google_template",
            return_value="<html><body>GOOGLE NOTICE</body></html>",
        ):
            msg = email_service._construir_mensaje_aviso_google(
                "pepe@test.com",
                "test@example.com",
                "en",
            )

        assert msg["Subject"] == "Access to your MoveOn account"
        texto = msg.get_body(preferencelist=("plain",))
        assert texto is not None
        assert "Google" in texto.get_content()
        html = _extraer_html(msg)
        assert "GOOGLE NOTICE" in html


class TestEnviarCodigoRecuperacion:
    """Agrupa pruebas relacionadas con enviar codigo recuperacion."""

    @pytest.mark.asyncio
    async def test_envio_ok_a_la_primera(self, monkeypatch):
        """Verifica que envio ok a la primera."""
        # Verifica que envio ok a la primera.
        _configurar_settings(monkeypatch)

        mock_send = AsyncMock(return_value=None)

        with patch.object(
            email_service,
            "_construir_mensaje_recuperacion",
            return_value=EmailMessage(),
        ) as mock_build, patch.object(
            email_service.aiosmtplib,
            "send",
            new=mock_send,
        ):
            ok = await email_service.enviar_codigo_recuperacion(
                "pepe@test.com",
                "123456",
                15,
                "en",
            )

        assert ok is True
        mock_build.assert_called_once_with(
            "pepe@test.com",
            "123456",
            15,
            "test@example.com",
            "en",
        )
        assert mock_send.await_count == 1

        await_args_obj = mock_send.await_args
        assert await_args_obj is not None

        kwargs = await_args_obj.kwargs
        assert kwargs["hostname"] == "smtp.example.com"
        assert kwargs["port"] == 587
        assert kwargs["username"] == "test@example.com"
        assert kwargs["password"] == "test-pass"
        assert kwargs["start_tls"] is True
        assert kwargs["timeout"] == 10.0

    @pytest.mark.asyncio
    async def test_reintenta_en_error_transitorio_y_acaba_ok(self, monkeypatch):
        """Verifica que reintenta en error transitorio y acaba ok."""
        # Verifica que reintenta en error transitorio y acaba ok.
        _configurar_settings(monkeypatch)

        mock_send = AsyncMock(
            side_effect=[
                SMTPTimeoutError("timeout"),
                None,
            ]
        )
        mock_sleep = AsyncMock()

        with patch.object(
            email_service,
            "_construir_mensaje_recuperacion",
            return_value=EmailMessage(),
        ), patch.object(
            email_service.aiosmtplib,
            "send",
            new=mock_send,
        ), patch.object(
            email_service.asyncio,
            "sleep",
            new=mock_sleep,
        ):
            ok = await email_service.enviar_codigo_recuperacion(
                "pepe@test.com",
                "123456",
                15,
                "en",
            )

        assert ok is True
        assert mock_send.await_count == 2
        mock_sleep.assert_awaited_once_with(1.0)

    @pytest.mark.asyncio
    async def test_reintenta_hasta_agotar_intentos_en_error_transitorio(
        self, monkeypatch
    ):
        """Verifica que reintenta hasta agotar intentos en error transitorio."""
        # Verifica que reintenta hasta agotar intentos en error transitorio.
        _configurar_settings(monkeypatch)

        mock_send = AsyncMock(
            side_effect=[
                SMTPServerDisconnected("down-1"),
                SMTPServerDisconnected("down-2"),
                SMTPServerDisconnected("down-3"),
            ]
        )
        mock_sleep = AsyncMock()

        with patch.object(
            email_service,
            "_construir_mensaje_recuperacion",
            return_value=EmailMessage(),
        ), patch.object(
            email_service.aiosmtplib,
            "send",
            new=mock_send,
        ), patch.object(
            email_service.asyncio,
            "sleep",
            new=mock_sleep,
        ):
            ok = await email_service.enviar_codigo_recuperacion(
                "pepe@test.com",
                "123456",
                15,
                "en",
            )

        assert ok is False
        assert mock_send.await_count == 3
        assert mock_sleep.await_count == 2
        mock_sleep.assert_any_await(1.0)
        mock_sleep.assert_any_await(2.0)

    @pytest.mark.asyncio
    async def test_no_reintenta_en_error_permanente(self, monkeypatch):
        """Verifica que no reintenta en error permanente."""
        # Verifica que no reintenta en error permanente.
        _configurar_settings(monkeypatch)

        mock_send = AsyncMock(side_effect=SMTPAuthenticationError(535, "auth failed"))
        mock_sleep = AsyncMock()

        with patch.object(
            email_service,
            "_construir_mensaje_recuperacion",
            return_value=EmailMessage(),
        ), patch.object(
            email_service.aiosmtplib,
            "send",
            new=mock_send,
        ), patch.object(
            email_service.asyncio,
            "sleep",
            new=mock_sleep,
        ):
            ok = await email_service.enviar_codigo_recuperacion(
                "pepe@test.com",
                "123456",
                15,
                "en",
            )

        assert ok is False
        assert mock_send.await_count == 1
        mock_sleep.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_respuesta_4xx_reintenta(self, monkeypatch):
        """Verifica que respuesta 4xx reintenta."""
        # Verifica que respuesta 4xx reintenta.
        _configurar_settings(monkeypatch)

        mock_send = AsyncMock(
            side_effect=[
                SMTPResponseException(421, "temporary failure"),
                None,
            ]
        )
        mock_sleep = AsyncMock()

        with patch.object(
            email_service,
            "_construir_mensaje_recuperacion",
            return_value=EmailMessage(),
        ), patch.object(
            email_service.aiosmtplib,
            "send",
            new=mock_send,
        ), patch.object(
            email_service.asyncio,
            "sleep",
            new=mock_sleep,
        ):
            ok = await email_service.enviar_codigo_recuperacion(
                "pepe@test.com",
                "123456",
                15,
                "en",
            )

        assert ok is True
        assert mock_send.await_count == 2
        mock_sleep.assert_awaited_once_with(1.0)

    @pytest.mark.asyncio
    async def test_respuesta_5xx_no_reintenta(self, monkeypatch):
        """Verifica que respuesta 5xx no reintenta."""
        # Verifica que respuesta 5xx no reintenta.
        _configurar_settings(monkeypatch)

        mock_send = AsyncMock(
            side_effect=SMTPResponseException(550, "mailbox unavailable")
        )
        mock_sleep = AsyncMock()

        with patch.object(
            email_service,
            "_construir_mensaje_recuperacion",
            return_value=EmailMessage(),
        ), patch.object(
            email_service.aiosmtplib,
            "send",
            new=mock_send,
        ), patch.object(
            email_service.asyncio,
            "sleep",
            new=mock_sleep,
        ):
            ok = await email_service.enviar_codigo_recuperacion(
                "pepe@test.com",
                "123456",
                15,
                "en",
            )

        assert ok is False
        assert mock_send.await_count == 1
        mock_sleep.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_error_generico_devuelve_false_sin_reintento(self, monkeypatch):
        """Verifica que error generico devuelve false sin reintento."""
        # Verifica que error generico devuelve false sin reintento.
        _configurar_settings(monkeypatch)

        mock_send = AsyncMock(side_effect=RuntimeError("boom"))
        mock_sleep = AsyncMock()

        with patch.object(
            email_service,
            "_construir_mensaje_recuperacion",
            return_value=EmailMessage(),
        ), patch.object(
            email_service.aiosmtplib,
            "send",
            new=mock_send,
        ), patch.object(
            email_service.asyncio,
            "sleep",
            new=mock_sleep,
        ):
            ok = await email_service.enviar_codigo_recuperacion(
                "pepe@test.com",
                "123456",
                15,
                "en",
            )

        assert ok is False
        assert mock_send.await_count == 1
        mock_sleep.assert_not_awaited()


class TestEnviarAvisoRecuperacionGoogle:
    """Agrupa pruebas relacionadas con enviar aviso recuperacion google."""

    @pytest.mark.asyncio
    async def test_envio_ok(self, monkeypatch):
        """Verifica que envio ok."""
        # Verifica que envio ok.
        _configurar_settings(monkeypatch)

        mock_send = AsyncMock(return_value=None)

        with patch.object(
            email_service,
            "_construir_mensaje_aviso_google",
            return_value=EmailMessage(),
        ) as mock_build, patch.object(
            email_service.aiosmtplib,
            "send",
            new=mock_send,
        ):
            ok = await email_service.enviar_aviso_recuperacion_google(
                "pepe@test.com",
                "en",
            )

        assert ok is True
        mock_build.assert_called_once_with(
            "pepe@test.com",
            "test@example.com",
            "en",
        )
        assert mock_send.await_count == 1
