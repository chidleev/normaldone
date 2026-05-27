# Nomenclature Normalization API

FastAPI-сервер для кластеризации и нормализации товарной номенклатуры с:

- локальной векторизацией (`sentence-transformers`),
- локальной векторной памятью (`ChromaDB`),
- кэшированием и статусами задач в `Redis`,
- LLM-нормализацией через `Gemini`.

## Быстрый старт (Docker)

1. Скопируйте переменные окружения:

```bash
cp .env.example .env
```

1. Заполните `GEMINI_API_KEY` в `.env`.

1. Запустите сервисы:

```bash
docker-compose up -d --build
```

После запуска:

- API: `http://localhost:8000`
- Redis: `localhost:6379`

## Локальный запуск (без Docker)

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
uvicorn main:app --reload
```

## Полезные команды

- Тесты:

```bash
pytest -q
```

- Очистка Redis-кэша и статусов:

```bash
python scripts/flush_redis_cache.py
```

## Основные эндпоинты

- `POST /api/v1/tasks/clusterize`
- `POST /api/v1/tasks/normalize`
- `GET /api/v1/tasks/{task_id}/status`
- `GET /api/v1/tasks/{task_id}/result`
- `POST /api/v1/memory/save`
