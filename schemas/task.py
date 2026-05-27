"""Схемы задач кластеризации и нормализации."""

from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class TaskStatus(str, Enum):
    """Допустимые статусы фоновой задачи."""

    PENDING = "PENDING"
    PROCESSING = "PROCESSING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"


class ClusterizeRequest(BaseModel):
    """Входящие данные для кластеризации номенклатуры."""

    items: list[str] = Field(..., description="Названия номенклатуры")
    base_attributes: list[str] = Field(
        ..., description="Обязательные атрибуты от пользователя"
    )


class ClusterInput(BaseModel):
    """Один кластер для нормализации."""

    name: str = Field(..., description="Название кластера")
    attributes: list[str] = Field(..., description="Атрибуты кластера")
    items: list[str] = Field(..., description="Названия товаров в кластере")


class NormalizeRequest(BaseModel):
    """Входящие данные для нормализации утверждённых кластеров."""

    clusters: list[ClusterInput]


class TaskCreateResponse(BaseModel):
    """Ответ на постановку задачи в очередь."""

    task_id: str
    status: str


class TaskStatusResponse(BaseModel):
    """Ответ на проверку статуса или получение результата."""

    task_id: str
    status: str
    result: dict[str, Any] | None = None
    error: str | None = None
