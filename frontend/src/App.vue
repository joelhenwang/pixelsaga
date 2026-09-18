<!-- Root (A07): route layouts plus shared infrastructure. No world
  bootstrap, no gameplay tabs; story entry binds its own context. -->
<script setup lang="ts">
import { onMounted } from "vue";
import { refresh, setTheme, worldId } from "./store";

onMounted(() => {
  const saved = localStorage.getItem("worldsim.theme");
  if (saved === "dark" || saved === "light") {
    setTheme(saved);
  }
  window.addEventListener("online", () => {
    if (worldId.value) {
      void refresh();
    }
  });
});
</script>
<template>
  <RouterView />
</template>
