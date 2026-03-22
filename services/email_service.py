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

REPORTES_DESTINO = (
    "alvaroportillo565@gmail.com",
    "galen2@gmx.net",
)


def _es_error_transitorio(exc: Exception) -> bool:
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

    if isinstance(exc, SMTPResponseException):
        return 400 <= exc.code < 500

    return False


def _adjuntar_logo_inline(msg: EmailMessage, email_destino: str) -> None:
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
                "falta_parte_html_en_correo",
                extra={
                    "email_destino": email_destino,
                    "logo_path": str(logo_path),
                },
            )
    else:
        logger.warning(
            "logo_correo_no_encontrado",
            extra={
                "email_destino": email_destino,
                "logo_path": str(logo_path),
            },
        )


def _construir_mensaje_recuperacion(
    email_destino: str,
    codigo: str,
    minutos: int,
    smtp_username: str,
) -> EmailMessage:
    msg = EmailMessage()
    msg["Subject"] = "Código de recuperación"
    msg["From"] = formataddr(("MoveOn App", smtp_username))
    msg["To"] = email_destino

    msg.set_content(
        f"Tu código de recuperación para MoveOn es: {codigo}. Expira en {minutos} minutos."
    )

    html_content = email_templates.recuperacion_password_template(codigo, minutos)
    msg.add_alternative(html_content, subtype="html")
    _adjuntar_logo_inline(msg, email_destino)
    return msg


def _construir_mensaje_reporte_perfil(
    usuario_reportante: str,
    usuario_reportado: str,
    reportar_nombre: bool,
    reportar_foto: bool,
    observaciones: str | None,
    smtp_username: str,
) -> EmailMessage:
    msg = EmailMessage()
    msg["Subject"] = "Reporte de perfil inapropiado"
    msg["From"] = formataddr(("MoveOn App", smtp_username))
    msg["To"] = ", ".join(REPORTES_DESTINO)

    motivos_txt = []
    if reportar_nombre:
        motivos_txt.append("Nombre de usuario inapropiado")
    if reportar_foto:
        motivos_txt.append("Foto de perfil inapropiada")

    msg.set_content(
        "\n".join(
            [
                "Se ha recibido un nuevo reporte de perfil en MoveOn.",
                "",
                f"Usuario que reporta: {usuario_reportante}",
                f"Usuario reportado: {usuario_reportado}",
                f"Motivos: {', '.join(motivos_txt)}",
                f"Observaciones: {observaciones or 'Sin observaciones'}",
            ]
        )
    )

    html_content = email_templates.reporte_perfil_inapropiado_template(
        usuario_reportante=usuario_reportante,
        usuario_reportado=usuario_reportado,
        reportar_nombre=reportar_nombre,
        reportar_foto=reportar_foto,
        observaciones=observaciones,
    )
    msg.add_alternative(html_content, subtype="html")
    _adjuntar_logo_inline(msg, ",".join(REPORTES_DESTINO))
    return msg


async def _enviar_mensaje(
    msg: EmailMessage,
    destino_log: str,
    evento_ok: str,
    evento_error_permanente: str,
    evento_error_transitorio: str,
    evento_agotado: str,
) -> bool:
    smtp_server = settings.EMAIL_HOST
    smtp_port = settings.EMAIL_PORT
    smtp_username = settings.EMAIL_USER
    smtp_password = settings.EMAIL_PASS

    timeout = settings.EMAIL_TIMEOUT_SECONDS
    max_retries = settings.EMAIL_MAX_RETRIES
    base_delay = settings.EMAIL_RETRY_BASE_DELAY_SECONDS

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
                evento_ok,
                extra={
                    "email_destino": destino_log,
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
                    evento_error_permanente,
                    extra={
                        "email_destino": destino_log,
                        "intento": intento,
                        "max_retries": max_retries,
                        "smtp_host": smtp_server,
                        "smtp_port": smtp_port,
                        "error_type": type(exc).__name__,
                    },
                )
                return False

            logger.warning(
                evento_error_transitorio,
                extra={
                    "email_destino": destino_log,
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
        evento_agotado,
        extra={
            "email_destino": destino_log,
            "max_retries": max_retries,
            "smtp_host": smtp_server,
            "smtp_port": smtp_port,
            "error_type": type(ultimo_error).__name__ if ultimo_error else None,
        },
        exc_info=ultimo_error,
    )
    return False


async def enviar_codigo_recuperacion(
    email_destino: str, codigo: str, minutos: int
) -> bool:
    msg = _construir_mensaje_recuperacion(
        email_destino, codigo, minutos, settings.EMAIL_USER
    )
    return await _enviar_mensaje(
        msg=msg,
        destino_log=email_destino,
        evento_ok="correo_recuperacion_enviado",
        evento_error_permanente="error_permanente_envio_correo_recuperacion",
        evento_error_transitorio="error_transitorio_envio_correo_recuperacion",
        evento_agotado="intentos_envio_correo_recuperacion_agotados",
    )


async def enviar_reporte_perfil_inapropiado(
    usuario_reportante: str,
    usuario_reportado: str,
    reportar_nombre: bool,
    reportar_foto: bool,
    observaciones: str | None,
) -> bool:
    msg = _construir_mensaje_reporte_perfil(
        usuario_reportante=usuario_reportante,
        usuario_reportado=usuario_reportado,
        reportar_nombre=reportar_nombre,
        reportar_foto=reportar_foto,
        observaciones=observaciones,
        smtp_username=settings.EMAIL_USER,
    )
    return await _enviar_mensaje(
        msg=msg,
        destino_log=",".join(REPORTES_DESTINO),
        evento_ok="correo_reporte_perfil_enviado",
        evento_error_permanente="error_permanente_envio_correo_reporte_perfil",
        evento_error_transitorio="error_transitorio_envio_correo_reporte_perfil",
        evento_agotado="intentos_envio_correo_reporte_perfil_agotados",
    )
