#routers/users.py

"""
Endpoints de Usuario y Autenticación.

Rutas protegidas por handshake que procesan el registro y login
utilizando esquemas de validación Pydantic.
"""
from fastapi import APIRouter, Depends, HTTPException, Header
from sqlalchemy.orm import Session
import database
import auth
import schemas

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
    """Paso 1: Identifica la aplicación y entrega un token de sesión temporal."""
    if x_app_id != auth.APP_ID_SECRET:
        raise HTTPException(status_code=403, detail="Acceso denegado: El acceso no proviene de la aplicación")
    
    # Crea el token de corta duración definido en auth.py
    return {"app_session_token": auth.crear_token_aplicacion()}

@router.post("/registro")
def registro(datos: schemas.RegistroUsuario, 
             db: Session = Depends(obtener_db), 
             _auth=Depends(auth.verificar_sesion_aplicacion)):
    """Paso 2: Registra al usuario validando duplicados y formato de datos."""
    
    # Comprobar si el nombre de usuario ya está tomado
    usuario_existe = db.query(database.Usuario).filter(database.Usuario.nombre == datos.usuario).first()
    if usuario_existe:
        raise HTTPException(status_code=400, detail="Registro denegado: El nombre de usuario ya está en uso")

    # Comprobar si el correo ya está registrado
    email_existe = db.query(database.Usuario).filter(database.Usuario.email == datos.email).first()
    if email_existe:
        raise HTTPException(status_code=400, detail="Registro denegado: El correo electrónico ya está registrado")

    # Crear el objeto de base de datos con la contraseña ya cifrada
    nuevo_usuario = database.Usuario(
        nombre=datos.usuario, 
        email=datos.email, 
        contraseña_encriptada=auth.encriptar_contraseña(datos.contraseña)
    )
    
    # Persistencia en PostgreSQL
    db.add(nuevo_usuario)
    db.commit()
    return {"estatus": "success", "mensaje": "Acceso y registro permitido: Usuario registrado correctamente"}

@router.post("/login")
def login(datos: schemas.LoginUsuario, 
          db: Session = Depends(obtener_db), 
          _auth=Depends(auth.verificar_sesion_aplicacion)):
    """Paso 3: Autentica al usuario y entrega el token de acceso final."""
    
    # Búsqueda flexible por nombre o email
    usuario_encontrado = db.query(database.Usuario).filter(
        (database.Usuario.email == datos.identificador) | (database.Usuario.nombre == datos.identificador)
    ).first()

    # Validación de existencia y coincidencia de hash de contraseña
    if not usuario_encontrado or not auth.comprobar_contraseña(datos.contraseña, str(usuario_encontrado.contraseña_encriptada)):
        raise HTTPException(status_code=401, detail="Acceso denegado: Credenciales incorrectas")
    
    # Generación del JWT de larga duración
    token = auth.crear_token_acceso(datos={"sub": usuario_encontrado.nombre})
    
    return {
        "estatus": "success",
        "nombre_usuario": usuario_encontrado.nombre,
        "token_acceso": token
    }