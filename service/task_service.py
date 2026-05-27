"""Бизнес-логика задач с хранением статусов в Redis."""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from schemas.task import ClusterizeRequest, NormalizeRequest, TaskStatus
from service.ports.clusterizer import ClusterizerPort
from service.ports.embedding import EmbeddingPort
from service.ports.llm import LLMPort
from service.ports.standardizer import StandardizerPort
from service.ports.task_store import TaskStorePort
from service.ports.vector_memory import VectorMemoryPort

logger = logging.getLogger(__name__)


async def create_task(task_id: str, task_store: TaskStorePort) -> None:
    """Регистрирует новую задачу со статусом PENDING в Redis."""
    state: dict[str, Any] = {
        "status": TaskStatus.PENDING.value,
        "result": None,
        "error": None,
    }
    await task_store.set_task_state(task_id, state)


async def get_task(task_id: str, task_store: TaskStorePort) -> dict[str, Any] | None:
    """Возвращает запись задачи или None, если идентификатор не найден."""
    return await task_store.get_task_state(task_id)


async def _set_task_state(
    task_id: str,
    task_store: TaskStorePort,
    *,
    status: TaskStatus,
    result: dict[str, Any] | None = None,
    error: str | None = None,
    progress: str | None = None,
) -> None:
    """Обновляет состояние задачи в Redis."""
    current = await task_store.get_task_state(task_id) or {}
    state: dict[str, Any] = {
        "status": status.value,
        "result": result if result is not None else current.get("result"),
        "error": error if error is not None else current.get("error"),
    }
    if progress is not None:
        state["progress"] = progress
    elif status == TaskStatus.PROCESSING and current.get("progress"):
        state["progress"] = current["progress"]
    await task_store.set_task_state(task_id, state)


async def _touch_processing(
    task_id: str,
    task_store: TaskStorePort,
    progress: str,
) -> None:
    """Продлевает PROCESSING в Redis во время долгих пауз Gemini."""
    await _set_task_state(
        task_id,
        task_store,
        status=TaskStatus.PROCESSING,
        progress=progress,
    )


async def clusterize_task(
    task_id: str,
    data: ClusterizeRequest,
    vectorizer: EmbeddingPort,
    vector_db: VectorMemoryPort,
    gemini_client: LLMPort,
    clusterizer: ClusterizerPort,
    task_store: TaskStorePort,
) -> None:
    """Выполняет кластеризацию с учетом памяти и атрибутов от Gemini."""
    try:
        await _set_task_state(task_id, task_store, status=TaskStatus.PROCESSING)
        embeddings: list[list[float]] = await asyncio.to_thread(
            vectorizer.get_embeddings,
            data.items,
        )
        memory_matches: list[dict[str, Any] | None] = await asyncio.to_thread(
            vector_db.find_similar,
            embeddings,
        )

        known_items: list[dict[str, Any]] = []
        unknown_items: list[str] = []
        unknown_vectors: list[list[float]] = []
        for item_name, item_vector, item_match in zip(
            data.items,
            embeddings,
            memory_matches,
            strict=True,
        ):
            if item_match is None:
                unknown_items.append(item_name)
                unknown_vectors.append(item_vector)
            else:
                known_items.append({"item": item_name, "attributes": item_match})

        new_item_clusters: list[dict[str, Any]] = await asyncio.to_thread(
            clusterizer.clusterize,
            unknown_items,
            unknown_vectors,
        )
        for cluster_index, cluster in enumerate(new_item_clusters, start=1):
            cluster_items = [str(item) for item in cluster.get("cluster_items", [])]
            await _touch_processing(
                task_id,
                task_store,
                progress=(
                    f"Gemini: кластер {cluster_index}/{len(new_item_clusters)} "
                    f"({len(cluster_items)} товаров)"
                ),
            )
            cluster_specific_attrs: list[str] = await gemini_client.get_cluster_attributes(
                cluster_items,
                data.base_attributes,
            )
            combined_attributes = list(
                dict.fromkeys(data.base_attributes + cluster_specific_attrs)
            )
            cluster["attributes"] = combined_attributes

        result_payload: dict[str, Any] = {
            "embeddings_count": len(embeddings),
            "known_items": known_items,
            "new_item_clusters": new_item_clusters,
            "base_attributes": data.base_attributes,
            "message": "Clusterization completed",
        }
        await _set_task_state(
            task_id,
            task_store,
            status=TaskStatus.COMPLETED,
            result=result_payload,
            error=None,
        )
        logger.info("Clusterize task %s completed", task_id)
    except Exception as exc:
        logger.exception("Clusterize task %s failed", task_id)
        await _set_task_state(
            task_id,
            task_store,
            status=TaskStatus.FAILED,
            error=str(exc),
        )


async def normalize_task(
    task_id: str,
    data: NormalizeRequest,
    gemini_client: LLMPort,
    standardizer: StandardizerPort,
    task_store: TaskStorePort,
) -> None:
    """Выполняет батч-нормализацию через Gemini и очистку значений."""
    try:
        await _set_task_state(task_id, task_store, status=TaskStatus.PROCESSING)
        normalized_items: list[dict[str, Any]] = []
        for cluster_index, cluster in enumerate(data.clusters, start=1):
            await _touch_processing(
                task_id,
                task_store,
                progress=(
                    f"Gemini: нормализация кластера {cluster_index}/{len(data.clusters)} "
                    f"({len(cluster.items)} товаров)"
                ),
            )
            batch_result: list[dict[str, Any]] = await gemini_client.normalize_items(
                cluster.items,
                cluster.attributes,
            )
            for normalized_entry in batch_result:
                values_raw: dict[str, Any] = dict(normalized_entry.get("values", {}))
                standardized_values = standardizer.process_item(
                    {k: str(v) for k, v in values_raw.items()}
                )
                normalized_entry["values"] = standardized_values
                normalized_items.append(normalized_entry)
        result_payload: dict[str, Any] = {
            "normalized": normalized_items,
            "message": "Normalization completed with Gemini",
        }
        await _set_task_state(
            task_id,
            task_store,
            status=TaskStatus.COMPLETED,
            result=result_payload,
            error=None,
        )
        logger.info("Normalize task %s completed", task_id)
    except Exception as exc:
        logger.exception("Normalize task %s failed", task_id)
        await _set_task_state(
            task_id,
            task_store,
            status=TaskStatus.FAILED,
            error=str(exc),
        )
