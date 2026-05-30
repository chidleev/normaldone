<script setup>
import {
  BookOpen,
  Database,
  Download,
  Eraser,
  FlaskConical,
  Layers,
  RotateCcw,
  Save,
  Search,
  Sparkles,
} from "@lucide/vue";
import IconButton from "./IconButton.vue";
import FormSelectMenu from "./FormSelectMenu.vue";

const props = defineProps({
  backendUrl: { type: String, required: true },
  embeddingProvider: { type: String, required: true },
  profileProvider: { type: String, required: true },
  normalizeProvider: { type: String, required: true },
  showNormalizeRecoveryActions: { type: Boolean, default: false },
  clusterCount: { type: Number, default: 0 },
});

const emit = defineEmits([
  "update:backendUrl",
  "update:embeddingProvider",
  "update:profileProvider",
  "update:normalizeProvider",
  "reset-session",
  "clusterize",
  "normalize",
  "normalize-resume",
  "normalize-restart",
  "save-memory",
  "export-xlsx",
  "export-csv",
  "flush-redis",
  "flush-qdrant",
  "load-test-cluster",
  "open-memory-search",
  "open-swagger",
]);
</script>

<template>
  <section class="toolbar">
    <div class="toolbar-row">
      <label class="field">
        <span>Backend URL</span>
        <div class="toolbar-backend-field">
          <IconButton
            title="Swagger (OpenAPI)"
            @click="emit('open-swagger')"
          >
            <BookOpen aria-hidden="true" />
          </IconButton>
          <input
            type="text"
            :value="backendUrl"
            placeholder=""
            @input="emit('update:backendUrl', $event.target.value)"
          />
        </div>
      </label>
      <FormSelectMenu
        label="Векторизация"
        :model-value="embeddingProvider"
        :options="[
          { value: 'local', label: 'local' },
          { value: 'gemini', label: 'gemini' },
        ]"
        @update:model-value="emit('update:embeddingProvider', $event)"
      />
      <FormSelectMenu
        label="Профиль кластера"
        :model-value="profileProvider"
        :options="[
          { value: 'g4f', label: 'g4f' },
          { value: 'gemini', label: 'gemini' },
        ]"
        @update:model-value="emit('update:profileProvider', $event)"
      />
      <FormSelectMenu
        label="Нормализация"
        :model-value="normalizeProvider"
        :options="[
          { value: 'g4f', label: 'g4f' },
          { value: 'gemini', label: 'gemini' },
        ]"
        @update:model-value="emit('update:normalizeProvider', $event)"
      />
    </div>
    <div class="toolbar-actions">
      <button class="btn-with-icon" type="button" @click="emit('clusterize')">
        <Layers aria-hidden="true" />
        Кластеризовать
      </button>
      <button
        v-if="!showNormalizeRecoveryActions"
        class="btn-with-icon"
        type="button"
        @click="emit('normalize')"
      >
        <Sparkles aria-hidden="true" />
        Нормализовать
      </button>
      <button
        v-if="showNormalizeRecoveryActions"
        class="btn-with-icon btn-with-icon--secondary"
        type="button"
        title="Продолжить нормализацию с необработанных позиций"
        @click="emit('normalize-resume')"
      >
        <Sparkles aria-hidden="true" />
        Продолжить
      </button>
      <button
        v-if="showNormalizeRecoveryActions"
        class="btn-with-icon btn-with-icon--secondary"
        type="button"
        title="Запустить нормализацию заново"
        @click="emit('normalize-restart')"
      >
        <RotateCcw aria-hidden="true" />
        Заново
      </button>
      <button
        class="btn-with-icon btn-with-icon--secondary"
        type="button"
        title="Загрузить демо-кластер с обогащёнными именами для проверки UI"
        @click="emit('load-test-cluster')"
      >
        <FlaskConical aria-hidden="true" />
        Тестовый кластер
      </button>
      <button
        v-if="clusterCount >= 2"
        class="btn-with-icon btn-with-icon--secondary"
        type="button"
        title="Сохранить все в Qdrant"
        @click="emit('save-memory')"
      >
        <Save aria-hidden="true" />
        Qdrant
      </button>
      <button
        v-if="clusterCount >= 2"
        class="btn-with-icon btn-with-icon--secondary"
        type="button"
        title="XLSX (один файл на все кластеры)"
        @click="emit('export-xlsx')"
      >
        <Download aria-hidden="true" />
        XLSX
      </button>
      <button
        v-if="clusterCount >= 2"
        class="btn-with-icon btn-with-icon--secondary"
        type="button"
        title="CSV в ZIP (один файл на кластер)"
        @click="emit('export-csv')"
      >
        <Download aria-hidden="true" />
        CSV
      </button>
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
