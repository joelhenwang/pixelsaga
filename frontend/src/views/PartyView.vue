<script setup lang="ts">
import { onMounted, ref, watch } from "vue";
import { useRouter } from "vue-router";
import type { CharacterSummary, PartyMemberView } from "@gen";
import { api } from "../api";
import { assetUrl } from "../assets";
import { portraitFor } from "../portrait";
import { fail, headers, refresh, role, switchRole, worldId } from "../store";

const router = useRouter();
const roster = ref<PartyMemberView[]>([]);
const faces = ref<Record<string, string>>({});
const characters = ref<CharacterSummary[]>([]);
const portraits = ref<Record<string, string>>({});
const linkTarget = ref<Record<string, string>>({});
const step = ref<1 | 2 | 3>(1);
const concept = ref<string>("");
const appearance = ref<string>("");
const personality = ref<string>("");
const race = ref<string>("human");
const klass = ref<string>("fighter");
const level = ref<number>(1);
const homeId = ref<string>("");
const places = ref<{ id: string; name: string }[]>([]);
const createdId = ref<string>("");

async function face(member: PartyMemberView): Promise<string> {
  if (faces.value[member.id]) {
    return faces.value[member.id];
  }
  const assetId = member.character_id ? portraits.value[member.character_id] : undefined;
  const src = assetId
    ? await assetUrl(assetId, worldId.value, headers.value, member.name).catch(() =>
        portraitFor(member.character_id ?? member.id, member.name),
      )
    : await portraitFor(member.character_id ?? member.id, member.name);
  faces.value[member.id] = src;
  return src;
}

async function load(): Promise<void> {
  if (!worldId.value) {
    return;
  }
  try {
    const [party, cast, map, art] = await Promise.all([
      api.party(worldId.value, headers.value),
      api.characters(worldId.value, headers.value),
      api.map(worldId.value, headers.value),
      api.listAssets(worldId.value, "portrait", headers.value).catch(() => []),
    ]);
    const refs: Record<string, string> = {};
    for (const asset of art) {
      if (asset.subject_id && !(asset.subject_id in refs)) {
        refs[asset.subject_id] = asset.id;
      }
    }
    portraits.value = refs;
    characters.value = cast;
    places.value = (map.places ?? []).map((p) => ({ id: p.id, name: p.name }));
    if (!homeId.value && places.value.length > 0) {
      homeId.value = places.value[0].id;
    }
    for (const member of roster.value) {
      await face(member);
    }
  } catch (error) {
    fail("party load failed", error);
  }
}

function hpFrac(member: PartyMemberView): number {
  return (member.hp_current ?? 0) / (member.hp_max ?? 1);
}

async function linkMember(member: PartyMemberView): Promise<void> {
  const target = linkTarget.value[member.id];
  if (!target) {
    return;
  }
  try {
    await api.linkPartyMember(
      member.id,
      { world_id: worldId.value, character_id: target, expected_version: member.version },
      headers.value,
    );
    await load();
  } catch (error) {
    fail("link failed", error);
  }
}

async function createAdventurer(): Promise<void> {
  if (!concept.value.trim() || !homeId.value) {
    fail("creation failed", new Error("name your adventurer and pick a home"));
    return;
  }
  try {
    const character = await api.createCharacter(
      {
        world_id: worldId.value,
        name: concept.value.trim(),
        location_id: homeId.value,
        appearance: appearance.value.trim(),
        personality: personality.value.trim(),
      },
      headers.value,
    );
    createdId.value = character.id;
    const member = await api.beginParty(
      {
        world_id: worldId.value,
        name: concept.value.trim(),
        race: race.value,
        character_class: klass.value,
        level: level.value,
        character_id: character.id,
      },
      headers.value,
    );
    concept.value = "";
    appearance.value = "";
    personality.value = "";
    step.value = 1;
    await load();
    await api.selectRole(
      { world_id: worldId.value, role: "player", character_id: member.character_id ?? character.id },
      headers.value,
    );
    switchRole("player", member.character_id ?? character.id);
    await refresh();
    void router.push("/scene");
  } catch (error) {
    fail("creation failed", error);
  }
}

function savingState(member: PartyMemberView): string {
  return member.character_id ? "linked" : "unlinked";
}

onMounted(() => {
  void load();
});
watch(worldId, () => {
  void load();
});
watch(role, () => {
  void load();
});
</script>

<template>
  <main class="party">
    <section class="roster">
      <div v-for="m in roster" :key="m.id" class="pcard">
        <img :src="faces[m.id] ?? ''" :alt="m.name" />
        <div class="pbody">
          <div class="pname"><span>{{ m.name }}</span><span>Lv {{ m.level }}</span></div>
          <div class="bar hp"><i :style="{ width: `${Math.round(hpFrac(m) * 100)}%` }"></i></div>
          <div class="nums">HP {{ m.hp_current ?? "?" }}/{{ m.hp_max ?? "?" }} · {{ savingState(m) }}</div>
          <div v-if="(m.conditions ?? []).length > 0" class="conds">{{ (m.conditions ?? []).join(", ") }}</div>
          <div v-if="!m.character_id" class="linkrow">
            <select v-model="linkTarget[m.id]" aria-label="Link character">
              <option value="" disabled selected>link a character…</option>
              <option v-for="c in characters" :key="c.id" :value="c.id">{{ c.name }}</option>
            </select>
            <button type="button" @click="linkMember(m)">link</button>
          </div>
        </div>
      </div>
      <p v-if="roster.length === 0" class="dim">No adventurers yet. Create one below.</p>
    </section>
    <section class="creator" aria-label="Character creation">
      <h1>New adventurer</h1>
      <ol class="steps">
        <li :aria-current="step === 1">concept</li>
        <li :aria-current="step === 2">appearance</li>
        <li :aria-current="step === 3">review</li>
      </ol>
      <div v-if="step === 1">
        <label>name<input v-model="concept" placeholder="e.g. Lyra" /></label>
        <label>home
          <select v-model="homeId">
            <option v-for="p in places" :key="p.id" :value="p.id">{{ p.name }}</option>
          </select>
        </label>
        <button type="button" :disabled="!concept.trim()" @click="step = 2">next</button>
      </div>
      <div v-if="step === 2">
        <label>appearance<input v-model="appearance" placeholder="e.g. copper pixie cut" /></label>
        <label>personality<input v-model="personality" placeholder="e.g. bright and blunt" /></label>
        <label>race<input v-model="race" /></label>
        <label>class<input v-model="klass" /></label>
        <label>level<input v-model.number="level" type="number" min="1" max="20" /></label>
        <button type="button" @click="step = 1">back</button>
        <button type="button" @click="step = 3">review</button>
      </div>
      <div v-if="step === 3">
        <p><b>{{ concept }}</b> · {{ race }} {{ klass }}, level {{ level }}</p>
        <p class="dim">{{ appearance }} {{ personality }}</p>
        <button type="button" @click="step = 2">back</button>
        <button type="button" @click="createAdventurer">create and play</button>
      </div>
      <p v-if="createdId" class="dim">created {{ createdId.slice(0, 8) }}</p>
    </section>
  </main>
</template>

<style scoped>
.party { display: grid; grid-template-columns: minmax(0, 1fr) 340px; gap: 14px; max-width: 1200px; margin: 0 auto; padding: 14px; }
.roster { display: grid; grid-template-columns: repeat(auto-fill, minmax(220px, 1fr)); gap: 10px; align-content: start; }
.pcard { border: 1px solid var(--border-subtle); border-radius: 12px; overflow: hidden; background: var(--surface-panel); }
.pcard img { width: 100%; height: 140px; object-fit: cover; display: block; background: #e8e2d4; }
.pcard .pbody { padding: 8px 10px; font-size: 12px; }
.pcard .pname { display: flex; justify-content: space-between; font-weight: 700; font-size: 13px; }
.bar { height: 5px; border-radius: 3px; background: #e8e2d4; margin-top: 4px; overflow: hidden; }
.bar i { display: block; height: 100%; background: var(--status-danger); }
.nums { color: var(--text-secondary); font-size: 11px; margin-top: 2px; }
.conds { font-size: 12px; color: var(--accent-gold); margin-top: 2px; }
.linkrow { display: flex; gap: 6px; margin-top: 6px; }
.linkrow select { flex: 1; font: inherit; font-size: 12px; }
.linkrow button, .creator button { border: 1px solid var(--action-primary); background: none; color: var(--action-primary); border-radius: 8px; padding: 6px 12px; cursor: pointer; font: inherit; }
.creator { background: var(--surface-panel); border: 1px solid var(--border-subtle); border-radius: 12px; padding: 14px; align-self: start; }
.creator h1 { font-family: var(--font-title); font-size: 17px; margin: 0 0 8px; }
.creator .steps { display: flex; gap: 8px; list-style: none; padding: 0; font-size: 12px; color: var(--text-secondary); }
.creator .steps [aria-current="true"] { color: var(--action-primary); font-weight: 700; }
.creator label { display: flex; flex-direction: column; gap: 4px; font-size: 13px; margin: 8px 0; }
.creator input, .creator select { font: inherit; border: 1px solid var(--border-subtle); border-radius: 8px; padding: 7px; }
.creator button { margin: 6px 6px 0 0; }
.dim { color: var(--text-secondary); }
@media (max-width: 900px) { .party { grid-template-columns: 1fr; } }
</style>
