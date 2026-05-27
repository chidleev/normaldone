from schemas.memory import MemorySaveRequest
from schemas.task import (
    ClusterInput,
    ClusterizeRequest,
    NormalizeRequest,
    TaskStatus,
)


def test_clusterize_request_schema() -> None:
    payload = ClusterizeRequest(items=["a", "b"], base_attributes=["бренд"])
    assert payload.items == ["a", "b"]
    assert payload.base_attributes == ["бренд"]


def test_normalize_request_schema() -> None:
    request = NormalizeRequest(
        clusters=[ClusterInput(name="c1", attributes=["вес"], items=["item-1"])]
    )
    assert request.clusters[0].name == "c1"
    assert request.clusters[0].attributes == ["вес"]


def test_memory_schema() -> None:
    request = MemorySaveRequest(items=[{"text": "item", "attributes": {"brand": "x"}}])
    assert request.items[0].text == "item"
    assert request.items[0].attributes["brand"] == "x"


def test_task_status_enum_values() -> None:
    assert TaskStatus.PENDING.value == "PENDING"
    assert TaskStatus.COMPLETED.value == "COMPLETED"
