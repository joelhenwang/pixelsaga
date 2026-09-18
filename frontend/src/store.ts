// Session state, split by responsibility (P02).
//
// Server state (worldId, clock, nextIndex, characters) reloads from the API
// and is keyed by world + role + character: stale responses from a previous
// selection are ignored, never rendered. UI state (theme, settings drawer,
// drafts) lives alongside but never mixes into server projections.
import { computed, ref } from "vue";
import { ApiError, api, headersFor, type ErrorKind, type Role } from "./api";

// -- Server state -----------------------------------------------------------
export const role = ref<Role>("watcher");
export const characterId = ref<string>("");
export const characters = ref<{ id: string; name: string }[]>([]);
export const worldId = ref<string>("");
export const clock = ref<string>("no world");
export const nextIndex = ref<number>(1);
export const connection = ref<"online" | "offline">("online");

// -- UI state ---------------------------------------------------------------
export const notice = ref<string>("");
export const errorKind = ref<ErrorKind | null>(null);
export const busy = ref<boolean>(false);
export const settingsOpen = ref<boolean>(false);
export const theme = ref<"light" | "dark">(
  document.documentElement.classList.contains("dark") ? "dark" : "light",
);
export const apiKey = ref<string>(localStorage.getItem("worldsim.key") ?? "");

export function setApiKey(key: string): void {
  apiKey.value = key;
  if (key) {
    localStorage.setItem("worldsim.key", key);
  } else {
    localStorage.removeItem("worldsim.key");
  }
}

export function setTheme(next: "light" | "dark"): void {
  theme.value = next;
  document.documentElement.classList.toggle("dark", next === "dark");
  localStorage.setItem("worldsim.theme", next);
}

export const headers = computed<Record<string, string>>(() => ({
  ...headersFor(role.value, characterId.value || null),
  ...(apiKey.value ? { Authorization: `Bearer ${apiKey.value}` } : {}),
}));

export function fail(message: string, error: unknown): void {
  if (error instanceof DOMException && error.name === "AbortError") {
    return;
  }
  if (error instanceof ApiError) {
    errorKind.value = error.kind;
    connection.value = error.kind === "transport" ? "offline" : "online";
    const request = error.requestId ? ` [${error.requestId}]` : "";
    notice.value = `${message}: ${error.message}${request}`;
    return;
  }
  errorKind.value = "unknown";
  connection.value = "online";
  notice.value = `${message}: ${error instanceof Error ? error.message : "unknown"}`;
}

// A session key changes on every world/role/character switch. In-flight
// reads started under an older key resolve into the void.
let sessionKey = 0;
let refreshAbort: AbortController | null = null;

export function session(): number {
  return sessionKey;
}

export function switchRole(next: Role, character: string | null): void {
  sessionKey += 1;
  refreshAbort?.abort();
  refreshAbort = null;
  // Privileged data must not survive a role change: clear first, reload after.
  role.value = next;
  characterId.value = character ?? "";
  characters.value = [];
  worldId.value = "";
  clock.value = "no world";
  nextIndex.value = 1;
  errorKind.value = null;
  notice.value = "";
}

export async function refresh(): Promise<void> {
  const key = sessionKey;
  refreshAbort?.abort();
  const controller = new AbortController();
  refreshAbort = controller;
  const options = { signal: controller.signal };
  notice.value = "";
  try {
    const world = await api.world(headers.value, options);
    if (key !== sessionKey) {
      return;
    }
    worldId.value = world.id;
    clock.value = `day ${world.day}, ${world.phase}`;
    const current = await api.currentPhase(headers.value, options);
    if (key !== sessionKey) {
      return;
    }
    nextIndex.value = current.absolute_index + 1;
    const list = await api.characters(world.id, headers.value, options);
    if (key !== sessionKey) {
      return;
    }
    characters.value = list.map((c) => ({ id: c.id, name: c.name }));
    if (!characterId.value && list.length > 0) {
      characterId.value = list[0].id;
    }
    errorKind.value = null;
    connection.value = "online";
  } catch (error) {
    if (key !== sessionKey) {
      return;
    }
    fail("refresh failed", error);
  }
}

export async function seedWorld(): Promise<boolean> {
  notice.value = "";
  errorKind.value = null;
  try {
    await api.seed(headers.value);
    await refresh();
    return true;
  } catch (error) {
    fail("seed failed", error);
    return false;
  }
}

// Central phase advancement (P02). One caller at a time; views report the
// returned run id and reload their own projections.
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
    errorKind.value = null;
    connection.value = "online";
    return report.run_id;
  } catch (error) {
    fail("advance failed", error);
    return "";
  } finally {
    busy.value = false;
  }
}
