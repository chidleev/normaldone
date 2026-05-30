import asyncio
from typing import Any

from schemas.task import (
    ClusterInput,
    ClusterizeRequest,
    NormalizeProvider,
    NormalizeRequest,
    TaskStatus,
)
from service.task_service import clusterize_task, create_task, get_task, normalize_task


class FakeRedisStorage:
    def __init__(self) -> None:
        self.state: dict[str, dict[str, Any]] = {}

    async def set_task_state(self, task_id: str, state: dict[str, Any]) -> None:
        self.state[task_id] = state

    async def get_task_state(self, task_id: str) -> dict[str, Any] | None:
        return self.state.get(task_id)


class FakeVectorizer:
    provider_name = "local"
    model_name = "fake-local"

    def get_embeddings(self, texts: list[str]) -> list[list[float]]:
        return [[float(i), float(i + 1)] for i in range(len(texts))]


class FakeGeminiVectorizer:
    provider_name = "gemini"
    model_name = "fake-gemini"

    def get_embeddings(self, texts: list[str]) -> list[list[float]]:
        return [[float(i + 100), float(i + 101)] for i in range(len(texts))]


class FailingGeminiVectorizer:
    provider_name = "gemini"
    model_name = "fake-gemini"

    def get_embeddings(self, texts: list[str]) -> list[list[float]]:
        _ = texts
        raise RuntimeError("gemini embeddings unavailable")


class FakeVectorStorage:
    def find_similar(
        self,
        local_vectors: list[list[float]],
        gemini_vectors: list[list[float]] | None = None,
        item_texts: list[str] | None = None,
    ) -> list[dict[str, Any] | None]:
        _ = (item_texts, gemini_vectors)
        result: list[dict[str, Any] | None] = []
        for idx, _ in enumerate(local_vectors):
            if idx == 0:
                result.append(
                    {
                        "text": "known item",
                        "cluster_name": "Память",
                        "attributes": {"бренд": "Test"},
                    }
                )
            else:
                result.append(None)
        return result


class FakeClusterizer:
    def clusterize(
        self, items: list[str], vectors: list[list[float]]
    ) -> list[dict[str, Any]]:
        _ = vectors
        if not items:
            return []
        return [{"cluster_items": items}]


class FakeGeminiClient:
    def __init__(self) -> None:
        self.normalize_calls: list[tuple[list[str], list[str]]] = []

    async def get_cluster_profile(
        self, items: list[str], base_attrs: list[str]
    ) -> dict[str, Any]:
        _ = (items, base_attrs)
        return {
            "category": "Тестовая категория",
            "attributes": ["тип", "материал"],
            "name_template": "{тип} {материал}",
        }

    async def normalize_items(
        self, items: list[str], attributes: list[str]
    ) -> list[dict[str, Any]]:
        self.normalize_calls.append((list(items), list(attributes)))
        if not attributes:
            return [{"item": item, "values": {}} for item in items]
        if len(attributes) == 1:
            return [{"item": item, "values": {attributes[0]: "5 KG"}} for item in items]
        second_attr = attributes[1]
        return [
            {"item": item, "values": {attributes[0]: "5 KG", second_attr: "100 MM"}}
            for item in items
        ]


class FailOnSecondNormalizeCallGeminiClient(FakeGeminiClient):
    async def normalize_items(
        self, items: list[str], attributes: list[str]
    ) -> list[dict[str, Any]]:
        if len(self.normalize_calls) >= 1:
            raise RuntimeError("503 UNAVAILABLE")
        return await super().normalize_items(items, attributes)


class FailingGeminiClient:
    async def get_cluster_profile(
        self, items: list[str], base_attrs: list[str]
    ) -> dict[str, Any]:
        _ = (items, base_attrs)
        raise RuntimeError("gemini failure")


class FakeStandardizer:
    def process_item(self, attributes: dict[str, str]) -> dict[str, str]:
        return {
            key: value.replace("KG", "кг").replace("MM", "мм")
            for key, value in attributes.items()
        }


def test_clusterize_task_stores_completed_state() -> None:
    async def _run() -> None:
        redis = FakeRedisStorage()
        task_id = "task-1"
        await create_task(task_id, redis)

        await clusterize_task(
            task_id=task_id,
            data=ClusterizeRequest(items=["known item", "new item"], base_attributes=["бренд"]),
            vectorizer=FakeVectorizer(),
            local_vectorizer=FakeVectorizer(),
            gemini_vectorizer=FakeGeminiVectorizer(),
            vector_db=FakeVectorStorage(),
            llm_client=FakeGeminiClient(),
            clusterizer=FakeClusterizer(),
            task_store=redis,
        )

        state = await get_task(task_id, redis)
        assert state is not None
        assert state["status"] == TaskStatus.COMPLETED.value
        assert len(state["result"]["known_items"]) == 1
        assert state["result"]["known_items"][0]["cluster_name"] == "Память"
        assert len(state["result"]["new_item_clusters"]) == 1
        assert "тип" in state["result"]["new_item_clusters"][0]["attributes"]
        assert state["result"]["new_item_clusters"][0]["category"] == "Тестовая категория"

    asyncio.run(_run())


def test_clusterize_task_sets_failed_on_exception() -> None:
    async def _run() -> None:
        redis = FakeRedisStorage()
        task_id = "task-fail"
        await create_task(task_id, redis)

        await clusterize_task(
            task_id=task_id,
            data=ClusterizeRequest(items=["a", "b"], base_attributes=["бренд"]),
            vectorizer=FakeVectorizer(),
            local_vectorizer=FakeVectorizer(),
            gemini_vectorizer=FakeGeminiVectorizer(),
            vector_db=FakeVectorStorage(),
            llm_client=FailingGeminiClient(),
            clusterizer=FakeClusterizer(),
            task_store=redis,
        )

        state = await get_task(task_id, redis)
        assert state is not None
        assert state["status"] == TaskStatus.FAILED.value
        assert "gemini failure" in state["error"]

    asyncio.run(_run())


def test_clusterize_task_fallbacks_to_local_when_gemini_vectorizer_fails() -> None:
    async def _run() -> None:
        redis = FakeRedisStorage()
        task_id = "task-gemini-fallback"
        await create_task(task_id, redis)

        await clusterize_task(
            task_id=task_id,
            data=ClusterizeRequest(items=["known item", "new item"], base_attributes=["бренд"]),
            vectorizer=FailingGeminiVectorizer(),
            local_vectorizer=FakeVectorizer(),
            gemini_vectorizer=FailingGeminiVectorizer(),
            vector_db=FakeVectorStorage(),
            llm_client=FakeGeminiClient(),
            clusterizer=FakeClusterizer(),
            task_store=redis,
        )

        state = await get_task(task_id, redis)
        assert state is not None
        assert state["status"] == TaskStatus.COMPLETED.value
        assert state["result"]["embeddings_count"] == 2

    asyncio.run(_run())


def test_normalize_task_applies_standardizer() -> None:
    async def _run() -> None:
        redis = FakeRedisStorage()
        task_id = "task-2"
        await create_task(task_id, redis)

        request = NormalizeRequest(
            clusters=[
                ClusterInput(
                    name="cluster",
                    attributes=["вес", "длина"],
                    items=["item-1", "item-2"],
                    enriched_name_template="{вес} {длина}",
                )
            ],
            llm_provider=NormalizeProvider.G4F,
        )

        await normalize_task(
            task_id=task_id,
            data=request,
            llm_client=FakeGeminiClient(),
            standardizer=FakeStandardizer(),
            vectorizer=FakeVectorizer(),
            task_store=redis,
        )

        state = await get_task(task_id, redis)
        assert state is not None
        assert state["status"] == TaskStatus.COMPLETED.value
        first = state["result"]["normalized"][0]
        assert first["values"]["вес"] == "5 кг"
        assert first["values"]["длина"] == "100 мм"
        assert "enriched_name" in first
        assert state["result"]["clusters_collapsed"]
        assert state["result"]["clusters_collapsed"][0]["rows"]

    asyncio.run(_run())


def test_normalize_task_skips_llm_for_memory_without_new_attrs() -> None:
    async def _run() -> None:
        redis = FakeRedisStorage()
        task_id = "task-memory-skip"
        await create_task(task_id, redis)
        llm = FakeGeminiClient()
        request = NormalizeRequest(
            clusters=[
                ClusterInput(
                    name="memory-cluster",
                    attributes=["вес", "длина"],
                    items=["item-memory"],
                    enriched_name_template="{вес} {длина}",
                    item_sources={"item-memory": "memory"},
                    item_values={"item-memory": {"вес": "1 KG", "длина": "20 MM"}},
                )
            ],
            llm_provider=NormalizeProvider.G4F,
        )

        await normalize_task(
            task_id=task_id,
            data=request,
            llm_client=llm,
            standardizer=FakeStandardizer(),
            vectorizer=FakeVectorizer(),
            task_store=redis,
        )

        state = await get_task(task_id, redis)
        assert state is not None
        assert state["status"] == TaskStatus.COMPLETED.value
        assert llm.normalize_calls == []
        first = state["result"]["normalized"][0]
        assert first["values"]["вес"] == "1 кг"
        assert first["values"]["длина"] == "20 мм"

    asyncio.run(_run())


def test_normalize_task_calls_llm_only_for_new_attrs_on_memory() -> None:
    async def _run() -> None:
        redis = FakeRedisStorage()
        task_id = "task-memory-new-attrs"
        await create_task(task_id, redis)
        llm = FakeGeminiClient()
        request = NormalizeRequest(
            clusters=[
                ClusterInput(
                    name="memory-cluster",
                    attributes=["вес", "длина", "бренд"],
                    items=["item-memory"],
                    enriched_name_template="{вес} {бренд}",
                    item_sources={"item-memory": "memory"},
                    item_values={"item-memory": {"вес": "1 KG", "длина": "20 MM"}},
                )
            ],
            llm_provider=NormalizeProvider.G4F,
        )

        await normalize_task(
            task_id=task_id,
            data=request,
            llm_client=llm,
            standardizer=FakeStandardizer(),
            vectorizer=FakeVectorizer(),
            task_store=redis,
        )

        state = await get_task(task_id, redis)
        assert state is not None
        assert state["status"] == TaskStatus.COMPLETED.value
        assert llm.normalize_calls == [(["item-memory"], ["бренд"])]
        first = state["result"]["normalized"][0]
        assert first["values"]["вес"] == "1 кг"
        assert first["values"]["длина"] == "20 мм"
        assert first["values"]["бренд"] == "5 кг"

    asyncio.run(_run())


def test_normalize_task_requests_llm_for_empty_memory_values() -> None:
    async def _run() -> None:
        redis = FakeRedisStorage()
        task_id = "task-memory-empty-values"
        await create_task(task_id, redis)
        llm = FakeGeminiClient()
        request = NormalizeRequest(
            clusters=[
                ClusterInput(
                    name="memory-cluster",
                    attributes=["вес", "длина", "бренд"],
                    items=["item-memory"],
                    enriched_name_template="{вес} {бренд}",
                    item_sources={"item-memory": "memory"},
                    item_values={"item-memory": {"вес": "1 KG", "длина": "  "}},
                )
            ],
            llm_provider=NormalizeProvider.G4F,
        )

        await normalize_task(
            task_id=task_id,
            data=request,
            llm_client=llm,
            standardizer=FakeStandardizer(),
            vectorizer=FakeVectorizer(),
            task_store=redis,
        )

        state = await get_task(task_id, redis)
        assert state is not None
        assert state["status"] == TaskStatus.COMPLETED.value
        assert llm.normalize_calls == [(["item-memory"], ["длина", "бренд"])]

    asyncio.run(_run())


def test_normalize_task_keeps_partial_result_on_failure() -> None:
    async def _run() -> None:
        redis = FakeRedisStorage()
        task_id = "task-partial-failure"
        await create_task(task_id, redis)
        llm = FailOnSecondNormalizeCallGeminiClient()
        request = NormalizeRequest(
            clusters=[
                ClusterInput(
                    name="cluster-1",
                    attributes=["вес"],
                    items=["item-1"],
                    enriched_name_template="{вес}",
                ),
                ClusterInput(
                    name="cluster-2",
                    attributes=["вес"],
                    items=["item-2"],
                    enriched_name_template="{вес}",
                ),
            ],
            llm_provider=NormalizeProvider.G4F,
        )

        await normalize_task(
            task_id=task_id,
            data=request,
            llm_client=llm,
            standardizer=FakeStandardizer(),
            vectorizer=FakeVectorizer(),
            task_store=redis,
        )

        state = await get_task(task_id, redis)
        assert state is not None
        assert state["status"] == TaskStatus.FAILED.value
        assert "503 UNAVAILABLE" in state["error"]
        assert state["result"]["is_partial"] is True
        assert state["result"]["completed_cluster_indexes"] == [0]
        assert state["result"]["remaining_items_count"] == 1
        assert len(state["result"]["normalized"]) == 1

    asyncio.run(_run())


def test_normalize_task_resume_uses_seed_and_skips_completed_clusters() -> None:
    async def _run() -> None:
        redis = FakeRedisStorage()
        task_id = "task-resume"
        await create_task(task_id, redis)
        request = NormalizeRequest(
            clusters=[
                ClusterInput(
                    name="cluster-1",
                    attributes=["вес"],
                    items=["item-1"],
                    enriched_name_template="{вес}",
                ),
                ClusterInput(
                    name="cluster-2",
                    attributes=["вес"],
                    items=["item-2"],
                    enriched_name_template="{вес}",
                ),
            ],
            llm_provider=NormalizeProvider.G4F,
            resume_completed_cluster_indexes=[0],
            resume_seed_normalized=[
                {
                    "item": "item-1",
                    "enriched_name": "1 кг",
                    "aliases": ["item-1"],
                    "values": {"вес": "1 кг"},
                }
            ],
            resume_seed_clusters_collapsed=[
                {
                    "name": "cluster-1",
                    "attributes": ["вес"],
                    "rows": [],
                    "items": [],
                }
            ],
            resume_expected_count=2,
        )

        await normalize_task(
            task_id=task_id,
            data=request,
            llm_client=FakeGeminiClient(),
            standardizer=FakeStandardizer(),
            vectorizer=FakeVectorizer(),
            task_store=redis,
        )

        state = await get_task(task_id, redis)
        assert state is not None
        assert state["status"] == TaskStatus.COMPLETED.value
        assert state["result"]["is_partial"] is False
        assert state["result"]["expected_count"] == 2
        assert state["result"]["actual_count"] == 2
        assert state["result"]["completed_cluster_indexes"] == [0, 1]
        assert len(state["result"]["normalized"]) == 2

    asyncio.run(_run())
