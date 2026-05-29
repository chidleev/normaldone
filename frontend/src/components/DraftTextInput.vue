<script setup>
import { toRef } from "vue";
import { useDraftField } from "../composables/useDraftField";

const props = defineProps({
  modelValue: { type: String, default: "" },
  placeholder: { type: String, default: "" },
  inputClass: { type: String, default: "cell-edit" },
  allowEmpty: { type: Boolean, default: true },
});

const emit = defineEmits(["update:modelValue", "commit"]);

const modelRef = toRef(props, "modelValue");

const { draft, rootRef, onInput, onFocus, commit } = useDraftField(modelRef, (trimmed, raw) => {
  if (!props.allowEmpty && !trimmed) {
    draft.value = String(props.modelValue ?? "");
    return;
  }
  emit("update:modelValue", raw);
  emit("commit", trimmed);
});

function onEnter() {
  commit();
}

defineExpose({ commit });
</script>

<template>
  <div ref="rootRef" class="draft-text-input">
    <slot name="prefix" />
    <slot name="sizer" :text="draft" />
    <input
      :class="inputClass"
      type="text"
      :value="draft"
      :placeholder="placeholder"
      @input="onInput"
      @focus="onFocus"
      @keydown.enter.prevent="onEnter"
    />
  </div>
</template>
