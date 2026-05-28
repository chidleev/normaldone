import pytest

from infrastructure.llm.base_llm import BaseLLMClient


class DummyLLM(BaseLLMClient):
    provider_name = "dummy"

    async def _complete(self, prompt: str, *, web_search: bool = False) -> str:
        _ = (prompt, web_search)
        return "{}"


def test_validate_normalize_batch_requires_exact_items() -> None:
    client = DummyLLM(cache_store=object())  # type: ignore[arg-type]
    batch = ["Товар A", "Товар B"]
    valid = [
        {"item": "Товар A", "values": {"бренд": "X"}},
        {"item": "Товар B", "values": {"бренд": "Y"}},
    ]
    client._validate_normalize_batch(batch, valid)

    invalid = [{"item": "Товар A", "values": {"бренд": "X"}}]
    with pytest.raises(ValueError, match="Ожидалось 2"):
        client._validate_normalize_batch(batch, invalid)

    broken = [{"values": {"бренд": "X"}}, {"item": "Товар B", "values": {}}]
    with pytest.raises(ValueError, match="без поля item"):
        client._validate_normalize_batch(batch, broken)
