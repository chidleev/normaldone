"""API для отдельного UI-клиента ручной проверки флоу."""

from __future__ import annotations

import csv
import io
import json
import uuid
from dataclasses import dataclass, field
from typing import Any
from urllib import error, request

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from fastapi.responses import StreamingResponse
from openpyxl import Workbook, load_workbook
from pydantic import BaseModel, Field

router = APIRouter(tags=["ui"])


@dataclass
class SessionData:
    """Сессионное состояние UI-процесса."""

    base_url: str = "http://127.0.0.1:8000"
    headers: list[str] = field(default_factory=list)
    cleaned_rows: list[dict[str, str]] = field(default_factory=list)
    excluded_row_indices: set[int] = field(default_factory=set)
    selected_column: str | None = None
    base_attributes: list[str] = field(default_factory=list)
    items: list[str] = field(default_factory=list)
    embedding_provider: str = "local"
    normalize_provider: str = "g4f"
    clusterize_task_id: str | None = None
    clusterize_result: dict[str, Any] | None = None
    approved_clusters: list[dict[str, Any]] = field(default_factory=list)
    normalize_task_id: str | None = None
    normalize_result: dict[str, Any] | None = None


SESSIONS: dict[str, SessionData] = {}


class StartTaskPayload(BaseModel):
    session_id: str
    base_url: str = Field(default="http://127.0.0.1:8000")
    provider: str | None = None


class ClusterizeStartPayload(BaseModel):
    session_id: str
    base_url: str = Field(default="http://127.0.0.1:8000")
    embedding_provider: str = "local"
    profile_provider: str = "g4f"


class ConfigurePayload(BaseModel):
    session_id: str
    selected_column: str
    base_attributes: list[str]


class ClustersPayload(BaseModel):
    session_id: str
    clusters: list[dict[str, Any]]


class SaveMemoryPayload(BaseModel):
    session_id: str
    base_url: str = Field(default="http://127.0.0.1:8000")


class SessionPayload(BaseModel):
    session_id: str


class EnsureSessionPayload(BaseModel):
    session_id: str | None = None


class RowIncludePayload(BaseModel):
    session_id: str
    row_index: int
    included: bool


def _get_session(session_id: str) -> SessionData:
    session = SESSIONS.get(session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="Session not found")
    return session


def _reset_session_state(session: SessionData) -> None:
    """Сбрасывает прогон, оставляя сессию и базовый URL."""
    session.headers = []
    session.cleaned_rows = []
    session.excluded_row_indices = set()
    session.selected_column = None
    session.base_attributes = []
    session.items = []
    session.clusterize_task_id = None
    session.clusterize_result = None
    session.approved_clusters = []
    session.normalize_task_id = None
    session.normalize_result = None


def _row_empty(row: dict[str, str]) -> bool:
    return all(not str(v).strip() for v in row.values())


def _post_json(url: str, payload: dict[str, Any]) -> dict[str, Any]:
    raw = json.dumps(payload).encode("utf-8")
    req = request.Request(
        url=url,
        method="POST",
        data=raw,
        headers={"Content-Type": "application/json"},
    )
    try:
        with request.urlopen(req, timeout=120) as response:
            body = response.read().decode("utf-8")
            return json.loads(body) if body else {}
    except error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        raise HTTPException(status_code=exc.code, detail=body) from exc
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=502, detail=f"Backend unavailable: {exc}") from exc


def _get_json(url: str) -> dict[str, Any]:
    req = request.Request(url=url, method="GET")
    try:
        with request.urlopen(req, timeout=120) as response:
            body = response.read().decode("utf-8")
            return json.loads(body) if body else {}
    except error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        raise HTTPException(status_code=exc.code, detail=body) from exc
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=502, detail=f"Backend unavailable: {exc}") from exc


def _parse_csv(content: bytes) -> tuple[list[str], list[dict[str, str]]]:
    text = content.decode("utf-8-sig", errors="replace")
    reader = csv.DictReader(io.StringIO(text))
    if not reader.fieldnames:
        return [], []
    headers = [str(h).strip() for h in reader.fieldnames]
    rows: list[dict[str, str]] = []
    for row in reader:
        rows.append({str(k).strip(): str(v or "").strip() for k, v in row.items()})
    return headers, rows


def _parse_xlsx(content: bytes) -> tuple[list[str], list[dict[str, str]]]:
    wb = load_workbook(io.BytesIO(content), read_only=True, data_only=True)
    ws = wb.active
    rows = list(ws.iter_rows(values_only=True))
    if not rows:
        return [], []
    headers = [str(v).strip() if v is not None else f"col_{i+1}" for i, v in enumerate(rows[0])]
    out_rows: list[dict[str, str]] = []
    for row in rows[1:]:
        out_rows.append({headers[i]: ("" if v is None else str(v).strip()) for i, v in enumerate(row)})
    return headers, out_rows


def _clean_rows(rows: list[dict[str, str]]) -> tuple[list[dict[str, str]], int, int]:
    cleaned: list[dict[str, str]] = []
    seen: set[tuple[tuple[str, str], ...]] = set()
    removed_empty = 0
    removed_duplicates = 0
    for row in rows:
        if _row_empty(row):
            removed_empty += 1
            continue
        key = tuple(sorted((k, str(v).strip()) for k, v in row.items()))
        if key in seen:
            removed_duplicates += 1
            continue
        seen.add(key)
        cleaned.append({k: str(v).strip() for k, v in row.items()})
    return cleaned, removed_empty, removed_duplicates


def _build_default_clusters(clusterize_result: dict[str, Any] | None) -> list[dict[str, Any]]:
    if not clusterize_result:
        return []
    base_attributes = list(clusterize_result.get("base_attributes") or [])
    clusters: list[dict[str, Any]] = []
    for idx, cluster in enumerate(clusterize_result.get("new_item_clusters", []), start=1):
        clusters.append(
            {
                "name": str(cluster.get("category") or f"Cluster {idx}"),
                "attributes": list(cluster.get("attributes") or base_attributes),
                "items": [str(item) for item in cluster.get("cluster_items", []) if str(item).strip()],
            }
        )
    for idx, known in enumerate(clusterize_result.get("known_items", []), start=1):
        attrs = known.get("attributes")
        attr_keys = list(attrs.keys()) if isinstance(attrs, dict) else base_attributes
        item_name = str(known.get("item", "")).strip()
        if item_name:
            clusters.append(
                {
                    "name": f"Known {idx}",
                    "attributes": attr_keys or base_attributes,
                    "items": [item_name],
                }
            )
    return clusters


@router.post("/ui/api/session/new")
async def create_session() -> dict[str, str]:
    session_id = str(uuid.uuid4())
    SESSIONS[session_id] = SessionData()
    return {"session_id": session_id}


@router.post("/ui/api/session/ensure")
async def ensure_session(payload: EnsureSessionPayload) -> dict[str, str]:
    """Возвращает существующую сессию или создает новую."""
    session_id = (payload.session_id or "").strip()
    if session_id and session_id in SESSIONS:
        return {"session_id": session_id}
    new_session_id = str(uuid.uuid4())
    SESSIONS[new_session_id] = SessionData()
    return {"session_id": new_session_id}


@router.post("/ui/api/session/reset")
async def reset_session(payload: SessionPayload) -> dict[str, str]:
    session = _get_session(payload.session_id)
    _reset_session_state(session)
    return {"status": "reset"}


@router.post("/ui/api/session/drop")
async def drop_session(payload: SessionPayload) -> dict[str, str]:
    """Удаляет сессию полностью."""
    SESSIONS.pop(payload.session_id, None)
    return {"status": "dropped"}


@router.post("/ui/api/upload")
async def upload_data(
    session_id: str = Form(...),
    file: UploadFile = File(...),
) -> dict[str, Any]:
    session = _get_session(session_id)
    ext = Path(file.filename or "").suffix.lower()
    content = await file.read()
    if ext == ".csv":
        headers, rows = _parse_csv(content)
    elif ext in {".xlsx", ".xlsm"}:
        headers, rows = _parse_xlsx(content)
    else:
        raise HTTPException(status_code=400, detail="Only CSV/XLSX supported")
    if not headers:
        raise HTTPException(status_code=400, detail="No columns found in file")
    cleaned_rows, removed_empty, removed_duplicates = _clean_rows(rows)
    if not cleaned_rows:
        raise HTTPException(status_code=400, detail="No rows left after cleanup")

    _reset_session_state(session)
    session.headers = headers
    session.cleaned_rows = cleaned_rows

    return {
        "headers": headers,
        "stats": {
            "rows_total": len(rows),
            "rows_after_cleaning": len(cleaned_rows),
            "removed_empty_rows": removed_empty,
            "removed_duplicates": removed_duplicates,
        },
        "preview_rows": [],
    }


@router.get("/ui/api/rows/{session_id}")
async def list_rows(
    session_id: str,
    page: int = 1,
    page_size: int = 10,
) -> dict[str, Any]:
    session = _get_session(session_id)
    if page < 1:
        page = 1
    if page_size < 1:
        page_size = 10
    if page_size > 100:
        page_size = 100
    total = len(session.cleaned_rows)
    total_pages = max(1, (total + page_size - 1) // page_size)
    if page > total_pages:
        page = total_pages
    start = (page - 1) * page_size
    end = start + page_size
    rows_payload: list[dict[str, Any]] = []
    for idx in range(start, min(end, total)):
        rows_payload.append(
            {
                "row_index": idx,
                "included": idx not in session.excluded_row_indices,
                "cells": session.cleaned_rows[idx],
            }
        )
    return {
        "page": page,
        "page_size": page_size,
        "total_rows": total,
        "total_pages": total_pages,
        "rows": rows_payload,
    }


@router.post("/ui/api/rows/include")
async def set_row_included(payload: RowIncludePayload) -> dict[str, Any]:
    session = _get_session(payload.session_id)
    if payload.row_index < 0 or payload.row_index >= len(session.cleaned_rows):
        raise HTTPException(status_code=400, detail="row_index out of range")
    if payload.included:
        session.excluded_row_indices.discard(payload.row_index)
    else:
        session.excluded_row_indices.add(payload.row_index)
    return {"status": "ok"}


@router.post("/ui/api/configure")
async def configure(payload: ConfigurePayload) -> dict[str, Any]:
    session = _get_session(payload.session_id)
    if payload.selected_column not in session.headers:
        raise HTTPException(status_code=400, detail="Selected column not found")
    attrs = [a.strip() for a in payload.base_attributes if a.strip()]
    if not attrs:
        raise HTTPException(status_code=400, detail="Provide at least one base attribute")
    items = [
        str(row.get(payload.selected_column, "")).strip()
        for idx, row in enumerate(session.cleaned_rows)
        if idx not in session.excluded_row_indices
    ]
    items = [item for item in items if item]
    if not items:
        raise HTTPException(status_code=400, detail="Selected column has no values")

    session.selected_column = payload.selected_column
    session.base_attributes = attrs
    session.items = items
    return {"selected_column": payload.selected_column, "base_attributes": attrs, "items_count": len(items)}


@router.post("/ui/api/clusterize/start")
async def start_clusterize(payload: ClusterizeStartPayload) -> dict[str, Any]:
    session = _get_session(payload.session_id)
    session.base_url = payload.base_url.rstrip("/")
    if not session.items:
        raise HTTPException(status_code=400, detail="Upload file and save config first")
    session.embedding_provider = payload.embedding_provider
    response = _post_json(
        f"{session.base_url}/api/v1/tasks/clusterize",
        {
            "items": session.items,
            "base_attributes": session.base_attributes,
            "embedding_provider": session.embedding_provider,
            "cluster_profile_provider": payload.profile_provider,
        },
    )
    task_id = str(response.get("task_id", "")).strip()
    if not task_id:
        raise HTTPException(status_code=502, detail="Backend did not return task_id")
    session.clusterize_task_id = task_id
    return response


@router.post("/ui/api/normalize/start")
async def start_normalize(payload: StartTaskPayload) -> dict[str, Any]:
    session = _get_session(payload.session_id)
    session.base_url = payload.base_url.rstrip("/")
    if not session.approved_clusters:
        raise HTTPException(status_code=400, detail="Approve clusters first")
    if payload.provider:
        session.normalize_provider = payload.provider
    response = _post_json(
        f"{session.base_url}/api/v1/tasks/normalize",
        {"clusters": session.approved_clusters, "llm_provider": session.normalize_provider},
    )
    task_id = str(response.get("task_id", "")).strip()
    if not task_id:
        raise HTTPException(status_code=502, detail="Backend did not return task_id")
    session.normalize_task_id = task_id
    return response


@router.get("/ui/api/task/{session_id}/{task_type}")
async def get_task_status(session_id: str, task_type: str) -> dict[str, Any]:
    session = _get_session(session_id)
    task_id = session.clusterize_task_id if task_type == "clusterize" else session.normalize_task_id
    if task_type not in {"clusterize", "normalize"}:
        raise HTTPException(status_code=400, detail="task_type must be clusterize|normalize")
    if not task_id:
        raise HTTPException(status_code=400, detail="Task not started")

    status_payload = _get_json(f"{session.base_url}/api/v1/tasks/{task_id}/status")
    if status_payload.get("status") != "COMPLETED":
        return status_payload
    result_payload = _get_json(f"{session.base_url}/api/v1/tasks/{task_id}/result")
    if task_type == "clusterize":
        session.clusterize_result = result_payload.get("result") or {}
        if not session.approved_clusters:
            session.approved_clusters = _build_default_clusters(session.clusterize_result)
    else:
        session.normalize_result = result_payload.get("result") or {}
    return result_payload


@router.get("/ui/api/clusters/{session_id}")
async def get_clusters(session_id: str) -> dict[str, Any]:
    return {"clusters": _get_session(session_id).approved_clusters}


@router.post("/ui/api/clusters/save")
async def save_clusters(payload: ClustersPayload) -> dict[str, Any]:
    session = _get_session(payload.session_id)
    valid: list[dict[str, Any]] = []
    for cluster in payload.clusters:
        name = str(cluster.get("name", "")).strip() or "Cluster"
        attrs = [str(v).strip() for v in cluster.get("attributes", []) if str(v).strip()]
        items = [str(v).strip() for v in cluster.get("items", []) if str(v).strip()]
        if not items:
            continue
        valid.append({"name": name, "attributes": attrs or session.base_attributes, "items": items})
    if not valid:
        raise HTTPException(status_code=400, detail="No valid clusters to save")
    session.approved_clusters = valid
    return {"saved_clusters": len(valid)}


@router.post("/ui/api/memory/save")
async def save_memory(payload: SaveMemoryPayload) -> dict[str, Any]:
    session = _get_session(payload.session_id)
    session.base_url = payload.base_url.rstrip("/")
    normalized = (session.normalize_result or {}).get("normalized") or []
    if not normalized:
        raise HTTPException(status_code=400, detail="Normalize result is empty")
    items = []
    for row in normalized:
        item_name = str(row.get("item", "")).strip()
        if item_name:
            items.append({"text": item_name, "attributes": dict(row.get("values", {}))})
    if not items:
        raise HTTPException(status_code=400, detail="No valid normalized items")
    return _post_json(f"{session.base_url}/api/v1/memory/save", {"items": items})


@router.get("/ui/api/export/{session_id}/xlsx")
async def export_xlsx(session_id: str) -> StreamingResponse:
    session = _get_session(session_id)
    clusters = session.approved_clusters or []
    if not clusters:
        raise HTTPException(status_code=400, detail="No clusters to export")
    normalized = (session.normalize_result or {}).get("normalized") or []
    normalized_map: dict[str, dict[str, Any]] = {
        str(row.get("item", "")).strip(): dict(row.get("values", {}))
        for row in normalized
        if str(row.get("item", "")).strip()
    }

    wb = Workbook()
    wb.remove(wb.active)
    for idx, cluster in enumerate(clusters, start=1):
        sheet_name = (str(cluster.get("name", "")).strip() or f"Cluster_{idx}")[:31]
        ws = wb.create_sheet(title=sheet_name)
        attributes = [str(a).strip() for a in cluster.get("attributes", []) if str(a).strip()]
        items = [str(i).strip() for i in cluster.get("items", []) if str(i).strip()]
        ws.append(["Номенклатура", *attributes])
        for item_name in items:
            values = normalized_map.get(item_name, {})
            ws.append([item_name, *[values.get(attr, "") for attr in attributes]])

    output = io.BytesIO()
    wb.save(output)
    output.seek(0)
    return StreamingResponse(
        output,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": 'attachment; filename="clusters_export.xlsx"'},
    )
