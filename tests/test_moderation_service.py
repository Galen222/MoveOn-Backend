# tests/test_moderation_service.py

"""Contiene pruebas automatizadas de este módulo."""

from __future__ import annotations

import pytest
from fastapi import HTTPException

from services import text_moderation_service as svc


def _write_dicts(
    tmp_path,
    *,
    en_words: list[str] | None = None,
    es_words: list[str] | None = None,
) -> None:
    """Gestiona write dicts."""
    (tmp_path / "en.txt").write_text(
        "\n".join(en_words or []),
        encoding="utf-8",
    )
    (tmp_path / "es.txt").write_text(
        "\n".join(es_words or []),
        encoding="utf-8",
    )


@pytest.fixture(autouse=True)
def _reset_cache():
    """Gestiona reset cache."""
    svc._load_dictionary_cached.cache_clear()
    yield
    svc._load_dictionary_cached.cache_clear()


@pytest.fixture
def _base_settings(monkeypatch, tmp_path):
    """Gestiona base configuración."""
    # Gestiona base configuración.
    monkeypatch.setattr(svc.settings, "TEXT_MODERATION_ENABLED", True, raising=False)
    monkeypatch.setattr(svc.settings, "TEXT_MODERATION_FAIL_OPEN", False, raising=False)
    monkeypatch.setattr(
        svc.settings,
        "TEXT_MODERATION_DICTIONARY_DIR",
        str(tmp_path),
        raising=False,
    )
    monkeypatch.setattr(
        svc.settings,
        "TEXT_MODERATION_DICTIONARY_LANGS",
        "es,en",
        raising=False,
    )
    monkeypatch.setattr(
        svc.settings,
        "TEXT_MODERATION_RESERVED_USERNAME_TOKENS",
        "admin,administrator,administrador,support,soporte,moderator,moderador",
        raising=False,
    )
    monkeypatch.setattr(
        svc.settings,
        "TEXT_MODERATION_IGNORE_DICTIONARY_TOKENS",
        "blog,contact,conversation,file,files,filter,footer,footer navigation,github,"
        "insights,issues,navigation,open,pricing,privacy,projects,pull requests,"
        "security,skip to content,terms,training",
        raising=False,
    )
    return tmp_path


class TestValidarNombreUsuario:
    """Agrupa pruebas relacionadas con validar nombre usuario."""

    @pytest.mark.asyncio
    async def test_username_reservado_bloquea(self, _base_settings):
        """Verifica que username reservado bloquea."""
        _write_dicts(
            _base_settings,
            en_words=["bitch"],
            es_words=["puta"],
        )

        with pytest.raises(HTTPException) as exc:
            await svc.validar_nombre_usuario("admin123")

        assert exc.value.status_code == 400
        assert "nombre de usuario" in exc.value.detail.lower()

    @pytest.mark.asyncio
    async def test_username_ingles_bloquea(self, _base_settings):
        """Verifica que username ingles bloquea."""
        _write_dicts(
            _base_settings,
            en_words=["bitch", "whore"],
            es_words=["puta"],
        )

        with pytest.raises(HTTPException) as exc:
            await svc.validar_nombre_usuario("bitch99")

        assert exc.value.status_code == 400

    @pytest.mark.asyncio
    async def test_username_espanol_con_leetspeak_bloquea(self, _base_settings):
        """Verifica que username espanol con leetspeak bloquea."""
        _write_dicts(
            _base_settings,
            en_words=["bitch"],
            es_words=["polla", "puta"],
        )

        with pytest.raises(HTTPException) as exc:
            await svc.validar_nombre_usuario("p0lla69")

        assert exc.value.status_code == 400

    @pytest.mark.asyncio
    async def test_username_limpio_pasa(self, _base_settings):
        """Verifica que username limpio pasa."""
        _write_dicts(
            _base_settings,
            en_words=["bitch"],
            es_words=["puta", "polla"],
        )

        await svc.validar_nombre_usuario("GalenRunner2026")


class TestValidarNombreReal:
    """Agrupa pruebas relacionadas con validar nombre real."""

    @pytest.mark.asyncio
    async def test_nombre_real_con_palabra_espanola_bloquea(self, _base_settings):
        """Verifica que nombre real con palabra espanola bloquea."""
        _write_dicts(
            _base_settings,
            en_words=["bitch"],
            es_words=["puta", "gilipollas"],
        )

        with pytest.raises(HTTPException) as exc:
            await svc.validar_nombre_real("María Puta García")

        assert exc.value.status_code == 400
        assert "nombre real" in exc.value.detail.lower()

    @pytest.mark.asyncio
    async def test_nombre_real_con_palabra_inglesa_bloquea(self, _base_settings):
        """Verifica que nombre real con palabra inglesa bloquea."""
        _write_dicts(
            _base_settings,
            en_words=["bitch", "whore"],
            es_words=["puta"],
        )

        with pytest.raises(HTTPException) as exc:
            await svc.validar_nombre_real("Mary Bitch Johnson")

        assert exc.value.status_code == 400

    @pytest.mark.asyncio
    async def test_nombre_real_limpio_pasa(self, _base_settings):
        """Verifica que nombre real limpio pasa."""
        _write_dicts(
            _base_settings,
            en_words=["bitch"],
            es_words=["puta"],
        )

        await svc.validar_nombre_real("María García")

    @pytest.mark.asyncio
    async def test_frase_exacta_bloquea_nombre_real(self, _base_settings):
        """Verifica que frase exacta bloquea nombre real."""
        _write_dicts(
            _base_settings,
            en_words=["son of a bitch"],
            es_words=["hijo de puta"],
        )

        with pytest.raises(HTTPException) as exc:
            await svc.validar_nombre_real("hijo de puta")

        assert exc.value.status_code == 400


class TestErroresDeDiccionario:
    """Agrupa pruebas relacionadas con errores de diccionario."""

    @pytest.mark.asyncio
    async def test_missing_dictionary_fail_open_deja_pasar(self, monkeypatch, tmp_path):
        """Verifica que missing dictionary fail open deja pasar."""
        # Verifica que missing dictionary fail open deja pasar.
        monkeypatch.setattr(
            svc.settings, "TEXT_MODERATION_ENABLED", True, raising=False
        )
        monkeypatch.setattr(
            svc.settings, "TEXT_MODERATION_FAIL_OPEN", True, raising=False
        )
        monkeypatch.setattr(
            svc.settings,
            "TEXT_MODERATION_DICTIONARY_DIR",
            str(tmp_path / "no-existe"),
            raising=False,
        )
        monkeypatch.setattr(
            svc.settings,
            "TEXT_MODERATION_DICTIONARY_LANGS",
            "es,en",
            raising=False,
        )
        monkeypatch.setattr(
            svc.settings,
            "TEXT_MODERATION_RESERVED_USERNAME_TOKENS",
            "admin,soporte",
            raising=False,
        )
        monkeypatch.setattr(
            svc.settings,
            "TEXT_MODERATION_IGNORE_DICTIONARY_TOKENS",
            "",
            raising=False,
        )

        await svc.validar_nombre_real("María García")

    @pytest.mark.asyncio
    async def test_missing_dictionary_fail_closed_devuelve_503(
        self, monkeypatch, tmp_path
    ):
        """Verifica que missing dictionary fail closed devuelve 503."""
        # Verifica que missing dictionary fail closed devuelve 503.
        monkeypatch.setattr(
            svc.settings, "TEXT_MODERATION_ENABLED", True, raising=False
        )
        monkeypatch.setattr(
            svc.settings, "TEXT_MODERATION_FAIL_OPEN", False, raising=False
        )
        monkeypatch.setattr(
            svc.settings,
            "TEXT_MODERATION_DICTIONARY_DIR",
            str(tmp_path / "no-existe"),
            raising=False,
        )
        monkeypatch.setattr(
            svc.settings,
            "TEXT_MODERATION_DICTIONARY_LANGS",
            "es,en",
            raising=False,
        )
        monkeypatch.setattr(
            svc.settings,
            "TEXT_MODERATION_RESERVED_USERNAME_TOKENS",
            "admin,soporte",
            raising=False,
        )
        monkeypatch.setattr(
            svc.settings,
            "TEXT_MODERATION_IGNORE_DICTIONARY_TOKENS",
            "",
            raising=False,
        )

        with pytest.raises(HTTPException) as exc:
            await svc.validar_nombre_real("María García")

        assert exc.value.status_code == 503
        assert "no se pudo validar" in exc.value.detail.lower()
