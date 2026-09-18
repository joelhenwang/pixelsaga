# P01 feedback log (v2 revisions applied)

## Adventure Journal

- Slim 44px topbar; base font 14px, narration 15px.
- Hero art 420px with title overlaid on a bottom scrim (translucent
  background, full-opacity text). Scene-ID meta line removed.
- Outcome line and "What does Wren attempt?" heading removed.
- Choice rows follow the reference: icon circle, title, subtitle,
  chevron, optional check chip.
- Composer is a 40px input with an inline send arrow; Enter submits.
- Sidebar: no "Party"/"Map" headings; party cards show portrait, name,
  level, HP/MP bars with numbers; thread list compact; map is a
  full-width rectangle pinned to the panel bottom with a View World link.

## World Observatory

- Tokens are portrait circles with a filled name plate and an action
  caption underneath. Selected state is a gold outline.
- Inspector is anchored 84px above the map column floor, clearing the
  composer; Escape or Close dismisses it.

## Carried forward (not prototype work)

- Per-turn scene art: generate a new image per turn, or use a small LLM
  to decide whether the scene changed enough to warrant one. Input to
  P04 (asset jobs need idempotency and cost caps) and P08.
- Sidebar density: revisit against real data widths in P02/P08.

## v3 revisions

- Journal icons use a centered white inner dot; send button embeds
  `send-message-icon.svg` (currentColor on teal).
- Hero is 480px: title card top-left, narration card bottom, both
  translucent dark so generated art cannot mask text.
- Observatory is full-bleed map with floating rounded toolbar,
  chronicle, and composer cards; collapse button removed.
- Chronicle entries carry typed icons: portrait for solo actions,
  portrait-type-portrait triples for interactions, highlighted cards
  for world events.
- Clicking an entry opens an 80%-viewport modal: 70% scene art,
  30% detail with speaker rows, View on map, Previous/Next, Esc
  to close. Fixture art stands in for per-event generation.
