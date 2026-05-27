"""Фоновые задачи и in-memory хранилище статусов."""

import asyncio
import logging
from typing import Any

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
        print(f"Embeddings count: {len(embeddings)}")
        await asyncio.sleep(10)
        tasks_store[task_id]["result"] = {
            "embeddings_count": len(embeddings),
            "clusters": [
                {
                    "name": "mock_cluster_1",
                    "attributes": data.base_attributes,
                    "items": data.items[: max(1, len(data.items) // 2)] or data.items,
                },
                {
                    "name": "mock_cluster_2",
                    "attributes": data.base_attributes,
                    "items": data.items[max(1, len(data.items) // 2) :],
                },
            ],
            "message": "Mock clusterization completed",
        }
        _set_status(task_id, TaskStatus.COMPLETED)
        logger.info("Clusterize task %s completed", task_id)
    except Exception as exc:
        logger.exception("Clusterize task %s failed", task_id)
        tasks_store[task_id]["status"] = TaskStatus.FAILED.value
        tasks_store[task_id]["error"] = str(exc)


async def mock_normalize_task(task_id: str, data: NormalizeRequest) -> None:
    """
    Имитирует долгую нормализацию: PROCESSING → пауза 10 с → тестовый результат.
    """
    try:
        _set_status(task_id, TaskStatus.PROCESSING)
        await asyncio.sleep(10)
        tasks_store[task_id]["result"] = {
            "normalized": [
                {
                    "cluster_name": cluster.name,
                    "attributes": cluster.attributes,
                    "items_count": len(cluster.items),
                }
                for cluster in data.clusters
            ],
            "message": "Mock normalization completed",
        }
        _set_status(task_id, TaskStatus.COMPLETED)
        logger.info("Normalize task %s completed", task_id)
    except Exception as exc:
        logger.exception("Normalize task %s failed", task_id)
        tasks_store[task_id]["status"] = TaskStatus.FAILED.value
        tasks_store[task_id]["error"] = str(exc)
