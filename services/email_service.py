# services/email_service.py

import os
import aiosmtplib
from email.message import EmailMessage
from services.email_templates import password_reset_template

class EmailService:
    def __init__(self):
        # Asegúrate de añadir estas variables a tu .env
        self.smtp_server = os.getenv("EMAIL_HOST")
        self.smtp_port = int(os.getenv("EMAIL_PORT", 587))
        self.smtp_username = os.getenv("EMAIL_USER")
        self.smtp_password = os.getenv("EMAIL_PASS")

    async def enviar_codigo_recuperacion(self, email_destino: str, codigo: str):
        """Construye y envía el correo de forma asíncrona."""
        msg = EmailMessage()
        msg['Subject'] = "Código de recuperación - MoveOn"
        msg['From'] = self.smtp_username
        msg['To'] = email_destino

        # Versión en texto plano
        msg.set_content(f"Tu código de recuperación para MoveOn es: {codigo}. Expira en 15 minutos.")

        # Versión HTML usando la plantilla
        html_content = password_reset_template(codigo)
        msg.add_alternative(html_content, subtype="html")

        try:
            await aiosmtplib.send(
                msg,
                hostname=self.smtp_server,
                port=self.smtp_port,
                username=self.smtp_username,
                password=self.smtp_password,
                start_tls=True
            )
            return True
        except Exception as e:
            # Imprime el error en consola para que puedas debuguear en Railway/Local
            print(f"ERROR EMAIL_SERVICE: {str(e)}")
            return False