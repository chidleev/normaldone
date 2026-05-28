"""API для отдельного UI-клиента ручной проверки флоу."""

from __future__ import annotations

import csv
import io
import json
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from fastapi import APIRouter, BackgroundTasks, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import StreamingResponse
from openpyxl import Workbook, load_workbook
import os

from api.task_dispatch import (
    dispatch_clusterize,
    dispatch_memory_save,
    dispatch_normalize,
    fetch_task_status,
)
from infrastructure.llm.factory import resolve_llm_provider
from pydantic import BaseModel, Field
from schemas.memory import MemoryItem, MemorySaveRequest
from schemas.task import (
    ClusterInput,
    ClusterProfileProvider,
    ClusterizeRequest,
    EmbeddingProvider,
    NormalizeProvider,
    NormalizeRequest,
)

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
    cluster_profile_provider: str = "g4f"
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


class RowUpdatePayload(BaseModel):
    session_id: str
    row_index: int
    cells: dict[str, str] = Field(default_factory=dict)


class RowCreatePayload(BaseModel):
    session_id: str
    cells: dict[str, str] = Field(default_factory=dict)


class RowDeletePayload(BaseModel):
    session_id: str
    row_index: int


class ColumnAddPayload(BaseModel):
    session_id: str
    column_name: str
    after_column: str | None = None


class SetSourceColumnPayload(BaseModel):
    session_id: str
    column_name: str


class ColumnRenamePayload(BaseModel):
    session_id: str
    old_name: str
    new_name: str


class ColumnDeletePayload(BaseModel):
    session_id: str
    column_name: str


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


def _validate_llm_provider(provider: str) -> str:
    resolved = resolve_llm_provider(provider)
    if resolved == "gemini" and not os.getenv("GEMINI_API_KEY"):
        raise HTTPException(
            status_code=400,
            detail="GEMINI_API_KEY не задан на сервере. Укажите ключ в .env или выберите g4f.",
        )
    return resolved


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


def _item_cluster_name_map(clusters: list[dict[str, Any]]) -> dict[str, str]:
    """Строит соответствие номенклатура → имя кластера из approved_clusters."""
    mapping: dict[str, str] = {}
    for cluster in clusters:
        name = str(cluster.get("name", "")).strip() or "Cluster"
        item_names = [str(i).strip() for i in cluster.get("items", []) if str(i).strip()]
        for row in cluster.get("rows") or []:
            item_name = str(row.get("item", "")).strip()
            if item_name:
                item_names.append(item_name)
        for item_name in item_names:
            mapping[item_name] = name
    return mapping


def _clusters_from_known_items(
    known_items: list[dict[str, Any]],
    base_attributes: list[str],
) -> list[dict[str, Any]]:
    """Группирует позиции из памяти по cluster_name с заполненными values."""
    from collections import defaultdict

    groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for known in known_items:
        item_name = str(known.get("item", "")).strip()
        if not item_name:
            continue
        cluster_name = str(known.get("cluster_name") or "").strip()
        if not cluster_name:
            cluster_name = str(known.get("text") or "").strip() or item_name
        groups[cluster_name].append(known)

    clusters: list[dict[str, Any]] = []
    for cluster_name, group in groups.items():
        attr_keys: list[str] = []
        rows: list[dict[str, Any]] = []
        items: list[str] = []
        for known in group:
            item_name = str(known.get("item", "")).strip()
            attrs = known.get("attributes")
            values: dict[str, str] = {}
            if isinstance(attrs, dict):
                values = {
                    str(key).strip(): str(value).strip()
                    for key, value in attrs.items()
                    if str(key).strip()
                }
            for key in values:
                if key not in attr_keys:
                    attr_keys.append(key)
            items.append(item_name)
            rows.append({"item": item_name, "values": values})
        clusters.append(
            {
                "name": cluster_name,
                "attributes": attr_keys or list(base_attributes),
                "items": items,
                "rows": rows,
            }
        )
    return clusters


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
    clusters.extend(
        _clusters_from_known_items(
            list(clusterize_result.get("known_items") or []),
            base_attributes,
        )
    )
    return clusters


def _clusters_for_ui(session: SessionData) -> list[dict[str, Any]]:
    """Кластеры для UI: items + rows с values после нормализации."""
    clusters = session.approved_clusters or []
    normalized_map: dict[str, dict[str, Any]] = {
        str(row.get("item", "")).strip(): dict(row.get("values") or {})
        for row in (session.normalize_result or {}).get("normalized") or []
        if str(row.get("item", "")).strip()
    }

    payload: list[dict[str, Any]] = []
    for cluster in clusters:
        name = str(cluster.get("name", "")).strip() or "Cluster"
        attrs = [str(a).strip() for a in cluster.get("attributes", []) if str(a).strip()]
        items = [str(i).strip() for i in cluster.get("items", []) if str(i).strip()]
        stored_rows_map: dict[str, dict[str, Any]] = {
            str(row.get("item", "")).strip(): dict(row.get("values") or {})
            for row in cluster.get("rows") or []
            if str(row.get("item", "")).strip()
        }
        rows: list[dict[str, Any]] = []
        for item_name in items:
            values_raw = {
                **stored_rows_map.get(item_name, {}),
                **normalized_map.get(item_name, {}),
            }
            row_attrs = list(attrs)
            for key in values_raw:
                key_name = str(key).strip()
                if key_name and key_name not in row_attrs:
                    row_attrs.append(key_name)
            rows.append(
                {
                    "item": item_name,
                    "values": {attr: str(values_raw.get(attr, "")).strip() for attr in row_attrs},
                }
            )
        merged_attrs = list(attrs)
        for row in rows:
            for attr in row["values"]:
                if attr not in merged_attrs:
                    merged_attrs.append(attr)
        payload.append(
            {
                "name": name,
                "attributes": merged_attrs or attrs,
                "items": items,
                "rows": rows,
            }
        )
    return payload


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
    session.selected_column = headers[0] if headers else None

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


@router.post("/ui/api/rows/update")
async def update_row(payload: RowUpdatePayload) -> dict[str, Any]:
    session = _get_session(payload.session_id)
    if payload.row_index < 0 or payload.row_index >= len(session.cleaned_rows):
        raise HTTPException(status_code=400, detail="row_index out of range")
    row = session.cleaned_rows[payload.row_index]
    for key, value in payload.cells.items():
        key_name = str(key).strip()
        if key_name in session.headers:
            row[key_name] = str(value or "").strip()
    return {"status": "ok", "row_index": payload.row_index, "cells": row}


@router.post("/ui/api/rows/add")
async def add_row(payload: RowCreatePayload) -> dict[str, Any]:
    session = _get_session(payload.session_id)
    if not session.headers:
        raise HTTPException(status_code=400, detail="Upload file first")
    new_row = {header: "" for header in session.headers}
    for key, value in payload.cells.items():
        key_name = str(key).strip()
        if key_name in session.headers:
            new_row[key_name] = str(value or "").strip()
    source_col = session.selected_column or session.headers[0]
    if not str(new_row.get(source_col, "")).strip():
        raise HTTPException(status_code=400, detail="Source nomenclature is required")
    session.cleaned_rows.insert(0, new_row)
    session.excluded_row_indices = {idx + 1 for idx in session.excluded_row_indices}
    return {"status": "ok", "row_index": 0, "cells": new_row}


@router.post("/ui/api/rows/delete")
async def delete_row(payload: RowDeletePayload) -> dict[str, Any]:
    session = _get_session(payload.session_id)
    if payload.row_index < 0 or payload.row_index >= len(session.cleaned_rows):
        raise HTTPException(status_code=400, detail="row_index out of range")
    session.cleaned_rows.pop(payload.row_index)
    updated_excluded: set[int] = set()
    for idx in session.excluded_row_indices:
        if idx == payload.row_index:
            continue
        updated_excluded.add(idx - 1 if idx > payload.row_index else idx)
    session.excluded_row_indices = updated_excluded
    return {"status": "ok"}


@router.post("/ui/api/columns/add")
async def add_column(payload: ColumnAddPayload) -> dict[str, Any]:
    session = _get_session(payload.session_id)
    name = payload.column_name.strip()
    if not name:
        raise HTTPException(status_code=400, detail="column_name is required")
    if name in session.headers:
        raise HTTPException(status_code=400, detail="Column already exists")
    anchor = (payload.after_column or "").strip() or session.selected_column or ""
    if not anchor and session.headers:
        anchor = session.headers[0]
    if anchor and anchor in session.headers:
        insert_at = session.headers.index(anchor) + 1
    else:
        insert_at = 0
    session.headers.insert(insert_at, name)
    for row in session.cleaned_rows:
        row[name] = ""
    return {"status": "ok", "headers": session.headers}


@router.post("/ui/api/columns/set-source")
async def set_source_column(payload: SetSourceColumnPayload) -> dict[str, Any]:
    session = _get_session(payload.session_id)
    name = payload.column_name.strip()
    if name not in session.headers:
        raise HTTPException(status_code=400, detail="Column not found")
    session.selected_column = name
    return {"selected_column": name, "headers": session.headers}


@router.post("/ui/api/columns/rename")
async def rename_column(payload: ColumnRenamePayload) -> dict[str, Any]:
    session = _get_session(payload.session_id)
    old_name = payload.old_name.strip()
    new_name = payload.new_name.strip()
    if not old_name or not new_name:
        raise HTTPException(status_code=400, detail="old_name and new_name are required")
    if old_name not in session.headers:
        raise HTTPException(status_code=400, detail="Column not found")
    if new_name != old_name and new_name in session.headers:
        raise HTTPException(status_code=400, detail="New column name already exists")
    idx = session.headers.index(old_name)
    session.headers[idx] = new_name
    for row in session.cleaned_rows:
        row[new_name] = row.pop(old_name, "")
    return {"status": "ok", "headers": session.headers}


@router.post("/ui/api/columns/delete")
async def delete_column(payload: ColumnDeletePayload) -> dict[str, Any]:
    session = _get_session(payload.session_id)
    name = payload.column_name.strip()
    if name not in session.headers:
        raise HTTPException(status_code=400, detail="Column not found")
    if len(session.headers) <= 1:
        raise HTTPException(status_code=400, detail="Cannot delete the last column")
    session.headers = [h for h in session.headers if h != name]
    for row in session.cleaned_rows:
        row.pop(name, None)
    return {"status": "ok", "headers": session.headers}


@router.post("/ui/api/configure")
async def configure(payload: ConfigurePayload) -> dict[str, Any]:
    session = _get_session(payload.session_id)
    if payload.selected_column not in session.headers:
        raise HTTPException(status_code=400, detail="Selected column not found")
    attrs = [a.strip() for a in payload.base_attributes if a.strip()]
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
async def start_clusterize(
    payload: ClusterizeStartPayload,
    request: Request,
    background_tasks: BackgroundTasks,
) -> dict[str, Any]:
    session = _get_session(payload.session_id)
    if not session.items:
        raise HTTPException(status_code=400, detail="Upload file and save config first")
    session.embedding_provider = payload.embedding_provider.strip().lower()
    session.cluster_profile_provider = _validate_llm_provider(payload.profile_provider)
    try:
        embedding = EmbeddingProvider(session.embedding_provider)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    body = ClusterizeRequest(
        items=session.items,
        base_attributes=session.base_attributes,
        embedding_provider=embedding,
        cluster_profile_provider=ClusterProfileProvider(session.cluster_profile_provider),
    )
    created = await dispatch_clusterize(request, body, background_tasks)
    session.clusterize_task_id = created.task_id
    return {
        "task_id": created.task_id,
        "status": created.status,
        "cluster_profile_provider": session.cluster_profile_provider,
        "embedding_provider": session.embedding_provider,
    }


@router.post("/ui/api/normalize/start")
async def start_normalize(
    payload: StartTaskPayload,
    request: Request,
    background_tasks: BackgroundTasks,
) -> dict[str, Any]:
    session = _get_session(payload.session_id)
    if not session.approved_clusters:
        raise HTTPException(status_code=400, detail="Approve clusters first")
    if payload.provider:
        session.normalize_provider = _validate_llm_provider(payload.provider)
    clusters = [
        ClusterInput(
            name=str(cluster.get("name", "")).strip() or "Cluster",
            attributes=[str(a).strip() for a in cluster.get("attributes", []) if str(a).strip()],
            items=[str(i).strip() for i in cluster.get("items", []) if str(i).strip()],
        )
        for cluster in session.approved_clusters
    ]
    body = NormalizeRequest(
        clusters=clusters,
        llm_provider=NormalizeProvider(session.normalize_provider),
    )
    created = await dispatch_normalize(request, body, background_tasks)
    session.normalize_task_id = created.task_id
    return {"task_id": created.task_id, "status": created.status}


@router.get("/ui/api/task/{session_id}/{task_type}")
async def get_task_status(session_id: str, task_type: str, request: Request) -> dict[str, Any]:
    session = _get_session(session_id)
    task_id = session.clusterize_task_id if task_type == "clusterize" else session.normalize_task_id
    if task_type not in {"clusterize", "normalize"}:
        raise HTTPException(status_code=400, detail="task_type must be clusterize|normalize")
    if not task_id:
        raise HTTPException(status_code=400, detail="Task not started")

    status = await fetch_task_status(task_id, request)
    payload = status.model_dump()
    if status.status != "COMPLETED":
        return payload
    if task_type == "clusterize":
        session.clusterize_result = status.result or {}
        if not session.approved_clusters:
            session.approved_clusters = _build_default_clusters(session.clusterize_result)
    else:
        session.normalize_result = status.result or {}
    return payload


@router.get("/ui/api/clusters/{session_id}")
async def get_clusters(session_id: str) -> dict[str, Any]:
    return {"clusters": _clusters_for_ui(_get_session(session_id))}


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
async def save_memory(payload: SaveMemoryPayload, request: Request) -> dict[str, Any]:
    session = _get_session(payload.session_id)
    normalized = (session.normalize_result or {}).get("normalized") or []
    if not normalized:
        raise HTTPException(status_code=400, detail="Normalize result is empty")
    if not session.approved_clusters:
        raise HTTPException(status_code=400, detail="No clusters to map items to memory")
    cluster_by_item = _item_cluster_name_map(session.approved_clusters)
    items: list[MemoryItem] = []
    for row in normalized:
        item_name = str(row.get("item", "")).strip()
        if not item_name:
            continue
        cluster_name = cluster_by_item.get(item_name)
        if not cluster_name:
            raise HTTPException(
                status_code=400,
                detail=f"Item not found in approved clusters: {item_name}",
            )
        items.append(
            MemoryItem(
                text=item_name,
                attributes=dict(row.get("values", {})),
                cluster_name=cluster_name,
            )
        )
    if not items:
        raise HTTPException(status_code=400, detail="No valid normalized items")
    saved = await dispatch_memory_save(
        request,
        MemorySaveRequest(items=items),
        embedding_provider=session.embedding_provider,
    )
    return {"saved_count": saved.saved_count}


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


@router.post("/ui/api/admin/flush-redis")
async def flush_redis_cache(request: Request) -> dict[str, Any]:
    """Очищает Redis: статусы задач и кэш ответов LLM."""
    await request.app.state.redis.flushdb()
    request.app.state.llm_clients = {}
    return {
        "status": "ok",
        "message": "Redis очищен (задачи и кэш LLM)",
    }


@router.post("/ui/api/admin/flush-qdrant")
async def flush_qdrant_memory(request: Request) -> dict[str, Any]:
    """Удаляет коллекцию векторной памяти в Qdrant."""
    vector_db = request.app.state.vector_db
    points_before = vector_db.get_points_count()
    collection_name = vector_db.collection_name
    removed = vector_db.clear_collection()
    if removed:
        message = f"Коллекция «{collection_name}» удалена ({points_before} точек)"
    else:
        message = f"Коллекция «{collection_name}» не найдена — уже пусто"
    return {
        "status": "ok",
        "message": message,
        "collection": collection_name,
        "points_before": points_before,
        "removed": removed,
    }
