<!-- Application shell (A07): main menu, profile, help, non-simulation
  pages. No world bootstrap here; story entry binds its own context. -->
<script setup lang="ts">
import { ref } from "vue";
import { useRoute } from "vue-router";
import { apiKey, errorKind, notice, setApiKey, setTheme, theme } from "../store";

const route = useRoute();
const drawer = ref(false);

function onKey(event: Event): void {
  setApiKey((event.target as HTMLInputElement).value.trim());
}

function onTheme(event: Event): void {
  setTheme((event.target as HTMLSelectElement).value as typeof theme.value);
}
</script>
<template>
  <div class="shell">
    <header class="topbar">
      <RouterLink to="/" class="brand">PixelSaga</RouterLink>
      <nav aria-label="Main">
        <RouterLink to="/">Home</RouterLink>
        <RouterLink to="/new-story">New Story</RouterLink>
        <RouterLink to="/stories">Stories</RouterLink>
        <RouterLink to="/library">Library</RouterLink>
        <RouterLink to="/settings">Settings</RouterLink>
      </nav>
      <span class="side">
        <RouterLink to="/help">Help</RouterLink>
        <RouterLink to="/profile" class="avatar" title="Local profile">J</RouterLink>
        <button class="ghost" type="button" @click="drawer = !drawer" aria-label="Access">
          access
        </button>
      </span>
    </header>
    <section class="settings" v-if="drawer" aria-label="Access">
      <label>key
        <input
          type="password" :value="apiKey" placeholder="bearer key, optional" autocomplete="off"
          @change="onKey" />
      </label>
      <label>theme
        <select :value="theme" @change="onTheme">
          <option value="light">light</option>
          <option value="dark">dark</option>
        </select>
      </label>
      <span class="notice" v-if="notice">{{ notice }}</span>
      <span v-if="errorKind" class="notice">state: {{ errorKind }}</span>
    </section>
    <RouterView />
  </div>
</template>
