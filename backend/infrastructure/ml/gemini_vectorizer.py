"""Эмбеддинги через Gemini API."""

from __future__ import annotations

import logging
import os
import time
from typing import Any

from dotenv import load_dotenv
from google import genai

from infrastructure.llm.rate_limit import is_rate_limit_error, read_rate_limits

logger = logging.getLogger(__name__)


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
        limits = read_rate_limits()
        self.default_batch_size = int(os.getenv("GEMINI_EMBEDDING_BATCH_SIZE", "32"))
        self.request_delay_seconds = int(
            os.getenv(
                "GEMINI_EMBEDDING_REQUEST_DELAY_SECONDS",
                str(limits.request_delay_seconds),
            )
        )
        self.rate_limit_retry_seconds = limits.rate_limit_retry_seconds
        self.max_retries = limits.max_retries

    def get_embeddings(
        self,
        texts: list[str],
        batch_size: int | None = None,
    ) -> list[list[float]]:
        """Возвращает эмбеддинги в формате list[list[float]]."""
        if not texts:
            return []

        size = batch_size or self.default_batch_size
        vectors: list[list[float]] = []
        for idx in range(0, len(texts), size):
            batch = texts[idx : idx + size]
            response: Any | None = None
            for attempt in range(1, self.max_retries + 1):
                try:
                    response = self.client.models.embed_content(
                        model=self.model_name,
                        contents=batch,
                    )
                    break
                except Exception as exc:
                    if is_rate_limit_error(exc) and attempt < self.max_retries:
                        wait_seconds = self.rate_limit_retry_seconds * attempt
                        logger.warning(
                            "Gemini embedding rate limit (attempt %s/%s), retry in %ss: %s",
                            attempt,
                            self.max_retries,
                            wait_seconds,
                            exc,
                        )
                        time.sleep(wait_seconds)
                        continue
                    raise

            if response is None:
                raise RuntimeError("Gemini embedding request failed without response")
            embeddings = getattr(response, "embeddings", None) or []
            for embedding in embeddings:
                values = getattr(embedding, "values", None)
                if values is None:
                    raise ValueError("Gemini embed_content returned item without values")
                vectors.append([float(v) for v in values])
            if idx + size < len(texts) and self.request_delay_seconds > 0:
                time.sleep(self.request_delay_seconds)
        return vectors
