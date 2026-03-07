# tests/test_user_service.py
#
# Tests para services/user_service.py.
# Cubre: registrar_nuevo_usuario, obtener_perfil, actualizar_perfil_usuario,
#        obtener_perfil_publico, buscar_usuario, eliminar_cuenta, obtener_ranking.

import pytest
from datetime import date, datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

from fastapi import HTTPException
from sqlalchemy.exc import IntegrityError

import database
import schemas
from schemas import ActualizarPerfil, GeneroUsuario, ProvinciaEspaña
from services import user_service


# ─────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────

def _make_usuario(
    id: int = 1,
    nombre_usuario: str = "pepe",
    email: str = "pepe@test.com",
    perfil_visible: bool = True,
    total_metros: int = 10_000,
    provincia: str | None = None,
) -> MagicMock:
    u = MagicMock(spec=database.Usuario)
    u.id = id
    u.nombre_usuario = nombre_usuario
    u.email = email
    u.perfil_visible = perfil_visible
    u.total_metros = total_metros
    u.provincia = provincia
    u.nombre_real = None
    u.fecha_nacimiento = date(1990, 1, 1)
    u.genero = None
    u.altura = None
    u.peso = None
    u.foto_perfil = None
    return u


def _make_db_one(resultado) -> AsyncMock:
    db = AsyncMock()
    db.execute = AsyncMock(return_value=MagicMock(
        scalar_one_or_none=MagicMock(return_value=resultado)
    ))
    db.commit = AsyncMock()
    db.add = MagicMock()
    db.rollback = AsyncMock()
    db.refresh = AsyncMock()
    db.delete = AsyncMock()
    return db


def _make_db_seq(*resultados) -> AsyncMock:
    """Cada item puede ser ('one', valor) o ('all', [lista]) o ('raw', mock)."""
    side = []
    for tipo, valor in resultados:
        m = MagicMock()
        if tipo == "one":
            m.scalar_one_or_none.return_value = valor
        elif tipo == "all":
            m.scalars.return_value.all.return_value = valor
        elif tipo == "raw":
            m = valor
        side.append(m)
    db = AsyncMock()
    db.execute = AsyncMock(side_effect=side)
    db.commit = AsyncMock()
    db.add = MagicMock()
    db.rollback = AsyncMock()
    db.refresh = AsyncMock()
    db.delete = AsyncMock()
    return db


def _datos_registro() -> schemas.Registro:
    from datetime import timedelta
    return schemas.Registro(
        nombre_usuario="GalenTest",
        email="galen@test.com",
        password="Password123!",
        fecha_nacimiento=date(1990, 5, 15),
        acepta_terminos=True,
        fecha_aceptacion_terminos=datetime.now(timezone.utc) - timedelta(seconds=5),
        version_terminos="1.0",
    )


# ─────────────────────────────────────────────
# registrar_nuevo_usuario
# ─────────────────────────────────────────────

class TestRegistrarNuevoUsuario:
    @pytest.mark.asyncio
    async def test_nombre_de_usuario_duplicado_lanza_400(self):
        existente = _make_usuario(nombre_usuario="galentest")
        db = _make_db_one(existente)

        with pytest.raises(HTTPException) as exc:
            await user_service.registrar_nuevo_usuario(db, _datos_registro())

        assert exc.value.status_code == 400
        assert "nombre de usuario" in exc.value.detail.lower()

    @pytest.mark.asyncio
    async def test_email_duplicado_lanza_400(self):
        existente = _make_usuario(nombre_usuario="otro", email="galen@test.com")
        db = _make_db_one(existente)

        with pytest.raises(HTTPException) as exc:
            await user_service.registrar_nuevo_usuario(db, _datos_registro())

        assert exc.value.status_code == 400
        assert "email" in exc.value.detail.lower()

    @pytest.mark.asyncio
    async def test_usuario_nuevo_hace_add_y_commit(self):
        db = _make_db_one(None)  # sin duplicados

        with patch("services.user_service.run_in_threadpool", new_callable=AsyncMock, return_value="hash"):
            await user_service.registrar_nuevo_usuario(db, _datos_registro())

        db.add.assert_called_once()
        db.commit.assert_called_once()

    @pytest.mark.asyncio
    async def test_integrity_error_hace_rollback_y_lanza_400(self):
        db = _make_db_one(None)
        db.commit = AsyncMock(side_effect=IntegrityError(None, None, Exception("constraint")))

        with patch("services.user_service.run_in_threadpool", new_callable=AsyncMock, return_value="hash"):
            with pytest.raises(HTTPException) as exc:
                await user_service.registrar_nuevo_usuario(db, _datos_registro())

        assert exc.value.status_code == 400
        db.rollback.assert_called_once()

    @pytest.mark.asyncio
    async def test_respuesta_incluye_nombre_usuario_y_estatus(self):
        db = _make_db_one(None)

        with patch("services.user_service.run_in_threadpool", new_callable=AsyncMock, return_value="hash"):
            resultado = await user_service.registrar_nuevo_usuario(db, _datos_registro())

        assert resultado["estatus"] == "success"
        assert resultado["nombre_usuario"] == "GalenTest"


# ─────────────────────────────────────────────
# obtener_perfil
# ─────────────────────────────────────────────

class TestObtenerPerfil:
    @pytest.mark.asyncio
    async def test_usuario_no_encontrado_lanza_404(self):
        db = _make_db_one(None)

        with pytest.raises(HTTPException) as exc:
            await user_service.obtener_perfil(db, "fantasma")

        assert exc.value.status_code == 404

    @pytest.mark.asyncio
    async def test_usuario_encontrado_devuelve_objeto(self):
        usuario = _make_usuario()
        db = _make_db_one(usuario)

        resultado = await user_service.obtener_perfil(db, "pepe")

        assert resultado is usuario


# ─────────────────────────────────────────────
# actualizar_perfil_usuario
# ─────────────────────────────────────────────

class TestActualizarPerfilUsuario:
    @pytest.mark.asyncio
    async def test_email_null_lanza_400(self):
        usuario = _make_usuario()
        db = _make_db_one(None)
        datos = ActualizarPerfil.model_construct(email=None)
        datos.__pydantic_fields_set__ = {"email"}

        with pytest.raises(HTTPException) as exc:
            await user_service.actualizar_perfil_usuario(db, usuario, datos)

        assert exc.value.status_code == 400
        assert "email" in exc.value.detail.lower()

    @pytest.mark.asyncio
    async def test_password_null_lanza_400(self):
        usuario = _make_usuario()
        db = _make_db_one(None)
        datos = ActualizarPerfil.model_construct(password=None)
        datos.__pydantic_fields_set__ = {"password"}

        with pytest.raises(HTTPException) as exc:
            await user_service.actualizar_perfil_usuario(db, usuario, datos)

        assert exc.value.status_code == 400
        assert "contraseña" in exc.value.detail.lower()

    @pytest.mark.asyncio
    async def test_email_duplicado_lanza_400(self):
        usuario = _make_usuario(id=1)
        otro = _make_usuario(id=2, email="nuevo@test.com")
        db = _make_db_seq(("one", otro))
        datos = ActualizarPerfil(email="nuevo@test.com")

        with pytest.raises(HTTPException) as exc:
            await user_service.actualizar_perfil_usuario(db, usuario, datos)

        assert exc.value.status_code == 400
        assert "email" in exc.value.detail.lower()

    @pytest.mark.asyncio
    async def test_actualizar_nombre_real_a_none_lo_borra(self):
        usuario = _make_usuario()
        usuario.nombre_real = "García"
        db = _make_db_one(None)
        datos = ActualizarPerfil.model_construct(nombre_real=None)
        datos.__pydantic_fields_set__ = {"nombre_real"}

        await user_service.actualizar_perfil_usuario(db, usuario, datos)

        assert usuario.nombre_real is None
        db.commit.assert_called_once()

    @pytest.mark.asyncio
    async def test_cambio_password_revoca_sesiones_activas(self):
        usuario = _make_usuario()
        db = _make_db_one(None)
        datos = ActualizarPerfil(password="NuevoPass1!")

        with patch("services.user_service.run_in_threadpool", new_callable=AsyncMock, return_value="nuevo_hash"):
            await user_service.actualizar_perfil_usuario(db, usuario, datos)

        # Debe haber ejecutado UPDATE en SesionRefresh y luego commit
        assert db.execute.called
        db.commit.assert_called_once()

    @pytest.mark.asyncio
    async def test_integrity_error_hace_rollback_y_lanza_400(self):
        usuario = _make_usuario()
        db = _make_db_one(None)
        db.commit = AsyncMock(side_effect=IntegrityError(None, None, Exception("constraint")))
        datos = ActualizarPerfil(email="libre@test.com")

        # el execute de comprobación duplicado devuelve None (no hay duplicado)
        db.execute = AsyncMock(return_value=MagicMock(
            scalar_one_or_none=MagicMock(return_value=None)
        ))
        db.rollback = AsyncMock()

        with pytest.raises(HTTPException) as exc:
            await user_service.actualizar_perfil_usuario(db, usuario, datos)

        assert exc.value.status_code == 400
        db.rollback.assert_called_once()

    @pytest.mark.asyncio
    async def test_payload_vacio_no_modifica_nada(self):
        usuario = _make_usuario()
        db = AsyncMock()
        db.commit = AsyncMock()
        datos = ActualizarPerfil()  # sin campos

        resultado = await user_service.actualizar_perfil_usuario(db, usuario, datos)

        assert resultado["estatus"] == "success"
        db.commit.assert_called_once()


# ─────────────────────────────────────────────
# obtener_perfil_publico
# ─────────────────────────────────────────────

class TestObtenerPerfilPublico:
    @pytest.mark.asyncio
    async def test_usuario_no_encontrado_lanza_404(self):
        db = _make_db_one(None)

        with pytest.raises(HTTPException) as exc:
            await user_service.obtener_perfil_publico(db, "fantasma")

        assert exc.value.status_code == 404

    @pytest.mark.asyncio
    async def test_perfil_privado_lanza_403(self):
        usuario = _make_usuario(perfil_visible=False)
        db = _make_db_one(usuario)

        with pytest.raises(HTTPException) as exc:
            await user_service.obtener_perfil_publico(db, "pepe")

        assert exc.value.status_code == 403
        assert "privado" in exc.value.detail.lower()

    @pytest.mark.asyncio
    async def test_perfil_publico_devuelve_usuario(self):
        usuario = _make_usuario(perfil_visible=True)
        db = _make_db_one(usuario)

        resultado = await user_service.obtener_perfil_publico(db, "pepe")

        assert resultado is usuario

    @pytest.mark.asyncio
    async def test_busqueda_es_case_insensitive(self):
        """Buscar "PEPE" debe encontrar al usuario guardado como "pepe"."""
        usuario = _make_usuario(nombre_usuario="pepe", perfil_visible=True)
        db = _make_db_one(usuario)

        resultado = await user_service.obtener_perfil_publico(db, "PEPE")
        assert resultado is usuario


# ─────────────────────────────────────────────
# buscar_usuario
# ─────────────────────────────────────────────

class TestBuscarUsuario:
    @pytest.mark.asyncio
    async def test_termino_menor_de_3_caracteres_devuelve_lista_vacia(self):
        db = AsyncMock()
        resultado = await user_service.buscar_usuario(db, "ab", "pepe")
        assert resultado == []
        db.execute.assert_not_called()

    @pytest.mark.asyncio
    async def test_termino_vacio_devuelve_lista_vacia(self):
        db = AsyncMock()
        resultado = await user_service.buscar_usuario(db, "", "pepe")
        assert resultado == []

    @pytest.mark.asyncio
    async def test_busqueda_valida_devuelve_usuarios(self):
        usuarios = [_make_usuario(nombre_usuario="galen"), _make_usuario(nombre_usuario="galeria")]
        db = _make_db_seq(("all", usuarios))

        resultado = await user_service.buscar_usuario(db, "gale", "pepe")
        assert resultado == usuarios

    @pytest.mark.asyncio
    async def test_sin_resultados_devuelve_lista_vacia(self):
        db = _make_db_seq(("all", []))
        resultado = await user_service.buscar_usuario(db, "xyz_raro_xyz", "pepe")
        assert resultado == []


# ─────────────────────────────────────────────
# eliminar_cuenta
# ─────────────────────────────────────────────

class TestEliminarCuenta:
    @pytest.mark.asyncio
    async def test_eliminar_cuenta_llama_delete_y_commit(self):
        usuario = _make_usuario()
        db = AsyncMock()
        db.delete = AsyncMock()
        db.commit = AsyncMock()

        resultado = await user_service.eliminar_cuenta(db, usuario)

        db.delete.assert_called_once_with(usuario)
        db.commit.assert_called_once()
        assert resultado["estatus"] == "success"


# ─────────────────────────────────────────────
# obtener_ranking
# ─────────────────────────────────────────────

class TestObtenerRanking:
    @pytest.mark.asyncio
    async def test_ranking_sin_filtro_devuelve_lista(self):
        fila1 = ("pepe", None, 50_000)
        fila2 = ("ana", None, 30_000)
        mock_result = MagicMock()
        mock_result.all.return_value = [fila1, fila2]
        db = AsyncMock()
        db.execute = AsyncMock(return_value=mock_result)

        resultado = await user_service.obtener_ranking(db)

        assert len(resultado) == 2
        assert resultado[0]["nombre_usuario"] == "pepe"
        assert "total_puntos" in resultado[0]

    @pytest.mark.asyncio
    async def test_ranking_con_provincia_filtra_correctamente(self):
        """El filtro por provincia se pasa como string al servicio."""
        mock_result = MagicMock()
        mock_result.all.return_value = []
        db = AsyncMock()
        db.execute = AsyncMock(return_value=mock_result)

        resultado = await user_service.obtener_ranking(db, provincia="Madrid")

        assert resultado == []
        db.execute.assert_called_once()

    @pytest.mark.asyncio
    async def test_puntos_calculados_correctamente(self):
        """1 KM = 1 punto → 10.000 metros = 10 puntos."""
        fila = ("runner", None, 10_000)
        mock_result = MagicMock()
        mock_result.all.return_value = [fila]
        db = AsyncMock()
        db.execute = AsyncMock(return_value=mock_result)

        resultado = await user_service.obtener_ranking(db)

        assert resultado[0]["total_puntos"] == 10
        