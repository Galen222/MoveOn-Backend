# routers/access.py

"""
Endpoints de Seguridad de Aplicación y Autenticación.

Gestiona el apretón de manos (handshake) inicial para validar la App,
el inicio de sesión, refresh y cierre de sesión.
"""
from fastapi import APIRouter, Depends, HTTPException, Header, Request, BackgroundTasks
from sqlalchemy.orm import Session
import auth
import schemas
from database import obtener_db
from services import access_service
from config import settings
from limiter_config import limiter

router = APIRouter(tags=["Seguridad"])

@router.get("/handshake", response_model=schemas.RespuestaHandshake)
@limiter.limit("30/minute")
def handshake(
    request: Request,
    x_app_id: str = Header(None)
):
    """Valida el identificador de app y entrega un token de sesión temporal."""
    if x_app_id != settings.APP_ID:
        raise HTTPException(status_code=403, detail="Error: El acceso no proviene de la aplicación MoveOn")
    # Crea el token de corta duración.
    return {"app_session_token": auth.crear_token_aplicacion()}

@router.post("/login", response_model=schemas.RespuestaLogin)
@limiter.limit("20/minute") # Limite 20 intentos por minuto
def login(
    request: Request,
    datos: schemas.Login,
    db: Session = Depends(obtener_db),
    _auth_app=Depends(auth.verificar_sesion_aplicacion)
):
    """Autentica al usuario y genera access token + refresh token."""
    # Búsqueda flexible por nombre o email.
    usuario_encontrado = access_service.buscar_por_identificador(db, datos.identificador)
    # Validación de existencia y coincidencia de hash de contraseña.
    if not usuario_encontrado or not auth.comprobar_password(
        datos.password, str(usuario_encontrado.password_encriptada)
    ):
        raise HTTPException(status_code=401, detail="Error: Credenciales no validas")

    return access_service.crear_sesion_login(db, usuario_encontrado)

@router.post("/token/refresh", response_model=schemas.RespuestaRefreshToken)
@limiter.limit("30/minute")
def refresh_token(
    request: Request,
    datos: schemas.SolicitudRefreshToken,
    db: Session = Depends(obtener_db),
    _auth_app=Depends(auth.verificar_sesion_aplicacion)
):
    """Renueva la sesión usando refresh token con rotación."""
    return access_service.refrescar_sesion(db, datos.refresh_token)

@router.post("/logout", response_model=schemas.RespuestaGenerica)
@limiter.limit("60/minute")
def logout(
    request: Request,
    datos: schemas.SolicitudLogout,
    db: Session = Depends(obtener_db),
    _auth_app=Depends(auth.verificar_sesion_aplicacion)
):
    """Revoca la sesión actual (refresh token)."""
    return access_service.cerrar_sesion(db, datos.refresh_token)

@router.post("/password/solicitar", response_model=schemas.RespuestaGenerica)
@limiter.limit("5/10minute")
def solicitar_password(
    request: Request,
    datos: schemas.Solicitarpassword,
    background_tasks: BackgroundTasks,
    db: Session = Depends(obtener_db),
    _auth_app=Depends(auth.verificar_sesion_aplicacion)
):
    """
    Solicitar código de 6 dígitos al email.
    Se envía en segundo plano para no bloquear la API mientras responde el servidor SMTP.
    """
    return access_service.generar_codigo_recuperacion(db, datos.email, background_tasks)

@router.post("/password/confirmar", response_model=schemas.RespuestaGenerica)
@limiter.limit("10/10minute")
def confirmar_password(
    request: Request,
    datos: schemas.Confirmarpassword,
    db: Session = Depends(obtener_db),
    _auth_app=Depends(auth.verificar_sesion_aplicacion)
):
    """Enviar código y nueva contraseña para resetear."""
    return access_service.resetear_password(db, datos)
