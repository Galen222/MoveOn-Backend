# tests/test_text_moderation_service.py

import httpx
import pytest
from unittest.mock import AsyncMock

from fastapi import HTTPException

from services import text_moderation_service as svc


class TestValidarNombreUsuario:
    @pytest.mark.asyncio
    async def test_username_reservado_bloquea_sin_llamar_openai(self, monkeypatch):
        mock_call = AsyncMock()

        monkeypatch.setattr(svc, "_call_openai", mock_call)
        monkeypatch.setattr(svc.settings, "TEXT_MODERATION_ENABLED", True, raising=False)
        monkeypatch.setattr(svc.settings, "OPENAI_API_KEY", "test-key", raising=False)
        monkeypatch.setattr(
            svc.settings,
            "TEXT_MODERATION_RESERVED_USERNAME_TOKENS",
            "admin,soporte,moderador",
            raising=False,
        )

        with pytest.raises(HTTPException) as exc:
            await svc.validar_nombre_usuario("admin123")

        assert exc.value.status_code == 400
        mock_call.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_openai_flagged_bloquea_username(self, monkeypatch):
        monkeypatch.setattr(svc.settings, "TEXT_MODERATION_ENABLED", True, raising=False)
        monkeypatch.setattr(svc.settings, "OPENAI_API_KEY", "test-key", raising=False)
        monkeypatch.setattr(
            svc.settings,
            "TEXT_MODERATION_RESERVED_USERNAME_TOKENS",
            "",
            raising=False,
        )

        monkeypatch.setattr(
            svc,
            "_call_openai",
            AsyncMock(
                return_value={
                    "id": "modr_x",
                    "model": "omni-moderation-latest",
                    "results": [
                        {
                            "flagged": True,
                            "categories": {
                                "sexual": False,
                                "harassment": True,
                                "harassment/threatening": False,
                                "hate": False,
                                "hate/threatening": False,
                            },
                            "category_scores": {
                                "sexual": 0.01,
                                "harassment": 0.91,
                                "harassment/threatening": 0.04,
                                "hate": 0.01,
                                "hate/threatening": 0.01,
                            },
                        }
                    ],
                }
            ),
        )

        with pytest.raises(HTTPException) as exc:
            await svc.validar_nombre_usuario("insulto123")

        assert exc.value.status_code == 400
        assert "nombre de usuario" in exc.value.detail.lower()

    @pytest.mark.asyncio
    async def test_openai_score_supera_umbral_y_bloquea_username(self, monkeypatch):
        monkeypatch.setattr(svc.settings, "TEXT_MODERATION_ENABLED", True, raising=False)
        monkeypatch.setattr(svc.settings, "OPENAI_API_KEY", "test-key", raising=False)
        monkeypatch.setattr(
            svc.settings,
            "TEXT_MODERATION_RESERVED_USERNAME_TOKENS",
            "",
            raising=False,
        )
        monkeypatch.setattr(
            svc.settings,
            "TEXT_MODERATION_USERNAME_SCORE_THRESHOLD",
            0.12,
            raising=False,
        )

        monkeypatch.setattr(
            svc,
            "_call_openai",
            AsyncMock(
                return_value={
                    "results": [
                        {
                            "flagged": False,
                            "categories": {
                                "sexual": True,
                                "harassment": False,
                                "harassment/threatening": False,
                                "hate": False,
                                "hate/threatening": False,
                            },
                            "category_scores": {
                                "sexual": 0.24,
                                "harassment": 0.02,
                                "harassment/threatening": 0.01,
                                "hate": 0.01,
                                "hate/threatening": 0.01,
                            },
                        }
                    ]
                }
            ),
        )

        with pytest.raises(HTTPException):
            await svc.validar_nombre_usuario("palabrota123")

    @pytest.mark.asyncio
    async def test_username_limpio_pasa(self, monkeypatch):
        monkeypatch.setattr(svc.settings, "TEXT_MODERATION_ENABLED", True, raising=False)
        monkeypatch.setattr(svc.settings, "OPENAI_API_KEY", "test-key", raising=False)
        monkeypatch.setattr(
            svc.settings,
            "TEXT_MODERATION_RESERVED_USERNAME_TOKENS",
            "admin,soporte",
            raising=False,
        )

        monkeypatch.setattr(
            svc,
            "_call_openai",
            AsyncMock(
                return_value={
                    "results": [
                        {
                            "flagged": False,
                            "categories": {
                                "sexual": False,
                                "harassment": False,
                                "harassment/threatening": False,
                                "hate": False,
                                "hate/threatening": False,
                            },
                            "category_scores": {
                                "sexual": 0.01,
                                "harassment": 0.01,
                                "harassment/threatening": 0.01,
                                "hate": 0.01,
                                "hate/threatening": 0.01,
                            },
                        }
                    ]
                }
            ),
        )

        await svc.validar_nombre_usuario("GalenRunner")


class TestValidarNombreReal:
    @pytest.mark.asyncio
    async def test_flagged_bloquea_nombre_real(self, monkeypatch):
        monkeypatch.setattr(svc.settings, "TEXT_MODERATION_ENABLED", True, raising=False)
        monkeypatch.setattr(svc.settings, "OPENAI_API_KEY", "test-key", raising=False)

        monkeypatch.setattr(
            svc,
            "_call_openai",
            AsyncMock(
                return_value={
                    "results": [
                        {
                            "flagged": True,
                            "categories": {
                                "sexual": False,
                                "harassment": True,
                                "harassment/threatening": False,
                                "hate": False,
                                "hate/threatening": False,
                            },
                            "category_scores": {
                                "sexual": 0.02,
                                "harassment": 0.88,
                                "harassment/threatening": 0.03,
                                "hate": 0.01,
                                "hate/threatening": 0.01,
                            },
                        }
                    ]
                }
            ),
        )

        with pytest.raises(HTTPException) as exc:
            await svc.validar_nombre_real("Nombre ofensivo")

        assert exc.value.status_code == 400
        assert "nombre real" in exc.value.detail.lower()

    @pytest.mark.asyncio
    async def test_score_bajo_permite_nombre_real(self, monkeypatch):
        monkeypatch.setattr(svc.settings, "TEXT_MODERATION_ENABLED", True, raising=False)
        monkeypatch.setattr(svc.settings, "OPENAI_API_KEY", "test-key", raising=False)
        monkeypatch.setattr(
            svc.settings,
            "TEXT_MODERATION_REAL_NAME_SCORE_THRESHOLD",
            0.45,
            raising=False,
        )

        monkeypatch.setattr(
            svc,
            "_call_openai",
            AsyncMock(
                return_value={
                    "results": [
                        {
                            "flagged": False,
                            "categories": {
                                "sexual": False,
                                "harassment": False,
                                "harassment/threatening": False,
                                "hate": False,
                                "hate/threatening": False,
                            },
                            "category_scores": {
                                "sexual": 0.03,
                                "harassment": 0.08,
                                "harassment/threatening": 0.01,
                                "hate": 0.01,
                                "hate/threatening": 0.01,
                            },
                        }
                    ]
                }
            ),
        )

        await svc.validar_nombre_real("María García")

    @pytest.mark.asyncio
    async def test_fail_open_si_openai_falla(self, monkeypatch):
        monkeypatch.setattr(svc.settings, "TEXT_MODERATION_ENABLED", True, raising=False)
        monkeypatch.setattr(svc.settings, "OPENAI_API_KEY", "test-key", raising=False)
        monkeypatch.setattr(svc.settings, "TEXT_MODERATION_FAIL_OPEN", True, raising=False)

        monkeypatch.setattr(
            svc,
            "_call_openai",
            AsyncMock(side_effect=httpx.ReadTimeout("timeout")),
        )

        await svc.validar_nombre_real("María García")

    @pytest.mark.asyncio
    async def test_fail_closed_devuelve_503_si_openai_falla(self, monkeypatch):
        monkeypatch.setattr(svc.settings, "TEXT_MODERATION_ENABLED", True, raising=False)
        monkeypatch.setattr(svc.settings, "OPENAI_API_KEY", "test-key", raising=False)
        monkeypatch.setattr(svc.settings, "TEXT_MODERATION_FAIL_OPEN", False, raising=False)

        monkeypatch.setattr(
            svc,
            "_call_openai",
            AsyncMock(side_effect=httpx.ConnectError("boom")),
        )

        with pytest.raises(HTTPException) as exc:
            await svc.validar_nombre_real("María García")

        assert exc.value.status_code == 503
        assert "no se pudo validar" in exc.value.detail.lower()
        