# tests/test_user_service.py

"""Cubre la lógica de negocio del servicio principal de usuarios.

Incluye alta, lectura de perfil, actualización, búsqueda pública, ranking y
eliminación de cuenta con sus efectos asociados.
"""

# Pruebas para services/user_service.py.
# Cubre: registrar_nuevo_usuario, obtener_perfil, actualizar_perfil_usuario,
# obtener_perfil_publico, buscar_usuario, eliminar_cuenta, obtener_ranking.

import pytest
from datetime import date, datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

from fastapi import HTTPException
from sqlalchemy.exc import IntegrityError

import database
import schemas
from schemas import ActualizarPerfil
from services import user_service

# ─────────────────────────────────────────────
# Ayudantes
# ─────────────────────────────────────────────


def _make_usuario(
    id: int = 1,
    nombre_usuario: str = "pepe",
    email: str = "pepe@test.com",
    perfil_visible: bool = True,
    total_metros: int = 10_000,
    provincia: str | None = None,
) -> MagicMock:
    """Construye un usuario simulado."""
    # Construye usuario.
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
    u.objetivo_semanal_metros = None
    u.objetivo_mensual_metros = None
    return u


def _make_db_one(resultado) -> AsyncMock:
    """Construye base de datos one."""
    db = AsyncMock()
    db.execute = AsyncMock(
        return_value=MagicMock(scalar_one_or_none=MagicMock(return_value=resultado))
    )
    db.commit = AsyncMock()
    db.add = MagicMock()
    db.rollback = AsyncMock()
    db.refresh = AsyncMock()
    db.delete = AsyncMock()
    return db


def _make_db_seq(*resultados) -> AsyncMock:
    """Cada item puede ser ('one', valor), ('count', n), ('items', [lista]) o ('raw', mock)."""
    # Construye base de datos seq.
    side = []
    for tipo, valor in resultados:
        m = MagicMock()
        if tipo == "one":
            m.scalar_one_or_none.return_value = valor
        elif tipo == "count":
            m.scalar_one.return_value = valor
        elif tipo in ("all", "items"):
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
    """Gestiona datos registro."""
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


@pytest.fixture(autouse=True)
def _stub_text_moderation(monkeypatch):
    """Gestiona stub text moderation."""
    monkeypatch.setattr(
        user_service.text_moderation_service,
        "validar_nombre_usuario",
        AsyncMock(),
    )
    monkeypatch.setattr(
        user_service.text_moderation_service,
        "validar_nombre_real",
        AsyncMock(),
    )


# ─────────────────────────────────────────────
# registrar_nuevo_usuario
# ─────────────────────────────────────────────


class TestRegistrarNuevoUsuario:
    """Agrupa pruebas relacionadas con registrar nuevo usuario."""

    @pytest.mark.asyncio
    async def test_nombre_de_usuario_duplicado_lanza_400(self):
        """Verifica que nombre de usuario duplicado lanza 400."""
        existente = _make_usuario(nombre_usuario="galentest")
        db = _make_db_one(existente)

        with pytest.raises(HTTPException) as exc:
            await user_service.registrar_nuevo_usuario(db, _datos_registro())

        assert exc.value.status_code == 400
        assert "nombre de usuario" in exc.value.detail.lower()

    @pytest.mark.asyncio
    async def test_email_duplicado_lanza_400(self):
        """Verifica que correo electrónico duplicado lanza 400."""
        existente = _make_usuario(nombre_usuario="otro", email="galen@test.com")
        db = _make_db_one(existente)

        with pytest.raises(HTTPException) as exc:
            await user_service.registrar_nuevo_usuario(db, _datos_registro())

        assert exc.value.status_code == 400
        assert "email" in exc.value.detail.lower()

    @pytest.mark.asyncio
    async def test_usuario_nuevo_hace_add_y_commit(self):
        """Verifica que usuario nuevo hace add y commit."""
        db = _make_db_one(None)  # sin duplicados

        with patch(
            "services.user_service.run_in_threadpool",
            new_callable=AsyncMock,
            return_value="hash",
        ):
            await user_service.registrar_nuevo_usuario(db, _datos_registro())

        db.add.assert_called_once()
        db.commit.assert_called_once()

    @pytest.mark.asyncio
    async def test_integrity_error_hace_rollback_y_lanza_400(self):
        """Verifica que integrity error hace rollback y lanza 400."""
        # Verifica que integrity error hace rollback y lanza 400.
        db = _make_db_one(None)
        db.commit = AsyncMock(
            side_effect=IntegrityError(None, None, Exception("constraint"))
        )

        with patch(
            "services.user_service.run_in_threadpool",
            new_callable=AsyncMock,
            return_value="hash",
        ):
            with pytest.raises(HTTPException) as exc:
                await user_service.registrar_nuevo_usuario(db, _datos_registro())

        assert exc.value.status_code == 400
        db.rollback.assert_called_once()

    @pytest.mark.asyncio
    async def test_respuesta_incluye_nombre_usuario_y_estatus(self):
        """Verifica que respuesta incluye nombre usuario y estatus."""
        db = _make_db_one(None)

        with patch(
            "services.user_service.run_in_threadpool",
            new_callable=AsyncMock,
            return_value="hash",
        ):
            resultado = await user_service.registrar_nuevo_usuario(
                db, _datos_registro()
            )

        assert resultado["estatus"] == "success"
        assert resultado["nombre_usuario"] == "GalenTest"

    @pytest.mark.asyncio
    async def test_registro_valida_username_y_nombre_real(self, monkeypatch):
        """Verifica que registro valida username y nombre real."""
        # Verifica que registro valida username y nombre real.
        db = _make_db_one(None)
        datos = _datos_registro().model_copy(update={"nombre_real": "María García"})

        mock_username = AsyncMock()
        mock_real = AsyncMock()

        monkeypatch.setattr(
            user_service.text_moderation_service,
            "validar_nombre_usuario",
            mock_username,
        )
        monkeypatch.setattr(
            user_service.text_moderation_service,
            "validar_nombre_real",
            mock_real,
        )

        with patch(
            "services.user_service.run_in_threadpool",
            new_callable=AsyncMock,
            return_value="hash",
        ):
            await user_service.registrar_nuevo_usuario(db, datos)

        mock_username.assert_awaited_once_with("GalenTest")
        mock_real.assert_awaited_once_with("María García")

    @pytest.mark.asyncio
    async def test_registro_sin_nombre_real_no_valida_nombre_real(self, monkeypatch):
        """Verifica que registro sin nombre real no valida nombre real."""
        # Verifica que registro sin nombre real no valida nombre real.
        db = _make_db_one(None)
        datos = _datos_registro()

        mock_real = AsyncMock()
        monkeypatch.setattr(
            user_service.text_moderation_service,
            "validar_nombre_real",
            mock_real,
        )

        with patch(
            "services.user_service.run_in_threadpool",
            new_callable=AsyncMock,
            return_value="hash",
        ):
            await user_service.registrar_nuevo_usuario(db, datos)

        mock_real.assert_not_awaited()


# ─────────────────────────────────────────────
# obtener_perfil
# ─────────────────────────────────────────────


class TestObtenerPerfil:
    """Agrupa pruebas relacionadas con obtener perfil."""

    @pytest.mark.asyncio
    async def test_usuario_no_encontrado_lanza_404(self):
        """Verifica que usuario no encontrado lanza 404."""
        db = _make_db_one(None)

        with pytest.raises(HTTPException) as exc:
            await user_service.obtener_perfil(db, 999)

        assert exc.value.status_code == 404

    @pytest.mark.asyncio
    async def test_usuario_encontrado_devuelve_objeto(self):
        """Verifica que usuario encontrado devuelve objeto."""
        usuario = _make_usuario()
        db = _make_db_one(usuario)

        resultado = await user_service.obtener_perfil(db, 1)

        assert resultado is usuario


# ─────────────────────────────────────────────
# actualizar_perfil_usuario
# ─────────────────────────────────────────────


class TestActualizarPerfilUsuario:
    """Agrupa pruebas relacionadas con actualizar perfil usuario."""

    @pytest.mark.asyncio
    async def test_email_null_lanza_400(self):
        """Verifica que correo electrónico null lanza 400."""
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
        """Verifica que password null lanza 400."""
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
        """Verifica que correo electrónico duplicado lanza 400."""
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
        """Verifica que actualizar nombre real a none lo borra."""
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
        """Verifica que cambio password revoca sesiones activas."""
        usuario = _make_usuario()
        db = _make_db_one(None)
        datos = ActualizarPerfil(password="NuevoPass1!")

        with patch(
            "services.user_service.run_in_threadpool",
            new_callable=AsyncMock,
            return_value="nuevo_hash",
        ):
            await user_service.actualizar_perfil_usuario(db, usuario, datos)

        assert db.execute.called
        db.commit.assert_called_once()

    @pytest.mark.asyncio
    async def test_integrity_error_hace_rollback_y_lanza_400(self):
        """Verifica que integrity error hace rollback y lanza 400."""
        # Verifica que integrity error hace rollback y lanza 400.
        usuario = _make_usuario()
        db = _make_db_one(None)
        db.commit = AsyncMock(
            side_effect=IntegrityError(None, None, Exception("constraint"))
        )
        datos = ActualizarPerfil(email="libre@test.com")

        db.execute = AsyncMock(
            return_value=MagicMock(scalar_one_or_none=MagicMock(return_value=None))
        )
        db.rollback = AsyncMock()

        with pytest.raises(HTTPException) as exc:
            await user_service.actualizar_perfil_usuario(db, usuario, datos)

        assert exc.value.status_code == 400
        db.rollback.assert_called_once()

    @pytest.mark.asyncio
    async def test_payload_vacio_no_modifica_nada(self):
        """Verifica que payload vacio no modifica nada."""
        usuario = _make_usuario()
        db = AsyncMock()
        db.commit = AsyncMock()
        datos = ActualizarPerfil()

        resultado = await user_service.actualizar_perfil_usuario(db, usuario, datos)

        assert resultado["estatus"] == "success"
        db.commit.assert_called_once()

    @pytest.mark.asyncio
    async def test_actualizar_nombre_real_llama_moderacion(self, monkeypatch):
        """Verifica que actualizar nombre real llama moderacion."""
        # Verifica que actualizar nombre real llama moderacion.
        usuario = _make_usuario()
        db = _make_db_one(None)
        datos = ActualizarPerfil(nombre_real="María García")

        mock_real = AsyncMock()
        monkeypatch.setattr(
            user_service.text_moderation_service,
            "validar_nombre_real",
            mock_real,
        )

        await user_service.actualizar_perfil_usuario(db, usuario, datos)

        mock_real.assert_awaited_once_with("María García")
        assert usuario.nombre_real == "María García"

    @pytest.mark.asyncio
    async def test_actualizar_nombre_real_null_no_llama_moderacion(self, monkeypatch):
        """Verifica que actualizar nombre real null no llama moderacion."""
        # Verifica que actualizar nombre real null no llama moderacion.
        usuario = _make_usuario()
        usuario.nombre_real = "Nombre Anterior"
        db = _make_db_one(None)

        datos = ActualizarPerfil.model_construct(nombre_real=None)
        datos.__pydantic_fields_set__ = {"nombre_real"}

        mock_real = AsyncMock()
        monkeypatch.setattr(
            user_service.text_moderation_service,
            "validar_nombre_real",
            mock_real,
        )

        await user_service.actualizar_perfil_usuario(db, usuario, datos)

        mock_real.assert_not_awaited()
        assert usuario.nombre_real is None

    @pytest.mark.asyncio
    async def test_actualizar_objetivo_semanal_metros(self):
        """Verifica que actualizar objetivo semanal metros."""
        usuario = _make_usuario()
        db = _make_db_one(None)
        datos = ActualizarPerfil(objetivo_semanal_metros=35000)

        resultado = await user_service.actualizar_perfil_usuario(db, usuario, datos)

        assert resultado["estatus"] == "success"
        assert usuario.objetivo_semanal_metros == 35000
        db.commit.assert_called_once()

    @pytest.mark.asyncio
    async def test_actualizar_objetivo_mensual_metros(self):
        """Verifica que actualizar objetivo mensual metros."""
        usuario = _make_usuario()
        db = _make_db_one(None)
        datos = ActualizarPerfil(objetivo_mensual_metros=120000)

        resultado = await user_service.actualizar_perfil_usuario(db, usuario, datos)

        assert resultado["estatus"] == "success"
        assert usuario.objetivo_mensual_metros == 120000
        db.commit.assert_called_once()


# ─────────────────────────────────────────────
# obtener_perfil_publico
# ─────────────────────────────────────────────


class TestObtenerPerfilPublico:
    """Agrupa pruebas relacionadas con obtener perfil publico."""

    @pytest.mark.asyncio
    async def test_usuario_no_encontrado_lanza_404(self):
        """Verifica que usuario no encontrado lanza 404."""
        db = _make_db_one(None)

        with pytest.raises(HTTPException) as exc:
            await user_service.obtener_perfil_publico(db, "fantasma")

        assert exc.value.status_code == 404

    @pytest.mark.asyncio
    async def test_perfil_privado_lanza_403(self):
        """Verifica que perfil privado lanza 403."""
        usuario = _make_usuario(perfil_visible=False)
        db = _make_db_one(usuario)

        with pytest.raises(HTTPException) as exc:
            await user_service.obtener_perfil_publico(db, "pepe")

        assert exc.value.status_code == 403
        assert "privado" in exc.value.detail.lower()

    @pytest.mark.asyncio
    async def test_perfil_publico_devuelve_usuario(self):
        """Verifica que perfil publico devuelve usuario."""
        usuario = _make_usuario(perfil_visible=True)
        db = _make_db_one(usuario)

        resultado = await user_service.obtener_perfil_publico(db, "pepe")

        assert resultado is usuario

    @pytest.mark.asyncio
    async def test_busqueda_es_case_insensitive(self):
        """Verifica que la búsqueda no distingue mayúsculas y minúsculas."""
        usuario = _make_usuario(nombre_usuario="pepe", perfil_visible=True)
        db = _make_db_one(usuario)

        resultado = await user_service.obtener_perfil_publico(db, "PEPE")
        assert resultado is usuario


# ─────────────────────────────────────────────
# buscar_usuario
# ─────────────────────────────────────────────


class TestBuscarUsuario:
    """Agrupa pruebas relacionadas con buscar usuario."""

    @pytest.mark.asyncio
    async def test_termino_menor_de_3_caracteres_devuelve_metadata_vacia(self):
        """Verifica que termino menor de 3 caracteres devuelve metadata vacia."""
        db = AsyncMock()

        resultado = await user_service.buscar_usuario(db, "ab", 1, skip=0, limit=20)

        assert resultado == {
            "items": [],
            "total": 0,
            "skip": 0,
            "limit": 20,
            "has_more": False,
        }
        db.execute.assert_not_called()

    @pytest.mark.asyncio
    async def test_termino_vacio_devuelve_metadata_vacia(self):
        """Verifica que termino vacio devuelve metadata vacia."""
        db = AsyncMock()

        resultado = await user_service.buscar_usuario(db, "", 1, skip=0, limit=20)

        assert resultado == {
            "items": [],
            "total": 0,
            "skip": 0,
            "limit": 20,
            "has_more": False,
        }

    @pytest.mark.asyncio
    async def test_busqueda_valida_devuelve_items_y_metadata(self):
        """Verifica que busqueda valida devuelve items y metadata."""
        # Verifica que busqueda valida devuelve items y metadata.
        usuarios = [
            _make_usuario(nombre_usuario="galen"),
            _make_usuario(nombre_usuario="galeria"),
        ]
        db = _make_db_seq(
            ("count", 3),
            ("items", usuarios),
        )

        resultado = await user_service.buscar_usuario(db, "gale", 1, skip=0, limit=2)

        assert resultado["items"] == usuarios
        assert resultado["total"] == 3
        assert resultado["skip"] == 0
        assert resultado["limit"] == 2
        assert resultado["has_more"] is True

    @pytest.mark.asyncio
    async def test_sin_resultados_devuelve_metadata_vacia(self):
        """Verifica que sin resultados devuelve metadata vacia."""
        # Verifica que sin resultados devuelve metadata vacia.
        db = _make_db_seq(
            ("count", 0),
            ("items", []),
        )

        resultado = await user_service.buscar_usuario(
            db, "xyz_raro_xyz", 1, skip=0, limit=20
        )

        assert resultado == {
            "items": [],
            "total": 0,
            "skip": 0,
            "limit": 20,
            "has_more": False,
        }


# ─────────────────────────────────────────────
# eliminar_cuenta
# ─────────────────────────────────────────────


class TestEliminarCuenta:
    """Agrupa pruebas relacionadas con eliminar cuenta."""

    @pytest.mark.asyncio
    async def test_eliminar_cuenta_llama_delete_y_commit(self):
        """Verifica que eliminar cuenta llama delete y commit."""
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
    """Agrupa pruebas relacionadas con obtener ranking."""

    @pytest.mark.asyncio
    async def test_ranking_sin_filtro_devuelve_lista(self):
        """Verifica que ranking sin filtro devuelve lista."""
        fila1 = ("pepe", None, 50_000, None)
        fila2 = ("ana", None, 30_000, None)
        mock_result = MagicMock()
        mock_result.all.return_value = [fila1, fila2]
        db = AsyncMock()
        db.execute = AsyncMock(return_value=mock_result)

        resultado = await user_service.obtener_ranking(db)

        assert len(resultado) == 2
        assert resultado[0]["nombre_usuario"] == "pepe"
        assert "total_puntos" in resultado[0]
        assert resultado[0]["foto_version"] == 0

    @pytest.mark.asyncio
    async def test_ranking_con_provincia_filtra_correctamente(self):
        """Verifica que ranking con provincia filtra correctamente."""
        mock_result = MagicMock()
        mock_result.all.return_value = []
        db = AsyncMock()
        db.execute = AsyncMock(return_value=mock_result)

        resultado = await user_service.obtener_ranking(db, provincia="Madrid")

        assert resultado == []
        db.execute.assert_called_once()

    @pytest.mark.asyncio
    async def test_puntos_calculados_correctamente(self):
        """Verifica que puntos calculados correctamente."""
        fila = ("runner", None, 10_000, None)
        mock_result = MagicMock()
        mock_result.all.return_value = [fila]
        db = AsyncMock()
        db.execute = AsyncMock(return_value=mock_result)

        resultado = await user_service.obtener_ranking(db)

        assert resultado[0]["total_puntos"] == 10
        assert resultado[0]["foto_version"] == 0
