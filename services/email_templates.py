# services/email_templates.py

from html import escape


def recuperacion_password_template(codigo: str, minutos: int) -> str:
    """Genera la plantilla HTML para el código de recuperación de MoveOn."""
    return f"""
    <!DOCTYPE html>
    <html lang="es">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <style>
            body {{
                font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
                color: #333;
                line-height: 1.6;
                margin: 0;
                padding: 0;
            }}
            .container {{
                max-width: 500px;
                margin: 40px auto;
                padding: 20px;
                border: 1px solid #e0e0e0;
                border-radius: 12px;
                box-shadow: 0 4px 12px rgba(0,0,0,0.05);
            }}
            .header {{
                text-align: center;
                padding-bottom: 20px;
                border-bottom: 2px solid #f4f4f4;
            }}
            .logo-image {{
                display: block;
                margin: 0 auto;
                max-width: 180px;
                width: 100%;
                height: auto;
            }}
            .content {{
                padding: 30px 10px;
                text-align: center;
            }}
            .code-box {{
                margin: 25px 0;
                padding: 20px;
                background-color: #f8f9fa;
                border-radius: 8px;
                border: 1px dashed #007bff;
            }}
            .code {{
                font-size: 35px;
                font-weight: bold;
                letter-spacing: 8px;
                color: #007bff;
            }}
            .footer {{
                font-size: 0.85em;
                color: #888;
                text-align: center;
                padding-top: 20px;
                border-top: 1px solid #f4f4f4;
            }}
        </style>
    </head>
    <body>
        <div class="container">
            <div class="header">
                <img class="logo-image" src="cid:moveon_logo" alt="MoveOn App">
            </div>
            <div class="content">
                <h2 style="margin-top: 0;">¿Olvidaste tu contraseña?</h2>
                <p>Usa el siguiente código de verificación para establecer una nueva contraseña en tu cuenta. Este código es de un solo uso.</p>
                <div class="code-box">
                    <div class="code">{codigo}</div>
                </div>
                <p style="font-size: 0.9em; color: #666;">Este código <strong>expirará en {minutos} minuto{"s" if minutos != 1 else ""}</strong>.</p>
            </div>
            <div class="footer">
                <p>Si no solicitaste este cambio, puedes ignorar este correo con seguridad.</p>
                <p>&copy; MoveOn App</p>
            </div>
        </div>
    </body>
    </html>
    """


def reporte_perfil_inapropiado_template(
    usuario_reportante: str,
    usuario_reportado: str,
    reportar_nombre: bool,
    reportar_foto: bool,
    observaciones: str | None,
) -> str:
    motivos_html = []
    if reportar_nombre:
        motivos_html.append("<li>Nombre de usuario inapropiado</li>")
    if reportar_foto:
        motivos_html.append("<li>Foto de perfil inapropiada</li>")

    observaciones_html = escape(observaciones) if observaciones else "Sin observaciones"

    return f"""
    <!DOCTYPE html>
    <html lang="es">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <style>
            body {{
                font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
                color: #333;
                line-height: 1.6;
                margin: 0;
                padding: 0;
            }}
            .container {{
                max-width: 560px;
                margin: 40px auto;
                padding: 20px;
                border: 1px solid #e0e0e0;
                border-radius: 12px;
                box-shadow: 0 4px 12px rgba(0,0,0,0.05);
            }}
            .header {{
                text-align: center;
                padding-bottom: 20px;
                border-bottom: 2px solid #f4f4f4;
            }}
            .logo-image {{
                display: block;
                margin: 0 auto;
                max-width: 180px;
                width: 100%;
                height: auto;
            }}
            .content {{
                padding: 24px 10px 10px;
            }}
            .card {{
                margin: 18px 0;
                padding: 16px;
                background-color: #f8f9fa;
                border-radius: 8px;
                border: 1px solid #e9ecef;
            }}
            .label {{
                font-size: 12px;
                color: #666;
                text-transform: uppercase;
                letter-spacing: .04em;
                margin-bottom: 6px;
            }}
            .value {{
                font-size: 16px;
                color: #222;
                font-weight: 600;
            }}
            .footer {{
                font-size: 0.85em;
                color: #888;
                text-align: center;
                padding-top: 20px;
                border-top: 1px solid #f4f4f4;
            }}
            ul {{
                margin: 8px 0 0;
                padding-left: 20px;
            }}
        </style>
    </head>
    <body>
        <div class="container">
            <div class="header">
                <img class="logo-image" src="cid:moveon_logo" alt="MoveOn App">
            </div>

            <div class="content">
                <h2 style="margin-top: 0;">Nuevo reporte de perfil</h2>
                <p>Se ha recibido un reporte de contenido potencialmente inapropiado en MoveOn.</p>

                <div class="card">
                    <div class="label">Usuario que reporta</div>
                    <div class="value">{escape(usuario_reportante)}</div>
                </div>

                <div class="card">
                    <div class="label">Usuario reportado</div>
                    <div class="value">{escape(usuario_reportado)}</div>
                </div>

                <div class="card">
                    <div class="label">Motivos del reporte</div>
                    <ul>
                        {''.join(motivos_html)}
                    </ul>
                </div>

                <div class="card">
                    <div class="label">Observaciones</div>
                    <div>{observaciones_html}</div>
                </div>
            </div>

            <div class="footer">
                <p>Correo generado automáticamente por MoveOn App.</p>
                <p>&copy; MoveOn App</p>
            </div>
        </div>
    </body>
    </html>
    """
