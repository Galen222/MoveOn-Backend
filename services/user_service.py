# services/user_service.py

"""
Servicio de Gestión de Usuarios.
Encapsula la lógica de negocio de registro y actualización de perfil.
"""
from sqlalchemy.orm import Session
from sqlalchemy import desc
from fastapi import HTTPException
import database
import auth
import schemas
from typing import Optional

def registrar_nuevo_usuario(db: Session, datos: schemas.Registro):
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
        genero=datos.genero,
        altura=datos.altura,
        peso=datos.peso,        
        provincia=datos.provincia,
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
    if datos.genero: usuario.genero = datos.genero
    if datos.altura is not None: usuario.altura = datos.altura
    if datos.peso is not None: usuario.peso = datos.peso    
    if datos.provincia: usuario.provincia = datos.provincia
    if datos.perfil_visible is not None: usuario.perfil_visible = datos.perfil_visible

    db.commit()
    return {"estatus": "success", "mensaje": "Perfil de usuario actualizado correctamente"}

def obtener_perfil_publico(db: Session, nombre_objetivo: str):
    """
    Busca un usuario por nombre para mostrar su ficha pública.
    Solo devuelve datos si el usuario existe y tiene perfil_visible=True.
    """
    usuario = db.query(database.Usuario).filter(
        database.Usuario.nombre_usuario == nombre_objetivo
    ).first()

    if not usuario:
        raise HTTPException(status_code=404, detail="Error: Usuario no encontrado")

    # LÓGICA DE PRIVACIDAD
    if not usuario.perfil_visible:
        raise HTTPException(status_code=403, detail="Error: Este perfil es privado")

    return usuario

def eliminar_cuenta(db: Session, usuario: database.Usuario):
    """Elimina permanentemente el registro de la base de datos."""
    db.delete(usuario)
    db.commit()
    return {"estatus": "success", "mensaje": "Tu cuenta ha sido eliminada permanentemente"}

def obtener_ranking(db: Session, provincia: Optional[str] = None):
    """
    Obtiene el Ranking de los usuarios con más kilometros recorridos.
    """
    
    # Query sobre la tabla Usuarios
    query = db.query(
        database.Usuario.nombre_usuario,
        database.Usuario.foto_perfil,
        database.Usuario.total_metros
    )

    # Filtro opcional
    if provincia:
        query = query.filter(database.Usuario.provincia == provincia)

    # Ordenar por el campo pre-calculado.
    # Filtrar que total_metros > 0 para no llenar el ranking de usuarios inactivos.
    # Filtrar que solo los usuarios con perfil publico aparezcan en el ranking.
    resultados = query.filter(
            database.Usuario.total_metros > 0,
            database.Usuario.perfil_visible == True
        )\
        .order_by(desc(database.Usuario.total_metros))\
        .limit(15)\
        .all()
    
    # Convertir Metros a Puntos
    ranking_procesado = []
    for nombre, foto, total_metros in resultados:
        # 1 KM = 1 Punto (División entera).
        puntos = int(total_metros / 1000)
        
        ranking_procesado.append({
            "nombre_usuario": nombre,
            "foto_perfil": foto, 
            "total_puntos": puntos
        })
        
    return ranking_procesado