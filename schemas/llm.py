"""Схемы структурированных ответов LLM."""

from __future__ import annotations

from pydantic import BaseModel, Field


class ClusterAttributesResponse(BaseModel):
    """Структура ответа для подбора атрибутов кластера."""

    attributes: list[str] = Field(default_factory=list)


class NormalizedItem(BaseModel):
    """Нормализованный товар с извлеченными свойствами."""

    item: str
    values: dict[str, str]


class NormalizeItemsResponse(BaseModel):
    """Структура ответа для нормализации группы товаров."""

    normalized: list[NormalizedItem] = Field(default_factory=list)
