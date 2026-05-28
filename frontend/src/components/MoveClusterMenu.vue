<script setup>
import { nextTick, onBeforeUnmount, onMounted, ref } from "vue";
import { ArrowRightLeft } from "@lucide/vue";
import IconButton from "./IconButton.vue";

const props = defineProps({
  targets: { type: Array, default: () => [] },
});

const emit = defineEmits(["select"]);

const open = ref(false);
const anchorRef = ref(null);
const menuRef = ref(null);
const menuStyle = ref({ top: "0px", left: "0px" });

function updateMenuPosition() {
  const button = anchorRef.value?.querySelector("button");
  if (!button) return;
  const rect = button.getBoundingClientRect();
  menuStyle.value = {
    top: `${rect.bottom + 4}px`,
    left: `${rect.left}px`,
  };
}

async function toggle() {
  if (!props.targets.length) return;
  open.value = !open.value;
  if (open.value) {
    await nextTick();
    updateMenuPosition();
  }
}

function pick(targetClusterIdx) {
  emit("select", targetClusterIdx);
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

function onViewportChange() {
  if (open.value) updateMenuPosition();
}

onMounted(() => {
  document.addEventListener("pointerdown", onDocumentPointer, true);
  document.addEventListener("keydown", onKeydown);
  window.addEventListener("resize", onViewportChange);
  window.addEventListener("scroll", onViewportChange, true);
});

onBeforeUnmount(() => {
  document.removeEventListener("pointerdown", onDocumentPointer, true);
  document.removeEventListener("keydown", onKeydown);
  window.removeEventListener("resize", onViewportChange);
  window.removeEventListener("scroll", onViewportChange, true);
});
</script>

<template>
  <div ref="anchorRef" class="move-menu-anchor">
    <IconButton
      title="Переместить в кластер"
      :disabled="!targets.length"
      @click.stop="toggle"
    >
      <ArrowRightLeft aria-hidden="true" />
    </IconButton>
    <Teleport to="body">
      <Transition name="move-menu-fade">
        <div
          v-if="open"
          ref="menuRef"
          class="move-menu move-menu--floating"
          role="menu"
          aria-label="Выбор кластера"
          :style="menuStyle"
          @click.stop
        >
          <button
            v-for="target in targets"
            :key="target.index"
            type="button"
            class="move-menu__item"
            role="menuitem"
            @click="pick(target.index)"
          >
            {{ target.name }}
          </button>
        </div>
      </Transition>
    </Teleport>
  </div>
</template>
