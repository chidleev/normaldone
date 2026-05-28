<script setup>
import { computed } from "vue";
import { AlertCircle, CheckCircle2, Info, Loader2 } from "@lucide/vue";

const props = defineProps({
  text: { type: String, default: "Готово" },
  tone: { type: String, default: "muted" },
  /** null — без полосы; -1 — неопределённый; 0–100 — процент */
  progress: { type: Number, default: null },
});

const showBar = computed(() => props.progress !== null && props.progress !== undefined);

const barStyle = computed(() => {
  if (props.progress < 0) return {};
  return { width: `${props.progress}%` };
});

const progressLabel = computed(() => {
  if (props.progress == null || props.progress < 0) return "";
  return `${props.progress}%`;
});
</script>

<template>
  <div class="status-line" :class="[tone, { 'has-progress': showBar }]" role="status">
    <div class="status-line__main">
      <Loader2 v-if="tone === 'progress'" class="status-line__icon status-line__icon--spin" aria-hidden="true" />
      <AlertCircle v-else-if="tone === 'err'" class="status-line__icon" aria-hidden="true" />
      <CheckCircle2 v-else-if="tone === 'ok'" class="status-line__icon" aria-hidden="true" />
      <Info v-else class="status-line__icon" aria-hidden="true" />
      <span class="status-line__text">{{ text || "Готово" }}</span>
      <span v-if="showBar && progress >= 0" class="status-line__percent">{{ progressLabel }}</span>
    </div>
    <div v-if="showBar" class="status-progress">
      <div class="status-progress__track" :class="{ 'is-indeterminate': progress < 0 }">
        <div class="status-progress__bar" :style="barStyle" />
      </div>
    </div>
  </div>
</template>
