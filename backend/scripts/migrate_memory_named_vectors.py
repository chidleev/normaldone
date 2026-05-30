#!/usr/bin/env python3
"""Миграция векторной памяти в named vectors (local required + gemini optional)."""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path
from typing import Any

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from dotenv import load_dotenv

from infrastructure.db.vector_store import VectorStorage
from infrastructure.ml.gemini_vectorizer import GeminiVectorizer
from infrastructure.ml.vectorizer import TextVectorizer


def _batch_payloads(source: VectorStorage, *, batch_size: int):
    offset: Any = None
    while True:
        points, offset = source.client.scroll(
            collection_name=source.collection_name,
            offset=offset,
            limit=batch_size,
            with_payload=True,
            with_vectors=False,
        )
        if not points:
            break
        payload_batch: list[dict[str, Any]] = []
        for point in points:
            payload = point.payload or {}
            if isinstance(payload, dict):
                payload_batch.append(payload)
        if payload_batch:
            yield payload_batch
        if offset is None:
            break


def main(
    *,
    source_collection: str,
    target_collection: str,
    batch_size: int,
    include_gemini: bool,
) -> None:
    load_dotenv()
    source = VectorStorage(collection_name=source_collection)
    target = VectorStorage(collection_name=target_collection)

    if not source.client.collection_exists(source.collection_name):
        print(f"Источник '{source.collection_name}' не найден, миграция не требуется")
        return

    local_vectorizer = TextVectorizer()
    gemini_vectorizer: GeminiVectorizer | None = None
    if include_gemini:
        try:
            gemini_vectorizer = GeminiVectorizer()
        except Exception as exc:
            print(f"Gemini недоступен, миграция продолжится без gemini-векторов: {exc}")

    migrated = 0
    skipped = 0
    gemini_failed_batches = 0
    for payload_batch in _batch_payloads(source, batch_size=batch_size):
        normalized = [source._parse_payload_loose(payload) for payload in payload_batch]
        texts = [str(item.get("text") or "").strip() for item in normalized]
        filtered: list[dict[str, Any]] = []
        for idx, text in enumerate(texts):
            if not text:
                skipped += 1
                continue
            filtered.append(normalized[idx])
        if not filtered:
            continue

        texts = [str(item.get("text") or "").strip() for item in filtered]
        attributes = [dict(item.get("attributes") or {}) for item in filtered]
        cluster_names = [str(item.get("cluster_name") or "").strip() for item in filtered]
        original_items_list = [list(item.get("original_items") or []) for item in filtered]
        original_item_values_list = [dict(item.get("original_item_values") or {}) for item in filtered]
        attribute_merge_list = [dict(item.get("attribute_merge") or {}) for item in filtered]
        attribute_merge_separators_list = [
            dict(item.get("attribute_merge_separators") or {}) for item in filtered
        ]

        local_vectors = local_vectorizer.get_embeddings(texts)
        gemini_vectors: list[list[float]] | None = None
        if gemini_vectorizer is not None:
            try:
                gemini_vectors = gemini_vectorizer.get_embeddings(texts)
            except Exception as exc:
                gemini_failed_batches += 1
                gemini_vectors = None
                print(f"Предупреждение: batch без gemini-векторов ({exc})")

        target.save_items(
            texts=texts,
            local_vectors=local_vectors,
            gemini_vectors=gemini_vectors,
            attributes=attributes,
            cluster_names=cluster_names,
            original_items_list=original_items_list,
            original_item_values_list=original_item_values_list,
            attribute_merge_list=attribute_merge_list,
            attribute_merge_separators_list=attribute_merge_separators_list,
        )
        migrated += len(texts)
        print(f"Перенесено {migrated} записей…")

    print("Миграция завершена")
    print(f"Источник: {source_collection}")
    print(f"Цель: {target_collection}")
    print(f"Перенесено: {migrated}")
    print(f"Пропущено пустых text: {skipped}")
    print(f"Batch без Gemini: {gemini_failed_batches}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Мигрирует старую память в named vectors: local обязателен, gemini опционален"
        )
    )
    parser.add_argument(
        "--source",
        default="nomenclature_memory",
        help="Имя исходной коллекции",
    )
    parser.add_argument(
        "--target",
        default="nomenclature_memory_named",
        help="Имя целевой коллекции",
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=128,
        help="Размер батча для scroll и пересчета эмбеддингов",
    )
    parser.add_argument(
        "--without-gemini",
        action="store_true",
        help="Мигрировать только local-векторы",
    )
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()
    try:
        main(
            source_collection=args.source,
            target_collection=args.target,
            batch_size=max(1, int(args.batch_size)),
            include_gemini=not args.without_gemini,
        )
    except Exception as exc:
        print(f"ОШИБКА: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc
