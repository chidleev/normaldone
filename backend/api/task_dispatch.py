"""Постановка и опрос задач внутри процесса (без HTTP loopback)."""

from __future__ import annotations

import asyncio
import logging
import uuid
from typing import Any

from fastapi import BackgroundTasks, HTTPException, Request

from infrastructure.llm.factory import create_llm_client, resolve_llm_provider
from infrastructure.ml.gemini_vectorizer import GeminiVectorizer
from schemas.memory import MemorySaveRequest, MemorySaveResponse
from schemas.task import (
    ClusterizeRequest,
    EmbeddingProvider,
    NormalizeRequest,
    TaskCreateResponse,
    TaskStatus,
    TaskStatusResponse,
)
from service import clusterize_task, create_task, get_task, normalize_task

logger = logging.getLogger(__name__)


async def _task_response(task_id: str, request: Request) -> TaskStatusResponse:
    record = await get_task(task_id, request.app.state.redis)
    if record is None:
        raise HTTPException(status_code=404, detail=f"Task {task_id} not found")
    return TaskStatusResponse(
        task_id=task_id,
        status=record["status"],
        result=record.get("result"),
        error=record.get("error"),
        progress=record.get("progress"),
        llm_provider=record.get("llm_provider"),
        embedding_provider=record.get("embedding_provider"),
        llm_model=record.get("llm_model"),
        embedding_model=record.get("embedding_model"),
    )


def _get_llm_client(request: Request, provider_raw: str):
    try:
        provider = resolve_llm_provider(provider_raw)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    clients = getattr(request.app.state, "llm_clients", {})
    client = clients.get(provider)
    if client is None:
        client = create_llm_client(request.app.state.redis, provider)
        clients[provider] = client
        request.app.state.llm_clients = clients
        logger.info("Initialized LLM client for provider=%s", provider)
    return provider, client


def _get_embedding_client(request: Request, provider: EmbeddingProvider):
    provider_name = provider.value
    clients = getattr(request.app.state, "embedding_clients", {})
    client = clients.get(provider_name)
    if client is None:
        try:
            if provider == EmbeddingProvider.GEMINI:
                client = GeminiVectorizer()
            else:
                client = request.app.state.vectorizer
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        clients[provider_name] = client
        request.app.state.embedding_clients = clients
        logger.info("Initialized embedding provider=%s", provider_name)
    return provider_name, client


async def dispatch_clusterize(
    request: Request,
    body: ClusterizeRequest,
    background_tasks: BackgroundTasks,
) -> TaskCreateResponse:
    embedding_provider, embedding_client = _get_embedding_client(request, body.embedding_provider)
    llm_provider, llm_client = _get_llm_client(request, body.cluster_profile_provider.value)
    task_id = str(uuid.uuid4())
    await create_task(
        task_id,
        request.app.state.redis,
        meta={
            "llm_provider": llm_provider,
            "embedding_provider": embedding_provider,
            "llm_model": getattr(llm_client, "model_name", None),
            "embedding_model": getattr(embedding_client, "model_name", None),
        },
    )
    background_tasks.add_task(
        clusterize_task,
        task_id,
        body,
        embedding_client,
        request.app.state.vector_db,
        llm_client,
        request.app.state.clusterizer,
        request.app.state.redis,
    )
    logger.info(
        "Clusterize task %s created with embedding=%s, llm=%s",
        task_id,
        embedding_provider,
        llm_provider,
    )
    return TaskCreateResponse(task_id=task_id, status=TaskStatus.PENDING.value)


async def dispatch_normalize(
    request: Request,
    body: NormalizeRequest,
    background_tasks: BackgroundTasks,
) -> TaskCreateResponse:
    provider, llm_client = _get_llm_client(request, body.llm_provider.value)
    task_id = str(uuid.uuid4())
    await create_task(
        task_id,
        request.app.state.redis,
        meta={"llm_provider": provider},
    )
    background_tasks.add_task(
        normalize_task,
        task_id,
        body,
        llm_client,
        request.app.state.standardizer,
        request.app.state.redis,
    )
    logger.info("Normalize task %s created with provider=%s", task_id, provider)
    return TaskCreateResponse(task_id=task_id, status=TaskStatus.PENDING.value)


async def fetch_task_status(task_id: str, request: Request) -> TaskStatusResponse:
    return await _task_response(task_id, request)


async def dispatch_memory_save(
    request: Request,
    body: MemorySaveRequest,
    embedding_provider: str = "local",
) -> MemorySaveResponse:
    try:
        texts: list[str] = [item.text for item in body.items]
        attributes: list[dict[str, Any]] = [item.attributes for item in body.items]
        cluster_names: list[str] = [item.cluster_name for item in body.items]
        try:
            provider = EmbeddingProvider(embedding_provider.strip().lower())
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        _, embedding_client = _get_embedding_client(request, provider)
        vectors: list[list[float]] = await asyncio.to_thread(
            embedding_client.get_embeddings,
            texts,
        )
        await asyncio.to_thread(
            request.app.state.vector_db.save_items,
            texts,
            vectors,
            attributes,
            cluster_names,
        )
        logger.info("Saved %s items to vector memory", len(texts))
        return MemorySaveResponse(saved_count=len(texts))
    except Exception as exc:
        logger.exception("Failed to save items to vector memory")
        raise HTTPException(status_code=500, detail=str(exc)) from exc
