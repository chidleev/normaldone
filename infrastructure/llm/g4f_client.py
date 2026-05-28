"""LLM-клиент через g4f (GPT-4 и др.) без API-ключа Google."""

from __future__ import annotations

import logging
import os

from dotenv import load_dotenv
from g4f.client import AsyncClient

from infrastructure.llm.base_llm import BaseLLMClient
from service.ports.cache_store import CacheStorePort

logger = logging.getLogger(__name__)


class G4FClient(BaseLLMClient):
    """Клиент g4f с моделью gpt-4 по умолчанию."""

    provider_name = "g4f"

    def __init__(self, cache_store: CacheStorePort) -> None:
        load_dotenv()
        super().__init__(cache_store)
        self.model_name = os.getenv("G4F_MODEL", "gpt-4")
        self.web_search_enabled = os.getenv("G4F_WEB_SEARCH", "true").lower() in (
            "1",
            "true",
            "yes",
        )
        self.client = AsyncClient()

    async def _complete(self, prompt: str, *, web_search: bool = False) -> str:
        use_search = web_search and self.web_search_enabled
        response = await self.client.chat.completions.create(
            model=self.model_name,
            messages=[{"role": "user", "content": prompt}],
            web_search=use_search,
        )
        if not response.choices:
            logger.warning("g4f returned no choices (web_search=%s)", use_search)
            return ""
        message = response.choices[0].message
        content = message.content if message else None
        if content is None:
            logger.warning("g4f returned null content (web_search=%s)", use_search)
            return ""
        text = str(content).strip()
        if not text:
            logger.warning("g4f returned empty string (web_search=%s)", use_search)
        return text
