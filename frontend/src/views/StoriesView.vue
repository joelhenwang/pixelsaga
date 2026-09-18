<!-- Stories catalog, read surface (A07): list, search, status filter,
  read-only original-setup modal. Lifecycle mutations land in A09. -->
<script setup lang="ts">
import { onMounted, ref, watch } from "vue";
import { useRoute, useRouter } from "vue-router";
import type { StorySetupView, StorySummary } from "@gen";
import { api } from "../api";
import { fail, headers, notice } from "../store";
import ModalDialog from "../components/ModalDialog.vue";

const route = useRoute();
const router = useRouter();
const loading = ref(true);
const items = ref<StorySummary[]>([]);
const nextCursor = ref<string | null>(null);
const status = ref((route.query.status as string) || "in_progress");
const query = ref((route.query.q as string) || "");
const setup = ref<StorySetupView | null>(null);
const setupTitle = ref("");
let openedInApp = false;

async function load(reset: boolean): Promise<void> {
  loading.value = true;
  try {
    const page = await api.listStories(
      headers.value,
      {
        status: status.value,
        q: query.value || undefined,
        cursor: reset ? undefined : nextCursor.value ?? undefined,
      },
    );
    const fresh = page.items ?? [];
    items.value = reset ? fresh : [...items.value, ...fresh];
    nextCursor.value = page.next_cursor ?? null;
  } catch (error) {
    fail("stories unavailable", error);
  } finally {
    loading.value = false;
  }
}

async function openSetup(story: StorySummary): Promise<void> {
  try {
    setupTitle.value = story.title;
    setup.value = await api.readSetup(story.story_id, headers.value);
    openedInApp = true;
    void router.push({ path: "/stories", query: { ...route.query, setup: story.story_id } });
  } catch (error) {
    fail("setup unavailable", error);
  }
}

function closeSetup(): void {
  setup.value = null;
  const rest = { ...route.query };
  delete rest.setup;
  if (openedInApp) {
    openedInApp = false;
    router.back();
  } else {
    void router.replace({ path: "/stories", query: rest });
  }
}

watch(
  () => route.query.setup,
  (next) => {
    if (typeof next === "string" && next && !setup.value) {
      const found = items.value.find((s) => s.story_id === next);
      if (found) void openSetup(found);
      else {
        setupTitle.value = "";
        api.readSetup(next, headers.value).then(
          (view) => {
            setupTitle.value = view.story_id;
            setup.value = view;
          },
          (error: unknown) => fail("setup unavailable", error),
        );
      }
    } else if (!next) {
      setup.value = null;
    }
  },
);

onMounted(() => {
  void load(true).then(() => {
    const direct = route.query.setup;
    if (typeof direct === "string" && direct) {
      const found = items.value.find((s) => s.story_id === direct);
      if (found) void openSetup(found);
    }
  });
});
</script>
<template>
  <main class="page">
    <h1>Your stories</h1>
    <div class="toolbar">
      <label>status
        <select v-model="status" @change="load(true)">
          <option value="in_progress">In Progress</option>
          <option value="completed">Completed</option>
          <option value="archived">Archived</option>
          <option value="all">All</option>
        </select>
      </label>
      <label>search
        <input type="search" v-model="query" @change="load(true)" placeholder="Title" />
      </label>
    </div>
    <div v-if="loading && !items.length">Loading stories.</div>
    <div v-else-if="!items.length" class="panel">
      <p>No stories here yet.</p>
    </div>
    <div v-else class="cards">
      <article v-for="s in items" :key="s.story_id" class="card">
        <b>{{ s.title }}</b>
        <p>{{ s.world_name }} &middot; {{ s.mode }} &middot; Day {{ s.day }}</p>
        <div class="row">
          <button type="button" @click="router.push(`/stories/${s.story_id}/play`)">
            {{ s.status === "active" && !s.archived ? "Continue" : "View story" }}
          </button>
          <button
            type="button" class="icon" :aria-label="`View original setup for ${s.title}`"
            @click="openSetup(s)"
          >i</button>
        </div>
      </article>
    </div>
    <button v-if="nextCursor" type="button" @click="load(false)">More stories</button>
    <ModalDialog v-if="setup" label="Original story setup" @close="closeSetup">
      <p class="kicker">STORY INFORMATION &middot; SAVED AT CREATION</p>
      <h2>{{ setupTitle }}</h2>
      <p v-if="setup.provenance === 'legacy_unknown'" class="legacy">
        Original setup unavailable: this story predates setup snapshots.
      </p>
      <dl v-else-if="setup.payload" class="setup">
        <dt>Mode</dt><dd>{{ (setup.payload.mode as Record<string, string>)?.role ?? "" }}</dd>
        <dt>Tone</dt><dd>{{ (setup.payload.story as Record<string, string>)?.tone ?? "" }}</dd>
        <dt>Created</dt><dd>{{ setup.created_at }}</dd>
      </dl>
      <button type="button" @click="closeSetup">Close</button>
    </ModalDialog>
  </main>
</template>
