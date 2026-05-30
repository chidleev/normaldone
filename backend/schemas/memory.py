"""Схемы для работы с векторной памятью."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class MemoryItem(BaseModel):
    """Один товар для сохранения в векторную памяти."""

    text: str = Field(..., description="Обогащённое стандартизованное наименование")
    attributes: dict[str, Any] = Field(..., description="Заполненные атрибуты товара")
    cluster_name: str = Field(..., description="Имя кластера из UI")
    original_items: list[str] = Field(
        default_factory=list,
        description="Исходные номенклатуры",
    )
    original_item_values: dict[str, dict[str, Any]] = Field(
        default_factory=dict,
        description="Значения атрибутов по каждой исходной номенклатуре",
    )
    attribute_merge: dict[str, str] = Field(
        default_factory=dict,
        description="Режимы слияния атрибутов для кластера",
    )
    attribute_merge_separators: dict[str, str] = Field(
        default_factory=dict,
        description="Разделители для аккумулятивных атрибутов",
    )


class MemorySaveRequest(BaseModel):
    """Запрос на сохранение набора товаров в векторную память."""

    items: list[MemoryItem]


class MemorySaveResponse(BaseModel):
    """Ответ на сохранение товаров в память."""

    saved_count: int
