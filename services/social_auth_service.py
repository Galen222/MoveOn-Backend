# services/social_auth_service.py

"""Implementa la lógica de negocio de este servicio."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import logging
from typing import Optional

import jwt
from jwt import PyJWKClient
from jwt.exceptions import InvalidTokenError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.concurrency import run_in_threadpool

import database
import schemas
from config import settings
from exceptions import app_http_exception

logger = logging.getLogger("app.social_auth")

_GOOGLE_JWKS_URL = "https://www.googleapis.com/oauth2/v3/certs"
_GOOGLE_ISSUERS = {"accounts.google.com", "https://accounts.google.com"}
_GOOGLE_JWK_CLIENT = PyJWKClient(_GOOGLE_JWKS_URL)


@dataclass(slots=True)
class SocialIdentity:
    """Representa social identidad."""

    provider: str
    provider_user_id: str
    email: Optional[str]
    nombre: Optional[str]
    avatar_url: Optional[str]
    email_verificado: bool


async def verificar_token_social(
    provider: schemas.ProveedorAuthSocial | str, token: str
) -> SocialIdentity:
    """Gestiona verificar token social."""
    if isinstance(provider, schemas.ProveedorAuthSocial):
        provider_value = provider.value
    else:
        provider_value = provider.strip().lower()

    if provider_value == schemas.ProveedorAuthSocial.GOOGLE.value:
        return await _verificar_google(token)

    raise app_http_exception(
        status_code=400,
        mensaje="Error: El proveedor social no es válido",
        error_code="SOCIAL_PROVIDER_INVALID",
    )


async def buscar_vinculo_social(
    db: AsyncSession, provider: str, provider_user_id: str
) -> Optional[database.UsuarioAuthSocial]:
    """Gestiona buscar vinculo social."""
    return (
        await db.execute(
            select(database.UsuarioAuthSocial).where(
                database.UsuarioAuthSocial.provider == provider,
                database.UsuarioAuthSocial.provider_user_id == provider_user_id,
            )
        )
    ).scalar_one_or_none()


def actualizar_metadata_vinculo(
    vinculo: database.UsuarioAuthSocial, identidad: SocialIdentity
) -> None:
    """Actualiza metadata vinculo."""
    vinculo.email_social = identidad.email.lower().strip() if identidad.email else None
    vinculo.nombre_social = identidad.nombre.strip() if identidad.nombre else None
    vinculo.avatar_url = identidad.avatar_url.strip() if identidad.avatar_url else None
    vinculo.ultimo_login_en = datetime.now(timezone.utc)


def crear_vinculo_social(
    usuario_id: int,
    identidad: SocialIdentity,
) -> database.UsuarioAuthSocial:
    """Construye vinculo social."""
    return database.UsuarioAuthSocial(
        usuario_id=usuario_id,
        provider=identidad.provider,
        provider_user_id=identidad.provider_user_id,
        email_social=identidad.email.lower().strip() if identidad.email else None,
        nombre_social=identidad.nombre.strip() if identidad.nombre else None,
        avatar_url=identidad.avatar_url.strip() if identidad.avatar_url else None,
    )


async def _verificar_google(token: str) -> SocialIdentity:
    """Gestiona verificar google."""
    # Gestiona verificar google.
    if not settings.GOOGLE_WEB_CLIENT_ID.strip():
        raise app_http_exception(
            status_code=503,
            mensaje="Error: La autenticación con Google no está configurada",
            error_code="GOOGLE_AUTH_NOT_CONFIGURED",
        )

    try:
        signing_key = await run_in_threadpool(
            _GOOGLE_JWK_CLIENT.get_signing_key_from_jwt, token
        )
        payload = jwt.decode(
            token,
            signing_key.key,
            algorithms=["RS256"],
            audience=settings.GOOGLE_WEB_CLIENT_ID,
            options={"require": ["exp", "iat", "iss", "sub"]},
        )
    except InvalidTokenError:
        logger.info("google_token_invalido")
        raise app_http_exception(
            status_code=401,
            mensaje="Error: El token de Google no es válido o ha expirado",
            error_code="GOOGLE_TOKEN_INVALID_OR_EXPIRED",
        )
    except Exception:
        logger.exception("google_token_verificacion_fallida")
        raise app_http_exception(
            status_code=503,
            mensaje="Error: No se pudo verificar el token de Google",
            error_code="GOOGLE_TOKEN_VERIFICATION_UNAVAILABLE",
        )

    issuer = str(payload.get("iss") or "")
    if issuer not in _GOOGLE_ISSUERS:
        raise app_http_exception(
            status_code=401,
            mensaje="Error: El emisor del token de Google no es válido",
            error_code="GOOGLE_TOKEN_ISSUER_INVALID",
        )

    provider_user_id = str(payload.get("sub") or "").strip()
    if not provider_user_id:
        raise app_http_exception(
            status_code=401,
            mensaje="Error: El token de Google no contiene un usuario válido",
            error_code="GOOGLE_TOKEN_MISSING_SUB",
        )

    email = payload.get("email")
    email_verificado = bool(payload.get("email_verified")) if email else False
    if email and not email_verificado:
        raise app_http_exception(
            status_code=401,
            mensaje="Error: La cuenta de Google debe tener el correo verificado",
            error_code="GOOGLE_EMAIL_NOT_VERIFIED",
        )

    picture = payload.get("picture")
    name = payload.get("name") or payload.get("given_name")

    return SocialIdentity(
        provider=schemas.ProveedorAuthSocial.GOOGLE.value,
        provider_user_id=provider_user_id,
        email=(
            str(email).strip().lower()
            if isinstance(email, str) and email.strip()
            else None
        ),
        nombre=str(name).strip() if isinstance(name, str) and name.strip() else None,
        avatar_url=(
            str(picture).strip()
            if isinstance(picture, str) and picture.strip()
            else None
        ),
        email_verificado=email_verificado,
    )
