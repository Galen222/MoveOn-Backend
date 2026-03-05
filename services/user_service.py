# services/user_service.py

"""
Servicio de Gestión de Usuarios.
Encapsula la lógica de negocio de registro y actualización de perfil.

Importante (Android Java): para que el backend reciba un null explícito
y lo pueda borrar, el cliente debe enviar los nulls en el JSON
(con Gson es new GsonBuilder().serializeNulls()), si no, el campo se omite
y el backend no puede distinguir “quiero borrarlo” de “no quiero tocarlo”.
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

    # Validación manual case-insensitive (porque unique=True es case-sensitive en algunos engines)
    existente = (await db.execute(
        select(database.Usuario).where(
            func.lower(database.Usuario.nombre_usuario) == nombre_usuario_key
        )
    )).scalar_one_or_none()

    if existente:
        raise HTTPException(
            status_code=400, detail="Error: El nombre de usuario ya está en uso")

    # Validación email duplicado
    existente_email = (await db.execute(
        select(database.Usuario).where(
            database.Usuario.email == email
        )
    )).scalar_one_or_none()

    if existente_email:
        raise HTTPException(
            status_code=400, detail="Error: El email ya está en uso")

    # Hash de contraseña (bcrypt) en threadpool para no bloquear el event loop
    password_hash = await run_in_threadpool(auth.encriptar_password, datos.password)

    # Guardar enums como string en BD (si viene None, guardar None)
    genero_val = datos.genero.value if datos.genero else None
    provincia_val = datos.provincia.value if datos.provincia else None

    nuevo_usuario = database.Usuario(
        nombre_usuario=nombre_usuario,
        email=email,
        password_encriptada=password_hash,
        nombre_real=datos.nombre_real.strip()
        if isinstance(datos.nombre_real, str) else datos.nombre_real,
        fecha_nacimiento=datos.fecha_nacimiento,
        genero=genero_val,
        altura=datos.altura,
        peso=datos.peso,
        provincia=provincia_val,
        perfil_visible=datos.perfil_visible,
        acepta_terminos=datos.acepta_terminos,
        fecha_eula=datos.fecha_aceptacion_terminos,
        version_terminos=datos.version_terminos
    )

    try:
        db.add(nuevo_usuario)
        await db.commit()
        await db.refresh(nuevo_usuario)
    except IntegrityError:
        await db.rollback()
        raise HTTPException(
            status_code=400,
            detail="Error: No se ha podido registrar el usuario. Revisa que el nombre/email no existan."
        )

    return {"estatus": "success", "mensaje": "Usuario registrado correctamente"}


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
    """Lógica para modificar el perfil de usuario (PATCH real).

    Reglas:
    - Si el campo NO viene en el JSON: no se toca en BD.
    - Si el campo viene con valor: se actualiza.
    - Si el campo viene explícitamente como null: se borra (se guarda NULL) SOLO si el campo es borrable.

    Nota importante (Pydantic v2):
    - Para distinguir entre "omitido" y "enviado como null", se usa:
        datos.model_dump(exclude_unset=True)
      Esto devuelve únicamente las claves presentes en la petición.
    """

    # Solo incluye campos presentes en el JSON (incluye explícitos null)
    payload = datos.model_dump(exclude_unset=True)

    # -------------------------
    # Campos opcionales BORRABLES (permiten null)
    # -------------------------

    if "nombre_real" in payload:
        # Permite borrar nombre_real enviando null
        usuario.nombre_real = payload["nombre_real"]

    if "genero" in payload:
        # Enum -> str o None
        g = payload["genero"]
        usuario.genero = g.value if g is not None else None

    if "altura" in payload:
        # int o None
        usuario.altura = payload["altura"]

    if "peso" in payload:
        # float o None
        usuario.peso = payload["peso"]

    if "provincia" in payload:
        # Enum -> str o None
        p = payload["provincia"]
        usuario.provincia = p.value if p is not None else None

    # -------------------------
    # Campos editables NO borrables (no aceptar null)
    # -------------------------

    if "email" in payload:
        if payload["email"] is None:
            raise HTTPException(status_code=400, detail="Error: El email no puede ser null")

        # Email siempre en minúsculas (aunque schemas ya lo baja, aquí blindamos)
        email = str(payload["email"]).strip().lower()

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

    if "password" in payload:
        if payload["password"] is None:
            raise HTTPException(status_code=400, detail="Error: La contraseña no puede ser null")

        usuario.password_encriptada = await run_in_threadpool(auth.encriptar_password, payload["password"])

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

    if "fecha_nacimiento" in payload:
        if payload["fecha_nacimiento"] is None:
            raise HTTPException(status_code=400, detail="Error: La fecha de nacimiento no puede ser null")
        usuario.fecha_nacimiento = payload["fecha_nacimiento"]

    if "perfil_visible" in payload:
        # En tu app Android es un toggle (true/false). No debería llegar null.
        if payload["perfil_visible"] is None:
            raise HTTPException(status_code=400, detail="Error: perfil_visible no puede ser null")
        usuario.perfil_visible = payload["perfil_visible"]

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

    if not termino or len(termino) < 3:
        raise HTTPException(
            status_code=400, detail="Error: La búsqueda requiere al menos 3 caracteres")

    usuarios = (await db.execute(
        select(database.Usuario)
        .where(
            database.Usuario.perfil_visible == True,
            database.Usuario.nombre_usuario.ilike(f"%{termino}%")
        )
        .limit(20)
    )).scalars().all()

    return usuarios


async def eliminar_cuenta(db: AsyncSession, usuario: database.Usuario):
    """Elimina permanentemente el registro de la base de datos."""
    await db.delete(usuario)
    await db.commit()
    return {"estatus": "success", "mensaje": "Cuenta eliminada correctamente"}


async def obtener_ranking(db: AsyncSession, provincia: Optional[str] = None):
    """Obtiene el Ranking de los usuarios con más kilometros recorridos."""
    query = select(
        database.Usuario.nombre_usuario,
        database.Usuario.foto_perfil,
        database.Usuario.total_metros
    ).where(
        database.Usuario.perfil_visible == True
    )

    if provincia:
        query = query.where(database.Usuario.provincia == provincia)

    query = query.order_by(desc(database.Usuario.total_metros)).limit(15)

    resultados = (await db.execute(query)).all()

    ranking = []
    for nombre_usuario, foto_perfil, total_metros in resultados:
        puntos = calculos.calcular_puntos_nivel(total_metros)
        ranking.append({
            "nombre_usuario": nombre_usuario,
            "foto_perfil": foto_perfil,
            "total_puntos": puntos
        })

    return ranking
