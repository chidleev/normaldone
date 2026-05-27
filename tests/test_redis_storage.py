import asyncio
from typing import Any

from infrastructure.db.redis_client import RedisStorage


class FakeRedisClient:
    def __init__(self) -> None:
        self.data: dict[str, str] = {}

    async def setex(self, key: str, ttl: int, value: str) -> None:
        _ = ttl
        self.data[key] = value

    async def get(self, key: str) -> str | None:
        return self.data.get(key)

    async def flushdb(self) -> None:
        self.data.clear()

    async def aclose(self) -> None:
        return None


def test_redis_storage_task_and_cache_methods(monkeypatch: Any) -> None:
    fake_client = FakeRedisClient()
    monkeypatch.setenv("REDIS_URL", "redis://fake:6379/0")
    monkeypatch.setattr(
        "infrastructure.db.redis_client.Redis.from_url",
        lambda *args, **kwargs: fake_client,
    )

    async def _run() -> None:
        storage = RedisStorage()
        await storage.set_task_state("123", {"status": "PENDING"})
        task_state = await storage.get_task_state("123")
        assert task_state == {"status": "PENDING"}

        await storage.set_cache("k1", {"v": 1})
        cached = await storage.get_cache("k1")
        assert cached == {"v": 1}

        await storage.flushdb()
        assert await storage.get_task_state("123") is None
        assert await storage.get_cache("k1") is None
        await storage.close()

    asyncio.run(_run())
