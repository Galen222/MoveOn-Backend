# utils/validators.py

"""Incluye utilidades auxiliares de la aplicación."""

import re
from datetime import date, datetime, timedelta, timezone
from typing import Any, Optional

from exceptions import AppValidationError


def interceptar_error_pydantic(
    valor: Any, handler, error_code: str, mensaje_error: str
):
    """
    Ejecuta el validador por defecto de Pydantic (handler).
    Si falla, lanza un AppValidationError con mensaje limpio y error_code explícito.
    """
    try:
        return handler(valor)
    except Exception:
        raise AppValidationError(mensaje_error, error_code)


# Funciones de lógica de validación


def validar_nombre_real_logica(v: str) -> str:
    """Valida un nombre real respetando longitudes mínimas/máximas y caracteres.

    Permite letras latinas (incluyendo acentos, ``ñ``, ``ü``), espacios,
    apóstrofes y guiones, pero rechaza números y cualquier símbolo,
    para evitar que el campo se use como canal de comentarios.

    Args:
        v: nombre real tal como llega del cliente.

    Returns:
        El mismo valor recibido si pasa todas las comprobaciones.

    Raises:
        AppValidationError: ``REAL_NAME_TOO_SHORT`` si tiene menos de 3 caracteres.
        AppValidationError: ``REAL_NAME_TOO_LONG`` si supera los 80 caracteres.
        AppValidationError: ``REAL_NAME_INVALID_CHARACTERS`` si contiene dígitos o símbolos no permitidos.
    """
    if len(v) < 3:
        raise AppValidationError(
            "Error: El nombre real es demasiado corto", "REAL_NAME_TOO_SHORT"
        )

    # Límite superior para evitar carga útils absurdamente grandes
    if len(v) > 80:
        raise AppValidationError(
            "Error: El nombre real no puede superar los 80 caracteres",
            "REAL_NAME_TOO_LONG",
        )

    # Solo letras (incluye acentos/ñ/ü), espacios, apóstrofe y guion
    if not re.match(r"^[a-zA-ZáéíóúÁÉÍÓÚñÑüÜ\s'-]+$", v):
        raise AppValidationError(
            "Error: El nombre no puede contener números ni símbolos especiales",
            "REAL_NAME_INVALID_CHARACTERS",
        )

    return v


def validar_password_logica(v: str) -> str:
    """Valida los requisitos mínimos de fortaleza de contraseña.

    Exige al menos 8 caracteres, una mayúscula y un número. El tope de
    72 bytes en UTF-8 viene dado por bcrypt, que ignora silenciosamente
    todo lo que pase de ahí; fallar explícitamente aquí evita que el
    usuario crea tener una contraseña más larga de lo que realmente
    protege el hash.

    Args:
        v: contraseña en claro tal como la introdujo el usuario.

    Returns:
        La misma contraseña recibida si pasa todas las comprobaciones.

    Raises:
        AppValidationError: ``PASSWORD_TOO_SHORT`` si tiene menos de 8 caracteres.
        AppValidationError: ``PASSWORD_TOO_LONG_BYTES`` si supera 72 bytes en UTF-8.
        AppValidationError: ``PASSWORD_MISSING_UPPERCASE`` si no incluye ninguna mayúscula.
        AppValidationError: ``PASSWORD_MISSING_NUMBER`` si no incluye ningún dígito.
    """
    if len(v) < 8:
        raise AppValidationError(
            "Error: La contraseña debe tener al menos 8 caracteres",
            "PASSWORD_TOO_SHORT",
        )
    # bcrypt solo usa los primeros 72 bytes reales
    if len(v.encode("utf-8")) > 72:
        raise AppValidationError(
            "Error: La contraseña no puede superar los 72 bytes en UTF-8",
            "PASSWORD_TOO_LONG_BYTES",
        )
    if not any(char.isupper() for char in v):
        raise AppValidationError(
            "Error: La contraseña debe incluir al menos una letra mayúscula",
            "PASSWORD_MISSING_UPPERCASE",
        )
    if not any(char.isdigit() for char in v):
        raise AppValidationError(
            "Error: La contraseña debe incluir al menos un número",
            "PASSWORD_MISSING_NUMBER",
        )
    return v


def validar_fecha_nacimiento_logica(v: date) -> date:
    """Valida la fecha de nacimiento exigiendo edad mínima y no-futuro.

    La edad se calcula por comparación de ``(mes, día)`` para no
    tener errores de un día alrededor del cumpleaños. El umbral de 18
    años responde a la política legal del servicio.

    Args:
        v: fecha de nacimiento propuesta.

    Returns:
        La misma fecha recibida si pasa las comprobaciones.

    Raises:
        AppValidationError: ``BIRTH_DATE_IN_FUTURE`` si la fecha es posterior a hoy.
        AppValidationError: ``AGE_RESTRICTION_NOT_MET`` si el usuario tiene menos de 18 años.
    """
    hoy = date.today()
    if v > hoy:
        raise AppValidationError(
            "Error: La fecha de nacimiento no puede ser en el futuro",
            "BIRTH_DATE_IN_FUTURE",
        )
    edad = hoy.year - v.year - ((hoy.month, hoy.day) < (v.month, v.day))
    if edad < 18:
        raise AppValidationError(
            "Error: Debes tener al menos 18 años para registrarte",
            "AGE_RESTRICTION_NOT_MET",
        )
    return v


def validar_altura_logica(v: Optional[int]) -> Optional[int]:
    """Valida la altura en centímetros dentro de un rango humano razonable.

    Admite ``None`` (campo opcional en el perfil). El rango 50–300 cm
    es intencionadamente amplio: cubre casos de niños registrados por
    familias y evita rechazar valores legítimos por celo excesivo.

    Args:
        v: altura en centímetros, o ``None`` si no se quiere fijar.

    Returns:
        El mismo valor recibido.

    Raises:
        AppValidationError: ``HEIGHT_OUT_OF_RANGE`` si está fuera de [50, 300].
    """
    if v is None:
        return v
    if not (50 <= v <= 300):
        raise AppValidationError(
            "Error: La altura debe estar entre 50cm y 300cm", "HEIGHT_OUT_OF_RANGE"
        )
    return v


def validar_peso_logica(v: Optional[float]) -> Optional[float]:
    """Valida el peso en kilogramos dentro de un rango humano razonable.

    Admite ``None`` (campo opcional). El rango 20–300 kg permite
    registros amplios sin filtrar datos legítimos.

    Args:
        v: peso en kilogramos, o ``None`` si no se quiere fijar.

    Returns:
        El mismo valor recibido.

    Raises:
        AppValidationError: ``WEIGHT_OUT_OF_RANGE`` si está fuera de [20, 300].
    """
    if v is None:
        return v
    if not (20 <= v <= 300):
        raise AppValidationError(
            "Error: El peso debe estar entre 20kg y 300kg", "WEIGHT_OUT_OF_RANGE"
        )
    return v


def validar_fecha_ruta_logica(v: datetime) -> datetime:
    """Valida y normaliza la fecha/hora reportada para una actividad.

    Exige que la fecha incluya zona horaria (evita ambigüedades al
    mostrar actividades entre clientes con husos distintos) y admite
    hasta 10 minutos de desfase en el futuro para absorber diferencias
    de reloj entre dispositivo y servidor. La salida se normaliza
    siempre a UTC para que la base de datos guarde valores homogéneos.

    Args:
        v: ``datetime`` propuesto por el cliente, debe incluir ``tzinfo``.

    Returns:
        El mismo instante en UTC, o el propio valor si venía vacío.

    Raises:
        AppValidationError: ``ACTIVITY_DATE_MISSING_TIMEZONE`` si falta ``tzinfo``.
        AppValidationError: ``ACTIVITY_DATE_IN_FUTURE`` si supera el margen de +10 minutos.
    """
    if v:
        if v.tzinfo is None:
            raise AppValidationError(
                "Error: La fecha debe incluir zona horaria",
                "ACTIVITY_DATE_MISSING_TIMEZONE",
            )

        ahora = datetime.now(timezone.utc)

        # Normalizar v a UTC para comparar y almacenar siempre igual
        v_utc = v.astimezone(timezone.utc)

        margen = ahora + timedelta(minutes=10)
        if v_utc > margen:
            raise AppValidationError(
                "Error: La fecha de la actividad no puede ser en el futuro",
                "ACTIVITY_DATE_IN_FUTURE",
            )

        return v_utc

    return v


def validar_distancia_logica(v: int) -> int:
    """
    Nadie corre más de 300km en una sola sesión (Sanity Check).
    Debe ser positiva y máximo 300km.
    """
    # 300,000 metros = 300km.
    if v <= 0:
        raise AppValidationError(
            "Error: La distancia debe ser mayor a 0", "DISTANCE_MUST_BE_POSITIVE"
        )
    if v > 300000:
        raise AppValidationError(
            "Error: La distancia parece incorrecta (máximo 300km)",
            "DISTANCE_OUT_OF_RANGE",
        )
    return v


def validar_duracion_logica(v: int) -> int:
    """
    Una actividad no suele durar más de 24 horas seguidas.
    Debe ser positiva y máximo 24 horas.
    """
    # 86400 segundos = 24 horas.
    if v <= 0:
        raise AppValidationError(
            "Error: La duración debe ser mayor a 0", "DURATION_MUST_BE_POSITIVE"
        )
    if v > 86400:
        raise AppValidationError(
            "Error: La duración excede el límite de 24 horas", "DURATION_TOO_LONG"
        )
    return v


def validar_calorias_logica(v: int) -> int:
    """
    Quemar más de 10.000 calorías en una sesión es fisiológicamente improbable.
    Debe ser positiva y máximo 10.000.
    """
    if v <= 0:
        raise AppValidationError(
            "Error: Las calorías deben ser mayor a 0", "CALORIES_MUST_BE_POSITIVE"
        )
    if v > 10000:
        raise AppValidationError(
            "Error: Las calorías parecen incorrectas (máximo 10.000)",
            "CALORIES_OUT_OF_RANGE",
        )
    return v


def validar_polilinea_logica(v: str) -> str:
    """Valida que la polilínea codificada esté en un tamaño razonable.

    Admite ``None`` (actividades sin GPS grabado). Una cadena de menos
    de 5 caracteres no puede representar una ruta real y suele ser
    basura; más de 200 000 caracteres sugiere un cliente defectuoso o
    un intento de abuso de tamaño.

    Args:
        v: polilínea codificada o ``None`` si no hay ruta.

    Returns:
        El mismo valor recibido (``None`` si entró ``None``).

    Raises:
        AppValidationError: ``ROUTE_INVALID`` si la cadena tiene menos de 5 caracteres.
        AppValidationError: ``ROUTE_TOO_LARGE`` si supera 200 000 caracteres.
    """
    if v is None:
        return None
    if len(v) < 5:
        raise AppValidationError("Error: La ruta parece inválida", "ROUTE_INVALID")
    if len(v) > 200000:
        raise AppValidationError(
            "Error: La ruta supera el tamaño máximo permitido",
            "ROUTE_TOO_LARGE",
        )
    return v


def validar_duracion_no_negativa_logica(
    v: int, field_name: str, error_prefix: str
) -> int:
    """Valida una duración en segundos como no-negativa y con tope de 24 h.

    A diferencia de ``validar_duracion_logica``, admite ``0`` porque
    componentes como "duración parado" pueden legítimamente serlo.

    Args:
        v: duración en segundos.
        field_name: nombre humano del campo, usado en el mensaje de error.
        error_prefix: prefijo del ``error_code`` (se le añade ``_NEGATIVE`` o ``_TOO_LONG``).

    Returns:
        El mismo valor recibido si pasa las comprobaciones.

    Raises:
        AppValidationError: ``{error_prefix}_NEGATIVE`` si es negativa.
        AppValidationError: ``{error_prefix}_TOO_LONG`` si supera los 86 400 segundos.
    """
    if v < 0:
        raise AppValidationError(
            f"Error: {field_name} no puede ser negativa",
            f"{error_prefix}_NEGATIVE",
        )
    if v > 86400:
        raise AppValidationError(
            f"Error: {field_name} excede el límite de 24 horas",
            f"{error_prefix}_TOO_LONG",
        )
    return v


def validar_ritmo_segundos_km_logica(v: int, field_name: str, error_prefix: str) -> int:
    """Valida un ritmo expresado en segundos por kilómetro.

    El rango superior se fija en 3600 s/km (= 1 h/km). Más que eso
    sería andar muy lento y casi seguro un error del cliente al
    calcular el ritmo.

    Args:
        v: ritmo en segundos por kilómetro.
        field_name: nombre humano del campo, usado en el mensaje de error.
        error_prefix: prefijo del ``error_code``.

    Returns:
        El mismo valor recibido.

    Raises:
        AppValidationError: ``{error_prefix}_NEGATIVE`` si es negativo.
        AppValidationError: ``{error_prefix}_OUT_OF_RANGE`` si supera 3600.
    """
    if v < 0:
        raise AppValidationError(
            f"Error: {field_name} no puede ser negativo",
            f"{error_prefix}_NEGATIVE",
        )
    if v > 3600:
        raise AppValidationError(
            f"Error: {field_name} parece inválido",
            f"{error_prefix}_OUT_OF_RANGE",
        )
    return v


def validar_velocidad_x100_logica(v: int, field_name: str, error_prefix: str) -> int:
    """Valida una velocidad codificada como km/h multiplicado por 100.

    El cliente envía enteros para evitar floats (``13.45 km/h → 1345``).
    El tope 10 000 equivale a 100 km/h, más que suficiente para cualquier
    actividad registrable en la app.

    Args:
        v: velocidad en formato km/h × 100.
        field_name: nombre humano del campo, usado en el mensaje de error.
        error_prefix: prefijo del ``error_code``.

    Returns:
        El mismo valor recibido.

    Raises:
        AppValidationError: ``{error_prefix}_NEGATIVE`` si es negativa.
        AppValidationError: ``{error_prefix}_OUT_OF_RANGE`` si supera 10 000.
    """
    if v < 0:
        raise AppValidationError(
            f"Error: {field_name} no puede ser negativa",
            f"{error_prefix}_NEGATIVE",
        )
    if v > 10000:
        raise AppValidationError(
            f"Error: {field_name} parece inválida",
            f"{error_prefix}_OUT_OF_RANGE",
        )
    return v


def validar_contador_tracking_logica(v: int, field_name: str, error_prefix: str) -> int:
    """Valida contadores auxiliares del tracking (pausas, alertas, etc.).

    Son enteros discretos; el tope de 500 descarta inputs claramente
    rotos sin ser tan bajo que invalide sesiones largas reales.

    Args:
        v: valor del contador.
        field_name: nombre humano del campo, usado en el mensaje de error.
        error_prefix: prefijo del ``error_code``.

    Returns:
        El mismo valor recibido.

    Raises:
        AppValidationError: ``{error_prefix}_NEGATIVE`` si es negativo.
        AppValidationError: ``{error_prefix}_OUT_OF_RANGE`` si supera 500.
    """
    if v < 0:
        raise AppValidationError(
            f"Error: {field_name} no puede ser negativo",
            f"{error_prefix}_NEGATIVE",
        )
    if v > 500:
        raise AppValidationError(
            f"Error: {field_name} excede el límite permitido",
            f"{error_prefix}_OUT_OF_RANGE",
        )
    return v
