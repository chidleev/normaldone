# Nomenclature Normalization API

FastAPI-сервер для кластеризации и нормализации товарной номенклатуры с:

- локальной векторизацией (`sentence-transformers`),
- локальной векторной памятью (`Qdrant`),
- кэшированием и статусами задач в `Redis`,
- LLM-нормализацией через **g4f (GPT-4 по умолчанию)** или `Gemini` (`LLM_PROVIDER`).

## Быстрый старт (Docker)

1. Скопируйте переменные окружения:

```bash
cp .env.example .env
```

1. Скопируйте `.env.example` → `.env` (по умолчанию `LLM_PROVIDER=g4f`, ключ Gemini не нужен).
   Для Gemini: `LLM_PROVIDER=gemini` и `GEMINI_API_KEY`.

1. Запустите сервисы:

```bash
docker-compose up -d --build
```

После запуска:

- API: `http://localhost:8000`
- Redis: `localhost:6379`
- Qdrant: `http://localhost:6333`

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

- Очистка Redis (кэш LLM и статусы задач):

```bash
python scripts/flush_redis_cache.py --yes
```

- Очистка векторной памяти Qdrant (если все товары попадают в `known_items`):

```bash
python scripts/flush_qdrant_memory.py --yes
```

Полный сброс тома Qdrant в Docker: `docker compose down -v` (удалит все данные Qdrant).

- E2E-проверка полного флоу на боевом API:

```bash
# Дождитесь в логах: "Application startup complete"
python scripts/e2e_flow_check.py
```

Скрипт сам ждёт `GET /health` (при первом запуске Docker модель грузится 2–5 мин).
После нормализации сохраняет `e2e_clusters.xlsx` (один лист = один кластер).

Свой путь для Excel:

```bash
python scripts/e2e_flow_check.py --excel-out reports/result.xlsx
```

Свои товары:

```bash
python scripts/e2e_flow_check.py --items-file my_items.json
```
my_items.json:
```JSON
{
  "base_attributes": ["бренд", "артикул", "единица измерения"],
  "items": ["Товар 1", "Товар 2", "Товар 3"]
}
```

## Основные эндпоинты

- `POST /api/v1/tasks/clusterize`
- `POST /api/v1/tasks/normalize`
- `GET /api/v1/tasks/{task_id}/status`
- `GET /api/v1/tasks/{task_id}/result`
- `POST /api/v1/memory/save`
