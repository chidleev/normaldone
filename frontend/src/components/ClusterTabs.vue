<script setup>
defineProps({
  clusters: { type: Array, required: true },
  activeTab: { type: String, required: true },
});

defineEmits(["tab-change", "add-cluster", "delete-cluster"]);
</script>

<template>
  <div class="tabs">
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
      {{ cluster.name || `Кластер ${idx + 1}` }}
      <span
        class="tab-close"
        role="button"
        tabindex="0"
        title="Удалить кластер"
        @click.stop="$emit('delete-cluster', idx)"
        @keydown.enter.stop.prevent="$emit('delete-cluster', idx)"
      >
        ×
      </span>
    </button>
    <button
      class="tab tab--add"
      type="button"
      title="Добавить кластер"
      @click="$emit('add-cluster')"
    >
      + Кластер
    </button>
  </div>
</template>
