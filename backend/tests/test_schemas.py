from schemas.memory import MemorySaveRequest
from schemas.task import (
    ClusterProfileProvider,
    ClusterInput,
    ClusterizeRequest,
    EmbeddingProvider,
    NormalizeRequest,
    NormalizeProvider,
    TaskStatus,
)


def test_clusterize_request_schema() -> None:
    payload = ClusterizeRequest(
        items=["a", "b"],
        base_attributes=["бренд"],
        embedding_provider=EmbeddingProvider.GEMINI,
        cluster_profile_provider=ClusterProfileProvider.G4F,
    )
    assert payload.items == ["a", "b"]
    assert payload.base_attributes == ["бренд"]
    assert payload.embedding_provider == EmbeddingProvider.GEMINI
    assert payload.cluster_profile_provider == ClusterProfileProvider.G4F


def test_normalize_request_schema() -> None:
    request = NormalizeRequest(
        clusters=[ClusterInput(name="c1", attributes=["вес"], items=["item-1"])],
        llm_provider=NormalizeProvider.G4F,
    )
    assert request.clusters[0].name == "c1"
    assert request.clusters[0].attributes == ["вес"]
    assert request.llm_provider == NormalizeProvider.G4F


def test_memory_schema() -> None:
    request = MemorySaveRequest(items=[{"text": "item", "attributes": {"brand": "x"}}])
    assert request.items[0].text == "item"
    assert request.items[0].attributes["brand"] == "x"


def test_task_status_enum_values() -> None:
    assert TaskStatus.PENDING.value == "PENDING"
    assert TaskStatus.COMPLETED.value == "COMPLETED"
