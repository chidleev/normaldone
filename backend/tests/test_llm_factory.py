from typing import Any

import pytest

from infrastructure.llm.factory import create_llm_client, resolve_llm_provider
from infrastructure.llm.gemini_client import GeminiClient


class FakeRedisStorage:
    async def get_cache(self, key: str) -> None:
        return None

    async def set_cache(self, key: str, data: dict) -> None:
        return None


def test_resolve_provider_alias() -> None:
    assert resolve_llm_provider("gpt-4") == "g4f"


def test_factory_creates_g4f_by_provider() -> None:
    try:
        from infrastructure.llm.g4f_client import G4FClient
    except ImportError:
        pytest.skip("g4f not installed")
        return
    client = create_llm_client(FakeRedisStorage(), "g4f")
    assert isinstance(client, G4FClient)


def test_factory_creates_gemini(monkeypatch: Any) -> None:
    monkeypatch.setenv("GEMINI_API_KEY", "fake-key")
    client = create_llm_client(FakeRedisStorage(), "gemini")
    assert isinstance(client, GeminiClient)
