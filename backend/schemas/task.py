"""Схемы задач кластеризации и нормализации."""

from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import AliasChoices, BaseModel, Field


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
        default_factory=list,
        description="Желаемые атрибуты от пользователя (можно пусто)",
    )
    embedding_provider: EmbeddingProvider = Field(
        default=EmbeddingProvider.LOCAL,
        description="Провайдер эмбеддингов для кластеризации: local|gemini",
    )
    cluster_profile_provider: ClusterProfileProvider = Field(
        default=ClusterProfileProvider.G4F,
        validation_alias=AliasChoices("cluster_profile_provider", "profile_provider"),
        description="Провайдер LLM для профиля кластера: g4f|gemini",
    )


class ClusterInput(BaseModel):
    """Один кластер для нормализации."""

    name: str = Field(..., description="Название кластера")
    attributes: list[str] = Field(..., description="Атрибуты кластера")
    items: list[str] = Field(..., description="Названия товаров в кластере")
    enriched_name_template: str = Field(
        default="",
        description="Шаблон обогащённого наименования с плейсхолдерами {атрибут}",
    )
    item_sources: dict[str, str] = Field(
        default_factory=dict,
        description="Источник строки: memory|ai по исходной номенклатуре",
    )
    item_values: dict[str, dict[str, str]] = Field(
        default_factory=dict,
        description="Известные значения атрибутов по item (используется для memory skip)",
    )
    attribute_merge: dict[str, str] = Field(
        default_factory=dict,
        description="Режим слияния атрибутов: priority|accumulative",
    )
    attribute_merge_separators: dict[str, str] = Field(
        default_factory=dict,
        description="Разделитель для аккумулятивного слияния (например ', ' или '; ')",
    )


class NormalizeRequest(BaseModel):
    """Входящие данные для нормализации утверждённых кластеров."""

    clusters: list[ClusterInput]
    llm_provider: NormalizeProvider = Field(
        ...,
        description="Провайдер LLM для нормализации: g4f|gemini",
    )
    resume_completed_cluster_indexes: list[int] = Field(
        default_factory=list,
        description="Индексы уже обработанных кластеров (для resume).",
    )
    resume_seed_normalized: list[dict[str, Any]] = Field(
        default_factory=list,
        description="Накопленные normalized-строки из partial результата.",
    )
    resume_seed_clusters_collapsed: list[dict[str, Any]] = Field(
        default_factory=list,
        description="Накопленные collapsed-кластеры из partial результата.",
    )
    resume_expected_count: int | None = Field(
        default=None,
        description="Ожидаемое количество позиций из предыдущего partial (если есть).",
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
    llm_provider: str | None = None
    embedding_provider: str | None = None
    llm_model: str | None = None
    embedding_model: str | None = None
