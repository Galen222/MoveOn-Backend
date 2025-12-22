# routers/users.py

"""
Endpoints de Usuario y Autenticación.

Define las rutas para el handshake inicial, el registro con validación de 
duplicados, el inicio de sesión y la gestión posterior del perfil de usuario.
"""
from fastapi import APIRouter, Depends, HTTPException, Header, File, UploadFile, Request
from sqlalchemy.orm import Session
from typing import Optional
import database
import auth
import schemas
import shutil
import os
import glob
import time

router = APIRouter(tags=["Autenticación"])

def obtener_db():
    """Dependencia para la conexión a la base de datos."""
    db = database.SessionLocal()
    try:
        yield db
    finally:
        db.close()

@router.get("/handshake")
def handshake(x_app_id: str = Header(None)):
    """Valida la App de Android y entrega un token de sesión temporal."""
    if x_app_id != auth.APP_ID_SECRET:
        raise HTTPException(status_code=403, detail="Error: El acceso no proviene de la aplicación")
    # Crea el token de corta duración
    return {"app_session_token": auth.crear_token_aplicacion()}

@router.post("/login")
def login(datos: schemas.LoginUsuario, 
          db: Session = Depends(obtener_db), 
          _auth_app=Depends(auth.verificar_sesion_aplicacion)):
    """Autentica al usuario y genera el token de acceso JWT final."""
    # Búsqueda flexible por nombre o email.
    usuario_encontrado = db.query(database.Usuario).filter(
        (database.Usuario.email == datos.identificador) | (database.Usuario.nombre_usuario == datos.identificador)
    ).first()

    # Validación de existencia y coincidencia de hash de contraseña.
    if not usuario_encontrado or not auth.comprobar_contraseña(datos.contraseña, str(usuario_encontrado.contraseña_encriptada)):
        raise HTTPException(status_code=401, detail="Error: Credenciales incorrectas")
    
    # Generación del JWT de larga duración.    
    token = auth.crear_token_acceso({"sub": usuario_encontrado.nombre_usuario})
    
    return {
        "estatus": "success",
        "nombre_usuario": usuario_encontrado.nombre_usuario,
        "token_acceso": token
    }

@router.post("/registro")
def registro(datos: schemas.RegistroUsuario, 
             db: Session = Depends(obtener_db), 
             _auth_app=Depends(auth.verificar_sesion_aplicacion)):
    
    # Comprobar si el nombre de usuario ya está tomado o si el correo ya está registrado.
    usuario_existente = db.query(database.Usuario).filter(
        (database.Usuario.nombre_usuario == datos.nombre_usuario) | 
        (database.Usuario.email == datos.email)
    ).first()

    if usuario_existente:
        if usuario_existente.nombre_usuario == datos.nombre_usuario:
            raise HTTPException(status_code=400, detail="Error: El nombre de usuario ya está en uso")
        raise HTTPException(status_code=400, detail="Error: El correo electrónico ya está registrado")

    # Crear el objeto de base de datos con la contraseña ya cifrada.
    nuevo_usuario = database.Usuario(
        nombre_usuario=datos.nombre_usuario,
        nombre_real=datos.nombre_real,
        email=datos.email,
        contraseña_encriptada=auth.encriptar_contraseña(datos.contraseña),
        fecha_nacimiento=datos.fecha_nacimiento,
        ciudad=datos.ciudad,
        perfil_visible=datos.perfil_visible
    )
    
    # Persistencia en PostgreSQL
    db.add(nuevo_usuario)
    db.commit()
    return {"estatus": "success", "mensaje": "Usuario registrado correctamente"}

@router.get("/perfil/informacion")
def obtener_mi_perfil(request: Request,
                      db: Session = Depends(obtener_db), 
                      _auth_app=Depends(auth.verificar_sesion_aplicacion),
                      usuario_actual: str = Depends(auth.obtener_usuario_actual)):
    """
    Obtiene los datos completos del usuario autenticado.
    Identifica al usuario mediante el token JWT del botón Authorize.
    """
    # Buscamos al usuario en la base de datos usando el 'sub' extraído automáticamente del token
    usuario = db.query(database.Usuario).filter(database.Usuario.nombre_usuario == usuario_actual).first()
    
    if not usuario:
        raise HTTPException(status_code=404, detail="Error: Perfil no encontrado")

    url_base = str(request.base_url).rstrip("/")
    url_foto = f"{url_base}/imagenes/{usuario.foto_perfil}" if usuario.foto_perfil else None

    return {
        "nombre_usuario": usuario.nombre_usuario,
        "nombre_real": usuario.nombre_real,
        "email": usuario.email,
        "fecha_nacimiento": usuario.fecha_nacimiento,
        "ciudad": usuario.ciudad,
        "foto_perfil": url_foto,
        "perfil_visible": usuario.perfil_visible
    }
    
@router.post("/perfil/foto")
async def subir_foto_perfil(
    db: Session = Depends(obtener_db),
    _auth_app=Depends(auth.verificar_sesion_aplicacion),
    usuario_actual: str = Depends(auth.obtener_usuario_actual),
    archivo: UploadFile = File(...)
):
    """
    Sube o actualiza la foto de perfil del usuario localmente.
    Valida formato y tamaño máximo de 2MB.
    """
    # Validar que sea una imagen.
    if archivo.content_type not in ["image/jpeg", "image/png", "image/jpg"]:
        raise HTTPException(status_code=400, detail="Error: Solo se permiten imágenes JPG o PNG")

    # Validar tamaño máximo (2MB). Leemos el tamaño del archivo desde el descriptor.
    archivo.file.seek(0, os.SEEK_END)
    tamano = archivo.file.tell()
    # Volvemos al inicio para poder guardarlo después.
    archivo.file.seek(0)
    if tamano > 2 * 1024 * 1024:
        raise HTTPException(status_code=400, detail="Error: La imagen supera los 2MB")

    # Limpiar fotos antiguas usando el patrón del nombre de usuario
    patron_antiguo = os.path.join("uploads", f"perfil_{usuario_actual}_*")
    for archivo_antiguo in glob.glob(patron_antiguo):
        try:
            os.remove(archivo_antiguo)
        except OSError:
            pass 

    # Nombre con timestamp para evitar caché de imagenes
    _, extension = os.path.splitext(archivo.filename or ".jpg")
    timestamp = int(time.time())
    nombre_archivo = f"perfil_{usuario_actual}_{timestamp}{extension.lower()}"
    ruta_final = os.path.join("uploads", nombre_archivo)

    # Guardar el archivo físicamente en la carpeta uploads.
    try:
        with open(ruta_final, "wb") as buffer:
            shutil.copyfileobj(archivo.file, buffer)
    except Exception:
        raise HTTPException(status_code=500, detail="Error: No se ha podido guardar la imagen en el servidor")

    # Actualizar la base de datos.
    usuario = db.query(database.Usuario).filter(database.Usuario.nombre_usuario == usuario_actual).first()
    if not usuario:
        raise HTTPException(status_code=404, detail="Error: Usuario no encontrado")
    
    usuario.foto_perfil = nombre_archivo
    db.commit()

    return {"estatus": "success", "mensaje": "Foto de perfil actualizada correctamente"}
   
@router.patch("/perfil/actualizar")
def actualizar_perfil(datos: schemas.ActualizarPerfil, 
                      db: Session = Depends(obtener_db), 
                      _auth_app=Depends(auth.verificar_sesion_aplicacion),
                      usuario_actual: str = Depends(auth.obtener_usuario_actual)):
    """
    Permite al usuario modificar su perfil de forma selectiva.
    """
    usuario = db.query(database.Usuario).filter(database.Usuario.nombre_usuario == usuario_actual).first() 
    
    if not usuario:
        raise HTTPException(status_code=404, detail="Error: Usuario no encontrado")

    # Actualización selectiva de campos
    if datos.nombre_real: 
        usuario.nombre_real = datos.nombre_real
    
    if datos.email:
    # Buscar si el email lo tiene OTRO usuario distinto al actual
        duplicado = db.query(database.Usuario).filter(
            database.Usuario.email == datos.email,
            database.Usuario.nombre_usuario != usuario_actual
    ).first()
        if duplicado:
            raise HTTPException(status_code=400, detail="Error: El nuevo correo ya está registrado")
        usuario.email = datos.email

    if datos.contraseña:
        # Si cambia contraseña, se debe hashear de nuevo
        usuario.contraseña_encriptada = auth.encriptar_contraseña(datos.contraseña)

    if datos.fecha_nacimiento:
        usuario.fecha_nacimiento = datos.fecha_nacimiento

    if datos.ciudad: 
        usuario.ciudad = datos.ciudad

    if datos.perfil_visible is not None: 
        usuario.perfil_visible = datos.perfil_visible

    db.commit()
    return {"estatus": "success", "mensaje": "Perfil actualizado correctamente"}

@router.delete("/perfil/borrar")
def borrar_perfil(db: Session = Depends(obtener_db), 
                  _auth_app=Depends(auth.verificar_sesion_aplicacion),
                  usuario_actual: str = Depends(auth.obtener_usuario_actual)):
    usuario = db.query(database.Usuario).filter(database.Usuario.nombre_usuario == usuario_actual).first()
    
    if not usuario:
        raise HTTPException(status_code=404, detail="Error: El usuario no existe")

    # Eliminación física de la foto de perfil del servidor
    if usuario.foto_perfil and usuario.foto_perfil != "default_avatar.png":
        ruta_foto = os.path.join("uploads", usuario.foto_perfil)
        if os.path.exists(ruta_foto):
            try:
                os.remove(ruta_foto)
            except OSError:
                pass

    db.delete(usuario)
    db.commit()
    return {"estatus": "success", "mensaje": "Tu cuenta ha sido eliminada permanentemente"}