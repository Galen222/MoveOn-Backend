# services/text_moderation_service.py

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
    if texto is None:
        return ""
    return " ".join(str(texto).strip().split())


def _quitar_acentos(texto: str) -> str:
    texto = unicodedata.normalize("NFKD", texto)
    return "".join(ch for ch in texto if not unicodedata.combining(ch))


def _normalizar_frase(texto: str | None) -> str:
    texto = _normalizar_texto(texto).lower()
    texto = _quitar_acentos(texto)
    texto = _MULTISPACE_RE.sub(" ", texto)
    return texto.strip()


def _normalizar_username(texto: str | None) -> str:
    texto = _normalizar_frase(texto).translate(_LEET_TRANSLATION)
    return "".join(ch for ch in texto if ch.isalnum())


def _parse_csv(value: str | None) -> list[str]:
    if not value:
        return []
    return [item.strip() for item in value.split(",") if item.strip()]


def _moderar_activado() -> bool:
    return bool(settings.TEXT_MODERATION_ENABLED)


def _bloqueo_payload(field: FieldType) -> tuple[str, str]:
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
            if not line or line.startswith("#"):
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
    return _load_dictionary_cached(
        settings.TEXT_MODERATION_DICTIONARY_DIR,
        settings.TEXT_MODERATION_DICTIONARY_LANGS,
        settings.TEXT_MODERATION_IGNORE_DICTIONARY_TOKENS,
    )


def _match_reserved_username(texto: str) -> str | None:
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
    normalizado = _normalizar_frase(texto)
    return [token for token in _REAL_NAME_TOKEN_SPLIT_RE.split(normalizado) if token]


def _match_real_name_dictionary(texto: str) -> str | None:
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
    await _validar(texto, field="username")


async def validar_nombre_real(texto: str) -> None:
    await _validar(texto, field="real_name")
