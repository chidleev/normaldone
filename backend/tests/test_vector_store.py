import uuid

from infrastructure.db.vector_store import VectorStorage


def test_item_id_is_valid_uuid() -> None:
    point_id = VectorStorage._item_id("Кабель ВВГнг 3x1.5 50м IEK")
    parsed = uuid.UUID(point_id)
    assert str(parsed) == point_id


def test_item_id_is_stable_for_same_text() -> None:
    text = "Розетка Legrand Valena"
    assert VectorStorage._item_id(text) == VectorStorage._item_id(text)
    assert VectorStorage._item_id(text) == VectorStorage._item_id(f"  {text.upper()}  ")
