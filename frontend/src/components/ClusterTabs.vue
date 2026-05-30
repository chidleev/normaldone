<script setup>
import { Database, Pencil, Sparkles } from "@lucide/vue";
import MoveClusterMenu from "./MoveClusterMenu.vue";

defineProps({
  clusters: { type: Array, required: true },
  activeTab: { type: String, required: true },
  memoryClusters: { type: Array, default: () => [] },
});

defineEmits([
  "tab-change",
  "add-cluster",
  "select-memory-cluster",
  "delete-cluster",
]);

function clusterSource(cluster) {
  const source = String(cluster?.source || "").trim().toLowerCase();
  if (source === "memory") return "memory";
  if (source === "manual" || source === "mixed") return "manual";
  return "ai";
}

function clusterSourceTitle(cluster) {
  const source = clusterSource(cluster);
  if (source === "memory") return "Кластер загружен из памяти";
  if (source === "manual") return "Кластер создан вручную";
  return "Кластер предложен нейронкой";
}
</script>

<template>
  <div class="tabs">
    <button
      class="tab"
      :class="{ active: activeTab === 'search' }"
      type="button"
      @click="$emit('tab-change', 'search')"
    >
      Поиск
    </button>
    <button
      class="tab"
      :class="{ active: activeTab === 'source' }"
      type="button"
      @click="$emit('tab-change', 'source')"
    >
      Исходные данные
    </button>
    <button
      v-for="(cluster, idx) in clusters"
      :key="idx"
      class="tab"
      :class="{ active: activeTab === `cluster-${idx}` }"
      type="button"
      @click="$emit('tab-change', `cluster-${idx}`)"
    >
      <Database
        v-if="clusterSource(cluster) === 'memory'"
        class="tab-source-icon"
        :title="clusterSourceTitle(cluster)"
        aria-hidden="true"
      />
      <Pencil
        v-else-if="clusterSource(cluster) === 'manual'"
        class="tab-source-icon"
        :title="clusterSourceTitle(cluster)"
        aria-hidden="true"
      />
      <Sparkles
        v-else
        class="tab-source-icon"
        :title="clusterSourceTitle(cluster)"
        aria-hidden="true"
      />
      {{ cluster.name || `Кластер ${idx + 1}` }}
      <span
        class="tab-close"
        role="button"
        tabindex="0"
        title="Закрыть кластер"
        @click.stop="$emit('delete-cluster', idx)"
        @keydown.enter.stop.prevent="$emit('delete-cluster', idx)"
      >
        ×
      </span>
    </button>
    <button class="tab tab--add" type="button" title="Добавить кластер" @click="$emit('add-cluster')">
      + Кластер
    </button>
    <MoveClusterMenu
      button-label="+ Из памяти"
      button-title="Загрузить кластер из памяти"
      button-class="tab tab--add"
      :targets="
        (memoryClusters || []).map((name, idx) => ({
          index: idx,
          name,
          value: name,
        }))
      "
      @select="(name) => $emit('select-memory-cluster', name)"
    />
  </div>
</template>
