# tests/test_access_service_refresh.py
#
# Tests para la lógica de rotación de refresh tokens en access_service.py.
# Este es el flujo más crítico de seguridad del backend:
#   - Token rotado no puede reutilizarse (revoca toda la familia)
#   - Token manipulado (hash no coincide) revoca toda la familia
#   - Sesión expirada en BD se rechaza aunque el JWT siga siendo válido
#   - Sesión no encontrada en BD siempre es 401
#   - El logout es idempotente: llamarlo dos veces no falla
#
# Usamos unittest.mock para aislar la lógica de la BD real.
# SQLite no soporta SELECT ... FOR UPDATE, así que mockear es
# más limpio y más rápido que monkeypatching de SQLAlchemy.

import pytest
import pytest_asyncio
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

from fastapi import HTTPException

import auth
import database
from services import access_service


# ─────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────

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
    """Construye un objeto SesionRefresh falso con los campos necesarios."""
    sesion = MagicMock(spec=database.SesionRefresh)
    sesion.jti = jti
    sesion.familia_id = familia_id
    sesion.token_hash = token_hash
    sesion.revocada_en = revocada_en
    sesion.expira_en = expira_en or (_ahora() + timedelta(days=30))
    sesion.usuario_id = usuario_id
    return sesion


def _make_usuario(nombre_usuario: str = "pepe", usuario_id: int = 1) -> MagicMock:
    usuario = MagicMock(spec=database.Usuario)
    usuario.id = usuario_id
    usuario.nombre_usuario = nombre_usuario
    return usuario


def _make_db(sesion_resultado=None, usuario_resultado=None) -> AsyncMock:
    """
    Construye un mock de AsyncSession cuyo db.execute().scalar_one_or_none()
    devuelve primero sesion_resultado y luego usuario_resultado
    en llamadas sucesivas.
    """
    db = AsyncMock()

    # Primera llamada a execute → busca la sesión
    # Llamadas siguientes → _revocar_familia (UPDATE) o busca usuario
    mock_result_sesion = MagicMock()
    mock_result_sesion.scalar_one_or_none.return_value = sesion_resultado

    mock_result_usuario = MagicMock()
    mock_result_usuario.scalar_one_or_none.return_value = usuario_resultado

    # side_effect: primera llamada devuelve sesion, el resto usuario
    db.execute = AsyncMock(side_effect=[
        mock_result_sesion,   # SELECT SesionRefresh WHERE jti=...
        MagicMock(),          # UPDATE revocación familia (si aplica)
        mock_result_usuario,  # SELECT Usuario WHERE id=...
        MagicMock(),          # add nueva sesión
    ])

    db.commit = AsyncMock()
    db.add = MagicMock()

    return db


# ─────────────────────────────────────────────
# Tests: refrescar_sesion
# ─────────────────────────────────────────────

class TestRefrescarSesion:

    @pytest.mark.asyncio
    async def test_token_rotado_lanza_401_reutilizado(self):
        """
        Si el token ya fue rotado (revocada_en != None), se debe:
          1. Revocar toda la familia (medida de seguridad ante robo de token).
          2. Devolver 401 con mensaje que incluya 'reutilizado'.
        """
        jti = "jti-rotado-001"
        familia = "familia-001"

        rt = auth.crear_token_refresh("pepe", jti, familia)
        rt_hash = access_service._hash_refresh_token(rt)

        sesion = _make_sesion(
            jti=jti,
            familia_id=familia,
            token_hash=rt_hash,
            revocada_en=_ahora() - timedelta(minutes=5),  # ya revocada
        )
        db = _make_db(sesion_resultado=sesion)

        with pytest.raises(HTTPException) as exc:
            await access_service.refrescar_sesion(db, rt)

        assert exc.value.status_code == 401
        assert "reutilizado" in exc.value.detail.lower()
        # La revocación de familia implica al menos 2 llamadas a db.execute
        # (SELECT sesión + UPDATE revocación) y un commit
        assert db.commit.called

    @pytest.mark.asyncio
    async def test_hash_manipulado_revoca_familia_y_lanza_401(self):
        """
        Si el token llega con hash distinto al guardado en BD
        (posible manipulación), se revoca toda la familia.

        Usamos un hash hardcodeado en BD ("a" * 64) que garantiza no coincidir
        con el hash del token real. Crear dos tokens con los mismos parámetros
        en el mismo milisegundo produce JWTs idénticos (mismo iat/exp/jti),
        así que sus hashes también coinciden: no sirve para simular manipulación.
        """
        jti = "jti-manipulado-002"
        familia = "familia-002"

        # Token real que el cliente envía
        rt = auth.crear_token_refresh("pepe", jti, familia)

        # En BD guardamos un hash claramente falso: no coincidirá con ningún token real
        hash_falso_en_bd = "a" * 64

        sesion = _make_sesion(
            jti=jti,
            familia_id=familia,
            token_hash=hash_falso_en_bd,  # no coincide con hash de rt
            revocada_en=None,
        )

        # El servicio ejecuta: SELECT sesion → UPDATE revocar familia
        db = AsyncMock()
        db.execute = AsyncMock(side_effect=[
            MagicMock(scalar_one_or_none=MagicMock(return_value=sesion)),
            MagicMock(),  # _revocar_familia_refresh (UPDATE)
        ])
        db.commit = AsyncMock()

        with pytest.raises(HTTPException) as exc:
            await access_service.refrescar_sesion(db, rt)

        assert exc.value.status_code == 401
        assert db.commit.called  # se revocó la familia

    @pytest.mark.asyncio
    async def test_sesion_no_encontrada_en_bd_lanza_401(self):
        """
        Si el JTI no existe en BD (token completamente desconocido), 401 limpio.
        """
        jti = "jti-inexistente-003"
        familia = "familia-003"
        rt = auth.crear_token_refresh("pepe", jti, familia)

        db = _make_db(sesion_resultado=None)  # BD no devuelve nada

        with pytest.raises(HTTPException) as exc:
            await access_service.refrescar_sesion(db, rt)

        assert exc.value.status_code == 401

    @pytest.mark.asyncio
    async def test_sesion_expirada_en_bd_lanza_401(self):
        """
        Aunque el JWT todavía sea válido (exp futuro), si la sesión
        en BD tiene expira_en en el pasado, se rechaza.
        """
        jti = "jti-expirado-004"
        familia = "familia-004"
        rt = auth.crear_token_refresh("pepe", jti, familia)
        rt_hash = access_service._hash_refresh_token(rt)

        sesion = _make_sesion(
            jti=jti,
            familia_id=familia,
            token_hash=rt_hash,
            revocada_en=None,
            expira_en=_ahora() - timedelta(days=1),  # expirada ayer
        )
        db = _make_db(sesion_resultado=sesion)

        with pytest.raises(HTTPException) as exc:
            await access_service.refrescar_sesion(db, rt)

        assert exc.value.status_code == 401
        assert "expirado" in exc.value.detail.lower()

    @pytest.mark.asyncio
    async def test_token_jwt_invalido_lanza_401_antes_de_consultar_bd(self):
        """
        Un token JWT con firma incorrecta se rechaza antes de tocar la BD.
        Verifica que el orden de validación sea correcto.
        """
        db = AsyncMock()

        with pytest.raises(HTTPException) as exc:
            await access_service.refrescar_sesion(db, "token.malformado.jwt")

        assert exc.value.status_code == 401
        # No debería haber consultado la BD en absoluto
        db.execute.assert_not_called()

    @pytest.mark.asyncio
    async def test_rotacion_exitosa_devuelve_nuevos_tokens(self):
        """
        Flujo feliz: token válido, sesión activa → nuevos tokens emitidos,
        sesión antigua marcada como revocada.
        """
        jti = "jti-valido-005"
        familia = "familia-005"
        rt = auth.crear_token_refresh("pepe", jti, familia)
        rt_hash = access_service._hash_refresh_token(rt)

        sesion = _make_sesion(
            jti=jti,
            familia_id=familia,
            token_hash=rt_hash,
            revocada_en=None,
        )
        usuario = _make_usuario("pepe")
        db = _make_db(sesion_resultado=sesion, usuario_resultado=usuario)

        # Orden real de ejecución en refrescar_sesion:
        #   1. SELECT SesionRefresh WHERE jti=... FOR UPDATE
        #   2. SELECT Usuario WHERE id=...
        #   3. DELETE _limpiar_sesiones_refresh_usuario
        db.execute = AsyncMock(side_effect=[
            MagicMock(scalar_one_or_none=MagicMock(return_value=sesion)),   # 1: sesion
            MagicMock(scalar_one_or_none=MagicMock(return_value=usuario)),  # 2: usuario
            MagicMock(),  # 3: DELETE limpiar sesiones antiguas
        ])

        resultado = await access_service.refrescar_sesion(db, rt)

        assert resultado["estatus"] == "success"
        assert resultado["nombre_usuario"] == "pepe"
        assert "token_acceso" in resultado
        assert "refresh_token" in resultado
        # El nuevo refresh token debe ser distinto al original
        assert resultado["refresh_token"] != rt


# ─────────────────────────────────────────────
# Tests: cerrar_sesion (logout)
# ─────────────────────────────────────────────

class TestCerrarSesion:

    @pytest.mark.asyncio
    async def test_logout_normal_revoca_sesion(self):
        """Logout con token válido y sesión activa: revoca correctamente."""
        jti = "jti-logout-001"
        familia = "familia-logout-001"
        rt = auth.crear_token_refresh("pepe", jti, familia)
        rt_hash = access_service._hash_refresh_token(rt)

        sesion = _make_sesion(
            jti=jti,
            familia_id=familia,
            token_hash=rt_hash,
            revocada_en=None,
        )

        db = AsyncMock()
        db.execute = AsyncMock(return_value=MagicMock(
            scalar_one_or_none=MagicMock(return_value=sesion)
        ))
        db.commit = AsyncMock()

        resultado = await access_service.cerrar_sesion(db, rt)

        assert resultado["estatus"] == "success"
        # La sesión debe quedar con revocada_en seteado
        assert sesion.revocada_en is not None
        db.commit.assert_called_once()

    @pytest.mark.asyncio
    async def test_logout_idempotente_sesion_ya_revocada(self):
        """
        Logout con token ya revocado: debe devolver success sin fallar.
        El cliente podría llamar logout dos veces (reconexión, crash, etc.).
        """
        jti = "jti-logout-002"
        familia = "familia-logout-002"
        rt = auth.crear_token_refresh("pepe", jti, familia)
        rt_hash = access_service._hash_refresh_token(rt)

        sesion = _make_sesion(
            jti=jti,
            familia_id=familia,
            token_hash=rt_hash,
            revocada_en=_ahora() - timedelta(hours=1),  # ya revocada
        )

        db = AsyncMock()
        db.execute = AsyncMock(return_value=MagicMock(
            scalar_one_or_none=MagicMock(return_value=sesion)
        ))
        db.commit = AsyncMock()

        resultado = await access_service.cerrar_sesion(db, rt)

        assert resultado["estatus"] == "success"
        # No debe haber hecho commit (ya estaba revocada)
        db.commit.assert_not_called()

    @pytest.mark.asyncio
    async def test_logout_con_token_jwt_invalido_responde_success(self):
        """
        Un token completamente inválido en logout debe responder success
        (idempotencia: no revelamos información sobre el estado).
        """
        db = AsyncMock()

        resultado = await access_service.cerrar_sesion(db, "token.invalido.jwt")

        assert resultado["estatus"] == "success"
        db.execute.assert_not_called()

    @pytest.mark.asyncio
    async def test_logout_sesion_no_encontrada_responde_success(self):
        """JTI válido pero no existe en BD → success igualmente."""
        jti = "jti-logout-003"
        familia = "familia-logout-003"
        rt = auth.crear_token_refresh("pepe", jti, familia)

        db = AsyncMock()
        db.execute = AsyncMock(return_value=MagicMock(
            scalar_one_or_none=MagicMock(return_value=None)
        ))

        resultado = await access_service.cerrar_sesion(db, rt)

        assert resultado["estatus"] == "success"


# ─────────────────────────────────────────────
# Tests: funciones de hash (unitarias puras)
# ─────────────────────────────────────────────

class TestFuncionesHash:
    def test_hash_refresh_es_determinista(self):
        """El mismo token siempre produce el mismo hash."""
        rt = auth.crear_token_refresh("pepe", "jti-hash-001", "fam-001")
        h1 = access_service._hash_refresh_token(rt)
        h2 = access_service._hash_refresh_token(rt)
        assert h1 == h2

    def test_hash_refresh_diferente_para_tokens_distintos(self):
        rt1 = auth.crear_token_refresh("pepe", "jti-1", "fam-1")
        rt2 = auth.crear_token_refresh("pepe", "jti-2", "fam-1")
        assert access_service._hash_refresh_token(rt1) != access_service._hash_refresh_token(rt2)

    def test_hash_refresh_longitud_sha256(self):
        """SHA-256 en hex son siempre 64 caracteres."""
        rt = auth.crear_token_refresh("pepe", "jti-hash-002", "fam-002")
        h = access_service._hash_refresh_token(rt)
        assert len(h) == 64

    def test_hash_codigo_recuperacion_es_determinista(self):
        h1 = access_service._hash_codigo_recuperacion("123456")
        h2 = access_service._hash_codigo_recuperacion("123456")
        assert h1 == h2

    def test_hash_codigo_recuperacion_diferente_por_codigo(self):
        h1 = access_service._hash_codigo_recuperacion("123456")
        h2 = access_service._hash_codigo_recuperacion("654321")
        assert h1 != h2