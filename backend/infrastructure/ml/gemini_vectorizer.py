"""Эмбеддинги через Gemini API."""

from __future__ import annotations

import os
from typing import Any

from dotenv import load_dotenv
from google import genai


class GeminiVectorizer:
    """Адаптер эмбеддингов Gemini с интерфейсом EmbeddingPort."""

    provider_name = "gemini"

    def __init__(self) -> None:
        load_dotenv()
        api_key = os.getenv("GEMINI_API_KEY")
        if not api_key:
            raise ValueError("GEMINI_API_KEY is not set in environment")
        self.client = genai.Client(api_key=api_key)
        self.model_name = os.getenv("GEMINI_EMBEDDING_MODEL", "gemini-embedding-001")

    def get_embeddings(self, texts: list[str], batch_size: int = 32) -> list[list[float]]:
        """Возвращает эмбеддинги в формате list[list[float]]."""
        if not texts:
            return []

        vectors: list[list[float]] = []
        for idx in range(0, len(texts), batch_size):
            batch = texts[idx : idx + batch_size]
            response: Any = self.client.models.embed_content(
                model=self.model_name,
                contents=batch,
            )
            embeddings = getattr(response, "embeddings", None) or []
            for embedding in embeddings:
                values = getattr(embedding, "values", None)
                if values is None:
                    raise ValueError("Gemini embed_content returned item without values")
                vectors.append([float(v) for v in values])
        return vectors
