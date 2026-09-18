<script setup lang="ts">
import { onMounted } from "vue";
import { useRoute } from "vue-router";
import {
  apiKey,
  characterId,
  characters,
  clock,
  connection,
  errorKind,
  notice,
  refresh,
  role,
  seedWorld,
  settingsOpen,
  setApiKey,
  setTheme,
  switchRole,
  theme,
} from "./store";

const route = useRoute();

const tabs = [
  { to: "/scene", label: "adventure" },
  { to: "/map", label: "world" },
  { to: "/party", label: "party" },
  { to: "/timeline", label: "journal" },
  { to: "/diary", label: "diary" },
  { to: "/relations", label: "relations" },
  { to: "/generations", label: "eras" },
  { to: "/operations", label: "ops" },
];

function onRoleChange(event: Event): void {
  const next = (event.target as HTMLSelectElement).value as typeof role.value;
  switchRole(next, null);
  void refresh();
}

function onCharacterChange(event: Event): void {
  switchRole("player", (event.target as HTMLSelectElement).value);
  void refresh();
}

async function seed(): Promise<void> {
  await seedWorld();
}

onMounted(() => {
  const saved = localStorage.getItem("worldsim.theme");
  if (saved === "dark" || saved === "light") {
    setTheme(saved);
  }
  window.addEventListener("online", () => {
    void refresh();
  });
  void refresh();
});
</script>
<template>
  <div class="shell">
    <header class="topbar">
      <span class="brand">Ember Vale</span>
      <nav aria-label="Views">
        <RouterLink
          v-for="t in tabs"
          :key="t.to"
          :to="t.to"
          :aria-current="route.path === t.to ? 'true' : 'false'"
        >{{ t.label }}</RouterLink>
      </nav>
      <span class="clock">{{ clock }}</span>
      <span class="conn" :data-state="connection">{{ connection }}</span>
      <button class="ghost" type="button" @click="settingsOpen = !settingsOpen" aria-label="Settings">
        settings
      </button>
    </header>
    <section class="settings" v-if="settingsOpen" aria-label="Settings">
      <label>role
        <select :value="role" @change="onRoleChange">
          <option value="watcher">watcher</option>
          <option value="player">player</option>
          <option value="director">director</option>
          <option value="deity">deity</option>
        </select>
      </label>
      <label v-if="role === 'player'">character
        <select :value="characterId" @change="onCharacterChange">
          <option v-for="c in characters" :key="c.id" :value="c.id">{{ c.name }}</option>
        </select>
      </label>
      <label>key
        <input
          type="password" :value="apiKey" placeholder="bearer key, optional" autocomplete="off"
          @change="setApiKey(($event.target as HTMLInputElement).value.trim()); refresh()" />
      </label>
      <label>theme
        <select :value="theme" @change="setTheme(($event.target as HTMLSelectElement).value as typeof theme)">
          <option value="light">light</option>
          <option value="dark">dark</option>
        </select>
      </label>
      <button type="button" @click="seed">seed</button>
      <button type="button" @click="refresh()">refresh</button>
      <RouterLink to="/operations">operations</RouterLink>
      <span class="notice" v-if="notice">{{ notice }}</span>
      <span v-if="errorKind" class="notice">state: {{ errorKind }}</span>
    </section>
    <RouterView />
  </div>
</template>
