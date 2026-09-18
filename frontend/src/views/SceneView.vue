<script setup lang="ts">
import { onMounted, onUnmounted, ref } from "vue";
import type { BeatView, SceneDetail, SceneSummary } from "@gen";
import { api } from "../api";
import { advance, busy, characters, characterId, clock, fail, headers, nextIndex, refresh, role, worldId } from "../store";
import Portrait from "../Portrait.vue";

const scenes = ref<SceneSummary[]>([]);
const currentId = ref<string>("");
const detail = ref<SceneDetail | null>(null);
const beats = ref<BeatView[]>([]);
const family = ref("wait");
const topic = ref("");
const targetId = ref("");
const destination = ref("");
const itemId = ref("");
const queued = ref<string>("");
const quietPhase = ref<boolean>(false);

async function selectScene(id: string): Promise<void> {
  currentId.value = id;
  try {
    detail.value = await api.scene(id, headers.value);
    beats.value = await api.narration(id, headers.value);
  } catch (error) {
    fail("scene load failed", error);
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
  } catch (error) {
    fail("scene load failed", error);
  }
}

async function submitAction(): Promise<void> {
  if (busy.value) {
    return;
  }
  const actor = role.value === "player" && characterId.value ? characterId.value : characters.value[0]?.id;
  if (!actor || !worldId.value) {
    fail("action failed", new Error("no character or world to act with"));
    return;
  }
  const action: Record<string, unknown> = { family: family.value, character_id: actor, snapshot_id: "00000000-0000-0000-0000-000000000000" };
  if (family.value === "observe") {
    action["focus"] = topic.value || "surroundings";
  }
  if (family.value === "communicate") {
    action["target_character_id"] = targetId.value;
    action["topic"] = topic.value || "hello";
  }
  if (family.value === "spar") {
    action["target_character_id"] = targetId.value;
  }
  if (family.value === "appeal") {
    action["proposition"] = topic.value || "the mill stands";
  }
  if (family.value === "transfer") {
    action["target_character_id"] = targetId.value;
    action["item_instance_id"] = itemId.value;
  }
  if (family.value === "move") {
    action["destination_location_id"] = destination.value;
  }
  busy.value = true;
  try {
    const report = await api.advance(worldId.value, nextIndex.value, headers.value, { [actor]: action });
    nextIndex.value = report.absolute_index + 1;
    quietPhase.value = report.quiet ?? false;
    const summaries = await api.scenes(report.run_id, headers.value);
    scenes.value = summaries;
    queued.value = `Queued ${family.value}${topic.value ? ": " + topic.value : ""}. You control the attempt, not its outcome.`;
    if (summaries.length > 0) {
      await selectScene(summaries[summaries.length - 1].id);
    }
    const world = await api.world(headers.value);
    clock.value = `day ${world.day}, ${world.phase}`;
  } catch (error) {
    fail("action failed", error);
  } finally {
    busy.value = false;
  }
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
    document.getElementById("topic")?.focus();
  }
}

onMounted(() => {
  window.addEventListener("keydown", onKey);
  void refresh();
});
onUnmounted(() => {
  window.removeEventListener("keydown", onKey);
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
  <main class="stage" aria-live="polite">
    <template v-if="detail">
      <h1>scene {{ detail.id.slice(0, 8) }} · {{ detail.status }}<span v-if="quietPhase" class="dim"> · quiet phase</span></h1>
      <p v-for="b in beats" :key="b.id" class="beat" :class="{ dialogue: b.speaker_id }">
        <span v-if="b.speaker_id" class="who">{{ b.speaker_id.slice(0, 8) }}:</span> {{ b.text }}
      </p>
      <p v-if="beats.length === 0" class="dim">No beats yet. Narration lands after commit.</p>
      <div class="cast">
        <div v-for="p in detail.participants" :key="p.character_id" class="person">
          <Portrait :asset-id="p.character_id" :name="p.character_id.slice(0, 8)" />
          <span><span class="nm">{{ p.character_id.slice(0, 8) }}</span><br><span class="rl">{{ p.role }}</span></span>
        </div>
      </div>
      <h2>attempts</h2>
      <p v-for="a in detail.attempts" :key="a.id" class="fact">{{ a.observable_summary }}</p>
    </template>
    <template v-else>
      <h1>no scene selected</h1>
      <p class="dim">Seed, advance a phase, then pick a scene. Arrows move between scenes, slash focuses the topic box.</p>
    </template>
  </main>
  <footer class="bar">
    <div class="row">
      <select v-model="family" aria-label="Action">
        <option value="wait">wait</option>
        <option value="observe">observe</option>
        <option value="rest">rest</option>
        <option value="move">move</option>
        <option value="communicate">communicate</option>
        <option value="spar">spar</option>
        <option value="appeal">appeal</option>
        <option value="transfer">transfer</option>
      </select>
      <select v-model="targetId" v-if="family === 'communicate' || family === 'spar' || family === 'transfer'" aria-label="Target">
        <option v-for="c in characters" :key="c.id" :value="c.id">{{ c.name }}</option>
      </select>
      <input v-model="destination" v-if="family === 'move'" placeholder="destination location id" aria-label="Destination">
      <input v-model="itemId" v-if="family === 'transfer'" placeholder="item instance id" aria-label="Item">
      <input id="topic" v-model="topic" placeholder="topic or focus: blank waits" aria-label="Topic">
      <button id="go" type="button" @click="submitAction" :disabled="busy">Act</button>
      <button type="button" @click="advanceHere" :disabled="busy">advance to {{ nextIndex }}</button>
    </div>
    <p id="queued" v-if="queued">{{ queued }}</p>
  </footer>
</template>
