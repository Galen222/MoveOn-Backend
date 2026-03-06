# services/email_service.py

import logging
from pathlib import Path
from email.message import EmailMessage
from email.utils import formataddr

import aiosmtplib

from services import email_templates
from config import settings

logger = logging.getLogger(__name__)


async def enviar_codigo_recuperacion(email_destino: str, codigo: str, minutos: int):
    """Construye y envía el correo de forma asíncrona."""
    # Obtener configuración del entorno
    smtp_server = settings.EMAIL_HOST
    smtp_port = settings.EMAIL_PORT
    smtp_username = settings.EMAIL_USER
    smtp_password = settings.EMAIL_PASS

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
            logger.warning("No se encontró la parte HTML del email para adjuntar el logo inline")
    else:
        logger.warning("No se encontró el logo del email en %s", logo_path)

    try:
        await aiosmtplib.send(
            msg,
            hostname=smtp_server,
            port=smtp_port,
            username=smtp_username,
            password=smtp_password,
            start_tls=True
        )
        logger.info("Correo de recuperación enviado a %s", email_destino)
        return True
    except Exception:
        logger.exception("ERROR AL ENVIAR EMAIL a %s", email_destino)
        return False
    