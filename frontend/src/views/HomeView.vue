<!-- Home (A07): continue hero, new-tale card, library card. Reads the
  catalog summary; valid with zero worlds and never seeds, advances,
  or calls a model on open. -->
<script setup lang="ts">
import { computed, onMounted, ref } from "vue";
import { useRouter } from "vue-router";
import type { PresetSummary, StorySummary } from "@gen";
import { ApiError, api } from "../api";
import { fail, headers, notice } from "../store";

const router = useRouter();
const loading = ref(true);
const stories = ref<StorySummary[]>([]);
const worlds = ref<PresetSummary[]>([]);
const characters = ref<PresetSummary[]>([]);
const failed = ref(false);

function pickContinue(list: StorySummary[]): StorySummary | null {
  const open = list.filter((s) => !s.archived && s.status === "active");
  if (!open.length) return null;
  open.sort((a, b) => (b.last_played_at ?? "").localeCompare(a.last_played_at ?? ""));
  return open[0];
}

async function load(signal: AbortSignal): Promise<void> {
  loading.value = true;
  failed.value = false;
  try {
    const [catalog, lib] = await Promise.all([
      api.listStories(headers.value, { status: "all", limit: 20 }, { signal }),
      api.listPresets(headers.value).catch(() => [] as PresetSummary[]),
    ]);
    stories.value = catalog.items ?? [];
    worlds.value = lib.filter((p) => p.kind === "world").slice(0, 2);
    characters.value = lib.filter((p) => p.kind === "character").slice(0, 3);
  } catch (error) {
    if (error instanceof DOMException && error.name === "AbortError") return;
    if (error instanceof ApiError && error.status === 401) {
      failed.value = true;
      return;
    }
    fail("home unavailable", error);
    failed.value = true;
  } finally {
    loading.value = false;
  }
}

let controller: AbortController | null = null;

onMounted(() => {
  controller = new AbortController();
  void load(controller.signal);
  return () => controller?.abort();
});

const continuing = computed(() => pickContinue(stories.value));

function openStory(id: string): void {
  void router.push(`/stories/${id}/play`);
}
</script>
<template>
  <main class="page">
    <div v-if="loading">Loading stories.</div>
    <div v-else-if="failed" class="notice">Stories are unavailable. {{ notice }}</div>
    <div v-else-if="!stories.length" class="panel">
      <h1>Begin your first tale</h1>
      <p>No stories yet. New Story and Settings are ready; nothing was seeded for you.</p>
      <button type="button" @click="router.push('/new-story')">Start a new story</button>
    </div>
    <div v-else class="home-grid">
      <section class="hero" aria-label="Continue story" v-if="continuing">
        <h1>{{ continuing.title }}</h1>
        <p>{{ continuing.world_name }} &middot; Day {{ continuing.day }}, {{ continuing.phase }}</p>
        <button type="button" @click="openStory(continuing.story_id)">Continue Story &rsaquo;</button>
      </section>
      <div class="side">
        <section class="panel" aria-label="Begin a new tale">
          <h2>Begin a new tale</h2>
          <button type="button" @click="router.push('/new-story')">New Story &rsaquo;</button>
        </section>
        <section class="panel" aria-label="Your library">
          <div class="openrow">
            <h2>Your Library</h2>
            <button type="button" class="link" @click="router.push('/library')">Open Library &rsaquo;</button>
          </div>
          <h3>Worlds</h3>
          <ul class="minis">
            <li v-for="w in worlds" :key="w.id">{{ w.name }}</li>
          </ul>
          <h3>Characters</h3>
          <ul class="minis">
            <li v-for="c in characters" :key="c.id">{{ c.name }}</li>
          </ul>
        </section>
      </div>
    </div>
  </main>
</template>
