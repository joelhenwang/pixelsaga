<!-- New Story wizard (A08): world, cast, mode, story, AI, review.
  Database-backed drafts with version conflicts; explicit saves;
  invalidation across steps; validated review with stable create keys. -->
<script setup lang="ts">
import { computed, onMounted, ref, watch } from "vue";
import { useRoute, useRouter } from "vue-router";
import type { PresetDetail, PresetSummary, ProviderProfileView, StoryDraftView } from "@gen";
import { api } from "../api";
import { fail, headers } from "../store";

const route = useRoute();
const router = useRouter();

const STEPS = ["world", "characters", "mode", "story", "ai", "review"] as const;
type Step = (typeof STEPS)[number];

const step = ref<Step>("world");
const draft = ref<StoryDraftView | null>(null);
const conflict = ref(false);
const notice = ref("");
const creating = ref(false);
const createKey = ref("");

// Lookups
const worldPresets = ref<PresetSummary[]>([]);
const charPresets = ref<PresetSummary[]>([]);
const worldDetail = ref<PresetDetail | null>(null);
const providers = ref<{ id: string; name: string }[]>([]);
const profiles = ref<ProviderProfileView[]>([]);
const profileConnection = ref("");

// Form state (mirrors draft payload)
const worldPreset = ref("");
const storyName = ref("");
const cast = ref<{ key: string; preset: string; name: string; location: string }[]>([]);
const mode = ref("watcher");
const controlled = ref("");
const title = ref("");
const premise = ref("");
const tone = ref("");
const pacing = ref("measured");
const profileId = ref("");
const artSource = ref("curated");
const validation = ref<{ valid: boolean; issues: string[] }>({ valid: false, issues: [] });

const visited = ref<Step[]>(["world"]);

function payload(): Record<string, unknown> {
  return {
    world: {
      preset_id: worldPreset.value || null,
      preset_revision: 1,
      name: storyName.value || null,
    },
    cast: cast.value.map((m) => ({
      instance_key: m.key,
      preset_id: m.preset || null,
      preset_revision: 1,
      name: m.name,
      location_key: m.location || null,
    })),
    mode: { role: mode.value, controlled_cast_key: controlled.value || null },
    story: {
      title: title.value || null,
      premise: premise.value || null,
      tone: tone.value || null,
      pacing: pacing.value,
    },
    ai: {
      profile_id: profileId.value.split(":")[0] || null,
      profile_revision: profileId.value.includes(":") ? Number(profileId.value.split(":")[1]) : null,
      art_source: artSource.value,
    },
  };
}

function fillFromDraft(view: StoryDraftView): void {
  const p = view.payload as Record<string, Record<string, unknown> | unknown[] | null>;
  const world = (p.world ?? {}) as Record<string, string | null>;
  const members = (p.cast ?? []) as Record<string, string | null>[];
  const md = (p.mode ?? {}) as Record<string, string | null>;
  const story = (p.story ?? {}) as Record<string, string | null>;
  const ai = (p.ai ?? {}) as Record<string, string | null>;
  worldPreset.value = world.preset_id ?? "";
  storyName.value = (world.name as string) ?? "";
  cast.value = members.map((m, i) => ({
    key: (m.instance_key as string) ?? `cast-${i}`,
    preset: (m.preset_id as string) ?? "",
    name: (m.name as string) ?? "",
    location: (m.location_key as string) ?? "",
  }));
  mode.value = (md.role as string) ?? "watcher";
  controlled.value = (md.controlled_cast_key as string) ?? "";
  title.value = (story.title as string) ?? "";
  premise.value = (story.premise as string) ?? "";
  tone.value = (story.tone as string) ?? "";
  pacing.value = (story.pacing as string) ?? "measured";
  const pinId = (ai.profile_id as string | null) ?? "";
  const pinRev = ai.profile_revision as number | null;
  profileId.value = pinId && pinRev ? `${pinId}:${pinRev}` : "";
  artSource.value = (ai.art_source as string) ?? "curated";
}

async function loadDraft(id: string): Promise<void> {
  draft.value = await api.readStoryDraft(id, headers.value);
  fillFromDraft(draft.value);
  conflict.value = false;
}

async function save(target: Step): Promise<boolean> {
  notice.value = "";
  try {
    if (!draft.value) {
      draft.value = await api.createStoryDraft(
        { payload: payload(), current_step: target }, headers.value,
      );
    } else {
      draft.value = await api.saveStoryDraft(
        draft.value.id,
        { payload: payload(), current_step: target, expected_version: draft.value.version },
        headers.value,
      );
    }
    conflict.value = false;
    await router.replace({
      path: "/new-story",
      query: { draft: draft.value.id, step: draft.value.current_step },
    });
    return true;
  } catch (error) {
    if (error instanceof Error && "status" in error && (error as { status: number }).status === 409) {
      conflict.value = true;
      notice.value = "Another tab changed this draft. Reload to keep their version, or save again to overwrite.";
      return false;
    }
    fail("draft save failed", error);
    return false;
  }
}

async function reloadDraft(): Promise<void> {
  if (!draft.value) return;
  await loadDraft(draft.value.id);
}

const locations = computed(() => {
  const payload = worldDetail.value?.revision as Record<string, { key: string; name: string }[]> | null;
  return payload?.locations ?? [];
});

async function pickWorld(id: string): Promise<void> {
  worldPreset.value = id;
  worldDetail.value = id ? await api.readPreset(id, headers.value) : null;
  // Remap or clear cast locations that no longer exist.
  const keys = new Set(locations.value.map((l) => l.key));
  for (const member of cast.value) {
    if (member.location && !keys.has(member.location)) member.location = "";
  }
}

function toggleCast(presetId: string, name: string): void {
  const at = cast.value.findIndex((m) => m.preset === presetId && m.name === name);
  if (at >= 0) {
    const [removed] = cast.value.splice(at, 1);
    if (controlled.value === removed?.key) controlled.value = "";
  } else {
    cast.value.push({ key: `cast-${cast.value.length}-${Date.now() % 1000}`, preset: presetId, name, location: "" });
  }
}

async function quickCreate(name: string): Promise<void> {
  if (!name.trim()) return;
  const created = await api.createPreset(
    { kind: "character", name: name.trim(), payload: { name: name.trim() } }, headers.value,
  );
  charPresets.value = (await api.listPresets(headers.value)).filter((p) => p.kind === "character");
  toggleCast(created.id, created.name);
}

function setMode(next: string): void {
  mode.value = next;
  if (next !== "player") controlled.value = "";
}

function earliestIncomplete(): Step {
  if (!worldPreset.value) return "world";
  if (!cast.value.length) return "characters";
  if (mode.value === "player" && !cast.value.some((m) => m.key === controlled.value)) return "mode";
  return "review";
}

async function go(target: Step): Promise<void> {
  const order = STEPS.indexOf(target);
  const need = STEPS.indexOf(earliestIncomplete());
  if (order > need + 1) {
    notice.value = "Finish the current step first; jumping ahead is blocked.";
    return;
  }
  if (order > STEPS.indexOf(step.value)) {
    const ok = await save(target);
    if (!ok) return;
  }
  step.value = target;
  if (!visited.value.includes(target)) visited.value.push(target);
  await router.replace({ path: "/new-story", query: { ...route.query, step: target } });
  if (target === "review" && draft.value) {
    const result = await api.validateStoryDraft(draft.value.id, headers.value);
    validation.value = { valid: result.valid ?? false, issues: result.issues ?? [] };
  }
}

function createKeyFor(draftId: string): string {
  const storeKey = `pixelsaga.create-key.${draftId}`;
  try {
    const kept = localStorage.getItem(storeKey);
    if (kept) return kept;
    const fresh = crypto.randomUUID();
    localStorage.setItem(storeKey, fresh);
    return fresh;
  } catch {
    return createKey.value || (createKey.value = crypto.randomUUID());
  }
}

async function create(): Promise<void> {
  if (!draft.value) return;
  creating.value = true;
  notice.value = "";
  try {
    const key = createKeyFor(draft.value.id);
    const result = await api.createStory(
      { draft_id: draft.value.id, expected_draft_version: draft.value.version },
      key,
      headers.value,
    );
    try {
      localStorage.removeItem(`pixelsaga.create-key.${draft.value.id}`);
    } catch {
      /* ignore */
    }
    await router.push(`/stories/${result.story_id}/play`);
  } catch (error) {
    fail("creation failed (retry reuses the same key)", error);
  } finally {
    creating.value = false;
  }
}

async function quickStart(): Promise<void> {
  const ember = worldPresets.value.find((w) => w.name === "Ember Vale");
  if (ember) await pickWorld(ember.id);
  const wren = charPresets.value.find((c) => c.name === "Wren");
  const ash = charPresets.value.find((c) => c.name === "Ash");
  cast.value = [];
  if (wren) toggleCast(wren.id, wren.name);
  if (ash) toggleCast(ash.id, ash.name);
  title.value = "The Sealed Gate";
  await save("review");
  await go("review");
}

watch(profileConnection, async (next) => {
  profiles.value = next ? await api.listProfiles(next, headers.value) : [];
});

onMounted(async () => {
  try {
    const all = await api.listPresets(headers.value);
    worldPresets.value = all.filter((p) => p.kind === "world");
    charPresets.value = all.filter((p) => p.kind === "character");
    providers.value = (await api.listProviders(headers.value)).map((p) => ({ id: p.id, name: p.name }));
    const id = route.query.draft;
    const at = route.query.step;
    if (typeof id === "string" && id) {
      await loadDraft(id);
      if (worldPreset.value) {
        worldDetail.value = await api.readPreset(worldPreset.value, headers.value);
      }
    }
    if (typeof at === "string" && (STEPS as readonly string[]).includes(at)) {
      step.value = at as Step;
    } else if (draft.value) {
      step.value = draft.value.current_step as Step;
    }
  } catch (error) {
    fail("wizard unavailable", error);
  }
});
</script>
<template>
  <main class="page">
    <h1>Create a new story</h1>
    <p class="sub">Draft saves explicitly. Nothing is created until Review.</p>
    <ol class="steps">
      <li v-for="s in STEPS" :key="s" :class="{ now: step === s }">
        <button type="button" @click="go(s)">{{ s }}</button>
      </li>
    </ol>
    <p class="notice" v-if="notice">{{ notice }}</p>
    <div v-if="conflict" class="panel">
      <p>This draft changed in another tab.</p>
      <button type="button" @click="reloadDraft">Reload their version</button>
    </div>

    <section v-if="step === 'world'" class="panel">
      <h2>World</h2>
      <div class="cards">
        <button
          v-for="w in worldPresets" :key="w.id" type="button" class="preset"
          :aria-pressed="worldPreset === w.id" @click="pickWorld(w.id)"
        ><b>{{ w.name }}</b><span>rev {{ w.current_revision }}</span></button>
      </div>
      <label>Story name <input type="text" v-model="storyName" /></label>
    </section>

    <section v-if="step === 'characters'" class="panel">
      <h2>Characters</h2>
      <div class="cards">
        <button
          v-for="c in charPresets" :key="c.id" type="button" class="preset"
          :aria-pressed="cast.some((m) => m.preset === c.id)"
          @click="toggleCast(c.id, c.name)"
        ><b>{{ c.name }}</b></button>
      </div>
      <label>Quick create <input type="text" placeholder="Name and Enter" @keyup.enter="quickCreate(($event.target as HTMLInputElement).value); ($event.target as HTMLInputElement).value = ''" /></label>
      <ul>
        <li v-for="m in cast" :key="m.key">
          {{ m.name }}
          <label>starts at
            <select v-model="m.location">
              <option value="">Choose…</option>
              <option v-for="l in locations" :key="l.key" :value="l.key">{{ l.name }}</option>
            </select>
          </label>
        </li>
      </ul>
    </section>

    <section v-if="step === 'mode'" class="panel">
      <h2>Play Mode</h2>
      <button type="button" :aria-pressed="mode === 'player'" @click="setMode('player')">Player</button>
      <button type="button" :aria-pressed="mode === 'watcher'" @click="setMode('watcher')">Watch</button>
      <button type="button" :aria-pressed="mode === 'director'" @click="setMode('director')">Director</button>
      <button type="button" :aria-pressed="mode === 'deity'" @click="setMode('deity')">Deity</button>
      <label v-if="mode === 'player'">Controlled character
        <select v-model="controlled">
          <option value="">Choose…</option>
          <option v-for="m in cast" :key="m.key" :value="m.key">{{ m.name }}</option>
        </select>
      </label>
    </section>

    <section v-if="step === 'story'" class="panel">
      <h2>Story</h2>
      <label>Title <input type="text" v-model="title" /></label>
      <label>Premise <input type="text" v-model="premise" /></label>
      <label>Tone <input type="text" v-model="tone" /></label>
      <label>Pacing
        <select v-model="pacing">
          <option value="measured">Measured</option>
          <option value="brisk">Brisk</option>
          <option value="slow burn">Slow burn</option>
        </select>
      </label>
    </section>

    <section v-if="step === 'ai'" class="panel">
      <h2>AI</h2>
      <label>Connection
        <select v-model="profileConnection">
          <option value="">None (demo narration)</option>
          <option v-for="p in providers" :key="p.id" :value="p.id">{{ p.name }}</option>
        </select>
      </label>
      <label>Profile
        <select v-model="profileId">
          <option value="">Default</option>
          <option v-for="r in profiles" :key="`${r.id}:${r.revision}`" :value="`${r.id}:${r.revision}`">
            {{ r.model_id }} (rev {{ r.revision }})
          </option>
        </select>
      </label>
      <label>Scene art
        <select v-model="artSource">
          <option value="curated">Curated starter art</option>
          <option value="none">No images</option>
        </select>
      </label>
      <p class="sub">Live generation is unavailable: no image adapter is configured.</p>
    </section>

    <section v-if="step === 'review'" class="panel">
      <h2>Review</h2>
      <dl>
        <dt>World</dt><dd>{{ worldDetail ? "selected" : "none" }} &middot; {{ cast.length }} cast</dd>
        <dt>Mode</dt><dd>{{ mode }}{{ controlled ? ` as ${cast.find((m) => m.key === controlled)?.name}` : "" }}</dd>
      </dl>
      <ul v-if="validation.issues.length">
        <li v-for="issue in validation.issues" :key="issue">{{ issue }}</li>
      </ul>
      <button type="button" :disabled="creating || !validation.valid" @click="create">
        {{ creating ? "Creating…" : "Create story" }}
      </button>
    </section>

    <div class="footer">
      <button type="button" @click="quickStart">Quick start from Ember Vale</button>
      <button type="button" @click="save(step)">Save draft</button>
    </div>
  </main>
</template>
