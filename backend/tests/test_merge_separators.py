from infrastructure.naming.merge_separators import (
    detect_accumulator_separator,
    merge_accumulator_values,
    normalize_merge_separator,
    split_accumulator_parts,
)


def test_split_accumulator_parts_multiseparator() -> None:
    assert split_accumulator_parts("красный, синий; голубой") == [
        "красный",
        "синий",
        "голубой",
    ]


def test_normalize_merge_separator() -> None:
    assert normalize_merge_separator(",") == ", "
    assert normalize_merge_separator("") is None


def test_merge_accumulator_values_auto_comma() -> None:
    result = merge_accumulator_values("красный, синий", "зеленый", None)
    assert result == "красный, синий, зеленый"
