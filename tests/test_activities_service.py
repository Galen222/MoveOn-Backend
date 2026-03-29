from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException

import schemas
from schemas import TipoActividad
from services import activities_service


def _ahora() -> datetime:
    return datetime.now(timezone.utc)


def _make_usuario(id: int = 1, total_metros: int = 0, total_calorias: int = 0) -> MagicMock:
    usuario = MagicMock()
    usuario.id = id
    usuario.total_metros = total_metros
    usuario.total_calorias = total_calorias
    return usuario


def _make_datos() -> schemas.GuardarActividad:
    return schemas.GuardarActividad(
        tipo=TipoActividad.CORRER,
        distancia=5000,
        duracion_total=1800,
        duracion_movimiento=1680,
        duracion_parado=120,
        duracion_pausa_manual=60,
        calorias_quemadas=300,
        ritmo_medio_movimiento=336,
        ritmo_medio_total=360,
        ritmo_maximo=290,
        velocidad_media_x100=1071,
        velocidad_max_x100=1840,
        auto_pausas=1,
        pausas_manuales=1,
        alertas_velocidad=0,
        ruta_mapa_url=None,
        fecha_ruta=_ahora() - timedelta(minutes=5),
    )


def _mock_execute_one(resultado):
    return AsyncMock(return_value=MagicMock(scalar_one_or_none=MagicMock(return_value=resultado)))


class TestCrearActividad:
    @pytest.mark.asyncio
    async def test_usuario_no_encontrado_lanza_404(self):
        db = AsyncMock()
        db.execute = _mock_execute_one(None)
        with pytest.raises(HTTPException):
            await activities_service.crear_actividad(db, 999, _make_datos())

    @pytest.mark.asyncio
    async def test_persiste_metricas_enriquecidas(self):
        usuario = _make_usuario(total_metros=1000, total_calorias=50)
        db = AsyncMock()
        db.execute = _mock_execute_one(usuario)
        db.add = MagicMock()
        db.commit = AsyncMock()
        db.refresh = AsyncMock()

        with patch('services.activities_service.calculos.calcular_puntos_nivel', return_value=15):
            resultado = await activities_service.crear_actividad(db, 1, _make_datos())

        actividad = db.add.call_args[0][0]
        assert actividad.duracion_total == 1800
        assert actividad.duracion_movimiento == 1680
        assert actividad.duracion_parado == 120
        assert actividad.ritmo_medio_movimiento == 336
        assert actividad.ritmo_medio_total == 360
        assert actividad.ritmo_maximo == 290
        assert resultado['velocidad_max_x100'] == 1840
        assert resultado['ritmo_maximo'] == 290
        assert resultado['nuevo_total_puntos'] == 15
        assert usuario.total_metros == 6000
        assert usuario.total_calorias == 350
