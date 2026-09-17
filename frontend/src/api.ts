import type {
  ActivityListResponse,
  BeatView,
  CharacterDetail,
  CharacterSummary,
  DiaryResponse,
  EndingsResponse,
  ErasResponse,
  FocusResponse,
  HookListResponse,
  LineageResponse,
  MacroAdvanceResponse,
  MacroRunsResponse,
  MapResponse,
  OperationsStatus,
  PartyBeginRequest,
  PartyMemberView,
  PartyRosterResponse,
  PlayerHeaders,
  RelationshipListResponse,
  SceneDetail,
  SceneSummary,
  Stage1AdvanceResponse,
  TimelineResponse,
  WatcherHeaders,
} from "@gen";

export type Role = "watcher" | "player";

export function headersFor(role: Role, characterId: string | null): WatcherHeaders | PlayerHeaders {
  if (role === "player" && characterId) {
    return { "X-Worldsim-Role": "player", "X-Worldsim-Character": characterId };
  }
  return { "X-Worldsim-Role": "watcher" };
}

function errorCode(body: unknown, status: number): string {
  if (body && typeof body === "object" && "error" in body) {
    const nested = body.error;
    if (nested && typeof nested === "object" && "code" in nested && typeof nested.code === "string") {
      return nested.code;
    }
  }
  return `HTTP_${status}`;
}

function mergeHeaders(base: Record<string, string>, extra: RequestInit["headers"]): Record<string, string> {
  if (!extra) {
    return { ...base };
  }
  if (extra instanceof Headers) {
    const out: Record<string, string> = { ...base };
    extra.forEach((value, key) => {
      out[key] = value;
    });
    return out;
  }
  if (Array.isArray(extra)) {
    return { ...base, ...Object.fromEntries(extra) };
  }
  return { ...base, ...extra };
}

async function request<T>(path: string, init: RequestInit, headers: Record<string, string>): Promise<T> {
  let attempt = 0;
  for (;;) {
    try {
      const response = await fetch(path, { ...init, headers: mergeHeaders(headers, init.headers) });
      if (!response.ok) {
        const body: unknown = await response.json().catch(() => ({}));
        throw new Error(`${response.status}: ${errorCode(body, response.status)}`);
      }
      return (await response.json()) as T;
    } catch (error) {
      attempt += 1;
      const message = error instanceof Error ? error.message : "";
      if (attempt > 2 || message.startsWith("403") || message.startsWith("422")) {
        throw error;
      }
      const { promise, resolve } = Promise.withResolvers<void>();
      setTimeout(resolve, 300 * attempt);
      await promise;
    }
  }
}

export const api = {
  characters(worldId: string, headers: Record<string, string>): Promise<CharacterSummary[]> {
    return request<CharacterSummary[]>(`/api/v1/stage1/characters?world_id=${worldId}`, {}, headers);
  },
  character(id: string, headers: Record<string, string>): Promise<CharacterDetail> {
    return request<CharacterDetail>(`/api/v1/stage1/characters/${id}`, {}, headers);
  },
  scenes(phaseRunId: string, headers: Record<string, string>): Promise<SceneSummary[]> {
    return request<SceneSummary[]>(`/api/v1/stage1/scenes?phase_run_id=${phaseRunId}`, {}, headers);
  },
  scene(id: string, headers: Record<string, string>): Promise<SceneDetail> {
    return request<SceneDetail>(`/api/v1/stage1/scenes/${id}`, {}, headers);
  },
  narration(sceneId: string, headers: Record<string, string>): Promise<BeatView[]> {
    return request<BeatView[]>(`/api/v1/stage1/scenes/${sceneId}/narration`, {}, headers);
  },
  advance(
    worldId: string,
    absoluteIndex: number,
    headers: Record<string, string>,
    playerIntents?: Record<string, Record<string, unknown>>,
  ): Promise<Stage1AdvanceResponse> {
    return request<Stage1AdvanceResponse>(
      "/api/v1/stage1/advance",
      {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ world_id: worldId, absolute_index: absoluteIndex, player_intents: playerIntents ?? {} }),
      },
      headers,
    );
  },
  timeline(worldId: string, headers: Record<string, string>, after = 0, limit = 20): Promise<TimelineResponse> {
    return request<TimelineResponse>(`/api/v1/stage2/timeline?world_id=${worldId}&after=${after}&limit=${limit}`, {}, headers);
  },
  world(headers: Record<string, string>): Promise<{ id: string; day: number; phase: string }> {
    return request("/api/v1/world", {}, headers);
  },
  map(worldId: string, headers: Record<string, string>): Promise<MapResponse> {
    return request<MapResponse>(`/api/v1/stage2/map?world_id=${worldId}`, {}, headers);
  },
  diary(characterId: string, headers: Record<string, string>): Promise<DiaryResponse> {
    return request<DiaryResponse>(`/api/v1/stage2/characters/${characterId}/diary`, {}, headers);
  },
  characterActivities(characterId: string, headers: Record<string, string>): Promise<ActivityListResponse> {
    return request<ActivityListResponse>(`/api/v1/stage2/characters/${characterId}/activities`, {}, headers);
  },
  relationships(worldId: string, characterId: string, headers: Record<string, string>): Promise<RelationshipListResponse> {
    return request<RelationshipListResponse>(
      `/api/v1/stage2/relationships?world_id=${worldId}&character_id=${characterId}`, {}, headers,
    );
  },
  hooks(worldId: string, headers: Record<string, string>): Promise<HookListResponse> {
    return request<HookListResponse>(`/api/v1/stage2/director/hooks?world_id=${worldId}`, {}, headers);
  },
  operations(worldId: string, headers: Record<string, string>): Promise<OperationsStatus> {
    return request<OperationsStatus>(`/api/v1/stage2/operations/status?world_id=${worldId}`, {}, headers);
  },
  party(worldId: string, headers: Record<string, string>): Promise<PartyRosterResponse> {
    return request<PartyRosterResponse>(`/api/v1/stage1/party?world_id=${worldId}`, {}, headers);
  },
  beginParty(body: PartyBeginRequest, headers: Record<string, string>): Promise<PartyMemberView> {
    return request<PartyMemberView>(
      "/api/v1/stage1/party/begin",
      {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      },
      headers,
    );
  },
  macroRuns(worldId: string, headers: Record<string, string>): Promise<MacroRunsResponse> {
    return request<MacroRunsResponse>(`/api/v1/macro/runs?world_id=${worldId}`, {}, headers);
  },
  lineage(worldId: string, headers: Record<string, string>): Promise<LineageResponse> {
    return request<LineageResponse>(`/api/v1/macro/lineage?world_id=${worldId}`, {}, headers);
  },
  focus(worldId: string, headers: Record<string, string>): Promise<FocusResponse> {
    return request<FocusResponse>(`/api/v1/macro/focus?world_id=${worldId}`, {}, headers);
  },
  eras(worldId: string, start: number, end: number, headers: Record<string, string>): Promise<ErasResponse> {
    return request<ErasResponse>(
      `/api/v1/macro/eras?world_id=${worldId}&start_absolute=${start}&end_absolute=${end}`, {}, headers,
    );
  },
  endings(worldId: string, headers: Record<string, string>): Promise<EndingsResponse> {
    return request<EndingsResponse>(`/api/v1/macro/endings?world_id=${worldId}`, {}, headers);
  },
  advanceMacro(
    worldId: string,
    day: number,
    resolution: string,
    headers: Record<string, string>,
  ): Promise<MacroAdvanceResponse> {
    return request<MacroAdvanceResponse>(
      "/api/v1/macro/advance",
      {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ world_id: worldId, day, resolution }),
      },
      headers,
    );
  },
};
