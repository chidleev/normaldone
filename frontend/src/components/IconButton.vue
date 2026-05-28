<script setup>
defineProps({
  title: { type: String, default: "" },
  danger: { type: Boolean, default: false },
  disabled: { type: Boolean, default: false },
});
</script>

<template>
  <button
    type="button"
    class="ghost icon-btn"
    :class="{ 'icon-btn--danger': danger }"
    :title="title"
    :aria-label="title || undefined"
    :disabled="disabled"
  >
    <slot />
  </button>
</template>
