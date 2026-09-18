// Shared session state: world, role, clock, and refresh (S2-UI-001).
//
// Views read these refs instead of prop-drilling. Canon-adjacent
// data (roster, scenes, timelines) stays view-local and reloads
// from the API; only session chrome lives here.
import { computed, ref } from "vue";
import { api, headersFor, type Role } from "./api";

export const role = ref<Role>("watcher");
export const characterId = ref<string>("");
export const characters = ref<{ id: string; name: string }[]>([]);
export const worldId = ref<string>("");
export const clock = ref<string>("no world");
export const nextIndex = ref<number>(1);
export const connection = ref<"online" | "offline">("online");
export const notice = ref<string>("");
export const busy = ref<boolean>(false);
export const apiKey = ref<string>(localStorage.getItem("worldsim.key") ?? "");

export function setApiKey(key: string): void {
  apiKey.value = key;
  if (key) {
    localStorage.setItem("worldsim.key", key);
  } else {
    localStorage.removeItem("worldsim.key");
  }
}

export const headers = computed<Record<string, string>>(() => ({
  ...headersFor(role.value, characterId.value || null),
  ...(apiKey.value ? { Authorization: `Bearer ${apiKey.value}` } : {}),
}));

export function fail(message: string, error: unknown): void {
  connection.value = "offline";
  notice.value = `${message}: ${error instanceof Error ? error.message : "unknown"}`;
}

export async function refresh(): Promise<void> {
  notice.value = "";
  try {
    const world = await api.world(headers.value);
    worldId.value = world.id;
    clock.value = `day ${world.day}, ${world.phase}`;
    const current = await fetch(`/api/v1/world/phases/current`, {
      headers: headers.value,
    }).then(async (r) => {
      if (!r.ok) {
        throw new Error(`${r.status}`);
      }
      return (await r.json()) as { absolute_index: number };
    });
    nextIndex.value = current.absolute_index + 1;
    const list = await api.characters(world.id, headers.value);
    characters.value = list.map((c) => ({ id: c.id, name: c.name }));
    if (!characterId.value && list.length > 0) {
      characterId.value = list[0].id;
    }
    connection.value = "online";
  } catch (error) {
    fail("refresh failed", error);
  }
}

export async function advance(): Promise<string> {
  if (busy.value) {
    return "";
  }
  busy.value = true;
  notice.value = "";
  try {
    const report = await api.advance(worldId.value, nextIndex.value, headers.value);
    nextIndex.value = report.absolute_index + 1;
    const world = await api.world(headers.value);
    clock.value = `day ${world.day}, ${world.phase}`;
    connection.value = "online";
    return report.run_id;
  } catch (error) {
    fail("advance failed", error);
    return "";
  } finally {
    busy.value = false;
  }
}
