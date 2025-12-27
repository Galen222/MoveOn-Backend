# routers/access.py

"""
Endpoints de Seguridad de Aplicación y Autenticación.

Gestiona el apretón de manos (handshake) inicial para validar la App 
y el inicio de sesión de usuarios para obtener tokens de acceso.
"""
from fastapi import APIRouter, Depends, HTTPException, Header, Request
from sqlalchemy.orm import Session
import auth
import schemas
from database import obtener_db
from services import access_service
from config import settings
from limiter_config import limiter

router = APIRouter(tags=["Seguridad"])

@router.get("/handshake", response_model=schemas.RespuestaGenerica)
def handshake(x_app_id: str = Header(None)):
    """Valida la App de Android y entrega un token de sesión temporal."""
    if x_app_id != settings.APP_ID_SECRET:
        raise HTTPException(status_code=403, detail="Error: El acceso no proviene de la aplicación MoveOn")
    # Crea el token de corta duración.
    return {"app_session_token": auth.crear_token_aplicacion()}

@router.post("/login", response_model=schemas.RespuestaLogin)
@limiter.limit("20/minute") # Limite 20 intentos por minuto
def login(request: Request,
          datos: schemas.Login, 
          db: Session = Depends(obtener_db), 
          _auth_app=Depends(auth.verificar_sesion_aplicacion)):
    """Autentica al usuario y genera el token de acceso JWT final."""
    # Búsqueda flexible por nombre o email.
    usuario_encontrado = access_service.buscar_por_identificador(db, datos.identificador)

    # Validación de existencia y coincidencia de hash de contraseña.
    if not usuario_encontrado or not auth.comprobar_contraseña(datos.contraseña, str(usuario_encontrado.contraseña_encriptada)):
        raise HTTPException(status_code=401, detail="Error: Credenciales no validas")
    
    # Generación del JWT de larga duración.
    token = auth.crear_token_acceso({"sub": usuario_encontrado.nombre_usuario})
    
    return {
        "estatus": "success",
        "nombre_usuario": usuario_encontrado.nombre_usuario,
        "token_acceso": token
    }

@router.post("/contraseña/solicitar", response_model=schemas.RespuestaGenerica)
async def solicitar_contraseña(datos: schemas.SolicitarContraseña, 
                     db: Session = Depends(obtener_db),
                     _auth_app=Depends(auth.verificar_sesion_aplicacion)):
    """Solicitar código de 6 dígitos al email."""
    return await access_service.generar_codigo_recuperacion(db, datos.email)

@router.post("/contraseña/confirmar", response_model=schemas.RespuestaGenerica)
def confirmar_contraseña(datos: schemas.ConfirmarContraseña, 
                     db: Session = Depends(obtener_db),
                     _auth_app=Depends(auth.verificar_sesion_aplicacion)):
    """Enviar código y nueva contraseña para resetear."""
    return access_service.resetear_contraseña(db, datos)