"""Общие константы и утилиты лимитирования LLM-запросов."""

from __future__ import annotations

BATCH_SIZE = 18
NORMALIZE_BATCH_SIZE = 8
REQUEST_DELAY_SECONDS = 4
RATE_LIMIT_RETRY_SECONDS = 15
MAX_RETRIES = 3


def chunk_items(items: list[str], batch_size: int = BATCH_SIZE) -> list[list[str]]:
    """Разбивает список товаров на батчи по 15–20 позиций."""
    if not items:
        return []
    return [items[idx : idx + batch_size] for idx in range(0, len(items), batch_size)]


def is_retriable_llm_error(exc: BaseException) -> bool:
    """Ошибки, при которых имеет смысл повторить запрос к LLM."""
    if is_rate_limit_error(exc):
        return True
    import json

    from pydantic import ValidationError

    if isinstance(exc, (json.JSONDecodeError, ValidationError, ValueError)):
        return True
    error_text = str(exc).lower()
    return any(
        marker in error_text
        for marker in (
            "json",
            "empty llm response",
            "validation error",
            "cannot extract json",
        )
    )


def is_rate_limit_error(exc: BaseException) -> bool:
    """Определяет ошибку превышения квоты (HTTP 429 / rate limit)."""
    error_text = str(exc).lower()
    return any(
        marker in error_text
        for marker in (
            "429",
            "too many requests",
            "rate limit",
            "resource_exhausted",
            "quota",
        )
    )
