"""Порт локальной кластеризации товаров."""

from __future__ import annotations

from typing import Any, Protocol


class ClusterizerPort(Protocol):
    """Контракт для группировки товаров по векторам."""

    def clusterize(
        self,
        items: list[str],
        vectors: list[list[float]],
    ) -> list[dict[str, Any]]: ...
