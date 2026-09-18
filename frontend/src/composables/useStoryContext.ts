// Story session binding (A07): entering, switching, and leaving a story.
//
// One story at a time. Entering validates the route ID, loads catalog
// metadata plus the saved role grant, bumps the session epoch to void
// in-flight work from the previous story, then binds immutable context.
// Leaving stops playback and clears projections; a committed server phase
// may finish, but nothing from A may render into or schedule for B.
import { reactive } from "vue";
import { ApiError, api } from "../api";
import { headers, refresh, switchRole, worldStatus } from "../store";
import { pause } from "./useSimulationControl";
import type { Role } from "../api";

export interface StoryBinding {
  storyId: string;
  worldId: string;
  title: string;
  role: string;
  characterId: string | null;
}

export const currentStory = reactive<{ binding: StoryBinding | null }>({
  binding: null,
});

const UUID_RE =
  /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;

export function isStoryId(value: string): boolean {
  return UUID_RE.test(value);
}

export async function enterStory(storyId: string): Promise<StoryBinding> {
  if (!isStoryId(storyId)) {
    throw new ApiError(404, "NOT_FOUND", "unknown story", "");
  }
  const detail = await api.readStory(storyId, headers.value);
  const grant = await api.roleGrant(detail.world_id, headers.value);
  const role = grant?.role ?? detail.mode ?? "watcher";
  const character = grant?.character_id ?? null;
  if (role === "player" && !character) {
    throw new ApiError(409, "PLAYER_UNBOUND", "this player story needs a character", "");
  }
  pause();
  switchRole(role as Role, character);
  worldStatus.value = detail.status;
  await refresh(detail.world_id);
  const binding: StoryBinding = {
    storyId,
    worldId: detail.world_id,
    title: detail.title,
    role,
    characterId: character,
  };
  currentStory.binding = binding;
  try {
    localStorage.setItem("pixelsaga.last-story", storyId);
  } catch {
    /* harmless UI preference only */
  }
  return binding;
}

export function lastStoryHint(): string | null {
  try {
    return localStorage.getItem("pixelsaga.last-story");
  } catch {
    return null;
  }
}

export async function leaveStory(): Promise<void> {
  pause();
  currentStory.binding = null;
  switchRole("watcher", null);
}
