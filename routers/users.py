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
from typing import List, Optional
from schemas import ProvinciaEspaña

router = APIRouter(tags=["Usuarios"])

@router.post("/registro", response_model=schemas.RespuestaRegistro)
def registro(datos: schemas.Registro, 
             db: Session = Depends(obtener_db), 
             _auth_app=Depends(auth.verificar_sesion_aplicacion)):
    """Registro de nuevo usuario con validación de duplicados."""
    return user_service.registrar_nuevo_usuario(db, datos)

@router.get("/perfil/informacion", response_model=schemas.RespuestaInformacionPerfil) 
def informacion_perfil(request: Request,
                      db: Session = Depends(obtener_db), 
                      _auth_app=Depends(auth.verificar_sesion_aplicacion),
                      usuario_actual: str = Depends(auth.obtener_usuario_actual)):
    """Obtiene los datos del perfil."""
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

@router.get("/perfil/publico/{nombre_usuario}", response_model=schemas.InformacionPerfilPublico)
def ver_perfil_publico(
    nombre_usuario: str, # El usuario a ver.
    request: Request,
    db: Session = Depends(obtener_db),
    _auth_app=Depends(auth.verificar_sesion_aplicacion)
):
    """
    Permite ver la ficha reducida de otro usuario si este tiene el perfil visible.
    Calcula los puntos de ese usuario en tiempo real basándose en los metros acumulados.
    """
    # Obtener el usuario.
    usuario_objetivo = user_service.obtener_perfil_publico(db, nombre_usuario)
    
    # Calcular puntos (1 KM = 1 Punto).
    metros = usuario_objetivo.total_metros if usuario_objetivo.total_metros else 0
    puntos = int(metros / 1000)

    # Devolver solo los datos públicos.
    return {
        "nombre_usuario": usuario_objetivo.nombre_usuario,
        "provincia": usuario_objetivo.provincia,
        "foto_perfil": file_service.construir_url_foto(usuario_objetivo.foto_perfil, request),
        "total_puntos": puntos
    }

@router.post("/perfil/foto", response_model=schemas.RespuestaGenerica)
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

@router.patch("/perfil/actualizar", response_model=schemas.RespuestaGenerica)
def actualizar_perfil(datos: schemas.ActualizarPerfil, 
                      db: Session = Depends(obtener_db), 
                      _auth_app=Depends(auth.verificar_sesion_aplicacion),
                      usuario_actual: str = Depends(auth.obtener_usuario_actual)):
    """Permite al usuario modificar su perfil."""
    usuario = user_service.obtener_perfil(db, usuario_actual)
    return user_service.actualizar_perfil_usuario(db, usuario, datos)

@router.delete("/perfil/borrar", response_model=schemas.RespuestaGenerica)
def borrar_perfil(db: Session = Depends(obtener_db), 
                  _auth_app=Depends(auth.verificar_sesion_aplicacion),
                  usuario_actual: str = Depends(auth.obtener_usuario_actual)):
    """Elimina la cuenta y borra la foto (local o nube)."""
    usuario = user_service.obtener_perfil(db, usuario_actual)
    
    file_service.borrar_foto(usuario.foto_perfil, usuario_actual)
    return user_service.eliminar_cuenta(db, usuario)

@router.get("/ranking/obtener", response_model=List[schemas.ObtenerRanking])
def obtener_ranking(
    request: Request,
    provincia: Optional[ProvinciaEspaña] = None, # filtro por provincia opcional.
    db: Session = Depends(obtener_db),
    _auth_app=Depends(auth.verificar_sesion_aplicacion)
):
    """
    Devuelve el TOP 15 de usuarios con más puntos (KM recorridos).
    Permite filtrar por provincia de foma opcional.
    """
    # Obtener los datos
    ranking = user_service.obtener_ranking(db, provincia)
    
    # Procesar la URL de las fotos para que la App pueda descargarlas.
    ranking_final = []
    for item in ranking:
        # Usar el servicio existente para crear la URL correcta.
        url_foto = file_service.construir_url_foto(item["foto_perfil"], request)
        
        ranking_final.append({
            "nombre_usuario": item["nombre_usuario"],
            "foto_perfil": url_foto,
            "total_puntos": item["total_puntos"]
        })
        
    return ranking_final