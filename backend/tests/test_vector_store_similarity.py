from unittest.mock import MagicMock

from infrastructure.db.vector_store import VectorStorage


def test_find_similar_uses_score_threshold_and_skips_empty_attributes() -> None:
    storage = VectorStorage.__new__(VectorStorage)
    storage.collection_name = "test"
    storage.client = MagicMock()
    storage.client.collection_exists.return_value = True

    good_point = MagicMock()
    good_point.payload = {
        "text": "Кабель IEK",
        "cluster_name": "Кабели",
        "attributes": {"бренд": "IEK"},
    }
    empty_point = MagicMock()
    empty_point.payload = {"attributes": {}, "cluster_name": "X"}

    storage.client.query_points.side_effect = [
        MagicMock(points=[good_point]),
        MagicMock(points=[]),
        MagicMock(points=[empty_point]),
    ]

    matches = storage.find_similar([[0.1], [0.2], [0.3]], threshold=0.15)

    assert matches[0] == {
        "text": "Кабель IEK",
        "cluster_name": "Кабели",
        "attributes": {"бренд": "IEK"},
    }
    assert matches[1] is None
    assert matches[2] is None

    calls = storage.client.query_points.call_args_list
    assert calls[0].kwargs["score_threshold"] == 0.85


def test_find_similar_legacy_payload_without_cluster_name() -> None:
    storage = VectorStorage.__new__(VectorStorage)
    storage.collection_name = "test"
    storage.client = MagicMock()
    storage.client.collection_exists.return_value = True

    legacy_point = MagicMock()
    legacy_point.payload = {"text": "Фильтр", "attributes": {"бренд": "Donaldson"}}

    storage.client.query_points.return_value = MagicMock(points=[legacy_point])

    match = storage.find_similar([[0.1]])[0]
    assert match is not None
    assert match["cluster_name"] == "Память"
    assert match["attributes"]["бренд"] == "Donaldson"


def test_save_items_includes_cluster_name_in_payload() -> None:
    storage = VectorStorage.__new__(VectorStorage)
    storage.collection_name = "test"
    storage.client = MagicMock()
    storage.client.collection_exists.return_value = True

    storage.save_items(
        texts=["Товар A"],
        vectors=[[0.1, 0.2]],
        attributes=[{"бренд": "X"}],
        cluster_names=["Фильтры"],
    )

    point = storage.client.upsert.call_args.kwargs["points"][0]
    assert point.payload["cluster_name"] == "Фильтры"
    assert point.payload["attributes"] == {"бренд": "X"}
