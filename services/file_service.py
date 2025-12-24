# services/file_service.py

"""
services/file_service.py

Servicio para manejar la validación y procesamiento de archivos.
"""
import os
import time
import glob
import re
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
    # Eliminar en el usuario cualquier caracter que no sea alfanumérico, guion bajo o guion por seguridad.
    usuario = re.sub(r'[^a-zA-Z0-9_-]', '', usuario_actual)
    
    if not usuario:
        raise HTTPException(status_code=400, detail="Error: Identificador de usuario inválido")

    # Usar el content_type validado previamente ignorando la extensión que el usuario envió en el filename.
    mapa_extensiones = {
        "image/jpeg": ".jpg",
        "image/jpg": ".jpg",
        "image/png": ".png"
    }
    extension = mapa_extensiones.get(archivo.content_type or "", ".jpg")

    # Usar usuario sanitizado para buscar y borrar archivos antiguos.
    patron_antiguo = os.path.join("uploads", f"perfil_{usuario}_*")
    for archivo_antiguo in glob.glob(patron_antiguo):
        try: os.remove(archivo_antiguo)
        except OSError: pass

    # Construir la ruta final con el usuario sanitizado.
    nombre_archivo = f"perfil_{usuario}_{int(time.time())}{extension}"
    ruta_final = os.path.join("uploads", nombre_archivo)

    try:
        await archivo.seek(0)
        contenido = await archivo.read()
        # Aquí 'ruta_final' ya no contiene caracteres controlados por el usuario sin filtrar.
        with open(ruta_final, "wb") as buffer:
            buffer.write(contenido)
    except Exception:
        raise HTTPException(status_code=500, detail="Error: No se ha podido guardar la imagen localmente")
    
    return nombre_archivo

async def guardar_nube(archivo: UploadFile, usuario_actual: str) -> str:
    """Lógica de guardado en Cloudinary."""
    try:
        resultado = cloudinary.uploader.upload(
            archivo.file,
            folder="perfiles",
            public_id=f"perfil_{usuario_actual}",
            overwrite=True,
            resource_type="image"
        )
        return resultado.get("secure_url")
    except Exception:
        raise HTTPException(status_code=500, detail="Error: No se ha podido subir la imagen a la nube")

def borrar_foto(foto_perfil: str, usuario_actual: str):
    """Lógica de borrado permanente segura."""    
    storage = settings.STORAGE_TYPE
    
    # Sanitizamos el usuario igual que en guardar_local
    usuario_safe = re.sub(r'[^a-zA-Z0-9_-]', '', usuario_actual)

    if storage != "cloudinary" and foto_perfil and foto_perfil != "default_avatar.png":
        # SEGURIDAD: Usamos os.path.basename para ignorar cualquier ruta de directorios (../) 
        # que pudiera venir en el nombre del archivo.
        nombre_archivo_seguro = os.path.basename(foto_perfil)
        
        # Construimos la ruta
        ruta_foto = os.path.join("uploads", nombre_archivo_seguro)
        
        # Verificación extra: Aseguramos que el archivo a borrar realmente pertenece a este usuario
        if f"perfil_{usuario_safe}" in nombre_archivo_seguro:
            if os.path.exists(ruta_foto):
                try: os.remove(ruta_foto)
                except OSError: pass
                
    if storage == "cloudinary":
        try:
            # Usamos el usuario sanitizado también para la nube
            cloudinary.uploader.destroy(f"perfiles/perfil_{usuario_safe}")
        except: pass