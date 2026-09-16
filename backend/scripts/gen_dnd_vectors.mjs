// Generates backend/tests/fixtures/dnd_vectors.json from the canonical
// perchance-ver/dnd.js engine. Rerun after any monolith change:
//   node backend/scripts/gen_dnd_vectors.mjs
// Every roll uses a scripted float sequence so the Python port can replay
// the exact algorithm (1 + floor(r * sides)) without matching Math.random.
import { readFileSync, writeFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const root = join(dirname(fileURLToPath(import.meta.url)), "..", "..");
const engineSrc = readFileSync(join(root, "perchance-ver", "dnd.js"), "utf8");
globalThis.window = undefined;
eval(engineSrc);
const Dnd = globalThis.PixelDnd;

function loadData() {
  const payload = {};
  for (const name of Dnd.DATA_FILES) {
    payload[name] = JSON.parse(
      readFileSync(join(root, "perchance-ver", "dnd-data", `${name}.json`), "utf8"),
    );
  }
  return Dnd.buildData(payload);
}

// Scripted rng: cycles seq so multi-die rolls stay deterministic.
function scripted(seq) {
  let i = 0;
  return () => seq[i++ % seq.length];
}

const data = loadData();
const V = {};

// ---- dice ----
V.parseDice = {};
for (const s of ["2d6+3", "d20", "1d8-2", "3d10", "d6", "0d6", "2d0", "abc", "", " 4d6 + 1 ", "2D8+5", "10d12-4"]) {
  V.parseDice[s] = Dnd.parseDice(s);
}
V.rollDice = {
  "2d6+3@[0.0,0.5,0.999]": Dnd.rollDice("2d6+3", scripted([0.0, 0.5])),
  "1d20@[0.0]": Dnd.rollDice("1d20", scripted([0.0])),
  "1d20@[0.9999]": Dnd.rollDice("1d20", scripted([0.9999])),
  "bogus": Dnd.rollDice("zzz", scripted([0.5])),
};
V.averageDice = { "2d6+3": Dnd.averageDice("2d6+3"), "1d12": Dnd.averageDice("1d12"), bogus: Dnd.averageDice("zzz") };

// ---- abilities ----
V.abilityMod = Object.fromEntries([1, 8, 9, 10, 11, 12, 14, 15, 20, 30].map((s) => [s, Dnd.abilityMod(s)]));
V.profBonus = Object.fromEntries([0, 1, 4, 5, 8, 9, 12, 13, 16, 17, 20].map((l) => [l, Dnd.profBonus(l)]));
V.fmtMod = Object.fromEntries([-2, 0, 3].map((n) => [n, Dnd.fmtMod(n)]));
V.slugify = {
  "Chain Mail": Dnd.slugify("Chain Mail"),
  "Acid Arrow!": Dnd.slugify("Acid Arrow!"),
  "": Dnd.slugify(""),
};
// ---- lookup ----
V.findEntry = {};
for (const [table, query] of [
  ["monsters", "Goblin"], ["monsters", "Goblins"], ["monsters", "zzz-nope"],
  ["weapons", "longsword"], ["weapons", "Long Sword"], ["armor", "Chain Mail"],
  ["spells", "fireball"], ["spells", "Fire Ball"], ["conditions", "POISONED"],
  ["races", "dragonborn"], ["classes", "Fighter"],
]) {
  const hit = Dnd.findEntry(data[table], query);
  V.findEntry[`${table}:${query}`] = hit ? { index: hit.index, name: hit.entry.name } : null;
}

// ---- xp / encounters ----
V.xpForLevel = Object.fromEntries([1, 5, 20, 21, 0].map((l) => [l, Dnd.xpForLevel(l)]));
V.levelFromXp = Object.fromEntries([0, 299, 300, 6499, 6500, 355000, 999999].map((x) => [x, Dnd.levelFromXp(x)]));
V.xpForNextLevel = {
  L1: Dnd.xpForNextLevel({ level: 1, xp: 0 }),
  L1partial: Dnd.xpForNextLevel({ level: 1, xp: 100 }),
  L20: Dnd.xpForNextLevel({ level: 20, xp: 400000 }),
};
V.encounterXp = Dnd.encounterXp(
  [{ index: "goblin", count: 3 }, { index: "bugbear", count: 1 }],
  data,
);
const party = [
  Dnd.createSheet({ name: "A", class: "fighter", level: 3 }),
  Dnd.createSheet({ name: "B", class: "wizard", level: 3 }),
];
V.encounterDifficulty = Dnd.encounterDifficulty(party, [{ index: "goblin", count: 3 }], data);

// ---- sheets ----
const fighter = Dnd.createSheet({
  name: "Borin", race: "dwarf", class: "fighter", level: 3,
  stats: { str: 16, dex: 12, con: 15, int: 8, wis: 11, cha: 10 },
  armor: "Chain Mail", shield: true, weapons: ["longsword"], xp: 900,
});
const wizard = Dnd.createSheet({
  name: "Elara", race: "elf", class: "wizard", level: 5,
  stats: { str: 8, dex: 14, con: 13, int: 17, wis: 12, cha: 10 },
  armor: null, weapons: ["dagger"], spells: ["fire-bolt", "fireball"], xp: 6500,
});
V.sheetDefaults = Dnd.createSheet({});
V.sheetMod = { str16: Dnd.sheetMod(fighter, "str"), int8: Dnd.sheetMod(fighter, "int") };
V.sheetProf = { L3: Dnd.sheetProf(fighter), L5: Dnd.sheetProf(wizard) };
V.spellcasting = {
  fighter: Dnd.spellcastingAbility(data, fighter),
  wizard: Dnd.spellcastingAbility(data, wizard),
  dc: Dnd.spellDC(data, wizard),
  atk: Dnd.spellAttackBonus(data, wizard),
  fighterDc: Dnd.spellDC(data, fighter),
};
V.weaponAttack = {
  longsword: Dnd.weaponAttackBonus(data, fighter, data.weapons["longsword"]),
  shortbowRanged: Dnd.weaponAttackBonus(data, fighter, data.weapons["shortbow"]),
  rapierFinesse: Dnd.weaponAttackBonus(data, wizard, data.weapons["rapier"]),
};
const dexHigh = Dnd.createSheet({ stats: { str: 10, dex: 18, con: 10, int: 10, wis: 10, cha: 10 }, armor: "zzz-nope" });
V.armorAC = {
  chainShield: Dnd.armorAC(data, fighter),
  unarmored: Dnd.armorAC(data, wizard),
  bogusArmor: Dnd.armorAC(data, Dnd.createSheet({ armor: "zzz-nope" })),
  missingArmorHighDex: Dnd.armorAC(data, dexHigh),
};
V.maxHp = { fighter3: Dnd.maxHp(data, fighter), wizard5: Dnd.maxHp(data, wizard), preset: Dnd.maxHp(data, Dnd.createSheet({ hp: { current: 5, max: 44 } })) };
const hpSheet = Dnd.createSheet({});
Dnd.ensureHp(hpSheet, 18);
V.ensureHp = hpSheet.hp;
V.classSpells = Dnd.classSpellList(data, wizard).slice(0, 5);
V.knownSpells = Dnd.knownSpells(data, wizard);
V.raceBonuses = { dwarf: Dnd.raceAbilityBonuses(data, "dwarf"), bogus: Dnd.raceAbilityBonuses(data, "zzz") };
V.sheetSummary = { fighter: Dnd.buildSheetSummary(fighter, data), wizard: Dnd.buildSheetSummary(wizard, data) };

// ---- spells ----
V.resolveSpell = {
  fireball3: Dnd.resolveSpell("fireball", wizard, data, 3),
  fireball5: Dnd.resolveSpell("fireball", wizard, data, 5),
  fireBolt1: Dnd.resolveSpell("fire-bolt", Dnd.createSheet({ class: "wizard", level: 1 }), data),
  fireBolt11: Dnd.resolveSpell("fire-bolt", Dnd.createSheet({ class: "wizard", level: 11 }), data),
  bogus: Dnd.resolveSpell("zzz-nope", wizard, data),
};
const cleric = Dnd.createSheet({ name: "Mira", class: "cleric", level: 3, stats: { str: 10, dex: 10, con: 12, int: 10, wis: 16, cha: 10 } });
V.resolveSpell.cureWounds = Dnd.resolveSpell("cure-wounds", cleric, data, 1);
V.describeSpell = {
  fireball3: Dnd.describeSpell(V.resolveSpell.fireball3),
  fireBolt1: Dnd.describeSpell(V.resolveSpell.fireBolt1),
  cureWounds: Dnd.describeSpell(V.resolveSpell.cureWounds),
  none: Dnd.describeSpell(null),
};

// ---- monsters ----
V.monsterSheet = Dnd.createMonsterSheet("goblin", data);
V.monsterSheetBogus = Dnd.createMonsterSheet("zzz-nope", data);
V.monsterSummary = { goblin: Dnd.monsterSummary("goblin", data), aboleth: Dnd.monsterSummary("aboleth", data), bogus: Dnd.monsterSummary("zzz", data) };

// ---- combat (scripted rng; crit damage path crashes in JS, excluded) ----
V.rollAttack = {
  miss: Dnd.rollAttack(5, 18, scripted([0.2])),
  hit: Dnd.rollAttack(5, 12, scripted([0.5])),
  nat20: Dnd.rollAttack(0, 30, scripted([0.9999])),
  nat1: Dnd.rollAttack(10, 5, scripted([0.0])),
};
V.rollSave = {
  fail: Dnd.rollSave(2, 15, scripted([0.2])),
  pass: Dnd.rollSave(5, 12, scripted([0.5])),
  nat20: Dnd.rollSave(0, 30, scripted([0.9999])),
};
V.applyDamage = (() => {
  const t = { hp: { current: 20, max: 20 } };
  const dealt = Dnd.applyDamage(t, 7.6);
  const overkill = Dnd.applyDamage(t, 99);
  return { dealt, overkill, current: t.hp.current, noTarget: Dnd.applyDamage(null, 5) };
})();
V.heal = (() => {
  const t = { hp: { current: 5, max: 20 } };
  const got = Dnd.heal(t, 8.4);
  const capped = Dnd.heal(t, 99);
  return { got, capped, current: t.hp.current, noTarget: Dnd.heal(null, 5) };
})();

// ---- leveling ----
V.levelUp = {
  fighter2: Dnd.levelUpPreview(Dnd.createSheet({ class: "fighter", level: 1 }), data),
  wizard4: Dnd.levelUpPreview(Dnd.createSheet({ class: "wizard", level: 3 }), data),
  maxed: Dnd.levelUpPreview(Dnd.createSheet({ class: "fighter", level: 20 }), data),
};

// ---- tag parsers ----
V.parseEncounter = {
  mixed: Dnd.parseEncounterTag("2x Goblin, 1x Bugbear", data),
  suffix: Dnd.parseEncounterTag("goblin x3; orc", data),
  words: Dnd.parseEncounterTag("3 goblins and 1 ogre", data),
  bogus: Dnd.parseEncounterTag("zzz-nope", data),
  empty: Dnd.parseEncounterTag("", data),
};
V.parseCast = {
  slotTarget: Dnd.parseCastTag("fireball at 3rd level on goblins", data),
  plain: Dnd.parseCastTag("cure wounds", data),
  bogus: Dnd.parseCastTag("zzz-nope", data),
  empty: Dnd.parseCastTag("  ", data),
};
V.parseAttack = {
  target: Dnd.parseAttackTag("longsword at goblin", data),
  plain: Dnd.parseAttackTag("dagger", data),
  bogus: Dnd.parseAttackTag("zzz-nope", data),
};
V.parseCondition = {
  full: Dnd.parseConditionTag("poisoned on goblin for 3 rounds", data),
  plain: Dnd.parseConditionTag("prone", data),
  bogus: Dnd.parseConditionTag("zzz-nope", data),
};

writeFileSync(
  join(root, "backend", "tests", "fixtures", "dnd_vectors.json"),
  JSON.stringify({ version: Dnd.version, vectors: V }, null, 1) + "\n",
);
console.log(`wrote ${Object.keys(V).length} vector groups`);
