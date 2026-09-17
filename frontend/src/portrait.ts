// Portrait seam (Stage 3 image slice, generation in Stage 4).
//
// Async cache-reading contract: `portraitFor` resolves an SVG data
// URI for an asset id plus display name, cached per pair. Today the
// cache is memory-only and the source is the deterministic fixture
// below (seeded by id AND name); Stage 4 generation plugs into the
// fetch step without touching callers. Stable across renders and
// clients with zero network.
import pack from "../../content/visual-styles/pixel-saga-v1.json";

const GRID = 16;

function fnv1a(text: string): number {
  let hash = 0x811c9dc5;
  for (let i = 0; i < text.length; i++) {
    hash ^= text.charCodeAt(i);
    hash = Math.imul(hash, 0x01000193);
  }
  return hash >>> 0;
}

function pick<T>(rand: () => number, items: readonly T[]): T {
  return items[Math.floor(rand() * items.length)];
}

function mulberry(seed: number): () => number {
  let state = seed >>> 0;
  return () => {
    state |= 0;
    state = (state + 0x6d2b79f5) | 0;
    let t = Math.imul(state ^ (state >>> 15), 1 | state);
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

const portraitCache = new Map<string, string>();

export function clearPortraitCache(): void {
  portraitCache.clear();
}

export async function portraitFor(id: string, name?: string): Promise<string> {
  const key = `${id}:${name ?? ""}`;
  const cached = portraitCache.get(key);
  if (cached !== undefined) {
    return cached;
  }
  const uri = renderFixture(id, name ?? "");
  portraitCache.set(key, uri);
  return uri;
}

function renderFixture(id: string, name: string): string {
  const palette = pack.palette;
  const rand = mulberry(fnv1a(`${id}:${name}`));
  const skin = pick(rand, palette.skin);
  const hair = pick(rand, palette.hair);
  const eyes = pick(rand, palette.eyes);
  const vest = pick(rand, palette.vest);
  const blush = palette.blush;
  const wide = rand() < 0.4;
  const long = rand() < 0.35;
  const fringe = rand() < 0.5;
  const blushed = rand() < 0.5;

  // Cells keyed `${x},${y}`; mirrored writes keep faces symmetric.
  const cells: Record<string, string> = {};
  const px = (x: number, y: number, color: string): void => {
    cells[`${x},${y}`] = color;
    cells[`${GRID - 1 - x},${y}`] = color;
  };

  const left = wide ? 2 : 3;
  const right = wide ? 5 : 4; // half-width; mirrored for the other side
  for (let y = 3; y <= 10; y++) {
    for (let x = left; x <= right; x++) {
      px(x, y, skin);
    }
  }
  // Hair cap and fringe.
  for (let x = left - 1; x <= right + 1; x++) {
    px(x, 2, hair);
    if (fringe && x % 2 === 0) {
      px(x, 3, hair);
    }
  }
  // Hair sides; long styles fall past the chin.
  const sideBottom = long ? 13 : 9;
  for (let y = 4; y <= sideBottom; y++) {
    px(left - 1, y, hair);
  }
  // Eyes, blush, mouth.
  px(right - 1, 7, eyes);
  px(right - 1, 8, eyes);
  if (blushed) {
    px(left, 9, blush);
  }
  px(right, 10, "#7a4a3a");
  // Vest with a collar accent.
  for (let y = 11; y <= 15; y++) {
    for (let x = 1; x <= 6; x++) {
      px(x, y, y === 11 && x >= 3 ? skin : vest);
    }
  }

  let body = "";
  for (const key of Object.keys(cells)) {
    const [x, y] = key.split(",").map(Number);
    body += `<rect x="${x}" y="${y}" width="1.02" height="1.02" fill="${cells[key]}"/>`;
  }
  const svg =
    `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 16 16" shape-rendering="crispEdges">` +
    `<rect width="16" height="16" fill="#101018"/>${body}</svg>`;
  return `data:image/svg+xml;utf8,${encodeURIComponent(svg)}`;
}
