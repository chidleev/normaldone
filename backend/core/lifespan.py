"""Lifespan-конфигурация для инициализации shared-ресурсов."""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from typing import AsyncIterator

from fastapi import FastAPI

from infrastructure.db.redis_client import RedisStorage
from infrastructure.db.vector_store import VectorStorage
from infrastructure.ml.clusterizer import ItemClusterizer
from infrastructure.ml.ml_config import read_cluster_distance_threshold
from infrastructure.ml.vectorizer import TextVectorizer
from infrastructure.utils.standardizer import DataStandardizer

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app_instance: FastAPI) -> AsyncIterator[None]:
    """Инициализирует и освобождает ресурсы приложения."""
    app_instance.state.redis = RedisStorage()
    app_instance.state.vectorizer = TextVectorizer()
    app_instance.state.embedding_clients = {"local": app_instance.state.vectorizer}
    app_instance.state.vector_db = VectorStorage()
    cluster_threshold = read_cluster_distance_threshold()
    app_instance.state.clusterizer = ItemClusterizer(distance_threshold=cluster_threshold)
    app_instance.state.llm_clients = {}
    app_instance.state.standardizer = DataStandardizer()
    logger.info("RedisStorage initialized")
    logger.info("TextVectorizer initialized")
    logger.info("VectorStorage initialized")
    logger.info("ItemClusterizer initialized (distance_threshold=%s)", cluster_threshold)
    logger.info("LLM clients cache initialized")
    logger.info("DataStandardizer initialized")
    yield
    await app_instance.state.redis.close()
