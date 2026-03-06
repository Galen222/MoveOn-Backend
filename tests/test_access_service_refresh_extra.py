from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException

import auth
import database
from services import access_service



def _ahora() -> datetime:
    return datetime.now(timezone.utc)



def _make_sesion(
    jti: str,
    familia_id: str,
    token_hash: str,
    revocada_en: datetime | None = None,
    expira_en: datetime | None = None,
    usuario_id: int = 1,
) -> MagicMock:
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
    usuario = MagicMock(spec=database.Usuario)
    usuario.id = usuario_id
    usuario.nombre_usuario = nombre_usuario
    return usuario


class TestRefreshExtra:
    @pytest.mark.asyncio
    async def test_refresh_reutilizado_llama_a_revocar_familia_correcta(self):
        jti = "jti-reuse-101"
        familia = "familia-reuse-101"
        rt = auth.crear_token_refresh("pepe", jti, familia)
        sesion = _make_sesion(
            jti=jti,
            familia_id=familia,
            token_hash=access_service._hash_refresh_token(rt),
            revocada_en=_ahora() - timedelta(minutes=1),
        )

        db = AsyncMock()
        db.execute = AsyncMock(
            return_value=MagicMock(
                scalar_one_or_none=MagicMock(return_value=sesion)
            )
        )
        db.commit = AsyncMock()

        with patch("services.access_service._revocar_familia_refresh", new_callable=AsyncMock) as mock_revocar:
            with pytest.raises(HTTPException) as exc:
                await access_service.refrescar_sesion(db, rt)

        assert exc.value.status_code == 401
        assert "reutilizado" in exc.value.detail.lower()
        mock_revocar.assert_awaited_once_with(db, familia)
        db.commit.assert_called_once()

    @pytest.mark.asyncio
    async def test_usuario_no_encontrado_revoca_sesion_actual_y_lanza_401(self):
        jti = "jti-user-missing-102"
        familia = "familia-user-missing-102"
        rt = auth.crear_token_refresh("pepe", jti, familia)
        sesion = _make_sesion(
            jti=jti,
            familia_id=familia,
            token_hash=access_service._hash_refresh_token(rt),
            revocada_en=None,
        )

        db = AsyncMock()
        db.execute = AsyncMock(side_effect=[
            MagicMock(scalar_one_or_none=MagicMock(return_value=sesion)),
            MagicMock(scalar_one_or_none=MagicMock(return_value=None)),
        ])
        db.commit = AsyncMock()

        with pytest.raises(HTTPException) as exc:
            await access_service.refrescar_sesion(db, rt)

        assert exc.value.status_code == 401
        assert "usuario no encontrado" in exc.value.detail.lower()
        assert sesion.revocada_en is not None
        db.commit.assert_called_once()

    @pytest.mark.asyncio
    async def test_crear_sesion_login_guarda_hash_y_limpia_sesiones_anteriores(self):
        usuario = _make_usuario("pepe", usuario_id=99)
        db = AsyncMock()
        db.commit = AsyncMock()
        db.add = MagicMock()

        with patch("services.access_service._limpiar_sesiones_refresh_usuario", new_callable=AsyncMock) as mock_limpiar:
            resultado = await access_service.crear_sesion_login(db, usuario)

        assert resultado["estatus"] == "success"
        assert resultado["nombre_usuario"] == "pepe"
        assert "token_acceso" in resultado
        assert "refresh_token" in resultado

        db.add.assert_called_once()
        sesion_guardada = db.add.call_args.args[0]
        assert sesion_guardada.usuario_id == 99
        assert sesion_guardada.token_hash == access_service._hash_refresh_token(resultado["refresh_token"])
        mock_limpiar.assert_awaited_once_with(db, 99)
        db.commit.assert_called_once()

    @pytest.mark.asyncio
    async def test_crear_sesion_login_si_commit_falla_propaga_excepcion(self):
        usuario = MagicMock()
        usuario.id = 55
        usuario.nombre_usuario = "pepe"

        db = AsyncMock()
        db.add = MagicMock()
        db.commit = AsyncMock(side_effect=RuntimeError("db down"))

        with patch("services.access_service._limpiar_sesiones_refresh_usuario", new_callable=AsyncMock) as mock_limpiar:
            with pytest.raises(RuntimeError, match="db down"):
                await access_service.crear_sesion_login(db, usuario)

        db.add.assert_called_once()
        mock_limpiar.assert_awaited_once_with(db, 55)
        db.commit.assert_called_once()