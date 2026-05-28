import { ref } from "vue";
import { extractDetail, translateDetail } from "../utils/formatApiError";

export class ApiError extends Error {
  constructor(message, { status, detail, raw } = {}) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.detail = detail;
    this.raw = raw;
  }
}

/** Нормализует Backend URL из тулбара. */
export function resolveBackendBaseUrl(rawUrl) {
  const trimmed = String(rawUrl ?? "").trim().replace(/\/+$/, "");
  if (!trimmed) return "";
  if (/:5173(\/|$)/.test(trimmed)) {
    return "http://localhost:8000";
  }
  return trimmed;
}

/**
 * @param {() => string} getBackendUrl — Backend URL из тулбара (приоритет над env).
 */
export function useApi(getBackendUrl = () => "") {
  const isBusy = ref(false);

  function apiUrl(path) {
    const normalizedPath = path.startsWith("/") ? path : `/${path}`;
    const fromField = resolveBackendBaseUrl(
      typeof getBackendUrl === "function" ? getBackendUrl() : "",
    );
    const fromEnv = resolveBackendBaseUrl(import.meta.env.VITE_API_BASE_URL || "");
    const base = fromField || fromEnv;
    return base ? `${base}${normalizedPath}` : normalizedPath;
  }

  async function request(method, path, payload, isForm = false) {
    const options = { method };
    if (payload !== undefined) {
      if (isForm) {
        options.body = payload;
      } else {
        options.headers = { "Content-Type": "application/json" };
        options.body = JSON.stringify(payload);
      }
    }
    const res = await fetch(apiUrl(path), options);
    const text = await res.text();
    let data;
    try {
      data = text ? JSON.parse(text) : {};
    } catch {
      data = text;
    }
    if (!res.ok) {
      const detail = extractDetail(data);
      const message = translateDetail(detail) || detail || res.statusText || "Ошибка запроса";
      throw new ApiError(message, { status: res.status, detail, raw: data });
    }
    return data;
  }

  return { isBusy, apiUrl, request, resolveBackendBaseUrl };
}
