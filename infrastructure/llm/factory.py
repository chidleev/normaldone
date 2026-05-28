"""Фабрика LLM-адаптеров по переменной окружения LLM_PROVIDER."""

from __future__ import annotations

import os

from dotenv import load_dotenv

from infrastructure.llm.gemini_client import GeminiClient
from service.ports.cache_store import CacheStorePort
from service.ports.llm import LLMPort

DEFAULT_LLM_PROVIDER = "g4f"


def get_llm_provider() -> str:
    """Возвращает имя провайдера LLM из окружения."""
    load_dotenv()
    return os.getenv("LLM_PROVIDER", DEFAULT_LLM_PROVIDER).strip().lower()


def create_llm_client(cache_store: CacheStorePort) -> LLMPort:
    """Создаёт LLM-клиент: g4f (по умолчанию) или gemini."""
    provider = get_llm_provider()
    if provider in ("g4f", "gpt4free", "gpt-4"):
        from infrastructure.llm.g4f_client import G4FClient

        return G4FClient(cache_store)
    if provider == "gemini":
        return GeminiClient(cache_store)
    raise ValueError(
        f"Unknown LLM_PROVIDER={provider!r}. Supported: g4f, gemini"
    )
