"""Клиент Gemini для подбора атрибутов и нормализации товаров."""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import os
from collections.abc import Iterator
from typing import Any

from dotenv import load_dotenv
from google import genai
from google.genai import types
from pydantic import BaseModel

from schemas.llm import ClusterAttributesResponse, NormalizeItemsResponse
from service.ports.cache_store import CacheStorePort

logger = logging.getLogger(__name__)

# Лимиты бесплатного тарифа Gemini 3.1 Flash Lite
BATCH_SIZE = 18
REQUEST_DELAY_SECONDS = 4
RATE_LIMIT_RETRY_SECONDS = 15
MAX_RETRIES = 3


def _chunk_items(items: list[str], batch_size: int = BATCH_SIZE) -> list[list[str]]:
    """Разбивает список товаров на батчи по 15–20 позиций."""
    if not items:
        return []
    return [items[idx : idx + batch_size] for idx in range(0, len(items), batch_size)]


def _is_rate_limit_error(exc: BaseException) -> bool:
    """Определяет ошибку превышения квоты (HTTP 429 / rate limit)."""
    error_text = str(exc).lower()
    return any(
        marker in error_text
        for marker in ("429", "too many requests", "rate limit", "resource_exhausted", "quota")
    )


class GeminiClient:
    """Клиент Gemini 3.1 Flash Lite с батчингом, паузами и защитой от 429."""

    def __init__(self, cache_store: CacheStorePort) -> None:
        """Читает токен из .env и инициализирует SDK-клиент."""
        load_dotenv()
        api_key = os.getenv("GEMINI_API_KEY")
        if not api_key:
            raise ValueError("GEMINI_API_KEY is not set in environment")
        self.cache_store = cache_store
        self.client = genai.Client(api_key=api_key)
        self.model_name: str = "gemini-3.1-flash-lite"
        self.batch_size: int = int(os.getenv("GEMINI_BATCH_SIZE", BATCH_SIZE))
        self.request_delay_seconds: int = int(
            os.getenv("GEMINI_REQUEST_DELAY_SECONDS", REQUEST_DELAY_SECONDS)
        )
        self.rate_limit_retry_seconds: int = int(
            os.getenv("GEMINI_RATE_LIMIT_RETRY_SECONDS", RATE_LIMIT_RETRY_SECONDS)
        )
        self.max_retries: int = int(os.getenv("GEMINI_MAX_RETRIES", MAX_RETRIES))

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
        """Выполняет один запрос к Gemini с кэшем и повторами при 429."""
        cache_key = self._build_cache_key(prompt, items)
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
                await self.cache_store.set_cache(cache_key, data)
                return data
            except Exception as exc:
                last_error = exc
                if _is_rate_limit_error(exc) and attempt < self.max_retries:
                    logger.warning(
                        "Gemini rate limit (attempt %s/%s), retrying in %ss: %s",
                        attempt,
                        self.max_retries,
                        self.rate_limit_retry_seconds,
                        exc,
                    )
                    await asyncio.sleep(self.rate_limit_retry_seconds)
                    continue
                raise

        if last_error is not None:
            raise last_error
        raise RuntimeError("Unreachable retry branch")

    async def _run_batched_requests(
        self,
        batches: list[list[str]],
        build_prompt: Any,
        response_schema: type[BaseModel],
        parse_batch: Any,
    ) -> list[Any]:
        """Выполняет батчи последовательно с asyncio.sleep между запросами к API."""
        aggregated: list[Any] = []
        for batch_index, batch in enumerate(batches):
            prompt = build_prompt(batch)
            payload = await self._generate_json(prompt, batch, response_schema)
            aggregated.extend(parse_batch(payload))
            if batch_index < len(batches) - 1:
                await asyncio.sleep(self.request_delay_seconds)
        return aggregated

    async def get_cluster_attributes(
        self,
        items: list[str],
        base_attrs: list[str],
    ) -> list[str]:
        """Определяет 3-5 специфичных атрибутов; крупные кластеры режутся на батчи."""
        batches = _chunk_items(items, self.batch_size)
        if not batches:
            return []

        def build_prompt(batch: list[str]) -> str:
            return (
                "Проанализируй список товаров, определи категорию и предложи 3-5 "
                "специфичных свойств для этой категории. Верни только JSON.\n"
                f"Список товаров: {batch}\n"
                f"Обязательные базовые атрибуты: {base_attrs}"
            )

        def parse_batch(payload: dict[str, Any]) -> Iterator[str]:
            parsed = ClusterAttributesResponse.model_validate(payload)
            yield from parsed.attributes

        attributes = await self._run_batched_requests(
            batches=batches,
            build_prompt=build_prompt,
            response_schema=ClusterAttributesResponse,
            parse_batch=parse_batch,
        )
        return list(dict.fromkeys(attributes))

    async def normalize_items(
        self,
        items: list[str],
        attributes: list[str],
    ) -> list[dict[str, Any]]:
        """Извлекает свойства товаров батчами с паузами между вызовами API."""
        batches = _chunk_items(items, self.batch_size)
        if not batches:
            return []

        def build_prompt(batch: list[str]) -> str:
            return (
                "Извлеки значения свойств для каждого товара. Если данных нет в "
                "названии, используй веб-поиск по артикулу или бренду. "
                "Верни только JSON.\n"
                f"Товары: {batch}\n"
                f"Свойства для извлечения: {attributes}"
            )

        def parse_batch(payload: dict[str, Any]) -> Iterator[dict[str, Any]]:
            parsed = NormalizeItemsResponse.model_validate(payload)
            for item in parsed.normalized:
                yield item.model_dump()

        return await self._run_batched_requests(
            batches=batches,
            build_prompt=build_prompt,
            response_schema=NormalizeItemsResponse,
            parse_batch=parse_batch,
        )
