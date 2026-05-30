<script setup>
import { computed, nextTick, onBeforeUnmount, onMounted, ref } from "vue";
import { ArrowRightLeft } from "@lucide/vue";
import IconButton from "./IconButton.vue";
import { computeFloatingMenuPosition } from "../utils/floatingMenuPosition";

const props = defineProps({
  targets: { type: Array, default: () => [] },
  buttonLabel: { type: String, default: "" },
  buttonTitle: { type: String, default: "Переместить в кластер" },
  buttonIcon: { type: [Object, Function], default: null },
  buttonClass: {
    type: String,
    default: "btn-with-icon btn-with-icon--secondary btn-with-icon--mini",
  },
});

const emit = defineEmits(["select"]);
const iconComponent = computed(() => props.buttonIcon || ArrowRightLeft);

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
  if (!props.targets.length) return;
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

function pick(targetClusterIdx) {
  emit("select", targetClusterIdx);
  open.value = false;
}

function onDocumentPointer(event) {
  if (!open.value) return;
  const target = event.target;
  if (anchorRef.value?.contains(target) || menuRef.value?.contains(target))
    return;
  open.value = false;
}

function onKeydown(event) {
  if (event.key === "Escape") open.value = false;
}

function onViewportChange() {
  if (!open.value) return;
  updateMenuPosition();
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
    <button
      v-if="buttonLabel"
      type="button"
      :class="buttonClass"
      :title="buttonTitle"
      :disabled="!targets.length"
      @click.stop="toggle"
    >
      <component
        :is="buttonIcon"
        v-if="buttonIcon"
        class="move-menu-trigger-icon"
        aria-hidden="true"
      />
      {{ buttonLabel }}
    </button>
    <IconButton
      v-else
      :title="buttonTitle"
      :disabled="!targets.length"
      @click.stop="toggle"
    >
      <component :is="iconComponent" class="move-menu-trigger-icon" aria-hidden="true" />
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
            @click="pick(target.value ?? target.index)"
          >
            {{ target.name }}
          </button>
        </div>
      </Transition>
    </Teleport>
  </div>
</template>
