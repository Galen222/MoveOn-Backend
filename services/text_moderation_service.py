# services/text_moderation_service.py

"""Implementa la lógica de negocio de este servicio."""

from __future__ import annotations

import logging
import re
import unicodedata
from functools import lru_cache
from pathlib import Path
from typing import Literal

from fastapi import HTTPException

from config import settings
from exceptions import app_http_exception

logger = logging.getLogger("app.text_moderation")

FieldType = Literal["username", "real_name"]

_MULTISPACE_RE = re.compile(r"\s+")
_REAL_NAME_TOKEN_SPLIT_RE = re.compile(r"[^a-z]+")
_USERNAME_MIN_TERM_LEN = 4
_REAL_NAME_MIN_TERM_LEN = 4

_LEET_TRANSLATION = str.maketrans(
    {
        "0": "o",
        "1": "i",
        "3": "e",
        "4": "a",
        "5": "s",
        "7": "t",
        "$": "s",
        "@": "a",
        "!": "i",
    }
)

_HIGH_RISK_RESERVED_TOKENS = {
    "admin",
    "administrator",
    "administrador",
    "support",
    "soporte",
    "moderator",
    "moderador",
    "staff",
    "official",
    "oficial",
    "root",
    "owner",
    "system",
    "sistema",
}


def _normalizar_texto(texto: str | None) -> str:
    """Colapsa espacios y recorta un texto, manteniendo acentos y caso.

    Se usa como primer paso en todas las normalizaciones: elimina
    espacios dobles, saltos de línea, tabs, etc., dejando una sola
    cadena limpia con palabras separadas por un único espacio.

    Args:
        texto: texto tal como llega del cliente.

    Returns:
        Texto limpio sin espacios redundantes; cadena vacía si la entrada era ``None`` o solo espacios.
    """
    if texto is None:
        return ""
    return " ".join(str(texto).strip().split())


def _quitar_acentos(texto: str) -> str:
    """Elimina marcas diacríticas mediante descomposición Unicode NFKD.

    Usa la descomposición canónica y filtra los caracteres combinables
    (acentos, virgulillas, diéresis), dejando solo el grafema base.
    Importante para que ``noël`` y ``noel`` o ``café`` y ``cafe``
    compartan forma normalizada a la hora de matear diccionarios.

    Args:
        texto: texto ya preprocesado (típicamente en minúsculas).

    Returns:
        El mismo texto sin marcas diacríticas.
    """
    texto = unicodedata.normalize("NFKD", texto)
    return "".join(ch for ch in texto if not unicodedata.combining(ch))


def _normalizar_frase(texto: str | None) -> str:
    """Forma canónica de una frase/nombre real para comparar con diccionarios.

    Encadena ``_normalizar_texto`` → minúsculas → ``_quitar_acentos`` →
    colapso de espacios múltiples. El resultado es lo que realmente se
    usa como clave en los conjuntos de ``phrase_terms``.

    Args:
        texto: texto libre (nombre real, frase).

    Returns:
        Forma canónica lista para comparar.
    """
    texto = _normalizar_texto(texto).lower()
    texto = _quitar_acentos(texto)
    texto = _MULTISPACE_RE.sub(" ", texto)
    return texto.strip()


def _normalizar_username(texto: str | None) -> str:
    """Forma canónica de un nombre de usuario para detección anti-leet.

    Extiende ``_normalizar_frase`` aplicando ``_LEET_TRANSLATION``
    (sustituciones típicas ``1→i``, ``3→e``, ``0→o``, etc.) y filtra
    todo lo que no sea alfanumérico. Así ``h3ll0_dude`` y ``hellodude``
    acaban siendo la misma clave en el conjunto de ``username_terms``.

    Args:
        texto: nombre de usuario tal como lo escribe el cliente.

    Returns:
        Cadena canónica alfanumérica, apta para matching contra ``username_terms``.
    """
    texto = _normalizar_frase(texto).translate(_LEET_TRANSLATION)
    return "".join(ch for ch in texto if ch.isalnum())


def _parse_csv(value: str | None) -> list[str]:
    """Parte una cadena CSV en lista, descartando elementos vacíos.

    Gemelo del parser de ``ip_rate_limit``, replicado aquí para no
    introducir dependencia entre el módulo de moderación y el de red.

    Args:
        value: cadena CSV tal como llega del entorno/configuración.

    Returns:
        Lista con cada elemento ya trimmed; vacía si la entrada era ``None`` o no aporta nada útil.
    """
    if not value:
        return []
    return [item.strip() for item in value.split(",") if item.strip()]


def _moderar_activado() -> bool:
    """Atajo que expone ``settings.TEXT_MODERATION_ENABLED`` como ``bool``.

    Existe para no repetir la conversión cada vez y para que el resto
    del módulo no hable directamente con ``settings``.

    Returns:
        ``True`` si la moderación de texto está activada, ``False`` en otro caso.
    """
    return bool(settings.TEXT_MODERATION_ENABLED)


def _bloqueo_payload(field: FieldType) -> tuple[str, str]:
    """Devuelve el par ``(mensaje, error_code)`` específico por tipo de campo.

    Username y nombre real tienen mensajes y códigos distintos para
    que la UI del cliente pueda mostrar un texto adecuado a cada campo.

    Args:
        field: ``"username"`` o cualquier otro valor (tratado como nombre real).

    Returns:
        Tupla ``(mensaje_humano, error_code_canonico)``.
    """
    if field == "username":
        return (
            "Error: El nombre de usuario contiene lenguaje inapropiado o no permitido",
            "USERNAME_INAPPROPRIATE_OR_NOT_ALLOWED",
        )
    return (
        "Error: El nombre real contiene lenguaje inapropiado o no permitido",
        "REAL_NAME_INAPPROPRIATE_OR_NOT_ALLOWED",
    )


def _reserved_tokens() -> list[str]:
    """Devuelve la lista normalizada de tokens reservados configurados.

    Los tokens vienen de ``settings.TEXT_MODERATION_RESERVED_USERNAME_TOKENS``
    (p. ej. ``"admin, moveon, support"``). Cada entrada se pasa por
    ``_normalizar_username`` para que un usuario no pueda evadirlo
    con mayúsculas o leet-speak (``Adm1n``, ``ADMIN``...).

    Returns:
        Lista de tokens canónicos no vacíos; lista vacía si la configuración no define ninguno.
    """
    return [
        _normalizar_username(token)
        for token in _parse_csv(settings.TEXT_MODERATION_RESERVED_USERNAME_TOKENS)
        if _normalizar_username(token)
    ]


@lru_cache(maxsize=8)
def _load_dictionary_cached(
    dictionary_dir: str,
    languages_csv: str,
    ignore_csv: str,
) -> dict[str, frozenset[str]]:
    """Carga y pre-indexa los diccionarios de profanidad por idioma.

    Se envuelve en ``lru_cache`` para no releer los ficheros en cada
    petición. La cache usa como clave los tres parámetros exactos de
    configuración, de forma que cambiar cualquiera en runtime (tests)
    produce una entrada distinta.

    Formato del fichero: una entrada por línea, comentarios con ``# `` al
    inicio. Por cada entrada se generan tres variantes pre-indexadas:

    - ``phrase_terms``: frases con espacios (``hijo de puta``), forma canónica.
    - ``single_terms``: palabras sueltas de longitud suficiente, para matching
      tokenizado en nombres reales.
    - ``username_terms``: forma colapsada sin caracteres no alfanuméricos,
      para matching contra nombres de usuario con leet-speak.

    Se pueden excluir términos concretos con ``TEXT_MODERATION_IGNORE_DICTIONARY_TOKENS``:
    útil para desbloquear falsos positivos sin editar los ficheros fuente.

    Args:
        dictionary_dir: ruta donde viven los ficheros ``<lang>.txt``.
        languages_csv: CSV de códigos de idioma a cargar (p. ej. ``"es,en"``).
        ignore_csv: CSV de términos a ignorar explícitamente.

    Returns:
        Diccionario con las tres claves ``single_terms``, ``phrase_terms`` y ``username_terms``, cada una un ``frozenset``.

    Raises:
        FileNotFoundError: si falta el directorio o el fichero de algún idioma configurado.
    """
    # Gestiona load dictionary cached.
    base_dir = Path(dictionary_dir)
    if not base_dir.exists():
        raise FileNotFoundError(f"No existe el directorio de diccionarios: {base_dir}")

    languages = [
        lang.strip().lower() for lang in languages_csv.split(",") if lang.strip()
    ]
    if not languages:
        raise FileNotFoundError("No hay idiomas configurados para moderación")

    ignored_phrases = {
        _normalizar_frase(token)
        for token in _parse_csv(ignore_csv)
        if _normalizar_frase(token)
    }
    ignored_usernames = {
        _normalizar_username(token)
        for token in _parse_csv(ignore_csv)
        if _normalizar_username(token)
    }

    single_terms: set[str] = set()
    phrase_terms: set[str] = set()
    username_terms: set[str] = set()

    for lang in languages:
        file_path = base_dir / f"{lang}.txt"
        if not file_path.exists():
            raise FileNotFoundError(
                f"No existe el diccionario para '{lang}': {file_path}"
            )

        contenido = file_path.read_text(encoding="utf-8", errors="ignore")

        for raw_line in contenido.splitlines():
            line = raw_line.strip()
            if not line or line.startswith("# "):
                continue

            term = _normalizar_frase(line)
            if not term or term in ignored_phrases:
                continue

            if " " in term:
                phrase_terms.add(term)
            elif len(term) >= _REAL_NAME_MIN_TERM_LEN:
                single_terms.add(term)

            username_term = _normalizar_username(line)
            if (
                username_term
                and len(username_term) >= _USERNAME_MIN_TERM_LEN
                and username_term not in ignored_usernames
            ):
                username_terms.add(username_term)

    return {
        "single_terms": frozenset(single_terms),
        "phrase_terms": frozenset(phrase_terms),
        "username_terms": frozenset(username_terms),
    }


def _load_dictionary() -> dict[str, frozenset[str]]:
    """Fachada sobre ``_load_dictionary_cached`` que usa los settings actuales.

    Extrae los tres parámetros de configuración justo en el momento
    de la llamada; ``lru_cache`` los compara por valor, así que si
    uno cambia (tests, reload) se recalcula automáticamente.

    Returns:
        Mismo diccionario que ``_load_dictionary_cached``.
    """
    return _load_dictionary_cached(
        settings.TEXT_MODERATION_DICTIONARY_DIR,
        settings.TEXT_MODERATION_DICTIONARY_LANGS,
        settings.TEXT_MODERATION_IGNORE_DICTIONARY_TOKENS,
    )


def _match_reserved_username(texto: str) -> str | None:
    """Busca coincidencia del username con la lista de tokens reservados.

    Reglas:

    - Coincidencia exacta (``username == token``).
    - Empieza o termina por el token (``admin123``, ``userAdmin``).
    - Para tokens de alto riesgo (``_HIGH_RISK_RESERVED_TOKENS``), también
      contiene el token en cualquier posición (``superadminuser``).

    El tercer caso existe para que términos como ``admin`` no se puedan
    colar como subcadena dentro de un nombre, pero sin hacer la regla
    tan estricta para tokens de menor riesgo que genere demasiados
    falsos positivos.

    Args:
        texto: nombre de usuario tal como lo envía el cliente.

    Returns:
        Token que hizo match o ``None`` si no hubo coincidencia.
    """
    # Gestiona match reserved username.
    username = _normalizar_username(texto)
    if not username:
        return None

    for token in _reserved_tokens():
        if not token:
            continue

        if username == token:
            return token

        if username.startswith(token) or username.endswith(token):
            return token

        if token in _HIGH_RISK_RESERVED_TOKENS and token in username:
            return token

    return None


def _match_username_dictionary(texto: str) -> str | None:
    """Busca palabras prohibidas en el nombre de usuario con matching ajustado.

    Usa la lista ``username_terms`` del diccionario cargado. Una palabra
    solo se considera match si aparece como subcadena cuyos bordes son
    (inicio de cadena, fin de cadena, o dígitos). Esto evita falsos
    positivos: ``shell`` contiene ``hell`` pero no debería bloquearse,
    mientras que ``hell_1234`` sí porque el borde derecho es dígito.

    Args:
        texto: nombre de usuario tal como lo envía el cliente.

    Returns:
        Término del diccionario que hizo match, o ``None`` si no hubo ninguno.
    """
    # Gestiona match username dictionary.
    username = _normalizar_username(texto)
    if not username:
        return None

    username_terms = _load_dictionary()["username_terms"]

    for term in username_terms:
        if username == term:
            return term

        start = username.find(term)
        while start != -1:
            end = start + len(term)
            left = username[:start]
            right = username[end:]

            if (not left or left.isdigit()) and (not right or right.isdigit()):
                return term

            start = username.find(term, start + 1)

    return None


def _tokenizar_nombre_real(texto: str) -> list[str]:
    """Divide un nombre real normalizado en tokens para matching por palabra.

    Usa la expresión ``_REAL_NAME_TOKEN_SPLIT_RE`` para partir por
    caracteres no alfanuméricos (espacios, apóstrofes, guiones), igual
    que haría cualquier humano al leer el nombre. Se descartan los
    tokens vacíos que pueda producir el split.

    Args:
        texto: nombre real ya normalizado con ``_normalizar_frase``.

    Returns:
        Lista de tokens individuales (palabras del nombre).
    """
    normalizado = _normalizar_frase(texto)
    return [token for token in _REAL_NAME_TOKEN_SPLIT_RE.split(normalizado) if token]


def _match_real_name_dictionary(texto: str) -> str | None:
    """Busca coincidencias contra frases y palabras en un nombre real.

    Dos niveles:

    1. Match por frase completa (``phrase_terms``): si el nombre
       normalizado coincide exactamente con una frase prohibida, se
       bloquea. Evita evasión por componer varias palabras buenas para
       formar una frase mala.
    2. Match por token individual: para cada palabra del nombre, se
       comprueba si pertenece a ``single_terms``.

    Args:
        texto: nombre real tal como lo envía el cliente.

    Returns:
        Frase o token que hizo match, o ``None`` si no hubo coincidencia.
    """
    # Gestiona match real name dictionary.
    normalizado = _normalizar_frase(texto)
    if not normalizado:
        return None

    dictionary = _load_dictionary()

    if normalizado in dictionary["phrase_terms"]:
        return normalizado

    for token in _tokenizar_nombre_real(normalizado):
        if token in dictionary["single_terms"]:
            return token

    return None


async def _validar(texto: str, *, field: FieldType) -> None:
    """Núcleo del validador: decide si bloquear un texto y cómo.

    Aplica, por orden:

    1. Normaliza la entrada y descarta vacíos (``None``/whitespace no se moderan).
    2. Si la moderación está deshabilitada, vuelve sin mirar.
    3. Para ``username`` aplica primero la lista de reservados
       (``_match_reserved_username``) y luego el diccionario de
       profanidad para usernames.
    4. Para nombres reales aplica directamente el diccionario de frases
       y tokens.
    5. Cada bloqueo se registra con un evento distinto (``text_moderation_reserved_username_blocked``
       o ``text_moderation_blocked``) para que sea trivial grepear por
       tipo de causa.
    6. Si el diccionario está mal configurado o falta (``FileNotFoundError``),
       consulta ``TEXT_MODERATION_FAIL_OPEN``: en modo fail-open deja pasar
       el texto con un log de error (preferible a tumbar el registro);
       en modo fail-closed responde 503.

    Args:
        texto: texto a validar.
        field: ``"username"`` o ``"real_name"``; cambia las reglas y el mensaje.

    Raises:
        AppHTTPException: 400 con ``USERNAME_INAPPROPRIATE_OR_NOT_ALLOWED`` o ``REAL_NAME_INAPPROPRIATE_OR_NOT_ALLOWED`` según el campo, si se detecta contenido prohibido.
        AppHTTPException: 503 ``CONTENT_VALIDATION_UNAVAILABLE`` si falta el diccionario y ``TEXT_MODERATION_FAIL_OPEN`` es falso.
    """
    # Gestiona validar.
    texto = _normalizar_texto(texto)
    if not texto:
        return

    if not _moderar_activado():
        return

    mensaje, error_code = _bloqueo_payload(field)

    try:
        if field == "username":
            reserved_match = _match_reserved_username(texto)
            if reserved_match:
                logger.warning(
                    "text_moderation_reserved_username_blocked",
                    extra={
                        "provider": "local_reserved_dictionary",
                        "field": field,
                        "text_len": len(texto),
                        "match": reserved_match,
                    },
                )
                raise app_http_exception(
                    status_code=400,
                    mensaje=mensaje,
                    error_code=error_code,
                )

            profanity_match = _match_username_dictionary(texto)
            if profanity_match:
                logger.warning(
                    "text_moderation_blocked",
                    extra={
                        "provider": "ldnoobwv2_local",
                        "field": field,
                        "text_len": len(texto),
                        "match": profanity_match,
                    },
                )
                raise app_http_exception(
                    status_code=400,
                    mensaje=mensaje,
                    error_code=error_code,
                )

            return

        profanity_match = _match_real_name_dictionary(texto)
        if profanity_match:
            logger.warning(
                "text_moderation_blocked",
                extra={
                    "provider": "ldnoobwv2_local",
                    "field": field,
                    "text_len": len(texto),
                    "match": profanity_match,
                },
            )
            raise app_http_exception(
                status_code=400,
                mensaje=mensaje,
                error_code=error_code,
            )

    except HTTPException:
        raise
    except FileNotFoundError as exc:
        logger.error(
            "text_moderation_dictionary_error",
            extra={
                "provider": "ldnoobwv2_local",
                "field": field,
                "dictionary_dir": settings.TEXT_MODERATION_DICTIONARY_DIR,
                "languages": settings.TEXT_MODERATION_DICTIONARY_LANGS,
                "fail_open": settings.TEXT_MODERATION_FAIL_OPEN,
                "error": str(exc),
            },
        )

        if settings.TEXT_MODERATION_FAIL_OPEN:
            return

        raise app_http_exception(
            status_code=503,
            mensaje="Error: No se pudo validar el contenido en este momento",
            error_code="CONTENT_VALIDATION_UNAVAILABLE",
        )


async def validar_nombre_usuario(texto: str) -> None:
    """Entrada pública del validador para nombres de usuario.

    Delega en ``_validar`` con ``field='username'`` para aplicar la
    combinación completa (reservados + diccionario anti-leet).

    Args:
        texto: nombre de usuario propuesto por el cliente.

    Raises:
        AppHTTPException: 400 ``USERNAME_INAPPROPRIATE_OR_NOT_ALLOWED`` si el nombre de usuario hace match con la lista de reservados o el diccionario de profanidad.
        AppHTTPException: 503 ``CONTENT_VALIDATION_UNAVAILABLE`` si la moderación falla y ``TEXT_MODERATION_FAIL_OPEN`` es falso.
    """
    await _validar(texto, field="username")


async def validar_nombre_real(texto: str) -> None:
    """Entrada pública del validador para nombres reales.

    Delega en ``_validar`` con ``field='real_name'`` que comprueba
    frases completas (``phrase_terms``) y tokens individuales
    (``single_terms``) del diccionario.

    Args:
        texto: nombre real propuesto por el cliente.

    Raises:
        AppHTTPException: 400 ``REAL_NAME_INAPPROPRIATE_OR_NOT_ALLOWED`` si el nombre real hace match con el diccionario de profanidad.
        AppHTTPException: 503 ``CONTENT_VALIDATION_UNAVAILABLE`` si la moderación falla y ``TEXT_MODERATION_FAIL_OPEN`` es falso.
    """
    await _validar(texto, field="real_name")
