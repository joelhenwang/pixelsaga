// Generates party-builder vectors from the monolith's inline script.
// Rerun after any monolith change:
//   node backend/scripts/gen_dnd_party_vectors.mjs
// Extracts the pure builder functions (tables + dndFirstSubclass +
// dndSpellLimits + dndAutoSpells + dndAutoSheet) from perchance-ver/
// index.html by source markers and evals them with a stubbed window.
import { readFileSync, writeFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const root = join(dirname(fileURLToPath(import.meta.url)), "..", "..");
const html = readFileSync(join(root, "perchance-ver", "index.html"), "utf8");
const engineSrc = readFileSync(join(root, "perchance-ver", "dnd.js"), "utf8");
globalThis.window = undefined;
eval(engineSrc);

const start = html.indexOf("const DND_STAT_ARRAY");
const end = html.indexOf("function dndSpellListData");
if (start === -1 || end === -1 || end < start) throw new Error("builder markers moved");
const builderSrc = html.slice(start, end);
const promptStart = html.indexOf("function buildDndPartyPrompt");
const promptEnd = html.indexOf("// The scenario used for D&D Mode");
if (promptStart === -1 || promptEnd === -1) throw new Error("prompt markers moved");
const promptSrc = html.slice(promptStart, promptEnd);
const windowStub = { PixelDnd: globalThis.PixelDnd };
globalThis.window = windowStub;
eval(builderSrc + promptSrc + ";globalThis.__dnd = { DND_STAT_ARRAY, DND_ABILITY_PRIORITY, DND_AUTO_WEAPONS, DND_AUTO_ARMOR, DND_MAX_PARTY_SIZE, dndSpellLimits, dndAutoSpells, dndAutoSheet, buildDndPartyPrompt, buildDndRulesText };");
const { DND_STAT_ARRAY, DND_ABILITY_PRIORITY, DND_AUTO_WEAPONS, DND_AUTO_ARMOR, DND_MAX_PARTY_SIZE, dndSpellLimits, dndAutoSpells, dndAutoSheet, buildDndPartyPrompt, buildDndRulesText } = globalThis.__dnd;
function loadData() {
  const payload = {};
  for (const name of globalThis.PixelDnd.DATA_FILES) {
    payload[name] = JSON.parse(
      readFileSync(join(root, "perchance-ver", "dnd-data", `${name}.json`), "utf8"),
    );
  }
  return globalThis.PixelDnd.buildData(payload);
}

const data = loadData();
const V = { tables: {}, limits: {}, autoSpells: {}, autoSheet: {}, partyPrompt: '', rulesText: '' };

V.tables.statArray = DND_STAT_ARRAY;
V.tables.priorities = DND_ABILITY_PRIORITY;
V.tables.autoWeapons = DND_AUTO_WEAPONS;
V.tables.autoArmor = DND_AUTO_ARMOR;
V.tables.maxParty = DND_MAX_PARTY_SIZE;

const baseStats = { str: 10, dex: 14, con: 12, int: 10, wis: 10, cha: 8 };
for (const [cls, level] of [["wizard", 1], ["wizard", 5], ["cleric", 3], ["fighter", 3], ["bard", 2]]) {
  V.limits[`${cls}${level}`] = dndSpellLimits(data, cls, level, baseStats);
}
for (const [cls, level] of [["wizard", 5], ["cleric", 3], ["bard", 2], ["sorcerer", 4]]) {
  V.autoSpells[`${cls}${level}`] = dndAutoSpells(data, cls, level, baseStats);
}
globalThis.state = { dnd: { active: true, party: [] } };
for (const [name, race, cls, level] of [
  ["Lyra", "elf", "ranger", 3],
  ["Borin", "dwarf", "fighter", 1],
  ["Elara", "human", "wizard", 5],
  ["Thrak", "half-orc", "barbarian", 2],
  ["Mira", "halfling", "cleric", 4],
]) {
  V.autoSheet[`${name}-${cls}${level}`] = dndAutoSheet(name, race, cls, level, data);
}

globalThis.state.dnd.data = data;
globalThis.state.dnd.party = Object.values(V.autoSheet).slice(0, 2);
V.partyPrompt = buildDndPartyPrompt();
V.rulesText = buildDndRulesText();
writeFileSync(
  join(root, "backend", "tests", "fixtures", "dnd_party_vectors.json"),
  JSON.stringify(V, null, 1) + "\n",
);
console.log(`wrote ${Object.keys(V.autoSheet).length} sheets`);
