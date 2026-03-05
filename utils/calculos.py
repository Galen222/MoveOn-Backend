# Utils/calculos.py

def calcular_puntos_nivel(metros: int) -> int:
    """
    Centraliza la lógica de conversión de metros a puntos.
    Regla actual: 1000 metros = 1 punto.
    """
    if not metros or metros < 0:
        return 0
    return metros // 1000
