# D&D 5e SRD Data (2014 ruleset)

Structured reference data for the D&D game mode. **Never shipped into prompts** —
loaded once at boot into `state.dnd` and looked up by the engine.

All content is the **official System Reference Document 5.1 (2014)**, released by
Wizards of the Coast under the OGL 1.0a (and later CC-BY-4.0). No PHB-only
content is included.

## Files

| File | Contents |
|---|---|
| `spells.json` | 319 spells: level, school, casting time, range, components, material, duration, concentration, ritual, attack type, save DC (type + success), area of effect, damage dice (`base`, `atSlotLevel`, `atCharacterLevel`), heal dice, caster classes, full description |
| `monsters.json` | 334 monsters: AC (+type), HP, hit dice, all 6 stats, precomputed save bonuses + skill bonuses (proficiency bonus from CR), CR + exact XP, speeds, senses, languages, resistances/immunities/vulnerabilities/condition immunities, special abilities, actions (attack bonus, DC, usage, damage dice+type), reactions, legendary actions |
| `classes.json` | 12 classes: hit die, saving throws, proficiencies (+ choices as text), spellcasting ability + info, starting equipment (+options), subclasses, full class spell list, and a `levels` array (1–20) with prof bonus, ability-score bonuses, features gained, and spell-slot table |
| `features.json` | 407 class/subclass features with descriptions |
| `subclasses.json` | 12 SRD subclasses (one per class): class, flavor, description, subclass spells |
| `skills.json` | 18 skills with governing ability |
| `weapons.json` | 37 weapons: category/range, damage dice+type, two-handed damage, range/throw range, properties (finesse, heavy, versatile...) |
| `armor.json` | 13 armor suits: category, AC base + dex bonus + max bonus, strength minimum, stealth disadvantage |
| `equipment.json` | 187 adventuring gear + tools: category, cost, weight |
| `magic-items.json` | 362 magic items: rarity, description, category |
| `races.json` | 9 races: speed, size, ability bonuses (+choices), languages, traits, subraces |
| `traits.json` | 38 racial traits with descriptions |
| `feats.json` | 1 feat (Grappler) — the SRD only includes Grappler as an example |
| `backgrounds.json` | 1 background (Acolyte) — the SRD only includes Acolyte as an example |
| `conditions.json` | 15 conditions with descriptions |
| `damage-types.json` | 13 damage types |
| `proficiencies.json` | 117 proficiency entries (armor/weapon/tool/skill/save names) |
| `xp.json` | Official CR → XP table (34 rows) |

## Format

Every file is a flat object keyed by the entry's slug (e.g. `spells.json["fireball"]`),
lowercase-hyphenated. Dice are plain strings (`"8d6"`, `"1d6+2"`) — roll them with
a `XdY+Z` parser. Spell damage at higher levels is in `damage.atSlotLevel`
(`{ "3": "8d6", "4": "9d6", ... }`); cantrips scale by character level in
`damage.atCharacterLevel`. Monster save/skill bonuses are **already computed**
(`saves.dex`, `skills.stealth`), so the engine never re-derives them.

## Sources & rebuild

Pulled from the **dnd5eapi.co** GraphQL endpoint (the `5e-bits/5e-srd-api` project)
on 2026-08-07. Monster save/skill bonuses use the API's own precomputed values
when present (they match the printed stat blocks, including WotC's errata'd
oddballs like the ancient red dragon's +16 Con save); when absent they are
derived as `stat mod + proficiency bonus`, where `PB = 2 + floor((CR-1)/4)` for
CR ≥ 1 else 2 (the official DMG progression: +2 at CR 1–4, +3 at 5–8, ...).
Monster `hit_dice` is the official full hit-points roll (`19d12+133`). The
CR→XP table is the official DMG table, verified against monster XP values.

The raw GraphQL pulls and processing scripts are in `scratch/srd/` (ephemeral —
not shipped). To rebuild: hit `https://www.dnd5eapi.co/graphql` with
`apollo-require-preflight: true` and re-run the per-domain queries (spells split
by level 0 vs 1–9 for the damage fields, monsters with inline fragments for the
AC/condition/proficiency unions, `equipments` with `IEquipment` + type fragments).

## License

SRD 5.1 © 2016 Wizards of the Coast LLC. Licensed under OGL 1.0a / CC-BY-4.0.
This file set is a data extraction of that SRD.

## Engine & status (2026-08-07)

The D&D engine is `src/dnd.js` (global `window.PixelDnd`). It is NOT a `<script>`
tag — it lazy-loads via `import('./src/dnd.js')` inside `getDndData()` the first
time D&D is enabled. (An extra blocking external `<script>` tag previously
tripped a perchance re-render race: its script processor does
`parent.insertBefore(newScript, oldScript)` and a detached trailing script has a
null parent, throwing `Cannot read properties of null (reading 'insertBefore')`.
The module loader touches no DOM, so it's invisible to that processor.) It is
PURE and DORMANT: nothing runs at load.
API: dice (`parseDice`/`rollDice`/`averageDice`), abilities (`abilityMod`,
`profBonus`), XP (`xpForLevel`/`levelFromXp`/`xpForNextLevel`), encounter
budgeting (`encounterXp`/`encounterDifficulty`), sheets (`createSheet`,
`maxHp`, `armorAC`, `spellDC`, `spellAttackBonus`, `weaponAttackBonus`,
`buildSheetSummary`), spell/monster resolution (`resolveSpell`,
`describeSpell`, `monsterSummary`, `createMonsterSheet`), combat
(`rollAttack`/`rollSave`/`applyDamage`/`heal`), leveling deltas
(`levelUpPreview`), and LLM tag parsers (`parseEncounterTag`/`parseCastTag`/
`parseAttackTag`/`parseConditionTag`). Data loading: `loadData(baseUrl)`
(defaults to `./src/dnd-data`) fetches all 18 files and caches the bundle;
`findEntry(map, str)` fuzzy-resolves names (hyphen/compact forms, plurals,
irregulars).

Integration in index.html is a dormant hook only: `state.dnd`
(`{enabled:false, active:false, data, party, combat}`), lazy `getDndData()`,
and `__debug.dndGetData`/`__debug.dndState` for testing. **Nothing ships
user-visible and nothing is gated yet** — the admin-gated "coming soon" card is
deliberately NOT built until the mode is assembled.

Status of these data files while the feature is under construction:
- `classes.json` was rebuilt 2026-08-07 to fix the API's duplicate class-level
  rows (the subclass-feature row carries `spellcasting:null`; the correct merge
  takes the base row's features/prof bonus and the row with spellcasting for
  slots). Verified: wizard L1 `[2]`, L3 `[4,2]`, L5 `[4,3,2]`, L20
  `[4,3,3,3,3,2,2,1,1]`; warlock L11 `[0,0,0,0,3]`; paladin L1 `[0]`, L2 `[2]`.
- `monsters.json` save/skill bonuses are the API's printed-stat-block values
  (e.g. adult red dragon saves dex+6/con+13/wis+7/cha+11, PB 6 for CR 17).

To ENABLE the mode (when we decide): move this whole folder to `src/dnd-data/`,
add the admin-gated entry point, and flip `state.dnd.enabled`. Until then the
files here in scratch/ are NOT served to the page and are ephemeral (a future
session may need to rebuild from the recipe above).
