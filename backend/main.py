"""Точка входа FastAPI приложения."""

import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from api.v1 import memory_router, router
from api.ui_router import router as ui_router
from core.lifespan import lifespan

logging.basicConfig(level=logging.INFO)


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
app.include_router(router)
app.include_router(memory_router)
app.include_router(ui_router)


@app.get("/health")
async def health() -> dict[str, str]:
    """Проверка готовности API после загрузки моделей."""
    return {"status": "ok"}
