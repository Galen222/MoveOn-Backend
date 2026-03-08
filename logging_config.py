# logging_config.py

import json
import logging
import sys
from typing import Any

from config import settings
from middlewares.request_context import get_request_id


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
}


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
    INFO:     2026-03-08 13:10:00 | app.main | aplicacion_iniciando | request_id=abc123 | storage_type=local
    """

    def format(self, record: logging.LogRecord) -> str:
        timestamp = self.formatTime(record, "%Y-%m-%d %H:%M:%S")
        message = record.getMessage()
        request_id = getattr(record, "request_id", "-")
        extras = self._get_extras(record)

        level_prefix = f"{record.levelname}:".ljust(10)

        partes = [
            f"{level_prefix}{timestamp}",
            record.name,
            message,
            f"request_id={request_id}",
        ]

        for key, value in extras.items():
            if value is not None:
                partes.append(f"{key}={value}")

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

    root = logging.getLogger()
    root.handlers.clear()

    log_level_name = getattr(settings, "LOG_LEVEL", "INFO")
    log_level = getattr(logging, str(log_level_name).upper(), logging.INFO)

    root.setLevel(log_level)
    root.addHandler(handler)
    