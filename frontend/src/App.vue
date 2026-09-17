<script setup lang="ts">
import { onMounted } from "vue";
import { useRoute } from "vue-router";
import { characterId, characters, clock, connection, fail, notice, refresh, role } from "./store";
import { headers } from "./store";

const route = useRoute();

async function seed(): Promise<void> {
  notice.value = "";
  try {
    await fetch("/api/v1/world/seed", { method: "POST", headers: headers.value });
    await refresh();
  } catch (error) {
    fail("seed failed", error);
  }
}

function toggleTheme(event: Event): void {
  const light = document.documentElement.classList.toggle("light");
  const target = event.target as HTMLElement | null;
  if (target) {
    target.textContent = light ? "dark" : "light";
  }
}

const tabs = [
  { to: "/scene", label: "scene" },
  { to: "/party", label: "party" },
  { to: "/timeline", label: "timeline" },
  { to: "/map", label: "map" },
  { to: "/diary", label: "diary" },
  { to: "/relations", label: "relations" },
  { to: "/generations", label: "generations" },
];

onMounted(() => {
  void refresh();
});
</script>

<template>
  <div class="shell">
    <nav class="tabs" aria-label="Views">
      <RouterLink
        v-for="t in tabs"
        :key="t.to"
        :to="t.to"
        :aria-current="route.path === t.to ? 'true' : 'false'"
      >{{ t.label }}</RouterLink>
      <span class="status">{{ clock }}</span>
      <span class="conn" :data-state="connection">{{ connection }}</span>
    </nav>
    <div class="toolbar">
      <label>role
        <select v-model="role" @change="refresh">
          <option value="watcher">watcher</option>
          <option value="player">player</option>
        </select>
      </label>
      <label v-if="role === 'player'">character
        <select v-model="characterId" @change="refresh">
          <option v-for="c in characters" :key="c.id" :value="c.id">{{ c.name }}</option>
        </select>
      </label>
      <button type="button" @click="seed">seed</button>
      <button type="button" @click="refresh">refresh</button>
      <button id="theme" type="button" @click="toggleTheme">light</button>
      <span class="notice" v-if="notice">{{ notice }}</span>
    </div>
    <RouterView />
  </div>
</template>
