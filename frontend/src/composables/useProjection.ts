// Shared world-projection loading (P05).
//
// One presentation snapshot plus a chronicle window, keyed by world,
// role, and revision. Stale selections resolve into the void; callers
// own rendering and image resolution.
import { ref } from "vue";
import type { ChronicleEntry, PresentationResponse } from "@gen";
import { api } from "../api";
import { headers, session, worldId } from "../store";

export const presentation = ref<PresentationResponse | null>(null);
export const entries = ref<ChronicleEntry[]>([]);
export const cursor = ref<number>(0);
export const hasMore = ref<boolean>(false);
export const watermark = ref<number>(0);
export const revision = ref<number>(-1);

export async function loadProjection(fail: (message: string, error: unknown) => void): Promise<void> {
  const key = session();
  const wid = worldId.value;
  if (!wid) {
    return;
  }
  try {
    const snapshot = await api.presentation(wid, headers.value);
    if (key !== session()) {
      return;
    }
    presentation.value = snapshot;
    revision.value = snapshot.revision;
    const page = await api.chronicle(wid, 0, 20, headers.value);
    if (key !== session()) {
      return;
    }
    entries.value = page.entries ?? [];
    cursor.value = page.next_after;
    hasMore.value = page.has_more;
    watermark.value = page.watermark;
  } catch (error) {
    fail("world load failed", error);
  }
}

export async function loadOlder(fail: (message: string, error: unknown) => void): Promise<void> {
  const key = session();
  const wid = worldId.value;
  if (!wid || !hasMore.value) {
    return;
  }
  try {
    const page = await api.chronicle(wid, cursor.value, 20, headers.value);
    if (key !== session()) {
      return;
    }
    const known = new Set(entries.value.map((e) => e.event_id));
    for (const entry of page.entries ?? []) {
      if (!known.has(entry.event_id)) {
        entries.value.push(entry);
      }
    }
    cursor.value = page.next_after;
    hasMore.value = page.has_more;
    watermark.value = page.watermark;
  } catch (error) {
    fail("chronicle load failed", error);
  }
}

export async function checkNew(fail: (message: string, error: unknown) => void): Promise<number> {
  const key = session();
  const wid = worldId.value;
  if (!wid) {
    return 0;
  }
  try {
    const page = await api.chronicle(wid, watermark.value, 20, headers.value);
    if (key !== session()) {
      return 0;
    }
    const known = new Set(entries.value.map((e) => e.event_id));
    const fresh = (page.entries ?? []).filter((e) => !known.has(e.event_id));
    entries.value = [...fresh, ...entries.value];
    watermark.value = page.watermark;
    if (page.has_more) {
      cursor.value = page.next_after;
      hasMore.value = true;
    }
    return fresh.length;
  } catch (error) {
    fail("event check failed", error);
    return 0;
  }
}
