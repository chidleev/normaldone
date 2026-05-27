import asyncio
from types import SimpleNamespace
from typing import Any

from infrastructure.llm.gemini_client import GeminiClient


class FakeRedisStorage:
    def __init__(self) -> None:
        self.cache: dict[str, dict[str, Any]] = {}

    async def get_cache(self, key: str) -> dict[str, Any] | None:
        return self.cache.get(key)

    async def set_cache(self, key: str, data: dict[str, Any]) -> None:
        self.cache[key] = data


class FakeModels:
    def __init__(self) -> None:
        self.calls = 0

    def generate_content(self, **kwargs: Any) -> SimpleNamespace:
        _ = kwargs
        self.calls += 1
        return SimpleNamespace(text='{"attributes":["бренд","модель"]}')


class FakeGenAIClient:
    def __init__(self, api_key: str) -> None:
        _ = api_key
        self.models = FakeModels()


def test_gemini_client_uses_cache(monkeypatch: Any) -> None:
    monkeypatch.setenv("GEMINI_API_KEY", "fake-key")
    monkeypatch.setattr("infrastructure.llm.gemini_client.genai.Client", FakeGenAIClient)

    async def _run() -> None:
        redis = FakeRedisStorage()
        client = GeminiClient(redis)

        result1 = await client.get_cluster_attributes(["item-a", "item-b"], ["бренд"])
        result2 = await client.get_cluster_attributes(["item-a", "item-b"], ["бренд"])

        assert result1 == ["бренд", "модель"]
        assert result2 == ["бренд", "модель"]
        assert client.client.models.calls == 1

    asyncio.run(_run())
