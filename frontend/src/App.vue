<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref } from "vue";
import type { BeatView, PartyMemberView, SceneDetail, SceneSummary } from "@gen";
import { api, headersFor, type Role } from "./api";
import Portrait from "./Portrait.vue";

const role = ref<Role>("watcher");
const characterId = ref<string>("");
const characters = ref<{ id: string; name: string }[]>([]);
const worldId = ref<string>("");
const clock = ref<string>("no world");
const nextIndex = ref<number>(1);
const scenes = ref<SceneSummary[]>([]);
const currentId = ref<string>("");
const detail = ref<SceneDetail | null>(null);
const beats = ref<BeatView[]>([]);
const family = ref("wait");
const topic = ref("");
const targetId = ref("");
const destination = ref("");
const queued = ref<string>("");
const view = ref<"scene" | "party">("scene");
const roster = ref<PartyMemberView[]>([]);
const beginName = ref<string>("");
const beginRace = ref<string>("human");
const beginClass = ref<string>("fighter");
const beginLevel = ref<number>(1);
const connection = ref<"online" | "offline">("online");
const notice = ref<string>("");
const busy = ref<boolean>(false);

const headers = computed<Record<string, string>>(() => ({ ...headersFor(role.value, characterId.value || null) }));

function fail(message: string, error: unknown): void {
  connection.value = "offline";
  notice.value = `${message}: ${error instanceof Error ? error.message : "unknown"}`;
}

async function seed(): Promise<void> {
  notice.value = "";
  try {
    await fetch("/api/v1/world/seed", { method: "POST", headers: headers.value });
    await refresh();
  } catch (error) {
    fail("seed failed", error);
  }
}

async function refresh(): Promise<void> {
  notice.value = "";
  try {
    const world = await api.world(headers.value);
    worldId.value = world.id;
    clock.value = `day ${world.day}, ${world.phase}`;
    const current = await fetch(`/api/v1/world/phases/current`, { headers: headers.value }).then(async (r) => {
      if (!r.ok) {
        throw new Error(`${r.status}`);
      }
      return (await r.json()) as { absolute_index: number };
    });
    nextIndex.value = current.absolute_index + 1;
    const party = await api.party(world.id, headers.value);
    roster.value = party.members ?? [];
    const list = await api.characters(world.id, headers.value);
    characters.value = list.map((c) => ({ id: c.id, name: c.name }));
    if (!characterId.value && list.length > 0) {
      characterId.value = list[0].id;
    }
    if (!targetId.value && list.length > 1) {
      targetId.value = list[1].id;
    }
    connection.value = "online";
  } catch (error) {
    fail("refresh failed", error);
  }
}

async function advance(): Promise<void> {
  if (busy.value) {
    return;
  }
  busy.value = true;
  notice.value = "";
  try {
    const report = await api.advance(worldId.value, nextIndex.value, headers.value);
    nextIndex.value = report.absolute_index + 1;
    const summaries = await api.scenes(report.run_id, headers.value);
    scenes.value = summaries;
    if (summaries.length > 0) {
      await selectScene(summaries[summaries.length - 1].id);
    }
    const world = await api.world(headers.value);
    clock.value = `day ${world.day}, ${world.phase}`;
    roster.value = (await api.party(worldId.value, headers.value)).members ?? [];
    connection.value = "online";
  } catch (error) {
    fail("advance failed", error);
  } finally {
    busy.value = false;
  }
}

async function selectScene(id: string): Promise<void> {
  currentId.value = id;
  try {
    detail.value = await api.scene(id, headers.value);
    beats.value = await api.narration(id, headers.value);
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
    notice.value = "no character or world to act with";
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
  if (family.value === "move") {
    action["destination_location_id"] = destination.value;
  }
  busy.value = true;
  try {
    const report = await api.advance(worldId.value, nextIndex.value, headers.value, { [actor]: action });
    nextIndex.value = report.absolute_index + 1;
    const summaries = await api.scenes(report.run_id, headers.value);
    scenes.value = summaries;
    queued.value = `Queued ${family.value}${topic.value ? ": " + topic.value : ""}. You control the attempt, not its outcome.`;
    if (summaries.length > 0) {
      await selectScene(summaries[summaries.length - 1].id);
    }
    const world = await api.world(headers.value);
    clock.value = `day ${world.day}, ${world.phase}`;
    roster.value = (await api.party(worldId.value, headers.value)).members ?? [];
  } catch (error) {
    fail("action failed", error);
  } finally {
    busy.value = false;
  }
}

function hpbar(member: PartyMemberView): string {
  const cur = member.hp_current ?? 0;
  const max = member.hp_max ?? 1;
  const cells = 10;
  const filled = Math.round((cur / max) * cells);
  return "■".repeat(filled) + "□".repeat(cells - filled);
}

function hpClass(member: PartyMemberView): string {
  const frac = (member.hp_current ?? 0) / (member.hp_max ?? 1);
  if (frac <= 0.25) {
    return "crit";
  }
  return frac <= 0.6 ? "low" : "";
}

async function beginAdventure(): Promise<void> {
  if (!worldId.value || !beginName.value.trim()) {
    notice.value = "name your adventurer first";
    return;
  }
  notice.value = "";
  try {
    await api.beginParty(
      {
        world_id: worldId.value,
        name: beginName.value.trim(),
        race: beginRace.value,
        character_class: beginClass.value,
        level: beginLevel.value,
      },
      headers.value,
    );
    beginName.value = "";
    const party = await api.party(worldId.value, headers.value);
    roster.value = party.members ?? [];
    connection.value = "online";
  } catch (error) {
    fail("begin failed", error);
  }
}

function toggleTheme(event: Event): void {
  const light = document.documentElement.classList.toggle("light");
  const target = event.target as HTMLElement | null;
  if (target) {
    target.textContent = light ? "dark" : "light";
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
  <div class="shell">
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
      <span class="conn" :data-state="connection">{{ connection }}</span>
    </nav>
    <div class="toolbar">
      <label>role
        <select v-model="role" @change="refresh">
          <option value="watcher">watcher</option>
          <option value="player">player</option>
        </select>
      </label>
      <label v-if="role === 'player'">character
        <select v-model="characterId" @change="refresh">
          <option v-for="c in characters" :key="c.id" :value="c.id">{{ c.name }}</option>
        </select>
      </label>
      <button type="button" @click="seed">seed</button>
      <button type="button" @click="advance" :disabled="busy">advance to {{ nextIndex }}</button>
      <button type="button" @click="refresh">refresh</button>
      <button type="button" @click="view = 'scene'" :disabled="view === 'scene'">scenes</button>
      <button type="button" @click="view = 'party'" :disabled="view === 'party'">party</button>
      <button id="theme" type="button" @click="toggleTheme">light</button>
      <span class="notice" v-if="notice">{{ notice }}</span>
    </div>
    <main class="stage" aria-live="polite">
      <template v-if="view === 'party'">
        <h1>party · {{ roster.length }} seated</h1>
        <div v-if="roster.length > 0">
          <div v-for="m in roster" :key="m.id" class="member">
            <div class="mrow">
              <Portrait :asset-id="m.id" :name="m.name" :size="32" />
              <span class="mname">{{ m.name }}</span>
              <span class="mmeta">lv {{ m.level }} {{ m.character_class }}</span>
              <span class="hp" :class="hpClass(m)"><span class="bar">{{ hpbar(m) }}</span> {{ m.hp_current }}/{{ m.hp_max }}</span>
            </div>
            <div v-if="(m.conditions ?? []).length > 0" class="conds">{{ (m.conditions ?? []).join(" · ") }}</div>
          </div>
        </div>
        <form class="beginform" @submit.prevent="beginAdventure">
          <h2>{{ roster.length > 0 ? "seat another" : "begin adventure" }}</h2>
          <div class="brow">
            <label>name<input v-model="beginName" maxlength="64" autocomplete="off" aria-label="Adventurer name"></label>
          </div>
          <div class="brow">
            <label>race
              <select v-model="beginRace">
                <option value="human">human</option>
                <option value="elf">elf</option>
                <option value="dwarf">dwarf</option>
                <option value="halfling">halfling</option>
              </select>
            </label>
            <label>class
              <select v-model="beginClass">
                <option value="fighter">fighter</option>
                <option value="ranger">ranger</option>
                <option value="wizard">wizard</option>
                <option value="cleric">cleric</option>
              </select>
            </label>
            <label>level
              <select v-model.number="beginLevel">
                <option :value="1">1</option>
                <option :value="2">2</option>
                <option :value="3">3</option>
              </select>
            </label>
          </div>
          <button id="begin" type="submit">begin</button>
        </form>
      </template>
      <template v-else-if="detail">

        <h1>scene {{ detail.id.slice(0, 8) }} · {{ detail.status }}</h1>
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
        </select>
        <select v-model="targetId" v-if="family === 'communicate'" aria-label="Target">
          <option v-for="c in characters" :key="c.id" :value="c.id">{{ c.name }}</option>
        </select>
        <input v-model="destination" v-if="family === 'move'" placeholder="destination location id" aria-label="Destination">
        <input id="topic" v-model="topic" placeholder="topic or focus: blank waits" aria-label="Topic">
        <button id="go" type="button" @click="submitAction" :disabled="busy">Act</button>
      </div>
      <p id="queued" v-if="queued">{{ queued }}</p>
    </footer>
  </div>
</template>
