<script setup>
defineProps({
  clusters: { type: Array, required: true },
  activeTab: { type: String, required: true },
});

defineEmits(["tab-change"]);
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
      type="button"
      :class="{ active: activeTab === `cluster-${idx}` }"
      @click="$emit('tab-change', `cluster-${idx}`)"
    >
      {{ cluster.name || `Кластер ${idx + 1}` }}
    </button>
  </div>
</template>
