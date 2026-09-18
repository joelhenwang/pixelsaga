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
const menuFor = ref<string | null>(null);
const renaming = ref<string | null>(null);
const renameText = ref("");
async function versionOf(storyId: string): Promise<number> {
  const detail = await api.readStory(storyId, headers.value);
  return detail.metadata_version ?? 0;
}

async function doRename(story: StorySummary): Promise<void> {
  try {
    await api.renameStory(story.story_id, renameText.value, await versionOf(story.story_id), headers.value);
    renaming.value = null;
    await load(true);
  } catch (error) {
    fail("rename failed", error);
  }
}

async function doArchive(story: StorySummary, archived: boolean): Promise<void> {
  const action = archived ? "Unarchive" : "Archive";
  if (!window.confirm(`${action} "${story.title}"?`)) return;
  try {
    if (archived) {
      await api.unarchiveStory(story.story_id, await versionOf(story.story_id), headers.value);
    } else {
      await api.archiveStory(story.story_id, await versionOf(story.story_id), headers.value);
    }
    menuFor.value = null;
    await load(true);
  } catch (error) {
    fail("archive failed", error);
  }
}

async function doExport(story: StorySummary): Promise<void> {
  try {
    const data = await api.exportSetup(story.story_id, headers.value);
    const blob = new Blob([JSON.stringify(data, null, 2)], { type: "application/json" });
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url;
    link.download = `story-setup-${story.story_id.slice(0, 8)}.json`;
    link.click();
    URL.revokeObjectURL(url);
    menuFor.value = null;
  } catch (error) {
    fail("export failed", error);
  }
}

async function doReuse(story: StorySummary): Promise<void> {
  try {
    const view = await api.readSetup(story.story_id, headers.value);
    const payload = (view.payload ?? {}) as Record<string, unknown>;
    const cast = (payload.cast ?? []) as unknown as Record<string, string>[];
    const mode = (payload.mode ?? {}) as Record<string, string>;
    const tale = (payload.story ?? {}) as Record<string, string>;
    const art = (payload.art ?? {}) as Record<string, string>;
    const draft = await api.createStoryDraft(
      {
        payload: {
          cast: cast.map((m) => ({
            instance_key: m.instance_key,
            name: m.name,
            location_key: m.location_key ?? null,
          })),
          mode: { role: mode.role ?? "watcher" },
          story: { title: tale.title ?? null, tone: tale.tone ?? null },
          ai: { art_source: art.art_source ?? "curated" },
        },
        current_step: "review",
      },
      headers.value,
    );
    await router.push({ path: "/new-story", query: { draft: draft.id, step: "review" } });
  } catch (error) {
    fail("reuse failed", error);
  }
}

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
          <button
            type="button" class="icon" :aria-label="`Actions for ${s.title}`"
            @click="menuFor = menuFor === s.story_id ? null : s.story_id"
          >&vellip;</button>
        </div>
        <div v-if="renaming === s.story_id" class="row">
          <input type="text" v-model="renameText" :aria-label="`New title for ${s.title}`" />
          <button type="button" @click="doRename(s)">Save</button>
        </div>
        <ul v-if="menuFor === s.story_id" class="menu">
          <li><button type="button" @click="renaming = s.story_id; renameText = s.title; menuFor = null">Rename</button></li>
          <li><button type="button" @click="doExport(s)">Export setup</button></li>
          <li><button type="button" @click="doReuse(s)">Use as new story</button></li>
          <li><button type="button" @click="doArchive(s, s.archived ?? false)">{{ s.archived ? "Unarchive" : "Archive story" }}</button></li>
        </ul>
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
