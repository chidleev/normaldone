<script setup>
import { AlertTriangle } from "@lucide/vue";

defineProps({
  open: { type: Boolean, default: false },
  title: { type: String, default: "Подтверждение" },
  message: { type: String, default: "" },
  confirmText: { type: String, default: "Подтвердить" },
  cancelText: { type: String, default: "Отмена" },
  secondaryText: { type: String, default: "" },
  danger: { type: Boolean, default: false },
});

const emit = defineEmits(["confirm", "cancel", "secondary"]);
</script>

<template>
  <Teleport to="body">
    <div v-if="open" class="confirm-backdrop" @click.self="emit('cancel')">
      <div class="confirm-dialog" role="dialog" aria-modal="true">
        <div class="confirm-dialog__title">
          <AlertTriangle class="confirm-dialog__icon" aria-hidden="true" />
          {{ title }}
        </div>
        <p class="confirm-dialog__message">{{ message }}</p>
        <div class="confirm-dialog__actions">
          <button type="button" class="btn-with-icon btn-with-icon--secondary" @click="emit('cancel')">
            {{ cancelText }}
          </button>
          <button
            v-if="secondaryText"
            type="button"
            class="btn-with-icon btn-with-icon--secondary"
            @click="emit('secondary')"
          >
            {{ secondaryText }}
          </button>
          <button
            type="button"
            class="btn-with-icon"
            :class="{ danger }"
            @click="emit('confirm')"
          >
            {{ confirmText }}
          </button>
        </div>
      </div>
    </div>
  </Teleport>
</template>
