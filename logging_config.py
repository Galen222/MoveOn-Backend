# logging_config.py

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
    return f"{color}{text}{RESET}"


def _level_prefix(levelname: str) -> str:
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
    def filter(self, record: logging.LogRecord) -> bool:
        record.request_id = get_request_id()
        return True


class JsonPipeFormatter(logging.Formatter):
    """
    Emite JSON real para logs de servidor.
    No añade campo `display`.
    """

    def format(self, record: logging.LogRecord) -> str:
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
        extras: dict[str, Any] = {}

        for key, value in record.__dict__.items():
            if key in _STANDARD_LOG_RECORD_KEYS:
                continue
            extras[key] = value

        return extras


class ConsolePipeFormatter(logging.Formatter):
    """
    Emite texto plano para consola interactiva con formato tipo uvicorn:
    INFO:     2026-03-08 13:10:00 | app.main | aplicacion_iniciada | request_id=abc123
    """

    def format(self, record: logging.LogRecord) -> str:
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
        extras: dict[str, Any] = {}

        for key, value in record.__dict__.items():
            if key in _STANDARD_LOG_RECORD_KEYS:
                continue
            extras[key] = value

        return extras


def setup_logging() -> None:
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
