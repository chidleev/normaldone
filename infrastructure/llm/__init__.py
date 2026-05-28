"""LLM-адаптеры."""

__all__ = ["create_llm_client", "get_llm_provider", "G4FClient", "GeminiClient"]


def __getattr__(name: str):
    if name == "create_llm_client":
        from infrastructure.llm.factory import create_llm_client

        return create_llm_client
    if name == "get_llm_provider":
        from infrastructure.llm.factory import get_llm_provider

        return get_llm_provider
    if name == "G4FClient":
        from infrastructure.llm.g4f_client import G4FClient

        return G4FClient
    if name == "GeminiClient":
        from infrastructure.llm.gemini_client import GeminiClient

        return GeminiClient
    raise AttributeError(name)
