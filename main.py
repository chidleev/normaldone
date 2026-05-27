"""Точка входа FastAPI: эндпоинты постановки и опроса фоновых задач."""

import asyncio
import logging
import uuid
from contextlib import asynccontextmanager
from typing import Any

from fastapi import BackgroundTasks, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from db.redis_client import RedisStorage
from db.vector_store import VectorStorage
from llm.gemini_client import GeminiClient
from ml.vectorizer import TextVectorizer
from schemas import (
    ClusterizeRequest,
    MemorySaveRequest,
    MemorySaveResponse,
    NormalizeRequest,
    TaskCreateResponse,
    TaskStatus,
    TaskStatusResponse,
)
from services import (
    clusterize_task,
    create_task,
    get_task,
    normalize_task,
)
from utils.standardizer import DataStandardizer

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app_instance: FastAPI):
    """Инициализирует shared-ресурсы приложения при старте."""
    app_instance.state.redis = RedisStorage()
    app_instance.state.vectorizer = TextVectorizer()
    app_instance.state.vector_db = VectorStorage()
    app_instance.state.gemini_client = GeminiClient(app_instance.state.redis)
    app_instance.state.standardizer = DataStandardizer()
    logger.info("RedisStorage initialized")
    logger.info("TextVectorizer initialized")
    logger.info("VectorStorage initialized")
    logger.info("GeminiClient initialized")
    logger.info("DataStandardizer initialized")
    yield
    await app_instance.state.redis.close()


app = FastAPI(
    title="Nomenclature Normalization API",
    description="API для фонового обмена данными между 1С и сервером кластеризации",
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


async def _task_response(task_id: str) -> TaskStatusResponse:
    """Собирает ответ по записи задачи из хранилища."""
    record = await get_task(task_id, app.state.redis)
    if record is None:
        raise HTTPException(status_code=404, detail=f"Task {task_id} not found")
    return TaskStatusResponse(
        task_id=task_id,
        status=record["status"],
        result=record.get("result"),
        error=record.get("error"),
    )


@app.post("/api/v1/tasks/clusterize", response_model=TaskCreateResponse)
async def clusterize(
    body: ClusterizeRequest,
    background_tasks: BackgroundTasks,
) -> TaskCreateResponse:
    """Ставит задачу кластеризации в очередь и запускает обработчик."""
    task_id = str(uuid.uuid4())
    await create_task(task_id, app.state.redis)
    background_tasks.add_task(
        clusterize_task,
        task_id,
        body,
        app.state.vectorizer,
        app.state.vector_db,
        app.state.gemini_client,
        app.state.redis,
    )
    logger.info("Clusterize task %s created", task_id)
    return TaskCreateResponse(task_id=task_id, status=TaskStatus.PENDING.value)


@app.post("/api/v1/tasks/normalize", response_model=TaskCreateResponse)
async def normalize(
    body: NormalizeRequest,
    background_tasks: BackgroundTasks,
) -> TaskCreateResponse:
    """Ставит задачу нормализации в очередь и запускает обработчик."""
    task_id = str(uuid.uuid4())
    await create_task(task_id, app.state.redis)
    background_tasks.add_task(
        normalize_task,
        task_id,
        body,
        app.state.gemini_client,
        app.state.standardizer,
        app.state.redis,
    )
    logger.info("Normalize task %s created", task_id)
    return TaskCreateResponse(task_id=task_id, status=TaskStatus.PENDING.value)


@app.get("/api/v1/tasks/{task_id}/status", response_model=TaskStatusResponse)
async def task_status(task_id: str) -> TaskStatusResponse:
    """Возвращает текущий статус задачи по идентификатору."""
    return await _task_response(task_id)


@app.get("/api/v1/tasks/{task_id}/result", response_model=TaskStatusResponse)
async def task_result(task_id: str) -> TaskStatusResponse:
    """
    Возвращает результат при статусе COMPLETED;
    иначе — текущий статус и поле error при наличии.
    """
    return await _task_response(task_id)


@app.post("/api/v1/memory/save", response_model=MemorySaveResponse)
async def save_memory(body: MemorySaveRequest) -> MemorySaveResponse:
    """Сохраняет товары с атрибутами в локальную векторную память."""
    texts: list[str] = [item.text for item in body.items]
    attributes: list[dict[str, Any]] = [item.attributes for item in body.items]
    vectors: list[list[float]] = await asyncio.to_thread(
        app.state.vectorizer.get_embeddings,
        texts,
    )
    await asyncio.to_thread(app.state.vector_db.save_items, texts, vectors, attributes)
    logger.info("Saved %s items to vector memory", len(texts))
    return MemorySaveResponse(saved_count=len(texts))
