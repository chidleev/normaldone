import { onBeforeUnmount, onMounted, ref, watch } from "vue";

/**
 * Локальный draft с сохранением по pointerdown вне поля (не по blur).
 */
export function useDraftField(modelValue, onCommit) {
  const draft = ref(String(modelValue.value ?? ""));
  const rootRef = ref(null);
  const focused = ref(false);

  watch(
    modelValue,
    (value) => {
      if (!focused.value) {
        draft.value = String(value ?? "");
      }
    },
    { immediate: true },
  );

  function onInput(event) {
    draft.value = event.target.value;
  }

  function onFocus() {
    focused.value = true;
    draft.value = String(modelValue.value ?? "");
  }

  function commit() {
    if (!focused.value) return;
    focused.value = false;
    const next = String(draft.value ?? "").trim();
    onCommit(next, draft.value);
  }

  function onDocumentPointer(event) {
    if (!focused.value) return;
    const target = event.target;
    if (rootRef.value?.contains(target)) return;
    commit();
  }

  onMounted(() => {
    document.addEventListener("pointerdown", onDocumentPointer, true);
  });

  onBeforeUnmount(() => {
    document.removeEventListener("pointerdown", onDocumentPointer, true);
  });

  return {
    draft,
    rootRef,
    onInput,
    onFocus,
    commit,
  };
}
