<!-- Library (A07): worlds and characters side by side, editors with
  dirty guards, revision saves, duplicate and archive. Follows the
  approved split mock. -->
<script setup lang="ts">
import { onMounted, ref } from "vue";
import { useRoute } from "vue-router";
import type { PresetDetail, PresetSummary } from "@gen";
import { api } from "../api";
import { fail, headers } from "../store";

const worlds = ref<PresetSummary[]>([]);
const characters = ref<PresetSummary[]>([]);
const selected = ref<PresetDetail | null>(null);
const name = ref("");
const dirty = ref(false);
const savedNote = ref("");

async function load(): Promise<void> {
  try {
    const all = await api.listPresets(headers.value);
    worlds.value = all.filter((p) => p.kind === "world");
    characters.value = all.filter((p) => p.kind === "character");
  } catch (error) {
    fail("library unavailable", error);
  }
}

async function select(id: string): Promise<void> {
  if (dirty.value && !window.confirm("Discard unsaved edits to switch presets?")) return;
  try {
    selected.value = await api.readPreset(id, headers.value);
    name.value = selected.value.name;
    dirty.value = false;
    savedNote.value = "";
  } catch (error) {
    fail("preset unavailable", error);
  }
}

async function save(): Promise<void> {
  if (!selected.value) return;
  try {
    if (selected.value.readonly) {
      fail("preset is read-only", new Error("duplicate a built-in before editing"));
      return;
    }
    const base = selected.value.revision ?? {};
    const payload = { ...base, name: name.value };
    selected.value = await api.addPresetRevision(
      selected.value.id,
      { payload, expected_version: selected.value.version },
      headers.value,
    );
    name.value = selected.value.name;
    dirty.value = false;
    savedNote.value = `Saved as rev ${selected.value.current_revision}. Pinned stories are unchanged.`;
    await load();
  } catch (error) {
    fail("save failed", error);
  }
}

async function duplicate(id: string): Promise<void> {
  try {
    selected.value = await api.duplicatePreset(id, headers.value);
    name.value = selected.value.name;
    dirty.value = false;
    await load();
  } catch (error) {
    fail("duplicate failed", error);
  }
}

async function toggleArchive(preset: PresetSummary): Promise<void> {
  try {
    if (preset.archived) {
      await api.unarchivePreset(preset.id, preset.version, headers.value);
    } else {
      await api.archivePreset(preset.id, preset.version, headers.value);
    }
    await load();
  } catch (error) {
    fail("archive failed", error);
  }
}

const route = useRoute();

onMounted(() => {
  void load().then(() => {
    const category = route.query.category;
    if (category === "style-packs" || category === "templates") {
      document.querySelector("details.more")?.setAttribute("open", "");
      document.querySelector("details.more")?.scrollIntoView();
    }
  });
});
</script>
<template>
  <main class="page">
    <h1>Library</h1>
    <div class="split">
      <section aria-label="World presets">
        <h2>Worlds</h2>
        <div class="cards">
          <button
            v-for="w in worlds" :key="w.id" type="button" class="preset"
            :aria-pressed="selected?.id === w.id" @click="select(w.id)"
          ><b>{{ w.name }}</b><span>rev {{ w.current_revision }}{{ w.readonly ? " · built-in" : "" }}</span></button>
        </div>
      </section>
      <section aria-label="Character presets">
        <h2>Characters</h2>
        <div class="cards">
          <button
            v-for="c in characters" :key="c.id" type="button" class="preset"
            :aria-pressed="selected?.id === c.id" @click="select(c.id)"
          ><b>{{ c.name }}</b><span>rev {{ c.current_revision }}{{ c.readonly ? " · built-in" : "" }}</span></button>
        </div>
      </section>
    </div>
    <section v-if="selected" class="panel" aria-label="Preset editor">
      <h2>Edit &middot; {{ selected.name }}</h2>
      <p class="dirty" v-if="dirty">Unsaved changes (will become a new revision).</p>
      <p class="dirty" v-if="savedNote">{{ savedNote }}</p>
      <label>Display name
        <input type="text" v-model="name" @input="dirty = name !== selected.name" />
      </label>
      <div class="row">
        <button type="button" :disabled="!dirty" @click="save">Save revision</button>
        <button type="button" @click="duplicate(selected.id)">Duplicate</button>
        <button
          type="button"
          @click="toggleArchive({ ...selected, archived: selected.archived_at !== null })"
        >{{ selected.archived_at ? "Unarchive" : "Archive" }}</button>
      </div>
      <p class="sub">Built-ins are read-only: duplicate before editing.</p>
    </section>
  </main>
</template>
