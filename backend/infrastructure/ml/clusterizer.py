"""Локальная группировка товаров на основе эмбеддингов."""

from __future__ import annotations

from collections import defaultdict
from typing import Any

from sklearn.cluster import AgglomerativeClustering

from infrastructure.ml.ml_config import read_cluster_distance_threshold


class ItemClusterizer:
    """Кластеризатор товаров по косинусному расстоянию эмбеддингов."""

    def __init__(self, distance_threshold: float | None = None) -> None:
        """Настраивает агломеративную кластеризацию без фиксированного числа групп."""
        threshold = (
            distance_threshold
            if distance_threshold is not None
            else read_cluster_distance_threshold()
        )
        self.distance_threshold = threshold
        self.model = AgglomerativeClustering(
            n_clusters=None,
            metric="cosine",
            linkage="average",
            distance_threshold=threshold,
        )

    def clusterize(
        self,
        items: list[str],
        vectors: list[list[float]],
    ) -> list[dict[str, Any]]:
        """Возвращает список групп в формате {'cluster_items': [...]}."""
        if len(items) != len(vectors):
            raise ValueError("items и vectors должны быть одной длины")
        if not items:
            return []
        if len(items) == 1:
            return [{"cluster_items": [items[0]]}]

        labels = self.model.fit_predict(vectors)
        grouped: dict[int, list[str]] = defaultdict(list)
        for item, label in zip(items, labels, strict=True):
            grouped[int(label)].append(item)

        return [{"cluster_items": cluster_items} for cluster_items in grouped.values()]
