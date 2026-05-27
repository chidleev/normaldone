"""Порт хранения статусов фоновых задач."""

from __future__ import annotations

from typing import Any, Protocol


class TaskStorePort(Protocol):
    """Контракт для чтения/записи состояния задачи."""

    async def set_task_state(self, task_id: str, state: dict[str, Any]) -> None: ...

    async def get_task_state(self, task_id: str) -> dict[str, Any] | None: ...

    async def close(self) -> None: ...
