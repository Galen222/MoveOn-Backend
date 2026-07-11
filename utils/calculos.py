# utils/calculos.py

"""Incluye utilidades auxiliares de la aplicación."""


def calcular_puntos_nivel(metros: int) -> int:
    """
    Centraliza la lógica de conversión de metros a puntos.
    Regla actual: 1000 metros = 1 punto.
    """
    if not metros or metros < 0:
        return 0
    return metros // 1000


def resolver_ritmo_maximo(
    ritmo_maximo: int,
    ritmo_medio_movimiento: int,
    velocidad_max_x100: int,
    tipo: object,
) -> int:
    """Devuelve un ritmo máximo válido o lo deriva de métricas persistibles.

    El móvil intenta calcular un mejor ritmo sostenido. Cuando una versión antigua,
    una sesión muy corta o una restauración del servicio envía ``0``, el backend
    reconstruye un valor prudente usando la velocidad máxima y acotándolo respecto
    al ritmo medio para no convertir un pico GPS aislado en un récord imposible.
    """
    ritmo_maximo = int(ritmo_maximo or 0)
    if ritmo_maximo > 0:
        return ritmo_maximo

    ritmo_medio_movimiento = int(ritmo_medio_movimiento or 0)
    velocidad_max_x100 = int(velocidad_max_x100 or 0)
    if ritmo_medio_movimiento <= 0 or velocidad_max_x100 <= 0:
        return 0

    velocidad_max_kmh = velocidad_max_x100 / 100.0
    pace_desde_velocidad_max = int(round(3600.0 / velocidad_max_kmh))

    tipo_valor = getattr(tipo, "value", tipo)
    es_correr = tipo_valor == "Correr"
    mejora_maxima = 60 if es_correr else 90
    ratio_minimo = 0.72 if es_correr else 0.80
    margen_minimo = 15 if es_correr else 10

    suelo = max(
        int(round(ritmo_medio_movimiento * ratio_minimo)),
        ritmo_medio_movimiento - mejora_maxima,
    )
    techo = max(1, ritmo_medio_movimiento - margen_minimo)
    candidato = min(pace_desde_velocidad_max, techo)

    return max(60, min(1800, max(suelo, candidato)))
