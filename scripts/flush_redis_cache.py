#!/usr/bin/env python3
"""Скрипт администратора: очистка Redis DB (кэш LLM и статусы задач)."""

from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from infrastructure.db.redis_client import RedisStorage


async def main(*, confirm: bool) -> None:
    storage = RedisStorage()
    try:
        if not confirm:
            print("Отмена. Для очистки передайте флаг --yes")
            return
        await storage.flushdb()
        print("Redis DB flushed (tasks + LLM cache)")
    finally:
        await storage.close()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Полная очистка текущей Redis DB (статусы задач и кэш LLM)",
    )
    parser.add_argument(
        "--yes",
        action="store_true",
        help="Подтвердить очистку без дополнительных вопросов",
    )
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()
    try:
        asyncio.run(main(confirm=args.yes))
    except Exception as exc:
        print(f"ОШИБКА: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc
