"""Парсинг JSON из ответов LLM."""

from __future__ import annotations

import json
import re
from typing import Any


def _try_parse_json(text: str) -> Any:
    return json.loads(text)


def _wrap_parsed(parsed: Any) -> dict[str, Any]:
    if isinstance(parsed, dict):
        return parsed
    if isinstance(parsed, list):
        if parsed and isinstance(parsed[0], str):
            return {"attributes": parsed}
        return {"normalized": parsed}
    raise json.JSONDecodeError("Unexpected JSON root type", str(parsed), 0)


def extract_json_object(text: str) -> dict[str, Any]:
    """Извлекает JSON-объект из ответа (в т.ч. из markdown-блока)."""
    cleaned = text.strip()
    if not cleaned:
        raise json.JSONDecodeError("Empty LLM response", "", 0)

    fence_match = re.search(r"```(?:json)?\s*([\s\S]*?)\s*```", cleaned, re.IGNORECASE)
    if fence_match:
        cleaned = fence_match.group(1).strip()

    try:
        return _wrap_parsed(_try_parse_json(cleaned))
    except json.JSONDecodeError:
        pass

    start = cleaned.find("{")
    end = cleaned.rfind("}")
    if start != -1 and end != -1 and end > start:
        try:
            return _wrap_parsed(_try_parse_json(cleaned[start : end + 1]))
        except json.JSONDecodeError:
            pass

    for pattern in (
        r'"attributes"\s*:\s*(\[[\s\S]*?\])',
        r'"normalized"\s*:\s*(\[[\s\S]*\])',
    ):
        match = re.search(pattern, cleaned, re.IGNORECASE)
        if not match:
            continue
        key = "attributes" if "attributes" in pattern else "normalized"
        try:
            array_value = _try_parse_json(match.group(1))
        except json.JSONDecodeError:
            continue
        return {key: array_value}

    array_only = cleaned.find("[")
    if array_only != -1:
        try:
            return _wrap_parsed(_try_parse_json(cleaned[array_only:]))
        except json.JSONDecodeError:
            pass

    raise json.JSONDecodeError("Cannot extract JSON object", cleaned[:500], 0)
