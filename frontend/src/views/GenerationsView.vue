<script setup lang="ts">
import { onMounted, ref, watch } from "vue";
import type { EraView, MacroRunView, TimelineEntry } from "@gen";
import { api } from "../api";
import { fail, headers, role, worldId } from "../store";

const YEAR_PHASES = 3600;

const runs = ref<MacroRunView[]>([]);
const focusRows = ref<{ slot: string; version: number; to: string; at: number; reason: string }[]>([]);
const endingRows = ref<{ kind: string; met: boolean; detail: string }[]>([]);
const eras = ref<EraView[]>([]);
const sources = ref<TimelineEntry[]>([]);
const selectedRun = ref<MacroRunView | null>(null);
const selectedEra = ref<EraView | null>(null);
const resolution = ref("week");
const day = ref(1);
const busy = ref(false);

function years(): { n: number; start: number; end: number }[] {
  if (runs.value.length === 0) return [];
  const maxEnd = Math.max(...runs.value.map((r) => r.end_absolute));
  const out: { n: number; start: number; end: number }[] = [];
  for (let s = 0; s < maxEnd; s += YEAR_PHASES) {
    out.push({ n: s / YEAR_PHASES + 1, start: s, end: Math.min(s + YEAR_PHASES, maxEnd) });
  }
  return out;
}

function runsIn(start: number, end: number): MacroRunView[] {
  return runs.value.filter((r) => r.start_absolute >= start && r.start_absolute < end);
}

async function load(): Promise<void> {
  if (!worldId.value) return;
  try {
    const [runRes, focusRes, endRes] = await Promise.all([
      api.macroRuns(worldId.value, headers.value),
      api.focus(worldId.value, headers.value),
      api.endings(worldId.value, headers.value),
    ]);
    runs.value = runRes.runs ?? [];
    focusRows.value = (focusRes.assignments ?? []).map((a) => ({
      slot: a.slot, version: a.version, to: a.to_name, at: a.effective_absolute, reason: a.reason,
    }));
    endingRows.value = (endRes.endings ?? []).map((e) => ({
      kind: e.kind, met: e.satisfied, detail: e.detail,
    }));
    selectedRun.value = null;
    selectedEra.value = null;
    sources.value = [];
    const ys = years();
    if (ys.length > 0) {
      const eraRes = await api.eras(worldId.value, ys[0].start, ys[ys.length - 1].end, headers.value);
      eras.value = eraRes.eras ?? [];
    }
  } catch (error) {
    fail("generations load failed", error);
  }
}

async function drill(era: EraView): Promise<void> {
  selectedEra.value = era;
  sources.value = [];
  try {
    const want = new Set(era.source_ids);
    let after = 0;
    for (let page = 0; page < 8 && want.size > 0; page++) {
      const pageRes = await api.timeline(worldId.value, headers.value, after, 100);
      const entries = pageRes.entries ?? [];
      if (entries.length === 0) break;
      for (const e of entries) {
        if (want.has(e.event_id)) {
          sources.value.push(e);
          want.delete(e.event_id);
        }
      }
      after = entries[entries.length - 1].sequence;
      if (entries.length < 100) break;
    }
  } catch (error) {
    fail("source drill failed", error);
  }
}

async function advance(): Promise<void> {
  if (role.value !== "watcher" || busy.value) return;
  busy.value = true;
  try {
    await api.advanceMacro(worldId.value, day.value, resolution.value, headers.value);
    await load();
  } catch (error) {
    fail("macro advance failed", error);
  } finally {
    busy.value = false;
  }
}

onMounted(() => {
  void load();
});
watch(worldId, () => {
  void load();
});
</script>

<template>
  <main class="stage" aria-live="polite">
    <h1>generations</h1>
    <div class="gen-ctrl">
      <span class="dim">advance</span>
      <button
        v-for="r in ['day', 'week', 'month', 'year']"
        :key="r"
        :aria-pressed="resolution === r"
        @click="resolution = r"
      >{{ r }}</button>
      <label class="dim">day <input v-model.number="day" type="number" min="1" /></label>
      <button :disabled="role !== 'watcher' || busy" @click="advance">run</button>
      <span v-if="role !== 'watcher'" class="dim">watcher only</span>
    </div>

    <div v-for="y in years()" :key="y.n" class="band">
      <div class="dim bandhead">year {{ y.n }} · phases {{ y.start }} to {{ y.end }}</div>
      <div class="track">
        <div
          v-for="r in runsIn(y.start, y.end)"
          :key="r.run_id"
          class="seg"
          :class="{ inter: r.state === 'interrupted', sel: selectedRun?.run_id === r.run_id }"
          :style="{ left: ((r.start_absolute - y.start) / (y.end - y.start) * 100) + '%', width: Math.max(1.5, (r.end_absolute - r.start_absolute) / (y.end - y.start) * 100) + '%' }"
          :title="`${r.resolution} ${r.start_absolute} to ${r.end_absolute} · ${r.state}`"
          @click="selectedRun = r"
        />
      </div>
    </div>
    <p v-if="runs.length === 0" class="dim">No macro runs yet. Advance a quiet span.</p>

    <div class="gen-grid">
      <div>
        <h1>run detail</h1>
        <div v-if="selectedRun">
          <p><b>{{ selectedRun.resolution }}</b> {{ selectedRun.start_absolute }} to {{ selectedRun.end_absolute }} · {{ selectedRun.state }}</p>
          <table v-if="(selectedRun.effects ?? []).length > 0">
            <tr><th>kind</th><th>detail</th></tr>
            <tr v-for="e in selectedRun.effects ?? []" :key="e.kind + e.detail">
              <td>{{ e.kind }}</td><td class="dim">{{ e.detail }}</td>
            </tr>
          </table>
          <p v-for="i in selectedRun.interruptions ?? []" :key="i.at_absolute" class="warn">
            break at {{ i.at_absolute }} · {{ i.reason }} · {{ i.detail }}
          </p>
        </div>
        <p v-else class="dim">Select a segment.</p>
      </div>
      <div>
        <h1>era digests</h1>
        <table v-if="eras.length > 0">
          <tr><th>span</th><th>digest</th><th>v</th></tr>
          <tr v-for="e in eras" :key="e.era_id" class="ev" @click="drill(e)">
            <td class="dim">{{ e.start_absolute }} to {{ e.end_absolute }}</td>
            <td>{{ e.text }}</td>
            <td class="dim">{{ e.version }}</td>
          </tr>
        </table>
        <p v-else class="dim">No digests for this span.</p>
        <div v-if="selectedEra">
          <h1>source events · {{ sources.length }} of {{ (selectedEra.source_ids ?? []).length }}</h1>
          <table v-if="sources.length > 0">
            <tr><th>seq</th><th>type</th><th>phase</th><th>detail</th></tr>
            <tr v-for="s in sources" :key="s.event_id">
              <td class="dim">{{ s.sequence }}</td><td>{{ s.event_type }}</td>
              <td class="dim">{{ s.absolute_index }}</td><td>{{ s.snippet ?? "—" }}</td>
            </tr>
          </table>
        </div>
      </div>
    </div>

    <div class="gen-grid">
      <div>
        <h1>focus chain</h1>
        <table v-if="focusRows.length > 0">
          <tr><th>slot</th><th>v</th><th>holder</th><th>from phase</th><th>reason</th></tr>
          <tr v-for="f in focusRows" :key="f.slot + f.version">
            <td>{{ f.slot }}</td><td class="dim">{{ f.version }}</td><td>{{ f.to }}</td>
            <td class="dim">{{ f.at }}</td><td class="dim">{{ f.reason }}</td>
          </tr>
        </table>
        <p v-else class="dim">No focus assignments.</p>
      </div>
      <div>
        <h1>ending evidence</h1>
        <table v-if="endingRows.length > 0">
          <tr><th>kind</th><th>met</th><th>detail</th></tr>
          <tr v-for="e in endingRows" :key="e.kind">
            <td>{{ e.kind }}</td><td :class="e.met ? 'ok' : 'dim'">{{ e.met ? "yes" : "no" }}</td>
            <td class="dim">{{ e.detail }}</td>
          </tr>
        </table>
        <p v-else class="dim">No ending evaluations.</p>
      </div>
    </div>
  </main>
</template>

<style scoped>
.gen-ctrl { display: flex; gap: 8px; align-items: center; flex-wrap: wrap; margin-bottom: 8px; }
.gen-ctrl button[aria-pressed="true"] { border-color: var(--acc); color: var(--acc); }
.gen-ctrl input { width: 72px; background: none; border: 1px solid var(--line); color: var(--fg); padding: 3px 6px; font: inherit; }
.band { margin-top: 10px; }
.bandhead { font-size: 12px; margin-bottom: 2px; }
.track { position: relative; height: 26px; border-bottom: 1px solid var(--line); }
.seg { position: absolute; top: 4px; height: 18px; background: #1d3a1d; border-left: 2px solid var(--acc); cursor: pointer; }
.seg.inter { background: #3a2f16; border-left-color: #e0a23c; }
.seg.sel { outline: 1px solid var(--fg); }
.gen-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 16px; margin-top: 12px; }
.ev { cursor: pointer; }
.warn { color: #e0a23c; }
.ok { color: var(--acc); }
</style>
