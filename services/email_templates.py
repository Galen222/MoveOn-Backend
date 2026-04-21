# services/email_templates.py

"""Implementa la lógica de negocio de este servicio."""

from html import escape


def _base_email_template(
    *, lang: str, title: str, body_html: str, footer_html: str
) -> str:
    """Gestiona base correo electrónico template."""
    # Gestiona base correo electrónico template.
    return f"""
    <!DOCTYPE html>
    <html lang="{lang}">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <style>
            body {{
                font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
                color: # 333;
                line-height: 1.6;
                margin: 0;
                padding: 0;
            }}
            .container {{
                max-width: 500px;
                margin: 40px auto;
                padding: 20px;
                border: 1px solid # e0e0e0;
                border-radius: 12px;
                box-shadow: 0 4px 12px rgba(0,0,0,0.05);
            }}
            .header {{
                text-align: center;
                padding-bottom: 20px;
                border-bottom: 2px solid # f4f4f4;
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
            .card {{
                margin: 25px 0;
                padding: 20px;
                background-color: # f8f9fa;
                border-radius: 8px;
                border: 1px dashed # 007bff;
            }}
            .code {{
                font-size: 35px;
                font-weight: bold;
                letter-spacing: 8px;
                color: # 007bff;
            }}
            .footer {{
                font-size: 0.85em;
                color: # 888;
                text-align: center;
                padding-top: 20px;
                border-top: 1px solid # f4f4f4;
            }}
        </style>
    </head>
    <body>
        <div class="container">
            <div class="header">
                <img class="logo-image" src="cid:moveon_logo" alt="MoveOn App">
            </div>
            <div class="content">
                <h2 style="margin-top: 0;">{title}</h2>
                {body_html}
            </div>
            <div class="footer">
                {footer_html}
                <p>&copy; MoveOn App</p>
            </div>
        </div>
    </body>
    </html>
    """


def recuperacion_password_template(
    codigo: str, minutos: int, locale: str = "es"
) -> str:
    """Genera la plantilla HTML para el código de recuperación de MoveOn."""
    # Gestiona recuperacion password template.
    if locale == "en":
        body_html = f"""
                <p>Use the following verification code to set a new password for your account. This code is single-use.</p>
                <div class=\"card\">
                    <div class=\"code\">{codigo}</div>
                </div>
                <p style=\"font-size: 0.9em; color: # 666;\">This code will <strong>expire in {minutos} minute{"s" if minutos != 1 else ""}</strong>.</p>
        """
        footer_html = "<p>If you did not request this change, you can safely ignore this email.</p>"
        return _base_email_template(
            lang="en",
            title="Forgot your password?",
            body_html=body_html,
            footer_html=footer_html,
        )

    body_html = f"""
                <p>Usa el siguiente código de verificación para establecer una nueva contraseña en tu cuenta. Este código es de un solo uso.</p>
                <div class=\"card\">
                    <div class=\"code\">{codigo}</div>
                </div>
                <p style=\"font-size: 0.9em; color: # 666;\">Este código <strong>expirará en {minutos} minuto{"s" if minutos != 1 else ""}</strong>.</p>
    """
    footer_html = "<p>Si no solicitaste este cambio, puedes ignorar este correo con seguridad.</p>"
    return _base_email_template(
        lang="es",
        title="¿Olvidaste tu contraseña?",
        body_html=body_html,
        footer_html=footer_html,
    )


def aviso_recuperacion_google_template(locale: str = "es") -> str:
    """Genera la plantilla HTML para informar de que la cuenta usa Google."""
    # Gestiona aviso recuperacion google template.
    if locale == "en":
        body_html = """
                <p>We received a request to change the password for this email address.</p>
                <p>Your MoveOn account is linked to Google, so it does not use this password recovery flow.</p>
                <p>Please return to the app and choose <strong>Continue with Google</strong> to sign in.</p>
        """
        footer_html = "<p>If you did not request access to your account, you can safely ignore this email.</p>"
        return _base_email_template(
            lang="en",
            title="Access to your MoveOn account",
            body_html=body_html,
            footer_html=footer_html,
        )

    body_html = """
                <p>Hemos recibido una solicitud para cambiar la contraseña de esta dirección de correo.</p>
                <p>Tu cuenta MoveOn está vinculada a Google, por lo que no utiliza este flujo de recuperación de contraseña.</p>
                <p>Vuelve a la app y pulsa <strong>Continuar con Google</strong> para iniciar sesión.</p>
        """
    footer_html = "<p>Si no has solicitado acceso a tu cuenta, puedes ignorar este correo con seguridad.</p>"
    return _base_email_template(
        lang="es",
        title="Acceso a tu cuenta MoveOn",
        body_html=body_html,
        footer_html=footer_html,
    )


def reporte_perfil_inapropiado_template(
    usuario_reportante: str,
    usuario_reportado: str,
    reportar_nombre: bool,
    reportar_foto: bool,
    observaciones: str | None,
) -> str:
    """Gestiona reporte perfil inapropiado template."""
    # Gestiona reporte perfil inapropiado template.
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
                color: # 333;
                line-height: 1.6;
                margin: 0;
                padding: 0;
            }}
            .container {{
                max-width: 560px;
                margin: 40px auto;
                padding: 20px;
                border: 1px solid # e0e0e0;
                border-radius: 12px;
                box-shadow: 0 4px 12px rgba(0,0,0,0.05);
            }}
            .header {{
                text-align: center;
                padding-bottom: 20px;
                border-bottom: 2px solid # f4f4f4;
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
            .intro-title {{
                margin-top: 0;
                text-align: center;
            }}
            .intro-text {{
                text-align: center;
            }}
            .card {{
                margin: 18px 0;
                padding: 16px;
                background-color: # f8f9fa;
                border-radius: 8px;
                border: 1px solid # e9ecef;
            }}
            .label {{
                font-size: 12px;
                color: # 666;
                text-transform: uppercase;
                letter-spacing: .04em;
                margin-bottom: 6px;
            }}
            .value {{
                font-size: 16px;
                color: # 222;
                font-weight: 600;
            }}
            .footer {{
                font-size: 0.85em;
                color: # 888;
                text-align: center;
                padding-top: 20px;
                border-top: 1px solid # f4f4f4;
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
                <h2 class="intro-title">Reporte de perfil</h2>
                <p class="intro-text">Se ha recibido un reporte de contenido potencialmente inapropiado en MoveOn.</p>

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
                <p>&copy; MoveOn App</p>
            </div>
        </div>
    </body>
    </html>
    """
