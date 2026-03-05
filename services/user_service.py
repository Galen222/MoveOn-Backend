# services/user_service.py

"""
Servicio de Gestión de Usuarios.
Encapsula la lógica de negocio de registro y actualización de perfil.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from fastapi import HTTPException
from sqlalchemy import desc, select, update, func
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.concurrency import run_in_threadpool

import auth
import database
import schemas
from utils import calculos

async def registrar_nuevo_usuario(db: AsyncSession, datos: schemas.Registro):
    """Registro de nuevo usuario con validación de duplicados."""
    # IMPORTANTE:
    # - nombre_usuario se guarda tal cual (case-preserving)
    # - pero no se permiten duplicados ignorando mayúsculas/minúsculas
    nombre_usuario = datos.nombre_usuario.strip()
    if not nombre_usuario:
        raise HTTPException(
            status_code=400, detail="Error: El nombre de usuario no puede estar vacío")

    # Email: estándar práctico -> guardar y comparar siempre en minúsculas
    email = str(datos.email).strip().lower()

    nombre_usuario_key = nombre_usuario.lower()

    # Buscar si existe ignorando mayúsculas/minúsculas (username) y en minúsculas (email)
    usuario_existente = (await db.execute(
        select(database.Usuario).where(
            (func.lower(database.Usuario.nombre_usuario) == nombre_usuario_key) |
            (database.Usuario.email == email)
        )
    )).scalar_one_or_none()

    if usuario_existente:
        # Comprobación específica para el mensaje de error
        if usuario_existente.nombre_usuario.lower() == nombre_usuario_key:
            raise HTTPException(
                status_code=400, detail="Error: El nombre de usuario ya está en uso")
        raise HTTPException(
            status_code=400, detail="Error: El email ya está en uso")

    password_hash = await run_in_threadpool(auth.encriptar_password, datos.password)

    nuevo_usuario = database.Usuario(
        nombre_usuario=nombre_usuario,
        nombre_real=datos.nombre_real,
        email=email,
        password_encriptada=password_hash,
        fecha_nacimiento=datos.fecha_nacimiento,
        genero=datos.genero.value if datos.genero else None,
        altura=datos.altura,
        peso=datos.peso,
        provincia=datos.provincia.value if datos.provincia else None,
        perfil_visible=datos.perfil_visible,
        acepta_terminos=datos.acepta_terminos,
        fecha_eula=datos.fecha_aceptacion_terminos,
        version_terminos=datos.version_terminos,

    )

    db.add(nuevo_usuario)

    try:
        await db.commit()
    except IntegrityError:
        # Si hay una carrera (dos registros a la vez), la DB puede disparar IntegrityError (sobre todo por email).
        # Para username case-insensitive, lo correcto en producción es un índice único:
        #   CREATE UNIQUE INDEX uq_usuarios_nombre_usuario_lower ON usuarios (lower(nombre_usuario));
        await db.rollback()

        conflicto = (await db.execute(
            select(database.Usuario).where(
                (func.lower(database.Usuario.nombre_usuario) == nombre_usuario_key) |
                (database.Usuario.email == email)
            )
        )).scalar_one_or_none()

        if conflicto and conflicto.nombre_usuario.lower() == nombre_usuario_key:
            raise HTTPException(
                status_code=400, detail="Error: El nombre de usuario ya está en uso")
        raise HTTPException(
            status_code=400, detail="Error: El email ya está en uso")

    return {
        "estatus": "success",
        "mensaje": "Usuario registrado correctamente",
        "nombre_usuario": nuevo_usuario.nombre_usuario
    }

async def obtener_perfil(db: AsyncSession, usuario_actual: str):
    """Busca al usuario en la base de datos usando el 'sub' extraído automáticamente del token."""    
    usuario = (await db.execute(
        select(database.Usuario).where(
            database.Usuario.nombre_usuario == usuario_actual)
    )).scalar_one_or_none()

    if not usuario:
        raise HTTPException(
            status_code=404, detail="Error: Perfil de usuario no encontrado")
    return usuario

async def actualizar_perfil_usuario(db: AsyncSession, usuario: database.Usuario, datos: schemas.ActualizarPerfil):
    """Lógica para modificar el perfil de usuario."""    
    if datos.nombre_real is not None:
        usuario.nombre_real = datos.nombre_real

    if datos.email:
        # Email siempre en minúsculas (aunque schemas ya lo baja, aquí blindamos)
        email = str(datos.email).strip().lower()

        duplicado = (await db.execute(
            select(database.Usuario).where(
                database.Usuario.email == email,
                database.Usuario.id != usuario.id
            )
        )).scalar_one_or_none()

        if duplicado:
            raise HTTPException(
                status_code=400, detail="Error: El email ya está en uso")

        usuario.email = email

    if datos.password:
        usuario.password_encriptada = await run_in_threadpool(auth.encriptar_password, datos.password)

        # Seguridad extra: revocar refresh tokens activos del usuario al cambiar contraseña
        ahora = datetime.now(timezone.utc)
        await db.execute(
            update(database.SesionRefresh)
            .where(
                database.SesionRefresh.usuario_id == usuario.id,
                database.SesionRefresh.revocada_en.is_(None)
            )
            .values(revocada_en=ahora)
        )

    if datos.fecha_nacimiento:
        usuario.fecha_nacimiento = datos.fecha_nacimiento

    if datos.genero is not None:
        usuario.genero = datos.genero.value if datos.genero else None

    if datos.altura is not None:
        usuario.altura = datos.altura

    if datos.peso is not None:
        usuario.peso = datos.peso

    if datos.provincia is not None:
        usuario.provincia = datos.provincia.value if datos.provincia else None

    if datos.perfil_visible is not None:
        usuario.perfil_visible = datos.perfil_visible

    await db.commit()
    return {"estatus": "success", "mensaje": "Perfil de usuario actualizado correctamente"}

async def obtener_perfil_publico(db: AsyncSession, nombre_objetivo: str):
    """
    Busca un usuario por nombre para mostrar su ficha pública.
    Solo devuelve datos si el usuario existe y tiene perfil_visible=True.
    """
    # Case-insensitive lookup: permite /perfil/publico/GaLeN aunque el guardado sea "Galen"
    nombre_key = nombre_objetivo.strip().lower()

    usuario = (await db.execute(
        select(database.Usuario).where(func.lower(
            database.Usuario.nombre_usuario) == nombre_key)
    )).scalar_one_or_none()

    if not usuario:
        raise HTTPException(
            status_code=404, detail="Error: Usuario no encontrado")

    # LÓGICA DE PRIVACIDAD
    if not usuario.perfil_visible:
        raise HTTPException(
            status_code=403, detail="Error: Este perfil es privado")

    return usuario

async def buscar_usuario(db: AsyncSession, termino_busqueda: str):
    """
    Busca usuarios cuyo nombre_usuario contenga el término.
    Filtros:
    1. Coincidencia parcial (ilike)
    2. Perfil visible (Privacidad)
    3. Límite de 20 (Rendimiento)
    """
    # Limpiamos espacios
    termino = termino_busqueda.strip()

    # Si la búsqueda está vacía, devolvemos lista vacía para no traer toda la DB
    if not termino:
        return []

    resultados = (await db.execute(
        select(database.Usuario).where(
            # ILIKE: Busca coincidencias sin importar mayúsculas/minúsculas
            # %termino% significa: contiene el texto en cualquier parte
            database.Usuario.nombre_usuario.ilike(f"%{termino}%"),
            # PRIVACIDAD: Solo usuarios visibles
            database.Usuario.perfil_visible == True
        ).limit(20)
    )).scalars().all()

    return resultados

async def eliminar_cuenta(db: AsyncSession, usuario: database.Usuario):
    """Elimina permanentemente el registro de la base de datos."""    
    await db.delete(usuario)
    await db.commit()
    return {"estatus": "success", "mensaje": "Tu cuenta ha sido eliminada permanentemente"}

async def obtener_ranking(db: AsyncSession, provincia: Optional[str] = None):
    """
    Obtiene el Ranking de los usuarios con más kilometros recorridos.
    """    
    # Query sobre la tabla Usuarios
    stmt = select(
        database.Usuario.nombre_usuario,
        database.Usuario.foto_perfil,
        database.Usuario.total_metros
    )

    # Filtro opcional
    if provincia:
        stmt = stmt.where(database.Usuario.provincia == provincia)

    # Ordenar por el campo pre-calculado.
    # Filtrar que total_metros > 0 para no llenar el ranking de usuarios inactivos.
    # Filtrar que solo los usuarios con perfil publico aparezcan en el ranking.
    resultados = (await db.execute(
        stmt.where(
            database.Usuario.total_metros > 0,
            database.Usuario.perfil_visible == True
        ).order_by(desc(database.Usuario.total_metros)).limit(15)
    )).all()

    # Convertir Metros a Puntos
    ranking_procesado = []
    for nombre, foto, total_metros in resultados:
        # 1 KM = 1 Punto (División entera).
        puntos = calculos.calcular_puntos_nivel(total_metros)

        ranking_procesado.append({
            "nombre_usuario": nombre,
            "foto_perfil": foto,
            "total_puntos": puntos
        })

    return ranking_procesado
