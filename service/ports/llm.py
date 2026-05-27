"""Порт LLM для подбора атрибутов и нормализации."""

from __future__ import annotations

from typing import Any, Protocol


class LLMPort(Protocol):
    """Контракт взаимодействия с внешней языковой моделью."""

    async def get_cluster_attributes(
        self,
        items: list[str],
        base_attrs: list[str],
    ) -> list[str]: ...

    async def normalize_items(
        self,
        items: list[str],
        attributes: list[str],
    ) -> list[dict[str, Any]]: ...
