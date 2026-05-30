const DETAIL_TRANSLATIONS = {
  "Session not found": "Сессия не найдена. Перезагрузите страницу или сбросьте сессию.",
  "Selected column not found":
    "Колонка-источник не найдена. Укажите источник (звезда в заголовке) или перезагрузите файл.",
  "Upload file first": "Сначала загрузите файл с данными.",
  "Source nomenclature is required": "Укажите номенклатуру в колонке-источнике.",
  "Selected column has no values": "В колонке-источнике нет значений для обработки.",
  "Upload file and save config first": "Загрузите файл и настройте колонки перед запуском.",
  "Approve clusters first": "Сначала выполните кластеризацию и проверьте кластеры.",
  "Only CSV/XLSX supported": "Поддерживаются только файлы CSV и XLSX.",
  "No columns found in file": "В файле не найдены колонки.",
  "No rows left after cleanup": "После очистки не осталось строк.",
  "row_index out of range": "Некорректный номер строки.",
  "column_name is required": "Укажите название колонки.",
  "Column already exists": "Колонка с таким именем уже есть.",
  "old_name and new_name are required": "Укажите старое и новое имя колонки.",
  "Column not found": "Колонка не найдена.",
  "New column name already exists": "Новое имя колонки уже занято.",
  "Cannot delete the last column": "Нельзя удалить последнюю колонку.",
  "No valid clusters to save": "Нет кластеров для сохранения.",
  "Normalize result is empty": "Результат нормализации пуст.",
  "No valid normalized items": "Нет данных для сохранения после нормализации.",
  "No clusters to export": "Нет кластеров для экспорта.",
  "Cluster index out of range": "Выбран некорректный кластер для экспорта.",
  "cluster_name is required": "Укажите имя кластера памяти.",
  "Memory cluster not found": "Кластер не найден в векторной памяти.",
  "Memory cluster name is empty": "У кластера не задано имя в памяти.",
  "text is required": "Укажите текст записи для удаления из памяти.",
  "Memory item not found": "Запись не найдена в векторной памяти.",
  "task_type must be clusterize|normalize": "Некорректный тип задачи.",
  "Task not started": "Задача ещё не запущена.",
  "Backend did not return task_id": "Сервер не вернул идентификатор задачи.",
};

function formatValidationItem(item) {
  if (!item || typeof item !== "object") return String(item ?? "");
  const loc = Array.isArray(item.loc) ? item.loc.filter((p) => p !== "body").join(".") : "";
  const msg = item.msg || item.message || "";
  if (loc && msg) return `${loc}: ${msg}`;
  return msg || loc || "";
}

export function extractDetail(data) {
  if (data == null) return "";
  if (typeof data === "string") {
    const trimmed = data.trim();
    if (trimmed.startsWith("{")) {
      try {
        return extractDetail(JSON.parse(trimmed));
      } catch {
        return trimmed;
      }
    }
    return trimmed;
  }
  if (typeof data !== "object") return String(data);

  if (typeof data.detail === "string") return data.detail.trim();
  if (Array.isArray(data.detail)) {
    const parts = data.detail.map(formatValidationItem).filter(Boolean);
    return parts.join("; ") || "";
  }
  if (data.detail && typeof data.detail === "object") {
    return formatValidationItem(data.detail) || JSON.stringify(data.detail);
  }
  if (typeof data.message === "string") return data.message.trim();
  if (typeof data.error === "string") return data.error.trim();
  return "";
}

function humanizeRawError(text) {
  const value = String(text ?? "").trim();
  if (!value) return "";
  const lower = value.toLowerCase();
  if (lower.includes("<html") || lower.includes("<!doctype")) {
    if (lower.includes("504") || lower.includes("gateway time-out")) {
      return "Таймаут LLM-провайдера (504). Смените провайдер или повторите позже.";
    }
    if (lower.includes("502") || lower.includes("bad gateway")) {
      return "LLM-провайдер недоступен (502).";
    }
    return "Сетевая ошибка LLM-провайдера.";
  }
  return value;
}

export function translateDetail(message) {
  const text = humanizeRawError(message);
  if (!text) return "";
  if (DETAIL_TRANSLATIONS[text]) return DETAIL_TRANSLATIONS[text];
  if (text.startsWith("Backend unavailable:")) {
    return `Сервер недоступен: ${text.replace("Backend unavailable:", "").trim()}`;
  }
  return text;
}

export function formatApiError(error, contextLabel) {
  let message = "";

  if (error?.name === "ApiError" || error?.detail != null) {
    message = error.message || translateDetail(error.detail) || translateDetail(extractDetail(error.raw));
  } else if (error?.message) {
    const parsed = extractDetail(error.message);
    message = translateDetail(parsed) || parsed || error.message;
  } else {
    message = translateDetail(extractDetail(error)) || "Неизвестная ошибка";
  }

  message = String(message).trim();
  if (!message) message = "Неизвестная ошибка";

  if (contextLabel) {
    return `${contextLabel}: ${message}`;
  }
  return message;
}

export function formatTaskError(errorValue) {
  const detail = humanizeRawError(extractDetail(errorValue) || String(errorValue ?? ""));
  return translateDetail(detail) || detail || "Задача завершилась с ошибкой";
}
