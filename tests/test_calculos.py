# tests/test_calculos.py

"""Comprueba las utilidades de cálculo derivadas del dominio de actividad.

Se centra en los puntos de nivel para asegurar que la gamificación mantiene
la progresión esperada ante cambios futuros.
"""

# Pruebas unitarias para utils/calculos.py.
# La lógica es simple (1000m = 1 punto) pero es la base del ranking,
# así que cualquier cambio accidental aquí rompe la competición entera.

from utils import calculos


class TestCalcularPuntosNivel:
    """Agrupa pruebas relacionadas con calcular puntos nivel."""

    def test_cero_metros_da_cero_puntos(self):
        """Verifica que cero metros da cero puntos."""
        assert calculos.calcular_puntos_nivel(0) == 0

    def test_metros_negativos_da_cero_puntos(self):
        # Caso defensivo: el servicio usa CASE para evitar negativos,
        # pero la función de cálculo también debe ser robusta.
        """Verifica que metros negativos da cero puntos."""
        assert calculos.calcular_puntos_nivel(-500) == 0

    def test_none_da_cero_puntos(self):
        # Puede llegar None si el campo DB devuelve NULL
        """Verifica que none da cero puntos."""
        assert calculos.calcular_puntos_nivel(None) == 0  # type: ignore[arg-type]

    def test_menos_de_un_kilometro_da_cero_puntos(self):
        """Verifica que menos de un kilometro da cero puntos."""
        assert calculos.calcular_puntos_nivel(999) == 0

    def test_exactamente_un_kilometro_da_un_punto(self):
        """Verifica que exactamente un kilometro da un punto."""
        assert calculos.calcular_puntos_nivel(1_000) == 1

    def test_kilometro_y_medio_da_un_punto(self):
        # División entera: 1500 // 1000 = 1
        """Verifica que kilometro y medio da un punto."""
        assert calculos.calcular_puntos_nivel(1_500) == 1

    def test_diez_kilometros_da_diez_puntos(self):
        """Verifica que diez kilometros da diez puntos."""
        assert calculos.calcular_puntos_nivel(10_000) == 10

    def test_maraton_completo(self):
        # 42.195 km → 42 puntos
        """Verifica que maraton completo."""
        assert calculos.calcular_puntos_nivel(42_195) == 42

    def test_valor_grande_no_desborda(self):
        # Un usuario muy activo con 10.000 km
        """Verifica que valor grande no desborda."""
        assert calculos.calcular_puntos_nivel(10_000_000) == 10_000
