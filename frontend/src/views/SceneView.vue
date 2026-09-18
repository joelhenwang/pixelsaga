<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref, watch } from "vue";
import { useRoute } from "vue-router";
import type { AssetView, BeatView, SceneDetail, SceneSummary, SuggestionView } from "@gen";
import { api } from "../api";
import { assetUrl } from "../assets";
import { portraitFor } from "../portrait";
import { advance, busy, characters, characterId, clock, fail, headers, nextIndex, refresh, role, worldId } from "../store";

const scenes = ref<SceneSummary[]>([]);
const currentId = ref<string>("");
const detail = ref<SceneDetail | null>(null);
const beats = ref<BeatView[]>([]);
const suggestions = ref<SuggestionView[]>([]);
const draft = ref<string>("");
const pendingSuggestion = ref<SuggestionView | null>(null);
const queued = ref<string>("");
const quietPhase = ref<boolean>(false);
const heroSrc = ref<string>("");
const heroCaption = ref<string>("");
const faceSrc = ref<Record<string, string>>({});
const backgroundAssets = ref<AssetView[]>([]);
const castName = ref<Record<string, string>>({});

const isPlayer = computed(() => role.value === "player" && characterId.value !== "");
const actorName = computed(() => characters.value.find((c) => c.id === characterId.value)?.name ?? "you");

function sceneKey(): string {
  return `worldsim.scene.${worldId.value}`;
}

async function speakerFace(id: string, name: string): Promise<string> {
  if (!faceSrc.value[id]) {
    faceSrc.value[id] = await portraitFor(id, name);
  }
  return faceSrc.value[id];
}

async function selectScene(id: string): Promise<void> {
  currentId.value = id;
  try {
    detail.value = await api.scene(id, headers.value);
    beats.value = await api.narration(id, headers.value);
    localStorage.setItem(sceneKey(), id);
    const names = new Set<string>();
    for (const p of detail.value.participants ?? []) {
      const name = castName.value[p.character_id] ?? p.character_id.slice(0, 8);
      names.add(name);
      await speakerFace(p.character_id, name);
    }
    for (const beat of beats.value) {
      if (beat.speaker_id) {
        const name = castName.value[beat.speaker_id] ?? beat.speaker_id.slice(0, 8);
        await speakerFace(beat.speaker_id, name);
      }
    }
    heroCaption.value = names.size > 0 ? [...names].join(", ") : "an empty room";
  } catch (error) {
    fail("scene load failed", error);
  }
}

async function loadContext(): Promise<void> {
  if (!worldId.value) {
    return;
  }
  try {
    const [party, backgrounds] = await Promise.all([
      api.characters(worldId.value, headers.value),
      api.listAssets(worldId.value, "background", headers.value),
    ]);
    const names: Record<string, string> = {};
    for (const c of party) {
      names[c.id] = c.name;
    }
    castName.value = names;
    backgroundAssets.value = backgrounds;
    if (backgrounds.length > 0) {
      heroSrc.value = await assetUrl(backgrounds[0].id, worldId.value, headers.value, "scene");
    } else {
      heroSrc.value = "";
    }
    if (isPlayer.value) {
      suggestions.value = await api.suggestions(characterId.value, headers.value);
    } else {
      suggestions.value = [];
    }
  } catch (error) {
    fail("adventure load failed", error);
  }
}

async function advanceHere(): Promise<void> {
  const runId = await advance();
  if (!runId) {
    return;
  }
  try {
    const summaries = await api.scenes(runId, headers.value);
    scenes.value = summaries;
    if (summaries.length > 0) {
      await selectScene(summaries[summaries.length - 1].id);
    }
    await loadContext();
  } catch (error) {
    fail("scene load failed", error);
  }
}

async function attemptSuggestion(suggestion: SuggestionView): Promise<void> {
  if (!isPlayer.value) {
    return;
  }
  if (suggestion.needs_topic) {
    pendingSuggestion.value = suggestion;
    document.getElementById("draft")?.focus();
    return;
  }
  await fileAttempt(suggestion.title);
}

async function fileAttempt(label: string): Promise<void> {
  if (!isPlayer.value || busy.value) {
    return;
  }
  busy.value = true;
  try {
    const extra = draft.value.trim() ? ` — ${draft.value.trim()}` : "";
    const item = await api.submitIntervention(
      {
        world_id: worldId.value,
        client_request_id: crypto.randomUUID(),
        text: `${actorName.value} attempts: ${label}${extra}`,
        mode: "attempt",
        scope: { kind: "characters", character_ids: [characterId.value], location_ids: [] },
        effective_at: "next_boundary",
      },
      headers.value,
    );
    if (item.status !== "queued") {
      queued.value = `Not queued (${item.status}): ${item.failure_reason || "see queue"}. Draft kept.`;
      return;
    }
    const runId = await advance();
    if (!runId) {
      queued.value = "Queued, but the phase did not advance. Draft kept.";
      return;
    }
    const result = await api.readIntervention(item.id, headers.value);
    if (result.status === "completed") {
      queued.value = `${actorName.value} attempted ${label}. You control the attempt, not its outcome.`;
      draft.value = "";
      pendingSuggestion.value = null;
    } else {
      queued.value = `Attempt ${result.status}: ${result.failure_reason || "see queue"}. Draft kept.`;
    }
    const summaries = await api.scenes(runId, headers.value);
    scenes.value = summaries;
    if (summaries.length > 0) {
      await selectScene(summaries[summaries.length - 1].id);
    }
    await loadContext();
  } catch (error) {
    fail("action failed", error);
  } finally {
    busy.value = false;
  }
}

function submitDraft(): void {
  if (pendingSuggestion.value) {
    const suggestion = pendingSuggestion.value;
    pendingSuggestion.value = null;
    void fileAttempt(suggestion.title);
    return;
  }
  const text = draft.value.trim();
  if (!text) {
    return;
  }
  void fileAttempt(text);
}

function onKey(event: KeyboardEvent): void {
  if (event.key === "ArrowRight" || event.key === "ArrowLeft") {
    const ids = scenes.value.map((s) => s.id);
    const at = ids.indexOf(currentId.value);
    const next = event.key === "ArrowRight" ? at + 1 : at - 1;
    if (next >= 0 && next < ids.length) {
      void selectScene(ids[next]);
    }
  }
  if (event.key === "/" && document.activeElement?.tagName !== "INPUT") {
    event.preventDefault();
    document.getElementById("draft")?.focus();
  }
}

const route = useRoute();

onMounted(() => {
  window.addEventListener("keydown", onKey);
  void refresh().then(() => {
    void loadContext();
    const linked = route.query.scene;
    if (typeof linked === "string" && linked) {
      void selectScene(linked);
      return;
    }
    const restored = localStorage.getItem(sceneKey());
    if (restored) {
      void selectScene(restored).catch(() => undefined);
    }
  });
});
onUnmounted(() => {
  window.removeEventListener("keydown", onKey);
});
watch(worldId, () => {
  void loadContext();
});
</script>

<template>
  <nav class="strip" aria-label="Scenes">
    <button
      v-for="s in scenes"
      :key="s.id"
      type="button"
      :aria-current="s.id === currentId ? 'true' : 'false'"
      @click="selectScene(s.id)"
    >
      {{ s.status }} · {{ s.id.slice(0, 8) }}
    </button>
    <span class="status">{{ clock }}</span>
  </nav>
  <main class="journal" aria-live="polite">
    <template v-if="detail">
      <div class="hero">
        <img v-if="heroSrc" class="heroart" :src="heroSrc" :alt="`Scene art: ${heroCaption}`" />
        <div v-else class="herofallback">schematic scene · art pending</div>
        <div class="title-card">
          <h1>Scene {{ detail.id.slice(0, 8) }} · {{ detail.status }}</h1>
          <p>{{ heroCaption }}<span v-if="quietPhase" class="dim"> · quiet phase</span></p>
        </div>
      </div>
      <div class="beats">
        <p v-if="beats.length === 0" class="dim">No beats yet. Narration lands after commit.</p>
        <div v-for="b in beats" :key="b.id" class="beat" :class="{ dialogue: b.speaker_id }">
          <img
            v-if="b.speaker_id"
            :src="faceSrc[b.speaker_id] ?? ''"
            :alt="castName[b.speaker_id] ?? ''"
          />
          <p>
            <strong v-if="b.speaker_id">{{ castName[b.speaker_id] ?? b.speaker_id.slice(0, 8) }}:</strong>
            {{ b.text }}
          </p>
        </div>
      </div>
      <div v-if="detail.resolution" class="outcome">
        <b>{{ detail.resolution.outcome }}</b> · {{ detail.resolution.resolver }} · {{ detail.resolution.rationale }}
      </div>
      <p v-for="a in detail.attempts" :key="a.id" class="fact">{{ a.observable_summary }}</p>
      <template v-if="isPlayer">
        <div class="choices">
          <button
            v-for="s in suggestions"
            :key="s.id"
            type="button"
            class="choice"
            @click="attemptSuggestion(s)"
          >
            <span class="icon"><i></i></span>
            <span><b>{{ s.title }}</b><span>{{ s.subtitle }}</span></span>
            <span class="chev">›</span>
          </button>
        </div>
        <div class="composer">
          <input
            id="draft"
            v-model="draft"
            aria-label="Custom action"
            :placeholder="pendingSuggestion ? `${pendingSuggestion.title}: add detail…` : 'Try something else…'"
            @keydown.enter="submitDraft"
          />
          <button id="go" type="button" aria-label="Send action" :disabled="busy" @click="submitDraft">
            <svg viewBox="0 0 280 280" role="img" aria-hidden="true">
              <path
                fill="#fff"
                d="M41.5 29.7 250.2 132.1 C261.0 137.4 261.0 152.6 250.2 157.9 L41.5 262.3 C31.3 267.4 20.5 258.1 23.3 247.1 L44.0 166.4 C44.6 163.9 46.6 162.2 49.1 161.9 L135.1 151.9 C143.0 151.0 143.0 140.0 135.1 139.1 L49.1 131.2 C46.6 130.9 44.6 129.2 44.0 126.8 L23.4 45.4 C20.6 34.3 31.3 24.7 41.5 29.7Z"
              />
            </svg>
          </button>
        </div>
        <p id="queued" v-if="queued">{{ queued }}</p>
      </template>
      <p v-else class="dim">Switch to Player and bind a character to act.</p>
    </template>
    <template v-else>
      <h1>no scene selected</h1>
      <p class="dim">Seed, advance a phase, then pick a scene. Arrows move between scenes, slash focuses the input.</p>
      <button type="button" @click="advanceHere" :disabled="busy">advance to {{ nextIndex }}</button>
    </template>
  </main>
</template>

<style scoped>
.journal { max-width: 1020px; margin: 0 auto; padding: 14px; }
.hero { position: relative; border-radius: 8px; overflow: hidden; background: #e8e2d4; }
.heroart { display: block; width: 100%; height: 420px; object-fit: cover; }
.herofallback { height: 120px; display: flex; align-items: center; justify-content: center; color: var(--text-secondary); }
.title-card { position: absolute; top: 14px; left: 14px; background: rgba(20, 16, 8, 0.55); border-radius: 8px; padding: 10px 16px; color: #fff; }
.title-card h1 { margin: 0; font-size: 22px; font-family: var(--font-title); color: #fff; }
.title-card p { margin: 2px 0 0; font-size: 12px; color: #fff; }
.beats { margin: 12px 0; }
.beat { display: flex; gap: 10px; align-items: flex-start; margin: 10px 0; font-size: 15px; line-height: 1.6; }
.beat img { width: 44px; height: 44px; border-radius: 50%; object-fit: cover; flex: none; background: #e8e2d4; }
.beat p { margin: 0; }
.beat.dialogue p { background: #f3efe4; border-radius: 8px; padding: 8px 12px; }
.outcome { border: 1px solid var(--border-subtle); border-radius: 8px; padding: 8px 12px; font-size: 13px; margin: 10px 0; background: var(--surface-panel); }
.fact { font-size: 13px; color: var(--text-secondary); margin: 4px 0; }
.dim { color: var(--text-secondary); }
.choices { display: flex; flex-direction: column; gap: 8px; margin: 10px 0; }
.choice { display: flex; gap: 10px; align-items: center; text-align: left; background: #fff; border: 1px solid var(--border-subtle); border-radius: 8px; padding: 8px 10px; cursor: pointer; font: inherit; width: 100%; }
.choice .icon { flex: none; width: 34px; height: 34px; border-radius: 50%; background: var(--action-primary); color: #fff; display: flex; align-items: center; justify-content: center; }
.choice .icon i { width: 12px; height: 12px; border-radius: 50%; background: #fff; display: block; }
.choice b { display: block; font-size: 14px; }
.choice span span { display: block; font-size: 12px; color: var(--text-secondary); }
.choice .chev { margin-left: auto; color: var(--text-secondary); }
.composer { position: relative; margin-top: 10px; }
.composer input { width: 100%; height: 40px; border: 1px solid var(--border-subtle); border-radius: 8px; padding: 0 44px 0 12px; font: inherit; background: #fff; }
.composer button { position: absolute; right: 6px; top: 6px; width: 28px; height: 28px; border: 0; border-radius: 6px; background: var(--action-primary); cursor: pointer; display: flex; align-items: center; justify-content: center; }
.composer button svg { width: 14px; height: 14px; display: block; }
.composer button:disabled { opacity: 0.4; cursor: default; }
#queued { font-size: 13px; color: var(--text-secondary); margin-top: 8px; }
.strip { display: flex; gap: 0; border-bottom: 1px solid var(--line, #ddd); font-size: 12px; overflow-x: auto; }
.strip button { border: 0; background: none; padding: 8px 12px; cursor: pointer; white-space: nowrap; }
.status { margin-left: auto; padding: 8px 12px; color: var(--text-secondary); white-space: nowrap; }
@media (max-width: 1100px) { .heroart { height: 300px; } }
</style>
