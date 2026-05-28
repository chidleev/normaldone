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
    def get_embeddings(self, texts: list[str]) -> list[list[float]]:
        return [[float(i), float(i + 1)] for i in range(len(texts))]


class FakeVectorStorage:
    def find_similar(self, vectors: list[list[float]]) -> list[dict[str, Any] | None]:
        result: list[dict[str, Any] | None] = []
        for idx, _ in enumerate(vectors):
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
    async def get_cluster_profile(
        self, items: list[str], base_attrs: list[str]
    ) -> dict[str, Any]:
        _ = (items, base_attrs)
        return {"category": "Тестовая категория", "attributes": ["тип", "материал"]}

    async def normalize_items(
        self, items: list[str], attributes: list[str]
    ) -> list[dict[str, Any]]:
        return [
            {"item": item, "values": {attributes[0]: "5 KG", attributes[1]: "100 MM"}}
            for item in items
        ]


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
                )
            ],
            llm_provider=NormalizeProvider.G4F,
        )

        await normalize_task(
            task_id=task_id,
            data=request,
            llm_client=FakeGeminiClient(),
            standardizer=FakeStandardizer(),
            task_store=redis,
        )

        state = await get_task(task_id, redis)
        assert state is not None
        assert state["status"] == TaskStatus.COMPLETED.value
        first = state["result"]["normalized"][0]
        assert first["values"]["вес"] == "5 кг"
        assert first["values"]["длина"] == "100 мм"

    asyncio.run(_run())
