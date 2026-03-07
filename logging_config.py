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
    Emite JSON real y además añade un campo `display`
    para lectura humana con separador `|`.
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

        payload["display"] = self._build_display(
            level=record.levelname,
            timestamp=timestamp,
            logger_name=record.name,
            message=message,
            request_id=request_id,
            extras=extras,
        )

        return json.dumps(payload, ensure_ascii=False, default=str)

    def _get_extras(self, record: logging.LogRecord) -> dict[str, Any]:
        extras: dict[str, Any] = {}

        for key, value in record.__dict__.items():
            if key in _STANDARD_LOG_RECORD_KEYS:
                continue
            extras[key] = value

        return extras

    def _build_display(
        self,
        level: str,
        timestamp: str,
        logger_name: str,
        message: str,
        request_id: str,
        extras: dict[str, Any],
    ) -> str:
        partes = [
            level,
            timestamp,
            logger_name,
            message,
            f"request_id={request_id}",
        ]

        for key, value in extras.items():
            partes.append(f"{key}={value}")

        return " | ".join(partes)


def setup_logging() -> None:
    handler = logging.StreamHandler(sys.stdout)
    handler.addFilter(RequestIdFilter())
    handler.setFormatter(JsonPipeFormatter())

    root = logging.getLogger()
    root.handlers.clear()

    log_level_name = getattr(settings, "LOG_LEVEL", "INFO")
    log_level = getattr(logging, str(log_level_name).upper(), logging.INFO)

    root.setLevel(log_level)
    root.addHandler(handler)
    