from infrastructure.ml.ml_config import (
    read_cluster_distance_threshold,
    read_enriched_dedup_threshold,
)


def test_cluster_distance_threshold_from_env(monkeypatch) -> None:
    monkeypatch.setenv("CLUSTERIZE_DISTANCE_THRESHOLD", "0.25")
    assert read_cluster_distance_threshold() == 0.25


def test_cluster_distance_threshold_default(monkeypatch) -> None:
    monkeypatch.delenv("CLUSTERIZE_DISTANCE_THRESHOLD", raising=False)
    monkeypatch.delenv("CLUSTER_DISTANCE_THRESHOLD", raising=False)
    assert read_cluster_distance_threshold() == 0.2
