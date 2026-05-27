"""Фоновые задачи и in-memory хранилище статусов."""

import asyncio
import logging
from typing import Any

from db.vector_store import VectorStorage
from llm.gemini_client import GeminiClient
from ml.clusterizer import ItemClusterizer
from ml.vectorizer import TextVectorizer
from schemas import ClusterizeRequest, NormalizeRequest, TaskStatus

logger = logging.getLogger(__name__)

# In-memory хранилище; в будущих тикетах заменится на Redis.
tasks_store: dict[str, dict[str, Any]] = {}


def create_task(task_id: str) -> None:
    """Регистрирует новую задачу со статусом PENDING."""
    tasks_store[task_id] = {
        "status": TaskStatus.PENDING.value,
        "result": None,
        "error": None,
    }


def get_task(task_id: str) -> dict[str, Any] | None:
    """Возвращает запись задачи или None, если идентификатор не найден."""
    return tasks_store.get(task_id)


def _set_status(task_id: str, status: TaskStatus) -> None:
    """Обновляет статус существующей задачи."""
    if task_id in tasks_store:
        tasks_store[task_id]["status"] = status.value


async def mock_clusterize_task(
    task_id: str,
    data: ClusterizeRequest,
    vectorizer: TextVectorizer,
    vector_db: VectorStorage,
    gemini_client: GeminiClient,
) -> None:
    """
    Имитирует долгую кластеризацию: PROCESSING → пауза 10 с → тестовый результат.
    """
    try:
        _set_status(task_id, TaskStatus.PROCESSING)
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

        print(
            f"Memory found: {len(known_items)} | To clusterize: {len(unknown_items)}"
        )
        print(f"Embeddings count: {len(embeddings)}")
        clusterizer = ItemClusterizer()
        new_item_clusters: list[dict[str, Any]] = await asyncio.to_thread(
            clusterizer.clusterize,
            unknown_items,
            unknown_vectors,
        )
        for cluster in new_item_clusters:
            cluster_items = [str(item) for item in cluster.get("cluster_items", [])]
            cluster_specific_attrs: list[str] = await asyncio.to_thread(
                gemini_client.get_cluster_attributes,
                cluster_items,
                data.base_attributes,
            )
            combined_attributes = list(dict.fromkeys(data.base_attributes + cluster_specific_attrs))
            cluster["attributes"] = combined_attributes
        print(f"Unknown clusters: {new_item_clusters}")
        await asyncio.sleep(10)
        tasks_store[task_id]["result"] = {
            "embeddings_count": len(embeddings),
            "known_items": known_items,
            "new_item_clusters": new_item_clusters,
            "base_attributes": data.base_attributes,
            "message": "Mock clusterization completed",
        }
        _set_status(task_id, TaskStatus.COMPLETED)
        logger.info("Clusterize task %s completed", task_id)
    except Exception as exc:
        logger.exception("Clusterize task %s failed", task_id)
        tasks_store[task_id]["status"] = TaskStatus.FAILED.value
        tasks_store[task_id]["error"] = str(exc)


async def mock_normalize_task(
    task_id: str,
    data: NormalizeRequest,
    gemini_client: GeminiClient,
) -> None:
    """
    Имитирует долгую нормализацию: PROCESSING → пауза 10 с → тестовый результат.
    """
    try:
        _set_status(task_id, TaskStatus.PROCESSING)
        batch_size = 40
        normalized_items: list[dict[str, Any]] = []
        for cluster in data.clusters:
            for idx in range(0, len(cluster.items), batch_size):
                items_batch = cluster.items[idx : idx + batch_size]
                batch_result: list[dict[str, Any]] = await asyncio.to_thread(
                    gemini_client.normalize_items,
                    items_batch,
                    cluster.attributes,
                )
                normalized_items.extend(batch_result)
        tasks_store[task_id]["result"] = {
            "normalized": normalized_items,
            "message": "Normalization completed with Gemini",
        }
        _set_status(task_id, TaskStatus.COMPLETED)
        logger.info("Normalize task %s completed", task_id)
    except Exception as exc:
        logger.exception("Normalize task %s failed", task_id)
        tasks_store[task_id]["status"] = TaskStatus.FAILED.value
        tasks_store[task_id]["error"] = str(exc)
