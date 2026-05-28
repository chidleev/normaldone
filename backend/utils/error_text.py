"""Человекочитаемые сообщения об ошибках для UI."""

from __future__ import annotations

import re


def _is_gemini_quota_error(text: str) -> bool:
    lower = text.lower()
    return "resource_exhausted" in lower or (
        "429" in text and ("quota" in lower or "rate" in lower)
    )


def format_gemini_quota_hint(
    *,
    phase: str,
    embedding_provider: str,
    embedding_model: str | None,
    llm_provider: str,
    llm_model: str | None,
) -> str:
    """Подсказка, если 429 пришёл не от той модели, что в дашборде Flash Lite."""
    embed = embedding_model or embedding_provider
    llm = llm_model or llm_provider
    lines = [
        "Квота Google Gemini исчерпана (429).",
        f"Этап сбоя: {phase}.",
        f"Векторизация: {embedding_provider} → {embed}.",
        f"Профиль кластера (LLM): {llm_provider} → {llm}.",
    ]
    if embedding_provider == "gemini":
        lines.append(
            "В дашборде «Gemini 3.1 Flash Lite» не видны вызовы векторизации — "
            "смотрите модель embedding (gemini-embedding-001) или общий лимит проекта."
        )
    elif llm_provider == "gemini":
        lines.append(
            "Проверьте лимиты модели GEMINI_MODEL и billing: https://ai.google.dev/gemini-api/docs/rate-limits"
        )
    lines.append(
        "Чтобы не тратить квоту: Векторизация=local, Профиль кластера=g4f."
    )
    return " ".join(lines)


def sanitize_error_message(
    error: Exception | str,
    *,
    phase: str = "",
    embedding_provider: str = "",
    embedding_model: str | None = None,
    llm_provider: str = "",
    llm_model: str | None = None,
) -> str:
    """Убирает HTML-страницы прокси и сокращает шум."""
    text = str(error).strip()
    if not text:
        return "Неизвестная ошибка"

    lower = text.lower()
    if "<html" in lower or "<!doctype" in lower:
        if "504" in lower or "gateway time-out" in lower:
            return (
                "Таймаут LLM-провайдера (504). "
                "Увеличьте ожидание или выберите другой провайдер (gemini/local)."
            )
        if "502" in lower or "bad gateway" in lower:
            return "LLM-провайдер недоступен (502). Повторите позже или смените провайдер."
        return "Сетевая ошибка LLM-провайдера. Проверьте провайдер и доступ в интернет."

    if "additionalproperties" in lower and "gemini" in lower:
        return (
            "Ошибка схемы Gemini API (Developer mode). "
            "Обновите backend: для gemini больше не передаётся strict JSON Schema. "
            "Пересоберите контейнер api."
        )

    if _is_gemini_quota_error(text) and (embedding_provider or llm_provider):
        return format_gemini_quota_hint(
            phase=phase or "неизвестен",
            embedding_provider=embedding_provider or "?",
            embedding_model=embedding_model,
            llm_provider=llm_provider or "?",
            llm_model=llm_model,
        )

    if _is_gemini_quota_error(text):
        return (
            "Квота Google Gemini исчерпана (429). "
            "Кластеризация может вызывать gemini-embedding-001 (векторизация) и "
            "GEMINI_MODEL (профиль кластера) — в дашборде это разные модели. "
            "Поставьте Векторизация=local, Профиль=g4f или проверьте billing."
        )

    text = re.sub(r"\s+", " ", text)
    if len(text) > 500:
        return text[:497] + "..."
    return text
