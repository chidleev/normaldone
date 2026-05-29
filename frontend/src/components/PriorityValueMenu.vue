<script setup>
import { nextTick, onBeforeUnmount, onMounted, ref } from "vue";
import { ChevronDown } from "@lucide/vue";
import IconButton from "./IconButton.vue";
import { computeFloatingMenuPosition } from "../utils/floatingMenuPosition";

const props = defineProps({
  values: { type: Array, default: () => [] },
  currentValue: { type: String, default: "" },
});

const emit = defineEmits(["select"]);

const open = ref(false);
const anchorRef = ref(null);
const menuRef = ref(null);
const menuStyle = ref({ top: "0px", left: "0px" });

function updateMenuPosition() {
  const button = anchorRef.value?.querySelector("button");
  if (!button) return;
  menuStyle.value = computeFloatingMenuPosition(button, menuRef.value);
}

async function toggle() {
  if (!props.values.length) return;
  if (open.value) {
    open.value = false;
    return;
  }
  const button = anchorRef.value?.querySelector("button");
  if (button) {
    menuStyle.value = computeFloatingMenuPosition(button, null);
  }
  open.value = true;
  await nextTick();
  updateMenuPosition();
}

function pick(value) {
  emit("select", String(value ?? ""));
  open.value = false;
}

function onDocumentPointer(event) {
  if (!open.value) return;
  const target = event.target;
  if (anchorRef.value?.contains(target) || menuRef.value?.contains(target)) return;
  open.value = false;
}

function onKeydown(event) {
  if (event.key === "Escape") open.value = false;
}

onMounted(() => {
  document.addEventListener("pointerdown", onDocumentPointer, true);
  document.addEventListener("keydown", onKeydown);
  window.addEventListener("resize", updateMenuPosition);
  window.addEventListener("scroll", updateMenuPosition, true);
});

onBeforeUnmount(() => {
  document.removeEventListener("pointerdown", onDocumentPointer, true);
  document.removeEventListener("keydown", onKeydown);
  window.removeEventListener("resize", updateMenuPosition);
  window.removeEventListener("scroll", updateMenuPosition, true);
});
</script>

<template>
  <div ref="anchorRef" class="priority-menu-anchor">
    <IconButton
      title="Выбрать итоговое значение из конфликтующих"
      class="priority-menu-trigger"
      @click.stop="toggle"
    >
      <ChevronDown aria-hidden="true" />
    </IconButton>
    <Teleport to="body">
      <div
        v-if="open"
        ref="menuRef"
        class="priority-menu"
        :style="menuStyle"
        @click.stop
      >
        <button
          v-for="value in values"
          :key="value"
          type="button"
          class="priority-menu__item"
          :class="{ 'priority-menu__item--active': value === currentValue }"
          @click="pick(value)"
        >
          {{ value }}
        </button>
      </div>
    </Teleport>
  </div>
</template>
