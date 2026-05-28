"""Общие константы и утилиты лимитирования LLM-запросов."""

from __future__ import annotations

import os
from dataclasses import dataclass


def _env_int(*keys: str, default: int) -> int:
    for key in keys:
        raw = os.getenv(key)
        if raw is not None and str(raw).strip():
            return int(raw)
    return default


@dataclass(frozen=True)
class RateLimits:
    batch_size: int
    normalize_batch_size: int
    request_delay_seconds: int
    rate_limit_retry_seconds: int
    max_retries: int


def read_rate_limits() -> RateLimits:
    """Лимиты из env (см. .env.example: LLM_*)."""
    return RateLimits(
        batch_size=_env_int("LLM_BATCH_SIZE", "GEMINI_BATCH_SIZE", default=18),
        normalize_batch_size=_env_int("LLM_NORMALIZE_BATCH_SIZE", default=8),
        request_delay_seconds=_env_int(
            "LLM_REQUEST_DELAY_SECONDS",
            "GEMINI_REQUEST_DELAY_SECONDS",
            default=4,
        ),
        rate_limit_retry_seconds=_env_int(
            "LLM_RATE_LIMIT_RETRY_SECONDS",
            "GEMINI_RATE_LIMIT_RETRY_SECONDS",
            default=15,
        ),
        max_retries=_env_int("LLM_MAX_RETRIES", "GEMINI_MAX_RETRIES", default=3),
    )


_limits = read_rate_limits()
BATCH_SIZE = _limits.batch_size
NORMALIZE_BATCH_SIZE = _limits.normalize_batch_size
REQUEST_DELAY_SECONDS = _limits.request_delay_seconds
RATE_LIMIT_RETRY_SECONDS = _limits.rate_limit_retry_seconds
MAX_RETRIES = _limits.max_retries


def chunk_items(items: list[str], batch_size: int | None = None) -> list[list[str]]:
    """Разбивает список товаров на батчи."""
    if not items:
        return []
    size = batch_size if batch_size is not None else read_rate_limits().batch_size
    return [items[idx : idx + size] for idx in range(0, len(items), size)]


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
