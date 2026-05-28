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


class EmbeddingProvider(str, Enum):
    """Доступные провайдеры эмбеддингов для кластеризации."""

    LOCAL = "local"
    GEMINI = "gemini"


class NormalizeProvider(str, Enum):
    """Доступные LLM-провайдеры для нормализации."""

    G4F = "g4f"
    GEMINI = "gemini"


class ClusterProfileProvider(str, Enum):
    """Доступные LLM-провайдеры для профиля кластера."""

    G4F = "g4f"
    GEMINI = "gemini"


class ClusterizeRequest(BaseModel):
    """Входящие данные для кластеризации номенклатуры."""

    items: list[str] = Field(..., description="Названия номенклатуры")
    base_attributes: list[str] = Field(
        ..., description="Обязательные атрибуты от пользователя"
    )
    embedding_provider: EmbeddingProvider = Field(
        default=EmbeddingProvider.LOCAL,
        description="Провайдер эмбеддингов для кластеризации: local|gemini",
    )
    cluster_profile_provider: ClusterProfileProvider = Field(
        default=ClusterProfileProvider.G4F,
        description="Провайдер LLM для профиля кластера: g4f|gemini",
    )


class ClusterInput(BaseModel):
    """Один кластер для нормализации."""

    name: str = Field(..., description="Название кластера")
    attributes: list[str] = Field(..., description="Атрибуты кластера")
    items: list[str] = Field(..., description="Названия товаров в кластере")


class NormalizeRequest(BaseModel):
    """Входящие данные для нормализации утверждённых кластеров."""

    clusters: list[ClusterInput]
    llm_provider: NormalizeProvider = Field(
        ...,
        description="Провайдер LLM для нормализации: g4f|gemini",
    )


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
    progress: str | None = None
