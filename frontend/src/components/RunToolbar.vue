<script setup>
import {
  Database,
  Download,
  Eraser,
  Layers,
  RotateCcw,
  Save,
  Sparkles,
} from "@lucide/vue";
import IconButton from "./IconButton.vue";

const props = defineProps({
  backendUrl: { type: String, required: true },
  embeddingProvider: { type: String, required: true },
  profileProvider: { type: String, required: true },
  normalizeProvider: { type: String, required: true },
});

const emit = defineEmits([
  "update:backendUrl",
  "update:embeddingProvider",
  "update:profileProvider",
  "update:normalizeProvider",
  "reset-session",
  "clusterize",
  "normalize",
  "save-memory",
  "export-xlsx",
  "flush-redis",
  "flush-qdrant",
]);
</script>

<template>
  <section class="toolbar">
    <div class="toolbar-row">
      <label class="field">
        <span>Backend URL</span>
        <input
          type="text"
          :value="backendUrl"
          placeholder=""
          @input="emit('update:backendUrl', $event.target.value)"
        />
      </label>
      <label class="field">
        <span>Векторизация</span>
        <select
          :value="embeddingProvider"
          @change="emit('update:embeddingProvider', $event.target.value)"
        >
          <option value="local">local</option>
          <option value="gemini">gemini</option>
        </select>
      </label>
      <label class="field">
        <span>Профиль кластера</span>
        <select
          :value="profileProvider"
          @change="emit('update:profileProvider', $event.target.value)"
        >
          <option value="g4f">g4f</option>
          <option value="gemini">gemini</option>
        </select>
      </label>
      <label class="field">
        <span>Нормализация</span>
        <select
          :value="normalizeProvider"
          @change="emit('update:normalizeProvider', $event.target.value)"
        >
          <option value="g4f">g4f</option>
          <option value="gemini">gemini</option>
        </select>
      </label>
    </div>
    <div class="toolbar-actions">
      <button class="btn-with-icon" type="button" @click="emit('clusterize')">
        <Layers aria-hidden="true" />
        Кластеризовать
      </button>
      <button class="btn-with-icon" type="button" @click="emit('normalize')">
        <Sparkles aria-hidden="true" />
        Нормализовать
      </button>
      <IconButton title="Сохранить в память" @click="emit('save-memory')">
        <Save aria-hidden="true" />
      </IconButton>
      <IconButton title="Экспорт XLSX" @click="emit('export-xlsx')">
        <Download aria-hidden="true" />
      </IconButton>
      <div class="spacer" />
      <IconButton title="Сбросить сессию" danger @click="emit('reset-session')">
        <RotateCcw aria-hidden="true" />
      </IconButton>
    </div>
    <div class="toolbar-maintenance">
      <span class="toolbar-maintenance__label">Контейнеры</span>
      <IconButton
        title="Очистить кэш Redis (задачи и ответы LLM)"
        danger
        @click="emit('flush-redis')"
      >
        <Eraser aria-hidden="true" />
      </IconButton>
      <IconButton
        title="Очистить векторную память Qdrant"
        danger
        @click="emit('flush-qdrant')"
      >
        <Database aria-hidden="true" />
      </IconButton>
    </div>
  </section>
</template>
