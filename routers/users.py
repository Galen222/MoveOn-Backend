# routers/users.py

"""
Endpoints de Gestión de Perfil de Usuario.
Define las rutas para el registro de nuevos usuarios y la gestión
posterior del perfil (consulta, actualización, foto y borrado).
"""
from fastapi import APIRouter, Depends, File, UploadFile, Request, Query, BackgroundTasks, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
import os
import auth
import schemas
from typing import List, Optional
from services import user_service, file_service
from database import obtener_db
from schemas import ProvinciaEspaña
from utils import calculos
from starlette.concurrency import run_in_threadpool
from config import settings
from ip_rate_limit import rate_limit

# Inyectamos la dependencia a nivel de Router para todos los endpoints de este archivo
router = APIRouter(
    tags=["Usuarios"],
    dependencies=[Depends(auth.verificar_sesion_aplicacion)]
)


@router.post("/registro", response_model=schemas.RespuestaRegistro)
@rate_limit(settings.RL_REGISTRO)
async def registro(
    request: Request,
    datos: schemas.Registro,
    db: AsyncSession = Depends(obtener_db)
):
    """Registro de nuevo usuario con validación de duplicados."""
    return await user_service.registrar_nuevo_usuario(db, datos)


@router.get("/perfil/informacion", response_model=schemas.RespuestaInformacionPerfil)
@rate_limit(settings.RL_PERFIL_INFO)
async def informacion_perfil(
    request: Request,
    db: AsyncSession = Depends(obtener_db),
    usuario_actual: str = Depends(auth.obtener_usuario_actual)
):
    """Obtiene los datos del perfil."""
    usuario = await user_service.obtener_perfil(db, usuario_actual)

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
        "perfil_visible": usuario.perfil_visible,
        "total_puntos": puntos
    }


@router.get("/perfil/informacion/{nombre_usuario}", response_model=schemas.InformacionPerfilPublico)
@rate_limit(settings.RL_PERFIL_PUBLICO)
async def informacion_perfil_publico(
    nombre_usuario: str,
    request: Request,
    db: AsyncSession = Depends(obtener_db),
    usuario_actual: str = Depends(auth.obtener_usuario_actual)
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
        "foto_perfil": file_service.construir_url_foto(usuario_objetivo.foto_perfil, request),
        "total_puntos": puntos
    }


@router.post("/perfil/foto", response_model=schemas.RespuestaGenerica)
@rate_limit(settings.RL_PERFIL_FOTO)
async def foto_perfil(
    request: Request,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(obtener_db),
    usuario_actual: str = Depends(auth.obtener_usuario_actual),
    archivo: UploadFile = File(...)
):
    # Validaciones de seguridad de la imagen (se ejecutan en threadpool porque Pillow es CPU/IO)
    await run_in_threadpool(file_service.validar_seguridad, archivo)

    # Obtenemos el usuario para saber qué foto tiene actualmente
    usuario = await user_service.obtener_perfil(db, usuario_actual)

    foto_antigua = usuario.foto_perfil

    # Subimos la nueva imagen.
    # Importante: NO borramos aquí la foto antigua (eso se hace tras commit).
    nueva_ruta_foto = await run_in_threadpool(
        file_service.procesar_subida,
        archivo,
        usuario_actual,
        None  # <- no pasar foto anterior para evitar borrados prematuros
    )

    # Si la subida fue exitosa, se actualiza la base de datos con la nueva ruta
    usuario.foto_perfil = nueva_ruta_foto

    # Commit protegido: si falla, hacemos rollback y limpiamos la nueva foto (evitar huérfanas)
    try:
        await db.commit()
    except Exception:
        await db.rollback()

        # Si el storage es local, podemos borrar la imagen recién subida.
        # En Cloudinary, el flujo actual hace overwrite por public_id, así que "borrar la nueva"
        # equivaldría a borrar la imagen del usuario (y no podemos restaurar la anterior sin más).
        if settings.STORAGE_TYPE != "cloudinary" and nueva_ruta_foto:
            await run_in_threadpool(file_service.borrar_foto, nueva_ruta_foto, usuario_actual)

        raise HTTPException(status_code=500, detail="Error: No se ha podido actualizar la foto de perfil")

    # Solo si el commit fue exitoso, borramos la antigua (evita desync).
    # Solo aplica a almacenamiento local (en Cloudinary se usa overwrite).
    if (
        settings.STORAGE_TYPE != "cloudinary"
        and foto_antigua
        and not str(foto_antigua).startswith("http")
        and (os.path.basename(str(foto_antigua)) != file_service.DEFAULT_AVATAR_SENTINEL)
    ):
        background_tasks.add_task(file_service.borrar_foto, foto_antigua, usuario_actual)

    return {"estatus": "success", "mensaje": "Foto actualizada correctamente"}


@router.patch("/perfil/actualizar", response_model=schemas.RespuestaGenerica)
@rate_limit(settings.RL_PERFIL_ACTUALIZAR)
async def actualizar_perfil(
    request: Request,
    datos: schemas.ActualizarPerfil,
    db: AsyncSession = Depends(obtener_db),
    usuario_actual: str = Depends(auth.obtener_usuario_actual)
):
    """Permite al usuario modificar su perfil."""
    usuario = await user_service.obtener_perfil(db, usuario_actual, for_update=True)
    return await user_service.actualizar_perfil_usuario(db, usuario, datos)


@router.delete("/perfil/borrar", response_model=schemas.RespuestaGenerica)
@rate_limit(settings.RL_PERFIL_BORRAR)
async def borrar_perfil(
    request: Request,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(obtener_db),
    usuario_actual: str = Depends(auth.obtener_usuario_actual)
):
    """
    Se elimina la cuenta (commit) y solo después se borra la foto
    (en background). Si el commit falla, NO se borra nada.
    """
    usuario = await user_service.obtener_perfil(db, usuario_actual)
    foto_perfil = usuario.foto_perfil  # guardar antes de borrar el usuario

    respuesta = await user_service.eliminar_cuenta(db, usuario)

    # Solo si commit OK (eliminar_cuenta hace commit), borramos la foto.
    # En background para no bloquear el endpoint con IO (disco / cloud).
    background_tasks.add_task(file_service.borrar_foto, foto_perfil, usuario_actual)

    return respuesta


@router.get("/perfil/buscar", response_model=List[schemas.BusquedaUsuario])
@rate_limit(settings.RL_PERFIL_BUSCAR)
async def buscar_perfil(
    request: Request,
    # 'q' es el parámetro de la URL: /perfil/buscar?q=pepe
    # min_length=3 valida que escriban al menos 3 letras antes de molestar a la base de datos
    q: str = Query(..., min_length=3, max_length=50, description="Término de búsqueda (min 3 caracteres)"),
    db: AsyncSession = Depends(obtener_db),
    usuario_actual: str = Depends(auth.obtener_usuario_actual)
):
    """
    Busca usuarios por nombre (coincidencia parcial).
    Solo devuelve usuarios con perfil público.
    """
    resultados = await user_service.buscar_usuario(db, q)

    # Procesamos para añadir la URL completa de la foto
    lista_final = []
    for usuario in resultados:
        url_foto = file_service.construir_url_foto(usuario.foto_perfil, request)
        lista_final.append({
            "nombre_usuario": usuario.nombre_usuario,
            "foto_perfil": url_foto
        })

    return lista_final


@router.get("/ranking/obtener", response_model=List[schemas.ObtenerRanking])
@rate_limit(settings.RL_RANKING)
async def obtener_ranking(
    request: Request,
    provincia: Optional[ProvinciaEspaña] = None,
    db: AsyncSession = Depends(obtener_db),
    usuario_actual: str = Depends(auth.obtener_usuario_actual)
):
    """
    Devuelve el TOP 15 de usuarios con más puntos (KM recorridos).
    Permite filtrar por provincia de foma opcional.
    """
    # Obtener los datos
    ranking = await user_service.obtener_ranking(db, provincia.value if provincia else None)

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