import asyncio
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from api import task_dispatch
from schemas.memory import MemoryItem, MemorySaveRequest


class FakeEmbeddingClient:
    def __init__(self, vectors: list[list[float]] | None = None, fail: bool = False) -> None:
        self._vectors = vectors or []
        self._fail = fail

    def get_embeddings(self, texts: list[str]) -> list[list[float]]:
        if self._fail:
            raise RuntimeError("embedding failure")
        if self._vectors:
            return self._vectors
        return [[float(i), float(i + 1)] for i in range(len(texts))]


class FakeVectorDB:
    def __init__(self) -> None:
        self.calls: list[dict[str, object]] = []

    def save_items(
        self,
        texts: list[str],
        local_vectors: list[list[float]],
        gemini_vectors: list[list[float]] | None,
        attributes: list[dict[str, object]],
        cluster_names: list[str] | None = None,
        original_items_list: list[list[str]] | None = None,
        original_item_values_list: list[dict[str, dict[str, object]]] | None = None,
        attribute_merge_list: list[dict[str, str]] | None = None,
        attribute_merge_separators_list: list[dict[str, str]] | None = None,
    ) -> None:
        self.calls.append(
            {
                "texts": texts,
                "local_vectors": local_vectors,
                "gemini_vectors": gemini_vectors,
                "attributes": attributes,
                "cluster_names": cluster_names,
                "original_items_list": original_items_list,
                "original_item_values_list": original_item_values_list,
                "attribute_merge_list": attribute_merge_list,
                "attribute_merge_separators_list": attribute_merge_separators_list,
            }
        )


def _request_with_db(vector_db: FakeVectorDB):
    return SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace(vector_db=vector_db)))


def _sample_payload() -> MemorySaveRequest:
    return MemorySaveRequest(
        items=[
            MemoryItem(
                text="Товар A",
                attributes={"бренд": "X"},
                cluster_name="Кластер",
                original_items=["Товар A"],
                original_item_values={"Товар A": {"бренд": "X"}},
            )
        ]
    )


def test_dispatch_memory_save_requires_local_vectors(monkeypatch: pytest.MonkeyPatch) -> None:
    async def _run() -> None:
        vector_db = FakeVectorDB()

        def _fake_get_embedding_client(request, provider):  # noqa: ANN001
            _ = request
            if provider.value == "local":
                return "local", FakeEmbeddingClient(fail=True)
            return "gemini", FakeEmbeddingClient(vectors=[[0.8, 0.9]])

        monkeypatch.setattr(task_dispatch, "_get_embedding_client", _fake_get_embedding_client)

        with pytest.raises(HTTPException) as exc_info:
            await task_dispatch.dispatch_memory_save(
                _request_with_db(vector_db),
                _sample_payload(),
                embedding_provider="gemini",
            )
        assert exc_info.value.status_code == 500
        assert vector_db.calls == []

    asyncio.run(_run())


def test_dispatch_memory_save_uses_local_when_gemini_unavailable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def _run() -> None:
        vector_db = FakeVectorDB()

        def _fake_get_embedding_client(request, provider):  # noqa: ANN001
            _ = request
            if provider.value == "local":
                return "local", FakeEmbeddingClient(vectors=[[0.1, 0.2]])
            raise RuntimeError("gemini down")

        monkeypatch.setattr(task_dispatch, "_get_embedding_client", _fake_get_embedding_client)

        response = await task_dispatch.dispatch_memory_save(
            _request_with_db(vector_db),
            _sample_payload(),
            embedding_provider="gemini",
        )

        assert response.saved_count == 1
        assert len(vector_db.calls) == 1
        call = vector_db.calls[0]
        assert call["local_vectors"] == [[0.1, 0.2]]
        assert call["gemini_vectors"] is None

    asyncio.run(_run())
