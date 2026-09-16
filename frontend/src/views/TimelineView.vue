<script setup lang="ts">
import { onMounted, ref, watch } from "vue";
import type { TimelineEntry } from "@gen";
import { api } from "../api";
import { fail, headers, worldId } from "../store";

const entries = ref<TimelineEntry[]>([]);
const total = ref<number>(0);

async function load(): Promise<void> {
  if (!worldId.value) {
    return;
  }
  try {
    const timeline = await api.timeline(worldId.value, headers.value);
    entries.value = timeline.entries ?? [];
    total.value = timeline.total;
  } catch (error) {
    fail("timeline load failed", error);
  }
}

onMounted(() => {
  void load();
});
watch(worldId, () => {
  void load();
});
</script>

<template>
  <main class="stage" aria-live="polite">
    <h1>timeline · {{ total }} events</h1>
    <table v-if="entries.length > 0">
      <tr><th>seq</th><th>type</th><th>phase</th><th>what happened</th></tr>
      <tr v-for="e in entries" :key="e.event_id">
        <td class="dim">{{ e.sequence }}</td>
        <td>{{ e.event_type }}</td>
        <td class="dim">{{ e.absolute_index }}</td>
        <td>{{ e.snippet ?? "—" }}</td>
      </tr>
    </table>
    <p v-else class="dim">No events yet. Advance a phase.</p>
  </main>
</template>
