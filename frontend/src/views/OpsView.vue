<script setup lang="ts">
import { onMounted, ref, watch } from "vue";
import { api } from "../api";
import { fail, headers, worldId } from "../store";

const rows = ref<[string, string][]>([]);

async function load(): Promise<void> {
  if (!worldId.value) {
    return;
  }
  try {
    const status = await api.operations(worldId.value, headers.value);
    rows.value = [
      ["open run", status.open_run_id ? `${status.open_run_id.slice(0, 8)} · ${status.open_run_state}` : "none"],
      ["pending outbox", String(status.pending_outbox)],
      ["total events", String(status.total_events)],
    ];
    const hooks = await api.hooks(worldId.value, headers.value).catch(() => null);
    if (hooks) {
      rows.value.push([
        "director",
        [...(hooks.hooks ?? []).map((h) => h.title), ...(hooks.arcs ?? []).map((a) => a.title)].join("; ") || "no open hooks or arcs",
      ]);
    }
  } catch (error) {
    fail("operations load failed", error);
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
    <h1>operations</h1>
    <table>
      <tr v-for="[k, v] in rows" :key="k">
        <td class="dim">{{ k }}</td>
        <td>{{ v }}</td>
      </tr>
    </table>
  </main>
</template>
