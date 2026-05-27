"""Клиент Gemini для подбора атрибутов и нормализации товаров."""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import os
from typing import Any

from dotenv import load_dotenv
from google import genai
from google.genai import types
from pydantic import BaseModel

from schemas.llm import ClusterAttributesResponse, NormalizeItemsResponse
from service.ports.cache_store import CacheStorePort

logger = logging.getLogger(__name__)


class GeminiClient:
    """Клиент Gemini 3.1 Flash Lite с поддержкой web search."""

    def __init__(self, cache_store: CacheStorePort) -> None:
        """Читает токен из .env и инициализирует SDK-клиент."""
        load_dotenv()
        api_key = os.getenv("GEMINI_API_KEY")
        if not api_key:
            raise ValueError("GEMINI_API_KEY is not set in environment")
        self.cache_store = cache_store
        self.client = genai.Client(api_key=api_key)
        self.model_name: str = "gemini-3.1-flash-lite"
        self.max_retries: int = 3
        self.retry_delay_seconds: int = 5

    @staticmethod
    def _build_cache_key(prompt: str, items: list[str]) -> str:
        payload = f"{prompt}||{'|'.join(items)}"
        return hashlib.md5(payload.encode("utf-8")).hexdigest()

    async def _generate_json(
        self,
        prompt: str,
        items: list[str],
        response_schema: type[BaseModel],
    ) -> dict[str, Any]:
        """Выполняет запрос к Gemini и возвращает JSON с повторами при ошибках."""
        cache_key = self._build_cache_key(prompt, items)
        cached = await self.cache_store.get_cache(cache_key)
        if cached is not None:
            return cached

        config = types.GenerateContentConfig(
            response_mime_type="application/json",
            response_schema=response_schema,
            tools=[types.Tool(google_search=types.GoogleSearch())],
        )

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
                await self.cache_store.set_cache(cache_key, data)
                return data
            except Exception as exc:
                error_text = str(exc).lower()
                retriable = any(
                    keyword in error_text
                    for keyword in ("timeout", "timed out", "429", "rate", "quota")
                )
                if retriable and attempt < self.max_retries:
                    logger.warning(
                        "Gemini request failed (attempt %s/%s), retrying in %ss: %s",
                        attempt,
                        self.max_retries,
                        self.retry_delay_seconds,
                        exc,
                    )
                    await asyncio.sleep(self.retry_delay_seconds)
                    continue
                raise

        raise RuntimeError("Unreachable retry branch")

    async def get_cluster_attributes(
        self,
        items: list[str],
        base_attrs: list[str],
    ) -> list[str]:
        """Определяет 3-5 специфичных атрибутов для группы товаров."""
        prompt = (
            "Проанализируй список товаров, определи категорию и предложи 3-5 "
            "специфичных свойств для этой категории. Верни только JSON.\n"
            f"Список товаров: {items}\n"
            f"Обязательные базовые атрибуты: {base_attrs}"
        )
        payload = await self._generate_json(prompt, items, ClusterAttributesResponse)
        parsed = ClusterAttributesResponse.model_validate(payload)
        return parsed.attributes

    async def normalize_items(
        self,
        items: list[str],
        attributes: list[str],
    ) -> list[dict[str, Any]]:
        """Извлекает значения свойств для товаров с использованием web search."""
        prompt = (
            "Извлеки значения свойств для каждого товара. Если данных нет в "
            "названии, используй веб-поиск по артикулу или бренду. "
            "Верни только JSON.\n"
            f"Товары: {items}\n"
            f"Свойства для извлечения: {attributes}"
        )
        payload = await self._generate_json(prompt, items, NormalizeItemsResponse)
        parsed = NormalizeItemsResponse.model_validate(payload)
        return [item.model_dump() for item in parsed.normalized]
