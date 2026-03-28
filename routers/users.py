# routers/users.py

"""
Endpoints de Gestión de Perfil de Usuario.
Define las rutas para el registro de nuevos usuarios y la gestión
posterior del perfil (consulta, actualización, foto y borrado).
"""
from fastapi import (
    APIRouter,
    Depends,
    File,
    UploadFile,
    Request,
    Query,
    BackgroundTasks,
    HTTPException,
)
from sqlalchemy.ext.asyncio import AsyncSession
import logging
import auth
import schemas
from typing import List, Optional
from services import user_service, file_service, social_auth_service
from services.identity_rate_limit import check_identity_limit
from database import obtener_db
from schemas import ProvinciaEspaña
from utils import calculos
from starlette.concurrency import run_in_threadpool
from config import settings
from exceptions import app_http_exception
from ip_rate_limit import rate_limit
from datetime import datetime, timezone

logger = logging.getLogger("app.users")

# Inyectamos la dependencia a nivel de Router para todos los endpoints de este archivo
router = APIRouter(
    tags=["Usuarios"], dependencies=[Depends(auth.verificar_sesion_aplicacion)]
)


@router.post("/registro", response_model=schemas.RespuestaRegistro)
@rate_limit(settings.RL_REGISTRO)
async def registro(
    request: Request, datos: schemas.Registro, db: AsyncSession = Depends(obtener_db)
):
    """Registro de nuevo usuario con validación de duplicados."""
    # Rate-limit adicional por identidad/email (anti-abuso distribuido)
    check_identity_limit("registro", str(datos.email), settings.RL_REGISTRO_ID)

    return await user_service.registrar_nuevo_usuario(db, datos)


@router.post("/registro/social", response_model=schemas.RespuestaLogin)
@rate_limit(settings.RL_REGISTRO)
async def registro_social(
    request: Request,
    datos: schemas.RegistroSocial,
    db: AsyncSession = Depends(obtener_db),
):
    """Registro o inicio de sesión con proveedor social verificado por backend."""
    identidad = await social_auth_service.verificar_token_social(
        datos.provider, datos.token
    )

    identity_key = (
        identidad.email or f"{identidad.provider}:{identidad.provider_user_id}"
    )
    check_identity_limit("registro", identity_key, settings.RL_REGISTRO_ID)

    return await user_service.registrar_usuario_social(db, datos, identidad)


@router.get("/perfil/informacion", response_model=schemas.RespuestaInformacionPerfil)
@rate_limit(settings.RL_PERFIL_INFO)
async def informacion_perfil(
    request: Request,
    db: AsyncSession = Depends(obtener_db),
    usuario_actual_id: int = Depends(auth.obtener_usuario_actual),
):
    """Obtiene los datos del perfil."""
    usuario = await user_service.obtener_perfil(db, usuario_actual_id)

    # Calcular puntos (1 KM = 1 Punto).
    puntos = calculos.calcular_puntos_nivel(usuario.total_metros)

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
        "foto_version": (
            int(usuario.foto_fecha_actualizacion.timestamp())
            if usuario.foto_fecha_actualizacion
            else 0
        ),
        "perfil_visible": usuario.perfil_visible,
        "total_puntos": puntos,
        "total_calorias": int(usuario.total_calorias or 0),
        "objetivo_semanal_metros": int(usuario.objetivo_semanal_metros or 50000),
        "objetivo_mensual_metros": int(usuario.objetivo_mensual_metros or 150000),
    }


@router.get(
    "/perfil/informacion/{nombre_usuario}",
    response_model=schemas.InformacionPerfilPublico,
)
@rate_limit(settings.RL_PERFIL_PUBLICO)
async def informacion_perfil_publico(
    nombre_usuario: str,
    request: Request,
    db: AsyncSession = Depends(obtener_db),
    usuario_actual_id: int = Depends(auth.obtener_usuario_actual),
):
    """
    Permite ver la ficha publica reducida de otro usuario si este tiene el perfil visible.
    Calcula los puntos de ese usuario en tiempo real basándose en los metros acumulados.
    """
    # Obtener el usuario.
    usuario_objetivo = await user_service.obtener_perfil_publico(db, nombre_usuario)

    # Calcular puntos (1 KM = 1 Punto).
    puntos = calculos.calcular_puntos_nivel(usuario_objetivo.total_metros)

    # Devolver solo los datos públicos.
    return {
        "nombre_usuario": usuario_objetivo.nombre_usuario,
        "provincia": usuario_objetivo.provincia,
        "foto_perfil": file_service.construir_url_foto(
            usuario_objetivo.foto_perfil, request
        ),
        "foto_version": (
            int(usuario_objetivo.foto_fecha_actualizacion.timestamp())
            if usuario_objetivo.foto_fecha_actualizacion
            else 0
        ),
        "total_puntos": puntos,
    }


@router.post("/perfil/foto", response_model=schemas.RespuestaGenerica)
@rate_limit(settings.RL_PERFIL_FOTO)
async def foto_perfil(
    request: Request,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(obtener_db),
    usuario_actual_id: int = Depends(auth.obtener_usuario_actual),
    archivo: UploadFile = File(...),
):
    logger.info(
        "actualizacion_foto_perfil_iniciada",
        extra={
            "usuario_id": usuario_actual_id,
            "nombre_archivo": archivo.filename,
            "content_type": archivo.content_type,
            "storage_type": settings.STORAGE_TYPE,
        },
    )

    foto_antigua = None
    nueva_ruta_foto = None

    try:
        # 1) Validar imagen y recuperar los bytes ya leídos
        raw = await run_in_threadpool(file_service.validar_seguridad, archivo)

        # 2) Subir primero la nueva imagen (sin releer el archivo)
        nueva_ruta_foto = await run_in_threadpool(
            file_service.procesar_subida, archivo, usuario_actual_id, raw, None
        )

        # 3) Bloquear la fila solo en el momento de actualizar la BD
        usuario = await user_service.obtener_perfil(
            db, usuario_actual_id, for_update=True
        )

        foto_antigua = usuario.foto_perfil
        usuario.foto_perfil = nueva_ruta_foto
        usuario.foto_fecha_actualizacion = datetime.now(timezone.utc)

        await db.commit()

        logger.info(
            "foto_perfil_actualizada",
            extra={
                "usuario_id": usuario_actual_id,
                "storage_type": settings.STORAGE_TYPE,
                "tenia_foto_anterior": bool(foto_antigua),
            },
        )

    except HTTPException:
        logger.warning(
            "actualizacion_foto_perfil_error_controlado",
            extra={
                "usuario_id": usuario_actual_id,
                "nombre_archivo": archivo.filename,
                "content_type": archivo.content_type,
                "storage_type": settings.STORAGE_TYPE,
            },
            exc_info=True,
        )

        # En tests puede venir db=None; en producción normalmente será una sesión real
        if db is not None and hasattr(db, "rollback"):
            await db.rollback()

        # Si ya habíamos subido la nueva imagen y luego falla el flujo, la limpiamos
        if settings.STORAGE_TYPE != "cloudinary" and nueva_ruta_foto:
            await run_in_threadpool(
                file_service.borrar_foto, nueva_ruta_foto, usuario_actual_id
            )

        raise

    except Exception:
        logger.exception(
            "actualizacion_foto_perfil_error_no_controlado",
            extra={
                "usuario_id": usuario_actual_id,
                "nombre_archivo": archivo.filename,
                "content_type": archivo.content_type,
                "storage_type": settings.STORAGE_TYPE,
            },
        )

        if db is not None and hasattr(db, "rollback"):
            await db.rollback()

        if settings.STORAGE_TYPE != "cloudinary" and nueva_ruta_foto:
            await run_in_threadpool(
                file_service.borrar_foto, nueva_ruta_foto, usuario_actual_id
            )

        raise app_http_exception(
            status_code=500,
            mensaje="Error: No se ha podido actualizar la foto de perfil",
            error_code="PROFILE_PHOTO_UPDATE_FAILED",
        )

    # 4) Solo después del commit borramos la antigua
    if (
        settings.STORAGE_TYPE != "cloudinary"
        and foto_antigua
        and not str(foto_antigua).startswith("http")
    ):
        background_tasks.add_task(
            file_service.borrar_foto, foto_antigua, usuario_actual_id
        )

    return {"estatus": "success", "mensaje": "Foto actualizada correctamente"}


@router.patch("/perfil/actualizar", response_model=schemas.RespuestaGenerica)
@rate_limit(settings.RL_PERFIL_ACTUALIZAR)
async def actualizar_perfil(
    request: Request,
    datos: schemas.ActualizarPerfil,
    db: AsyncSession = Depends(obtener_db),
    usuario_actual_id: int = Depends(auth.obtener_usuario_actual),
):
    """Permite al usuario modificar su perfil."""
    usuario = await user_service.obtener_perfil(db, usuario_actual_id, for_update=True)
    return await user_service.actualizar_perfil_usuario(db, usuario, datos)


@router.delete("/perfil/borrar", response_model=schemas.RespuestaGenerica)
@rate_limit(settings.RL_PERFIL_BORRAR)
async def borrar_perfil(
    request: Request,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(obtener_db),
    usuario_actual_id: int = Depends(auth.obtener_usuario_actual),
):
    """
    Se elimina la cuenta (commit) y solo después se borra la foto
    (en background). Si el commit falla, NO se borra nada.
    """
    usuario = await user_service.obtener_perfil(db, usuario_actual_id)
    foto_perfil = usuario.foto_perfil  # guardar antes de borrar el usuario

    respuesta = await user_service.eliminar_cuenta(db, usuario)

    # Solo si commit OK (eliminar_cuenta hace commit), borramos la foto.
    # En background para no bloquear el endpoint con IO (disco / cloud).
    background_tasks.add_task(file_service.borrar_foto, foto_perfil, usuario_actual_id)

    return respuesta


@router.get("/perfil/buscar", response_model=schemas.RespuestaBusquedaUsuariosPaginada)
@rate_limit(settings.RL_PERFIL_BUSCAR)
async def buscar_perfil(
    request: Request,
    q: str = Query(
        ...,
        min_length=3,
        max_length=50,
        description="Término de búsqueda (min 3 caracteres)",
    ),
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=20, ge=1, le=100),
    db: AsyncSession = Depends(obtener_db),
    usuario_actual_id: int = Depends(auth.obtener_usuario_actual),
):
    """
    Busca usuarios por nombre (coincidencia parcial).
    Solo devuelve usuarios con perfil público y excluye al usuario autenticado.
    Devuelve resultados paginados con metadata.
    """
    resultados = await user_service.buscar_usuario(
        db, q, usuario_actual_id, skip, limit
    )

    lista_final = []
    for usuario in resultados["items"]:
        url_foto = file_service.construir_url_foto(usuario.foto_perfil, request)
        foto_version = (
            int(usuario.foto_fecha_actualizacion.timestamp())
            if usuario.foto_fecha_actualizacion
            else 0
        )
        lista_final.append(
            {
                "nombre_usuario": usuario.nombre_usuario,
                "foto_perfil": url_foto,
                "foto_version": foto_version,
            }
        )

    return {
        "items": lista_final,
        "total": resultados["total"],
        "skip": resultados["skip"],
        "limit": resultados["limit"],
        "has_more": resultados["has_more"],
    }


@router.post("/perfil/reporte", response_model=schemas.RespuestaGenerica)
@rate_limit(settings.RL_PERFIL_REPORTE)
async def reportar_perfil(
    request: Request,
    datos: schemas.ReportePerfilInapropiado,
    db: AsyncSession = Depends(obtener_db),
    usuario_actual_id: int = Depends(auth.obtener_usuario_actual),
):
    """
    Reporta un nombre o una foto de perfil inapropiados.
    Envía un correo a moderación con el reportante, el reportado y el motivo.
    """
    return await user_service.reportar_perfil_inapropiado(db, usuario_actual_id, datos)


@router.get("/ranking/obtener", response_model=List[schemas.ObtenerRanking])
@rate_limit(settings.RL_RANKING)
async def obtener_ranking(
    request: Request,
    provincia: Optional[ProvinciaEspaña] = None,
    db: AsyncSession = Depends(obtener_db),
    usuario_actual_id: int = Depends(auth.obtener_usuario_actual),
):
    """
    Devuelve el TOP 15 de usuarios con más puntos (KM recorridos).
    Permite filtrar por provincia de foma opcional.
    """
    # Obtener los datos
    ranking = await user_service.obtener_ranking(
        db, provincia.value if provincia else None
    )

    # Procesar la URL de las fotos para que la App pueda descargarlas.
    ranking_final = []
    for item in ranking:
        # Usar el servicio existente para crear la URL correcta.
        url_foto = file_service.construir_url_foto(item["foto_perfil"], request)
        ranking_final.append(
            {
                "nombre_usuario": item["nombre_usuario"],
                "foto_perfil": url_foto,
                "foto_version": item["foto_version"],
                "total_puntos": item["total_puntos"],
                "total_metros": item["total_metros"],
            }
        )

    return ranking_final
