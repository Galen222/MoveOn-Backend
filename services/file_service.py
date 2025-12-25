# services/file_service.py

"""
services/file_service.py

Servicio para manejar la validación y procesamiento de archivos.
"""
import os
import time
import glob
import hashlib
from typing import Optional
from fastapi import UploadFile, HTTPException, Request
import cloudinary.uploader
import cloudinary
from config import settings

# Si la API está en producción carga variables de Cloudinary.
if settings.STORAGE_TYPE == "cloudinary":
    cloudinary.config(
        cloud_name = settings.CLOUDINARY_CLOUD_NAME,
        api_key = settings.CLOUDINARY_API_KEY,
        api_secret = settings.CLOUDINARY_API_SECRET,
        secure = True
    )

# Firmas de contenido malicioso conocidas.
MALICIOUS_SIGNATURES = [
    b'<%eval', b'<%execute', b'<script>',
    b'javascript:', b'vbscript:',
    b'.exe\x00', b'.dll\x00'
]

def construir_url_foto(foto_perfil: Optional[str], request: Request) -> Optional[str]:
    if not foto_perfil:
        return None
    # Si la foto es de Cloudinary (empieza por http), se usa tal cual. Si es local, se construye la URL.
    if foto_perfil.startswith("http"):
        return foto_perfil
    url_base = str(request.base_url).rstrip("/")
    return f"{url_base}/imagenes/{foto_perfil}"

async def validar_seguridad(archivo: UploadFile):
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
    content = await archivo.read()
    # Regresar el puntero del archivo al inicio
    await archivo.seek(0)
    content_lower = content.lower()
    for signature in MALICIOUS_SIGNATURES:
        if signature in content_lower:
            raise HTTPException(status_code=400, detail="Error: Contenido malicioso detectado")
    return True

async def procesar_subida(archivo: UploadFile, usuario_actual: str) -> str:
    """Manejador de subida que elige entre Local o Nube."""
    if settings.STORAGE_TYPE == "cloudinary":
        return await guardar_nube(archivo, usuario_actual)
    return await guardar_local(archivo, usuario_actual)

async def guardar_local(archivo: UploadFile, usuario_actual: str) -> str:
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

    # Buscar archivos que contengan el hash.
    patron_antiguo = os.path.join(carpeta_imagenes, f"perfil_{nombre_seguro}_*")
    for archivo_antiguo in glob.glob(patron_antiguo):
        try: 
            os.remove(archivo_antiguo)
        except OSError: 
            pass

    # Construir la ruta final usando el hash.
    nombre_archivo = f"perfil_{nombre_seguro}_{int(time.time())}{extension}"
    ruta_final = os.path.join(carpeta_imagenes, nombre_archivo)

    try:
        await archivo.seek(0)
        contenido = await archivo.read()

        with open(ruta_final, "wb") as buffer:
            buffer.write(contenido)
    except Exception:
        raise HTTPException(status_code=500, detail="Error: No se ha podido guardar la imagen localmente")
    
    return nombre_archivo

async def guardar_nube(archivo: UploadFile, usuario_actual: str) -> str:
    """Lógica de guardado en Cloudinary usando Hash."""
    try:
        # Generar el hash del usuario
        usuario_hash = hashlib.sha256(usuario_actual.encode()).hexdigest()

        resultado = cloudinary.uploader.upload(
            archivo.file,
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