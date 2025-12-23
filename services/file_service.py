# services/file_service.py

"""
services/file_service.py

Servicio para manejar la validación y procesamiento de archivos.
Adaptado para MoveOn API con soporte Local y Cloudinary.
"""

import os
import time
import shutil
import glob
from typing import Optional
from fastapi import UploadFile, HTTPException, Request
import cloudinary.uploader

class FileService:
    """
    Servicio para validar y procesar archivos adjuntos.
    """

    def __init__(self):
        # Configuración de almacenamiento (Local o Cloudinary)
        self.STORAGE_TYPE = os.getenv("STORAGE_TYPE", "local")
        
        # Configuración de Cloudinary desde variables de entorno.
        if self.STORAGE_TYPE == "cloudinary":
            cloudinary.config(
                cloud_name = os.getenv("CLOUDINARY_CLOUD_NAME"),
                api_key = os.getenv("CLOUDINARY_API_KEY"),
                api_secret = os.getenv("CLOUDINARY_API_SECRET"),
                secure = True
            )

    # Firmas de contenido malicioso conocidas.
    MALICIOUS_SIGNATURES = [
        b'<%eval', b'<%execute', b'<script>',
        b'javascript:', b'vbscript:',
        b'.exe\x00', b'.dll\x00'
    ]
    
    def construir_url_foto(self, foto_perfil: Optional[str], request: Request) -> Optional[str]:
        """Gestiona la lógica de visualización."""
        if not foto_perfil:
            return None
            
        # Si la foto es de Cloudinary (empieza por http), se usa tal cual. Si es local, se construye la URL.
        if foto_perfil.startswith("http"):
            return foto_perfil
            
        url_base = str(request.base_url).rstrip("/")
        return f"{url_base}/imagenes/{foto_perfil}"
    
    async def validar_seguridad(self, archivo: UploadFile):
        """Valida tamaño y busca firmas maliciosas en el contenido."""
        
        # Validar tipo de archivo.
        if archivo.content_type not in ["image/jpeg", "image/png", "image/jpg"]:
            raise HTTPException(status_code=400, detail="Error: Solo imágenes JPG o PNG")
        
        # Validar tamaño máximo (2MB). Leemos el tamaño del archivo desde el descriptor.
        archivo.file.seek(0, os.SEEK_END)
        tamano = archivo.file.tell()
        # Volvemos al inicio para poder guardarlo después.
        archivo.file.seek(0)
        
        if tamano > 2 * 1024 * 1024:
            raise HTTPException(status_code=400, detail="Error: La imagen supera los 2MB")

        # Escaneo de firmas maliciosas
        content = await archivo.read()
        await archivo.seek(0) # Regresar el puntero del archivo al inicio
        content_lower = content.lower()
        for signature in self.MALICIOUS_SIGNATURES:
            if signature in content_lower:
                raise HTTPException(status_code=400, detail="Error: Contenido malicioso detectado en la imagen")
        
        return True

    async def procesar_subida(self, archivo: UploadFile, usuario_actual: str) -> str:
        """Orquestador de subida que elige entre Local o Nube."""
        if self.STORAGE_TYPE == "cloudinary":
            return await self.guardar_nube(archivo, usuario_actual)
        return await self.guardar_local(archivo, usuario_actual)

    async def guardar_local(self, archivo: UploadFile, usuario_actual: str) -> str:
        """Lógica de guardado local."""
        patron_antiguo = os.path.join("uploads", f"perfil_{usuario_actual}_*")
        for archivo_antiguo in glob.glob(patron_antiguo):
            try: os.remove(archivo_antiguo)
            except OSError: pass

        _, extension = os.path.splitext(archivo.filename or ".jpg")
        timestamp = int(time.time())
        nombre_archivo = f"perfil_{usuario_actual}_{timestamp}{extension.lower()}"
        ruta_final = os.path.join("uploads", nombre_archivo)

        try:
            # Volvemos al inicio para asegurarnos de leer todo el contenido
            await archivo.seek(0)
            contenido = await archivo.read()
            with open(ruta_final, "wb") as buffer:
                buffer.write(contenido)
        except Exception:
            raise HTTPException(status_code=500, detail="Error: No se ha podido guardar la imagen en el servidor")
        
        return nombre_archivo

    async def guardar_nube(self, archivo: UploadFile, usuario_actual: str) -> str:
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
            raise HTTPException(status_code=500, detail="Error: No se ha podido guardar la imagen en la nube")

    def borrar_foto(self, foto_perfil: str, usuario_actual: str):
        """Lógica de borrado permanente."""
        if self.STORAGE_TYPE != "cloudinary" and foto_perfil and foto_perfil != "default_avatar.png":
            ruta_foto = os.path.join("uploads", foto_perfil)
            if os.path.exists(ruta_foto):
                try: os.remove(ruta_foto)
                except OSError: pass
                
        if self.STORAGE_TYPE == "cloudinary":
            try:
                cloudinary.uploader.destroy(f"perfiles/perfil_{usuario_actual}")
            except: pass