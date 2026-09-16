<script setup lang="ts">
import { onMounted, ref } from "vue";
import type { PartyMemberView } from "@gen";
import { api } from "../api";
import Portrait from "../Portrait.vue";
import { fail, headers, worldId } from "../store";

const roster = ref<PartyMemberView[]>([]);
const beginName = ref<string>("");
const beginRace = ref<string>("human");
const beginClass = ref<string>("fighter");
const beginLevel = ref<number>(1);

async function loadParty(): Promise<void> {
  if (!worldId.value) {
    return;
  }
  try {
    const party = await api.party(worldId.value, headers.value);
    roster.value = party.members ?? [];
  } catch (error) {
    fail("party load failed", error);
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
    fail("begin failed", new Error("name your adventurer first"));
    return;
  }
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
    await loadParty();
  } catch (error) {
    fail("begin failed", error);
  }
}

onMounted(() => {
  void loadParty();
});
</script>

<template>
  <main class="stage" aria-live="polite">
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
  </main>
</template>
