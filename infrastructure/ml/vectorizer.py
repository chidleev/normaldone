"""Локальная векторизация текстов через sentence-transformers."""

from __future__ import annotations

from typing import ClassVar

import numpy as np
from sentence_transformers import SentenceTransformer


class TextVectorizer:
    """Singleton-обертка для модели эмбеддингов."""

    _instance: ClassVar["TextVectorizer | None"] = None
    _initialized: ClassVar[bool] = False

    def __new__(cls) -> "TextVectorizer":
        """Возвращает единственный экземпляр класса."""
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self, model_name: str = "cointegrated/rubert-tiny2") -> None:
        """Загружает модель один раз при первом создании экземпляра."""
        if self.__class__._initialized:
            return
        self.model_name: str = model_name
        self.model: SentenceTransformer = SentenceTransformer(self.model_name)
        self.__class__._initialized = True

    def get_embeddings(self, texts: list[str], batch_size: int = 32) -> list[list[float]]:
        """Вычисляет эмбеддинги батчами и возвращает list[list[float]]."""
        if not texts:
            return []

        all_vectors: list[list[float]] = []
        for idx in range(0, len(texts), batch_size):
            batch: list[str] = texts[idx : idx + batch_size]
            vectors: np.ndarray = self.model.encode(
                batch,
                batch_size=batch_size,
                convert_to_numpy=True,
                show_progress_bar=False,
            )
            all_vectors.extend(vectors.tolist())
        return all_vectors
