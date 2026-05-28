from unittest.mock import MagicMock

from infrastructure.db.vector_store import VectorStorage


def test_find_similar_uses_score_threshold_and_skips_empty_attributes() -> None:
    storage = VectorStorage.__new__(VectorStorage)
    storage.collection_name = "test"
    storage.client = MagicMock()
    storage.client.collection_exists.return_value = True

    good_point = MagicMock()
    good_point.payload = {"attributes": {"бренд": "IEK"}}
    weak_point = MagicMock()
    weak_point.payload = {"attributes": {"бренд": "X"}}
    empty_point = MagicMock()
    empty_point.payload = {"attributes": {}}

    storage.client.query_points.side_effect = [
        MagicMock(points=[good_point]),
        MagicMock(points=[]),
        MagicMock(points=[empty_point]),
    ]

    matches = storage.find_similar([[0.1], [0.2], [0.3]], threshold=0.15)

    assert matches[0] == {"бренд": "IEK"}
    assert matches[1] is None
    assert matches[2] is None

    calls = storage.client.query_points.call_args_list
    assert calls[0].kwargs["score_threshold"] == 0.85
