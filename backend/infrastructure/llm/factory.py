"""Фабрика LLM-адаптеров с явным выбором провайдера."""

from __future__ import annotations

from infrastructure.llm.gemini_client import GeminiClient
from service.ports.cache_store import CacheStorePort
from service.ports.llm import LLMPort

SUPPORTED_LLM_PROVIDERS = ("g4f", "gemini")

def resolve_llm_provider(provider: str) -> str:
    """Нормализует имя провайдера из запроса клиента."""
    resolved = provider.strip().lower()
    if resolved in ("gpt4free", "gpt-4"):
        resolved = "g4f"
    if resolved not in SUPPORTED_LLM_PROVIDERS:
        supported = ", ".join(SUPPORTED_LLM_PROVIDERS)
        raise ValueError(f"Unknown LLM provider={resolved!r}. Supported: {supported}")
    return resolved


def create_llm_client(cache_store: CacheStorePort, provider: str) -> LLMPort:
    """Создаёт LLM-клиент для выбранного провайдера."""
    provider = resolve_llm_provider(provider)
    if provider in ("g4f", "gpt4free", "gpt-4"):
        from infrastructure.llm.g4f_client import G4FClient

        return G4FClient(cache_store)
    if provider == "gemini":
        return GeminiClient(cache_store)
    supported = ", ".join(SUPPORTED_LLM_PROVIDERS)
    raise ValueError(f"Unknown LLM provider={provider!r}. Supported: {supported}")
