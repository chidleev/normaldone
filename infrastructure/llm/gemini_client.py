"""Клиент Gemini для подбора атрибутов и нормализации товаров."""

from __future__ import annotations

import asyncio
import json
import logging
import os

from dotenv import load_dotenv
from google import genai
from google.genai import types
from pydantic import BaseModel

from infrastructure.llm.base_llm import BaseLLMClient
from infrastructure.llm.rate_limit import is_rate_limit_error
from service.ports.cache_store import CacheStorePort

logger = logging.getLogger(__name__)


class GeminiClient(BaseLLMClient):
    """Клиент Gemini 3.1 Flash Lite с JSON-schema и web search."""

    provider_name = "gemini"

    def __init__(self, cache_store: CacheStorePort) -> None:
        load_dotenv()
        super().__init__(cache_store)
        api_key = os.getenv("GEMINI_API_KEY")
        if not api_key:
            raise ValueError("GEMINI_API_KEY is not set in environment")
        self.client = genai.Client(api_key=api_key)
        self.model_name: str = os.getenv("GEMINI_MODEL", "gemini-3.1-flash-lite")

    async def _complete(self, prompt: str) -> str:
        raise NotImplementedError("Gemini uses structured _generate_json override")

    async def _generate_json(
        self,
        prompt: str,
        items: list[str],
        response_schema: type[BaseModel],
        *,
        web_search: bool = False,
        use_cache: bool = True,
    ) -> dict:
        _ = web_search  # Gemini всегда использует Google Search tool
        cache_key = self._build_cache_key(self.provider_name, prompt, items)
        if use_cache:
            cached = await self.cache_store.get_cache(cache_key)
            if cached is not None:
                return cached

        config = types.GenerateContentConfig(
            response_mime_type="application/json",
            response_schema=response_schema,
            tools=[types.Tool(google_search=types.GoogleSearch())],
        )

        last_error: Exception | None = None
        for attempt in range(1, self.max_retries + 1):
            try:
                response = await asyncio.to_thread(
                    self.client.models.generate_content,
                    model=self.model_name,
                    contents=prompt,
                    config=config,
                )
                raw_text: str = response.text if response.text else "{}"
                data = json.loads(raw_text)
                response_schema.model_validate(data)
                if use_cache:
                    await self.cache_store.set_cache(cache_key, data)
                return data
            except Exception as exc:
                last_error = exc
                if is_rate_limit_error(exc) and attempt < self.max_retries:
                    wait_seconds = self.rate_limit_retry_seconds * attempt
                    logger.warning(
                        "Gemini rate limit (attempt %s/%s), retry in %ss: %s",
                        attempt,
                        self.max_retries,
                        wait_seconds,
                        exc,
                    )
                    await asyncio.sleep(wait_seconds)
                    continue
                raise

        if last_error is not None:
            raise last_error
        raise RuntimeError("Unreachable retry branch")
