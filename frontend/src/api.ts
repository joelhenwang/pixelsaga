import type {
  ActivityListResponse,
  BeatView,
  CharacterDetail,
  CharacterSummary,
  ChronicleResponse,
  DiaryResponse,
  EndingsResponse,
  EraView,
  ErasResponse,
  FocusAssignmentView,
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
  PresentationResponse,
  RoleGrantView,
  SceneDetail,
  SceneSummary,
  ScheduleCancelResponse,
  Stage1AdvanceResponse,
  TimelineResponse,
  WatcherHeaders,
} from "@gen";

export type Role = "watcher" | "player";

export type ErrorKind =
  | "transport"
  | "auth"
  | "forbidden"
  | "empty"
  | "conflict"
  | "validation"
  | "unknown";

export class ApiError extends Error {
  readonly status: number;
  readonly code: string;
  readonly requestId: string;
  readonly kind: ErrorKind;
  readonly retryable: boolean;

  constructor(status: number, code: string, message: string, requestId: string) {
    super(message);
    this.status = status;
    this.code = code;
    this.requestId = requestId;
    this.kind = kindFor(status, code);
    this.retryable = status === 429 || status >= 500;
  }
}

export function kindFor(status: number, code: string): ErrorKind {
  if (status === 0) {
    return "transport";
  }
  if (status === 401) {
    return "auth";
  }
  if (status === 403) {
    return "forbidden";
  }
  if (status === 404) {
    return code === "WORLD_NOT_FOUND" ? "empty" : "unknown";
  }
  if (status === 409) {
    return "conflict";
  }
  if (status === 422) {
    return "validation";
  }
  return "unknown";
}

export function headersFor(role: Role, characterId: string | null): WatcherHeaders | PlayerHeaders {
  if (role === "player" && characterId) {
    return { "X-Worldsim-Role": "player", "X-Worldsim-Character": characterId };
  }
  return { "X-Worldsim-Role": "watcher" };
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

export interface RequestOptions {
  signal?: AbortSignal;
}

async function request<T>(
  path: string,
  init: RequestInit,
  headers: Record<string, string>,
  options: RequestOptions = {},
): Promise<T> {
  // Only safe reads retry. Writes never replay: a retry could double-apply.
  const safe = !init.method || init.method === "GET";
  let attempt = 0;
  for (;;) {
    let response: Response;
    try {
      response = await fetch(path, { ...init, headers: mergeHeaders(headers, init.headers), signal: options.signal });
    } catch (error) {
      if (error instanceof DOMException && error.name === "AbortError") {
        throw error;
      }
      attempt += 1;
      if (!safe || attempt > 2) {
        throw new ApiError(0, "TRANSPORT", "request failed", "");
      }
      const backoff = Promise.withResolvers<void>();
      setTimeout(backoff.resolve, 300 * attempt);
      await backoff.promise;
      continue;
    }
    if (!response.ok) {
      const body: unknown = await response.json().catch(() => ({}));
      const nested = body && typeof body === "object" && "error" in body ? body.error : null;
      const code =
        nested && typeof nested === "object" && "code" in nested && typeof nested.code === "string"
          ? nested.code
          : `HTTP_${response.status}`;
      const message =
        nested && typeof nested === "object" && "message" in nested && typeof nested.message === "string"
          ? nested.message
          : `${response.status} ${code}`;
      const error = new ApiError(response.status, code, message, response.headers.get("X-Request-ID") ?? "");
      attempt += 1;
      if (safe && error.retryable && attempt <= 2) {
        const retry = Promise.withResolvers<void>();
        setTimeout(retry.resolve, 300 * attempt);
        await retry.promise;
        continue;
      }
      throw error;
    }
    return (await response.json()) as T;
  }
}

export const api = {
  characters(worldId: string, headers: Record<string, string>, options: RequestOptions = {}): Promise<CharacterSummary[]> {
    return request<CharacterSummary[]>(`/api/v1/stage1/characters?world_id=${worldId}`, {}, headers, options);
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
  world(headers: Record<string, string>, options: RequestOptions = {}): Promise<{ id: string; day: number; phase: string }> {
    return request("/api/v1/world", {}, headers, options);
  },
  seed(headers: Record<string, string>): Promise<{ world_id: string; duplicate: boolean }> {
    return request("/api/v1/world/seed", { method: "POST" }, headers);
  },
  currentPhase(headers: Record<string, string>, options: RequestOptions = {}): Promise<{ absolute_index: number }> {
    return request("/api/v1/world/phases/current", {}, headers, options);
  },
  timeline(worldId: string, headers: Record<string, string>, after = 0, limit = 20): Promise<TimelineResponse> {
    return request<TimelineResponse>(`/api/v1/stage2/timeline?world_id=${worldId}&after=${after}&limit=${limit}`, {}, headers);
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
  composeEra(
    worldId: string, ownerId: string, start: number, end: number,
    headers: Record<string, string>,
  ): Promise<EraView> {
    return request<EraView>(
      "/api/v1/macro/eras/compose",
      {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ world_id: worldId, owner_id: ownerId, start_absolute: start, end_absolute: end }),
      },
      headers,
    );
  },
  evaluateEndings(
    worldId: string, at: number, headers: Record<string, string>,
  ): Promise<EndingsResponse> {
    return request<EndingsResponse>(
      "/api/v1/macro/endings/evaluate",
      {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ world_id: worldId, at_absolute: at }),
      },
      headers,
    );
  },
  assignFocus(
    worldId: string, slot: string, to: string, reason: string, at: number,
    headers: Record<string, string>,
  ): Promise<FocusAssignmentView> {
    return request<FocusAssignmentView>(
      "/api/v1/macro/focus/assign",
      {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ world_id: worldId, slot, to_character_id: to, reason, effective_absolute: at }),
      },
      headers,
    );
  },
  createCharacter(
    body: { world_id: string; name: string; location_id: string; appearance?: string; personality?: string; background?: string },
    headers: Record<string, string>,
  ): Promise<CharacterSummary> {
    return request<CharacterSummary>(
      "/api/v1/stage1/characters",
      { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) },
      headers,
    );
  },
  linkPartyMember(
    memberId: string,
    body: { world_id: string; character_id: string; expected_version: number },
    headers: Record<string, string>,
  ): Promise<PartyMemberView> {
    return request<PartyMemberView>(
      `/api/v1/stage1/party/${memberId}/link`,
      { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) },
      headers,
    );
  },
  presentation(worldId: string, headers: Record<string, string>): Promise<PresentationResponse> {
    return request<PresentationResponse>(`/api/v1/world/presentation?world_id=${worldId}`, {}, headers);
  },
  chronicle(worldId: string, after: number, limit: number, headers: Record<string, string>): Promise<ChronicleResponse> {
    return request<ChronicleResponse>(`/api/v1/world/chronicle?world_id=${worldId}&after=${after}&limit=${limit}`, {}, headers);
  },
  roleGrant(worldId: string, headers: Record<string, string>): Promise<RoleGrantView | null> {
    return request(`/api/v1/stage2/roles?world_id=${worldId}`, {}, headers);
  },
  selectRole(
    body: { world_id: string; role: string; character_id?: string | null },
    headers: Record<string, string>,
  ): Promise<RoleGrantView> {
    return request<RoleGrantView>(
      "/api/v1/stage2/roles/select",
      { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) },
      headers,
    );
  },
  async assetBytes(assetId: string, worldId: string, headers: Record<string, string>): Promise<Blob> {
    const response = await fetch(`/api/v1/assets/${assetId}?world_id=${worldId}`, { headers });
    if (!response.ok) {
      const body: unknown = await response.json().catch(() => ({}));
      const nested = body && typeof body === "object" && "error" in body ? body.error : null;
      const code =
        nested && typeof nested === "object" && "code" in nested && typeof nested.code === "string"
          ? nested.code
          : `HTTP_${response.status}`;
      throw new ApiError(response.status, code, code, response.headers.get("X-Request-ID") ?? "");
    }
    return await response.blob();
  },
  cancelSchedule(scheduleId: string, headers: Record<string, string>): Promise<ScheduleCancelResponse> {
    return request<ScheduleCancelResponse>(`/api/v1/macro/schedules/${scheduleId}/cancel`, { method: "POST" }, headers);
  },
};
