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

from fastapi import UploadFile, HTTPException, Request
import cloudinary.uploader
import cloudinary

from config import settings

# Pillow para verificar que el archivo es realmente una imagen
from PIL import Image, UnidentifiedImageError

# Límite de seguridad (anti "decompression bomb")
# Puedes ajustar este valor si lo necesitas (20MP por defecto)
MAX_IMAGE_PIXELS = 13_000_000
Image.MAX_IMAGE_PIXELS = MAX_IMAGE_PIXELS

# Si la API está en producción carga variables de Cloudinary.
if settings.STORAGE_TYPE == "cloudinary":
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


def construir_url_foto(foto_perfil: Optional[str], request: Request) -> Optional[str]:
    if not foto_perfil:
        return None

    # Si la foto es de Cloudinary (empieza por http), se usa tal cual. Si es local, se construye la URL.
    if foto_perfil.startswith("http"):
        return foto_perfil

    url_base = str(request.base_url).rstrip("/")
    return f"{url_base}/imagenes/{foto_perfil}"


def validar_seguridad(archivo: UploadFile):
    # Validar tipo de archivo.
    if archivo.content_type not in ["image/jpeg", "image/png", "image/jpg"]:
        raise HTTPException(status_code=400, detail="Error: Solo imágenes JPG o PNG")

    # Validar tamaño máximo (2MB). Leemos el tamaño del archivo desde el descriptor.
    archivo.file.seek(0, os.SEEK_END)
    tamano = archivo.file.tell()
    # Vuelve al inicio para poder guardarlo después.
    archivo.file.seek(0)

    if tamano > 2 * 1024 * 1024:
        raise HTTPException(status_code=400, detail="Error: La imagen supera los 2MB")

    # Escaneo de firmas maliciosas
    content = archivo.file.read()
    # Regresar el puntero del archivo al inicio
    archivo.file.seek(0)

    content_lower = content.lower()
    for signature in MALICIOUS_SIGNATURES:
        if signature in content_lower:
            raise HTTPException(status_code=400, detail="Error: Contenido malicioso detectado")

    # Verificar que el archivo ES realmente una imagen (no solo el content_type)
    try:
        img = Image.open(BytesIO(content))
        img.verify()
    except (UnidentifiedImageError, OSError):
        raise HTTPException(status_code=400, detail="Error: El archivo no es una imagen válida")

    # Validar dimensiones/píxeles (anti "decompression bomb")
    try:
        img2 = Image.open(BytesIO(content))
        img2.load()
        if (img2.width * img2.height) > MAX_IMAGE_PIXELS:
            raise HTTPException(status_code=400, detail="Error: Imagen demasiado grande")
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(status_code=400, detail="Error: El archivo no es una imagen válida")

    return True


def _reencode_image(archivo: UploadFile, extension: str) -> bytes:
    """
    Re-encodea la imagen para:
    - asegurar formato real (JPEG/PNG)
    - eliminar metadata
    """
    archivo.file.seek(0)
    raw = archivo.file.read()
    archivo.file.seek(0)

    try:
        im = Image.open(BytesIO(raw))
        im.load()
    except (UnidentifiedImageError, OSError):
        raise HTTPException(status_code=400, detail="Error: El archivo no es una imagen válida")

    out = BytesIO()

    # Elegimos formato final según la extensión calculada
    if extension == ".png":
        # PNG puede mantener transparencia
        if im.mode not in ("RGB", "RGBA"):
            im = im.convert("RGBA")
        im.save(out, format="PNG", optimize=True)
        return out.getvalue()

    # JPEG por defecto
    # JPEG no soporta alpha, convertimos a RGB si hace falta
    if im.mode in ("RGBA", "P"):
        im = im.convert("RGB")
    im.save(out, format="JPEG", optimize=True, quality=85)
    return out.getvalue()


def procesar_subida(archivo: UploadFile, usuario_actual: str, foto_anterior_bd: Optional[str] = None) -> str:
    """Manejador de subida que elige entre Local o Nube."""
    if settings.STORAGE_TYPE == "cloudinary":
        return guardar_nube(archivo, usuario_actual)
    return guardar_local(archivo, usuario_actual, foto_anterior_bd)


def guardar_local(archivo: UploadFile, usuario_actual: str, foto_anterior_bd: Optional[str] = None) -> str:
    """Lógica de guardado local segura."""
    # Usar la variable de settings.
    carpeta_imagenes = settings.UPLOAD_DIR

    # Genera un HASH SHA-256 para el nombre del archivo de la foto de perfil.
    nombre_seguro = hashlib.sha256(usuario_actual.encode()).hexdigest()

    # Definir extensión segura basada en content_type
    mapa_extensiones = {
        "image/jpeg": ".jpg",
        "image/jpg": ".jpg",
        "image/png": ".png"
    }
    extension = mapa_extensiones.get(archivo.content_type or "", ".jpg")

    # Re-encode para limpiar metadata y asegurar formato real
    data_limpia = _reencode_image(archivo, extension)

    # Borramos explícitamente la foto referenciada en la BD
    if foto_anterior_bd and foto_anterior_bd != "default_avatar.png" and not foto_anterior_bd.startswith("http"):
        nombre_archivo_antiguo = os.path.basename(foto_anterior_bd)
        ruta_antigua = os.path.join(carpeta_imagenes, nombre_archivo_antiguo)
        if os.path.exists(ruta_antigua):
            try:
                os.remove(ruta_antigua)
            except OSError:
                pass

    # Construir la ruta final usando el hash.
    nombre_archivo = f"perfil_{nombre_seguro}_{int(time.time())}{extension}"
    ruta_final = os.path.join(carpeta_imagenes, nombre_archivo)

    try:
        with open(ruta_final, "wb") as buffer:
            buffer.write(data_limpia)
    except Exception:
        raise HTTPException(status_code=500, detail="Error: No se ha podido guardar la imagen localmente")

    return nombre_archivo


def guardar_nube(archivo: UploadFile, usuario_actual: str) -> str:
    """Lógica de guardado en Cloudinary usando Hash."""
    try:
        # Generar el hash del usuario
        usuario_hash = hashlib.sha256(usuario_actual.encode()).hexdigest()

        # Definir extensión segura basada en content_type (mismo criterio que en local)
        mapa_extensiones = {
            "image/jpeg": ".jpg",
            "image/jpg": ".jpg",
            "image/png": ".png"
        }
        extension = mapa_extensiones.get(archivo.content_type or "", ".jpg")

        # Re-encode para limpiar metadata y asegurar formato real
        data_limpia = _reencode_image(archivo, extension)

        resultado = cloudinary.uploader.upload(
            BytesIO(data_limpia),
            folder="perfiles",
            # Usar el hash en lugar del nombre de usuario legible
            public_id=f"perfil_{usuario_hash}",
            overwrite=True,
            resource_type="image"
        )
        return resultado.get("secure_url")
    except Exception:
        raise HTTPException(status_code=500, detail="Error: No se ha podido subir la imagen a la nube")


def borrar_foto(foto_perfil: str, usuario_actual: str):
    """Lógica de borrado permanente segura usando Hashing."""
    # Usar las variables de settings.
    storage = settings.STORAGE_TYPE
    carpeta_imagenes = settings.UPLOAD_DIR

    # Generar el mismo hash que se usa al guardar
    usuario_hash = hashlib.sha256(usuario_actual.encode()).hexdigest()

    if storage != "cloudinary" and foto_perfil and foto_perfil != "default_avatar.png":
        # Usar basename por precaución (limpia rutas como ../)
        nombre_archivo_seguro = os.path.basename(foto_perfil)
        ruta_foto = os.path.join(carpeta_imagenes, nombre_archivo_seguro)

        # Solo borrar la foto si el nombre del archivo contiene el hash de este usuario.
        if f"perfil_{usuario_hash}" in nombre_archivo_seguro:
            if os.path.exists(ruta_foto):
                try:
                    os.remove(ruta_foto)
                except OSError:
                    pass

    if storage == "cloudinary":
        try:
            # Usar el mismo hash para borrar en la nube
            cloudinary.uploader.destroy(f"perfiles/perfil_{usuario_hash}")
        except:
            pass
        