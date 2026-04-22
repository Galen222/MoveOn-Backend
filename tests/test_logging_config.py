# tests/test_logging_config.py

"""Verifica los filtros y formateadores del subsistema de logging.

Estas pruebas comprueban la inyección del ``request_id``, la salida JSON y
texto plano, y la configuración final de loggers según el modo elegido.
"""

# Cubre:
# - RequestIdFilter
# - JsonPipeFormatter
# - ConsolePipeFormatter
# - setup_logging

import json
import logging
import re
import sys

import logging_config


ANSI_RE = re.compile(r"\x1b\[[0-9;]*m")


def strip_ansi(text: str) -> str:
    """Elimina secuencias ANSI para poder comparar texto de consola en bruto.

    Los tests del formateador de consola verifican el contenido semántico del
    log sin depender de códigos de color.
    """
    return ANSI_RE.sub("", text)


class TestRequestIdFilter:
    """Comprueba el filtro que inyecta ``request_id`` en cada ``LogRecord``.

    Así se garantiza que el resto de formateadores pueda apoyarse en ese dato
    aunque el mensaje original no lo incluya.
    """

    def test_inyecta_request_id_en_record(self, monkeypatch):
        """Verifica que el filtro copia al record el identificador expuesto por el contexto.

        Este comportamiento es la base para correlacionar todas las líneas de log
        de una misma petición HTTP.
        """
        monkeypatch.setattr(logging_config, "get_request_id", lambda: "req-123")

        record = logging.LogRecord(
            name="app.test",
            level=logging.INFO,
            pathname=__file__,
            lineno=10,
            msg="hola",
            args=(),
            exc_info=None,
        )

        filtro = logging_config.RequestIdFilter()
        assert filtro.filter(record) is True
        assert getattr(record, "request_id") == "req-123"


class TestJsonPipeFormatter:
    """Cubre la serialización estructurada en JSON del logger de aplicación.

    Las pruebas validan campos base, extras permitidos y cómo se representa una
    traza cuando el record incluye ``exc_info``.
    """

    def test_formatea_json_sin_display_y_con_extras(self):
        """Comprueba que el formatter emite JSON limpio con extras relevantes del record.

        Además verifica que no se cuele el campo ``display`` usado solo en otros
        formatos de salida.
        """
        formatter = logging_config.JsonPipeFormatter()

        record = logging.LogRecord(
            name="app.test",
            level=logging.INFO,
            pathname=__file__,
            lineno=20,
            msg="evento_ok",
            args=(),
            exc_info=None,
        )
        setattr(record, "request_id", "req-abc")
        setattr(record, "method", "GET")
        setattr(record, "path", "/healthz")
        setattr(record, "status_code", 200)

        out = formatter.format(record)
        payload = json.loads(out)

        assert payload["level"] == "INFO"
        assert payload["logger"] == "app.test"
        assert payload["message"] == "evento_ok"
        assert payload["request_id"] == "req-abc"
        assert payload["method"] == "GET"
        assert payload["path"] == "/healthz"
        assert payload["status_code"] == 200
        assert "display" not in payload

    def test_incluye_exception_si_hay_exc_info(self):
        """Asegura que las excepciones viajan serializadas cuando el record trae ``exc_info``.

        El objetivo es no perder la traza en logs estructurados consumidos por
        plataformas externas.
        """
        formatter = logging_config.JsonPipeFormatter()

        try:
            raise ValueError("boom")
        except ValueError:
            record = logging.LogRecord(
                name="app.test",
                level=logging.ERROR,
                pathname=__file__,
                lineno=40,
                msg="evento_error",
                args=(),
                exc_info=sys.exc_info(),
            )
            setattr(record, "request_id", "req-err")

        out = formatter.format(record)
        payload = json.loads(out)

        assert payload["level"] == "ERROR"
        assert payload["message"] == "evento_error"
        assert payload["request_id"] == "req-err"
        assert "exception" in payload
        assert "ValueError: boom" in payload["exception"]


class TestConsolePipeFormatter:
    """Comprueba el formatter de consola inspirado en el estilo de Uvicorn.

    La suite protege la línea legible para desarrollo, incluyendo extras útiles
    y la representación de excepciones.
    """

    def test_formatea_texto_plano_tipo_uvicorn_con_extras(self):
        """Verifica la línea de texto plano generada para un record informativo con extras.

        Se fija el timestamp para que la aserción compare solo el formato final y
        no la hora real de ejecución.
        """
        formatter = logging_config.ConsolePipeFormatter()
        formatter.formatTime = lambda record, datefmt=None: "2026-03-08 13:10:00"

        record = logging.LogRecord(
            name="app.main",
            level=logging.INFO,
            pathname=__file__,
            lineno=20,
            msg="aplicacion_iniciada",
            args=(),
            exc_info=None,
        )
        setattr(record, "request_id", "abc123")
        setattr(record, "storage_type", "local")

        out = formatter.format(record)

        assert strip_ansi(out) == (
            "INFO:     2026-03-08 13:10:00 | app.main | aplicacion_iniciada | "
            "request_id=abc123 | storage_type=local"
        )

    def test_incluye_exception_si_hay_exc_info(self):
        """Comprueba que una excepción se adjunta al formato de consola cuando existe ``exc_info``.

        Esto evita que el modo legible oculte información clave de depuración.
        """
        formatter = logging_config.ConsolePipeFormatter()
        formatter.formatTime = lambda record, datefmt=None: "2026-03-08 13:10:00"

        try:
            raise ValueError("boom")
        except ValueError:
            record = logging.LogRecord(
                name="app.test",
                level=logging.ERROR,
                pathname=__file__,
                lineno=40,
                msg="evento_error",
                args=(),
                exc_info=sys.exc_info(),
            )
            setattr(record, "request_id", "req-err")

        out = formatter.format(record)
        out_clean = strip_ansi(out)

        assert (
            "ERROR:    2026-03-08 13:10:00 | app.test | evento_error | request_id=req-err"
            in out_clean
        )
        assert "ValueError: boom" in out_clean

    def test_no_incluye_task_name_como_extra(self):
        """Asegura que ``task_name`` no se duplica como extra visible en consola.

        El formatter debe reservar ese dato para el formato interno sin ensuciar
        la línea principal que ve el desarrollador.
        """
        formatter = logging_config.ConsolePipeFormatter()
        formatter.formatTime = lambda record, datefmt=None: "2026-03-08 13:10:00"

        record = logging.LogRecord(
            name="app.main",
            level=logging.INFO,
            pathname=__file__,
            lineno=20,
            msg="evento_ok",
            args=(),
            exc_info=None,
        )
        setattr(record, "request_id", "abc123")
        setattr(record, "taskName", "Task-2")

        out = formatter.format(record)

        assert "taskName=Task-2" not in strip_ansi(out)


class TestSetupLogging:
    """Ejercita la configuración global de loggers y handlers del proyecto.

    Estas pruebas comprueban que ``setup_logging`` monta el formatter correcto
    según el modo JSON o consola.
    """

    def test_configura_logger_app_con_formatter_json(self, monkeypatch):
        """Verifica que el logger de aplicación recibe el formatter JSON en modo estructurado.

        Así se protege la configuración usada en entornos donde los logs se
        consumen por máquinas.
        """
        monkeypatch.setattr(logging_config.settings, "LOG_LEVEL", "DEBUG")
        monkeypatch.setattr(logging_config.settings, "LOG_FORMAT", "json")

        logger = logging.getLogger("app")
        old_handlers = logger.handlers[:]
        old_level = logger.level
        old_propagate = logger.propagate

        try:
            logging_config.setup_logging()

            logger = logging.getLogger("app")

            assert logger.level == logging.DEBUG
            assert logger.propagate is False
            assert len(logger.handlers) == 1

            handler = logger.handlers[0]
            assert isinstance(handler, logging.StreamHandler)
            assert isinstance(handler.formatter, logging_config.JsonPipeFormatter)
            assert any(
                isinstance(f, logging_config.RequestIdFilter) for f in handler.filters
            )
        finally:
            logger.handlers.clear()
            for h in old_handlers:
                logger.addHandler(h)
            logger.setLevel(old_level)
            logger.propagate = old_propagate

    def test_configura_logger_app_con_formatter_console(self, monkeypatch):
        """Comprueba que el logger monta el formatter legible cuando se pide modo consola.

        Con ello se evita una configuración cruzada entre producción y desarrollo.
        """
        monkeypatch.setattr(logging_config.settings, "LOG_LEVEL", "INFO")
        monkeypatch.setattr(logging_config.settings, "LOG_FORMAT", "console")

        logger = logging.getLogger("app")
        old_handlers = logger.handlers[:]
        old_level = logger.level
        old_propagate = logger.propagate

        try:
            logging_config.setup_logging()

            logger = logging.getLogger("app")

            assert logger.level == logging.INFO
            assert logger.propagate is False
            assert len(logger.handlers) == 1

            handler = logger.handlers[0]
            assert isinstance(handler, logging.StreamHandler)
            assert isinstance(handler.formatter, logging_config.ConsolePipeFormatter)
            assert any(
                isinstance(f, logging_config.RequestIdFilter) for f in handler.filters
            )
        finally:
            logger.handlers.clear()
            for h in old_handlers:
                logger.addHandler(h)
            logger.setLevel(old_level)
            logger.propagate = old_propagate
