"""Роуты задач кластеризации и нормализации."""

from __future__ import annotations

import asyncio
import logging
import uuid
from typing import Any

from fastapi import APIRouter, BackgroundTasks, HTTPException, Request

from schemas.memory import MemorySaveRequest, MemorySaveResponse
from schemas.task import (
    ClusterizeRequest,
    NormalizeRequest,
    TaskCreateResponse,
    TaskStatus,
    TaskStatusResponse,
)
from service import clusterize_task, create_task, get_task, normalize_task

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/v1/tasks", tags=["tasks"])
memory_router = APIRouter(prefix="/api/v1/memory", tags=["memory"])


async def _task_response(task_id: str, request: Request) -> TaskStatusResponse:
    """Собирает ответ по записи задачи из Redis."""
    record = await get_task(task_id, request.app.state.redis)
    if record is None:
        raise HTTPException(status_code=404, detail=f"Task {task_id} not found")
    return TaskStatusResponse(
        task_id=task_id,
        status=record["status"],
        result=record.get("result"),
        error=record.get("error"),
    )


@router.post("/clusterize", response_model=TaskCreateResponse)
async def clusterize(
    body: ClusterizeRequest,
    background_tasks: BackgroundTasks,
    request: Request,
) -> TaskCreateResponse:
    """Ставит задачу кластеризации в очередь и запускает обработчик."""
    task_id = str(uuid.uuid4())
    await create_task(task_id, request.app.state.redis)
    background_tasks.add_task(
        clusterize_task,
        task_id,
        body,
        request.app.state.vectorizer,
        request.app.state.vector_db,
        request.app.state.gemini_client,
        request.app.state.clusterizer,
        request.app.state.redis,
    )
    logger.info("Clusterize task %s created", task_id)
    return TaskCreateResponse(task_id=task_id, status=TaskStatus.PENDING.value)


@router.post("/normalize", response_model=TaskCreateResponse)
async def normalize(
    body: NormalizeRequest,
    background_tasks: BackgroundTasks,
    request: Request,
) -> TaskCreateResponse:
    """Ставит задачу нормализации в очередь и запускает обработчик."""
    task_id = str(uuid.uuid4())
    await create_task(task_id, request.app.state.redis)
    background_tasks.add_task(
        normalize_task,
        task_id,
        body,
        request.app.state.gemini_client,
        request.app.state.standardizer,
        request.app.state.redis,
    )
    logger.info("Normalize task %s created", task_id)
    return TaskCreateResponse(task_id=task_id, status=TaskStatus.PENDING.value)


@router.get("/{task_id}/status", response_model=TaskStatusResponse)
async def task_status(task_id: str, request: Request) -> TaskStatusResponse:
    """Возвращает текущий статус задачи по идентификатору."""
    return await _task_response(task_id, request)


@router.get("/{task_id}/result", response_model=TaskStatusResponse)
async def task_result(task_id: str, request: Request) -> TaskStatusResponse:
    """Возвращает результат при COMPLETED; иначе статус/ошибку."""
    return await _task_response(task_id, request)


@memory_router.post("/save", response_model=MemorySaveResponse)
async def save_memory(body: MemorySaveRequest, request: Request) -> MemorySaveResponse:
    """Сохраняет товары с атрибутами в локальную векторную память."""
    texts: list[str] = [item.text for item in body.items]
    attributes: list[dict[str, Any]] = [item.attributes for item in body.items]
    vectors: list[list[float]] = await asyncio.to_thread(
        request.app.state.vectorizer.get_embeddings,
        texts,
    )
    await asyncio.to_thread(request.app.state.vector_db.save_items, texts, vectors, attributes)
    logger.info("Saved %s items to vector memory", len(texts))
    return MemorySaveResponse(saved_count=len(texts))
