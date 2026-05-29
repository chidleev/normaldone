<script setup>
import { nextTick, onBeforeUnmount, onMounted, ref } from "vue";
import { ChevronDown } from "@lucide/vue";
import IconButton from "./IconButton.vue";
import { computeFloatingMenuPosition } from "../utils/floatingMenuPosition";

const props = defineProps({
  aliases: { type: Array, default: () => [] },
});

const open = ref(false);
const anchorRef = ref(null);
const menuRef = ref(null);
const menuStyle = ref({ top: "0px", left: "0px" });

const items = () =>
  (props.aliases || []).map((name) => String(name || "").trim()).filter(Boolean);

async function toggle() {
  if (!items().length) return;
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

function updateMenuPosition() {
  const button = anchorRef.value?.querySelector("button");
  if (!button) return;
  menuStyle.value = computeFloatingMenuPosition(button, menuRef.value);
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
  <div ref="anchorRef" class="aliases-menu-anchor">
    <IconButton
      :title="
        items().length
          ? `Исходные номенклатуры (${items().length})`
          : 'Нет исходных номенклатур'
      "
      :disabled="!items().length"
      @click="toggle"
    >
      <ChevronDown aria-hidden="true" />
    </IconButton>
    <Teleport to="body">
      <div
        v-if="open"
        ref="menuRef"
        class="aliases-menu"
        :style="menuStyle"
        role="menu"
      >
        <p class="aliases-menu__title">Исходные номенклатуры</p>
        <ul class="aliases-menu__list">
          <li v-for="(name, idx) in items()" :key="`${idx}-${name}`">{{ name }}</li>
        </ul>
      </div>
    </Teleport>
  </div>
</template>
