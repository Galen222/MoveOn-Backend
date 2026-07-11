"""Limpia de forma interactiva los datos creados por los seeders.

La limpieza distingue tres grupos independientes:

- ``seed_usuarios.py``: elimina sus actividades seed y las 30 cuentas demo
  creadas por ese script.
- ``seed_aportillo.py``: elimina únicamente las actividades cuyo
  ``client_local_id`` pertenece a ese seed.
- ``seed_galen.py``: elimina únicamente las actividades cuyo
  ``client_local_id`` pertenece a ese seed.
- Cuenta ``Galen``: puede eliminarse de forma independiente, junto con todos sus
  datos asociados, conservando siempre la cuenta ``GalenG``.

Los usuarios demo se identifican únicamente por los pares exactos de
``nombre_usuario`` y ``email`` definidos por ``seed_usuarios.py``. La eliminación
de la cuenta ``Galen`` es una opción explícita e independiente y usa una
coincidencia exacta del nombre, por lo que nunca afecta a ``GalenG``.
"""

from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path
import asyncio
import sys

# Añadir la raíz del proyecto ANTES de importar módulos internos.
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from sqlalchemy import func, or_, select  # noqa: E402
from sqlalchemy.ext.asyncio import AsyncSession  # noqa: E402

import database  # noqa: E402
from scripts.seed_catalogo import (  # noqa: E402
    APORTILLO_SEED_VERSION,
    GALEN_SEED_VERSION,
    USUARIOS_SEED_USERNAMES,
    USUARIOS_SEED_VERSION,
)


PREFIJOS_SEED = {
    "usuarios": (f"{USUARIOS_SEED_VERSION}-",),
    "aportillo": (f"{APORTILLO_SEED_VERSION}-",),
    "galen": (f"{GALEN_SEED_VERSION}-",),
}

@dataclass(frozen=True)
class SeleccionLimpieza:
    """Indica qué grupos ha elegido limpiar el operador."""

    usuarios: bool = False
    aportillo: bool = False
    galen: bool = False
    cuenta_galen: bool = False

    @property
    def hay_algo(self) -> bool:
        """Devuelve ``True`` cuando se ha seleccionado al menos una opción."""
        return (
            self.usuarios
            or self.aportillo
            or self.galen
            or self.cuenta_galen
        )

    @property
    def grupos(self) -> tuple[str, ...]:
        """Devuelve los nombres internos de los grupos seleccionados."""
        seleccionados: list[str] = []
        if self.usuarios:
            seleccionados.append("usuarios")
        if self.aportillo:
            seleccionados.append("aportillo")
        if self.galen:
            seleccionados.append("galen")
        return tuple(seleccionados)


@dataclass
class TotalesEliminados:
    """Acumulados que deben restarse a un usuario por actividades borradas."""

    actividades: int = 0
    metros: int = 0
    calorias: int = 0
    duracion: int = 0

    def agregar(self, actividad: database.Actividad) -> None:
        """Añade las métricas de una actividad al acumulado."""
        self.actividades += 1
        self.metros += int(actividad.distancia or 0)
        self.calorias += int(actividad.calorias_quemadas or 0)
        self.duracion += int(actividad.duracion_total or 0)


@dataclass(frozen=True)
class ResultadoLimpieza:
    """Resumen final de la operación de limpieza."""

    actividades_borradas: int
    usuarios_borrados: int
    usuarios_no_coincidentes: int


def normalizar_respuesta(valor: str) -> str:
    """Normaliza una respuesta interactiva para compararla de forma segura."""
    return valor.strip().casefold()


def respuesta_afirmativa(valor: str) -> bool:
    """Acepta las variantes habituales de una respuesta afirmativa."""
    return normalizar_respuesta(valor) in {"s", "si", "sí", "y", "yes"}


def preguntar_si_no(mensaje: str) -> bool:
    """Pregunta S/N; una entrada vacía o desconocida se interpreta como no."""
    return respuesta_afirmativa(input(f"{mensaje} [s/N]: "))


def solicitar_seleccion() -> SeleccionLimpieza:
    """Pregunta de forma independiente qué grupo de datos seed se desea borrar."""
    print("=== Limpieza de datos seed ===")
    print("Responde S o N en cada opción.")
    print()

    usuarios = preguntar_si_no(
        "¿Borrar los 30 usuarios demo de seed_usuarios.py y todos sus datos?"
    )
    aportillo = preguntar_si_no(
        "¿Borrar solo las actividades creadas por seed_aportillo.py?"
    )
    galen = preguntar_si_no(
        "¿Borrar solo las actividades seed de Galen/GalenG?"
    )
    cuenta_galen = preguntar_si_no(
        "¿Borrar la cuenta Galen y todos sus datos, conservando GalenG?"
    )

    return SeleccionLimpieza(
        usuarios=usuarios,
        aportillo=aportillo,
        galen=galen,
        cuenta_galen=cuenta_galen,
    )


def identidades_usuarios_seed() -> tuple[tuple[str, str], ...]:
    """Devuelve pares exactos ``(username, email)`` de las cuentas demo."""
    return tuple(
        (username.casefold(), f"{username}@prueba.com".casefold())
        for username in USUARIOS_SEED_USERNAMES
    )


def es_usuario_seed_eliminable(usuario: database.Usuario) -> bool:
    """Comprueba que una cuenta coincide exactamente con una identidad demo.

    La coincidencia exige simultáneamente el username y el email generados por
    ``seed_usuarios.py``. No se aplican listas artificiales de protección: una
    cuenta ajena al catálogo demo no puede coincidir con este predicado.
    """
    username = str(usuario.nombre_usuario or "").strip().casefold()
    email = str(usuario.email or "").strip().casefold()

    return (username, email) in frozenset(identidades_usuarios_seed())




def es_cuenta_galen_objetivo(usuario: database.Usuario) -> bool:
    """Devuelve ``True`` solo para la cuenta cuyo username es exactamente Galen.

    La comparación no distingue mayúsculas/minúsculas y no consulta el método
    de autenticación. Por tanto, funciona igual para contraseña, Google o ambos,
    y nunca confunde ``Galen`` con ``GalenG``.
    """
    username = str(usuario.nombre_usuario or "").strip().casefold()
    return username == "galen"


async def obtener_cuenta_galen(
    db: AsyncSession,
) -> database.Usuario | None:
    """Obtiene exclusivamente la cuenta Galen mediante coincidencia exacta."""
    result = await db.execute(
        select(database.Usuario).where(
            func.lower(database.Usuario.nombre_usuario) == "galen"
        )
    )
    usuario = result.scalar_one_or_none()
    if usuario is not None and not es_cuenta_galen_objetivo(usuario):
        raise RuntimeError("La consulta de Galen devolvió una cuenta inesperada")
    return usuario


async def contar_actividades_usuario(
    db: AsyncSession,
    usuario_id: int,
) -> int:
    """Cuenta las actividades que desaparecerán por CASCADE al borrar la cuenta."""
    result = await db.execute(
        select(func.count())
        .select_from(database.Actividad)
        .where(database.Actividad.usuario_id == usuario_id)
    )
    return int(result.scalar_one())

def prefijos_seleccionados(seleccion: SeleccionLimpieza) -> tuple[str, ...]:
    """Devuelve únicamente los prefijos correspondientes a la selección."""
    prefijos: list[str] = []
    for grupo in seleccion.grupos:
        prefijos.extend(PREFIJOS_SEED[grupo])
    return tuple(prefijos)


def construir_filtro_actividades(prefijos: tuple[str, ...]):
    """Construye el filtro que limita el borrado a ``client_local_id`` seed."""
    if not prefijos:
        raise ValueError("Debe indicarse al menos un prefijo seed")

    return or_(
        *(
            database.Actividad.client_local_id.like(f"{prefijo}%")
            for prefijo in prefijos
        )
    )


def detectar_grupo(client_local_id: str | None) -> str:
    """Identifica el grupo seed a partir de un ``client_local_id``."""
    if not client_local_id:
        return "sin-client-local-id"

    for grupo, prefijos in PREFIJOS_SEED.items():
        if any(client_local_id.startswith(prefijo) for prefijo in prefijos):
            return grupo

    return "otro"


async def obtener_actividades_seed(
    db: AsyncSession,
    prefijos: tuple[str, ...],
) -> list[database.Actividad]:
    """Carga solo las actividades de los prefijos seed seleccionados."""
    result = await db.execute(
        select(database.Actividad).where(construir_filtro_actividades(prefijos))
    )
    return list(result.scalars().all())


async def obtener_usuarios_seed(
    db: AsyncSession,
) -> tuple[list[database.Usuario], int]:
    """Carga las cuentas demo exactas y cuenta candidatos no coincidentes."""
    identidades = identidades_usuarios_seed()
    emails = tuple(email for _username, email in identidades)

    result = await db.execute(
        select(database.Usuario).where(func.lower(database.Usuario.email).in_(emails))
    )
    candidatos = list(result.scalars().all())

    eliminables: list[database.Usuario] = []
    omitidos = 0
    for usuario in candidatos:
        if es_usuario_seed_eliminable(usuario):
            eliminables.append(usuario)
        else:
            omitidos += 1

    return eliminables, omitidos


async def ajustar_acumulados_usuarios(
    db: AsyncSession,
    actividades: list[database.Actividad],
    usuarios_que_se_borraran: set[int],
) -> None:
    """Resta de cada perfil las métricas de las actividades seed eliminadas."""
    acumulados: dict[int, TotalesEliminados] = defaultdict(TotalesEliminados)
    for actividad in actividades:
        usuario_id = int(actividad.usuario_id)
        if usuario_id in usuarios_que_se_borraran:
            continue
        acumulados[usuario_id].agregar(actividad)

    if not acumulados:
        return

    result = await db.execute(
        select(database.Usuario)
        .where(database.Usuario.id.in_(tuple(acumulados)))
        .with_for_update()
    )
    usuarios = list(result.scalars().all())

    for usuario in usuarios:
        eliminado = acumulados[int(usuario.id)]
        usuario.total_metros = max(0, int(usuario.total_metros or 0) - eliminado.metros)
        usuario.total_calorias = max(
            0,
            int(usuario.total_calorias or 0) - eliminado.calorias,
        )
        usuario.total_duracion_segundos = max(
            0,
            int(usuario.total_duracion_segundos or 0) - eliminado.duracion,
        )
        usuario.total_actividades = max(
            0,
            int(usuario.total_actividades or 0) - eliminado.actividades,
        )


async def ejecutar_limpieza(
    seleccion: SeleccionLimpieza,
) -> ResultadoLimpieza:
    """Ejecuta en una única transacción la limpieza seleccionada."""
    if not seleccion.hay_algo:
        return ResultadoLimpieza(0, 0, 0)

    await database.init_db()
    if database.AsyncSessionLocal is None:
        raise RuntimeError("No se pudo inicializar AsyncSessionLocal")

    async with database.AsyncSessionLocal() as db:
        usuarios: list[database.Usuario] = []
        omitidos = 0
        if seleccion.usuarios:
            usuarios, omitidos = await obtener_usuarios_seed(db)

        cuenta_galen: database.Usuario | None = None
        cuenta_galen_id: int | None = None
        cuenta_galen_foto: str | None = None
        actividades_cuenta_galen = 0
        if seleccion.cuenta_galen:
            cuenta_galen = await obtener_cuenta_galen(db)
            if cuenta_galen is not None:
                cuenta_galen_id = int(cuenta_galen.id)
                cuenta_galen_foto = cuenta_galen.foto_perfil
                actividades_cuenta_galen = await contar_actividades_usuario(
                    db,
                    cuenta_galen_id,
                )
                usuarios.append(cuenta_galen)

        usuarios_que_se_borraran = {int(usuario.id) for usuario in usuarios}
        prefijos = prefijos_seleccionados(seleccion)
        actividades = (
            await obtener_actividades_seed(db, prefijos)
            if prefijos
            else []
        )

        resumen_actividades = Counter(
            detectar_grupo(actividad.client_local_id) for actividad in actividades
        )

        print()
        print("=== Datos encontrados ===")
        for grupo in seleccion.grupos:
            print(f"- Actividades {grupo}: {resumen_actividades.get(grupo, 0)}")
        if seleccion.usuarios:
            usuarios_demo_encontrados = len(usuarios) - (1 if cuenta_galen else 0)
            print(f"- Usuarios demo exactos: {usuarios_demo_encontrados}")
            print(f"- Candidatos con email demo pero identidad no exacta: {omitidos}")
            print("- La limpieza de usuarios demo no incluye Galen ni GalenG.")
        if seleccion.cuenta_galen:
            if cuenta_galen is None:
                print("- Cuenta Galen: no encontrada")
            else:
                print("- Cuenta Galen: 1")
                print(
                    f"- Actividades totales de Galen que se borrarán por CASCADE: "
                    f"{actividades_cuenta_galen}"
                )
                print("- Cuenta GalenG: se conservará")

        if not actividades and not usuarios:
            print("No hay datos seleccionados que borrar.")
            return ResultadoLimpieza(0, 0, omitidos)

        if not preguntar_si_no("¿Confirmas el borrado mostrado arriba?"):
            print("Operación cancelada. No se ha borrado nada.")
            return ResultadoLimpieza(0, 0, omitidos)

        try:
            await ajustar_acumulados_usuarios(
                db,
                actividades,
                usuarios_que_se_borraran,
            )

            for actividad in actividades:
                await db.delete(actividad)

            for usuario in usuarios:
                await db.delete(usuario)

            await db.commit()
        except Exception:
            await db.rollback()
            raise

        if cuenta_galen_id is not None:
            # Igual que el endpoint normal de borrado de perfil: tras confirmar
            # el commit, elimina la foto local o de Cloudinary en modo best-effort.
            from services import file_service

            file_service.borrar_foto(cuenta_galen_foto, cuenta_galen_id)

        print()
        print("=== Limpieza finalizada ===")
        usuarios_demo_borrados = len(usuarios) - (1 if cuenta_galen else 0)
        print(f"Actividades seed borradas directamente: {len(actividades)}")
        print(f"Usuarios demo borrados: {usuarios_demo_borrados}")
        if seleccion.cuenta_galen:
            print(f"Cuenta Galen borrada: {1 if cuenta_galen else 0}")
        if omitidos:
            print(f"Candidatos no coincidentes omitidos: {omitidos}")
        if seleccion.cuenta_galen and cuenta_galen is not None:
            print("Cuenta Galen y todos sus datos asociados eliminados.")
            print("Cuenta GalenG y todos sus datos conservados.")
        else:
            print("Actividades no seed de Galen/GalenG conservadas.")
            print("Cuentas Galen/GalenG conservadas.")

        return ResultadoLimpieza(
            actividades_borradas=len(actividades),
            usuarios_borrados=len(usuarios),
            usuarios_no_coincidentes=omitidos,
        )


async def main() -> None:
    """Solicita la selección y ejecuta la limpieza elegida."""
    seleccion = solicitar_seleccion()
    if not seleccion.hay_algo:
        print("No has seleccionado ninguna limpieza. No se ha borrado nada.")
        return

    await ejecutar_limpieza(seleccion)


if __name__ == "__main__":
    asyncio.run(main())
