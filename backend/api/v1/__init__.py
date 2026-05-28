"""Экспорт роутеров API v1."""

from api.v1.tasks import memory_router, router

__all__ = ["router", "memory_router"]
