<script setup lang="ts">
import { onMounted, ref, watch } from "vue";
import type { MapPlace } from "@gen";
import { api } from "../api";
import { fail, headers, worldId } from "../store";

const places = ref<MapPlace[]>([]);

async function load(): Promise<void> {
  if (!worldId.value) {
    return;
  }
  try {
    const map = await api.map(worldId.value, headers.value);
    places.value = map.places ?? [];
  } catch (error) {
    fail("map load failed", error);
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
    <h1>map · the Vale</h1>
    <div v-for="p in places" :key="p.id" class="maprow">
      <span class="dot" :class="{ dimdot: !p.discovered }" aria-hidden="true"></span>
      <span>
        <b>{{ p.discovered ? p.name : "unknown ground" }}</b>
        <span class="dim"> {{ p.region }}</span>
        <span v-if="p.discovered && (p.routes ?? []).length > 0" class="dim">
          · to {{ (p.routes ?? []).map((r) => `${r.to_location_id.slice(0, 8)} (${r.duration_phases})`).join(", ") }}
        </span>
        <br>
        <span class="dim">{{ (p.occupants ?? []).join(", ") || "empty" }}</span>
      </span>
    </div>
    <p v-if="places.length === 0" class="dim">No ground yet. Seed a world.</p>
  </main>
</template>
