# Settled direction: application pages (A01, 19 September 2026)

Selected mocks in `mocks/application-pages/` (v2 where noted). These supersede
the PNG concept descriptions where they differ.

## Home: variant A, reference-faithful (v2, approved with retouches)

- `home-a.html` (+ `a01-home-a.png`). `home-b.html` rejected.
- Left: Continue Story hero card, cover art with overlaid info card
  (CURRENT STORY eyebrow, title + setup entry, day/phase/place, synopsis)
  and a Continue Story button. No recent-stories footer strip.
- Right: "Begin a new tale" card (New Story + Quick Start: Ember Vale),
  then "Your Library" card with Open Library link, world preset rectangles
  and character profile rectangles (image over brief info).
- Shared shell: 44px topbar (slimmed per feedback), PixelSaga brand, main
  menu Home / New Story / Stories / Library / Settings, Help + local profile.

## Library: simultaneous split (approved)

- `library.html` (+ `a01-library.png`).
- Worlds left, Characters right, gold vertical divider, both visible at once.
  Rectangles carry image over brief info. Editor below with dirty guard and
  revision semantics. Style Packs and Templates in a disclosure row.

## Wizard, Stories, Settings: standing as built

- `new-story.html`: six steps, cast-before-mode, Player binding validation,
  Watch revealing Observer/Director/Deity, explicit draft save, stable review.
- `stories.html`: catalog cards, read-only setup modal (focus trap, Esc,
  backdrop close, focus restore), archive in the card menu only, legacy
  unknown-honest state.
- `settings.html`: seven-section rail, honest provider/image states,
  disabled-with-reason fields, cache scope boundaries.
- No specific changes requested; any later feedback revisits these files first.

## Standing inputs to implementation (A02+)

- Shell topbar 44px; serif titles, sans body; ivory/teal/gold tokens.
- No Vue components were edited for A01. Implementation follows this file.
