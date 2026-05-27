"""Фоновые задачи с хранением статусов в Redis."""

import asyncio
import logging
from typing import Any

from db.redis_client import RedisStorage
from db.vector_store import VectorStorage
from llm.gemini_client import GeminiClient
from ml.clusterizer import ItemClusterizer
from ml.vectorizer import TextVectorizer
from schemas import ClusterizeRequest, NormalizeRequest, TaskStatus
from utils.standardizer import DataStandardizer

logger = logging.getLogger(__name__)

async def create_task(task_id: str, redis_storage: RedisStorage) -> None:
    """Регистрирует новую задачу со статусом PENDING в Redis."""
    state = {
        "status": TaskStatus.PENDING.value,
        "result": None,
        "error": None,
    }
    await redis_storage.set_task_state(task_id, state)


async def get_task(task_id: str, redis_storage: RedisStorage) -> dict[str, Any] | None:
    """Возвращает запись задачи или None, если идентификатор не найден."""
    return await redis_storage.get_task_state(task_id)


async def _set_task_state(
    task_id: str,
    redis_storage: RedisStorage,
    *,
    status: TaskStatus,
    result: dict[str, Any] | None = None,
    error: str | None = None,
) -> None:
    """Обновляет состояние задачи в Redis."""
    current = await redis_storage.get_task_state(task_id) or {}
    state = {
        "status": status.value,
        "result": result if result is not None else current.get("result"),
        "error": error if error is not None else current.get("error"),
    }
    await redis_storage.set_task_state(task_id, state)


async def clusterize_task(
    task_id: str,
    data: ClusterizeRequest,
    vectorizer: TextVectorizer,
    vector_db: VectorStorage,
    gemini_client: GeminiClient,
    redis_storage: RedisStorage,
) -> None:
    """Выполняет кластеризацию с учетом памяти и атрибутов от Gemini."""
    try:
        await _set_task_state(task_id, redis_storage, status=TaskStatus.PROCESSING)
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
            cluster_specific_attrs: list[str] = await gemini_client.get_cluster_attributes(
                cluster_items,
                data.base_attributes,
            )
            combined_attributes = list(dict.fromkeys(data.base_attributes + cluster_specific_attrs))
            cluster["attributes"] = combined_attributes
        print(f"Unknown clusters: {new_item_clusters}")
        await asyncio.sleep(10)
        result_payload = {
            "embeddings_count": len(embeddings),
            "known_items": known_items,
            "new_item_clusters": new_item_clusters,
            "base_attributes": data.base_attributes,
            "message": "Clusterization completed",
        }
        await _set_task_state(
            task_id,
            redis_storage,
            status=TaskStatus.COMPLETED,
            result=result_payload,
            error=None,
        )
        logger.info("Clusterize task %s completed", task_id)
    except Exception as exc:
        logger.exception("Clusterize task %s failed", task_id)
        await _set_task_state(
            task_id,
            redis_storage,
            status=TaskStatus.FAILED,
            error=str(exc),
        )


async def normalize_task(
    task_id: str,
    data: NormalizeRequest,
    gemini_client: GeminiClient,
    standardizer: DataStandardizer,
    redis_storage: RedisStorage,
) -> None:
    """Выполняет батч-нормализацию через Gemini и очистку значений."""
    try:
        await _set_task_state(task_id, redis_storage, status=TaskStatus.PROCESSING)
        batch_size = 40
        normalized_items: list[dict[str, Any]] = []
        for cluster in data.clusters:
            for idx in range(0, len(cluster.items), batch_size):
                items_batch = cluster.items[idx : idx + batch_size]
                batch_result: list[dict[str, Any]] = await gemini_client.normalize_items(
                    items_batch,
                    cluster.attributes,
                )
                for normalized_entry in batch_result:
                    values_raw: dict[str, Any] = dict(normalized_entry.get("values", {}))
                    standardized_values = standardizer.process_item(
                        {k: str(v) for k, v in values_raw.items()}
                    )
                    normalized_entry["values"] = standardized_values
                    normalized_items.append(normalized_entry)
        result_payload = {
            "normalized": normalized_items,
            "message": "Normalization completed with Gemini",
        }
        await _set_task_state(
            task_id,
            redis_storage,
            status=TaskStatus.COMPLETED,
            result=result_payload,
            error=None,
        )
        logger.info("Normalize task %s completed", task_id)
    except Exception as exc:
        logger.exception("Normalize task %s failed", task_id)
        await _set_task_state(
            task_id,
            redis_storage,
            status=TaskStatus.FAILED,
            error=str(exc),
        )
