"""Асинхронное хранилище задач и кэша на Redis."""

from __future__ import annotations

import json
import os
from typing import Any

from dotenv import load_dotenv
from redis.asyncio import Redis


class RedisStorage:
    """Управляет статусами задач и кэшем ответов Gemini в Redis."""

    TASK_TTL_SECONDS = 24 * 60 * 60
    CACHE_TTL_SECONDS = 30 * 24 * 60 * 60

    def __init__(self) -> None:
        """Инициализирует асинхронный клиент Redis из REDIS_URL."""
        load_dotenv()
        redis_url = os.getenv("REDIS_URL")
        if not redis_url:
            raise ValueError("REDIS_URL is not set in environment")
        self.redis: Redis = Redis.from_url(redis_url, decode_responses=True)

    @staticmethod
    def _task_key(task_id: str) -> str:
        return f"task:{task_id}"

    @staticmethod
    def _cache_key(key: str) -> str:
        return f"gemini_cache:{key}"

    async def set_task_state(self, task_id: str, state: dict[str, Any]) -> None:
        """Сохраняет состояние задачи с TTL 24 часа."""
        await self.redis.setex(
            self._task_key(task_id),
            self.TASK_TTL_SECONDS,
            json.dumps(state, ensure_ascii=False),
        )

    async def get_task_state(self, task_id: str) -> dict[str, Any] | None:
        """Возвращает состояние задачи или None, если ключа нет."""
        raw = await self.redis.get(self._task_key(task_id))
        if raw is None:
            return None
        return json.loads(raw)

    async def set_cache(self, key: str, data: dict[str, Any]) -> None:
        """Сохраняет кэшированный ответ Gemini с TTL 30 дней."""
        await self.redis.setex(
            self._cache_key(key),
            self.CACHE_TTL_SECONDS,
            json.dumps(data, ensure_ascii=False),
        )

    async def get_cache(self, key: str) -> dict[str, Any] | None:
        """Возвращает кэшированный ответ Gemini или None."""
        raw = await self.redis.get(self._cache_key(key))
        if raw is None:
            return None
        return json.loads(raw)

    async def flushdb(self) -> None:
        """Полностью очищает текущую Redis DB."""
        await self.redis.flushdb()

    async def close(self) -> None:
        """Корректно закрывает соединение с Redis."""
        await self.redis.aclose()
