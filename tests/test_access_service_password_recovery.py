from datetime import timedelta, timezone, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import BackgroundTasks, HTTPException

import schemas
from services import access_service



def _ahora() -> datetime:
    return datetime.now(timezone.utc)


class TestGenerarCodigoRecuperacion:
    @pytest.mark.asyncio
    async def test_email_existente_guarda_hash_y_programa_envio(self):
        usuario = MagicMock()
        usuario.codigo_recuperacion = None
        usuario.codigo_expiracion = None

        db = AsyncMock()
        db.execute = AsyncMock(
            return_value=MagicMock(
                scalar_one_or_none=MagicMock(return_value=usuario)
            )
        )
        db.commit = AsyncMock()

        background_tasks = BackgroundTasks()

        with patch("services.access_service.secrets.randbelow", return_value=0):
            resultado = await access_service.generar_codigo_recuperacion(
                db,
                "USER@Test.com",
                background_tasks,
            )

        assert resultado["estatus"] == "success"
        assert usuario.codigo_recuperacion == access_service._hash_codigo_recuperacion("100000")
        assert usuario.codigo_expiracion is not None
        db.commit.assert_called_once()
        assert len(background_tasks.tasks) == 1
        tarea = background_tasks.tasks[0]
        assert tarea.args[0] == "USER@Test.com"
        assert tarea.args[1] == "100000"

    @pytest.mark.asyncio
    async def test_email_inexistente_no_hace_commit_ni_programa_envio(self):
        db = AsyncMock()
        db.execute = AsyncMock(
            return_value=MagicMock(
                scalar_one_or_none=MagicMock(return_value=None)
            )
        )
        db.commit = AsyncMock()

        background_tasks = BackgroundTasks()

        resultado = await access_service.generar_codigo_recuperacion(
            db,
            "nadie@test.com",
            background_tasks,
        )

        assert resultado["estatus"] == "success"
        db.commit.assert_not_called()
        assert background_tasks.tasks == []


class TestResetearPassword:
    @pytest.mark.asyncio
    async def test_codigo_correcto_actualiza_password_y_revoca_refresh_tokens(self):
        usuario = MagicMock()
        usuario.id = 7
        usuario.codigo_expiracion = _ahora() + timedelta(minutes=10)
        usuario.codigo_recuperacion = access_service._hash_codigo_recuperacion("123456")
        usuario.password_encriptada = "hash-antiguo"

        db = AsyncMock()
        db.execute = AsyncMock(side_effect=[
            MagicMock(scalar_one_or_none=MagicMock(return_value=usuario)),
            MagicMock(),
        ])
        db.commit = AsyncMock()

        datos = schemas.ConfirmarPassword(
            email="user@test.com",
            codigo="123456",
            nueva_password="Password1",
        )

        async def fake_run_in_threadpool(fn, *args, **kwargs):
            return "hash-nuevo"

        with patch("services.access_service.run_in_threadpool", side_effect=fake_run_in_threadpool):
            resultado = await access_service.resetear_password(db, datos)

        assert resultado["estatus"] == "success"
        assert usuario.password_encriptada == "hash-nuevo"
        assert usuario.codigo_recuperacion is None
        assert usuario.codigo_expiracion is None
        assert db.execute.call_count == 2
        db.commit.assert_called_once()

    @pytest.mark.asyncio
    async def test_codigo_expirado_lanza_400_y_no_hace_commit(self):
        usuario = MagicMock()
        usuario.id = 7
        usuario.codigo_expiracion = _ahora() - timedelta(minutes=1)
        usuario.codigo_recuperacion = access_service._hash_codigo_recuperacion("123456")

        db = AsyncMock()
        db.execute = AsyncMock(
            return_value=MagicMock(
                scalar_one_or_none=MagicMock(return_value=usuario)
            )
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
        db = AsyncMock()
        db.execute = AsyncMock(
            return_value=MagicMock(
                scalar_one_or_none=MagicMock(return_value=None)
            )
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
