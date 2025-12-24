# services/user_service.py

"""
Servicio de Gestión de Usuarios.
Encapsula la lógica de negocio de registro y actualización de perfil.
"""
from sqlalchemy.orm import Session
from fastapi import HTTPException
import database
import auth
import schemas

def registrar_nuevo_usuario(db: Session, datos: schemas.RegistroUsuario):
    """Registro de nuevo usuario con validación de duplicados."""
    # Buscar si existe ignorando mayúsculas/minúsculas
    usuario_existente = db.query(database.Usuario).filter(
        (database.Usuario.nombre_usuario.ilike(datos.nombre_usuario)) | 
        (database.Usuario.email == datos.email.lower())
    ).first()

    if usuario_existente:
        # Comprobación específica para el mensaje de error
        if usuario_existente.nombre_usuario.lower() == datos.nombre_usuario.lower():
            raise HTTPException(status_code=400, detail="Error: El nombre de usuario ya está en uso")
        raise HTTPException(status_code=400, detail="Error: El email ya está en uso")

    nuevo_usuario = database.Usuario(
        nombre_usuario=datos.nombre_usuario,
        nombre_real=datos.nombre_real,
        email=datos.email,
        contraseña_encriptada=auth.encriptar_contraseña(datos.contraseña),
        fecha_nacimiento=datos.fecha_nacimiento,
        ciudad=datos.ciudad,
        perfil_visible=datos.perfil_visible
    )
    
    db.add(nuevo_usuario)
    db.commit()
    return {
        "estatus": "success", 
        "mensaje": "Usuario registrado correctamente",
        "nombre_usuario": nuevo_usuario.nombre_usuario
    }

def obtener_perfil(db: Session, usuario_actual: str):
    """Busca al usuario en la base de datos usando el 'sub' extraído automáticamente del token."""
    usuario = db.query(database.Usuario).filter(database.Usuario.nombre_usuario == usuario_actual).first()
    if not usuario:
        raise HTTPException(status_code=404, detail="Error: Perfil de usuario no encontrado")
    return usuario

def actualizar_perfil_usuario(db: Session, usuario: database.Usuario, datos: schemas.ActualizarPerfil):
    """Lógica para modificar el perfil de usuario."""
    if datos.nombre_real: usuario.nombre_real = datos.nombre_real
    if datos.email:
        duplicado = db.query(database.Usuario).filter(
            database.Usuario.email == datos.email,
            database.Usuario.nombre_usuario != usuario.nombre_usuario
        ).first()
        if duplicado:
            raise HTTPException(status_code=400, detail="Error: El email ya está en uso")
        usuario.email = datos.email
    
    if datos.contraseña:
        usuario.contraseña_encriptada = auth.encriptar_contraseña(datos.contraseña)
    if datos.fecha_nacimiento: usuario.fecha_nacimiento = datos.fecha_nacimiento
    if datos.ciudad: usuario.ciudad = datos.ciudad
    if datos.perfil_visible is not None: usuario.perfil_visible = datos.perfil_visible

    db.commit()
    return {"estatus": "success", "mensaje": "Perfil de usuario actualizado correctamente"}

def eliminar_cuenta(db: Session, usuario: database.Usuario):
    """Elimina permanentemente el registro de la base de datos."""
    db.delete(usuario)
    db.commit()
    return {"estatus": "success", "mensaje": "Tu cuenta ha sido eliminada permanentemente"}