"""Схемы для работы с векторной памятью."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class MemoryItem(BaseModel):
    """Один товар для сохранения в векторной памяти."""

    text: str = Field(..., description="Название товара")
    attributes: dict[str, Any] = Field(..., description="Заполненные атрибуты товара")
    cluster_name: str = Field(..., description="Имя кластера из UI")


class MemorySaveRequest(BaseModel):
    """Запрос на сохранение набора товаров в векторную память."""

    items: list[MemoryItem]


class MemorySaveResponse(BaseModel):
    """Ответ на сохранение товаров в память."""

    saved_count: int
