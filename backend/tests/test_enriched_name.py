from infrastructure.naming.enriched_name import (
    collapse_cluster_rows,
    dedupe_enriched_groups,
    merge_values_by_behavior,
    render_template,
)
from infrastructure.naming.merge_separators import detect_accumulator_separator


def test_render_template_substitutes_named_placeholders() -> None:
    result = render_template(
        "{бренд} фильтр {артикул}",
        {"бренд": "Donaldson", "артикул": "P551551"},
    )
    assert result == "Donaldson фильтр P551551"


def test_render_template_case_insensitive_keys() -> None:
    result = render_template("{Бренд}", {"бренд": "IEK"})
    assert result == "IEK"


def test_render_template_unknown_placeholder_becomes_empty() -> None:
    result = render_template("{бренд} {нет}", {"бренд": "X"})
    assert result == "X"


def test_dedupe_groups_similar_embeddings() -> None:
    entries = [
        {"enriched_name": "Donaldson фильтр P1", "item": "Фильтр A", "values": {}, "source": "ai"},
        {"enriched_name": "Donaldson фильтр P1", "item": "Фильтр B", "values": {}, "source": "ai"},
        {"enriched_name": "IEK кабель", "item": "Кабель C", "values": {}, "source": "ai"},
    ]
    embeddings = [
        [1.0, 0.0],
        [0.99, 0.01],
        [0.0, 1.0],
    ]
    groups = dedupe_enriched_groups(entries, embeddings, threshold=0.15)
    assert len(groups) == 2
    merged = next(g for g in groups if len(g["aliases"]) == 2)
    assert "Фильтр A" in merged["aliases"]
    assert "Фильтр B" in merged["aliases"]


def test_collapse_cluster_rows_keeps_aliases() -> None:
    entries = [
        {"enriched_name": "X", "item": "orig-1", "values": {"бренд": "A"}, "source": "memory"},
    ]
    collapsed = collapse_cluster_rows(entries, [[1.0, 0.0]])
    assert collapsed[0]["enriched_name"] == "X"
    assert collapsed[0]["aliases"] == ["orig-1"]
    assert collapsed[0]["members"][0]["item"] == "orig-1"


def test_merge_values_priority_keeps_first() -> None:
    target = {"бренд": "A"}
    merge_values_by_behavior(target, {"бренд": "B"}, {}, "бренд")
    assert target["бренд"] == "A"


def test_merge_values_accumulative_joins_with_semicolon() -> None:
    target = {"цвет": "красный; синий"}
    merge_values_by_behavior(
        target,
        {"цвет": "зеленый"},
        {"цвет": "accumulative"},
        "цвет",
    )
    assert target["цвет"] == "красный; синий; зеленый"


def test_merge_values_accumulative_joins_with_comma() -> None:
    target = {"цвет": "красный, синий"}
    merge_values_by_behavior(
        target,
        {"цвет": "зеленый"},
        {"цвет": "accumulative"},
        "цвет",
    )
    assert target["цвет"] == "красный, синий, зеленый"


def test_merge_values_accumulative_explicit_separator() -> None:
    target = {"тег": "a|b"}
    merge_values_by_behavior(
        target,
        {"тег": "c"},
        {"тег": "accumulative"},
        "тег",
        attribute_merge_separators={"тег": " | "},
    )
    assert target["тег"] == "a | b | c"


def test_detect_accumulator_separator_prefers_comma() -> None:
    assert detect_accumulator_separator("красный, синий", "зеленый") == ", "


def test_dedupe_merge_accumulative_attribute() -> None:
    entries = [
        {
            "enriched_name": "Same",
            "item": "A",
            "values": {"код": "1"},
            "source": "ai",
        },
        {
            "enriched_name": "Same",
            "item": "B",
            "values": {"код": "2"},
            "source": "ai",
        },
    ]
    embeddings = [[1.0, 0.0], [0.99, 0.01]]
    groups = dedupe_enriched_groups(
        entries,
        embeddings,
        threshold=0.15,
        attribute_merge={"код": "accumulative"},
    )
    assert len(groups) == 1
    assert groups[0]["values"]["код"] == "1; 2"
    assert len(groups[0]["members"]) == 2


def test_dedupe_merge_accumulative_comma_separator() -> None:
    entries = [
        {
            "enriched_name": "Same",
            "item": "A",
            "values": {"цвет": "красный, синий"},
            "source": "ai",
        },
        {
            "enriched_name": "Same",
            "item": "B",
            "values": {"цвет": "зеленый"},
            "source": "ai",
        },
    ]
    embeddings = [[1.0, 0.0], [0.99, 0.01]]
    groups = dedupe_enriched_groups(
        entries,
        embeddings,
        threshold=0.15,
        attribute_merge={"цвет": "accumulative"},
    )
    assert groups[0]["values"]["цвет"] == "красный, синий, зеленый"
