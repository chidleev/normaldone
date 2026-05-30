<script setup>
import { computed, nextTick, onBeforeUnmount, onMounted, ref } from "vue";
import { ChevronDown } from "@lucide/vue";
import { computeFloatingMenuPosition } from "../utils/floatingMenuPosition";

const props = defineProps({
  label: { type: String, default: "" },
  modelValue: { type: String, default: "" },
  options: { type: Array, default: () => [] },
});

const emit = defineEmits(["update:modelValue"]);

const open = ref(false);
const anchorRef = ref(null);
const menuRef = ref(null);
const menuStyle = ref({ top: "0px", left: "0px" });

const currentLabel = computed(() => {
  const current = (props.options || []).find(
    (opt) => String(opt?.value ?? "") === String(props.modelValue ?? ""),
  );
  return String(current?.label || props.modelValue || "");
});

function updateMenuPosition() {
  const button = anchorRef.value?.querySelector("button");
  if (!button) return;
  menuStyle.value = computeFloatingMenuPosition(button, menuRef.value);
}

async function toggle() {
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

function selectOption(value) {
  emit("update:modelValue", String(value ?? ""));
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
  <div class="field field-select" ref="anchorRef">
    <span>{{ label }}</span>
    <button type="button" class="select-menu-trigger" @click="toggle">
      <span>{{ currentLabel }}</span>
      <ChevronDown aria-hidden="true" />
    </button>
    <Teleport to="body">
      <div
        v-if="open"
        ref="menuRef"
        class="select-menu-list"
        :style="menuStyle"
      >
        <button
          v-for="option in options"
          :key="String(option?.value ?? option)"
          type="button"
          class="select-menu-item"
          :class="{ 'select-menu-item--active': String(option?.value ?? '') === String(modelValue ?? '') }"
          @click="selectOption(option?.value)"
        >
          {{ option?.label ?? option?.value ?? "" }}
        </button>
      </div>
    </Teleport>
  </div>
</template>
