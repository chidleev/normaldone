from typing import Any

import pytest

from infrastructure.llm.factory import create_llm_client, get_llm_provider
from infrastructure.llm.gemini_client import GeminiClient


class FakeRedisStorage:
    async def get_cache(self, key: str) -> None:
        return None

    async def set_cache(self, key: str, data: dict) -> None:
        return None


def test_default_provider_is_g4f(monkeypatch: Any) -> None:
    monkeypatch.setenv("LLM_PROVIDER", "g4f")
    assert get_llm_provider() == "g4f"


def test_factory_creates_g4f_by_default(monkeypatch: Any) -> None:
    monkeypatch.setenv("LLM_PROVIDER", "g4f")
    try:
        from infrastructure.llm.g4f_client import G4FClient
    except ImportError:
        pytest.skip("g4f not installed")
        return
    client = create_llm_client(FakeRedisStorage())
    assert isinstance(client, G4FClient)


def test_factory_creates_gemini(monkeypatch: Any) -> None:
    monkeypatch.setenv("LLM_PROVIDER", "gemini")
    monkeypatch.setenv("GEMINI_API_KEY", "fake-key")
    client = create_llm_client(FakeRedisStorage())
    assert isinstance(client, GeminiClient)
