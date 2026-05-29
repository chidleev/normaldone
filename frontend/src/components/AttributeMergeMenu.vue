<script setup>
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from "vue";
import IconButton from "./IconButton.vue";
import { normalizeMergeSeparator } from "../utils/attributeMergeUtils";
import { computeFloatingMenuPosition } from "../utils/floatingMenuPosition";

const props = defineProps({
  attribute: { type: String, required: true },
  behavior: { type: String, default: "priority" },
  separator: { type: String, default: "" },
});

const emit = defineEmits(["update-config"]);

const open = ref(false);
const anchorRef = ref(null);
const menuRef = ref(null);
const menuStyle = ref({ top: "0px", left: "0px" });
const localBehavior = ref(props.behavior);
const localSeparator = ref(props.separator || "");

const isAccumulative = computed(() => localBehavior.value === "accumulative");

const label = computed(() => (isAccumulative.value ? "А" : "П"));

const title = computed(() =>
  isAccumulative.value
    ? "Аккумулятивное слияние: части объединяются с автоопределением разделителя (, ; |)"
    : "Приоритетное слияние: первое непустое значение",
);

watch(
  () => [props.behavior, props.separator],
  ([behavior, separator]) => {
    if (!open.value) {
      localBehavior.value = behavior;
      localSeparator.value = separator || "";
    }
  },
);

async function toggle() {
  if (open.value) {
    open.value = false;
    return;
  }
  localBehavior.value = props.behavior;
  localSeparator.value = props.separator || "";
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

function setBehavior(next) {
  localBehavior.value = next;
  if (next !== "accumulative") {
    localSeparator.value = "";
    apply();
  }
}

function apply() {
  const behavior = localBehavior.value === "accumulative" ? "accumulative" : "priority";
  const separator =
    behavior === "accumulative" ? normalizeMergeSeparator(localSeparator.value) : null;
  emit("update-config", {
    attribute: props.attribute,
    behavior,
    separator,
  });
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
  <div ref="anchorRef" class="attr-merge-menu-anchor">
    <IconButton class="attr-merge-btn" :title="`${label}: ${title}`" @click.stop="toggle">
      <span class="attr-merge-btn__label">{{ label }}</span>
    </IconButton>
    <Teleport to="body">
      <div
        v-if="open"
        ref="menuRef"
        class="attr-merge-menu"
        :style="menuStyle"
        @click.stop
      >
        <p class="attr-merge-menu__title">{{ attribute }}</p>
        <div class="attr-merge-menu__modes">
          <button
            type="button"
            class="attr-merge-menu__mode"
            :class="{ 'attr-merge-menu__mode--active': !isAccumulative }"
            @click="setBehavior('priority')"
          >
            Приоритетное
          </button>
          <button
            type="button"
            class="attr-merge-menu__mode"
            :class="{ 'attr-merge-menu__mode--active': isAccumulative }"
            @click="setBehavior('accumulative')"
          >
            Аккумулятивное
          </button>
        </div>
        <label v-if="isAccumulative" class="attr-merge-menu__sep-field">
          <span>Разделитель</span>
          <input
            v-model="localSeparator"
            type="text"
            class="attr-merge-menu__sep-input"
            placeholder="авто (, ; |)"
            @keydown.enter.prevent="apply"
          />
          <span class="attr-merge-menu__hint">Пусто — по данным: «,» или «;» и т.д.</span>
        </label>
        <button type="button" class="attr-merge-menu__apply" @click="apply">Применить</button>
      </div>
    </Teleport>
  </div>
</template>
