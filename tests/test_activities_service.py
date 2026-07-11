# tests/test_activities_service.py

"""Ejercita el alta de actividades y la actualización de agregados del usuario.

Las pruebas validan idempotencia, persistencia de métricas y manejo de
errores en el servicio que registra actividades cerradas.
"""

from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException

import schemas
from schemas import TipoActividad
from services import activities_service


def _ahora() -> datetime:
    """Devuelve la fecha y hora actual."""
    return datetime.now(timezone.utc)


def _make_usuario(
    id: int = 1, total_metros: int = 0, total_calorias: int = 0
) -> MagicMock:
    """Construye un usuario simulado."""
    usuario = MagicMock()
    usuario.id = id
    usuario.total_metros = total_metros
    usuario.total_calorias = total_calorias
    return usuario


def _make_datos() -> schemas.GuardarActividad:
    """Construye datos."""
    return schemas.GuardarActividad(
        client_local_id="test-local-id",
        tipo=TipoActividad.CORRER,
        distancia=5000,
        duracion_total=1800,
        duracion_movimiento=1680,
        duracion_parado=120,
        duracion_pausa_manual=60,
        calorias_quemadas=300,
        pasos=4321,
        ritmo_medio_movimiento=336,
        ritmo_medio_total=360,
        ritmo_maximo=290,
        velocidad_media_x100=1071,
        velocidad_max_x100=1840,
        auto_pausas=1,
        pausas_manuales=1,
        alertas_velocidad=0,
        ruta_polilinea=None,
        ruta_mapa_url=None,
        fecha_ruta=_ahora() - timedelta(minutes=5),
    )


def _mock_execute_one(resultado):
    """Crea un simulacro de execute one."""
    return AsyncMock(
        return_value=MagicMock(scalar_one_or_none=MagicMock(return_value=resultado))
    )


class TestCrearActividad:
    """Agrupa pruebas relacionadas con crear actividad."""

    @pytest.mark.asyncio
    async def test_usuario_no_encontrado_lanza_404(self):
        """Verifica que usuario no encontrado lanza 404."""
        db = AsyncMock()
        db.execute = _mock_execute_one(None)
        with pytest.raises(HTTPException):
            await activities_service.crear_actividad(db, 999, _make_datos())

    @pytest.mark.asyncio
    async def test_reutiliza_actividad_existente_por_client_local_id(self):
        """Verifica que reutiliza una actividad existente por client local id."""
        usuario = _make_usuario(total_metros=1000, total_calorias=50)
        usuario.total_duracion_segundos = 600
        usuario.total_actividades = 1

        actividad_existente = MagicMock()
        actividad_existente.id = 7
        actividad_existente.tipo = "Correr"
        actividad_existente.distancia = 5000
        actividad_existente.duracion_total = 1800
        actividad_existente.duracion_movimiento = 1680
        actividad_existente.duracion_parado = 120
        actividad_existente.duracion_pausa_manual = 60
        actividad_existente.calorias_quemadas = 300
        actividad_existente.pasos = 4321
        actividad_existente.ritmo_medio_movimiento = 336
        actividad_existente.ritmo_medio_total = 360
        actividad_existente.ritmo_maximo = 290
        actividad_existente.velocidad_media_x100 = 1071
        actividad_existente.velocidad_max_x100 = 1840
        actividad_existente.auto_pausas = 1
        actividad_existente.pausas_manuales = 1
        actividad_existente.alertas_velocidad = 0
        actividad_existente.ruta_polilinea = None
        actividad_existente.ruta_mapa_url = None
        actividad_existente.fecha_ruta = _ahora() - timedelta(minutes=5)

        execute_results = [
            MagicMock(scalar_one_or_none=MagicMock(return_value=usuario)),
            MagicMock(scalar_one_or_none=MagicMock(return_value=actividad_existente)),
        ]

        db = AsyncMock()
        db.execute = AsyncMock(side_effect=execute_results)
        db.add = MagicMock()
        db.commit = AsyncMock()
        db.refresh = AsyncMock()

        datos = _make_datos().model_copy(update={"client_local_id": "local-123"})

        with patch(
            "services.activities_service.calculos.calcular_puntos_nivel",
            return_value=15,
        ):
            resultado = await activities_service.crear_actividad(db, 1, datos)

        assert resultado["id"] == 7
        assert resultado["nuevo_total_puntos"] == 15
        db.add.assert_not_called()
        db.commit.assert_not_called()
        assert usuario.total_metros == 1000
        assert usuario.total_calorias == 50

    @pytest.mark.asyncio
    async def test_persiste_metricas_enriquecidas(self):
        """Verifica que persiste metricas enriquecidas."""
        # Verifica que persiste metricas enriquecidas.
        usuario = _make_usuario(total_metros=1000, total_calorias=50)
        db = AsyncMock()
        db.execute = AsyncMock(
            side_effect=[
                MagicMock(scalar_one_or_none=MagicMock(return_value=usuario)),
                MagicMock(scalar_one_or_none=MagicMock(return_value=None)),
            ]
        )
        db.add = MagicMock()
        db.commit = AsyncMock()
        db.refresh = AsyncMock()

        with patch(
            "services.activities_service.calculos.calcular_puntos_nivel",
            return_value=15,
        ):
            resultado = await activities_service.crear_actividad(db, 1, _make_datos())

        actividad = db.add.call_args[0][0]
        assert actividad.duracion_total == 1800
        assert actividad.duracion_movimiento == 1680
        assert actividad.duracion_parado == 120
        assert actividad.pasos == 4321
        assert actividad.ritmo_medio_movimiento == 336
        assert actividad.ritmo_medio_total == 360
        assert actividad.ritmo_maximo == 290
        assert resultado["velocidad_max_x100"] == 1840
        assert resultado["ritmo_maximo"] == 290
        assert resultado["pasos"] == 4321
        assert resultado["nuevo_total_puntos"] == 15
        assert usuario.total_metros == 6000
        assert usuario.total_calorias == 350
