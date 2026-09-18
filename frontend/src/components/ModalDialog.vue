<!-- Shared accessible modal dialog (A07). Focus trap, Esc, inert
  background, focus restore. For directly loaded modal URLs, closing
  falls back to the base route supplied by the caller. -->
<script setup lang="ts">
import { onMounted, onUnmounted, useTemplateRef } from "vue";

const props = defineProps<{ label: string }>();
const emit = defineEmits<{ close: [] }>();
const dialog = useTemplateRef<HTMLElement>("dialog");
let opener: Element | null = null;

function onKey(event: KeyboardEvent): void {
  if (event.key === "Escape") {
    emit("close");
    return;
  }
  if (event.key !== "Tab" || !dialog.value) return;
  const items = [...dialog.value.querySelectorAll<HTMLElement>("button, a[href], input, select, textarea")]
    .filter((element) => element.offsetParent !== null);
  if (!items.length) return;
  const first = items[0];
  const last = items[items.length - 1];
  if (event.shiftKey && document.activeElement === first) {
    event.preventDefault();
    last.focus();
  } else if (!event.shiftKey && document.activeElement === last) {
    event.preventDefault();
    first.focus();
  }
}

onMounted(() => {
  opener = document.activeElement;
  document.addEventListener("keydown", onKey);
  dialog.value?.querySelector<HTMLElement>("button")?.focus();
});

onUnmounted(() => {
  document.removeEventListener("keydown", onKey);
  if (opener instanceof HTMLElement) opener.focus();
});
</script>
<template>
  <div class="backdrop" @click.self="emit('close')">
    <div ref="dialog" class="modal" role="dialog" aria-modal="true" :aria-label="props.label">
      <slot />
    </div>
  </div>
</template>
