<script setup>
import { computed, nextTick, onBeforeUnmount, onMounted, ref } from "vue";
import { MoreHorizontal, RefreshCw, Scissors, Merge } from "@lucide/vue";
import IconButton from "./IconButton.vue";
import { computeFloatingMenuPosition } from "../utils/floatingMenuPosition";

const props = defineProps({
  aliases: { type: Array, default: () => [] },
  mergeTargets: { type: Array, default: () => [] },
  canRegenerate: { type: Boolean, default: true },
});

const emit = defineEmits(["regenerate", "split-alias", "merge-into"]);

const open = ref(false);
const submenu = ref("");
const anchorRef = ref(null);
const menuRef = ref(null);
const menuStyle = ref({ top: "0px", left: "0px" });

const aliasItems = computed(() =>
  (props.aliases || []).map((name) => String(name || "").trim()).filter(Boolean),
);

const mergeItems = computed(() =>
  (props.mergeTargets || []).filter(
    (target) => Number.isInteger(target.index) && String(target.label || "").trim(),
  ),
);

async function toggle() {
  if (open.value) {
    open.value = false;
    submenu.value = "";
    return;
  }
  submenu.value = "";
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

function openSubmenu(name) {
  submenu.value = submenu.value === name ? "" : name;
  nextTick(updateMenuPosition);
}

function pickSplit(alias) {
  emit("split-alias", alias);
  open.value = false;
  submenu.value = "";
}

function pickMerge(index) {
  emit("merge-into", index);
  open.value = false;
  submenu.value = "";
}

function pickRegenerate() {
  emit("regenerate");
  open.value = false;
  submenu.value = "";
}

function onDocumentPointer(event) {
  if (!open.value) return;
  const target = event.target;
  if (anchorRef.value?.contains(target) || menuRef.value?.contains(target)) return;
  open.value = false;
  submenu.value = "";
}

function onKeydown(event) {
  if (event.key === "Escape") {
    open.value = false;
    submenu.value = "";
  }
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
  <div ref="anchorRef" class="row-ops-menu-anchor">
    <IconButton title="Действия со строкой" @click.stop="toggle">
      <MoreHorizontal aria-hidden="true" />
    </IconButton>
    <Teleport to="body">
      <div
        v-if="open"
        ref="menuRef"
        class="row-ops-menu"
        :style="menuStyle"
        @click.stop
      >
        <button
          type="button"
          class="row-ops-menu__item"
          :disabled="!canRegenerate"
          @click="pickRegenerate"
        >
          <RefreshCw aria-hidden="true" />
          Пересоздать обогащённое имя
        </button>
        <button
          type="button"
          class="row-ops-menu__item"
          :disabled="aliasItems.length <= 1"
          @click="openSubmenu('split')"
        >
          <Scissors aria-hidden="true" />
          Вычленить…
        </button>
        <ul v-if="submenu === 'split'" class="row-ops-submenu">
          <li v-for="alias in aliasItems" :key="alias">
            <button type="button" @click="pickSplit(alias)">{{ alias }}</button>
          </li>
        </ul>
        <button
          type="button"
          class="row-ops-menu__item"
          :disabled="!mergeItems.length"
          @click="openSubmenu('merge')"
        >
          <Merge aria-hidden="true" />
          Влить в…
        </button>
        <ul v-if="submenu === 'merge'" class="row-ops-submenu">
          <li v-for="target in mergeItems" :key="target.index">
            <button type="button" @click="pickMerge(target.index)">
              {{ target.label }}
            </button>
          </li>
        </ul>
      </div>
    </Teleport>
  </div>
</template>
