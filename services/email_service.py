# services/email_service.py

"""Implementa la lógica de negocio de este servicio."""

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
    """Clasifica una excepción SMTP como transitoria (merece reintento) o no.

    Clasificación:

    - Timeouts, desconexiones y errores de red → transitorios.
    - Auth, remitente/destinatario rechazados, ``SMTPNotSupported`` →
      permanentes: reintentar no va a cambiar el resultado.
    - ``SMTPResponseException`` con código 4xx → transitorio (el 5xx no).
    - Resto → considerado permanente por defecto para no reintentar
      en bucle ante errores desconocidos.

    Args:
        exc: excepción capturada al enviar el correo.

    Returns:
        ``True`` si procede reintentar el envío; ``False`` si hay que rendirse.
    """
    # Indica si error transitorio.
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


def _normalizar_locale(locale: str) -> str:
    """Reduce un locale arbitrario al conjunto cerrado ``{"es", "en"}``.

    Acepta ``en``, ``en-US``, ``en_GB``, etc. para inglés. Cualquier otro
    valor cae a español, que es el idioma por defecto del servicio.

    Args:
        locale: locale tal como llega del cliente.

    Returns:
        ``"en"`` si el locale empieza por inglés, ``"es"`` en cualquier otro caso.
    """
    normalizado = (
        locale.strip().lower().replace("_", "-") if isinstance(locale, str) else ""
    )
    if normalizado.startswith("en"):
        return "en"
    return "es"


def _adjuntar_logo_inline(msg: EmailMessage, email_destino: str) -> None:
    """Adjunta el logo de MoveOn como imagen inline (``cid:moveon_logo``).

    Busca ``assets/email/moveon.png`` relativo a la raíz del proyecto.
    Si no existe, emite un warning en vez de fallar para que el correo
    se envíe aunque sea sin logo. Si no encuentra parte HTML a la que
    asociar la imagen también avisa: el mensaje seguiría saliendo como
    texto plano pero sin referencia al ``cid``.

    Args:
        msg: mensaje al que añadir el adjunto (se muta in place).
        email_destino: destinatario, sólo para enriquecer los logs.
    """
    # Adjunta logo embebido.
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
    locale: str,
) -> EmailMessage:
    """Construye el ``EmailMessage`` de recuperación de contraseña.

    Añade versión texto plano y versión HTML con la plantilla del
    idioma correspondiente, y pega el logo inline. El ``Subject`` y el
    texto plano se traducen también según ``locale``.

    Args:
        email_destino: dirección a la que se envía el correo.
        codigo: código numérico que el usuario debe introducir en la app.
        minutos: minutos de validez del código; pluraliza en el texto.
        smtp_username: dirección usada como remitente (``From``).
        locale: idioma preferido del usuario; se normaliza a ``"es"``/``"en"``.

    Returns:
        Mensaje listo para enviar con ``_enviar_mensaje``.
    """
    # Construye mensaje recuperacion.
    locale_normalizado = _normalizar_locale(locale)

    msg = EmailMessage()
    msg["Subject"] = (
        "Recovery code" if locale_normalizado == "en" else "Código de recuperación"
    )
    msg["From"] = formataddr(("MoveOn App", smtp_username))
    msg["To"] = email_destino

    if locale_normalizado == "en":
        msg.set_content(
            f"Your MoveOn recovery code is: {codigo}. It expires in {minutos} minute{'s' if minutos != 1 else ''}."
        )
    else:
        msg.set_content(
            f"Tu código de recuperación para MoveOn es: {codigo}. Expira en {minutos} minuto{'s' if minutos != 1 else ''}."
        )

    html_content = email_templates.recuperacion_password_template(
        codigo, minutos, locale_normalizado
    )
    msg.add_alternative(html_content, subtype="html")
    _adjuntar_logo_inline(msg, email_destino)
    return msg


def _construir_mensaje_aviso_google(
    email_destino: str,
    smtp_username: str,
    locale: str,
) -> EmailMessage:
    """Construye el correo que avisa de que la cuenta usa Google.

    Mismo chasis que el de recuperación pero con el texto adaptado.
    Se usa cuando alguien intenta recuperar contraseña de una cuenta
    social: en vez de contestar distinto en el endpoint (y filtrar el
    tipo de cuenta), se envía este email al dueño.

    Args:
        email_destino: dirección del correo.
        smtp_username: dirección usada como remitente.
        locale: idioma preferido; se normaliza.

    Returns:
        Mensaje listo para enviar con ``_enviar_mensaje``.
    """
    # Construye mensaje aviso google.
    locale_normalizado = _normalizar_locale(locale)

    msg = EmailMessage()
    msg["Subject"] = (
        "Access to your MoveOn account"
        if locale_normalizado == "en"
        else "Acceso a tu cuenta MoveOn"
    )
    msg["From"] = formataddr(("MoveOn App", smtp_username))
    msg["To"] = email_destino

    if locale_normalizado == "en":
        msg.set_content(
            "We received a password change request for this email address. "
            "Your MoveOn account is linked to Google, so it does not use this password recovery flow. "
            "Please return to the app and choose 'Continue with Google' to sign in."
        )
    else:
        msg.set_content(
            "Hemos recibido una solicitud para cambiar la contraseña de esta dirección de correo. "
            "Tu cuenta MoveOn está vinculada a Google, por lo que no utiliza este flujo de recuperación de contraseña. "
            "Vuelve a la app y pulsa 'Continuar con Google' para iniciar sesión."
        )

    html_content = email_templates.aviso_recuperacion_google_template(
        locale_normalizado
    )
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
    """Construye el correo interno de reporte de perfil inapropiado.

    Se envía al buzón de moderación (``REPORTES_DESTINO``) en lugar de
    al usuario. Incluye versión texto plano con un resumen y versión
    HTML rica con tarjetas por motivo y observaciones escapadas.

    Args:
        usuario_reportante: nombre del usuario que lanza el reporte.
        usuario_reportado: nombre del usuario reportado.
        reportar_nombre: ``True`` si el motivo incluye el nombre.
        reportar_foto: ``True`` si el motivo incluye la foto.
        observaciones: texto libre opcional aportado por el reportante.
        smtp_username: dirección usada como remitente.

    Returns:
        Mensaje listo para enviar con ``_enviar_mensaje``.
    """
    # Construye mensaje reporte perfil.
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
    """Envía un ``EmailMessage`` con política de reintentos acotada.

    Intenta enviar hasta ``EMAIL_MAX_RETRIES`` veces con backoff. Usa
    ``_es_error_transitorio`` para decidir si un fallo merece reintento:
    timeouts y desconexiones reintentan; auth o destinatarios rechazados
    se abortan de inmediato para no gastar ciclos en algo imposible.

    Cada resultado se registra con un evento distinto (``evento_ok``,
    ``evento_error_permanente``, ``evento_error_transitorio``,
    ``evento_agotado``) para poder grepear en logs por tipo de correo.

    Args:
        msg: mensaje ya construido y con logo adjunto.
        destino_log: destinatario para registrar en los logs.
        evento_ok: clave de log al enviar con éxito.
        evento_error_permanente: clave de log ante errores que no se reintentan.
        evento_error_transitorio: clave de log por cada reintento tras fallo transitorio.
        evento_agotado: clave de log cuando se consumen todos los reintentos sin éxito.

    Returns:
        ``True`` si el envío termina con éxito; ``False`` si se agotan los reintentos o hay un error permanente.
    """
    # Envía mensaje.
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
    email_destino: str,
    codigo: str,
    minutos: int,
    locale: str,
) -> bool:
    """Construye y envía el email con el código de recuperación de contraseña.

    Combina ``_construir_mensaje_recuperacion`` y ``_enviar_mensaje``
    para que el servicio de acceso no tenga que conocer los detalles
    de SMTP ni de plantillas.

    Args:
        email_destino: dirección del usuario que solicitó recuperación.
        codigo: código numérico generado por el servicio de acceso.
        minutos: minutos de validez del código (para pluralizar y mostrar).
        locale: idioma preferido del usuario; se normaliza internamente.

    Returns:
        ``True`` si el correo se envía con éxito; ``False`` si falla definitivamente.
    """
    # Envía codigo recuperacion.
    msg = _construir_mensaje_recuperacion(
        email_destino,
        codigo,
        minutos,
        settings.EMAIL_USER,
        locale,
    )
    return await _enviar_mensaje(
        msg=msg,
        destino_log=email_destino,
        evento_ok="correo_recuperacion_enviado",
        evento_error_permanente="error_permanente_envio_correo_recuperacion",
        evento_error_transitorio="error_transitorio_envio_correo_recuperacion",
        evento_agotado="intentos_envio_correo_recuperacion_agotados",
    )


async def enviar_aviso_recuperacion_google(
    email_destino: str,
    locale: str,
) -> bool:
    """Envía el email que avisa al dueño de una cuenta Google sobre
    la solicitud de recuperación de contraseña.

    No da pistas de si la cuenta existe o no a terceros: el endpoint
    respondió ya de forma genérica, y aquí sólo el propio dueño del
    email ve la información del tipo de cuenta en su bandeja.

    Args:
        email_destino: dirección del usuario que solicitó la recuperación.
        locale: idioma preferido del usuario; se normaliza internamente.

    Returns:
        ``True`` si el correo se envía con éxito; ``False`` si falla.
    """
    msg = _construir_mensaje_aviso_google(
        email_destino,
        settings.EMAIL_USER,
        locale,
    )
    return await _enviar_mensaje(
        msg=msg,
        destino_log=email_destino,
        evento_ok="correo_aviso_recuperacion_google_enviado",
        evento_error_permanente="error_permanente_envio_correo_aviso_recuperacion_google",
        evento_error_transitorio="error_transitorio_envio_correo_aviso_recuperacion_google",
        evento_agotado="intentos_envio_correo_aviso_recuperacion_google_agotados",
    )


async def enviar_reporte_perfil_inapropiado(
    usuario_reportante: str,
    usuario_reportado: str,
    reportar_nombre: bool,
    reportar_foto: bool,
    observaciones: str | None,
) -> bool:
    """Envía el email interno de reporte de perfil al buzón de moderación.

    Reutiliza la misma maquinaria de reintento que el resto de emails,
    pero el destinatario es siempre ``REPORTES_DESTINO``, no el usuario.

    Args:
        usuario_reportante: nombre del usuario que lanza el reporte.
        usuario_reportado: nombre del usuario reportado.
        reportar_nombre: ``True`` si el motivo incluye el nombre.
        reportar_foto: ``True`` si el motivo incluye la foto.
        observaciones: texto libre opcional aportado por el reportante.

    Returns:
        ``True`` si el correo se envía con éxito; ``False`` si falla.
    """
    # Envía reporte perfil inapropiado.
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
