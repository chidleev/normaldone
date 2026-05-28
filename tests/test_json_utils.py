import json

import pytest

from infrastructure.llm.json_utils import extract_json_object


def test_extract_json_from_markdown_fence() -> None:
    raw = '```json\n{"attributes": ["бренд", "тип"]}\n```'
    data = extract_json_object(raw)
    assert data == {"attributes": ["бренд", "тип"]}


def test_extract_json_from_top_level_array() -> None:
    raw = '[{"item": "a", "values": {"бренд": "X"}}]'
    data = extract_json_object(raw)
    assert data["normalized"][0]["item"] == "a"


def test_extract_attributes_array_only() -> None:
    raw = '["тип", "материал", "размер"]'
    data = extract_json_object(raw)
    assert data == {"attributes": ["тип", "материал", "размер"]}


def test_empty_response_raises() -> None:
    with pytest.raises(json.JSONDecodeError):
        extract_json_object("   ")
