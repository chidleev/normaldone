"""Базовый LLM-клиент: батчи, кэш Redis, паузы и повторы при 429."""

from __future__ import annotations

import asyncio
import hashlib
import logging
from collections.abc import Callable, Iterator
from typing import Any

from pydantic import BaseModel

from infrastructure.llm.rate_limit import (
    chunk_items,
    is_rate_limit_error,
    is_retriable_llm_error,
    read_rate_limits,
)
from schemas.llm import ClusterAttributesResponse, NormalizeItemsResponse
from service.ports.cache_store import CacheStorePort

logger = logging.getLogger(__name__)


class BaseLLMClient:
    """Общая логика get_cluster_attributes / normalize_items для любого провайдера."""

    provider_name: str = "base"

    def __init__(self, cache_store: CacheStorePort) -> None:
        self.cache_store = cache_store
        limits = read_rate_limits()
        self.batch_size = limits.batch_size
        self.normalize_batch_size = limits.normalize_batch_size
        self.request_delay_seconds = limits.request_delay_seconds
        self.rate_limit_retry_seconds = limits.rate_limit_retry_seconds
        self.max_retries = limits.max_retries

    @staticmethod
    def _build_cache_key(
        provider: str,
        prompt: str,
        items: list[str],
        *,
        web_search: bool = False,
    ) -> str:
        payload = f"{provider}||{web_search}||{prompt}||{'|'.join(items)}"
        return hashlib.md5(payload.encode("utf-8")).hexdigest()

    async def _complete(self, prompt: str, *, web_search: bool = False) -> str:
        """Выполняет один запрос к провайдеру и возвращает сырой текст."""
        raise NotImplementedError

    async def _generate_json(
        self,
        prompt: str,
        items: list[str],
        response_schema: type[BaseModel],
        *,
        web_search: bool = False,
        use_cache: bool = True,
    ) -> dict[str, Any]:
        """Запрос с кэшем и повторами при 429."""
        cache_key = self._build_cache_key(
            self.provider_name,
            prompt,
            items,
            web_search=web_search,
        )
        if use_cache:
            cached = await self.cache_store.get_cache(cache_key)
            if cached is not None:
                return cached
        use_cache_on_success = use_cache

        schema_hint = (
            f"\n\nВерни ТОЛЬКО валидный JSON без пояснений, комментариев и markdown. "
            f"Схема: {response_schema.model_json_schema()}"
        )
        full_prompt = prompt + schema_hint

        last_error: Exception | None = None
        for attempt in range(1, self.max_retries + 1):
            try:
                from infrastructure.llm.json_utils import extract_json_object

                raw_text = await self._complete(full_prompt, web_search=web_search)
                if not raw_text or not raw_text.strip():
                    raise ValueError("Empty LLM response")
                data = extract_json_object(raw_text)
                response_schema.model_validate(data)
                if use_cache_on_success:
                    await self.cache_store.set_cache(cache_key, data)
                return data
            except Exception as exc:
                last_error = exc
                raw_preview = locals().get("raw_text", "") or ""
                if is_retriable_llm_error(exc) and attempt < self.max_retries:
                    wait_seconds = self.rate_limit_retry_seconds * attempt
                    preview = raw_preview[:200].replace("\n", " ") if raw_preview else ""
                    logger.warning(
                        "%s retriable error (attempt %s/%s), retry in %ss: %s; preview=%r",
                        self.provider_name,
                        attempt,
                        self.max_retries,
                        wait_seconds,
                        exc,
                        preview,
                    )
                    await asyncio.sleep(wait_seconds)
                    use_cache_on_success = False
                    continue
                logger.error(
                    "%s non-retriable LLM error: %s",
                    self.provider_name,
                    exc,
                )
                raise

        if last_error is not None:
            raise last_error
        raise RuntimeError("Unreachable retry branch")

    async def _run_batched_requests(
        self,
        batches: list[list[str]],
        build_prompt: Callable[[list[str]], str],
        response_schema: type[BaseModel],
        parse_batch: Callable[[dict[str, Any]], Iterator[Any]],
        *,
        web_search: bool = False,
    ) -> list[Any]:
        aggregated: list[Any] = []
        for batch_index, batch in enumerate(batches):
            prompt = build_prompt(batch)
            payload = await self._generate_json(
                prompt,
                batch,
                response_schema,
                web_search=web_search,
            )
            aggregated.extend(parse_batch(payload))
            if batch_index < len(batches) - 1:
                await asyncio.sleep(self.request_delay_seconds)
        return aggregated

    async def get_cluster_profile(
        self,
        items: list[str],
        base_attrs: list[str],
    ) -> dict[str, Any]:
        batches = chunk_items(items, self.batch_size)
        if not batches:
            return {
                "category": "Без категории",
                "attributes": list(base_attrs),
                "name_template": "",
            }

        def build_prompt(batch: list[str]) -> str:
            if base_attrs:
                attrs_hint = f"Следующие атрибуты уже учтены пользователем (исключи их из ответа): {base_attrs}\n"
            else:
                attrs_hint = "Базовые атрибуты не заданы — предложи полный набор атрибутов самостоятельно.\n"
            return (
                "Проанализируй список товаров и верни название кластера (что это за продукт + общий признак, который будет однозначно идентифицировать товары в этом кластере - например бренд). "
                "Затем предложи (дополни) максимально полный список необходимых и полезных атрибутов, "
                "которые можно извлечь из названия товаров или найти через веб-поиск. "
                "Также предложи шаблон обогащённого стандартизованного наименования (name_template): "
                "слова и символы с плейсхолдерами {имя_атрибута} для подстановки значений атрибутов.\n"
                f"Список товаров: {batch}\n"
                f"{attrs_hint}"
                'Пример ответа: {"category": "Фильтры топливные", "attributes": '
                '["бренд", "артикул", "тип фильтра"], '
                '"name_template": "{бренд} фильтр {тип фильтра} {артикул}"}'
            )

        categories: list[str] = []
        templates: list[str] = []

        def parse_batch(payload: dict[str, Any]) -> Iterator[str]:
            parsed = ClusterAttributesResponse.model_validate(payload)
            category = str(parsed.category).strip()
            if category:
                categories.append(category)
            template = str(parsed.name_template or "").strip()
            if template:
                templates.append(template)
            yield from parsed.attributes

        attributes = await self._run_batched_requests(
            batches=batches,
            build_prompt=build_prompt,
            response_schema=ClusterAttributesResponse,
            parse_batch=parse_batch,
        )
        unique_attributes = list(dict.fromkeys(base_attrs + attributes))
        category = categories[0] if categories else "Без категории"
        name_template = templates[0] if templates else ""
        return {
            "category": category,
            "attributes": unique_attributes,
            "name_template": name_template,
        }

    @staticmethod
    def _validate_normalize_batch(
        batch: list[str],
        normalized: list[dict[str, Any]],
    ) -> None:
        """Проверяет, что LLM вернул ровно по одной записи на каждый товар."""
        if len(normalized) != len(batch):
            raise ValueError(
                f"Ожидалось {len(batch)} товаров в ответе, получено {len(normalized)}"
            )
        returned_items = [str(entry.get("item", "")).strip() for entry in normalized]
        if any(not name for name in returned_items):
            raise ValueError("В ответе есть записи без поля item")
        batch_set = set(batch)
        returned_set = set(returned_items)
        if returned_set != batch_set:
            missing = batch_set - returned_set
            extra = returned_set - batch_set
            details: list[str] = []
            if missing:
                details.append(f"нет в ответе: {list(missing)[:3]}")
            if extra:
                details.append(f"лишние: {list(extra)[:3]}")
            raise ValueError("; ".join(details) or "Несовпадение списка товаров")

    async def _normalize_batch(
        self,
        batch: list[str],
        attributes: list[str],
    ) -> list[dict[str, Any]]:
        """Нормализует один батч с повтором при неполном JSON."""
        numbered = "\n".join(f"{idx}. {name}" for idx, name in enumerate(batch, start=1))
        prompt = (
            f"Извлеки значения свойств для КАЖДОГО из {len(batch)} товаров ниже. "
            "Сначала используй данные из названия. "
            "Если свойства нет в названии — найди через веб-поиск по артикулу, бренду "
            "или каталожному номеру.\n"
            f"Свойства: {attributes}\n"
            f"Товары:\n{numbered}\n"
            "Формат ответа — только JSON:\n"
            '{"normalized": [{"item": "<точное название из списка>", '
            '"values": {"<свойство>": "<значение>"}}]}\n'
            f"В массиве normalized должно быть ровно {len(batch)} элементов."
        )

        def parse_batch(payload: dict[str, Any]) -> list[dict[str, Any]]:
            parsed = NormalizeItemsResponse.model_validate(payload)
            return [item.model_dump() for item in parsed.normalized]

        last_error: Exception | None = None
        for attempt in range(1, self.max_retries + 1):
            try:
                payload = await self._generate_json(
                    prompt,
                    batch,
                    NormalizeItemsResponse,
                    web_search=True,
                    use_cache=attempt == 1,
                )
                normalized = parse_batch(payload)
                self._validate_normalize_batch(batch, normalized)
                return normalized
            except ValueError as exc:
                last_error = exc
                if attempt < self.max_retries:
                    logger.warning(
                        "%s normalize batch incomplete (attempt %s/%s): %s",
                        self.provider_name,
                        attempt,
                        self.max_retries,
                        exc,
                    )
                    await asyncio.sleep(self.rate_limit_retry_seconds)
                    continue
                raise

        if last_error is not None:
            raise last_error
        raise RuntimeError("Unreachable normalize batch branch")

    async def normalize_items(
        self,
        items: list[str],
        attributes: list[str],
    ) -> list[dict[str, Any]]:
        batches = chunk_items(items, self.normalize_batch_size)
        if not batches:
            return []

        aggregated: list[dict[str, Any]] = []
        for batch_index, batch in enumerate(batches):
            aggregated.extend(await self._normalize_batch(batch, attributes))
            if batch_index < len(batches) - 1:
                await asyncio.sleep(self.request_delay_seconds)
        return aggregated
