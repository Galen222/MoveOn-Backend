# logging_config.py

"""Módulo relacionado con registro configuración."""

import json
import logging
import sys
from typing import Any

try:
    import colorama

    colorama.just_fix_windows_console()
except Exception:
    pass

from config import settings
from middlewares.request_context import get_request_id

RESET = "\033[0m"
GREEN = "\033[32m"
YELLOW = "\033[33m"
RED = "\033[31m"
CYAN = "\033[36m"

_STANDARD_LOG_RECORD_KEYS = {
    "name",
    "msg",
    "args",
    "levelname",
    "levelno",
    "pathname",
    "filename",
    "module",
    "exc_info",
    "exc_text",
    "stack_info",
    "lineno",
    "funcName",
    "created",
    "msecs",
    "relativeCreated",
    "thread",
    "threadName",
    "processName",
    "process",
    "message",
    "asctime",
    "request_id",
    "taskName",
    "color_message",
}


def _color(text: str, color: str) -> str:
    """Envuelve un texto en códigos ANSI de color y reset.

    Se usa sólo por el formateador de consola. El reset explícito al
    final impide que el color se quede "pegado" a campos posteriores
    si el terminal no limpia entre líneas.

    Args:
        text: texto a colorear.
        color: código ANSI de apertura (p. ej. ``\033[32m`` para verde).

    Returns:
        Texto coloreado seguido del código ANSI de reset.
    """
    return f"{color}{text}{RESET}"


def _level_prefix(levelname: str) -> str:
    """Construye el prefijo de nivel con color y alineación fija (10 cols).

    Imita el estilo de uvicorn: el nivel queda coloreado pero la columna
    total (``nivel:<espacios>``) siempre tiene 10 caracteres visibles
    para que el resto de la línea esté alineado.

    Args:
        levelname: nivel de log estándar de Python (``INFO``, ``WARNING``...).

    Returns:
        Prefijo coloreado si el nivel es conocido, o la versión sin color si no.
    """
    # Gestiona level prefix.
    plain = f"{levelname}:".ljust(10)

    if levelname == "INFO":
        color = GREEN
    elif levelname == "WARNING":
        color = YELLOW
    elif levelname in {"ERROR", "CRITICAL"}:
        color = RED
    elif levelname == "DEBUG":
        color = CYAN
    else:
        return plain

    word = levelname
    suffix_and_padding = plain[len(word) :]
    return f"{color}{word}{RESET}{suffix_and_padding}"


def _format_extra(key: str, value: Any) -> str:
    """Da formato a un campo "extra" del log para la consola.

    Si el campo es ``status_code`` se colorea en verde para 2xx/3xx y
    en rojo para 4xx/5xx, para que inspeccionar logs a ojo sea rápido.
    El resto de campos se emite como ``clave=valor`` sin color.

    Args:
        key: nombre del campo extra tal como se pasó a ``logger.log(..., extra=...)``.
        value: valor asociado.

    Returns:
        Cadena ``clave=valor`` lista para concatenar en la línea de log.
    """
    if key == "status_code":
        try:
            code = int(value)
        except (TypeError, ValueError):
            return f"{key}={value}"

        if 200 <= code < 400:
            return f"{key}={_color(str(code), GREEN)}"
        if 400 <= code < 600:
            return f"{key}={_color(str(code), RED)}"
        return f"{key}={code}"

    return f"{key}={value}"


class RequestIdFilter(logging.Filter):
    """Filtro para request identificador."""

    def filter(self, record: logging.LogRecord) -> bool:
        """Inyecta el ``request_id`` de la petición en curso en cada ``LogRecord``.

        Lo toma del contexto de petición gestionado por ``RequestContextMiddleware``
        (``contextvar``), de forma que los logs emitidos durante el
        procesamiento de una petición puedan correlacionarse por su id.

        Args:
            record: registro de log a enriquecer.

        Returns:
            ``True`` siempre (el filtro nunca descarta logs; solo añade metadata).
        """
        record.request_id = get_request_id()
        return True


class JsonPipeFormatter(logging.Formatter):
    """
    Emite JSON real para logs de servidor.
    No añade campo `display`.
    """

    def format(self, record: logging.LogRecord) -> str:
        """Serializa un ``LogRecord`` como JSON para consumo de agregadores.

        Emite un único objeto por línea con ``level``, ``timestamp``,
        ``logger``, ``message``, ``request_id`` y todos los ``extras`` del
        record. Si la excepción viene asociada, añade también ``exception``
        con el traceback formateado. Usa ``default=str`` para que objetos no
        serializables (p. ej. UUIDs, datetimes, Decimal) no rompan la línea.

        Args:
            record: registro de log generado por el logger.

        Returns:
            Cadena JSON con todos los campos relevantes; un solo objeto por línea.
        """
        # Gestiona format.
        timestamp = self.formatTime(record, "%Y-%m-%d %H:%M:%S")
        message = record.getMessage()
        request_id = getattr(record, "request_id", "-")
        extras = self._get_extras(record)

        payload: dict[str, Any] = {
            "level": record.levelname,
            "timestamp": timestamp,
            "logger": record.name,
            "message": message,
            "request_id": request_id,
        }

        payload.update(extras)

        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)

        return json.dumps(payload, ensure_ascii=False, default=str)

    def _get_extras(self, record: logging.LogRecord) -> dict[str, Any]:
        """Extrae los campos personalizados de un ``LogRecord``.

        Itera sobre ``record.__dict__`` descartando las claves estándar
        que Python pone en todos los records (thread, module, lineno...),
        de forma que el resto son los ``extra`` que el llamador pasó a
        ``logger.log(..., extra={...})``.

        Args:
            record: registro de log del que se extraen los extras.

        Returns:
            Diccionario con sólo los campos personalizados del log.
        """
        extras: dict[str, Any] = {}

        for key, value in record.__dict__.items():
            if key in _STANDARD_LOG_RECORD_KEYS:
                continue
            extras[key] = value

        return extras


class ConsolePipeFormatter(logging.Formatter):
    """
    Emite texto plano para consola interactiva con formato tipo uvicorn:
    INFO:     2026-03-08 13:10:00 | app.main | aplicacion_iniciada | petición_id=abc123
    """

    def format(self, record: logging.LogRecord) -> str:
        """Serializa un ``LogRecord`` como línea legible estilo uvicorn.

        Produce algo como:

            INFO:     2026-03-08 13:10:00 | app.main | aplicacion_iniciada | request_id=abc123

        Añade cada extra como ``clave=valor``, saltando los que sean
        ``None`` para no ensuciar la línea. Si hay excepción asociada,
        imprime el traceback debajo.

        Args:
            record: registro de log generado por el logger.

        Returns:
            Cadena formateada lista para imprimir en consola.
        """
        # Gestiona format.
        timestamp = self.formatTime(record, "%Y-%m-%d %H:%M:%S")
        message = record.getMessage()
        request_id = getattr(record, "request_id", "-")
        extras = self._get_extras(record)

        partes = [
            f"{_level_prefix(record.levelname)}{timestamp}",
            record.name,
            message,
            f"request_id={request_id}",
        ]

        for key, value in extras.items():
            if value is not None:
                partes.append(_format_extra(key, value))

        out = " | ".join(partes)

        if record.exc_info:
            out += "\n" + self.formatException(record.exc_info)

        return out

    def _get_extras(self, record: logging.LogRecord) -> dict[str, Any]:
        """Misma extracción de extras que ``JsonPipeFormatter._get_extras``.

        Se duplica en lugar de compartirse por herencia para mantener los
        dos formateadores totalmente independientes y evitar acoplar el
        contrato JSON con el de consola.

        Args:
            record: registro de log del que se extraen los extras.

        Returns:
            Diccionario con los campos personalizados del log.
        """
        extras: dict[str, Any] = {}

        for key, value in record.__dict__.items():
            if key in _STANDARD_LOG_RECORD_KEYS:
                continue
            extras[key] = value

        return extras


def setup_logging() -> None:
    """Configura el logger ``app`` y sus hijos con el formato elegido.

    Lee ``settings.LOG_FORMAT`` (``console`` o ``json``) y
    ``settings.LOG_LEVEL`` para decidir formateador y verbosidad. Limpia
    handlers previos para que llamar varias veces a esta función en
    tests no duplique salidas, y pone ``propagate=False`` para que los
    logs de ``app.*`` no se doblen con el root logger.

    Returns:
        ``None``. El efecto es la configuración global del logging.
    """
    # Gestiona setup registro.
    handler = logging.StreamHandler(sys.stdout)
    handler.addFilter(RequestIdFilter())

    log_format_name = str(getattr(settings, "LOG_FORMAT", "json")).strip().lower()

    if log_format_name == "console":
        handler.setFormatter(ConsolePipeFormatter())
    else:
        handler.setFormatter(JsonPipeFormatter())

    log_level_name = getattr(settings, "LOG_LEVEL", "INFO")
    log_level = getattr(logging, str(log_level_name).upper(), logging.INFO)

    app_logger = logging.getLogger("app")
    app_logger.handlers.clear()
    app_logger.setLevel(log_level)
    app_logger.propagate = False
    app_logger.addHandler(handler)
