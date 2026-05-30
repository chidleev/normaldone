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
    state: dict[str, Any] = dict(current)
    state["status"] = status.value
    state["result"] = result if result is not None else current.get("result")
    state["error"] = error if error is not None else current.get("error")
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
    local_vectorizer: EmbeddingPort,
    gemini_vectorizer: EmbeddingPort | None,
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
        embeddings: list[list[float]]
        try:
            embeddings = await asyncio.to_thread(vectorizer.get_embeddings, data.items)
        except Exception:
            preferred_provider = getattr(vectorizer, "provider_name", "").lower()
            local_provider = getattr(local_vectorizer, "provider_name", "").lower()
            if preferred_provider == local_provider:
                raise
            logger.warning(
                "Preferred embeddings failed (%s), fallback to local",
                preferred_provider or "unknown",
                exc_info=True,
            )
            await _touch_processing(
                task_id,
                task_store,
                progress="Gemini недоступен, fallback на local-векторизацию…",
            )
            embeddings = await asyncio.to_thread(local_vectorizer.get_embeddings, data.items)
            embed_provider = getattr(local_vectorizer, "provider_name", embed_provider)
            embed_model = getattr(local_vectorizer, "model_name", embed_model)
        await _touch_processing(
            task_id,
            task_store,
            progress=f"Векторизация ({embed_model}): {len(data.items)}/{len(data.items)}",
        )
        phase = "память"
        await _touch_processing(task_id, task_store, progress="Поиск в памяти…")
        local_embeddings = (
            embeddings
            if getattr(local_vectorizer, "provider_name", "").lower()
            == getattr(vectorizer, "provider_name", "").lower()
            else await asyncio.to_thread(local_vectorizer.get_embeddings, data.items)
        )
        gemini_embeddings: list[list[float]] | None = None
        if gemini_vectorizer is not None:
            gemini_provider = getattr(gemini_vectorizer, "provider_name", "").lower()
            if gemini_provider == getattr(vectorizer, "provider_name", "").lower():
                gemini_embeddings = embeddings
            else:
                try:
                    gemini_embeddings = await asyncio.to_thread(
                        gemini_vectorizer.get_embeddings,
                        data.items,
                    )
                except Exception:
                    logger.warning(
                        "Gemini vectors unavailable for memory lookup, use local only",
                        exc_info=True,
                    )
        memory_matches: list[dict[str, Any] | None] = await asyncio.to_thread(
            vector_db.find_similar,
            local_embeddings,
            gemini_embeddings,
            data.items,
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
                        "enriched_name": str(item_match.get("text") or "").strip() or item_name,
                        "attributes": dict(item_match.get("attributes") or {}),
                        "cluster_name": str(
                            item_match.get("cluster_name") or "Память"
                        ).strip()
                        or "Память",
                        "original_items": originals,
                        "original_item_values": dict(item_match.get("original_item_values") or {}),
                        "attribute_merge": dict(item_match.get("attribute_merge") or {}),
                        "attribute_merge_separators": dict(
                            item_match.get("attribute_merge_separators") or {}
                        ),
                        "text": str(item_match.get("text") or "").strip(),
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


def _normalize_partial_result_payload(
    *,
    normalized_items: list[dict[str, Any]],
    clusters_collapsed: list[dict[str, Any]],
    expected_total: int,
    completed_indexes: set[int],
    is_partial: bool,
    message: str,
) -> dict[str, Any]:
    """Собирает payload результата нормализации (partial/final)."""
    actual_count = len(normalized_items)
    return {
        "normalized": normalized_items,
        "clusters_collapsed": clusters_collapsed,
        "expected_count": expected_total,
        "actual_count": actual_count,
        "remaining_items_count": max(0, expected_total - actual_count),
        "completed_cluster_indexes": sorted(completed_indexes),
        "is_partial": is_partial,
        "message": message,
    }


async def normalize_task(
    task_id: str,
    data: NormalizeRequest,
    llm_client: LLMPort,
    standardizer: StandardizerPort,
    vectorizer: EmbeddingPort,
    task_store: TaskStorePort,
) -> None:
    """Выполняет батч-нормализацию, обогащённые имена и дедупликацию."""
    expected_total = data.resume_expected_count
    if expected_total is None:
        expected_total = sum(len(cluster.items) for cluster in data.clusters)
    completed_cluster_indexes: set[int] = {
        int(index)
        for index in (data.resume_completed_cluster_indexes or [])
        if isinstance(index, int) and 0 <= int(index) < len(data.clusters)
    }
    normalized_items: list[dict[str, Any]] = [
        dict(item) for item in (data.resume_seed_normalized or [])
    ]
    clusters_collapsed: list[dict[str, Any]] = [
        dict(cluster) for cluster in (data.resume_seed_clusters_collapsed or [])
    ]
    latest_result_payload = _normalize_partial_result_payload(
        normalized_items=normalized_items,
        clusters_collapsed=clusters_collapsed,
        expected_total=expected_total,
        completed_indexes=completed_cluster_indexes,
        is_partial=True,
        message="Normalization in progress",
    )
    try:
        await _touch_processing(
            task_id,
            task_store,
            progress=f"Нормализация: {len(completed_cluster_indexes)}/{len(data.clusters)}",
        )
        await _set_task_state(
            task_id,
            task_store,
            status=TaskStatus.PROCESSING,
            result=latest_result_payload,
            error=None,
        )
        for cluster_index, cluster in enumerate(data.clusters):
            if cluster_index in completed_cluster_indexes:
                continue
            display_index = cluster_index + 1
            template = str(cluster.enriched_name_template or "").strip()
            sources = {
                str(key).strip(): str(value).strip().lower()
                for key, value in (cluster.item_sources or {}).items()
                if str(key).strip()
            }
            item_values_map = {
                str(key).strip(): {
                    str(attr).strip(): str(val).strip()
                    for attr, val in dict(values or {}).items()
                    if str(attr).strip()
                }
                for key, values in (cluster.item_values or {}).items()
                if str(key).strip()
            }
            normalized_sources = {
                item_name: source if source in ("memory", "ai") else "ai"
                for item_name, source in sources.items()
            }
            ai_items: list[str] = []
            memory_items: list[str] = []
            for item_name in cluster.items:
                source = normalized_sources.get(item_name, "ai")
                if source == "memory":
                    memory_items.append(item_name)
                else:
                    ai_items.append(item_name)

            llm_values_by_item: dict[str, dict[str, str]] = {}
            if ai_items:
                await _touch_processing(
                    task_id,
                    task_store,
                    progress=(
                        f"LLM: нормализация кластера {display_index}/{len(data.clusters)} "
                        f"({len(ai_items)} AI-товаров)"
                    ),
                )
                ai_batch_result: list[dict[str, Any]] = await llm_client.normalize_items(
                    ai_items,
                    cluster.attributes,
                )
                for normalized_entry in ai_batch_result:
                    item_name = str(normalized_entry.get("item", "")).strip()
                    if not item_name:
                        logger.warning(
                            "Skip normalized AI entry without item field: %s",
                            normalized_entry,
                        )
                        continue
                    llm_values_by_item[item_name] = {
                        str(key).strip(): str(value).strip()
                        for key, value in dict(normalized_entry.get("values", {})).items()
                        if str(key).strip()
                    }

            memory_base_values: dict[str, dict[str, str]] = {
                item_name: dict(item_values_map.get(item_name, {})) for item_name in memory_items
            }
            memory_missing_attrs_groups: dict[tuple[str, ...], list[str]] = defaultdict(list)
            for item_name in memory_items:
                known_values = memory_base_values.get(item_name, {})
                missing_attrs = tuple(
                    attr
                    for attr in cluster.attributes
                    if attr
                    and (
                        attr not in known_values
                        or not str(known_values.get(attr, "")).strip()
                    )
                )
                if missing_attrs:
                    memory_missing_attrs_groups[missing_attrs].append(item_name)

            memory_llm_values: dict[str, dict[str, str]] = {}
            for missing_attrs, missing_items in memory_missing_attrs_groups.items():
                await _touch_processing(
                    task_id,
                    task_store,
                    progress=(
                        f"LLM: новые атрибуты в памяти {display_index}/{len(data.clusters)} "
                        f"({len(missing_items)} товаров, +{len(missing_attrs)} атрибутов)"
                    ),
                )
                memory_batch_result: list[dict[str, Any]] = await llm_client.normalize_items(
                    missing_items,
                    list(missing_attrs),
                )
                for normalized_entry in memory_batch_result:
                    item_name = str(normalized_entry.get("item", "")).strip()
                    if not item_name:
                        logger.warning(
                            "Skip normalized memory entry without item field: %s",
                            normalized_entry,
                        )
                        continue
                    memory_llm_values[item_name] = {
                        str(key).strip(): str(value).strip()
                        for key, value in dict(normalized_entry.get("values", {})).items()
                        if str(key).strip()
                    }

            await _touch_processing(
                task_id,
                task_store,
                progress=(
                    f"Сборка нормализованных строк {display_index}/{len(data.clusters)} "
                    f"({len(cluster.items)} товаров)"
                ),
            )
            cluster_entries: list[dict[str, Any]] = []
            for item_name in cluster.items:
                source = normalized_sources.get(item_name, "ai")
                values_raw: dict[str, str]
                if source == "memory":
                    values_raw = dict(memory_base_values.get(item_name, {}))
                    values_raw.update(memory_llm_values.get(item_name, {}))
                else:
                    values_raw = dict(llm_values_by_item.get(item_name, {}))
                standardized_values = standardizer.process_item(
                    {k: str(v) for k, v in values_raw.items()}
                )
                enriched_name = render_template(template, standardized_values) or item_name
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
                    f"Дедупликация кластера {display_index}/{len(data.clusters)} "
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
            completed_cluster_indexes.add(cluster_index)
            latest_result_payload = _normalize_partial_result_payload(
                normalized_items=normalized_items,
                clusters_collapsed=clusters_collapsed,
                expected_total=expected_total,
                completed_indexes=completed_cluster_indexes,
                is_partial=True,
                message="Normalization in progress",
            )
            await _set_task_state(
                task_id,
                task_store,
                status=TaskStatus.PROCESSING,
                result=latest_result_payload,
                error=None,
                progress=(
                    f"Нормализация: {len(completed_cluster_indexes)}/{len(data.clusters)}"
                ),
            )

        result_payload = _normalize_partial_result_payload(
            normalized_items=normalized_items,
            clusters_collapsed=clusters_collapsed,
            expected_total=expected_total,
            completed_indexes=completed_cluster_indexes,
            is_partial=False,
            message="Normalization completed",
        )
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
        latest_result_payload = _normalize_partial_result_payload(
            normalized_items=normalized_items,
            clusters_collapsed=clusters_collapsed,
            expected_total=expected_total,
            completed_indexes=completed_cluster_indexes,
            is_partial=True,
            message="Normalization interrupted",
        )
        await _set_task_state(
            task_id,
            task_store,
            status=TaskStatus.FAILED,
            result=latest_result_payload,
            error=sanitize_error_message(exc),
        )
