# services/file_service.py

"""
services/file_service.py

Servicio para manejar la validación y procesamiento de archivos.
"""
import os
import time
import hashlib
from typing import Optional
from io import BytesIO
import logging

from fastapi import UploadFile, HTTPException, Request
import cloudinary.uploader
import cloudinary

from config import settings

logger = logging.getLogger("app.files")

# Pillow para verificar que el archivo es realmente una imagen
from PIL import Image, UnidentifiedImageError


# Sentinel: en tu caso "default_avatar.png" NO existe en backend.
# Existe en Android como drawable, así que el backend debe devolver null y no intentar borrarla.
DEFAULT_AVATAR_SENTINEL = "default_avatar.png"

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
    if not settings.CLOUDINARY_CLOUD_NAME or not settings.CLOUDINARY_API_KEY or not settings.CLOUDINARY_API_SECRET:
        raise RuntimeError(
            "STORAGE_TYPE=cloudinary pero faltan credenciales: "
            "CLOUDINARY_CLOUD_NAME / CLOUDINARY_API_KEY / CLOUDINARY_API_SECRET"
        )

    cloudinary.config(
        cloud_name=settings.CLOUDINARY_CLOUD_NAME,
        api_key=settings.CLOUDINARY_API_KEY,
        api_secret=settings.CLOUDINARY_API_SECRET,
        secure=True
    )

# Firmas de contenido malicioso conocidas.
MALICIOUS_SIGNATURES = [
    b'<%eval',
    b'<%execute',
    b'<script>',
    b'javascript:',
    b'vbscript:',
    b'.exe\x00',
    b'.dll\x00'
]

# NOTA:
# - En producción usamos Cloudinary y guardamos secure_url en BD -> se devuelve tal cual (no depende de base_url).
# - request.base_url solo se usa en modo local con storage local (HTTP), donde es suficiente.
# - Si en el futuro se despliega detrás de reverse proxy/HTTPS, considerar usar X-Forwarded-* o PUBLIC_BASE_URL.
def construir_url_foto(foto_perfil: Optional[str], request: Request) -> Optional[str]:
    """
    Devuelve la URL completa de la foto si existe.
    Si es 'default_avatar.png' (sentinel local de Android), devuelve None para que la app use su drawable.
    """
    if not foto_perfil:
        return None

    # Si alguien guardó "default_avatar.png" en BD (o viene en ruta), no se sirve desde backend
    if os.path.basename(str(foto_perfil)) == DEFAULT_AVATAR_SENTINEL:
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
            detail=f"Error: La imagen supera el máximo permitido ({mb:.2f}MB)"
        )

    content = archivo.file.read()
    archivo.file.seek(0)

    content_lower = content.lower()
    for signature in MALICIOUS_SIGNATURES:
        if signature in content_lower:
            raise HTTPException(status_code=400, detail="Error: Contenido malicioso detectado")

    try:
        img = Image.open(BytesIO(content))
        img.verify()
    except (UnidentifiedImageError, OSError):
        raise HTTPException(status_code=400, detail="Error: El archivo no es una imagen válida")

    try:
        img2 = Image.open(BytesIO(content))
        img2.load()
        if (img2.width * img2.height) > MAX_IMAGE_PIXELS:
            raise HTTPException(status_code=400, detail="Error: Imagen demasiado grande")
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(status_code=400, detail="Error: El archivo no es una imagen válida")

    return content


def _reencode_image(raw: bytes, extension: str) -> bytes:
    try:
        im = Image.open(BytesIO(raw))
        im.load()
    except (UnidentifiedImageError, OSError):
        raise HTTPException(status_code=400, detail="Error: El archivo no es una imagen válida")

    out = BytesIO()

    if extension == ".png":
        if im.mode not in ("RGB", "RGBA"):
            im = im.convert("RGBA")
        im.save(out, format="PNG", optimize=True)
        data = out.getvalue()

        if len(data) > MAX_IMAGE_BYTES:
            mb = MAX_IMAGE_BYTES / (1024 * 1024)
            raise HTTPException(
                status_code=400,
                detail=f"Error: La imagen procesada supera el máximo ({mb:.2f}MB)"
            )
        return data

    if im.mode in ("RGBA", "P"):
        im = im.convert("RGB")

    im.save(out, format="JPEG", optimize=True, quality=IMAGE_JPEG_QUALITY)
    data = out.getvalue()

    if len(data) > MAX_IMAGE_BYTES:
        mb = MAX_IMAGE_BYTES / (1024 * 1024)
        raise HTTPException(
            status_code=400,
            detail=f"Error: La imagen procesada supera el máximo ({mb:.2f}MB)"
        )

    return data


def procesar_subida(
    archivo: UploadFile,
    usuario_actual: str,
    raw: bytes,
    foto_anterior_bd: Optional[str] = None
) -> str:
    if settings.STORAGE_TYPE == "cloudinary":
        return guardar_nube(archivo, usuario_actual, raw)
    return guardar_local(archivo, usuario_actual, raw, foto_anterior_bd)


def guardar_local(
    archivo: UploadFile,
    usuario_actual: str,
    raw: bytes,
    foto_anterior_bd: Optional[str] = None
) -> str:
    carpeta_imagenes = settings.UPLOAD_DIR
    nombre_seguro = hashlib.sha256(usuario_actual.encode()).hexdigest()

    mapa_extensiones = {
        "image/jpeg": ".jpg",
        "image/jpg": ".jpg",
        "image/png": ".png",
    }
    extension = mapa_extensiones.get(archivo.content_type or "", ".jpg")

    data_limpia = _reencode_image(raw, extension)

    nombre_archivo = f"perfil_{nombre_seguro}_{int(time.time())}{extension}"
    ruta_final = os.path.join(carpeta_imagenes, nombre_archivo)

    try:
        with open(ruta_final, "wb") as buffer:
            buffer.write(data_limpia)
    except Exception:
        logger.exception(
            "error_guardado_archivo_local",
            extra={
                "usuario": usuario_actual,
                "content_type": archivo.content_type,
                "storage_type": settings.STORAGE_TYPE,
                "ruta_destino": ruta_final,
            },
        )
        raise HTTPException(
            status_code=500,
            detail="Error: No se ha podido guardar la imagen localmente"
        )

    return nombre_archivo


def guardar_nube(archivo: UploadFile, usuario_actual: str, raw: bytes) -> str:
    try:
        usuario_hash = hashlib.sha256(usuario_actual.encode()).hexdigest()

        mapa_extensiones = {
            "image/jpeg": ".jpg",
            "image/jpg": ".jpg",
            "image/png": ".png",
        }
        extension = mapa_extensiones.get(archivo.content_type or "", ".jpg")

        data_limpia = _reencode_image(raw, extension)

        resultado = cloudinary.uploader.upload(
            BytesIO(data_limpia),
            folder="perfiles",
            public_id=f"perfil_{usuario_hash}",
            overwrite=True,
            resource_type="image"
        )

        url = resultado.get("secure_url")
        if not url:
            raise HTTPException(
                status_code=500,
                detail="Error: Cloudinary no devolvió URL válida"
            )
        return url

    except HTTPException:
        raise
    except Exception:
        logger.exception(
            "error_subida_cloudinary",
            extra={
                "usuario": usuario_actual,
                "content_type": archivo.content_type,
                "storage_type": settings.STORAGE_TYPE,
            },
        )
        raise HTTPException(
            status_code=500,
            detail="Error: No se ha podido subir la imagen a la nube"
        )


def borrar_foto(foto_perfil: str, usuario_actual: str):
    """Lógica de borrado permanente segura usando Hashing."""
    if not foto_perfil:
        return

    # Si es el sentinel (avatar local de Android), no hay nada que borrar en backend
    if os.path.basename(foto_perfil) == DEFAULT_AVATAR_SENTINEL:
        return

    # Cloudinary: borrado fiable por el mismo public_id con el que subimos
    if settings.STORAGE_TYPE == "cloudinary":
        try:
            usuario_hash = hashlib.sha256(usuario_actual.encode()).hexdigest()
            public_id = f"perfiles/perfil_{usuario_hash}"
            cloudinary.uploader.destroy(
                public_id,
                resource_type="image",
                invalidate=True
            )
        except Exception:
            logger.warning(
                "error_borrado_cloudinary",
                extra={
                    "usuario": usuario_actual,
                    "foto": foto_perfil,
                    "storage_type": settings.STORAGE_TYPE,
                },
                exc_info=True,
            )
        return

    # Local (tu lógica actual)
    try:
        carpeta_imagenes = settings.UPLOAD_DIR
        ruta = os.path.join(carpeta_imagenes, os.path.basename(foto_perfil))
        if os.path.exists(ruta):
            os.remove(ruta)
    except Exception:
        logger.warning(
            "error_borrado_archivo_local",
            extra={
                "usuario": usuario_actual,
                "foto": foto_perfil,
                "storage_type": settings.STORAGE_TYPE,
            },
            exc_info=True,
        )
        return
    