# services/email_templates.py

def recuperacion_contraseña_template(codigo: str) -> str:
    """Genera la plantilla HTML para el código de recuperación de MoveOn."""
    return f"""
    <!DOCTYPE html>
    <html lang="es">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <style>
            body {{ font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; color: #333; line-height: 1.6; margin: 0; padding: 0; }}
            .container {{ max-width: 500px; margin: 40px auto; padding: 20px; border: 1px solid #e0e0e0; border-radius: 12px; box-shadow: 0 4px 12px rgba(0,0,0,0.05); }}
            .header {{ text-align: center; padding-bottom: 20px; border-bottom: 2px solid #f4f4f4; }}
            .logo {{ font-size: 24px; font-weight: bold; color: #007bff; text-decoration: none; }}
            .content {{ padding: 30px 10px; text-align: center; }}
            .code-box {{ margin: 25px 0; padding: 20px; background-color: #f8f9fa; border-radius: 8px; border: 1px dashed #007bff; }}
            .code {{ font-size: 35px; font-weight: bold; letter-spacing: 8px; color: #007bff; }}
            .footer {{ font-size: 0.85em; color: #888; text-align: center; padding-top: 20px; border-top: 1px solid #f4f4f4; }}
        </style>
    </head>
    <body>
        <div class="container">
            <div class="header">
                <div class="logo">MoveOn</div>
            </div>
            <div class="content">
                <h2 style="margin-top: 0;">¿Olvidaste tu contraseña?</h2>
                <p>Usa el siguiente código de verificación para establecer una nueva contraseña en tu cuenta. Este código es de un solo uso.</p>
                <div class="code-box">
                    <div class="code">{codigo}</div>
                </div>
                <p style="font-size: 0.9em; color: #666;">Este código <strong>expirará en 15 minutos</strong>.</p>
            </div>
            <div class="footer">
                <p>Si no solicitaste este cambio, puedes ignorar este correo con seguridad.</p>
                <p>&copy; MoveOn App</p>
            </div>
        </div>
    </body>
    </html>
    """