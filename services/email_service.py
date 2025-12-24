# services/email_service.py

import aiosmtplib
from email.message import EmailMessage
from services import email_templates
from config import settings

async def enviar_codigo_recuperacion(email_destino: str, codigo: str):
    """Construye y envía el correo de forma asíncrona."""
    # Obtener configuración del entorno 
    smtp_server = settings.EMAIL_HOST
    smtp_port = settings.EMAIL_PORT
    smtp_username = settings.EMAIL_USER
    smtp_password = settings.EMAIL_PASS

    msg = EmailMessage()
    msg['Subject'] = "Código de recuperación - MoveOn"
    msg['From'] = smtp_username
    msg['To'] = email_destino

    msg.set_content(f"Tu código de recuperación para MoveOn es: {codigo}. Expira en 15 minutos.")
    html_content = email_templates.recuperacion_contraseña_template(codigo)
    msg.add_alternative(html_content, subtype="html")

    try:
        await aiosmtplib.send(
            msg,
            hostname=smtp_server,
            port=smtp_port,
            username=smtp_username,
            password=smtp_password,
            start_tls=True
        )
        return True
    except Exception as e:
        # Imprime el error en consola para debuguear
        print(f"ERROR AL ENVIAR EMAIL: {str(e)}")
        return False