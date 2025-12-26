# routers/users.py

"""
Endpoints de Gestión de Perfil de Usuario.

Define las rutas para el registro de nuevos usuarios y la gestión 
posterior del perfil (consulta, actualización, foto y borrado).
"""
from fastapi import APIRouter, Depends, File, UploadFile, Request
from sqlalchemy.orm import Session
import auth
import schemas
from services import user_service, file_service
from database import obtener_db
from fastapi.concurrency import run_in_threadpool

router = APIRouter(tags=["Usuarios"])

@router.post("/registro")
def registro(datos: schemas.RegistroUsuario, 
             db: Session = Depends(obtener_db), 
             _auth_app=Depends(auth.verificar_sesion_aplicacion)):
    """Registro de nuevo usuario con validación de duplicados."""
    return user_service.registrar_nuevo_usuario(db, datos)

@router.get("/perfil/informacion")
def informacion_perfil(request: Request,
                      db: Session = Depends(obtener_db), 
                      _auth_app=Depends(auth.verificar_sesion_aplicacion),
                      usuario_actual: str = Depends(auth.obtener_usuario_actual)):
    """Obtiene los datos del perfil. Maneja para la imagen de perfil URLs locales o de Cloudinary."""
    usuario = user_service.obtener_perfil(db, usuario_actual)
    
    return {
        "nombre_usuario": usuario.nombre_usuario,
        "nombre_real": usuario.nombre_real,
        "email": usuario.email,
        "fecha_nacimiento": usuario.fecha_nacimiento,
        "genero": usuario.genero,
        "altura": usuario.altura,
        "peso": usuario.peso,        
        "provincia": usuario.provincia,
        "foto_perfil": file_service.construir_url_foto(usuario.foto_perfil, request),
        "perfil_visible": usuario.perfil_visible
    }
    
@router.post("/perfil/foto")
async def foto_perfil(
    db: Session = Depends(obtener_db),
    _auth_app=Depends(auth.verificar_sesion_aplicacion),
    usuario_actual: str = Depends(auth.obtener_usuario_actual),
    archivo: UploadFile = File(...)
):
    await file_service.validar_seguridad(archivo)
    # Ejecutar la consulta bloqueante en un hilo separado
    usuario = await run_in_threadpool(user_service.obtener_perfil, db, usuario_actual)
    
    # Se procesa la subida.
    nueva_ruta_foto = await file_service.procesar_subida(archivo, usuario_actual)
    
    # Si la subida fue exitosa, se actualiza la base de datos.
    usuario.foto_perfil = nueva_ruta_foto
    
    # Ejecutar el commit bloqueante en un hilo separado
    await run_in_threadpool(db.commit)
    
    return {"estatus": "success", "mensaje": "Foto actualizada correctamente"}

@router.patch("/perfil/actualizar")
def actualizar_perfil(datos: schemas.ActualizarPerfil, 
                      db: Session = Depends(obtener_db), 
                      _auth_app=Depends(auth.verificar_sesion_aplicacion),
                      usuario_actual: str = Depends(auth.obtener_usuario_actual)):
    """Permite al usuario modificar su perfil."""
    usuario = user_service.obtener_perfil(db, usuario_actual)
    return user_service.actualizar_perfil_usuario(db, usuario, datos)

@router.delete("/perfil/borrar")
def borrar_perfil(db: Session = Depends(obtener_db), 
                  _auth_app=Depends(auth.verificar_sesion_aplicacion),
                  usuario_actual: str = Depends(auth.obtener_usuario_actual)):
    """Elimina la cuenta y borra la foto (local o nube)."""
    usuario = user_service.obtener_perfil(db, usuario_actual)
    
    file_service.borrar_foto(usuario.foto_perfil, usuario_actual)
    return user_service.eliminar_cuenta(db, usuario)