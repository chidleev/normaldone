from api.ui_router import _build_default_clusters, _clusters_from_known_items


def test_clusters_from_known_items_groups_by_cluster_name() -> None:
    known = [
        {
            "item": "Фильтр A",
            "cluster_name": "Фильтры топливные",
            "attributes": {"бренд": "Donaldson", "артикул": "P1"},
        },
        {
            "item": "Фильтр B",
            "cluster_name": "Фильтры топливные",
            "attributes": {"бренд": "Donaldson", "артикул": "P2"},
        },
        {
            "item": "Кабель C",
            "cluster_name": "Кабели",
            "attributes": {"бренд": "IEK"},
        },
    ]

    clusters = _clusters_from_known_items(known, base_attributes=["бренд"])

    assert len(clusters) == 2
    filters = next(c for c in clusters if c["name"] == "Фильтры топливные")
    assert len(filters["items"]) == 2
    assert filters["rows"][0]["values"]["артикул"] == "P1"
    assert filters["rows"][0]["source"] == "memory"
    assert filters["rows"][1]["values"]["артикул"] == "P2"
    assert filters["rows"][1]["source"] == "memory"


def test_build_default_clusters_merges_known_into_one_cluster() -> None:
    result = {
        "base_attributes": ["бренд"],
        "new_item_clusters": [],
        "known_items": [
            {
                "item": "A",
                "cluster_name": "Группа 1",
                "attributes": {"бренд": "X"},
            },
            {
                "item": "B",
                "cluster_name": "Группа 1",
                "attributes": {"бренд": "Y"},
            },
        ],
    }

    clusters = _build_default_clusters(result)

    assert len(clusters) == 1
    assert clusters[0]["name"] == "Группа 1"
    assert clusters[0]["items"] == ["A", "B"]
    assert len(clusters[0]["rows"]) == 2
    assert all(row["source"] == "memory" for row in clusters[0]["rows"])


def test_build_default_clusters_marks_new_clusters_as_ai() -> None:
    result = {
        "base_attributes": ["бренд"],
        "new_item_clusters": [
            {
                "category": "Фильтры",
                "attributes": ["бренд"],
                "cluster_items": ["A", "B"],
            }
        ],
        "known_items": [],
    }

    clusters = _build_default_clusters(result)

    assert len(clusters) == 1
    assert clusters[0]["rows"][0]["source"] == "ai"
    assert clusters[0]["rows"][1]["source"] == "ai"
