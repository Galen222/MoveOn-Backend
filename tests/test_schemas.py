from datetime import datetime, timedelta, timezone

import pytest
from pydantic import ValidationError

import schemas
from schemas import TipoActividad


def _ahora():
    return datetime.now(timezone.utc)


def _payload(**kwargs):
    base = {
        "tipo": TipoActividad.CORRER,
        "distancia": 5000,
        "duracion_total": 1800,
        "duracion_movimiento": 1680,
        "duracion_parado": 120,
        "duracion_pausa_manual": 60,
        "calorias_quemadas": 350,
        "ritmo_medio_movimiento": 336,
        "ritmo_medio_total": 360,
        "velocidad_media_x100": 1071,
        "velocidad_max_x100": 1840,
        "auto_pausas": 1,
        "pausas_manuales": 1,
        "alertas_velocidad": 0,
        "fecha_ruta": _ahora() - timedelta(minutes=10),
    }
    base.update(kwargs)
    return base


class TestGuardarActividadSchema:
    def test_payload_valido(self):
        data = schemas.GuardarActividad(**_payload())
        assert data.duracion_total == 1800
        assert data.duracion_movimiento == 1680
        assert data.duracion_parado == 120

    def test_duracion_breakdown_invalido(self):
        with pytest.raises(
            ValidationError,
            match="La suma de duración en movimiento y parada debe coincidir con la duración total",
        ):
            schemas.GuardarActividad(**_payload(duracion_parado=100))

    def test_velocidad_max_no_puede_ser_menor_que_media(self):
        with pytest.raises(
            ValidationError,
            match="La velocidad máxima no puede ser menor que la velocidad media",
        ):
            schemas.GuardarActividad(
                **_payload(velocidad_media_x100=1200, velocidad_max_x100=1100)
            )

    def test_ritmo_medio_movimiento_es_obligatorio_si_hay_movimiento(self):
        with pytest.raises(
            ValidationError,
            match="Falta el ritmo medio en movimiento",
        ):
            schemas.GuardarActividad(**_payload(ritmo_medio_movimiento=0))

    def test_fecha_futura_invalida(self):
        with pytest.raises(
            ValidationError,
            match="La fecha de la actividad no puede ser en el futuro",
        ):
            schemas.GuardarActividad(**_payload(fecha_ruta=_ahora() + timedelta(days=1)))
