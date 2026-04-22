# services/file_service.py

"""
Servicio para manejar la validación y procesamiento de archivos.
"""
import os
import re
import time
import hashlib
import uuid
from typing import Optional
from io import BytesIO
import logging

from fastapi import UploadFile, HTTPException, Request
import cloudinary.uploader
import cloudinary

from config import settings
from exceptions import app_http_exception

# Pillow para verificar que el archivo es realmente una imagen
from PIL import Image, ImageOps, UnidentifiedImageError

logger = logging.getLogger("app.files")

# Límite de seguridad (anti "decompression bomb")
# Ajustable por env (ej: 13MP)
MAX_IMAGE_PIXELS = int(settings.MAX_IMAGE_PIXELS)

# Tamaño máximo de imagen (bytes) ajustable por env (ej: 2MB)
MAX_IMAGE_BYTES = settings.MAX_IMAGE_BYTES

# Calidad JPEG para re-encode, ajustable por env
IMAGE_JPEG_QUALITY = settings.IMAGE_JPEG_QUALITY
# clamp razonable (Pillow recomienda no pasarse de 95)
if IMAGE_JPEG_QUALITY < 1:
    IMAGE_JPEG_QUALITY = 1
if IMAGE_JPEG_QUALITY > 95:
    IMAGE_JPEG_QUALITY = 95

# Si la API está en producción carga variables de Cloudinary.
if settings.STORAGE_TYPE == "cloudinary":
    if (
        not settings.CLOUDINARY_CLOUD_NAME
        or not settings.CLOUDINARY_API_KEY
        or not settings.CLOUDINARY_API_SECRET
    ):
        raise RuntimeError(
            "STORAGE_TYPE=cloudinary pero faltan credenciales: "
            "CLOUDINARY_CLOUD_NAME / CLOUDINARY_API_KEY / CLOUDINARY_API_SECRET"
        )

    cloudinary.config(
        cloud_name=settings.CLOUDINARY_CLOUD_NAME,
        api_key=settings.CLOUDINARY_API_KEY,
        api_secret=settings.CLOUDINARY_API_SECRET,
        secure=True,
    )


ALLOWED_IMAGE_CONTENT_TYPES = {
    "image/jpeg",
    "image/png",
    "image/jpg",
    "image/webp",
    "image/heic",
    "image/heif",
    "image/heic-sequence",
    "image/heif-sequence",
}


# NOTA:
# - En producción usamos Cloudinary y guardamos una URL canónica SIN versión en BD.
# Así evitamos depender de una secure_url versionada nueva tras cada overwrite.
# - petición.base_url solo se usa en modo local con storage local (HTTP), donde es suficiente.
# - Si en el futuro se despliega detrás de reverse proxy/HTTPS, considerar usar X-Forwarded-* o PUBLIC_BASE_URL.
def construir_url_foto(foto_perfil: Optional[str], request: Request) -> Optional[str]:
    """Resuelve la URL pública absoluta de una foto de perfil.

    Si ``foto_perfil`` es ya una URL absoluta (Cloudinary) se devuelve
    tal cual. Si es un nombre de fichero (almacenamiento local), se
    antepone ``settings.PUBLIC_BASE_URL`` si está configurada, o la
    ``base_url`` de la petición en su defecto. Así el cliente recibe
    siempre una URL navegable directamente, sin tener que construirla.

    Args:
        foto_perfil: valor tal como está guardado en la base de datos (URL completa, nombre de fichero, o ``None``).
        request: petición entrante, usada para inferir la URL base en modo local cuando no hay ``PUBLIC_BASE_URL``.

    Returns:
        URL absoluta de la foto, o ``None`` si el usuario no tiene foto.
    """
    if not foto_perfil:
        return None

    # Si la foto es de Cloudinary (empieza por http), se usa tal cual
    if str(foto_perfil).startswith("http"):
        return str(foto_perfil)

    # Si hay URL pública configurada, se usa siempre
    url_base = settings.PUBLIC_BASE_URL or str(request.base_url).rstrip("/")
    ruta = str(foto_perfil).lstrip("/")

    return f"{url_base}/imagenes/{ruta}"


def validar_seguridad(archivo: UploadFile) -> bytes:
    """Comprueba que el fichero subido es una imagen válida y segura.

    Aplica tres capas de defensa:

    1. ``Content-Type`` debe estar en la lista blanca
       (``ALLOWED_IMAGE_CONTENT_TYPES``).
    2. Tamaño en bytes por debajo de ``MAX_IMAGE_BYTES``.
    3. El contenido se abre DOS veces con Pillow: primero con
       ``.verify()`` para detectar cabeceras corruptas, y luego con
       ``.load()`` para forzar la decodificación real del bitmap y
       atrapar bombas de decompresión (``DecompressionBombError``)
       que ``.verify()`` no detecta. Además comprueba que el producto
       ancho×alto no supere ``MAX_IMAGE_PIXELS``.

    Args:
        archivo: fichero subido tal como lo entrega FastAPI (``UploadFile``).

    Returns:
        Bytes del fichero ya leídos del stream (para que ``procesar_subida``
        no tenga que volver a leer el ``SpooledTemporaryFile``).

    Raises:
        AppHTTPException: 400 ``IMAGE_FORMAT_NOT_ALLOWED`` si el MIME no está permitido.
        AppHTTPException: 400 ``IMAGE_FILE_TOO_LARGE`` si el fichero supera el máximo en bytes.
        AppHTTPException: 400 ``IMAGE_TOO_LARGE`` si el producto ancho×alto supera el máximo en píxeles.
        AppHTTPException: 400 ``INVALID_IMAGE_FILE`` si Pillow no puede abrir/decodificar el fichero.
    """
    # Valida seguridad.
    content_type = (archivo.content_type or "").lower()
    if content_type not in ALLOWED_IMAGE_CONTENT_TYPES:
        raise app_http_exception(
            status_code=400,
            mensaje="Error: Solo imágenes JPG, PNG, WEBP o HEIC/HEIF",
            error_code="IMAGE_FORMAT_NOT_ALLOWED",
        )

    archivo.file.seek(0, os.SEEK_END)
    tamano = archivo.file.tell()
    archivo.file.seek(0)

    if tamano > MAX_IMAGE_BYTES:
        mb = MAX_IMAGE_BYTES / (1024 * 1024)
        raise app_http_exception(
            status_code=400,
            mensaje=f"Error: La imagen supera el máximo permitido ({mb:.2f}MB)",
            error_code="IMAGE_FILE_TOO_LARGE",
        )

    content = archivo.file.read()
    archivo.file.seek(0)

    try:
        img = Image.open(BytesIO(content))
        if (img.width * img.height) > MAX_IMAGE_PIXELS:
            raise app_http_exception(
                status_code=400,
                mensaje="Error: Imagen demasiado grande",
                error_code="IMAGE_TOO_LARGE",
            )
        img.verify()
    except (UnidentifiedImageError, OSError, Image.DecompressionBombError):
        raise app_http_exception(
            status_code=400,
            mensaje="Error: El archivo no es una imagen válida",
            error_code="INVALID_IMAGE_FILE",
        )

    try:
        img2 = Image.open(BytesIO(content))
        if (img2.width * img2.height) > MAX_IMAGE_PIXELS:
            raise app_http_exception(
                status_code=400,
                mensaje="Error: Imagen demasiado grande",
                error_code="IMAGE_TOO_LARGE",
            )
        img2.load()
    except HTTPException:
        raise
    except Exception:
        raise app_http_exception(
            status_code=400,
            mensaje="Error: El archivo no es una imagen válida",
            error_code="INVALID_IMAGE_FILE",
        )

    return content


def _reencode_image(raw: bytes, extension: str) -> bytes:
    """Re-codifica la imagen en PNG o JPEG descartando todo el EXIF.

    Antes de decodificar aplica ``ImageOps.exif_transpose`` para que la
    orientación EXIF quede materializada en los píxeles: si después
    stripeamos EXIF, la imagen no se ve de lado. A propósito NO se
    pasa ``exif=`` ni ``pnginfo=`` al guardar para que GPS y otros
    metadatos sensibles no sobrevivan al proceso.

    Para JPEG fuerza ``RGB`` (convierte modos ``RGBA``/``P``) y aplica
    ``optimize=True`` con ``IMAGE_JPEG_QUALITY``. Tras re-encodear vuelve
    a comprobar el tamaño resultante: la compresión puede crecer si la
    entrada era ya óptima, y no queremos persistir imágenes mayores
    que el tope.

    Args:
        raw: bytes originales del fichero subido.
        extension: ``".png"`` para mantener PNG con transparencia, otro valor para JPEG.

    Returns:
        Bytes de la imagen ya sanitizada en el formato elegido.

    Raises:
        AppHTTPException: 400 ``IMAGE_TOO_LARGE`` si la entrada supera ``MAX_IMAGE_PIXELS`` en píxeles.
        AppHTTPException: 400 ``INVALID_IMAGE_FILE`` si Pillow no puede decodificar la imagen.
        AppHTTPException: 400 ``PROCESSED_IMAGE_TOO_LARGE`` si la salida comprimida supera ``MAX_IMAGE_BYTES``.
    """
    try:
        im = Image.open(BytesIO(raw))
        if (im.width * im.height) > MAX_IMAGE_PIXELS:
            raise app_http_exception(
                status_code=400,
                mensaje="Error: Imagen demasiado grande",
                error_code="IMAGE_TOO_LARGE",
            )
        im.load()

        # Aplica la orientación EXIF antes de eliminar metadatos.
        # Así evitamos que algunas fotos queden giradas al strippear EXIF.
        im = ImageOps.exif_transpose(im)
    except (UnidentifiedImageError, OSError, Image.DecompressionBombError):
        raise app_http_exception(
            status_code=400,
            mensaje="Error: El archivo no es una imagen válida",
            error_code="INVALID_IMAGE_FILE",
        )

    out = BytesIO()

    if extension == ".png":
        if im.mode not in ("RGB", "RGBA"):
            im = im.convert("RGBA")

        # Importante:
        # - No pasamos pnginfo
        # - No pasamos exif
        # => se eliminan metadatos embebidos al re-encodear
        im.save(out, format="PNG", optimize=True)
        data = out.getvalue()

        if len(data) > MAX_IMAGE_BYTES:
            mb = MAX_IMAGE_BYTES / (1024 * 1024)
            raise app_http_exception(
                status_code=400,
                mensaje=f"Error: La imagen procesada supera el máximo ({mb:.2f}MB)",
                error_code="PROCESSED_IMAGE_TOO_LARGE",
            )
        return data

    if im.mode in ("RGBA", "P"):
        im = im.convert("RGB")

    # Importante:
    # - No pasamos exif
    # => no se preservan EXIF/GPS
    im.save(out, format="JPEG", optimize=True, quality=IMAGE_JPEG_QUALITY)
    data = out.getvalue()

    if len(data) > MAX_IMAGE_BYTES:
        mb = MAX_IMAGE_BYTES / (1024 * 1024)
        raise app_http_exception(
            status_code=400,
            mensaje=f"Error: La imagen procesada supera el máximo ({mb:.2f}MB)",
            error_code="PROCESSED_IMAGE_TOO_LARGE",
        )

    return data


def _strip_cloudinary_version(url: str) -> str:
    """
    Elimina el segmento /v1234567890/ de una secure_url de Cloudinary.
    Ejemplo:
    https://res.cloudinary.com/demo/image/upload/v1712345678/perfiles/foto.jpg
    ->
    https://res.cloudinary.com/demo/image/upload/perfiles/foto.jpg

    Con esto guardamos una URL canónica estable en BD para el mismo public_id.
    """
    return re.sub(r"/v\d+/", "/", url, count=1)


def procesar_subida(
    archivo: UploadFile,
    usuario_actual_id: int,
    raw: bytes,
    foto_anterior_bd: Optional[str] = None,
) -> str:
    """Despacha al backend de almacenamiento activo (local o Cloudinary).

    La selección se hace con ``settings.STORAGE_TYPE``:

    - ``cloudinary``: sube a la nube, devuelve URL canónica sin versión.
    - otro valor: guarda en disco, devuelve el nombre de fichero.

    Cualquier ``HTTPException`` generada aguas abajo se propaga tal cual
    para no enmascarar mensajes de validación. Cualquier otra excepción
    (errores de red, disco, etc.) se registra con traceback y se
    convierte en un 500 genérico para no filtrar detalles internos.

    Args:
        archivo: fichero subido (para leer ``content_type`` y logs).
        usuario_actual_id: id del usuario dueño, usado para derivar el nombre de fichero.
        raw: bytes del fichero ya validados por ``validar_seguridad``.
        foto_anterior_bd: valor anterior del campo ``foto_perfil`` en la base de datos (no se usa ahora en cloud, solo en local).

    Returns:
        URL completa en Cloudinary o nombre de fichero local, listo para persistir en ``foto_perfil``.

    Raises:
        AppHTTPException: 500 ``IMAGE_PROCESSING_FAILED`` para errores inesperados.
        Cualquier ``AppHTTPException`` que levante ``guardar_local`` o ``guardar_nube``.
    """
    # Gestiona procesar subida.
    try:
        if settings.STORAGE_TYPE == "cloudinary":
            return guardar_nube(archivo, usuario_actual_id, raw)
        return guardar_local(archivo, usuario_actual_id, raw, foto_anterior_bd)
    except HTTPException:
        raise
    except Exception:
        logger.exception(
            "error_procesado_subida",
            extra={
                "usuario_id": usuario_actual_id,
                "content_type": archivo.content_type,
                "storage_type": settings.STORAGE_TYPE,
            },
        )
        raise app_http_exception(
            status_code=500,
            mensaje="Error: No se ha podido procesar la imagen",
            error_code="IMAGE_PROCESSING_FAILED",
        )


def guardar_local(
    archivo: UploadFile,
    usuario_actual_id: int,
    raw: bytes,
    foto_anterior_bd: Optional[str] = None,
) -> str:
    """Guarda la imagen en el directorio de uploads local del servidor.

    El nombre de fichero combina:

    - ``perfil_``, para identificar el tipo.
    - Hash SHA-256 del id de usuario, para no exponer el id en la URL.
    - Timestamp UNIX actual, para invalidar caché de clientes al cambiar foto.
    - 12 hex chars de un UUID aleatorio, para evitar colisiones cuando
      el usuario actualiza varias fotos en el mismo segundo.
    - Extensión normalizada (HEIC/HEIF se persisten como ``.jpg`` porque
      el re-encoder los convierte a JPEG).

    Args:
        archivo: fichero subido (solo se usa su ``content_type``).
        usuario_actual_id: id del dueño, para derivar el nombre.
        raw: bytes ya validados por ``validar_seguridad``.
        foto_anterior_bd: valor anterior del campo en BD; no se borra aquí,
            el borrado lo hace ``borrar_foto`` en background tras commit.

    Returns:
        Nombre del fichero ya guardado (no la ruta absoluta), para persistir en ``foto_perfil``.

    Raises:
        AppHTTPException: 500 ``IMAGE_SAVE_FAILED`` si no se puede escribir en disco.
        Cualquier ``AppHTTPException`` que levante ``_reencode_image``.
    """
    # Guarda local.
    carpeta_imagenes = settings.UPLOAD_DIR
    nombre_seguro = hashlib.sha256(str(usuario_actual_id).encode()).hexdigest()

    mapa_extensiones = {
        "image/jpeg": ".jpg",
        "image/jpg": ".jpg",
        "image/png": ".png",
        "image/webp": ".jpg",
        "image/heic": ".jpg",
        "image/heif": ".jpg",
        "image/heic-sequence": ".jpg",
        "image/heif-sequence": ".jpg",
    }
    content_type = (archivo.content_type or "").lower()
    extension = mapa_extensiones.get(content_type, ".jpg")
    nombre_archivo = (
        f"perfil_{nombre_seguro}_{int(time.time())}_{uuid.uuid4().hex[:12]}{extension}"
    )
    ruta_final = os.path.join(carpeta_imagenes, nombre_archivo)

    try:
        data_limpia = _reencode_image(raw, extension)

        with open(ruta_final, "wb") as buffer:
            buffer.write(data_limpia)

        return nombre_archivo

    except HTTPException:
        raise
    except Exception:
        logger.exception(
            "error_guardado_archivo_local",
            extra={
                "usuario_id": usuario_actual_id,
                "content_type": archivo.content_type,
                "storage_type": settings.STORAGE_TYPE,
                "ruta_destino": os.path.join(
                    carpeta_imagenes,
                    nombre_archivo,
                ),
            },
        )
        raise app_http_exception(
            status_code=500,
            mensaje="Error: No se ha podido guardar la imagen localmente",
            error_code="IMAGE_SAVE_FAILED",
        )


def guardar_nube(archivo: UploadFile, usuario_actual_id: int, raw: bytes) -> str:
    """Sube la imagen a Cloudinary bajo un ``public_id`` estable por usuario.

    Fuerza siempre JPEG como formato final para que un mismo usuario
    tenga siempre el mismo asset independientemente del formato que
    suba, lo que simplifica purgas y caché. Usa ``overwrite=True`` +
    ``invalidate=True`` para reemplazar la foto anterior y purgar la
    CDN en una sola llamada.

    La URL devuelta se normaliza con ``_strip_cloudinary_version`` para
    guardar en BD una URL canónica sin versión: así los clientes no
    quedan pegados a una ``v1234567890`` concreta y se evita invalidar
    cachés locales cada vez que Cloudinary genera una nueva versión
    interna.

    Args:
        archivo: fichero subido (solo se usa su ``content_type`` en el log de error).
        usuario_actual_id: id del dueño; se hashea con SHA-256 para derivar el ``public_id``.
        raw: bytes ya validados por ``validar_seguridad``.

    Returns:
        URL canónica de Cloudinary (sin segmento de versión) lista para persistir en ``foto_perfil``.

    Raises:
        AppHTTPException: 500 ``CLOUDINARY_INVALID_URL`` si Cloudinary no devuelve ``secure_url``.
        AppHTTPException: 500 ``IMAGE_UPLOAD_FAILED`` si la subida lanza cualquier otra excepción.
        Cualquier ``AppHTTPException`` que levante ``_reencode_image``.
    """
    try:
        usuario_hash = hashlib.sha256(str(usuario_actual_id).encode()).hexdigest()

        # En Cloudinary siempre normalizamos a JPG para que el asset final
        # tenga siempre el mismo formato, independientemente de si el usuario
        # subió JPG o PNG.
        extension = ".jpg"
        data_limpia = _reencode_image(raw, extension)

        resultado = cloudinary.uploader.upload(
            BytesIO(data_limpia),
            folder="perfiles",
            public_id=f"perfil_{usuario_hash}",
            overwrite=True,
            invalidate=True,
            resource_type="image",
        )

        url = resultado.get("secure_url")
        if not url:
            raise app_http_exception(
                status_code=500,
                mensaje="Error: Cloudinary no devolvió URL válida",
                error_code="CLOUDINARY_INVALID_URL",
            )

        # Guardamos una URL canónica sin versión.
        return _strip_cloudinary_version(url)

    except HTTPException:
        raise
    except Exception:
        logger.exception(
            "error_subida_cloudinary",
            extra={
                "usuario_id": usuario_actual_id,
                "content_type": archivo.content_type,
                "storage_type": settings.STORAGE_TYPE,
            },
        )
        raise app_http_exception(
            status_code=500,
            mensaje="Error: No se ha podido subir la imagen a la nube",
            error_code="IMAGE_UPLOAD_FAILED",
        )


def borrar_foto(foto_perfil: Optional[str], usuario_actual_id: int) -> None:
    """Borra la foto anterior del almacenamiento activo de forma best-effort.

    Comportamiento por backend:

    - Cloudinary: calcula el mismo ``public_id`` estable por usuario que
      usa ``guardar_nube`` y lo destruye con ``invalidate=True`` para
      purgar la CDN. El hashing garantiza que no se dependa del valor
      guardado en BD (puede haber cambiado).
    - Local: resuelve la ruta absoluta desde ``UPLOAD_DIR`` + basename
      y elimina el fichero si existe.

    Cualquier excepción durante el borrado se registra como warning
    pero no se propaga: esta función la invoca ``BackgroundTasks`` tras
    un commit con éxito (cambio de foto / eliminación de cuenta), y
    propagar aquí dejaría la base de datos ya modificada con un error
    que no puede deshacerse.

    Args:
        foto_perfil: valor anterior del campo ``foto_perfil``, usado para decidir si hay algo que borrar.
        usuario_actual_id: id del dueño, necesario para reconstruir el ``public_id`` en Cloudinary.
    """
    # Elimina foto.
    if not foto_perfil:
        return

    if settings.STORAGE_TYPE == "cloudinary":
        try:
            usuario_hash = hashlib.sha256(str(usuario_actual_id).encode()).hexdigest()
            public_id = f"perfiles/perfil_{usuario_hash}"
            cloudinary.uploader.destroy(
                public_id,
                resource_type="image",
                invalidate=True,
            )
        except Exception:
            logger.warning(
                "error_borrado_cloudinary",
                extra={
                    "usuario_id": usuario_actual_id,
                    "foto": foto_perfil,
                    "storage_type": settings.STORAGE_TYPE,
                },
                exc_info=True,
            )
        return

    try:
        carpeta_imagenes = settings.UPLOAD_DIR
        ruta = os.path.join(carpeta_imagenes, os.path.basename(foto_perfil))
        if os.path.exists(ruta):
            os.remove(ruta)
    except Exception:
        logger.warning(
            "error_borrado_archivo_local",
            extra={
                "usuario_id": usuario_actual_id,
                "foto": foto_perfil,
                "storage_type": settings.STORAGE_TYPE,
            },
            exc_info=True,
        )
