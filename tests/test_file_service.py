# tests/test_file_service.py
#
# Tests para services/file_service.py.
# Cubre: validar_seguridad, construir_url_foto, borrar_foto, _reencode_image.
#
# No necesitamos BD ni red: todas las funciones son síncronas y operan
# sobre contenido en memoria o sobre el sistema de archivos local.

import io
import os
import tempfile
from io import BytesIO
from unittest.mock import MagicMock, patch

import pytest
from fastapi import HTTPException
from PIL import Image

from services import file_service


# ─────────────────────────────────────────────
# Helpers compartidos
# ─────────────────────────────────────────────

class FakeUploadFile:
    """
    Simulacro mínimo de FastAPI UploadFile.
    Solo necesita .content_type y .file (file-like con seek/tell/read).
    """
    def __init__(self, content: bytes, content_type: str):
        self.content_type = content_type
        self.file = io.BytesIO(content)


def _make_jpeg_bytes(width: int = 100, height: int = 100) -> bytes:
    img = Image.new("RGB", (width, height), color=(200, 100, 50))
    buf = io.BytesIO()
    img.save(buf, format="JPEG")
    return buf.getvalue()


def _make_png_bytes(width: int = 100, height: int = 100) -> bytes:
    img = Image.new("RGBA", (width, height), color=(50, 100, 200, 255))
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def _make_rgba_bytes(width: int = 10, height: int = 10) -> bytes:
    img = Image.new("RGBA", (width, height), color=(100, 200, 50, 128))
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def _fake_request(base_url: str = "http://localhost:8000/") -> MagicMock:
    req = MagicMock()
    req.base_url = base_url
    return req


# ─────────────────────────────────────────────
# validar_seguridad — content-type
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
# validar_seguridad — tamaño
# ─────────────────────────────────────────────

class TestValidarTamano:
    def test_rechaza_archivo_superior_al_maximo(self):
        datos_grandes = b"\xff\xd8\xff" + b"x" * (file_service.MAX_IMAGE_BYTES + 1)
        archivo = FakeUploadFile(datos_grandes, "image/jpeg")
        with pytest.raises(HTTPException) as exc:
            file_service.validar_seguridad(archivo)  # type: ignore[arg-type]
        assert exc.value.status_code == 400
        assert "máximo" in exc.value.detail.lower()

    def test_acepta_imagen_dentro_del_limite(self):
        archivo = FakeUploadFile(_make_jpeg_bytes(), "image/jpeg")
        raw = file_service.validar_seguridad(archivo) # type: ignore[arg-type]
        assert isinstance(raw, bytes)
        assert raw


# ─────────────────────────────────────────────
# validar_seguridad — firmas maliciosas
# ─────────────────────────────────────────────

class TestValidarFirmasMaliciosas:
    def _archivo_con_firma(self, firma: bytes) -> FakeUploadFile:
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
# validar_seguridad — imagen real (Pillow)
# ─────────────────────────────────────────────

class TestValidarImagenReal:
    def test_rechaza_bytes_aleatorios_como_jpeg(self):
        basura = b"\xde\xad\xbe\xef" * 500
        archivo = FakeUploadFile(basura, "image/jpeg")
        with pytest.raises(HTTPException) as exc:
            file_service.validar_seguridad(archivo)  # type: ignore[arg-type]
        assert exc.value.status_code == 400
        assert "válida" in exc.value.detail.lower()

    def test_acepta_jpeg_valido(self):
        archivo = FakeUploadFile(_make_jpeg_bytes(), "image/jpeg")
        raw = file_service.validar_seguridad(archivo) # type: ignore[arg-type]
        assert isinstance(raw, bytes)
        assert raw

    def test_acepta_png_valido(self):
        archivo = FakeUploadFile(_make_png_bytes(), "image/png")
        raw = file_service.validar_seguridad(archivo) # type: ignore[arg-type]
        assert isinstance(raw, bytes)
        assert raw


# ─────────────────────────────────────────────
# validar_seguridad — anti decompression bomb
# ─────────────────────────────────────────────

class TestValidarDimensiones:
    def test_rechaza_imagen_con_demasiados_pixels(self):
        limite_original = file_service.MAX_IMAGE_PIXELS
        try:
            file_service.MAX_IMAGE_PIXELS = 1_000
            archivo = FakeUploadFile(_make_jpeg_bytes(width=40, height=40), "image/jpeg")
            with pytest.raises(HTTPException) as exc:
                file_service.validar_seguridad(archivo)  # type: ignore[arg-type]
            assert exc.value.status_code == 400
            assert "grande" in exc.value.detail.lower()
        finally:
            file_service.MAX_IMAGE_PIXELS = limite_original


# ─────────────────────────────────────────────
# construir_url_foto
# ─────────────────────────────────────────────

class TestConstruirUrlFoto:
    def test_none_devuelve_none(self):
        assert file_service.construir_url_foto(None, _fake_request()) is None

    def test_cadena_vacia_devuelve_none(self):
        assert file_service.construir_url_foto("", _fake_request()) is None

    def test_sentinel_devuelve_none(self):
        assert file_service.construir_url_foto("default_avatar.png", _fake_request()) is None

    def test_sentinel_en_ruta_larga_devuelve_none(self):
        ruta = "/uploads/perfil_abc/default_avatar.png"
        assert file_service.construir_url_foto(ruta, _fake_request()) is None

    def test_url_cloudinary_se_devuelve_tal_cual(self):
        url = "https://res.cloudinary.com/demo/image/upload/sample.jpg"
        assert file_service.construir_url_foto(url, _fake_request()) == url

    def test_url_http_se_devuelve_tal_cual(self):
        url = "http://cdn.example.com/foto.jpg"
        assert file_service.construir_url_foto(url, _fake_request()) == url

    def test_ruta_local_construye_url_completa(self):
        resultado = file_service.construir_url_foto(
            "perfil_abc123.jpg", _fake_request("http://localhost:8000/")
        )
        assert resultado == "http://localhost:8000/imagenes/perfil_abc123.jpg"

    def test_ruta_local_sin_barra_final_no_duplica_slash(self):
        resultado = file_service.construir_url_foto(
            "perfil_abc123.jpg", _fake_request("http://localhost:8000")
        )
        assert resultado is not None
        sin_protocolo = resultado.replace("http://", "").replace("https://", "")
        assert "//" not in sin_protocolo


# ─────────────────────────────────────────────
# borrar_foto
# ─────────────────────────────────────────────

class TestBorrarFoto:
    def test_none_no_hace_nada(self):
        file_service.borrar_foto(None, "pepe")  # type: ignore[arg-type]

    def test_cadena_vacia_no_hace_nada(self):
        file_service.borrar_foto("", "pepe")

    def test_sentinel_no_intenta_borrar(self):
        with patch("os.path.exists") as mock_exists:
            file_service.borrar_foto("default_avatar.png", "pepe")
        mock_exists.assert_not_called()

    def test_local_borra_archivo_existente(self):
        with tempfile.NamedTemporaryFile(suffix=".jpg", delete=False) as f:
            nombre = os.path.basename(f.name)
            f.write(b"fake")

        try:
            with patch.object(file_service.settings, "STORAGE_TYPE", "local"), \
                 patch.object(file_service.settings, "UPLOAD_DIR", tempfile.gettempdir()):
                file_service.borrar_foto(nombre, "pepe")
            assert not os.path.exists(f.name)
        finally:
            if os.path.exists(f.name):
                os.remove(f.name)

    def test_local_archivo_inexistente_no_explota(self):
        with patch.object(file_service.settings, "STORAGE_TYPE", "local"), \
             patch.object(file_service.settings, "UPLOAD_DIR", "/tmp"):
            file_service.borrar_foto("no_existe_jamas_xyz.jpg", "pepe")

    def test_cloudinary_llama_a_destroy(self):
        with patch.object(file_service.settings, "STORAGE_TYPE", "cloudinary"), \
             patch("cloudinary.uploader.destroy") as mock_destroy:
            file_service.borrar_foto("https://cloudinary.com/foto.jpg", "pepe")
        mock_destroy.assert_called_once()

    def test_cloudinary_fallo_no_propaga_excepcion(self):
        with patch.object(file_service.settings, "STORAGE_TYPE", "cloudinary"), \
             patch("cloudinary.uploader.destroy", side_effect=Exception("timeout")):
            file_service.borrar_foto("https://cloudinary.com/foto.jpg", "pepe")


# ─────────────────────────────────────────────
# _reencode_image
# ─────────────────────────────────────────────

class TestReencodeImage:
    def test_jpeg_rgb_produce_bytes_validos(self):
        raw = _make_jpeg_bytes()
        data = file_service._reencode_image(raw, ".jpg")
        assert Image.open(BytesIO(data)).format == "JPEG"

    def test_png_produce_bytes_validos(self):
        raw = _make_png_bytes()
        data = file_service._reencode_image(raw, ".png")
        assert Image.open(BytesIO(data)).format == "PNG"

    def test_rgba_a_jpeg_convierte_a_rgb(self):
        """JPEG no soporta alpha: RGBA debe convertirse a RGB sin error."""
        raw = _make_rgba_bytes()
        data = file_service._reencode_image(raw, ".jpg")
        assert Image.open(BytesIO(data)).mode == "RGB"

    def test_png_con_alpha_no_explota(self):
        raw = _make_rgba_bytes()
        data = file_service._reencode_image(raw, ".png")
        assert Image.open(BytesIO(data)).format == "PNG"

    def test_archivo_no_imagen_lanza_400(self):
        raw = b"esto no es una imagen"
        with pytest.raises(HTTPException) as exc:
            file_service._reencode_image(raw, ".jpg")
        assert exc.value.status_code == 400

    def test_imagen_reencodada_supera_limite_lanza_400(self):
        raw = _make_png_bytes()
        with patch.object(file_service, "MAX_IMAGE_BYTES", 1):
            with pytest.raises(HTTPException) as exc:
                file_service._reencode_image(raw, ".png")
        assert exc.value.status_code == 400


# ─────────────────────────────────────────────
# procesar_subida
# ─────────────────────────────────────────────

class TestProcesarSubida:
    def test_cloudinary_delega_a_guardar_nube(self):
        raw = _make_jpeg_bytes()
        archivo = FakeUploadFile(raw, "image/jpeg")
        with patch.object(file_service.settings, "STORAGE_TYPE", "cloudinary"), \
             patch.object(file_service, "guardar_nube", return_value="https://cdn.example.com/foto.jpg") as mock_nube, \
             patch.object(file_service, "guardar_local") as mock_local:
            resultado = file_service.procesar_subida(archivo, "pepe", raw) # type: ignore[arg-type]
        mock_nube.assert_called_once()
        mock_local.assert_not_called()
        assert resultado == "https://cdn.example.com/foto.jpg"

    def test_local_delega_a_guardar_local(self):
        raw = _make_jpeg_bytes()
        archivo = FakeUploadFile(raw, "image/jpeg")
        with patch.object(file_service.settings, "STORAGE_TYPE", "local"), \
             patch.object(file_service, "guardar_local", return_value="perfil_abc.jpg") as mock_local, \
             patch.object(file_service, "guardar_nube") as mock_nube:
            resultado = file_service.procesar_subida(archivo, "pepe", raw) # type: ignore[arg-type]
        mock_local.assert_called_once()
        mock_nube.assert_not_called()
        assert resultado == "perfil_abc.jpg"

    def test_foto_anterior_se_pasa_a_guardar_local(self):
        raw = _make_jpeg_bytes()
        archivo = FakeUploadFile(raw, "image/jpeg")
        with patch.object(file_service.settings, "STORAGE_TYPE", "local"), \
             patch.object(file_service, "guardar_local", return_value="nueva.jpg") as mock_local:
            file_service.procesar_subida(archivo, "pepe", raw, foto_anterior_bd="anterior.jpg")  # type: ignore[arg-type]
        # foto_anterior_bd puede llegar como arg posicional o kwarg
        args = mock_local.call_args.args
        assert "anterior.jpg" in args or mock_local.call_args.kwargs.get("foto_anterior_bd") == "anterior.jpg"


# ─────────────────────────────────────────────
# guardar_local
# ─────────────────────────────────────────────

class TestGuardarLocal:
    def test_guarda_jpeg_y_devuelve_nombre_archivo(self):
        raw = _make_jpeg_bytes()
        archivo = FakeUploadFile(raw, "image/jpeg")
        with tempfile.TemporaryDirectory() as tmpdir:
            with patch.object(file_service.settings, "UPLOAD_DIR", tmpdir):
                nombre = file_service.guardar_local(archivo, "pepe", raw) # type: ignore[arg-type]
        assert nombre.endswith(".jpg")
        assert nombre.startswith("perfil_")

    def test_guarda_png_con_extension_correcta(self):
        raw = _make_png_bytes()
        archivo = FakeUploadFile(raw, "image/png")
        with tempfile.TemporaryDirectory() as tmpdir:
            with patch.object(file_service.settings, "UPLOAD_DIR", tmpdir):
                nombre = file_service.guardar_local(archivo, "pepe", raw) # type: ignore[arg-type]
        assert nombre.endswith(".png")

    def test_archivo_realmente_existe_en_disco(self):
        raw = _make_jpeg_bytes()
        archivo = FakeUploadFile(raw, "image/jpeg")
        with tempfile.TemporaryDirectory() as tmpdir:
            with patch.object(file_service.settings, "UPLOAD_DIR", tmpdir):
                nombre = file_service.guardar_local(archivo, "pepe", raw) # type: ignore[arg-type]
                ruta = os.path.join(tmpdir, nombre)
            assert os.path.exists(ruta)
            assert os.path.getsize(ruta) > 0

    def test_nombre_derivado_de_hash_usuario(self):
        """El mismo usuario siempre genera el mismo prefijo de hash."""
        import hashlib
        raw = _make_jpeg_bytes()
        archivo = FakeUploadFile(raw, "image/jpeg")
        hash_esperado = hashlib.sha256("pepe".encode()).hexdigest()
        with tempfile.TemporaryDirectory() as tmpdir:
            with patch.object(file_service.settings, "UPLOAD_DIR", tmpdir):
                nombre = file_service.guardar_local(archivo, "pepe", raw) # type: ignore[arg-type]
        assert hash_esperado in nombre

    def test_imagen_invalida_lanza_400(self):
        raw = b"esto no es imagen"
        archivo = FakeUploadFile(raw, "image/jpeg")
        with tempfile.TemporaryDirectory() as tmpdir:
            with patch.object(file_service.settings, "UPLOAD_DIR", tmpdir):
                with pytest.raises(HTTPException) as exc:
                    file_service.guardar_local(archivo, "pepe", raw)  # type: ignore[arg-type]
        assert exc.value.status_code == 400

    def test_error_escritura_lanza_500(self):
        raw = _make_jpeg_bytes()
        archivo = FakeUploadFile(raw, "image/jpeg")
        with patch.object(file_service.settings, "UPLOAD_DIR", "/ruta/que/no/existe/jamas"):
            with pytest.raises(HTTPException) as exc:
                file_service.guardar_local(archivo, "pepe", raw)  # type: ignore[arg-type]
        assert exc.value.status_code == 500


# ─────────────────────────────────────────────
# guardar_nube (Cloudinary)
# ─────────────────────────────────────────────

class TestGuardarNube:
    def _raw_jpeg(self) -> bytes:
        return _make_jpeg_bytes()

    def _archivo_jpeg(self) -> FakeUploadFile:
        return FakeUploadFile(_make_jpeg_bytes(), "image/jpeg")

    def test_exito_devuelve_secure_url(self):
        with patch("cloudinary.uploader.upload", return_value={"secure_url": "https://res.cloudinary.com/foto.jpg"}):
            raw = self._raw_jpeg()
            archivo = FakeUploadFile(raw, "image/jpeg")
            resultado = file_service.guardar_nube(archivo, "pepe", raw) # type: ignore[arg-type]
        assert resultado == "https://res.cloudinary.com/foto.jpg"

    def test_cloudinary_sin_secure_url_lanza_500(self):
        """BUG 2: si Cloudinary devuelve dict sin secure_url debe ser 500, no None en BD."""
        with patch("cloudinary.uploader.upload", return_value={"public_id": "perfiles/perfil_abc"}):
            with pytest.raises(HTTPException) as exc:
                raw = self._raw_jpeg()
                archivo = FakeUploadFile(raw, "image/jpeg")
                file_service.guardar_nube(archivo, "pepe", raw)  # type: ignore[arg-type]
        assert exc.value.status_code == 500

    def test_cloudinary_fallo_de_red_lanza_500(self):
        with patch("cloudinary.uploader.upload", side_effect=Exception("timeout")):
            with pytest.raises(HTTPException) as exc:
                raw = self._raw_jpeg()
                archivo = FakeUploadFile(raw, "image/jpeg")
                file_service.guardar_nube(archivo, "pepe", raw)  # type: ignore[arg-type]
        assert exc.value.status_code == 500

    def test_imagen_invalida_lanza_400_no_500(self):
        """BUG 1: HTTPException(400) de _reencode_image NO debe convertirse en 500."""
        raw = b"basura"
        archivo = FakeUploadFile(raw, "image/jpeg")
        with pytest.raises(HTTPException) as exc:
            file_service.guardar_nube(archivo, "pepe", raw)  # type: ignore[arg-type]
        assert exc.value.status_code == 400

    def test_public_id_usa_hash_del_usuario(self):
        """El public_id en Cloudinary debe ser determinista y basado en el usuario."""
        import hashlib
        hash_esperado = hashlib.sha256("pepe".encode()).hexdigest()
        public_id_esperado = f"perfil_{hash_esperado}"

        capturado = {}
        def fake_upload(data, **kwargs):
            capturado.update(kwargs)
            return {"secure_url": "https://res.cloudinary.com/foto.jpg"}

        with patch("cloudinary.uploader.upload", side_effect=fake_upload):
            raw = self._raw_jpeg()
            archivo = FakeUploadFile(raw, "image/jpeg")
            file_service.guardar_nube(archivo, "pepe", raw)  # type: ignore[arg-type]

        assert capturado.get("public_id") == public_id_esperado

    def test_overwrite_true_en_upload(self):
        """Cloudinary debe usar overwrite=True para que solo haya una foto por usuario."""
        capturado = {}
        def fake_upload(data, **kwargs):
            capturado.update(kwargs)
            return {"secure_url": "https://res.cloudinary.com/foto.jpg"}

        with patch("cloudinary.uploader.upload", side_effect=fake_upload):
            raw = self._raw_jpeg()
            archivo = FakeUploadFile(raw, "image/jpeg")
            file_service.guardar_nube(archivo, "pepe", raw)  # type: ignore[arg-type]

        assert capturado.get("overwrite") is True
        