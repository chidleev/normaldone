"""Бизнес-логика задач с хранением статусов в Redis."""

from __future__ import annotations

import asyncio
import logging
from collections import defaultdict
from typing import Any

from infrastructure.naming.enriched_name import collapse_cluster_rows, render_template

from schemas.task import ClusterizeRequest, NormalizeRequest, TaskStatus
from service.ports.clusterizer import ClusterizerPort
from service.ports.embedding import EmbeddingPort
from service.ports.llm import LLMPort
from service.ports.standardizer import StandardizerPort
from service.ports.task_store import TaskStorePort
from service.ports.vector_memory import VectorMemoryPort
from utils.error_text import sanitize_error_message

logger = logging.getLogger(__name__)


async def create_task(
    task_id: str,
    task_store: TaskStorePort,
    *,
    meta: dict[str, Any] | None = None,
) -> None:
    """Регистрирует новую задачу со статусом PENDING в Redis."""
    state: dict[str, Any] = {
        "status": TaskStatus.PENDING.value,
        "result": None,
        "error": None,
    }
    if meta:
        state.update(meta)
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
    llm_client: LLMPort,
    clusterizer: ClusterizerPort,
    task_store: TaskStorePort,
) -> None:
    """Выполняет кластеризацию с учетом памяти и атрибутов от выбранного LLM."""
    llm_provider = getattr(llm_client, "provider_name", data.cluster_profile_provider.value)
    llm_model = getattr(llm_client, "model_name", llm_provider)
    embed_provider = getattr(vectorizer, "provider_name", data.embedding_provider.value)
    embed_model = getattr(vectorizer, "model_name", embed_provider)
    phase = "старт"
    try:
        await _touch_processing(
            task_id,
            task_store,
            progress=(
                f"Векторизация ({embed_provider}/{embed_model}): 0/{len(data.items)}"
            ),
        )
        await _set_task_state(task_id, task_store, status=TaskStatus.PROCESSING)
        phase = "векторизация"
        embeddings: list[list[float]] = await asyncio.to_thread(
            vectorizer.get_embeddings,
            data.items,
        )
        await _touch_processing(
            task_id,
            task_store,
            progress=f"Векторизация ({embed_model}): {len(data.items)}/{len(data.items)}",
        )
        phase = "память"
        await _touch_processing(task_id, task_store, progress="Поиск в памяти…")
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
                originals = [
                    str(name).strip()
                    for name in item_match.get("original_items") or []
                    if str(name).strip()
                ]
                known_items.append(
                    {
                        "item": item_name,
                        "attributes": dict(item_match.get("attributes") or {}),
                        "cluster_name": str(
                            item_match.get("cluster_name") or "Память"
                        ).strip()
                        or "Память",
                        "original_items": originals,
                    }
                )

        phase = "группировка"
        await _touch_processing(
            task_id,
            task_store,
            progress=f"Группировка: {len(unknown_items)} новых позиций",
        )
        new_item_clusters: list[dict[str, Any]] = await asyncio.to_thread(
            clusterizer.clusterize,
            unknown_items,
            unknown_vectors,
        )
        for cluster_index, cluster in enumerate(new_item_clusters, start=1):
            cluster_items = [str(item) for item in cluster.get("cluster_items", [])]
            phase = "профиль кластера"
            await _touch_processing(
                task_id,
                task_store,
                progress=(
                    f"Профиль ({llm_provider}/{llm_model}): кластер {cluster_index}/"
                    f"{len(new_item_clusters)} ({len(cluster_items)} товаров)"
                ),
            )
            cluster_profile: dict[str, Any] = await llm_client.get_cluster_profile(
                cluster_items,
                data.base_attributes,
            )
            cluster["category"] = str(cluster_profile.get("category", "Без категории"))
            cluster["attributes"] = list(cluster_profile.get("attributes", data.base_attributes))
            cluster["name_template"] = str(cluster_profile.get("name_template") or "").strip()

        known_groups: dict[str, list[str]] = defaultdict(list)
        for known in known_items:
            cluster_name = str(known.get("cluster_name") or "Память").strip() or "Память"
            item_name = str(known.get("item", "")).strip()
            if item_name:
                known_groups[cluster_name].append(item_name)

        known_group_total = len(known_groups)
        for group_index, (cluster_name, group_items) in enumerate(known_groups.items(), start=1):
            phase = "профиль known"
            await _touch_processing(
                task_id,
                task_store,
                progress=(
                    f"Профиль памяти ({llm_provider}): группа {group_index}/"
                    f"{known_group_total} ({len(group_items)} товаров)"
                ),
            )
            profile = await llm_client.get_cluster_profile(group_items, data.base_attributes)
            template = str(profile.get("name_template") or "").strip()
            for known in known_items:
                if str(known.get("cluster_name") or "").strip() == cluster_name:
                    known["name_template"] = template

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
            error=sanitize_error_message(
                exc,
                phase=phase,
                embedding_provider=embed_provider,
                embedding_model=embed_model,
                llm_provider=llm_provider,
                llm_model=llm_model,
            ),
        )


async def normalize_task(
    task_id: str,
    data: NormalizeRequest,
    llm_client: LLMPort,
    standardizer: StandardizerPort,
    vectorizer: EmbeddingPort,
    task_store: TaskStorePort,
) -> None:
    """Выполняет батч-нормализацию, обогащённые имена и дедупликацию."""
    try:
        await _touch_processing(
            task_id,
            task_store,
            progress=f"Нормализация: 0/{len(data.clusters)}",
        )
        await _set_task_state(task_id, task_store, status=TaskStatus.PROCESSING)
        normalized_items: list[dict[str, Any]] = []
        clusters_collapsed: list[dict[str, Any]] = []
        for cluster_index, cluster in enumerate(data.clusters, start=1):
            await _touch_processing(
                task_id,
                task_store,
                progress=(
                    f"LLM: нормализация кластера {cluster_index}/{len(data.clusters)} "
                    f"({len(cluster.items)} товаров)"
                ),
            )
            batch_result: list[dict[str, Any]] = await llm_client.normalize_items(
                cluster.items,
                cluster.attributes,
            )
            cluster_entries: list[dict[str, Any]] = []
            template = str(cluster.enriched_name_template or "").strip()
            sources = cluster.item_sources or {}
            for normalized_entry in batch_result:
                item_name = str(normalized_entry.get("item", "")).strip()
                if not item_name:
                    logger.warning("Skip normalized entry without item field: %s", normalized_entry)
                    continue
                values_raw: dict[str, Any] = dict(normalized_entry.get("values", {}))
                standardized_values = standardizer.process_item(
                    {k: str(v) for k, v in values_raw.items()}
                )
                enriched_name = render_template(template, standardized_values) or item_name
                source = str(sources.get(item_name) or "ai").strip().lower()
                if source not in ("memory", "ai"):
                    source = "ai"
                cluster_entries.append(
                    {
                        "item": item_name,
                        "enriched_name": enriched_name,
                        "values": standardized_values,
                        "source": source,
                    }
                )
                normalized_items.append(
                    {
                        "item": item_name,
                        "enriched_name": enriched_name,
                        "aliases": [item_name],
                        "values": standardized_values,
                    }
                )

            await _touch_processing(
                task_id,
                task_store,
                progress=(
                    f"Дедупликация кластера {cluster_index}/{len(data.clusters)} "
                    f"({len(cluster_entries)} позиций)"
                ),
            )
            enriched_texts = [
                str(entry.get("enriched_name") or entry.get("item") or "").strip()
                for entry in cluster_entries
            ]
            embeddings = await asyncio.to_thread(vectorizer.get_embeddings, enriched_texts)
            attribute_merge = {
                str(key).strip(): str(value).strip()
                for key, value in (cluster.attribute_merge or {}).items()
                if str(key).strip() and str(value).strip() in ("priority", "accumulative")
            }
            attribute_merge_separators = {
                str(key).strip(): str(value).strip()
                for key, value in (cluster.attribute_merge_separators or {}).items()
                if str(key).strip() and str(value).strip()
            }
            collapsed_rows = await asyncio.to_thread(
                collapse_cluster_rows,
                cluster_entries,
                embeddings,
                None,
                attribute_merge,
                attribute_merge_separators,
            )
            clusters_collapsed.append(
                {
                    "name": cluster.name,
                    "attributes": cluster.attributes,
                    "enriched_name_template": template,
                    "attribute_merge": attribute_merge,
                    "attribute_merge_separators": attribute_merge_separators,
                    "rows": collapsed_rows,
                    "items": [str(row.get("enriched_name") or "") for row in collapsed_rows],
                }
            )

        expected_total = sum(len(cluster.items) for cluster in data.clusters)
        result_payload: dict[str, Any] = {
            "normalized": normalized_items,
            "clusters_collapsed": clusters_collapsed,
            "expected_count": expected_total,
            "actual_count": len(normalized_items),
            "message": "Normalization completed",
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
            error=sanitize_error_message(exc),
        )
