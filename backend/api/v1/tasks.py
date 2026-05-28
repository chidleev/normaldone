"""Роуты задач кластеризации и нормализации."""

from __future__ import annotations

import logging

from fastapi import APIRouter, BackgroundTasks, Request

from api.task_dispatch import (
    dispatch_clusterize,
    dispatch_memory_save,
    dispatch_normalize,
    fetch_task_status,
)
from schemas.memory import MemorySaveRequest, MemorySaveResponse
from schemas.task import (
    ClusterizeRequest,
    NormalizeRequest,
    TaskCreateResponse,
    TaskStatusResponse,
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/v1/tasks", tags=["tasks"])
memory_router = APIRouter(prefix="/api/v1/memory", tags=["memory"])


@router.post("/clusterize", response_model=TaskCreateResponse)
async def clusterize(
    body: ClusterizeRequest,
    background_tasks: BackgroundTasks,
    request: Request,
) -> TaskCreateResponse:
    """Ставит задачу кластеризации в очередь и запускает обработчик."""
    return await dispatch_clusterize(request, body, background_tasks)


@router.post("/normalize", response_model=TaskCreateResponse)
async def normalize(
    body: NormalizeRequest,
    background_tasks: BackgroundTasks,
    request: Request,
) -> TaskCreateResponse:
    """Ставит задачу нормализации в очередь и запускает обработчик."""
    return await dispatch_normalize(request, body, background_tasks)


@router.get("/{task_id}/status", response_model=TaskStatusResponse)
async def task_status(task_id: str, request: Request) -> TaskStatusResponse:
    """Возвращает текущий статус задачи по идентификатору."""
    return await fetch_task_status(task_id, request)


@router.get("/{task_id}/result", response_model=TaskStatusResponse)
async def task_result(task_id: str, request: Request) -> TaskStatusResponse:
    """Возвращает результат при COMPLETED; иначе статус/ошибку."""
    return await fetch_task_status(task_id, request)


@memory_router.post("/save", response_model=MemorySaveResponse)
async def save_memory(body: MemorySaveRequest, request: Request) -> MemorySaveResponse:
    """Сохраняет товары с атрибутами в локальную векторную память."""
    return await dispatch_memory_save(request, body)
