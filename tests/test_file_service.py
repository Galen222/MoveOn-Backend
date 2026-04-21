# tests/test_file_service.py

"""Contiene pruebas automatizadas de este módulo."""

# Pruebas para services/file_service.py.
# Cubre: validar_seguridad, construir_url_foto, borrar_foto, _reencode_image,
# _strip_cloudinary_version, procesar_subida, guardar_local y guardar_nube.

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
# Ayudantes compartidos
# ─────────────────────────────────────────────


class FakeUploadFile:
    """
    Simulacro mínimo de FastAPI UploadFile.
    Solo necesita .content_type y .file (file-like con seek/tell/read).
    """

    def __init__(self, content: bytes, content_type: str):
        """Inicializa la instancia."""
        self.content_type = content_type
        self.file = io.BytesIO(content)


def _make_jpeg_bytes(width: int = 100, height: int = 100) -> bytes:
    """Construye bytes JPEG."""
    img = Image.new("RGB", (width, height), color=(200, 100, 50))
    buf = io.BytesIO()
    img.save(buf, format="JPEG")
    return buf.getvalue()


def _make_png_bytes(width: int = 100, height: int = 100) -> bytes:
    """Construye png bytes."""
    img = Image.new("RGBA", (width, height), color=(50, 100, 200, 255))
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def _make_rgba_bytes(width: int = 10, height: int = 10) -> bytes:
    """Construye rgba bytes."""
    img = Image.new("RGBA", (width, height), color=(100, 200, 50, 128))
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def _make_webp_bytes(width: int = 100, height: int = 100) -> bytes:
    """Construye webp bytes."""
    img = Image.new("RGB", (width, height), color=(120, 80, 220))
    buf = io.BytesIO()
    img.save(buf, format="WEBP")
    return buf.getvalue()


def _make_jpeg_with_exif_orientation() -> bytes:
    """Construye jpeg with exif orientation."""
    img = Image.new("RGB", (10, 20), color=(200, 100, 50))
    exif = Image.Exif()
    exif[274] = 6  # Orientation: rotate 90 CW
    buf = io.BytesIO()
    img.save(buf, format="JPEG", exif=exif)
    return buf.getvalue()


def _fake_request(base_url: str = "http://localhost:8000/") -> MagicMock:
    """Crea un simulacro de request."""
    req = MagicMock()
    req.base_url = base_url
    return req


# ─────────────────────────────────────────────
# validar_seguridad — content-type
# ─────────────────────────────────────────────


class TestValidarContentType:
    """Agrupa pruebas relacionadas con validar content type."""

    def test_rechaza_pdf(self):
        """Verifica que rechaza pdf."""
        archivo = FakeUploadFile(b"%PDF-1.4", "application/pdf")
        with pytest.raises(HTTPException) as exc:
            file_service.validar_seguridad(archivo)  # type: ignore[arg-type]
        assert exc.value.status_code == 400
        assert "JPG" in exc.value.detail or "PNG" in exc.value.detail

    def test_rechaza_gif(self):
        """Verifica que rechaza gif."""
        archivo = FakeUploadFile(b"GIF89a", "image/gif")
        with pytest.raises(HTTPException) as exc:
            file_service.validar_seguridad(archivo)  # type: ignore[arg-type]
        assert exc.value.status_code == 400

    def test_rechaza_content_type_vacio(self):
        """Verifica que rechaza content type vacio."""
        archivo = FakeUploadFile(b"cualquier cosa", "")
        with pytest.raises(HTTPException):
            file_service.validar_seguridad(archivo)  # type: ignore[arg-type]


# ─────────────────────────────────────────────
# validar_seguridad — tamaño
# ─────────────────────────────────────────────


class TestValidarTamano:
    """Agrupa pruebas relacionadas con validar tamano."""

    def test_rechaza_archivo_superior_al_maximo(self):
        """Verifica que rechaza archivo superior al maximo."""
        datos_grandes = b"\xff\xd8\xff" + b"x" * (file_service.MAX_IMAGE_BYTES + 1)
        archivo = FakeUploadFile(datos_grandes, "image/jpeg")
        with pytest.raises(HTTPException) as exc:
            file_service.validar_seguridad(archivo)  # type: ignore[arg-type]
        assert exc.value.status_code == 400
        assert "máximo" in exc.value.detail.lower()

    def test_acepta_imagen_dentro_del_limite(self):
        """Verifica que acepta imagen dentro del limite."""
        archivo = FakeUploadFile(_make_jpeg_bytes(), "image/jpeg")
        raw = file_service.validar_seguridad(archivo)  # type: ignore[arg-type]
        assert isinstance(raw, bytes)
        assert raw


# ─────────────────────────────────────────────
# validar_seguridad — firmas maliciosas
# ─────────────────────────────────────────────


class TestValidarFirmasMaliciosas:
    """Agrupa pruebas relacionadas con validar firmas maliciosas."""

    def _archivo_con_firma(self, firma: bytes) -> FakeUploadFile:
        """Gestiona archivo con firma."""
        contenido = b"\x00" * 10 + firma + b"\x00" * 10
        return FakeUploadFile(contenido, "image/jpeg")

    def test_rechaza_script_tag(self):
        """Verifica que rechaza script tag."""
        archivo = self._archivo_con_firma(b"<script>")
        with pytest.raises(HTTPException) as exc:
            file_service.validar_seguridad(archivo)  # type: ignore[arg-type]
        assert exc.value.status_code == 400
        assert "malicioso" in exc.value.detail.lower()

    def test_rechaza_eval_php(self):
        """Verifica que rechaza eval php."""
        archivo = self._archivo_con_firma(b"<%eval")
        with pytest.raises(HTTPException) as exc:
            file_service.validar_seguridad(archivo)  # type: ignore[arg-type]
        assert exc.value.status_code == 400

    def test_rechaza_javascript_protocol(self):
        """Verifica que rechaza javascript protocol."""
        archivo = self._archivo_con_firma(b"javascript:")
        with pytest.raises(HTTPException) as exc:
            file_service.validar_seguridad(archivo)  # type: ignore[arg-type]
        assert exc.value.status_code == 400


# ─────────────────────────────────────────────
# validar_seguridad — imagen real (Pillow)
# ─────────────────────────────────────────────


class TestValidarImagenReal:
    """Agrupa pruebas relacionadas con validar imagen real."""

    def test_rechaza_bytes_aleatorios_como_jpeg(self):
        """Verifica que rechaza bytes aleatorios como jpeg."""
        basura = b"\xde\xad\xbe\xef" * 500
        archivo = FakeUploadFile(basura, "image/jpeg")
        with pytest.raises(HTTPException) as exc:
            file_service.validar_seguridad(archivo)  # type: ignore[arg-type]
        assert exc.value.status_code == 400
        assert "válida" in exc.value.detail.lower()

    def test_acepta_jpeg_valido(self):
        """Verifica que acepta jpeg valido."""
        archivo = FakeUploadFile(_make_jpeg_bytes(), "image/jpeg")
        raw = file_service.validar_seguridad(archivo)  # type: ignore[arg-type]
        assert isinstance(raw, bytes)
        assert raw

    def test_acepta_png_valido(self):
        """Verifica que acepta png valido."""
        archivo = FakeUploadFile(_make_png_bytes(), "image/png")
        raw = file_service.validar_seguridad(archivo)  # type: ignore[arg-type]
        assert isinstance(raw, bytes)
        assert raw

    def test_acepta_webp_valido(self):
        """Verifica que acepta webp valido."""
        archivo = FakeUploadFile(_make_webp_bytes(), "image/webp")
        raw = file_service.validar_seguridad(archivo)  # type: ignore[arg-type]
        assert isinstance(raw, bytes)
        assert raw


# ─────────────────────────────────────────────
# validar_seguridad — anti decompression bomb
# ─────────────────────────────────────────────


class TestValidarDimensiones:
    """Agrupa pruebas relacionadas con validar dimensiones."""

    def test_rechaza_imagen_con_demasiados_pixels(self):
        """Verifica que rechaza imagen con demasiados pixels."""
        limite_original = file_service.MAX_IMAGE_PIXELS
        try:
            file_service.MAX_IMAGE_PIXELS = 1_000
            archivo = FakeUploadFile(
                _make_jpeg_bytes(width=40, height=40), "image/jpeg"
            )
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
    """Agrupa pruebas relacionadas con construir URL foto."""

    def test_none_devuelve_none(self):
        """Verifica que None devuelve None."""
        assert file_service.construir_url_foto(None, _fake_request()) is None

    def test_cadena_vacia_devuelve_none(self):
        """Verifica que una cadena vacía devuelve None."""
        assert file_service.construir_url_foto("", _fake_request()) is None

    def test_url_cloudinary_se_devuelve_tal_cual(self):
        """Verifica que URL cloudinary se devuelve tal cual."""
        url = "https://res.cloudinary.com/demo/image/upload/sample.jpg"
        assert file_service.construir_url_foto(url, _fake_request()) == url

    def test_url_http_se_devuelve_tal_cual(self):
        """Verifica que URL HTTP se devuelve tal cual."""
        url = "http://cdn.example.com/foto.jpg"
        assert file_service.construir_url_foto(url, _fake_request()) == url

    def test_ruta_local_construye_url_completa(self):
        """Verifica que ruta local construye URL completa."""
        resultado = file_service.construir_url_foto(
            "perfil_abc123.jpg", _fake_request("http://localhost:8000/")
        )
        assert resultado == "http://localhost:8000/imagenes/perfil_abc123.jpg"

    def test_ruta_local_sin_barra_final_no_duplica_slash(self):
        """Verifica que ruta local sin barra final no duplica slash."""
        resultado = file_service.construir_url_foto(
            "perfil_abc123.jpg", _fake_request("http://localhost:8000")
        )
        assert resultado == "http://localhost:8000/imagenes/perfil_abc123.jpg"

    def test_public_base_url_tiene_prioridad(self):
        """Verifica que public base URL tiene prioridad."""
        with patch.object(
            file_service.settings, "PUBLIC_BASE_URL", "https://api.moveon.com"
        ):
            resultado = file_service.construir_url_foto(
                "perfil_abc123.jpg", _fake_request("http://localhost:8000/")
            )
        assert resultado == "https://api.moveon.com/imagenes/perfil_abc123.jpg"

    def test_public_base_url_vacio_usa_request(self):
        """Cuando PUBLIC_BASE_URL está vacío, se usa request.base_url."""
        with patch.object(file_service.settings, "PUBLIC_BASE_URL", ""):
            resultado = file_service.construir_url_foto(
                "perfil_abc123.jpg", _fake_request("http://localhost:8000/")
            )
        assert resultado == "http://localhost:8000/imagenes/perfil_abc123.jpg"

    def test_public_base_url_no_afecta_urls_cloudinary(self):
        """Las URLs http(s) de Cloudinary se devuelven tal cual, sin importar PUBLIC_BASE_URL."""
        url_cloud = "https://res.cloudinary.com/demo/image/upload/sample.jpg"
        with patch.object(
            file_service.settings, "PUBLIC_BASE_URL", "https://api.moveon.com"
        ):
            resultado = file_service.construir_url_foto(url_cloud, _fake_request())
        assert resultado == url_cloud


# ─────────────────────────────────────────────
# borrar_foto
# ─────────────────────────────────────────────


class TestBorrarFoto:
    """Agrupa pruebas relacionadas con borrar foto."""

    def test_none_no_hace_nada(self):
        """Verifica que none no hace nada."""
        file_service.borrar_foto(None, 1)  # type: ignore[arg-type]

    def test_cadena_vacia_no_hace_nada(self):
        """Verifica que cadena vacia no hace nada."""
        file_service.borrar_foto("", 1)

    def test_local_borra_archivo_existente(self):
        """Verifica que local borra archivo existente."""
        with tempfile.NamedTemporaryFile(suffix=".jpg", delete=False) as f:
            nombre = os.path.basename(f.name)
            f.write(b"fake")

        try:
            with patch.object(
                file_service.settings, "STORAGE_TYPE", "local"
            ), patch.object(file_service.settings, "UPLOAD_DIR", tempfile.gettempdir()):
                file_service.borrar_foto(nombre, 1)
            assert not os.path.exists(f.name)
        finally:
            if os.path.exists(f.name):
                os.remove(f.name)

    def test_local_archivo_inexistente_no_explota(self):
        """Verifica que local archivo inexistente no explota."""
        with patch.object(file_service.settings, "STORAGE_TYPE", "local"), patch.object(
            file_service.settings, "UPLOAD_DIR", "/tmp"
        ):
            file_service.borrar_foto("no_existe_jamas_xyz.jpg", 1)

    def test_cloudinary_llama_a_destroy(self):
        """Verifica que cloudinary llama a destroy."""
        with patch.object(file_service.settings, "STORAGE_TYPE", "cloudinary"), patch(
            "cloudinary.uploader.destroy"
        ) as mock_destroy:
            file_service.borrar_foto("https://cloudinary.com/foto.jpg", 1)
        mock_destroy.assert_called_once()

    def test_cloudinary_fallo_no_propaga_excepcion(self):
        """Verifica que cloudinary fallo no propaga excepcion."""
        with patch.object(file_service.settings, "STORAGE_TYPE", "cloudinary"), patch(
            "cloudinary.uploader.destroy", side_effect=Exception("boom")
        ):
            file_service.borrar_foto("https://cloudinary.com/foto.jpg", 1)


# ─────────────────────────────────────────────
# _reencode_image
# ─────────────────────────────────────────────


class TestReencodeImage:
    """Agrupa pruebas relacionadas con reencode imagen."""

    def test_jpeg_rgb_produce_bytes_validos(self):
        """Verifica que jpeg rgb produce bytes validos."""
        raw = _make_jpeg_bytes()
        data = file_service._reencode_image(raw, ".jpg")
        assert Image.open(BytesIO(data)).format == "JPEG"

    def test_png_produce_bytes_validos(self):
        """Verifica que png produce bytes validos."""
        raw = _make_png_bytes()
        data = file_service._reencode_image(raw, ".png")
        assert Image.open(BytesIO(data)).format == "PNG"

    def test_rgba_a_jpeg_convierte_a_rgb(self):
        """JPEG no soporta alpha: RGBA debe convertirse a RGB sin error."""
        raw = _make_rgba_bytes()
        data = file_service._reencode_image(raw, ".jpg")
        assert Image.open(BytesIO(data)).mode == "RGB"

    def test_png_con_alpha_no_explota(self):
        """Verifica que png con alpha no explota."""
        raw = _make_rgba_bytes()
        data = file_service._reencode_image(raw, ".png")
        assert Image.open(BytesIO(data)).format == "PNG"

    def test_reencode_normaliza_orientacion_y_no_preserva_exif(self):
        """Verifica que reencode normaliza orientacion y no preserva exif."""
        raw = _make_jpeg_with_exif_orientation()

        data = file_service._reencode_image(raw, ".jpg")

        im = Image.open(BytesIO(data))

        # Tras exif_transpose, la imagen queda físicamente girada.
        assert im.size == (20, 10)

        # Y ya no debe depender del tag EXIF de orientación.
        assert im.getexif().get(274) is None

    def test_archivo_no_imagen_lanza_400(self):
        """Verifica que archivo no imagen lanza 400."""
        raw = b"esto no es una imagen"
        with pytest.raises(HTTPException) as exc:
            file_service._reencode_image(raw, ".jpg")
        assert exc.value.status_code == 400

    def test_imagen_reencodada_supera_limite_lanza_400(self):
        """Verifica que imagen reencodada supera limite lanza 400."""
        raw = _make_png_bytes()
        with patch.object(file_service, "MAX_IMAGE_BYTES", 1):
            with pytest.raises(HTTPException) as exc:
                file_service._reencode_image(raw, ".png")
        assert exc.value.status_code == 400


# ─────────────────────────────────────────────
# _strip_cloudinary_version
# ─────────────────────────────────────────────


class TestStripCloudinaryVersion:
    """Agrupa pruebas relacionadas con strip cloudinary version."""

    def test_quita_segmento_de_version(self):
        """Verifica que quita segmento de version."""
        url = (
            "https://res.cloudinary.com/demo/image/upload/v1712345678/perfiles/foto.jpg"
        )
        resultado = file_service._strip_cloudinary_version(url)
        assert (
            resultado
            == "https://res.cloudinary.com/demo/image/upload/perfiles/foto.jpg"
        )

    def test_si_no_hay_version_devuelve_igual(self):
        """Verifica que si no hay version devuelve igual."""
        url = "https://res.cloudinary.com/demo/image/upload/perfiles/foto.jpg"
        resultado = file_service._strip_cloudinary_version(url)
        assert resultado == url


# ─────────────────────────────────────────────
# procesar_subida
# ─────────────────────────────────────────────


class TestProcesarSubida:
    """Agrupa pruebas relacionadas con procesar subida."""

    def test_cloudinary_delega_a_guardar_nube(self):
        """Verifica que cloudinary delega a guardar nube."""
        raw = _make_jpeg_bytes()
        archivo = FakeUploadFile(raw, "image/jpeg")
        with patch.object(
            file_service.settings, "STORAGE_TYPE", "cloudinary"
        ), patch.object(
            file_service,
            "guardar_nube",
            return_value="https://cdn.example.com/foto.jpg",
        ) as mock_nube, patch.object(
            file_service, "guardar_local"
        ) as mock_local:
            resultado = file_service.procesar_subida(archivo, 1, raw)  # type: ignore[arg-type]
        mock_nube.assert_called_once()
        mock_local.assert_not_called()
        assert resultado == "https://cdn.example.com/foto.jpg"

    def test_local_delega_a_guardar_local(self):
        """Verifica que local delega a guardar local."""
        raw = _make_jpeg_bytes()
        archivo = FakeUploadFile(raw, "image/jpeg")
        with patch.object(file_service.settings, "STORAGE_TYPE", "local"), patch.object(
            file_service, "guardar_local", return_value="perfil_abc.jpg"
        ) as mock_local, patch.object(file_service, "guardar_nube") as mock_nube:
            resultado = file_service.procesar_subida(archivo, 1, raw)  # type: ignore[arg-type]
        mock_local.assert_called_once()
        mock_nube.assert_not_called()
        assert resultado == "perfil_abc.jpg"

    def test_foto_anterior_se_pasa_a_guardar_local(self):
        """Verifica que foto anterior se pasa a guardar local."""
        raw = _make_jpeg_bytes()
        archivo = FakeUploadFile(raw, "image/jpeg")
        with patch.object(file_service.settings, "STORAGE_TYPE", "local"), patch.object(
            file_service, "guardar_local", return_value="nueva.jpg"
        ) as mock_local:
            file_service.procesar_subida(archivo, 1, raw, foto_anterior_bd="anterior.jpg")  # type: ignore[arg-type]
        # foto_anterior_bd puede llegar como arg posicional o kwarg
        args = mock_local.call_args.args
        assert (
            "anterior.jpg" in args
            or mock_local.call_args.kwargs.get("foto_anterior_bd") == "anterior.jpg"
        )


# ─────────────────────────────────────────────
# guardar_local
# ─────────────────────────────────────────────


class TestGuardarLocal:
    """Agrupa pruebas relacionadas con guardar local."""

    def test_guarda_jpeg_y_devuelve_nombre_archivo(self):
        """Verifica que guarda jpeg y devuelve nombre archivo."""
        raw = _make_jpeg_bytes()
        archivo = FakeUploadFile(raw, "image/jpeg")
        with tempfile.TemporaryDirectory() as tmpdir:
            with patch.object(file_service.settings, "UPLOAD_DIR", tmpdir):
                nombre = file_service.guardar_local(archivo, 1, raw)  # type: ignore[arg-type]
        assert nombre.endswith(".jpg")
        assert nombre.startswith("perfil_")

    def test_guarda_png_con_extension_correcta(self):
        """Verifica que guarda png con extension correcta."""
        raw = _make_png_bytes()
        archivo = FakeUploadFile(raw, "image/png")
        with tempfile.TemporaryDirectory() as tmpdir:
            with patch.object(file_service.settings, "UPLOAD_DIR", tmpdir):
                nombre = file_service.guardar_local(archivo, 1, raw)  # type: ignore[arg-type]
        assert nombre.endswith(".png")

    def test_guarda_webp_normalizado_a_jpg(self):
        """Verifica que webp se normaliza a jpg en almacenamiento local."""
        raw = _make_webp_bytes()
        archivo = FakeUploadFile(raw, "image/webp")
        with tempfile.TemporaryDirectory() as tmpdir:
            with patch.object(file_service.settings, "UPLOAD_DIR", tmpdir):
                nombre = file_service.guardar_local(archivo, 1, raw)  # type: ignore[arg-type]
                ruta = os.path.join(tmpdir, nombre)
                formato = Image.open(ruta).format

            assert nombre.endswith(".jpg")
            assert formato == "JPEG"

    def test_archivo_realmente_existe_en_disco(self):
        """Verifica que archivo realmente existe en disco."""
        raw = _make_jpeg_bytes()
        archivo = FakeUploadFile(raw, "image/jpeg")
        with tempfile.TemporaryDirectory() as tmpdir:
            with patch.object(file_service.settings, "UPLOAD_DIR", tmpdir):
                nombre = file_service.guardar_local(archivo, 1, raw)  # type: ignore[arg-type]
                ruta = os.path.join(tmpdir, nombre)
            assert os.path.exists(ruta)
            assert os.path.getsize(ruta) > 0

    def test_nombre_derivado_de_hash_usuario(self):
        """El mismo usuario siempre genera el mismo prefijo de hash."""
        import hashlib

        raw = _make_jpeg_bytes()
        archivo = FakeUploadFile(raw, "image/jpeg")
        hash_esperado = hashlib.sha256(str(1).encode()).hexdigest()
        with tempfile.TemporaryDirectory() as tmpdir:
            with patch.object(file_service.settings, "UPLOAD_DIR", tmpdir):
                nombre = file_service.guardar_local(archivo, 1, raw)  # type: ignore[arg-type]
        assert hash_esperado in nombre

    def test_imagen_invalida_lanza_400(self):
        """Verifica que imagen invalida lanza 400."""
        raw = b"esto no es imagen"
        archivo = FakeUploadFile(raw, "image/jpeg")
        with tempfile.TemporaryDirectory() as tmpdir:
            with patch.object(file_service.settings, "UPLOAD_DIR", tmpdir):
                with pytest.raises(HTTPException) as exc:
                    file_service.guardar_local(archivo, 1, raw)  # type: ignore[arg-type]
        assert exc.value.status_code == 400

    def test_error_escritura_lanza_500(self):
        """Verifica que error escritura lanza 500."""
        raw = _make_jpeg_bytes()
        archivo = FakeUploadFile(raw, "image/jpeg")
        with patch.object(
            file_service.settings, "UPLOAD_DIR", "/ruta/que/no/existe/jamas"
        ):
            with pytest.raises(HTTPException) as exc:
                file_service.guardar_local(archivo, 1, raw)  # type: ignore[arg-type]
        assert exc.value.status_code == 500


# ─────────────────────────────────────────────
# guardar_nube (Cloudinary)
# ─────────────────────────────────────────────


class TestGuardarNube:
    """Agrupa pruebas relacionadas con guardar nube."""

    def _raw_jpeg(self) -> bytes:
        """Gestiona raw jpeg."""
        return _make_jpeg_bytes()

    def test_exito_devuelve_url_sin_version(self):
        """Verifica que exito devuelve URL sin version."""
        with patch(
            "cloudinary.uploader.upload",
            return_value={
                "secure_url": "https://res.cloudinary.com/demo/image/upload/v1712345678/perfiles/foto.jpg"
            },
        ):
            raw = self._raw_jpeg()
            archivo = FakeUploadFile(raw, "image/jpeg")
            resultado = file_service.guardar_nube(archivo, 1, raw)  # type: ignore[arg-type]

        assert (
            resultado
            == "https://res.cloudinary.com/demo/image/upload/perfiles/foto.jpg"
        )

    def test_cloudinary_sin_secure_url_lanza_500(self):
        """Si Cloudinary devuelve dict sin secure_url debe ser 500, no None en BD."""
        with patch(
            "cloudinary.uploader.upload",
            return_value={"public_id": "perfiles/perfil_abc"},
        ):
            with pytest.raises(HTTPException) as exc:
                raw = self._raw_jpeg()
                archivo = FakeUploadFile(raw, "image/jpeg")
                file_service.guardar_nube(archivo, 1, raw)  # type: ignore[arg-type]
        assert exc.value.status_code == 500

    def test_cloudinary_fallo_de_red_lanza_500(self):
        """Verifica que cloudinary fallo de red lanza 500."""
        with patch("cloudinary.uploader.upload", side_effect=Exception("timeout")):
            with pytest.raises(HTTPException) as exc:
                raw = self._raw_jpeg()
                archivo = FakeUploadFile(raw, "image/jpeg")
                file_service.guardar_nube(archivo, 1, raw)  # type: ignore[arg-type]
        assert exc.value.status_code == 500

    def test_imagen_invalida_lanza_400_no_500(self):
        """HTTPException(400) de _reencode_image NO debe convertirse en 500."""
        raw = b"basura"
        archivo = FakeUploadFile(raw, "image/jpeg")
        with pytest.raises(HTTPException) as exc:
            file_service.guardar_nube(archivo, 1, raw)  # type: ignore[arg-type]
        assert exc.value.status_code == 400

    def test_public_id_usa_hash_del_usuario(self):
        """El public_id en Cloudinary debe ser determinista y basado en el usuario."""
        import hashlib

        hash_esperado = hashlib.sha256(str(1).encode()).hexdigest()
        public_id_esperado = f"perfil_{hash_esperado}"

        capturado = {}

        def fake_upload(data, **kwargs):
            """Crea un simulacro de upload."""
            capturado.update(kwargs)
            return {
                "secure_url": "https://res.cloudinary.com/demo/image/upload/v1/perfiles/foto.jpg"
            }

        with patch("cloudinary.uploader.upload", side_effect=fake_upload):
            raw = self._raw_jpeg()
            archivo = FakeUploadFile(raw, "image/jpeg")
            file_service.guardar_nube(archivo, 1, raw)  # type: ignore[arg-type]

        assert capturado.get("public_id") == public_id_esperado

    def test_overwrite_true_en_upload(self):
        """Cloudinary debe usar overwrite=True para que solo haya una foto por usuario."""
        capturado = {}

        def fake_upload(data, **kwargs):
            """Crea un simulacro de upload."""
            capturado.update(kwargs)
            return {
                "secure_url": "https://res.cloudinary.com/demo/image/upload/v1/perfiles/foto.jpg"
            }

        with patch("cloudinary.uploader.upload", side_effect=fake_upload):
            raw = self._raw_jpeg()
            archivo = FakeUploadFile(raw, "image/jpeg")
            file_service.guardar_nube(archivo, 1, raw)  # type: ignore[arg-type]

        assert capturado.get("overwrite") is True

    def test_invalidate_true_en_upload(self):
        """Cloudinary debe invalidar caché al sobrescribir el asset."""
        capturado = {}

        def fake_upload(data, **kwargs):
            """Crea un simulacro de upload."""
            capturado.update(kwargs)
            return {
                "secure_url": "https://res.cloudinary.com/demo/image/upload/v1/perfiles/foto.jpg"
            }

        with patch("cloudinary.uploader.upload", side_effect=fake_upload):
            raw = self._raw_jpeg()
            archivo = FakeUploadFile(raw, "image/jpeg")
            file_service.guardar_nube(archivo, 1, raw)  # type: ignore[arg-type]

        assert capturado.get("invalidate") is True

    def test_resource_type_image_en_upload(self):
        """Verifica que resource type imagen en upload."""
        capturado = {}

        def fake_upload(data, **kwargs):
            """Crea un simulacro de upload."""
            capturado.update(kwargs)
            return {
                "secure_url": "https://res.cloudinary.com/demo/image/upload/v1/perfiles/foto.jpg"
            }

        with patch("cloudinary.uploader.upload", side_effect=fake_upload):
            raw = self._raw_jpeg()
            archivo = FakeUploadFile(raw, "image/jpeg")
            file_service.guardar_nube(archivo, 1, raw)  # type: ignore[arg-type]

        assert capturado.get("resource_type") == "image"

    def test_png_se_normaliza_a_jpg_antes_de_subir(self):
        """Aunque el usuario suba PNG, en Cloudinary debe enviarse JPEG."""
        raw = _make_png_bytes()
        archivo = FakeUploadFile(raw, "image/png")

        capturado = {}

        def fake_upload(data, **kwargs):
            """Crea un simulacro de upload."""
            capturado["data"] = data
            capturado.update(kwargs)
            return {
                "secure_url": "https://res.cloudinary.com/demo/image/upload/v99/perfiles/foto.jpg"
            }

        with patch("cloudinary.uploader.upload", side_effect=fake_upload):
            resultado = file_service.guardar_nube(archivo, 1, raw)  # type: ignore[arg-type]

        datos_subidos = capturado["data"].getvalue()
        imagen_subida = Image.open(BytesIO(datos_subidos))

        assert imagen_subida.format == "JPEG"
        assert (
            resultado
            == "https://res.cloudinary.com/demo/image/upload/perfiles/foto.jpg"
        )
