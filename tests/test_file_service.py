# tests/test_file_service.py
#
# Tests para la capa de validación de imágenes en services/file_service.py.
# No necesitamos BD ni red: validar_seguridad() es una función pura que
# opera sobre el contenido del fichero en memoria.
#
# Dependencias externas necesarias: Pillow (ya requerida por el proyecto).

import io
import logging

import pytest
from PIL import Image
from fastapi import HTTPException
from starlette.requests import Request

from services import file_service


# ─────────────────────────────────────────────
# Helper: FakeUploadFile
# ─────────────────────────────────────────────

class FakeUploadFile:
    """
    Simulacro mínimo de FastAPI UploadFile para tests.
    Solo necesita .content_type y .file (file-like object con seek/tell/read).
    """

    def __init__(self, content: bytes, content_type: str):
        self.content_type = content_type
        self.file = io.BytesIO(content)


def _make_jpeg_bytes(width: int = 100, height: int = 100) -> bytes:
    """Crea una imagen JPEG válida en memoria con Pillow."""
    img = Image.new("RGB", (width, height), color=(200, 100, 50))
    buf = io.BytesIO()
    img.save(buf, format="JPEG")
    return buf.getvalue()


def _make_png_bytes(width: int = 100, height: int = 100) -> bytes:
    """Crea una imagen PNG válida en memoria con Pillow."""
    img = Image.new("RGBA", (width, height), color=(50, 100, 200, 255))
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def _make_request(
    scheme: str = "https",
    host: str = "api.moveon.test",
    port: int = 443,
) -> Request:
    """Construye un Request mínimo para probar construir_url_foto()."""
    scope = {
        "type": "http",
        "http_version": "1.1",
        "method": "GET",
        "scheme": scheme,
        "path": "/",
        "raw_path": b"/",
        "query_string": b"",
        "headers": [],
        "client": ("127.0.0.1", 12345),
        "server": (host, port),
        "root_path": "",
    }
    return Request(scope)


# ─────────────────────────────────────────────
# Content-type
# ─────────────────────────────────────────────

class TestValidarContentType:
    def test_rechaza_pdf(self):
        archivo = FakeUploadFile(b"%PDF-1.4", "application/pdf")
        with pytest.raises(HTTPException) as exc:
            file_service.validar_seguridad(archivo)  # type: ignore[arg-type]
        assert exc.value.status_code == 400
        assert "JPG" in exc.value.detail or "PNG" in exc.value.detail

    def test_rechaza_gif(self):
        archivo = FakeUploadFile(b"GIF89a", "image/gif")
        with pytest.raises(HTTPException) as exc:
            file_service.validar_seguridad(archivo)  # type: ignore[arg-type]
        assert exc.value.status_code == 400

    def test_rechaza_content_type_vacio(self):
        archivo = FakeUploadFile(b"cualquier cosa", "")
        with pytest.raises(HTTPException):
            file_service.validar_seguridad(archivo)  # type: ignore[arg-type]


# ─────────────────────────────────────────────
# Tamaño
# ─────────────────────────────────────────────

class TestValidarTamano:
    def test_rechaza_archivo_superior_al_maximo(self):
        # Creamos un blob que excede MAX_IMAGE_BYTES (por defecto 2MB)
        datos_grandes = b"\xff\xd8\xff" + b"x" * (file_service.MAX_IMAGE_BYTES + 1)
        archivo = FakeUploadFile(datos_grandes, "image/jpeg")
        with pytest.raises(HTTPException) as exc:
            file_service.validar_seguridad(archivo)  # type: ignore[arg-type]
        assert exc.value.status_code == 400
        assert "máximo" in exc.value.detail.lower()

    def test_acepta_imagen_dentro_del_limite(self):
        # Una imagen JPEG real de 100x100 pesa ~2KB, muy por debajo de 2MB
        jpeg = _make_jpeg_bytes()
        archivo = FakeUploadFile(jpeg, "image/jpeg")
        resultado = file_service.validar_seguridad(archivo)  # type: ignore[arg-type]
        assert resultado is True


# ─────────────────────────────────────────────
# Firmas maliciosas
# ─────────────────────────────────────────────

class TestValidarFirmasMaliciosas:
    def _archivo_con_firma(self, firma: bytes) -> FakeUploadFile:
        """Construye un 'archivo' que pasa el check de tamaño pero contiene firma maliciosa."""
        contenido = b"\x00" * 10 + firma + b"\x00" * 10
        return FakeUploadFile(contenido, "image/jpeg")

    def test_rechaza_script_tag(self):
        archivo = self._archivo_con_firma(b"<script>")
        with pytest.raises(HTTPException) as exc:
            file_service.validar_seguridad(archivo)  # type: ignore[arg-type]
        assert exc.value.status_code == 400
        assert "malicioso" in exc.value.detail.lower()

    def test_rechaza_eval_php(self):
        archivo = self._archivo_con_firma(b"<%eval")
        with pytest.raises(HTTPException) as exc:
            file_service.validar_seguridad(archivo)  # type: ignore[arg-type]
        assert exc.value.status_code == 400

    def test_rechaza_javascript_protocol(self):
        archivo = self._archivo_con_firma(b"javascript:")
        with pytest.raises(HTTPException) as exc:
            file_service.validar_seguridad(archivo)  # type: ignore[arg-type]
        assert exc.value.status_code == 400


# ─────────────────────────────────────────────
# Validación de imagen real
# ─────────────────────────────────────────────

class TestValidarImagenReal:
    def test_rechaza_bytes_aleatorios_como_jpeg(self):
        """Content-type dice JPEG pero el contenido es basura aleatoria."""
        basura = b"\xde\xad\xbe\xef" * 500
        archivo = FakeUploadFile(basura, "image/jpeg")
        with pytest.raises(HTTPException) as exc:
            file_service.validar_seguridad(archivo)  # type: ignore[arg-type]
        assert exc.value.status_code == 400
        assert "válida" in exc.value.detail.lower()

    def test_acepta_jpeg_valido(self):
        jpeg = _make_jpeg_bytes()
        archivo = FakeUploadFile(jpeg, "image/jpeg")
        assert file_service.validar_seguridad(archivo) is True  # type: ignore[arg-type]

    def test_acepta_png_valido(self):
        png = _make_png_bytes()
        archivo = FakeUploadFile(png, "image/png")
        assert file_service.validar_seguridad(archivo) is True  # type: ignore[arg-type]


# ─────────────────────────────────────────────
# Anti decompression bomb
# ─────────────────────────────────────────────

class TestValidarDimensiones:
    def test_rechaza_imagen_con_demasiados_pixels(self):
        """
        Verifica que imágenes con más de MAX_IMAGE_PIXELS sean rechazadas.
        Usamos un límite artificialmente bajo en el test para no crear
        una imagen enorme en memoria.
        """
        limite_original = file_service.MAX_IMAGE_PIXELS
        try:
            file_service.MAX_IMAGE_PIXELS = 1_000

            imagen_grande = _make_jpeg_bytes(width=40, height=40)
            archivo = FakeUploadFile(imagen_grande, "image/jpeg")

            with pytest.raises(HTTPException) as exc:
                file_service.validar_seguridad(archivo)  # type: ignore[arg-type]
            assert exc.value.status_code == 400
            assert "grande" in exc.value.detail.lower()
        finally:
            file_service.MAX_IMAGE_PIXELS = limite_original


# ─────────────────────────────────────────────
# Construcción de URL de foto
# ─────────────────────────────────────────────

class TestConstruirUrlFoto:
    def test_construir_url_foto_local_construye_url_completa(self):
        request = _make_request(scheme="https", host="api.moveon.test", port=443)

        url = file_service.construir_url_foto("perfil_abc123.jpg", request)

        assert url == "https://api.moveon.test/imagenes/perfil_abc123.jpg"

    def test_construir_url_foto_http_se_devuelve_tal_cual(self):
        request = _make_request()

        original = "https://res.cloudinary.com/demo/image/upload/v1/perfiles/perfil_x.jpg"
        url = file_service.construir_url_foto(original, request)

        assert url == original


# ─────────────────────────────────────────────
# Logging de borrado
# ─────────────────────────────────────────────

class TestBorrarFoto:
    def test_borrar_foto_cloudinary_fallido_loguea_warning(self, monkeypatch, caplog):
        monkeypatch.setattr(file_service.settings, "STORAGE_TYPE", "cloudinary")

        def fake_destroy(*args, **kwargs):
            raise RuntimeError("boom")

        monkeypatch.setattr(file_service.cloudinary.uploader, "destroy", fake_destroy)

        with caplog.at_level(logging.WARNING, logger="app.files"):
            file_service.borrar_foto(
                "https://res.cloudinary.com/demo/image/upload/v1/perfiles/perfil_x.jpg",
                "pepe",
            )

        assert "cloudinary" in caplog.text.lower()