#
# Tests para services/activities_service.py.
# Cubre la lógica de negocio de actividades: crear, obtener, eliminar unitaria
# y borrado masivo con reset de total_metros.
#
# Estrategia de mock:
# - db.execute devuelve resultados distintos en cada llamada via side_effect.
# - db.refresh es un AsyncMock que puede ajustar atributos del objeto.
# - calculos.calcular_puntos_nivel se parchea en tests donde el resultado
#   de db.refresh no puede poblar total_metros (expression de SQLAlchemy).

from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException

import schemas
from schemas import TipoActividad
from services import activities_service


# ─────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────

def _ahora() -> datetime:
    return datetime.now(timezone.utc)


def _make_usuario(nombre: str = "pepe", id: int = 1, total_metros: int = 0) -> MagicMock:
    u = MagicMock()
    u.id = id
    u.nombre_usuario = nombre
    u.total_metros = total_metros
    return u


def _make_actividad(
    id: int = 1,
    distancia: int = 5000,
    duracion: int = 1800,
    calorias: int = 300,
    usuario_id: int = 1,
) -> MagicMock:
    a = MagicMock()
    a.id = id
    a.distancia = distancia
    a.duracion = duracion
    a.calorias_quemadas = calorias
    a.usuario_id = usuario_id
    a.tipo = "Correr"
    a.ruta_polilinea = None
    a.ruta_mapa_url = None
    a.fecha_ruta = _ahora()
    return a


def _make_datos_actividad(distancia: int = 5000) -> schemas.GuardarActividad:
    return schemas.GuardarActividad(
        tipo=TipoActividad.CORRER,
        distancia=distancia,
        duracion=1800,
        calorias_quemadas=300,
        ruta_mapa_url=None,
        fecha_ruta=_ahora() - timedelta(minutes=5),
    )


def _mock_execute_one(resultado):
    """db.execute que devuelve scalar_one_or_none con un valor fijo."""
    return AsyncMock(
        return_value=MagicMock(scalar_one_or_none=MagicMock(return_value=resultado))
    )


def _mock_execute_seq(*resultados):
    """
    db.execute con side_effect: cada llamada devuelve el siguiente resultado.
    Cada item en resultados debe ser (tipo, valor):
      - ("one", obj)  → scalar_one_or_none = obj
      - ("count", n)  → scalar_one = n
      - ("none", None) → ejecuta sin retorno útil (DELETE, UPDATE)
    """
    side = []
    for tipo, valor in resultados:
        mock = MagicMock()
        if tipo == "one":
            mock.scalar_one_or_none.return_value = valor
        elif tipo == "count":
            mock.scalar_one.return_value = valor
        side.append(mock)
    return AsyncMock(side_effect=side)


# ─────────────────────────────────────────────
# crear_actividad
# ─────────────────────────────────────────────

class TestCrearActividad:
    @pytest.mark.asyncio
    async def test_usuario_no_encontrado_lanza_404(self):
        db = AsyncMock()
        db.execute = _mock_execute_one(None)

        with pytest.raises(HTTPException) as exc:
            await activities_service.crear_actividad(db, "fantasma", _make_datos_actividad())

        assert exc.value.status_code == 404
        assert "usuario" in exc.value.detail.lower()

    @pytest.mark.asyncio
    async def test_usuario_encontrado_hace_add_y_commit(self):
        usuario = _make_usuario(total_metros=10_000)
        db = AsyncMock()
        db.execute = _mock_execute_one(usuario)
        db.add = MagicMock()
        db.commit = AsyncMock()
        db.refresh = AsyncMock()

        with patch("services.activities_service.calculos.calcular_puntos_nivel", return_value=15):
            await activities_service.crear_actividad(db, 1, _make_datos_actividad())

        db.add.assert_called_once()
        db.commit.assert_called_once()

    @pytest.mark.asyncio
    async def test_respuesta_tiene_campos_requeridos(self):
        usuario = _make_usuario(total_metros=5_000)
        db = AsyncMock()
        db.execute = _mock_execute_one(usuario)
        db.add = MagicMock()
        db.commit = AsyncMock()
        db.refresh = AsyncMock()

        with patch("services.activities_service.calculos.calcular_puntos_nivel", return_value=10):
            resultado = await activities_service.crear_actividad(db, 1, _make_datos_actividad())

        campos = {"tipo", "distancia", "duracion", "calorias_quemadas", "fecha_ruta", "nuevo_total_puntos"}
        for campo in campos:
            assert campo in resultado, f"Campo '{campo}' ausente en respuesta"

    @pytest.mark.asyncio
    async def test_nuevo_total_puntos_viene_de_calculos(self):
        usuario = _make_usuario(total_metros=10_000)
        db = AsyncMock()
        db.execute = _mock_execute_one(usuario)
        db.add = MagicMock()
        db.commit = AsyncMock()
        db.refresh = AsyncMock()

        with patch("services.activities_service.calculos.calcular_puntos_nivel", return_value=42) as mock_calc:
            resultado = await activities_service.crear_actividad(db, 1, _make_datos_actividad())

        assert resultado["nuevo_total_puntos"] == 42
        mock_calc.assert_called_once()

    @pytest.mark.asyncio
    async def test_distancia_de_datos_se_refleja_en_respuesta(self):
        usuario = _make_usuario()
        db = AsyncMock()
        db.execute = _mock_execute_one(usuario)
        db.add = MagicMock()
        db.commit = AsyncMock()
        db.refresh = AsyncMock()

        datos = _make_datos_actividad(distancia=12_500)
        with patch("services.activities_service.calculos.calcular_puntos_nivel", return_value=0):
            resultado = await activities_service.crear_actividad(db, 1, datos)

        assert resultado["distancia"] == 12_500


# ─────────────────────────────────────────────
# obtener_actividad
# ─────────────────────────────────────────────

class TestObtenerActividad:
    @pytest.mark.asyncio
    async def test_usuario_no_encontrado_lanza_404(self):
        db = AsyncMock()
        db.execute = _mock_execute_one(None)

        with pytest.raises(HTTPException) as exc:
            await activities_service.obtener_actividad(db, "fantasma", 1)
        assert exc.value.status_code == 404

    @pytest.mark.asyncio
    async def test_actividad_no_encontrada_lanza_404(self):
        usuario = _make_usuario()
        db = AsyncMock()
        db.execute = _mock_execute_seq(
            ("one", usuario),   # SELECT usuario
            ("one", None),      # SELECT actividad → no encontrada
        )

        with pytest.raises(HTTPException) as exc:
            await activities_service.obtener_actividad(db, 1, 999)
        assert exc.value.status_code == 404
        assert "actividad" in exc.value.detail.lower()

    @pytest.mark.asyncio
    async def test_devuelve_el_objeto_actividad(self):
        usuario = _make_usuario()
        actividad = _make_actividad(id=42)
        db = AsyncMock()
        db.execute = _mock_execute_seq(
            ("one", usuario),
            ("one", actividad),
        )

        resultado = await activities_service.obtener_actividad(db, 1, 42)
        assert resultado is actividad


# ─────────────────────────────────────────────
# obtener_actividades
# ─────────────────────────────────────────────

class TestObtenerActividades:
    @pytest.mark.asyncio
    async def test_devuelve_items_y_metadata(self):
        actividades = [_make_actividad(id=i) for i in range(3)]

        mock_result_total = MagicMock()
        mock_result_total.scalar_one.return_value = 3

        mock_result_items = MagicMock()
        mock_result_items.scalars.return_value.all.return_value = actividades

        db = AsyncMock()
        db.execute = AsyncMock(side_effect=[mock_result_total, mock_result_items])

        resultado = await activities_service.obtener_actividades(db, 1, skip=0, limit=2)

        assert resultado["items"] == actividades
        assert resultado["total"] == 3
        assert resultado["skip"] == 0
        assert resultado["limit"] == 2
        assert resultado["has_more"] is True

    @pytest.mark.asyncio
    async def test_lista_vacia_devuelve_metadata_correcta(self):
        mock_result_total = MagicMock()
        mock_result_total.scalar_one.return_value = 0

        mock_result_items = MagicMock()
        mock_result_items.scalars.return_value.all.return_value = []

        db = AsyncMock()
        db.execute = AsyncMock(side_effect=[mock_result_total, mock_result_items])

        resultado = await activities_service.obtener_actividades(db, 1, skip=0, limit=20)

        assert resultado == {
            "items": [],
            "total": 0,
            "skip": 0,
            "limit": 20,
            "has_more": False,
        }


# ─────────────────────────────────────────────
# eliminar_actividad
# ─────────────────────────────────────────────

class TestEliminarActividad:
    @pytest.mark.asyncio
    async def test_usuario_no_encontrado_lanza_404(self):
        db = AsyncMock()
        db.execute = _mock_execute_one(None)

        with pytest.raises(HTTPException) as exc:
            await activities_service.eliminar_actividad(db, "fantasma", 1)
        assert exc.value.status_code == 404

    @pytest.mark.asyncio
    async def test_actividad_no_encontrada_lanza_404(self):
        usuario = _make_usuario()
        db = AsyncMock()
        db.execute = _mock_execute_seq(
            ("one", usuario),
            ("one", None),
        )

        with pytest.raises(HTTPException) as exc:
            await activities_service.eliminar_actividad(db, 1, 999)
        assert exc.value.status_code == 404

    @pytest.mark.asyncio
    async def test_elimina_la_actividad_y_hace_commit(self):
        usuario = _make_usuario(total_metros=10_000)
        actividad = _make_actividad(distancia=5_000)
        db = AsyncMock()
        db.execute = _mock_execute_seq(
            ("one", usuario),
            ("one", actividad),
        )
        db.delete = AsyncMock()
        db.commit = AsyncMock()
        db.refresh = AsyncMock()

        with patch("services.activities_service.calculos.calcular_puntos_nivel", return_value=5):
            await activities_service.eliminar_actividad(db, 1, 1)

        db.delete.assert_called_once_with(actividad)
        db.commit.assert_called_once()

    @pytest.mark.asyncio
    async def test_respuesta_incluye_estatus_y_nuevos_puntos(self):
        usuario = _make_usuario(total_metros=10_000)
        actividad = _make_actividad(distancia=5_000)
        db = AsyncMock()
        db.execute = _mock_execute_seq(
            ("one", usuario),
            ("one", actividad),
        )
        db.delete = AsyncMock()
        db.commit = AsyncMock()
        db.refresh = AsyncMock()

        with patch("services.activities_service.calculos.calcular_puntos_nivel", return_value=5):
            resultado = await activities_service.eliminar_actividad(db, 1, 1)

        assert resultado["estatus"] == "success"
        assert resultado["nuevo_total_puntos"] == 5


# ─────────────────────────────────────────────
# eliminar_actividades (borrado masivo)
# ─────────────────────────────────────────────

class TestEliminarActividades:
    @pytest.mark.asyncio
    async def test_usuario_no_encontrado_lanza_404(self):
        db = AsyncMock()
        db.execute = _mock_execute_one(None)

        with pytest.raises(HTTPException) as exc:
            await activities_service.eliminar_actividades(db, "fantasma")
        assert exc.value.status_code == 404

    @pytest.mark.asyncio
    async def test_resetea_total_metros_a_cero(self):
        usuario = _make_usuario(total_metros=50_000)
        db = AsyncMock()
        db.execute = _mock_execute_seq(
            ("one", usuario),    # SELECT usuario
            ("count", 3),        # SELECT count(*)
            ("none", None),      # DELETE actividades
        )
        db.commit = AsyncMock()

        await activities_service.eliminar_actividades(db, 1)

        assert usuario.total_metros == 0

    @pytest.mark.asyncio
    async def test_hace_commit_tras_borrado(self):
        usuario = _make_usuario()
        db = AsyncMock()
        db.execute = _mock_execute_seq(
            ("one", usuario),
            ("count", 0),
            ("none", None),
        )
        db.commit = AsyncMock()

        await activities_service.eliminar_actividades(db, 1)
        db.commit.assert_called_once()

    @pytest.mark.asyncio
    async def test_mensaje_incluye_numero_de_actividades_borradas(self):
        usuario = _make_usuario()
        db = AsyncMock()
        db.execute = _mock_execute_seq(
            ("one", usuario),
            ("count", 7),    # siete actividades
            ("none", None),
        )
        db.commit = AsyncMock()

        resultado = await activities_service.eliminar_actividades(db, 1)

        assert resultado["estatus"] == "success"
        assert "7" in resultado["mensaje"]

    @pytest.mark.asyncio
    async def test_usuario_sin_actividades_devuelve_cero_borradas(self):
        usuario = _make_usuario(total_metros=0)
        db = AsyncMock()
        db.execute = _mock_execute_seq(
            ("one", usuario),
            ("count", 0),
            ("none", None),
        )
        db.commit = AsyncMock()

        resultado = await activities_service.eliminar_actividades(db, 1)
        assert "0" in resultado["mensaje"]
