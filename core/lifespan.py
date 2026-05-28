"""Lifespan-конфигурация для инициализации shared-ресурсов."""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from typing import AsyncIterator

from fastapi import FastAPI

from infrastructure.db.redis_client import RedisStorage
from infrastructure.db.vector_store import VectorStorage
from infrastructure.llm.factory import create_llm_client, get_llm_provider
from infrastructure.ml.clusterizer import ItemClusterizer
from infrastructure.ml.vectorizer import TextVectorizer
from infrastructure.utils.standardizer import DataStandardizer

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app_instance: FastAPI) -> AsyncIterator[None]:
    """Инициализирует и освобождает ресурсы приложения."""
    app_instance.state.redis = RedisStorage()
    app_instance.state.vectorizer = TextVectorizer()
    app_instance.state.vector_db = VectorStorage()
    app_instance.state.clusterizer = ItemClusterizer()
    app_instance.state.llm_client = create_llm_client(app_instance.state.redis)
    app_instance.state.llm_provider = get_llm_provider()
    app_instance.state.standardizer = DataStandardizer()
    logger.info("RedisStorage initialized")
    logger.info("TextVectorizer initialized")
    logger.info("VectorStorage initialized")
    logger.info("ItemClusterizer initialized")
    logger.info("LLM provider: %s", app_instance.state.llm_provider)
    logger.info("DataStandardizer initialized")
    yield
    await app_instance.state.redis.close()
