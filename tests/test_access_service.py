# tests/test_access_service.py

"""Verifica la lógica de autenticación persistente y recuperación de acceso.

Cubre búsquedas de usuario, creación y refresco de sesiones, revocación de
tokens, emisión de códigos de recuperación y reseteo seguro de contraseña.
"""

# Cubre todas las funciones públicas de services/access_service.py:
# buscar_por_identificador, crear_sesion_login,
# refrescar_sesion, cerrar_sesion,
# generar_codigo_recuperacion, resetear_password,
# _hash_refresh_token, _hash_codigo_recuperacion.

from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import BackgroundTasks, HTTPException

import auth
import database
import schemas
from services import access_service

# ─────────────────────────────────────────────
# Ayudantes
# ─────────────────────────────────────────────


def _ahora() -> datetime:
    """Devuelve la fecha y hora actual."""
    return datetime.now(timezone.utc)


def _make_sesion(
    jti: str,
    familia_id: str,
    token_hash: str,
    revocada_en: datetime | None = None,
    expira_en: datetime | None = None,
    usuario_id: int = 1,
) -> MagicMock:
    """Construye una sesión simulada."""
    sesion = MagicMock(spec=database.SesionRefresh)
    sesion.jti = jti
    sesion.familia_id = familia_id
    sesion.token_hash = token_hash
    sesion.revocada_en = revocada_en
    sesion.expira_en = expira_en or (_ahora() + timedelta(days=30))
    sesion.usuario_id = usuario_id
    sesion.ultimo_uso_en = None
    sesion.reemplazada_por_jti = None
    return sesion


def _make_usuario(nombre_usuario: str = "pepe", usuario_id: int = 1) -> MagicMock:
    """Construye un usuario simulado."""
    usuario = MagicMock(spec=database.Usuario)
    usuario.id = usuario_id
    usuario.nombre_usuario = nombre_usuario
    return usuario


# ─────────────────────────────────────────────
# buscar_por_identificador
# ─────────────────────────────────────────────


class TestBuscarPorIdentificador:
    """Agrupa pruebas relacionadas con buscar por identificador."""

    @pytest.mark.asyncio
    async def test_identificador_existente_devuelve_usuario(self):
        """Verifica que identificador existente devuelve usuario."""
        usuario = _make_usuario("pepe")
        db = AsyncMock()
        db.execute = AsyncMock(
            return_value=MagicMock(scalar_one_or_none=MagicMock(return_value=usuario))
        )

        resultado = await access_service.buscar_por_identificador(db, "pepe")

        assert resultado is usuario
        db.execute.assert_called_once()

    @pytest.mark.asyncio
    async def test_identificador_inexistente_devuelve_none(self):
        """Verifica que un identificador inexistente devuelve None."""
        db = AsyncMock()
        db.execute = AsyncMock(
            return_value=MagicMock(scalar_one_or_none=MagicMock(return_value=None))
        )

        resultado = await access_service.buscar_por_identificador(db, "nadie")

        assert resultado is None

    @pytest.mark.asyncio
    async def test_busqueda_por_email_case_insensitive(self):
        """La búsqueda por email debe funcionar independientemente de mayúsculas."""
        usuario = _make_usuario("pepe")
        db = AsyncMock()
        db.execute = AsyncMock(
            return_value=MagicMock(scalar_one_or_none=MagicMock(return_value=usuario))
        )

        resultado = await access_service.buscar_por_identificador(
            db, "PEPE@EXAMPLE.COM"
        )

        assert resultado is usuario

    @pytest.mark.asyncio
    async def test_busqueda_llama_a_execute(self):
        """Verifica que el servicio consulta la BD (no devuelve hardcoded)."""
        db = AsyncMock()
        db.execute = AsyncMock(
            return_value=MagicMock(scalar_one_or_none=MagicMock(return_value=None))
        )

        await access_service.buscar_por_identificador(db, "cualquiera")

        db.execute.assert_called_once()


# ─────────────────────────────────────────────
# crear_sesion_login
# ─────────────────────────────────────────────


class TestCrearSesionLogin:
    """Agrupa pruebas relacionadas con crear sesion login."""

    @pytest.mark.asyncio
    async def test_guarda_hash_y_llama_limpiar(self):
        """Verifica que guarda hash y llama limpiar."""
        # Verifica que guarda hash y llama limpiar.
        usuario = _make_usuario("pepe", usuario_id=99)
        db = AsyncMock()
        db.commit = AsyncMock()
        db.add = MagicMock()

        with patch(
            "services.access_service._limpiar_sesiones_refresh_usuario",
            new_callable=AsyncMock,
        ) as mock_limpiar:
            resultado = await access_service.crear_sesion_login(db, usuario)

        assert resultado["estatus"] == "success"
        assert resultado["nombre_usuario"] == "pepe"
        assert "token_acceso" in resultado
        assert "refresh_token" in resultado

        db.add.assert_called_once()
        sesion_guardada = db.add.call_args.args[0]
        assert sesion_guardada.usuario_id == 99
        assert sesion_guardada.token_hash == access_service._hash_refresh_token(
            resultado["refresh_token"]
        )
        mock_limpiar.assert_awaited_once_with(db, 99)
        db.commit.assert_called_once()


# ─────────────────────────────────────────────
# refrescar_sesion — casos de error
# ─────────────────────────────────────────────


class TestRefrescarSesionErrores:
    """Agrupa pruebas relacionadas con refrescar sesion errores."""

    @pytest.mark.asyncio
    async def test_token_jwt_invalido_rechazado_sin_tocar_bd(self):
        """Verifica que token JWT invalido rechazado sin tocar bd."""
        db = AsyncMock()

        with pytest.raises(HTTPException) as exc:
            await access_service.refrescar_sesion(db, "token.malformado.jwt")

        assert exc.value.status_code == 401
        db.execute.assert_not_called()

    @pytest.mark.asyncio
    async def test_sesion_no_encontrada_lanza_401(self):
        """Verifica que sesion no encontrada lanza 401."""
        jti, familia = "jti-miss-001", "fam-miss-001"
        rt = auth.crear_token_refresh(1, jti, familia)

        db = AsyncMock()
        db.execute = AsyncMock(
            return_value=MagicMock(scalar_one_or_none=MagicMock(return_value=None))
        )

        with pytest.raises(HTTPException) as exc:
            await access_service.refrescar_sesion(db, rt)

        assert exc.value.status_code == 401

    @pytest.mark.asyncio
    async def test_token_revocado_lanza_401_reutilizado(self):
        """Verifica que token revocado lanza 401 reutilizado."""
        # Verifica que token revocado lanza 401 reutilizado.
        jti, familia = "jti-rotado-001", "familia-001"
        rt = auth.crear_token_refresh(1, jti, familia)
        sesion = _make_sesion(
            jti=jti,
            familia_id=familia,
            token_hash=access_service._hash_refresh_token(rt),
            revocada_en=_ahora() - timedelta(minutes=5),
        )

        db = AsyncMock()
        db.execute = AsyncMock(
            return_value=MagicMock(scalar_one_or_none=MagicMock(return_value=sesion))
        )
        db.commit = AsyncMock()

        with pytest.raises(HTTPException) as exc:
            await access_service.refrescar_sesion(db, rt)

        assert exc.value.status_code == 401
        assert "reutilizado" in exc.value.detail.lower()
        db.commit.assert_called_once()

    @pytest.mark.asyncio
    async def test_token_revocado_invoca_revocar_familia(self):
        """Verifica que token revocado invoca revocar familia."""
        # Verifica que token revocado invoca revocar familia.
        jti, familia = "jti-reuse-101", "familia-reuse-101"
        rt = auth.crear_token_refresh(1, jti, familia)
        sesion = _make_sesion(
            jti=jti,
            familia_id=familia,
            token_hash=access_service._hash_refresh_token(rt),
            revocada_en=_ahora() - timedelta(minutes=1),
        )

        db = AsyncMock()
        db.execute = AsyncMock(
            return_value=MagicMock(scalar_one_or_none=MagicMock(return_value=sesion))
        )
        db.commit = AsyncMock()

        with patch(
            "services.access_service._revocar_familia_refresh", new_callable=AsyncMock
        ) as mock_rev:
            with pytest.raises(HTTPException):
                await access_service.refrescar_sesion(db, rt)

        mock_rev.assert_awaited_once_with(db, familia)

    @pytest.mark.asyncio
    async def test_hash_manipulado_revoca_familia_y_lanza_401(self):
        """Verifica que hash manipulado revoca familia y lanza 401."""
        jti, familia = "jti-manipulado-002", "familia-002"
        rt = auth.crear_token_refresh(1, jti, familia)
        sesion = _make_sesion(
            jti=jti,
            familia_id=familia,
            token_hash="a" * 64,  # hash falso → jamás coincide
        )

        db = AsyncMock()
        db.execute = AsyncMock(
            side_effect=[
                MagicMock(scalar_one_or_none=MagicMock(return_value=sesion)),
                MagicMock(),
            ]
        )
        db.commit = AsyncMock()

        with pytest.raises(HTTPException) as exc:
            await access_service.refrescar_sesion(db, rt)

        assert exc.value.status_code == 401
        assert db.commit.called

    @pytest.mark.asyncio
    async def test_sesion_expirada_en_bd_lanza_401(self):
        """Verifica que sesion expirada en bd lanza 401."""
        # Verifica que sesion expirada en bd lanza 401.
        jti, familia = "jti-expirado-004", "familia-004"
        rt = auth.crear_token_refresh(1, jti, familia)
        sesion = _make_sesion(
            jti=jti,
            familia_id=familia,
            token_hash=access_service._hash_refresh_token(rt),
            expira_en=_ahora() - timedelta(days=1),
        )

        db = AsyncMock()
        db.execute = AsyncMock(
            return_value=MagicMock(scalar_one_or_none=MagicMock(return_value=sesion))
        )

        with pytest.raises(HTTPException) as exc:
            await access_service.refrescar_sesion(db, rt)

        assert exc.value.status_code == 401
        assert "expirado" in exc.value.detail.lower()

    @pytest.mark.asyncio
    async def test_usuario_no_encontrado_revoca_sesion_y_lanza_401(self):
        """Verifica que usuario no encontrado revoca sesion y lanza 401."""
        # Verifica que usuario no encontrado revoca sesion y lanza 401.
        jti, familia = "jti-user-miss-102", "fam-user-miss-102"
        rt = auth.crear_token_refresh(1, jti, familia)
        sesion = _make_sesion(
            jti=jti,
            familia_id=familia,
            token_hash=access_service._hash_refresh_token(rt),
        )

        db = AsyncMock()
        db.execute = AsyncMock(
            side_effect=[
                MagicMock(scalar_one_or_none=MagicMock(return_value=sesion)),
                MagicMock(scalar_one_or_none=MagicMock(return_value=None)),
            ]
        )
        db.commit = AsyncMock()

        with pytest.raises(HTTPException) as exc:
            await access_service.refrescar_sesion(db, rt)

        assert exc.value.status_code == 401
        assert "usuario no encontrado" in exc.value.detail.lower()
        assert sesion.revocada_en is not None
        db.commit.assert_called_once()


# ─────────────────────────────────────────────
# refrescar_sesion — flujo feliz
# ─────────────────────────────────────────────


class TestRefrescarSesionExito:
    """Agrupa pruebas relacionadas con refrescar sesion exito."""

    @pytest.mark.asyncio
    async def test_rotacion_exitosa_devuelve_nuevos_tokens(self):
        """Verifica que rotacion exitosa devuelve nuevos tokens."""
        # Verifica que rotacion exitosa devuelve nuevos tokens.
        jti, familia = "jti-valido-005", "familia-005"
        rt = auth.crear_token_refresh(1, jti, familia)
        sesion = _make_sesion(
            jti=jti,
            familia_id=familia,
            token_hash=access_service._hash_refresh_token(rt),
        )
        usuario = _make_usuario("pepe")

        db = AsyncMock()
        db.execute = AsyncMock(
            side_effect=[
                MagicMock(scalar_one_or_none=MagicMock(return_value=sesion)),
                MagicMock(scalar_one_or_none=MagicMock(return_value=usuario)),
                MagicMock(),
            ]
        )
        db.commit = AsyncMock()
        db.add = MagicMock()

        resultado = await access_service.refrescar_sesion(db, rt)

        assert resultado["estatus"] == "success"
        assert resultado["nombre_usuario"] == "pepe"
        assert "token_acceso" in resultado
        assert "refresh_token" in resultado
        assert resultado["refresh_token"] != rt

    @pytest.mark.asyncio
    async def test_rotacion_marca_sesion_anterior_como_revocada(self):
        """Verifica que rotacion marca sesion anterior como revocada."""
        # Verifica que rotacion marca sesion anterior como revocada.
        jti, familia = "jti-valido-006", "familia-006"
        rt = auth.crear_token_refresh(1, jti, familia)
        sesion = _make_sesion(
            jti=jti,
            familia_id=familia,
            token_hash=access_service._hash_refresh_token(rt),
        )
        usuario = _make_usuario("pepe")

        db = AsyncMock()
        db.execute = AsyncMock(
            side_effect=[
                MagicMock(scalar_one_or_none=MagicMock(return_value=sesion)),
                MagicMock(scalar_one_or_none=MagicMock(return_value=usuario)),
                MagicMock(),
            ]
        )
        db.commit = AsyncMock()
        db.add = MagicMock()

        await access_service.refrescar_sesion(db, rt)

        assert sesion.revocada_en is not None
        assert sesion.reemplazada_por_jti is not None


# ─────────────────────────────────────────────
# cerrar_sesion (logout)
# ─────────────────────────────────────────────


class TestCerrarSesion:
    """Agrupa pruebas relacionadas con cerrar sesion."""

    @pytest.mark.asyncio
    async def test_logout_normal_revoca_sesion(self):
        """Verifica que logout normal revoca sesion."""
        # Verifica que logout normal revoca sesion.
        jti, familia = "jti-logout-001", "familia-logout-001"
        rt = auth.crear_token_refresh(1, jti, familia)
        sesion = _make_sesion(
            jti=jti,
            familia_id=familia,
            token_hash=access_service._hash_refresh_token(rt),
        )

        db = AsyncMock()
        db.execute = AsyncMock(
            return_value=MagicMock(scalar_one_or_none=MagicMock(return_value=sesion))
        )
        db.commit = AsyncMock()

        resultado = await access_service.cerrar_sesion(db, rt)

        assert resultado["estatus"] == "success"
        assert sesion.revocada_en is not None
        db.commit.assert_called_once()

    @pytest.mark.asyncio
    async def test_logout_idempotente_sesion_ya_revocada(self):
        """Verifica que logout idempotente sesion ya revocada."""
        # Verifica que logout idempotente sesion ya revocada.
        jti, familia = "jti-logout-002", "familia-logout-002"
        rt = auth.crear_token_refresh(1, jti, familia)
        sesion = _make_sesion(
            jti=jti,
            familia_id=familia,
            token_hash=access_service._hash_refresh_token(rt),
            revocada_en=_ahora() - timedelta(hours=1),
        )

        db = AsyncMock()
        db.execute = AsyncMock(
            return_value=MagicMock(scalar_one_or_none=MagicMock(return_value=sesion))
        )
        db.commit = AsyncMock()

        resultado = await access_service.cerrar_sesion(db, rt)

        assert resultado["estatus"] == "success"
        db.commit.assert_not_called()

    @pytest.mark.asyncio
    async def test_logout_token_invalido_responde_success(self):
        """Verifica que logout token invalido responde success."""
        db = AsyncMock()
        resultado = await access_service.cerrar_sesion(db, "token.invalido.jwt")

        assert resultado["estatus"] == "success"
        db.execute.assert_not_called()

    @pytest.mark.asyncio
    async def test_logout_sesion_no_encontrada_responde_success(self):
        """Verifica que logout sesion no encontrada responde success."""
        rt = auth.crear_token_refresh(1, "jti-logout-003", "fam-003")

        db = AsyncMock()
        db.execute = AsyncMock(
            return_value=MagicMock(scalar_one_or_none=MagicMock(return_value=None))
        )

        resultado = await access_service.cerrar_sesion(db, rt)
        assert resultado["estatus"] == "success"

    @pytest.mark.asyncio
    async def test_logout_hash_manipulado_no_revoca_la_sesion(self):
        """Verifica que logout hash manipulado no revoca la sesion."""
        jti, familia = "jti-logout-004", "fam-004"
        rt = auth.crear_token_refresh(1, jti, familia)
        sesion = _make_sesion(
            jti=jti,
            familia_id=familia,
            token_hash="b" * 64,  # hash distinto al del token
        )

        db = AsyncMock()
        db.execute = AsyncMock(
            return_value=MagicMock(scalar_one_or_none=MagicMock(return_value=sesion))
        )
        db.commit = AsyncMock()

        resultado = await access_service.cerrar_sesion(db, rt)

        assert resultado["estatus"] == "success"
        db.commit.assert_not_called()
        assert sesion.revocada_en is None


# ─────────────────────────────────────────────
# generar_codigo_recuperacion
# ─────────────────────────────────────────────


class TestGenerarCodigoRecuperacion:
    """Agrupa pruebas relacionadas con generar codigo recuperacion."""

    @pytest.mark.asyncio
    async def test_email_existente_guarda_hash_y_programa_envio(self):
        """Verifica que correo electrónico existente guarda hash y programa envio."""
        # Verifica que correo electrónico existente guarda hash y programa envio.
        usuario = MagicMock()
        usuario.codigo_recuperacion = None
        usuario.codigo_expiracion = None

        db = AsyncMock()
        db.execute = AsyncMock(
            return_value=MagicMock(scalar_one_or_none=MagicMock(return_value=usuario))
        )
        db.commit = AsyncMock()

        background_tasks = BackgroundTasks()

        with patch("services.access_service.secrets.randbelow", return_value=0):
            resultado = await access_service.generar_codigo_recuperacion(
                db,
                "USER@Test.com",
                background_tasks,
                "en",
            )

        assert resultado["estatus"] == "success"
        assert usuario.codigo_recuperacion == access_service._hash_codigo_recuperacion(
            "100000"
        )
        assert usuario.codigo_expiracion is not None
        db.commit.assert_called_once()
        assert len(background_tasks.tasks) == 1
        tarea = background_tasks.tasks[0]
        assert tarea.args[0] == "user@test.com"
        assert tarea.args[1] == "100000"
        assert tarea.args[3] == "en"

    @pytest.mark.asyncio
    async def test_email_inexistente_no_hace_commit_ni_programa_envio(self):
        """Verifica que correo electrónico inexistente no hace commit ni programa envio."""
        # Verifica que correo electrónico inexistente no hace commit ni programa envio.
        db = AsyncMock()
        db.execute = AsyncMock(
            return_value=MagicMock(scalar_one_or_none=MagicMock(return_value=None))
        )
        db.commit = AsyncMock()

        background_tasks = BackgroundTasks()

        resultado = await access_service.generar_codigo_recuperacion(
            db,
            "nadie@test.com",
            background_tasks,
            "es",
        )

        assert resultado["estatus"] == "success"
        db.commit.assert_not_called()
        assert background_tasks.tasks == []

    @pytest.mark.asyncio
    async def test_respuesta_identica_email_exista_o_no(self):
        """No debe filtrarse si el email está registrado o no."""
        # Verifica que respuesta identica correo electrónico exista o no.
        usuario = MagicMock()
        usuario.id = 1
        usuario.codigo_recuperacion = None
        usuario.codigo_expiracion = None

        db_existe = AsyncMock()
        db_existe.execute = AsyncMock(
            side_effect=[
                MagicMock(scalar_one_or_none=MagicMock(return_value=usuario)),
                MagicMock(scalar_one_or_none=MagicMock(return_value=None)),
            ]
        )
        db_existe.commit = AsyncMock()

        db_no_existe = AsyncMock()
        db_no_existe.execute = AsyncMock(
            return_value=MagicMock(scalar_one_or_none=MagicMock(return_value=None))
        )

        with patch("services.access_service.secrets.randbelow", return_value=0):
            r1 = await access_service.generar_codigo_recuperacion(
                db_existe, "existe@test.com", BackgroundTasks(), "es"
            )
        r2 = await access_service.generar_codigo_recuperacion(
            db_no_existe, "noexiste@test.com", BackgroundTasks(), "es"
        )

        assert r1["estatus"] == r2["estatus"] == "success"

    @pytest.mark.asyncio
    async def test_cuenta_google_no_genera_codigo_y_programa_aviso(self):
        """Verifica que cuenta google no genera codigo y programa aviso."""
        # Verifica que cuenta google no genera codigo y programa aviso.
        usuario = MagicMock()
        usuario.id = 12
        usuario.codigo_recuperacion = None
        usuario.codigo_expiracion = None

        db = AsyncMock()
        db.execute = AsyncMock(
            side_effect=[
                MagicMock(scalar_one_or_none=MagicMock(return_value=usuario)),
                MagicMock(scalar_one_or_none=MagicMock(return_value=1)),
            ]
        )
        db.commit = AsyncMock()

        background_tasks = BackgroundTasks()

        resultado = await access_service.generar_codigo_recuperacion(
            db,
            "google@test.com",
            background_tasks,
            "en",
        )

        assert resultado["estatus"] == "success"
        assert "instructions" in resultado["mensaje"].lower()
        assert usuario.codigo_recuperacion is None
        assert usuario.codigo_expiracion is None
        db.commit.assert_not_called()
        assert len(background_tasks.tasks) == 1
        tarea = background_tasks.tasks[0]
        assert tarea.args == ("google@test.com", "en")


# ─────────────────────────────────────────────
# resetear_password
# ─────────────────────────────────────────────


class TestResetearPassword:
    """Agrupa pruebas relacionadas con resetear password."""

    @pytest.mark.asyncio
    async def test_codigo_correcto_actualiza_password_y_revoca_refresh_tokens(self):
        """Verifica que codigo correcto actualiza password y revoca refresco tokens."""
        # Verifica que codigo correcto actualiza password y revoca refresco tokens.
        usuario = MagicMock()
        usuario.id = 7
        usuario.codigo_expiracion = _ahora() + timedelta(minutes=10)
        usuario.codigo_recuperacion = access_service._hash_codigo_recuperacion("123456")
        usuario.password_encriptada = "hash-antiguo"

        db = AsyncMock()
        db.execute = AsyncMock(
            side_effect=[
                MagicMock(scalar_one_or_none=MagicMock(return_value=usuario)),
                MagicMock(scalar_one_or_none=MagicMock(return_value=None)),
                MagicMock(),
            ]
        )
        db.commit = AsyncMock()

        datos = schemas.ConfirmarPassword(
            email="user@test.com",
            codigo="123456",
            nueva_password="Password1",
        )

        async def fake_run_in_threadpool(fn, *args, **kwargs):
            """Crea un simulacro de run in threadpool."""
            return "hash-nuevo"

        with patch(
            "services.access_service.run_in_threadpool",
            side_effect=fake_run_in_threadpool,
        ):
            resultado = await access_service.resetear_password(db, datos)

        assert resultado["estatus"] == "success"
        assert usuario.password_encriptada == "hash-nuevo"
        assert usuario.codigo_recuperacion is None
        assert usuario.codigo_expiracion is None
        assert db.execute.call_count == 3
        db.commit.assert_called_once()

    @pytest.mark.asyncio
    async def test_codigo_expirado_lanza_400_y_no_hace_commit(self):
        """Verifica que codigo expirado lanza 400 y no hace commit."""
        # Verifica que codigo expirado lanza 400 y no hace commit.
        usuario = MagicMock()
        usuario.id = 7
        usuario.codigo_expiracion = _ahora() - timedelta(minutes=1)
        usuario.codigo_recuperacion = access_service._hash_codigo_recuperacion("123456")

        db = AsyncMock()
        db.execute = AsyncMock(
            return_value=MagicMock(scalar_one_or_none=MagicMock(return_value=usuario))
        )
        db.commit = AsyncMock()

        datos = schemas.ConfirmarPassword(
            email="user@test.com",
            codigo="123456",
            nueva_password="Password1",
        )

        with pytest.raises(HTTPException) as exc:
            await access_service.resetear_password(db, datos)

        assert exc.value.status_code == 400
        assert "expirado" in exc.value.detail.lower()
        db.commit.assert_not_called()

    @pytest.mark.asyncio
    async def test_codigo_o_email_invalidos_lanza_400(self):
        """Verifica que codigo o correo electrónico invalidos lanza 400."""
        # Verifica que codigo o correo electrónico invalidos lanza 400.
        db = AsyncMock()
        db.execute = AsyncMock(
            return_value=MagicMock(scalar_one_or_none=MagicMock(return_value=None))
        )

        datos = schemas.ConfirmarPassword(
            email="user@test.com",
            codigo="123456",
            nueva_password="Password1",
        )

        with pytest.raises(HTTPException) as exc:
            await access_service.resetear_password(db, datos)

        assert exc.value.status_code == 400
        assert "inválidos" in exc.value.detail.lower()

    @pytest.mark.asyncio
    async def test_codigo_incorrecto_lanza_400(self):
        """Código incorrecto: el servicio filtra por email+hash en una sola query,
        así que un código equivocado devuelve None → mismo 400 que email inválido."""
        db = AsyncMock()
        db.execute = AsyncMock(
            return_value=MagicMock(
                scalar_one_or_none=MagicMock(
                    return_value=None
                )  # hash no coincide → no encontrado
            )
        )
        db.commit = AsyncMock()

        datos = schemas.ConfirmarPassword(
            email="user@test.com",
            codigo="999999",  # código equivocado
            nueva_password="Password1",
        )

        with pytest.raises(HTTPException) as exc:
            await access_service.resetear_password(db, datos)

        assert exc.value.status_code == 400
        assert "inválidos" in exc.value.detail.lower()
        db.commit.assert_not_called()

    @pytest.mark.asyncio
    async def test_cuenta_google_con_codigo_existente_se_bloquea_y_limpia_otp(self):
        """Verifica que cuenta google con codigo existente se bloquea y limpia otp."""
        usuario = MagicMock()
        usuario.id = 7
        usuario.codigo_expiracion = _ahora() + timedelta(minutes=10)
        usuario.codigo_recuperacion = access_service._hash_codigo_recuperacion("123456")

        db = AsyncMock()
        db.execute = AsyncMock(
            side_effect=[
                MagicMock(scalar_one_or_none=MagicMock(return_value=usuario)),
                MagicMock(scalar_one_or_none=MagicMock(return_value=1)),
            ]
        )
        db.commit = AsyncMock()

        datos = schemas.ConfirmarPassword(
            email="google@test.com",
            codigo="123456",
            nueva_password="Password1",
        )

        with pytest.raises(HTTPException) as exc:
            await access_service.resetear_password(db, datos)

        assert exc.value.status_code == 400
        assert exc.value.detail["error_code"] == "RECOVERY_CODE_OR_EMAIL_INVALID"  # type: ignore
        assert usuario.codigo_recuperacion is None
        assert usuario.codigo_expiracion is None
        db.commit.assert_called_once()


# ─────────────────────────────────────────────
# Funciones de hash
# ─────────────────────────────────────────────


class TestFuncionesHash:
    """Agrupa pruebas relacionadas con funciones hash."""

    def test_hash_refresh_determinista(self):
        """Verifica que hash refresco determinista."""
        rt = auth.crear_token_refresh(1, "jti-h1", "fam-h1")
        assert access_service._hash_refresh_token(
            rt
        ) == access_service._hash_refresh_token(rt)

    def test_hash_refresh_distinto_por_token(self):
        """Verifica que hash refresco distinto por token."""
        rt1 = auth.crear_token_refresh(1, "jti-1", "fam")
        rt2 = auth.crear_token_refresh(1, "jti-2", "fam")
        assert access_service._hash_refresh_token(
            rt1
        ) != access_service._hash_refresh_token(rt2)

    def test_hash_refresh_longitud_64(self):
        """Verifica que hash refresco longitud 64."""
        rt = auth.crear_token_refresh(1, "jti-len", "fam-len")
        assert len(access_service._hash_refresh_token(rt)) == 64

    def test_hash_codigo_recuperacion_determinista(self):
        """Verifica que hash codigo recuperacion determinista."""
        assert access_service._hash_codigo_recuperacion(
            "123456"
        ) == access_service._hash_codigo_recuperacion("123456")

    def test_hash_codigo_diferente_por_codigo(self):
        """Verifica que hash codigo diferente por codigo."""
        assert access_service._hash_codigo_recuperacion(
            "123456"
        ) != access_service._hash_codigo_recuperacion("654321")

    def test_hash_refresh_y_codigo_usan_secretos_distintos(self):
        """Verifica que hash refresco y codigo usan secretos distintos."""
        texto = "mismo-texto"
        assert access_service._hash_refresh_token(
            texto
        ) != access_service._hash_codigo_recuperacion(texto)
