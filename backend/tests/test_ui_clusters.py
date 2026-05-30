from api.ui_router import (
    _build_default_clusters,
    _cluster_export_rows,
    _cluster_from_memory_points,
    _clusters_from_known_items,
    _normalize_cluster_attribute_mode,
    _normalize_selected_cluster_indexes,
    _extract_resume_indexes,
    _normalize_mode,
)


def test_clusters_from_known_items_groups_by_cluster_name() -> None:
    known = [
        {
            "item": "Фильтр A",
            "enriched_name": "Donaldson фильтр P1",
            "cluster_name": "Фильтры топливные",
            "attributes": {"бренд": "Donaldson", "артикул": "P1"},
            "original_items": ["Фильтр A", "FILTER A"],
        },
        {
            "item": "Фильтр B",
            "enriched_name": "Donaldson фильтр P1",
            "cluster_name": "Фильтры топливные",
            "attributes": {"бренд": "Donaldson", "артикул": "P2"},
            "original_items": ["Фильтр B"],
        },
        {
            "item": "Кабель C",
            "enriched_name": "IEK кабель",
            "cluster_name": "Кабели",
            "attributes": {"бренд": "IEK"},
            "original_items": ["Кабель C"],
        },
    ]

    clusters = _clusters_from_known_items(known, base_attributes=["бренд"])

    assert len(clusters) == 2
    filters = next(c for c in clusters if c["name"] == "Фильтры топливные")
    assert len(filters["items"]) == 1
    assert filters["rows"][0]["enriched_name"] == "Donaldson фильтр P1"
    assert filters["rows"][0]["aliases"] == ["Фильтр A", "FILTER A", "Фильтр B"]
    assert filters["rows"][0]["values"]["артикул"] == "P1"
    assert filters["rows"][0]["source"] == "memory"
    assert len(filters["rows"][0]["members"]) == 3


def test_clusters_from_known_items_preserves_merge_and_member_values() -> None:
    known = [
        {
            "item": "Фильтр A",
            "enriched_name": "Donaldson фильтр P1",
            "cluster_name": "Фильтры",
            "attributes": {"бренд": "Donaldson", "артикул": "P1"},
            "original_items": ["Фильтр A", "Фильтр B"],
            "original_item_values": {
                "Фильтр A": {"бренд": "Donaldson", "артикул": "P1"},
                "Фильтр B": {"бренд": "Donaldson", "артикул": "P2"},
            },
            "attribute_merge": {"бренд": "accumulative"},
            "attribute_merge_separators": {"бренд": " / "},
        }
    ]

    clusters = _clusters_from_known_items(known, base_attributes=["бренд", "артикул"])
    assert len(clusters) == 1
    cluster = clusters[0]
    assert cluster["attribute_merge"] == {"бренд": "accumulative"}
    assert cluster["attribute_merge_separators"] == {"бренд": "/"}
    row = cluster["rows"][0]
    by_item = {member["item"]: member["values"] for member in row["members"]}
    assert by_item["Фильтр A"]["артикул"] == "P1"
    assert by_item["Фильтр B"]["артикул"] == "P2"


def test_build_default_clusters_merges_known_into_one_cluster() -> None:
    result = {
        "base_attributes": ["бренд"],
        "new_item_clusters": [],
        "known_items": [
            {
                "item": "A",
                "enriched_name": "Group1 товар",
                "cluster_name": "Группа 1",
                "attributes": {"бренд": "X"},
                "original_items": ["A", "A old"],
            },
            {
                "item": "B",
                "enriched_name": "Group1 товар",
                "cluster_name": "Группа 1",
                "attributes": {"бренд": "Y"},
                "original_items": ["B"],
            },
        ],
    }

    clusters = _build_default_clusters(result)

    assert len(clusters) == 1
    assert clusters[0]["name"] == "Группа 1"
    assert clusters[0]["items"] == ["Group1 товар"]
    assert len(clusters[0]["rows"]) == 1
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


def test_cluster_from_memory_points_restores_attribute_merge_settings() -> None:
    cluster = _cluster_from_memory_points(
        "Фильтры",
        points=[
            {
                "text": "Donaldson фильтр P1",
                "original_items": ["Фильтр A"],
                "attributes": {"бренд": "Donaldson"},
                "attribute_merge": {"бренд": "accumulative"},
                "attribute_merge_separators": {"бренд": " / "},
            }
        ],
        base_attributes=["бренд"],
    )

    assert cluster["attribute_merge"] == {"бренд": "accumulative"}
    assert cluster["attribute_merge_separators"] == {"бренд": "/"}


def test_cluster_from_memory_points_preserves_member_specific_values() -> None:
    cluster = _cluster_from_memory_points(
        "Фильтры",
        points=[
            {
                "text": "Donaldson фильтр P1",
                "original_items": ["Фильтр A", "Фильтр B"],
                "attributes": {"бренд": "Donaldson", "артикул": "P1"},
                "original_item_values": {
                    "Фильтр A": {"бренд": "Donaldson", "артикул": "P1"},
                    "Фильтр B": {"бренд": "Donaldson", "артикул": "P2"},
                },
            }
        ],
        base_attributes=["бренд", "артикул"],
    )

    row = cluster["rows"][0]
    by_item = {member["item"]: member["values"] for member in row["members"]}
    assert by_item["Фильтр A"]["артикул"] == "P1"
    assert by_item["Фильтр B"]["артикул"] == "P2"


def test_cluster_export_rows_keeps_only_merged_rows_when_rows_exist() -> None:
    cluster = {
        "attributes": ["бренд", "артикул"],
        "items": ["Фильтр A", "Фильтр B"],
        "rows": [
            {
                "enriched_name": "Donaldson фильтр P1",
                "aliases": ["Фильтр A", "Фильтр B"],
                "values": {"бренд": "Donaldson", "артикул": "P1"},
            }
        ],
    }

    attributes, rows_out = _cluster_export_rows(cluster, normalized_map={})

    assert attributes == ["бренд", "артикул"]
    assert rows_out == [["Donaldson фильтр P1", "Фильтр A; Фильтр B", "Donaldson", "P1"]]


def test_extract_resume_indexes_filters_invalid_values() -> None:
    result = {
        "completed_cluster_indexes": [0, 2, 2, -1, "x", 100],
    }
    assert _extract_resume_indexes(result, total_clusters=3) == [0, 2]


def test_normalize_mode_validation() -> None:
    assert _normalize_mode("resume") == "resume"
    assert _normalize_mode("RESTART") == "restart"


def test_normalize_cluster_attribute_mode_validation() -> None:
    assert _normalize_cluster_attribute_mode("all") == "all"
    assert _normalize_cluster_attribute_mode("missing") == "missing"
    assert _normalize_cluster_attribute_mode(None) == "default"


def test_normalize_selected_cluster_indexes_defaults_to_all() -> None:
    assert _normalize_selected_cluster_indexes([], total_clusters=3) == [0, 1, 2]


def test_normalize_selected_cluster_indexes_deduplicates_and_sorts_by_input_order() -> None:
    assert _normalize_selected_cluster_indexes([2, 1, 2, 0], total_clusters=3) == [2, 1, 0]
