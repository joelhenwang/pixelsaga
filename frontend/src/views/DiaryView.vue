<script setup lang="ts">
import { onMounted, ref, watch } from "vue";
import type { DiaryEntry } from "@gen";
import { api } from "../api";
import { characterId, characters, fail, headers } from "../store";

const entries = ref<{ kind: string; items: DiaryEntry[] }[]>([]);

async function load(): Promise<void> {
  if (!characterId.value) {
    return;
  }
  try {
    const diary = await api.diary(characterId.value, headers.value);
    entries.value = [
      { kind: "observation", items: diary.observations ?? [] },
      { kind: "memory", items: diary.memories ?? [] },
      { kind: "summary", items: diary.summaries ?? [] },
      { kind: "digest", items: diary.digests ?? [] },
    ];
  } catch (error) {
    fail("diary load failed", error);
  }
}

onMounted(() => {
  void load();
});
watch(characterId, () => {
  void load();
});
</script>

<template>
  <main class="stage" aria-live="polite">
    <h1>diary</h1>
    <label class="dim">whose
      <select v-model="characterId" @change="load">
        <option v-for="c in characters" :key="c.id" :value="c.id">{{ c.name }}</option>
      </select>
    </label>
    <template v-for="group in entries" :key="group.kind">
      <h2>{{ group.kind }}s</h2>
      <p v-for="(e, i) in group.items" :key="i" class="fact">
        <span class="dim">phase {{ e.phase }} ·</span> {{ e.text }}
      </p>
      <p v-if="group.items.length === 0" class="dim">none yet</p>
    </template>
  </main>
</template>
