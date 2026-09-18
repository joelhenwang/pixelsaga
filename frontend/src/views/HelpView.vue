<!-- Help and onboarding (A07): capabilities, terminology, honest
  limits. Skippable and replayable; not a main destination. -->
<script setup lang="ts">
import { ref } from "vue";

const open = ref(!localStorage.getItem("pixelsaga.help-seen"));

function dismiss(): void {
  try {
    localStorage.setItem("pixelsaga.help-seen", "1");
  } catch {
    /* ignore */
  }
  open.value = false;
}
</script>
<template>
  <main class="page narrow">
    <h1>Help</h1>
    <div v-if="open" class="panel">
      <h2>Welcome to PixelSaga</h2>
      <p>Choose a cast first, then how to play. A Player directs one cast member.</p>
      <button type="button" @click="dismiss">Skip tour</button>
    </div>
    <h2>Roles</h2>
    <p>Watcher observes. Director guides events through proposals. Deity may force
    outcomes. Player files attempts for one bound character only.</p>
    <h2>Next phase, not next beat</h2>
    <p>Simulation advances one phase at a time. Beats are narration, not the clock.</p>
    <h2>Art</h2>
    <p>Curated starter art ships with Ember Vale. Live generation is unavailable
    until an image adapter is configured; nothing here generates on mount.</p>
    <h2>Original setup</h2>
    <p>Every story keeps its immutable creation snapshot. Later Library or
    Settings changes never rewrite it; legacy stories say so honestly.</p>
  </main>
</template>
