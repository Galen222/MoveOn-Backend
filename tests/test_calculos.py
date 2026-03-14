# tests/test_calculos.py
#
# Tests unitarios para utils/calculos.py.
# La lógica es simple (1000m = 1 punto) pero es la base del ranking,
# así que cualquier cambio accidental aquí rompe la competición entera.

from utils import calculos


class TestCalcularPuntosNivel:
    def test_cero_metros_da_cero_puntos(self):
        assert calculos.calcular_puntos_nivel(0) == 0

    def test_metros_negativos_da_cero_puntos(self):
        # Caso defensivo: el servicio usa CASE para evitar negativos,
        # pero la función de cálculo también debe ser robusta.
        assert calculos.calcular_puntos_nivel(-500) == 0

    def test_none_da_cero_puntos(self):
        # Puede llegar None si el campo DB devuelve NULL
        assert calculos.calcular_puntos_nivel(None) == 0  # type: ignore[arg-type]

    def test_menos_de_un_kilometro_da_cero_puntos(self):
        assert calculos.calcular_puntos_nivel(999) == 0

    def test_exactamente_un_kilometro_da_un_punto(self):
        assert calculos.calcular_puntos_nivel(1_000) == 1

    def test_kilometro_y_medio_da_un_punto(self):
        # División entera: 1500 // 1000 = 1
        assert calculos.calcular_puntos_nivel(1_500) == 1

    def test_diez_kilometros_da_diez_puntos(self):
        assert calculos.calcular_puntos_nivel(10_000) == 10

    def test_maraton_completo(self):
        # 42.195 km → 42 puntos
        assert calculos.calcular_puntos_nivel(42_195) == 42

    def test_valor_grande_no_desborda(self):
        # Un usuario muy activo con 10.000 km
        assert calculos.calcular_puntos_nivel(10_000_000) == 10_000
