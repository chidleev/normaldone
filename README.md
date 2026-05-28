# Nomenclature Normalization API

FastAPI-сервер для кластеризации и нормализации товарной номенклатуры с:

- локальной векторизацией (`sentence-transformers`),
- локальной векторной памятью (`Qdrant`),
- кэшированием и статусами задач в `Redis`,
- LLM-нормализацией через `g4f` или `Gemini` (провайдер передается в API-запросе).

## Быстрый старт (Docker)

1. Скопируйте переменные окружения:

```bash
cp .env.example .env
```

1. Скопируйте `.env.example` → `.env`.
   Для Gemini укажите `GEMINI_API_KEY`.

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
pip install -r backend/requirements.txt
uvicorn backend.main:app --reload
```

## Полезные команды

- Тесты:

```bash
pytest -q backend/tests
```

- Очистка Redis (кэш LLM и статусы задач):

```bash
python backend/scripts/flush_redis_cache.py --yes
```

- Очистка векторной памяти Qdrant (если все товары попадают в `known_items`):

```bash
python backend/scripts/flush_qdrant_memory.py --yes
```

Полный сброс тома Qdrant в Docker: `docker compose down -v` (удалит все данные Qdrant).

## UI (Vite, отдельный контейнер)

UI вынесен в отдельный Vite-frontend контейнер и открывается по адресу:

- `http://localhost:5173`

Backend API остается на `http://localhost:8000`, фронт проксирует нужные маршруты.

UI покрывает этапы:

- загрузка CSV/XLSX, очистка пустых строк и точных дубликатов;
- запуск `clusterize` в фоне + автоопрос статуса;
- ручная правка кластеров через вкладки/таблицы;
- запуск `normalize` + автоопрос статуса;
- сохранение подтвержденных данных в память (`/api/v1/memory/save`);
- выгрузка результата в Excel (`.xlsx`, один лист = один кластер).

## Основные эндпоинты

- `POST /api/v1/tasks/clusterize`
- `POST /api/v1/tasks/normalize`
- `GET /api/v1/tasks/{task_id}/status`
- `GET /api/v1/tasks/{task_id}/result`
- `POST /api/v1/memory/save`
