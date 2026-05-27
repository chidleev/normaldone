"""Точка входа FastAPI: эндпоинты постановки и опроса фоновых задач."""

import logging
import uuid
from contextlib import asynccontextmanager

from fastapi import BackgroundTasks, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from ml.vectorizer import TextVectorizer
from schemas import (
    ClusterizeRequest,
    NormalizeRequest,
    TaskCreateResponse,
    TaskStatus,
    TaskStatusResponse,
)
from services import (
    create_task,
    get_task,
    mock_clusterize_task,
    mock_normalize_task,
)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app_instance: FastAPI):
    """Инициализирует shared-ресурсы приложения при старте."""
    app_instance.state.vectorizer = TextVectorizer()
    logger.info("TextVectorizer initialized")
    yield


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


def _task_response(task_id: str) -> TaskStatusResponse:
    """Собирает ответ по записи задачи из хранилища."""
    record = get_task(task_id)
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
    """Ставит задачу кластеризации в очередь и запускает mock-обработчик."""
    task_id = str(uuid.uuid4())
    create_task(task_id)
    background_tasks.add_task(mock_clusterize_task, task_id, body, app.state.vectorizer)
    logger.info("Clusterize task %s created", task_id)
    return TaskCreateResponse(task_id=task_id, status=TaskStatus.PENDING.value)


@app.post("/api/v1/tasks/normalize", response_model=TaskCreateResponse)
async def normalize(
    body: NormalizeRequest,
    background_tasks: BackgroundTasks,
) -> TaskCreateResponse:
    """Ставит задачу нормализации в очередь и запускает mock-обработчик."""
    task_id = str(uuid.uuid4())
    create_task(task_id)
    background_tasks.add_task(mock_normalize_task, task_id, body)
    logger.info("Normalize task %s created", task_id)
    return TaskCreateResponse(task_id=task_id, status=TaskStatus.PENDING.value)


@app.get("/api/v1/tasks/{task_id}/status", response_model=TaskStatusResponse)
async def task_status(task_id: str) -> TaskStatusResponse:
    """Возвращает текущий статус задачи по идентификатору."""
    return _task_response(task_id)


@app.get("/api/v1/tasks/{task_id}/result", response_model=TaskStatusResponse)
async def task_result(task_id: str) -> TaskStatusResponse:
    """
    Возвращает результат при статусе COMPLETED;
    иначе — текущий статус и поле error при наличии.
    """
    return _task_response(task_id)
