#!/usr/bin/env python3
"""
Проверка полного боевого флоу Nomenclature Normalization API.

Шаги:
  1. (опционально) сохранение эталонного товара в векторную память
  2. кластеризация списка номенклатуры
  3. нормализация полученных кластеров
  4. сохранение нормализованных товаров обратно в память

Запуск (API должен быть поднят, в .env задан GEMINI_API_KEY):

    python scripts/e2e_flow_check.py
    python scripts/e2e_flow_check.py --base-url http://localhost:8000
    python scripts/e2e_flow_check.py --items-file my_items.json

Формат my_items.json:
    {
      "base_attributes": ["бренд", "артикул"],
      "items": ["Товар 1", "Товар 2"]
    }
"""

from __future__ import annotations

import argparse
import json
import sys
import time
import urllib.error
import urllib.request
from typing import Any


DEFAULT_ITEMS = [
    "Кабель ВВГнг 3x2.5 100м IEK",
    "Кабель ВВГнг(А)-LS 3х2.5 100 м IEK",
    "Розетка Legrand Valena белая 2-местная",
    "Выключатель Legrand Valena одноклавишный белый",
    "Профиль алюминиевый 20x20 2м",
]

DEFAULT_BASE_ATTRIBUTES = ["бренд", "артикул", "единица измерения"]

MEMORY_KNOWN_ITEM = {
    "text": "Кабель ВВГнг 3x1.5 50м IEK",
    "attributes": {
        "бренд": "IEK",
        "артикул": "ВВГнг-3x1.5-50",
        "единица измерения": "м",
        "сечение": "3x1.5",
        "длина": "50 м",
    },
}


class ApiClient:
    """Минимальный HTTP-клиент без внешних зависимостей."""

    def __init__(self, base_url: str, timeout: float) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout

    def request(
        self,
        method: str,
        path: str,
        *,
        body: dict[str, Any] | None = None,
    ) -> Any:
        url = f"{self.base_url}{path}"
        data = None
        headers = {"Accept": "application/json"}
        if body is not None:
            data = json.dumps(body, ensure_ascii=False).encode("utf-8")
            headers["Content-Type"] = "application/json; charset=utf-8"

        req = urllib.request.Request(url, data=data, headers=headers, method=method)
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as response:
                raw = response.read().decode("utf-8")
                return json.loads(raw) if raw else None
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"{method} {path} -> HTTP {exc.code}: {detail}") from exc
        except urllib.error.URLError as exc:
            raise RuntimeError(f"Не удалось подключиться к {url}: {exc}") from exc


def wait_for_task(
    client: ApiClient,
    task_id: str,
    *,
    poll_interval: float,
    timeout: float,
    label: str,
) -> dict[str, Any]:
    """Ожидает COMPLETED/FAILED, печатает progress если API его отдаёт."""
    started = time.monotonic()
    last_progress: str | None = None

    while True:
        elapsed = time.monotonic() - started
        if elapsed > timeout:
            raise TimeoutError(
                f"{label}: превышен таймаут {timeout:.0f} с (task_id={task_id})"
            )

        payload = client.request("GET", f"/api/v1/tasks/{task_id}/status")
        status = payload.get("status")
        progress = payload.get("progress")

        if progress and progress != last_progress:
            print(f"  [{label}] progress: {progress}")
            last_progress = progress
        elif status in ("PENDING", "PROCESSING"):
            print(f"  [{label}] status={status} ({elapsed:.0f} с)")

        if status == "COMPLETED":
            print(f"  [{label}] COMPLETED за {elapsed:.1f} с")
            return payload
        if status == "FAILED":
            error = payload.get("error") or "unknown error"
            raise RuntimeError(f"{label} failed: {error}")

        time.sleep(poll_interval)


def build_normalize_request(clusterize_result: dict[str, Any]) -> dict[str, Any]:
    """Собирает тело /normalize из результата кластеризации."""
    clusters: list[dict[str, Any]] = []
    for index, cluster in enumerate(clusterize_result.get("new_item_clusters", []), start=1):
        items = cluster.get("cluster_items") or []
        attributes = cluster.get("attributes") or []
        if not items:
            continue
        clusters.append(
            {
                "name": f"cluster_{index}",
                "attributes": attributes,
                "items": items,
            }
        )

    if not clusters:
        raise RuntimeError(
            "Нет new_item_clusters для нормализации. "
            "Возможно, все товары попали в known_items — добавьте новые позиции."
        )
    return {"clusters": clusters}


def load_items(path: str | None) -> tuple[list[str], list[str]]:
    if not path:
        return DEFAULT_ITEMS, DEFAULT_BASE_ATTRIBUTES
    with open(path, encoding="utf-8") as file:
        payload = json.load(file)
    items = payload.get("items")
    base_attributes = payload.get("base_attributes", DEFAULT_BASE_ATTRIBUTES)
    if not isinstance(items, list) or not items:
        raise ValueError("В файле должен быть непустой массив 'items'")
    return [str(item) for item in items], [str(attr) for attr in base_attributes]


def run_flow(args: argparse.Namespace) -> int:
    client = ApiClient(args.base_url, timeout=args.http_timeout)
    items, base_attributes = load_items(args.items_file)

    print(f"API: {args.base_url}")
    print(f"Товаров для кластеризации: {len(items)}")
    print(f"Базовые атрибуты: {base_attributes}")
    print()

    if args.seed_memory:
        print("1/4 Сохранение эталонного товара в память...")
        memory_resp = client.request(
            "POST",
            "/api/v1/memory/save",
            body={"items": [MEMORY_KNOWN_ITEM]},
        )
        print(f"     saved_count={memory_resp.get('saved_count')}")
        print()

    print("2/4 Кластеризация...")
    clusterize_create = client.request(
        "POST",
        "/api/v1/tasks/clusterize",
        body={"items": items, "base_attributes": base_attributes},
    )
    clusterize_task_id = clusterize_create["task_id"]
    print(f"     task_id={clusterize_task_id}")

    clusterize_done = wait_for_task(
        client,
        clusterize_task_id,
        poll_interval=args.poll_interval,
        timeout=args.timeout,
        label="clusterize",
    )
    clusterize_result = clusterize_done.get("result") or {}
    known_count = len(clusterize_result.get("known_items", []))
    new_clusters_count = len(clusterize_result.get("new_item_clusters", []))
    print(f"     known_items={known_count}, new_item_clusters={new_clusters_count}")
    print()

    normalize_body = build_normalize_request(clusterize_result)
    total_normalize_items = sum(len(cluster["items"]) for cluster in normalize_body["clusters"])
    print(
        f"3/4 Нормализация ({len(normalize_body['clusters'])} кластеров, "
        f"{total_normalize_items} товаров)..."
    )

    normalize_create = client.request(
        "POST",
        "/api/v1/tasks/normalize",
        body=normalize_body,
    )
    normalize_task_id = normalize_create["task_id"]
    print(f"     task_id={normalize_task_id}")

    normalize_done = wait_for_task(
        client,
        normalize_task_id,
        poll_interval=args.poll_interval,
        timeout=args.timeout,
        label="normalize",
    )
    normalize_result = normalize_done.get("result") or {}
    normalized_items = normalize_result.get("normalized", [])
    print(f"     normalized_count={len(normalized_items)}")
    print()

    if args.save_memory and normalized_items:
        print("4/4 Сохранение нормализованных товаров в память...")
        memory_items = [
            {
                "text": entry.get("item", ""),
                "attributes": entry.get("values", {}),
            }
            for entry in normalized_items
            if entry.get("item")
        ]
        save_resp = client.request(
            "POST",
            "/api/v1/memory/save",
            body={"items": memory_items},
        )
        print(f"     saved_count={save_resp.get('saved_count')}")
    else:
        print("4/4 Сохранение в память пропущено (--no-save-memory)")

    print()
    print("=== Итог ===")
    print(
        json.dumps(
            {
                "clusterize_task_id": clusterize_task_id,
                "normalize_task_id": normalize_task_id,
                "known_items": known_count,
                "new_clusters": new_clusters_count,
                "normalized_items": len(normalized_items),
                "sample_normalized": normalized_items[:2],
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="E2E проверка API номенклатуры")
    parser.add_argument(
        "--base-url",
        default="http://localhost:8000",
        help="Базовый URL API (по умолчанию http://localhost:8000)",
    )
    parser.add_argument(
        "--items-file",
        help="JSON с полями items и base_attributes",
    )
    parser.add_argument(
        "--poll-interval",
        type=float,
        default=5.0,
        help="Интервал опроса статуса задачи, сек (по умолчанию 5)",
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=1800.0,
        help="Макс. ожидание одной задачи, сек (по умолчанию 1800 = 30 мин)",
    )
    parser.add_argument(
        "--http-timeout",
        type=float,
        default=120.0,
        help="Таймаут одного HTTP-запроса, сек",
    )
    parser.add_argument(
        "--seed-memory",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Сначала сохранить эталонный товар в Qdrant (по умолчанию да)",
    )
    parser.add_argument(
        "--save-memory",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="После нормализации сохранить результат в память (по умолчанию да)",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    try:
        raise SystemExit(run_flow(args))
    except (RuntimeError, TimeoutError, ValueError) as exc:
        print(f"\nОШИБКА: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc


if __name__ == "__main__":
    main()
