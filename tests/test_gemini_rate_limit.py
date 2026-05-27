import asyncio
from types import SimpleNamespace
from typing import Any

import pytest

from infrastructure.llm.gemini_client import BATCH_SIZE, GeminiClient


class FakeRedisStorage:
    def __init__(self) -> None:
        self.cache: dict[str, dict[str, Any]] = {}

    async def get_cache(self, key: str) -> dict[str, Any] | None:
        return self.cache.get(key)

    async def set_cache(self, key: str, data: dict[str, Any]) -> None:
        self.cache[key] = data


class FakeModels:
    def __init__(self, fail_times: int = 0) -> None:
        self.calls = 0
        self.fail_times = fail_times

    def generate_content(self, **kwargs: Any) -> SimpleNamespace:
        _ = kwargs
        self.calls += 1
        if self.calls <= self.fail_times:
            raise RuntimeError("429 Too Many Requests")
        return SimpleNamespace(
            text='{"normalized":[{"item":"x","values":{"вес":"1 кг"}}]}'
        )


class FakeGenAIClient:
    def __init__(self, api_key: str, fail_times: int = 0) -> None:
        _ = api_key
        self.models = FakeModels(fail_times=fail_times)


def test_normalize_items_splits_into_batches(monkeypatch: Any) -> None:
    monkeypatch.setenv("GEMINI_API_KEY", "fake-key")
    monkeypatch.setattr("infrastructure.llm.gemini_client.genai.Client", FakeGenAIClient)

    sleeps: list[float] = []

    async def fake_sleep(seconds: float) -> None:
        sleeps.append(seconds)

    monkeypatch.setattr("infrastructure.llm.gemini_client.asyncio.sleep", fake_sleep)

    async def _run() -> None:
        client = GeminiClient(FakeRedisStorage())
        items = [f"item-{idx}" for idx in range(BATCH_SIZE + 5)]
        result = await client.normalize_items(items, ["вес"])

        assert len(result) == 2
        assert client.client.models.calls == 2
        assert sleeps == [client.request_delay_seconds]

    asyncio.run(_run())


def test_generate_json_retries_on_429(monkeypatch: Any) -> None:
    monkeypatch.setenv("GEMINI_API_KEY", "fake-key")
    monkeypatch.setattr(
        "infrastructure.llm.gemini_client.genai.Client",
        lambda api_key: FakeGenAIClient(api_key, fail_times=1),
    )

    sleeps: list[float] = []

    async def fake_sleep(seconds: float) -> None:
        sleeps.append(seconds)

    monkeypatch.setattr("infrastructure.llm.gemini_client.asyncio.sleep", fake_sleep)

    async def _run() -> None:
        client = GeminiClient(FakeRedisStorage())
        result = await client.normalize_items(["item-1"], ["вес"])

        assert len(result) == 1
        assert client.client.models.calls == 2
        assert client.rate_limit_retry_seconds in sleeps

    asyncio.run(_run())


def test_generate_json_raises_after_max_retries(monkeypatch: Any) -> None:
    monkeypatch.setenv("GEMINI_API_KEY", "fake-key")
    monkeypatch.setattr(
        "infrastructure.llm.gemini_client.genai.Client",
        lambda api_key: FakeGenAIClient(api_key, fail_times=10),
    )
    monkeypatch.setattr("infrastructure.llm.gemini_client.asyncio.sleep", asyncio.sleep)

    async def _run() -> None:
        client = GeminiClient(FakeRedisStorage())
        with pytest.raises(RuntimeError, match="429"):
            await client.normalize_items(["item-1"], ["вес"])
        assert client.client.models.calls == client.max_retries

    asyncio.run(_run())
