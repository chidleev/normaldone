"""Пороги расстояний для ML-кластеризации и дедупликации (из env)."""

from __future__ import annotations

import os


def _env_float(*keys: str, default: float) -> float:
    for key in keys:
        raw = os.getenv(key)
        if raw is not None and str(raw).strip():
            try:
                return float(raw)
            except ValueError:
                continue
    return default


def read_cluster_distance_threshold() -> float:
    """
    Порог agglomerative clustering (косинусное расстояние).

    CLUSTERIZE_DISTANCE_THRESHOLD — меньше значение → больше мелких кластеров.
    По умолчанию 0.2 (similarity >= 0.8 для объединения).
    """
    return _env_float("CLUSTERIZE_DISTANCE_THRESHOLD", "CLUSTER_DISTANCE_THRESHOLD", default=0.2)


def read_enriched_dedup_threshold() -> float:
    """Порог дедупликации обогащённых имён после нормализации."""
    return _env_float("ENRICHED_DEDUP_THRESHOLD", default=0.15)
