# services/text_moderation_service.py

from __future__ import annotations

import logging
import unicodedata
from typing import Any, Literal

import httpx
from fastapi import HTTPException

from config import settings

logger = logging.getLogger("app.text_moderation")

OPENAI_MODERATION_URL = "https://api.openai.com/v1/moderations"

FieldType = Literal["username", "real_name"]

_RELEVANT_CATEGORY_KEYS = (
    "sexual",
    "harassment",
    "harassment/threatening",
    "hate",
    "hate/threatening",
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


def _normalizar_username_para_reservas(texto: str) -> str:
    texto = _normalizar_texto(texto).lower()

    # Quitar acentos por si en el futuro cambias reglas del username
    texto = unicodedata.normalize("NFKD", texto)
    texto = "".join(ch for ch in texto if not unicodedata.combining(ch))

    # Como tu username ya es alfanumérico, esto lo deja listo para comparar
    return "".join(ch for ch in texto if ch.isalnum())


def _parse_csv(value: str | None) -> list[str]:
    if not value:
        return []
    return [item.strip().lower() for item in value.split(",") if item.strip()]


def _reserved_tokens() -> list[str]:
    return _parse_csv(settings.TEXT_MODERATION_RESERVED_USERNAME_TOKENS)


def _username_reservado_match(texto: str) -> str | None:
    username = _normalizar_username_para_reservas(texto)
    if not username:
        return None

    for token in _reserved_tokens():
        token_norm = _normalizar_username_para_reservas(token)
        if not token_norm:
            continue

        # Exacto o claramente derivado
        if (
            username == token_norm
            or username.startswith(token_norm)
            or username.endswith(token_norm)
        ):
            return token_norm

        # Para los tokens más sensibles, también bloqueamos si aparecen dentro
        if token_norm in _HIGH_RISK_RESERVED_TOKENS and token_norm in username:
            return token_norm

    return None


def _provider_disponible() -> bool:
    return bool(
        settings.TEXT_MODERATION_ENABLED
        and settings.OPENAI_API_KEY
    )


def _mensaje_bloqueo(field: FieldType) -> str:
    if field == "username":
        return "Error: El nombre de usuario contiene lenguaje inapropiado o no permitido"
    return "Error: El nombre real contiene lenguaje inapropiado o no permitido"


def _timeout() -> httpx.Timeout:
    total = float(settings.TEXT_MODERATION_TIMEOUT_SECONDS or 3.0)
    connect = min(total, 3.0)
    return httpx.Timeout(timeout=total, connect=connect)


def _threshold(field: FieldType) -> float:
    if field == "username":
        return float(settings.TEXT_MODERATION_USERNAME_SCORE_THRESHOLD)
    return float(settings.TEXT_MODERATION_REAL_NAME_SCORE_THRESHOLD)


def _extraer_resultado(data: dict[str, Any]) -> dict[str, Any]:
    results = data.get("results")
    if not isinstance(results, list) or not results:
        raise ValueError("Respuesta inválida de OpenAI Moderation: results vacío")

    result = results[0]
    if not isinstance(result, dict):
        raise ValueError("Respuesta inválida de OpenAI Moderation: result no es un objeto")

    return result


def _categorias_relevantes_activas(categories: dict[str, Any]) -> list[str]:
    activas: list[str] = []
    for key in _RELEVANT_CATEGORY_KEYS:
        if bool(categories.get(key)):
            activas.append(key)
    return activas


def _max_relevant_score(scores: dict[str, Any]) -> float:
    valores: list[float] = []

    for key in _RELEVANT_CATEGORY_KEYS:
        value = scores.get(key)
        if isinstance(value, (int, float)):
            valores.append(float(value))

    return max(valores) if valores else 0.0


async def _call_openai(texto: str) -> dict[str, Any]:
    headers = {
        "Authorization": f"Bearer {settings.OPENAI_API_KEY}",
        "Content-Type": "application/json",
    }

    payload = {
        "model": settings.OPENAI_MODERATION_MODEL,
        "input": texto,
    }

    async with httpx.AsyncClient(timeout=_timeout()) as client:
        response = await client.post(
            OPENAI_MODERATION_URL,
            headers=headers,
            json=payload,
        )
        response.raise_for_status()
        data = response.json()

    if not isinstance(data, dict):
        raise ValueError("Respuesta no válida de OpenAI Moderation")

    return data


async def _validar(texto: str, *, field: FieldType) -> None:
    texto = _normalizar_texto(texto)
    if not texto:
        return

    # 1) Username reservado: bloqueo local, sin depender de red
    if field == "username":
        reserved_match = _username_reservado_match(texto)
        if reserved_match:
            logger.warning(
                "text_moderation_reserved_username_blocked",
                extra={
                    "provider": "local_reserved_dictionary",
                    "field": field,
                    "text_len": len(texto),
                    "reserved_match": reserved_match,
                },
            )
            raise HTTPException(status_code=400, detail=_mensaje_bloqueo(field))

    # 2) Si OpenAI no está configurado, no seguimos
    if not _provider_disponible():
        return

    try:
        data = await _call_openai(texto)
        result = _extraer_resultado(data)

        flagged = bool(result.get("flagged"))
        categories = result.get("categories") or {}
        scores = result.get("category_scores") or {}

        if not isinstance(categories, dict):
            categories = {}
        if not isinstance(scores, dict):
            scores = {}

        categorias_activas = _categorias_relevantes_activas(categories)
        max_score = _max_relevant_score(scores)
        threshold = _threshold(field)

        # Política:
        # - si OpenAI lo marca como flagged -> bloquear
        # - si no lo marca, pero alguna categoría relevante supera el umbral -> bloquear
        if flagged or max_score >= threshold:
            logger.warning(
                "text_moderation_blocked",
                extra={
                    "provider": "openai",
                    "field": field,
                    "model": settings.OPENAI_MODERATION_MODEL,
                    "text_len": len(texto),
                    "flagged": flagged,
                    "max_relevant_score": max_score,
                    "threshold": threshold,
                    "active_categories": categorias_activas,
                },
            )
            raise HTTPException(status_code=400, detail=_mensaje_bloqueo(field))

    except HTTPException:
        raise
    except (httpx.HTTPError, ValueError) as exc:
        logger.error(
            "text_moderation_provider_error",
            extra={
                "provider": "openai",
                "field": field,
                "model": settings.OPENAI_MODERATION_MODEL,
                "text_len": len(texto),
                "fail_open": settings.TEXT_MODERATION_FAIL_OPEN,
                "error": str(exc),
            },
        )

        if settings.TEXT_MODERATION_FAIL_OPEN:
            return

        raise HTTPException(
            status_code=503,
            detail="Error: No se pudo validar el contenido en este momento",
        )


async def validar_nombre_usuario(texto: str) -> None:
    await _validar(texto, field="username")


async def validar_nombre_real(texto: str) -> None:
    await _validar(texto, field="real_name")
    