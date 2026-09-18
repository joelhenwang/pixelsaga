<script setup lang="ts">
import { computed, onMounted, ref, watch } from "vue";
import { useRouter } from "vue-router";
import { assetUrl } from "../assets";
import { portraitFor } from "../portrait";
import { checkNew, entries, hasMore, loadOlder, loadProjection, presentation } from "../composables/useProjection";
import { fail, headers, worldId } from "../store";
import {
  controlNotice,
  controlState,
  nextPhase,
  pace,
  pause,
  play,
  reconcile,
  resetControl,
  type PhaseOutcome,
} from "../composables/useSimulationControl";

const router = useRouter();
type Filter = "meaningful" | "all" | "following" | "major";
const MAJOR_TYPES = new Set(["world_ended", "deity_override", "schedule_fired", "macro_aggregate"]);

const filter = ref<Filter>("meaningful");
const followedId = ref<string>("");
const selectedId = ref<string>("");
const expandedSeq = ref<number>(-1);
const zoom = ref<number>(1);
const mapSrc = ref<string>("");
const faceSrc = ref<Record<string, string>>({});
const freshCount = ref<number>(0);

const castById = computed(() => new Map((presentation.value?.cast ?? []).map((c) => [c.character_id, c])));
const anchorByLocation = computed(
  () =>
    new Map<string, { x: number; y: number }>(
      (presentation.value?.manifest.anchors ?? []).map((a) => [a.location_id, { x: Number(a.x), y: Number(a.y) }]),
    ),
);
const activityByCharacter = computed(
  () => new Map((presentation.value?.activities ?? []).map((a) => [a.character_id, a])),
);


const visibleEntries = computed(() => {
  const list = entries.value;
  if (filter.value === "all") {
    return list;
  }
  if (filter.value === "following") {
    return list.filter((e) => (e.participant_ids ?? []).includes(followedId.value));
  }
  if (filter.value === "major") {
    return list.filter((e) => MAJOR_TYPES.has(e.event_type));
  }
  return list.filter((e) => (e.participant_ids ?? []).length > 0 || MAJOR_TYPES.has(e.event_type));
});

const selected = computed(() => (selectedId.value ? castById.value.get(selectedId.value) : undefined));
const selectedActivity = computed(() => (selectedId.value ? activityByCharacter.value.get(selectedId.value) : undefined));

async function face(characterId: string, name: string, assetId: string | null | undefined): Promise<string> {
  if (faceSrc.value[characterId]) {
    return faceSrc.value[characterId];
  }
  const src = assetId
    ? await assetUrl(assetId, worldId.value, headers.value, name)
    : await portraitFor(characterId, name);
  faceSrc.value[characterId] = src;
  return src;
}

async function resolveFaces(): Promise<void> {
  for (const member of presentation.value?.cast ?? []) {
    await face(member.character_id, member.name, member.portrait_asset_id);
  }
  const manifest = presentation.value?.manifest;
  if (manifest?.asset_id) {
    mapSrc.value = await assetUrl(manifest.asset_id, worldId.value, headers.value, "map");
  } else {
    mapSrc.value = "";
  }
}

function tokenStyle(characterId: string): Record<string, string> {
  const member = castById.value.get(characterId);
  const anchor = member ? anchorByLocation.value.get(member.location_id) : undefined;
  if (!anchor) {
    return { display: "none" };
  }
  return { left: `${anchor.x * 100}%`, top: `${anchor.y * 100}%` };
}

function activityLabel(characterId: string): string {
  const activity = activityByCharacter.value.get(characterId);
  if (!activity) {
    return "Present";
  }
  if (activity.kind === "travel") {
    return "Travelling";
  }
  return activity.kind.charAt(0).toUpperCase() + activity.kind.slice(1);
}

function parts(entry: { participant_ids?: string[] | null }): string[] {
  return entry.participant_ids ?? [];
}

function select(characterId: string): void {
  selectedId.value = selectedId.value === characterId ? "" : characterId;
}

function follow(characterId: string): void {
  followedId.value = characterId;
  filter.value = "following";
}

function openScene(sceneId: string | null): void {
  if (sceneId) {
    void router.push({ path: "/scene", query: { scene: sceneId } });
  }
}

function highlight(entryParticipantIds: string[]): void {
  const first = entryParticipantIds[0];
  if (first && castById.value.has(first)) {
    selectedId.value = first;
  }
}

function onKey(event: KeyboardEvent): void {
  if (event.key === "Escape") {
    selectedId.value = "";
  }
}

async function reload(): Promise<void> {
  faceSrc.value = {};
  mapSrc.value = "";
  await loadProjection(fail);
  await resolveFaces();
}

const lastSeenIndex = ref<number>(0);

async function onResolve(): Promise<PhaseOutcome> {
  await reload();
  const fresh = entries.value.filter((e) => e.absolute_index > lastSeenIndex.value);
  lastSeenIndex.value = Math.max(lastSeenIndex.value, ...entries.value.map((e) => e.absolute_index), 0);
  const major = fresh.some((e) => MAJOR_TYPES.has(e.event_type));
  return major ? "pause" : "continue";
}

function togglePlay(): void {
  if (controlState.value === "idle" || controlState.value === "paused" || controlState.value === "failed") {
    resetControl();
    void play(onResolve);
  } else {
    pause();
  }
}

onMounted(() => {
  window.addEventListener("keydown", onKey);
  void reload().then(() => {
    lastSeenIndex.value = Math.max(...entries.value.map((e) => e.absolute_index), 0);
    void reconcile();
  });
});
watch(worldId, () => {
  resetControl();
  void reload();
});
</script>

<template>
  <div class="world">
    <div class="mapcol" aria-label="World map">
      <div class="simcontrols" role="group" aria-label="Simulation controls">
        <button type="button" :disabled="controlState === 'resolving'" @click="nextPhase(onResolve)">
          Next phase
        </button>
        <button type="button" @click="togglePlay">
          {{ controlState === "idle" || controlState === "paused" || controlState === "failed" ? "Play" : "Pause" }}
        </button>
        <select v-model="pace" aria-label="Pacing">
          <option value="slow">Slow</option>
          <option value="normal">Normal</option>
          <option value="fast">Fast</option>
        </select>
        <span class="simstate">{{ controlState }}</span>
        <span v-if="controlNotice" class="simnotice">{{ controlNotice }}</span>
      </div>
      <div v-if="!mapSrc" class="schematic">schematic ground · art pending</div>
      <div class="viewport" :style="{ transform: `scale(${zoom})` }">
        <img v-if="mapSrc" class="map" :src="mapSrc" alt="Ember Vale map" />
        <button
          v-for="c in presentation?.cast ?? []"
          :key="c.character_id"
          type="button"
          class="token"
          :class="{ selected: c.character_id === selectedId }"
          :style="tokenStyle(c.character_id)"
          :aria-label="`${c.name} at ${c.location_id.slice(0, 8)}, ${activityLabel(c.character_id)}`"
          @click="select(c.character_id)"
        >
          <img :src="faceSrc[c.character_id] ?? ''" :alt="c.name" />
          <span class="nameplate">{{ c.name }}</span>
          <span class="action">{{ activityLabel(c.character_id) }}</span>
        </button>
      </div>
      <div class="maptools" role="group" aria-label="Map controls">
        <button type="button" @click="zoom = Math.min(2.5, +(zoom + 0.25).toFixed(2))">+</button>
        <button type="button" @click="zoom = Math.max(1, +(zoom - 0.25).toFixed(2))">−</button>
        <button type="button" @click="zoom = 1">reset</button>
      </div>
      <div v-if="selected" class="inspector">
        <h2>{{ selected.name }}</h2>
        <p class="meta">{{ selected.life_status }} · {{ activityLabel(selected.character_id) }}</p>
        <p v-if="selectedActivity?.kind === 'travel'">
          Travelling. Canonical location unchanged until the activity completes.
        </p>
        <button type="button" @click="follow(selected.character_id)">follow</button>
        <button type="button" @click="selectedId = ''">close</button>
      </div>
      <div class="accesslist">
        <span>characters:</span>
        <button v-for="c in presentation?.cast ?? []" :key="c.character_id" type="button" @click="select(c.character_id)">
          {{ c.name }}
        </button>
      </div>
    </div>
    <aside class="chronicle" aria-label="Chronicle">
      <h1>World Chronicle</h1>
      <div class="filters" role="group" aria-label="Filters">
        <button
          v-for="f in (['meaningful', 'all', 'following', 'major'] as const)"
          :key="f"
          type="button"
          :aria-pressed="filter === f"
          @click="filter = f"
        >{{ f }}</button>
        <button type="button" @click="checkNew(fail).then((n) => (freshCount = n))">
          new events{{ freshCount > 0 ? ` (${freshCount})` : "" }}
        </button>
      </div>
      <button
        v-for="e in visibleEntries"
        :key="e.event_id"
        type="button"
        :class="{ world: parts(e).length === 0 }"
        @click="expandedSeq = expandedSeq === e.sequence ? -1 : e.sequence; highlight(parts(e))"
      >
        <span class="icons">
          <template v-if="parts(e).length === 0"><span class="solo">✦</span></template>
          <template v-else>
            <img :src="faceSrc[parts(e)[0]] ?? ''" :alt="castById.get(parts(e)[0])?.name ?? ''" />
            <template v-if="parts(e).length > 1">
              <span class="mid">⇄</span>
              <img :src="faceSrc[parts(e)[1]] ?? ''" :alt="castById.get(parts(e)[1])?.name ?? ''" />
            </template>
          </template>
        </span>
        <span>
          <b>{{ e.title }}</b>
          <span class="meta">day {{ e.absolute_index }} · {{ e.event_type }}</span>
          <span v-if="expandedSeq === e.sequence" class="detail">
            <p v-if="e.text">{{ e.text }}</p>
            <button v-if="e.scene_id" type="button" @click.stop="openScene(e.scene_id)">open scene</button>
          </span>
        </span>
      </button>
      <button v-if="hasMore" type="button" @click="loadOlder(fail)">older events</button>
      <p v-if="visibleEntries.length === 0" class="dim">No events under this filter yet.</p>
    </aside>
  </div>
</template>

<style scoped>
.simcontrols { position: absolute; top: 12px; left: 12px; z-index: 5; display: flex; gap: 8px; align-items: center; background: var(--surface-panel); border: 1px solid var(--border-subtle); border-radius: 14px; padding: 8px 12px; box-shadow: 0 4px 18px rgba(20, 16, 8, 0.25); font-size: 13px; }
.simcontrols button { border: 1px solid var(--action-primary); background: #fff; color: var(--action-primary); border-radius: 8px; padding: 5px 12px; cursor: pointer; font: inherit; }
.simcontrols button:disabled { opacity: 0.4; cursor: default; }
.simcontrols select { font: inherit; border-radius: 8px; border: 1px solid var(--border-subtle); padding: 5px; }
.simcontrols .simstate { color: var(--text-secondary); }
.simcontrols .simnotice { color: var(--accent-gold); }
.world { display: grid; grid-template-columns: minmax(0, 1fr) 350px; gap: 0; min-height: calc(100vh - 44px); }
.mapcol { position: relative; overflow: hidden; background: #e8e2d4; min-height: 60vh; }
.schematic { position: absolute; inset: 0; display: flex; align-items: center; justify-content: center; color: var(--text-secondary); }
.viewport { position: absolute; inset: 0; transform-origin: center; }
.viewport .map { position: absolute; inset: 0; width: 100%; height: 100%; object-fit: fill; }
.token { position: absolute; transform: translate(-50%, -50%); background: none; border: 0; padding: 0; display: flex; flex-direction: column; align-items: center; cursor: pointer; }
.token img { width: 48px; height: 48px; border-radius: 50%; object-fit: cover; border: 2px solid var(--surface-panel); outline: 2px solid var(--action-primary); background: #e8e2d4; }
.token.selected img { outline-color: var(--accent-gold); }
.token .nameplate { background: var(--action-primary); color: #fff; border-radius: 4px; padding: 1px 10px; font-size: 12.5px; margin-top: 2px; white-space: nowrap; }
.token.selected .nameplate { background: var(--accent-gold); }
.token .action { font-size: 11.5px; color: var(--text-primary); background: rgba(255, 252, 247, 0.9); border-radius: 4px; padding: 0 8px; margin-top: 2px; white-space: nowrap; }
.maptools { position: absolute; right: 12px; top: 12px; display: flex; gap: 4px; }
.maptools button { width: 32px; height: 32px; border-radius: 8px; border: 1px solid var(--border-subtle); background: var(--surface-panel); cursor: pointer; }
.inspector { position: absolute; left: 12px; bottom: 64px; background: var(--surface-panel); border: 1px solid var(--border-subtle); border-radius: 12px; padding: 12px; max-width: 320px; z-index: 3; }
.inspector h2 { font-family: var(--font-title); margin: 0; font-size: 17px; }
.inspector .meta { color: var(--text-secondary); font-size: 12px; }
.accesslist { position: absolute; left: 12px; bottom: 12px; display: flex; gap: 6px; align-items: center; font-size: 12px; color: var(--text-secondary); }
.accesslist button { border: 1px solid var(--border-subtle); background: var(--surface-panel); border-radius: 12px; padding: 1px 10px; cursor: pointer; font-size: 12px; }
.chronicle { background: var(--surface-panel); border-left: 1px solid var(--border-subtle); overflow-y: auto; padding: 12px 14px; max-height: calc(100vh - 44px); }
.chronicle h1 { font-family: var(--font-title); font-size: 17px; margin: 0 0 8px; }
.filters { display: flex; gap: 6px; margin-bottom: 8px; flex-wrap: wrap; }
.filters button { border: 1px solid var(--border-subtle); background: #fff; border-radius: 14px; padding: 2px 10px; cursor: pointer; font-size: 12.5px; }
.filters button[aria-pressed="true"] { background: var(--action-primary); color: #fff; border-color: var(--action-primary); }
.entry { display: flex; gap: 10px; width: 100%; text-align: left; background: none; border: 0; border-bottom: 1px solid var(--border-subtle); padding: 8px 0; cursor: pointer; font: inherit; color: inherit; }
.entry .icons { flex: none; display: flex; align-items: center; }
.entry .icons img { width: 36px; height: 36px; border-radius: 50%; object-fit: cover; border: 2px solid var(--surface-panel); outline: 1px solid var(--border-subtle); background: #e8e2d4; }
.entry .icons img + img { margin-left: -10px; }
.entry .icons .mid { width: 22px; height: 22px; border-radius: 50%; background: var(--accent-social); color: #fff; font-size: 12px; display: flex; align-items: center; justify-content: center; margin: 0 -6px; z-index: 1; border: 2px solid var(--surface-panel); }
.entry .icons .solo { width: 36px; height: 36px; border-radius: 50%; background: var(--accent-magic); color: #fff; display: flex; align-items: center; justify-content: center; font-size: 17px; }
.entry b { display: block; font-size: 13.5px; }
.entry .meta { font-size: 11.5px; color: var(--text-secondary); }
.entry .detail p { margin: 4px 0; font-size: 12.5px; }
.entry .detail button { color: var(--action-primary); background: none; border: 0; cursor: pointer; padding: 0; font-size: 12.5px; }
.entry.world { border: 1px solid var(--accent-magic); border-radius: 10px; padding: 8px; margin: 8px 0; background: #f6f1fb; }
.dim { color: var(--text-secondary); }
@media (max-width: 1100px) {
  .world { grid-template-columns: 1fr; }
  .chronicle { max-height: 45vh; border-top: 2px solid var(--accent-gold); }
}
</style>
