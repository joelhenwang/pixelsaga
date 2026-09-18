# Settled design direction (post-P01, 18 September 2026)

Selected prototypes: `mocks/revamp/adventure-journal.html` (v3) and
`mocks/revamp/world-observatory.html` (v3). They supersede the
section 4 mockup descriptions in `IMPLEMENTATION_PLAN.md` where they
differ. Full feedback trail in `P01_FEEDBACK.md`.

## Adventure Journal

- Slim topbar (~44px), 14px base type, 15px narration.
- 480px hero: title card top-left, narration card bottom over the art.
  Both cards are translucent dark with full-opacity white text, so
  generated art cannot mask copy.
- Choice rows: teal circle with centered white inner dot, title,
  subtitle, chevron, optional check chip.
- Composer: 40px input with a 28px teal send square inside it; icon is
  `assets/images/send-message-icon.svg` inlined with white fill
  (SVG-via-`<img>` cannot inherit `currentColor` and renders black).
- Sidebar without headings: party cards (portrait, name, level, HP/MP
  bars with numbers), one compact thread, full-width map rectangle
  pinned to the panel bottom with a View World link.

## World Observatory

- Full-bleed map; toolbar, chronicle, and composer are floating
  rounded cards over it. No collapse-chronicle control.
- Tokens: portrait circle, filled name plate, action caption below.
  Gold outline when selected.
- Chronicle entries carry typed icons: solo portrait, triple
  (portrait, interaction glyph, portrait), highlighted card for world
  events.
- Clicking an entry opens an 80%-viewport modal: 70% scene art, 30%
  detail with speaker rows, View on map, Previous/Next, Esc/backdrop
  close. Fixture art stands in for per-event generation.

## Standing inputs to later packets

- Per-turn scene art (generate per turn or gate on an LLM
  change-check): P04 job idempotency plus cost caps, then P08.
- Terminology: `Next phase` for simulation advance, never `Next beat`.
- Queued is not executed; travelling tokens never claim arrival.
