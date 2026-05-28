#!/usr/bin/env python3
"""Скрипт администратора: очистка векторной памяти Qdrant."""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from dotenv import load_dotenv

from infrastructure.db.vector_store import VectorStorage


def main(*, confirm: bool, collection_name: str) -> None:
    load_dotenv()
    qdrant_url = os.getenv("QDRANT_URL", "(не задан, используется QDRANT_PATH)")
    qdrant_path = os.getenv("QDRANT_PATH", "./qdrant_data")
    print(f"QDRANT_URL={qdrant_url}")
    if not os.getenv("QDRANT_URL"):
        print(f"QDRANT_PATH={qdrant_path}")

    if not confirm:
        print("Отмена. Для очистки передайте флаг --yes")
        return

    storage = VectorStorage(collection_name=collection_name)
    points_before = storage.get_points_count()
    print(f"Коллекция '{collection_name}': точек до очистки = {points_before}")

    if storage.clear_collection():
        print(f"Коллекция Qdrant '{collection_name}' удалена")
    else:
        print(f"Коллекция Qdrant '{collection_name}' не найдена — нечего очищать")

    points_after = storage.get_points_count()
    print(f"Точек после очистки = {points_after}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Удаляет коллекцию векторной памяти в Qdrant (все сохранённые товары)",
    )
    parser.add_argument(
        "--yes",
        action="store_true",
        help="Подтвердить очистку без дополнительных вопросов",
    )
    parser.add_argument(
        "--collection",
        default="nomenclature_memory",
        help="Имя коллекции Qdrant (по умолчанию nomenclature_memory)",
    )
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()
    try:
        main(confirm=args.yes, collection_name=args.collection)
    except Exception as exc:
        print(f"ОШИБКА: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc
