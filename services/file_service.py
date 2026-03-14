# services/file_service.py

"""
services/file_service.py

Servicio para manejar la validación y procesamiento de archivos.
"""
import os
import re
import time
import hashlib
from typing import Optional
from io import BytesIO
import logging

from fastapi import UploadFile, HTTPException, Request
import cloudinary.uploader
import cloudinary

from config import settings

# Pillow para verificar que el archivo es realmente una imagen
from PIL import Image, ImageOps, UnidentifiedImageError

logger = logging.getLogger("app.files")

# Límite de seguridad (anti "decompression bomb")
# Ajustable por env (ej: 13MP)
MAX_IMAGE_PIXELS = int(settings.MAX_IMAGE_PIXELS)
Image.MAX_IMAGE_PIXELS = MAX_IMAGE_PIXELS

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

# Firmas de contenido malicioso conocidas.
MALICIOUS_SIGNATURES = [
    b"<%eval",
    b"<%execute",
    b"<script>",
    b"javascript:",
    b"vbscript:",
    b".exe\x00",
    b".dll\x00",
]


# NOTA:
# - En producción usamos Cloudinary y guardamos una URL canónica SIN versión en BD.
#   Así evitamos depender de una secure_url versionada nueva tras cada overwrite.
# - request.base_url solo se usa en modo local con storage local (HTTP), donde es suficiente.
# - Si en el futuro se despliega detrás de reverse proxy/HTTPS, considerar usar X-Forwarded-* o PUBLIC_BASE_URL.
def construir_url_foto(foto_perfil: Optional[str], request: Request) -> Optional[str]:
    """
    Devuelve la URL completa de la foto si existe.
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
    if archivo.content_type not in ["image/jpeg", "image/png", "image/jpg"]:
        raise HTTPException(status_code=400, detail="Error: Solo imágenes JPG o PNG")

    archivo.file.seek(0, os.SEEK_END)
    tamano = archivo.file.tell()
    archivo.file.seek(0)

    if tamano > MAX_IMAGE_BYTES:
        mb = MAX_IMAGE_BYTES / (1024 * 1024)
        raise HTTPException(
            status_code=400,
            detail=f"Error: La imagen supera el máximo permitido ({mb:.2f}MB)",
        )

    content = archivo.file.read()
    archivo.file.seek(0)

    content_lower = content.lower()
    for signature in MALICIOUS_SIGNATURES:
        if signature in content_lower:
            raise HTTPException(
                status_code=400, detail="Error: Contenido malicioso detectado"
            )

    try:
        img = Image.open(BytesIO(content))
        img.verify()
    except (UnidentifiedImageError, OSError):
        raise HTTPException(
            status_code=400, detail="Error: El archivo no es una imagen válida"
        )

    try:
        img2 = Image.open(BytesIO(content))
        img2.load()
        if (img2.width * img2.height) > MAX_IMAGE_PIXELS:
            raise HTTPException(
                status_code=400, detail="Error: Imagen demasiado grande"
            )
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(
            status_code=400, detail="Error: El archivo no es una imagen válida"
        )

    return content


def _reencode_image(raw: bytes, extension: str) -> bytes:
    try:
        im = Image.open(BytesIO(raw))
        im.load()

        # Aplica la orientación EXIF antes de eliminar metadatos.
        # Así evitamos que algunas fotos queden giradas al strippear EXIF.
        im = ImageOps.exif_transpose(im)
    except (UnidentifiedImageError, OSError):
        raise HTTPException(
            status_code=400, detail="Error: El archivo no es una imagen válida"
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
            raise HTTPException(
                status_code=400,
                detail=f"Error: La imagen procesada supera el máximo ({mb:.2f}MB)",
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
        raise HTTPException(
            status_code=400,
            detail=f"Error: La imagen procesada supera el máximo ({mb:.2f}MB)",
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
        raise HTTPException(
            status_code=500,
            detail="Error: No se ha podido procesar la imagen",
        )


def guardar_local(
    archivo: UploadFile,
    usuario_actual_id: int,
    raw: bytes,
    foto_anterior_bd: Optional[str] = None,
) -> str:
    carpeta_imagenes = settings.UPLOAD_DIR
    nombre_seguro = hashlib.sha256(str(usuario_actual_id).encode()).hexdigest()

    mapa_extensiones = {
        "image/jpeg": ".jpg",
        "image/jpg": ".jpg",
        "image/png": ".png",
    }
    extension = mapa_extensiones.get(archivo.content_type or "", ".jpg")

    try:
        data_limpia = _reencode_image(raw, extension)

        nombre_archivo = f"perfil_{nombre_seguro}_{int(time.time())}{extension}"
        ruta_final = os.path.join(carpeta_imagenes, nombre_archivo)

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
                    f"perfil_{nombre_seguro}_{int(time.time())}{extension}",
                ),
            },
        )
        raise HTTPException(
            status_code=500,
            detail="Error: No se ha podido guardar la imagen localmente",
        )


def guardar_nube(archivo: UploadFile, usuario_actual_id: int, raw: bytes) -> str:
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
            raise HTTPException(
                status_code=500,
                detail="Error: Cloudinary no devolvió URL válida",
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
        raise HTTPException(
            status_code=500,
            detail="Error: No se ha podido subir la imagen a la nube",
        )


def borrar_foto(foto_perfil: Optional[str], usuario_actual_id: int) -> None:
    """Lógica de borrado permanente segura usando hashing."""
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
