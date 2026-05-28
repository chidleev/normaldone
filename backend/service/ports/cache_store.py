"""Порт кэширования ответов LLM."""

from __future__ import annotations

from typing import Any, Protocol


class CacheStorePort(Protocol):
    """Контракт для кэша структурированных ответов."""

    async def get_cache(self, key: str) -> dict[str, Any] | None: ...

    async def set_cache(self, key: str, data: dict[str, Any]) -> None: ...
