from types import SimpleNamespace
from typing import Any

from infrastructure.ml.gemini_vectorizer import GeminiVectorizer


class FakeEmbedding:
    def __init__(self, values: list[float]) -> None:
        self.values = values


class FakeModels:
    def __init__(self, fail_times: int = 0) -> None:
        self.fail_times = fail_times
        self.calls = 0

    def embed_content(self, **kwargs: Any) -> SimpleNamespace:
        contents = list(kwargs.get("contents") or [])
        self.calls += 1
        if self.calls <= self.fail_times:
            raise RuntimeError("429 Too Many Requests")
        return SimpleNamespace(embeddings=[FakeEmbedding([float(idx)]) for idx, _ in enumerate(contents)])


class FakeGenAIClient:
    def __init__(self, api_key: str, fail_times: int = 0) -> None:
        _ = api_key
        self.models = FakeModels(fail_times=fail_times)


def test_embedding_batches_wait_between_requests(monkeypatch: Any) -> None:
    monkeypatch.setenv("GEMINI_API_KEY", "fake-key")
    monkeypatch.setenv("GEMINI_EMBEDDING_REQUEST_DELAY_SECONDS", "3")
    monkeypatch.setattr("infrastructure.ml.gemini_vectorizer.genai.Client", FakeGenAIClient)

    sleeps: list[int] = []
    monkeypatch.setattr("infrastructure.ml.gemini_vectorizer.time.sleep", lambda sec: sleeps.append(int(sec)))

    vectorizer = GeminiVectorizer()
    vectors = vectorizer.get_embeddings(["a", "b", "c", "d", "e"], batch_size=2)

    assert len(vectors) == 5
    assert vectorizer.client.models.calls == 3
    assert sleeps == [3, 3]


def test_embedding_retries_on_rate_limit(monkeypatch: Any) -> None:
    monkeypatch.setenv("GEMINI_API_KEY", "fake-key")
    monkeypatch.setenv("LLM_RATE_LIMIT_RETRY_SECONDS", "7")
    monkeypatch.setenv("LLM_MAX_RETRIES", "3")
    monkeypatch.setattr(
        "infrastructure.ml.gemini_vectorizer.genai.Client",
        lambda api_key: FakeGenAIClient(api_key, fail_times=1),
    )

    sleeps: list[int] = []
    monkeypatch.setattr("infrastructure.ml.gemini_vectorizer.time.sleep", lambda sec: sleeps.append(int(sec)))

    vectorizer = GeminiVectorizer()
    vectors = vectorizer.get_embeddings(["a"], batch_size=1)

    assert len(vectors) == 1
    assert vectorizer.client.models.calls == 2
    assert 7 in sleeps
