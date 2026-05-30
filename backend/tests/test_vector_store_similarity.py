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
        "original_items": [],
        "original_item_values": {},
        "attribute_merge": {},
        "attribute_merge_separators": {},
        "matched_by": "local",
    }
    assert matches[1] is None
    assert matches[2] is None

    calls = storage.client.query_points.call_args_list
    assert calls[0].kwargs["score_threshold"] == 0.85
    assert calls[0].kwargs["using"] == "local"


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
        local_vectors=[[0.1, 0.2]],
        gemini_vectors=None,
        attributes=[{"бренд": "X"}],
        cluster_names=["Фильтры"],
    )

    storage.save_items(
        texts=["Товар B"],
        local_vectors=[[0.2, 0.3]],
        gemini_vectors=[[0.9, 1.0]],
        attributes=[{"бренд": "Y"}],
        cluster_names=["Фильтры"],
        original_items_list=[["Исходное B"]],
        original_item_values_list=[{"Исходное B": {"бренд": "Y", "артикул": "B-1"}}],
        attribute_merge_list=[{"бренд": "accumulative"}],
        attribute_merge_separators_list=[{"бренд": "; "}],
    )
    point = storage.client.upsert.call_args.kwargs["points"][0]
    assert point.payload["cluster_name"] == "Фильтры"
    assert point.payload["attributes"] == {"бренд": "Y"}
    assert point.vector["local"] == [0.2, 0.3]
    assert point.vector["gemini"] == [0.9, 1.0]
    assert point.payload["original_items"] == ["Исходное B"]
    assert point.payload["original_item_values"] == {"Исходное B": {"бренд": "Y", "артикул": "B-1"}}
    assert point.payload["attribute_merge"] == {"бренд": "accumulative"}
    assert point.payload["attribute_merge_separators"] == {"бренд": ";"}


def test_find_similar_prefers_original_items_payload_match() -> None:
    storage = VectorStorage.__new__(VectorStorage)
    storage.collection_name = "test"
    storage.client = MagicMock()
    storage.client.collection_exists.return_value = True

    vector_point = MagicMock()
    vector_point.payload = {
        "text": "Векторный матч",
        "cluster_name": "Кластер Вектор",
        "attributes": {"бренд": "VectorBrand"},
        "original_items": ["Другая строка"],
    }
    payload_point = MagicMock()
    payload_point.payload = {
        "text": "Память фильтр Donaldson",
        "cluster_name": "Фильтры",
        "attributes": {"бренд": "Donaldson"},
        "original_items": ["Фильтр масляный P551551"],
    }

    storage.client.query_points.return_value = MagicMock(points=[vector_point])
    storage.client.scroll.return_value = ([payload_point], None)

    match = storage.find_similar(
        [[0.1, 0.2]],
        [[0.7, 0.8]],
        item_texts=["ФИЛЬТР   масляный   P551551"],
        threshold=0.15,
    )[0]

    assert match is not None
    assert match["text"] == "Память фильтр Donaldson"
    assert match["cluster_name"] == "Фильтры"
    assert match["attributes"] == {"бренд": "Donaldson"}
    assert match["matched_by"] == "payload"


def test_find_similar_prefers_gemini_then_fallbacks_to_local() -> None:
    storage = VectorStorage.__new__(VectorStorage)
    storage.collection_name = "test"
    storage.client = MagicMock()
    storage.client.collection_exists.return_value = True
    storage.client.scroll.return_value = ([], None)

    gemini_point = MagicMock()
    gemini_point.payload = {
        "text": "Gemini матч",
        "cluster_name": "Gemini Cluster",
        "attributes": {"бренд": "GemBrand"},
    }
    local_point = MagicMock()
    local_point.payload = {
        "text": "Local матч",
        "cluster_name": "Local Cluster",
        "attributes": {"бренд": "LocBrand"},
    }
    storage.client.query_points.side_effect = [
        MagicMock(points=[gemini_point]),
        RuntimeError("gemini unavailable"),
        MagicMock(points=[local_point]),
    ]

    match_gemini = storage.find_similar([[0.1]], [[0.7]])[0]
    match_local = storage.find_similar([[0.2]], [[0.8]])[0]

    assert match_gemini is not None
    assert match_gemini["text"] == "Gemini матч"
    assert match_gemini["matched_by"] == "gemini"
    assert match_local is not None
    assert match_local["text"] == "Local матч"
    assert match_local["matched_by"] == "local"


def test_search_local_returns_ranked_matches() -> None:
    storage = VectorStorage.__new__(VectorStorage)
    storage.collection_name = "test"
    storage.client = MagicMock()
    storage.client.collection_exists.return_value = True

    point_a = MagicMock()
    point_a.payload = {
        "text": "Фильтр Donaldson",
        "cluster_name": "Фильтры",
        "attributes": {"бренд": "Donaldson"},
    }
    point_a.score = 0.93
    point_b = MagicMock()
    point_b.payload = {
        "text": "Кабель IEK",
        "cluster_name": "Кабели",
        "attributes": {"бренд": "IEK"},
    }
    point_b.score = 0.81
    storage.client.query_points.return_value = MagicMock(points=[point_a, point_b])

    rows = storage.search_local([0.1, 0.2], limit=2)

    assert rows == [
        {
            "text": "Фильтр Donaldson",
            "cluster_name": "Фильтры",
            "relevance": 0.93,
        },
        {
            "text": "Кабель IEK",
            "cluster_name": "Кабели",
            "relevance": 0.81,
        },
    ]
    call = storage.client.query_points.call_args
    assert call.kwargs["using"] == "local"
    assert call.kwargs["limit"] == 2
