"""Скрипт администратора для очистки Redis DB (включая кэш и статусы)."""

import asyncio

from db.redis_client import RedisStorage


async def main() -> None:
    storage = RedisStorage()
    try:
        await storage.flushdb()
        print("Redis DB flushed")
    finally:
        await storage.close()


if __name__ == "__main__":
    asyncio.run(main())
