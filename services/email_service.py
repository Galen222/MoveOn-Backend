# services/email_service.py

import asyncio
import logging
from pathlib import Path
from email.message import EmailMessage
from email.utils import formataddr

import aiosmtplib
from aiosmtplib.errors import (
    SMTPAuthenticationError,
    SMTPConnectError,
    SMTPNotSupported,
    SMTPRecipientRefused,
    SMTPRecipientsRefused,
    SMTPResponseException,
    SMTPSenderRefused,
    SMTPServerDisconnected,
    SMTPTimeoutError,
)

from services import email_templates
from config import settings

logger = logging.getLogger("app.email")


def _es_error_transitorio(exc: Exception) -> bool:
    # Errores claros de red / timeout / conexión
    if isinstance(
        exc,
        (
            SMTPTimeoutError,
            SMTPConnectError,
            SMTPServerDisconnected,
            TimeoutError,
            ConnectionError,
        ),
    ):
        return True

    # Fallos claramente permanentes / de configuración
    if isinstance(
        exc,
        (
            SMTPAuthenticationError,
            SMTPRecipientsRefused,
            SMTPRecipientRefused,
            SMTPSenderRefused,
            SMTPNotSupported,
        ),
    ):
        return False

    # Respuestas SMTP genéricas: 4xx suelen ser temporales; 5xx, permanentes
    if isinstance(exc, SMTPResponseException):
        return 400 <= exc.code < 500

    # Fallback conservador
    return False


def _construir_mensaje(
    email_destino: str,
    codigo: str,
    minutos: int,
    smtp_username: str,
) -> EmailMessage:
    msg = EmailMessage()
    msg["Subject"] = "Código de recuperación - MoveOn"
    msg["From"] = formataddr(("MoveOn App", smtp_username))
    msg["To"] = email_destino

    msg.set_content(
        f"Tu código de recuperación para MoveOn es: {codigo}. Expira en {minutos} minutos."
    )

    html_content = email_templates.recuperacion_password_template(codigo, minutos)
    msg.add_alternative(html_content, subtype="html")

    logo_path = Path(__file__).resolve().parents[1] / "assets" / "email" / "moveon.png"

    if logo_path.exists():
        with open(logo_path, "rb") as f:
            logo_data = f.read()

        html_part = msg.get_body(preferencelist=("html",))
        if html_part is not None:
            html_part.add_related(
                logo_data,
                maintype="image",
                subtype="png",
                cid="<moveon_logo>",
                filename="moveon.png",
                disposition="inline",
            )
        else:
            logger.warning(
                "email_html_part_missing",
                extra={
                    "email_destino": email_destino,
                    "logo_path": str(logo_path),
                },
            )
    else:
        logger.warning(
            "email_logo_missing",
            extra={
                "email_destino": email_destino,
                "logo_path": str(logo_path),
            },
        )

    return msg


async def enviar_codigo_recuperacion(email_destino: str, codigo: str, minutos: int) -> bool:
    """Construye y envía el correo de forma asíncrona con retry en errores transitorios."""

    smtp_server = settings.EMAIL_HOST
    smtp_port = settings.EMAIL_PORT
    smtp_username = settings.EMAIL_USER
    smtp_password = settings.EMAIL_PASS

    timeout = settings.EMAIL_TIMEOUT_SECONDS
    max_retries = settings.EMAIL_MAX_RETRIES
    base_delay = settings.EMAIL_RETRY_BASE_DELAY_SECONDS

    msg = _construir_mensaje(email_destino, codigo, minutos, smtp_username)

    ultimo_error: Exception | None = None

    for intento in range(1, max_retries + 1):
        try:
            await aiosmtplib.send(
                msg,
                hostname=smtp_server,
                port=smtp_port,
                username=smtp_username,
                password=smtp_password,
                start_tls=True,
                timeout=timeout,
            )

            logger.info(
                "recovery_email_sent",
                extra={
                    "email_destino": email_destino,
                    "intento": intento,
                    "max_retries": max_retries,
                    "smtp_host": smtp_server,
                    "smtp_port": smtp_port,
                },
            )
            return True

        except Exception as exc:
            ultimo_error = exc
            transitorio = _es_error_transitorio(exc)

            if not transitorio:
                logger.exception(
                    "recovery_email_send_permanent_error",
                    extra={
                        "email_destino": email_destino,
                        "intento": intento,
                        "max_retries": max_retries,
                        "smtp_host": smtp_server,
                        "smtp_port": smtp_port,
                        "error_type": type(exc).__name__,
                    },
                )
                return False

            logger.warning(
                "recovery_email_send_transient_error",
                extra={
                    "email_destino": email_destino,
                    "intento": intento,
                    "max_retries": max_retries,
                    "smtp_host": smtp_server,
                    "smtp_port": smtp_port,
                    "error_type": type(exc).__name__,
                    "error": str(exc),
                },
            )

            if intento < max_retries:
                await asyncio.sleep(base_delay * (2 ** (intento - 1)))

    logger.exception(
        "recovery_email_send_exhausted",
        extra={
            "email_destino": email_destino,
            "max_retries": max_retries,
            "smtp_host": smtp_server,
            "smtp_port": smtp_port,
            "error_type": type(ultimo_error).__name__ if ultimo_error else None,
        },
        exc_info=ultimo_error,
    )
    return False
