# routers/users.py

"""
Endpoints de Usuario y Autenticación.

Define las rutas para el handshake inicial, el registro con validación de 
duplicados, el inicio de sesión y la gestión posterior del perfil de usuario.
"""
from fastapi import APIRouter, Depends, HTTPException, Header, File, UploadFile
from sqlalchemy.orm import Session
from typing import Optional
import database
import auth
import schemas
import shutil
import os

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
    # Búsqueda flexible por nombre o email
    usuario_encontrado = db.query(database.Usuario).filter(
        (database.Usuario.email == datos.identificador) | (database.Usuario.nombre_usuario == datos.identificador)
    ).first()

    # Validación de existencia y coincidencia de hash de contraseña
    if not usuario_encontrado or not auth.comprobar_contraseña(datos.contraseña, str(usuario_encontrado.contraseña_encriptada)):
        raise HTTPException(status_code=401, detail="Error: Credenciales incorrectas")
    
    # Generación del JWT de larga duración    
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
    """Registro de nuevo usuario."""
    # Comprobar si el nombre de usuario ya está tomado
    if db.query(database.Usuario).filter(database.Usuario.nombre_usuario == datos.nombre_usuario).first():
        raise HTTPException(status_code=400, detail="Error: El nombre de usuario ya está en uso")

    # Comprobar si el correo ya está registrado
    if db.query(database.Usuario).filter(database.Usuario.email == datos.email).first():
        raise HTTPException(status_code=400, detail="Error: El correo electrónico ya está registrado")

    # Crear el objeto de base de datos con la contraseña ya cifrada
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
def obtener_mi_perfil(db: Session = Depends(obtener_db), 
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

    return {
        "nombre_usuario": usuario.nombre_usuario,
        "nombre_real": usuario.nombre_real,
        "email": usuario.email,
        "fecha_nacimiento": usuario.fecha_nacimiento,
        "ciudad": usuario.ciudad,
        "foto_perfil": f"http://127.0.0.1:8000/imagenes/{usuario.foto_perfil}" if usuario.foto_perfil else None,
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
    # 1. Validar que sea una imagen
    if archivo.content_type not in ["image/jpeg", "image/png", "image/jpg"]:
        raise HTTPException(status_code=400, detail="Error: Solo se permiten imágenes JPG o PNG")

    # 2. Validar tamaño máximo (2MB). Leemos el tamaño del archivo desde el descriptor
    archivo.file.seek(0, os.SEEK_END)
    tamano_archivo = archivo.file.tell()
    archivo.file.seek(0) # Volvemos al inicio para poder guardarlo después

    if tamano_archivo > 2 * 1024 * 1024:
        raise HTTPException(status_code=400, detail="Error: La imagen es demasiado pesada (máximo 2MB)")

    # 3. Definir nombre único y extensión segura para Pylance
    nombre_original = archivo.filename if archivo.filename else "foto.jpg"
    extension = nombre_original.split(".")[-1]
    nombre_archivo = f"perfil_{usuario_actual}.{extension}"
    ruta_final = os.path.join("uploads", nombre_archivo)

    # 4. Guardar el archivo físicamente en la carpeta uploads
    try:
        with open(ruta_final, "wb") as buffer:
            shutil.copyfileobj(archivo.file, buffer)
    except Exception:
        raise HTTPException(status_code=500, detail="Error al guardar la imagen en el servidor")

    # 5. Actualizar la base de datos con protección para Pylance
    usuario = db.query(database.Usuario).filter(database.Usuario.nombre_usuario == usuario_actual).first()
    
    if not usuario:
        raise HTTPException(status_code=404, detail="Error: Usuario no encontrado en la base de datos")

    usuario.foto_perfil = nombre_archivo
    db.commit()

    return {
        "estatus": "success",
        "mensaje": "Foto de perfil actualizada",
        "url_foto": f"/imagenes/{nombre_archivo}"
    }

    return {
        "estatus": "success",
        "mensaje": "Foto de perfil actualizada",
        "url_foto": f"/imagenes/{nombre_archivo}"
    }
    
@router.patch("/perfil/actualizar")
def actualizar_perfil(datos: schemas.ActualizarPerfil, 
                      db: Session = Depends(obtener_db), 
                      _auth_app=Depends(auth.verificar_sesion_aplicacion),
                      usuario_actual: str = Depends(auth.obtener_usuario_actual)):
    """
    Permite al usuario modificar su perfil.
    Utiliza el token JWT para identificar al usuario de forma segura.
    """
    usuario = db.query(database.Usuario).filter(database.Usuario.nombre_usuario == usuario_actual).first() 
    
    if not usuario:
        raise HTTPException(status_code=404, detail="Error: Usuario no encontrado")

    if datos.nombre_real: usuario.nombre_real = datos.nombre_real
    if datos.ciudad: usuario.ciudad = datos.ciudad
    if datos.foto_perfil: usuario.foto_perfil = datos.foto_perfil
    if datos.perfil_visible is not None: usuario.perfil_visible = datos.perfil_visible

    db.commit()
    return {"estatus": "success", "mensaje": "Perfil del usuario actualizado correctamente"}

@router.delete("/perfil/borrar")
def borrar_perfil(db: Session = Depends(obtener_db), 
                  _auth_app=Depends(auth.verificar_sesion_aplicacion),
                  usuario_actual: str = Depends(auth.obtener_usuario_actual)):
    """
    Elimina la cuenta del usuario autenticado permanentemente.
    """
    usuario = db.query(database.Usuario).filter(database.Usuario.nombre_usuario == usuario_actual).first()
    
    if not usuario:
        raise HTTPException(status_code=404, detail="Error: El usuario no existe")

    db.delete(usuario)
    db.commit()
    return {"estatus": "success", "mensaje": "Tu cuenta ha sido eliminada permanentemente"}