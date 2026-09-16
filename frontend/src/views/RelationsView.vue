<script setup lang="ts">
import { onMounted, ref, watch } from "vue";
import type { RelationshipView } from "@gen";
import { api } from "../api";
import { characterId, characters, fail, headers, worldId } from "../store";

const members = ref<RelationshipView[]>([]);

async function load(): Promise<void> {
  if (!worldId.value || !characterId.value) {
    return;
  }
  try {
    const list = await api.relationships(worldId.value, characterId.value, headers.value);
    members.value = list.members ?? [];
  } catch (error) {
    fail("relations load failed", error);
  }
}

onMounted(() => {
  void load();
});
watch([worldId, characterId], () => {
  void load();
});
</script>

<template>
  <main class="stage" aria-live="polite">
    <h1>relations</h1>
    <label class="dim">whose
      <select v-model="characterId" @change="load">
        <option v-for="c in characters" :key="c.id" :value="c.id">{{ c.name }}</option>
      </select>
    </label>
    <table v-if="members.length > 0">
      <tr><th>direction</th><th>standing</th><th>trust</th><th>affection</th><th>respect</th></tr>
      <tr v-for="m in members" :key="m.id">
        <td class="dim">{{ m.direction }}</td>
        <td>{{ m.summary }}</td>
        <td>{{ m.trust }}</td>
        <td>{{ m.affection }}</td>
        <td>{{ m.respect }}</td>
      </tr>
    </table>
    <p v-else class="dim">No recorded relations yet.</p>
  </main>
</template>
