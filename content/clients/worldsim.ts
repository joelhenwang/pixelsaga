// Generated TypeScript client for the worldsim HTTP boundary.
//
// Regenerate with `make contracts` (runs scripts/gen_ts_client.py).
// Checked in so the Vue surface shares one typed contract.

export interface CharacterSummary {
  id: string;
  life_status: string;
  location_id: string;
  name: string;
}

export interface CharacterDetail {
  card?: Record<string, unknown> | null;
  id: string;
  life_status: string;
  location_id: string;
  name: string;
  state?: Record<string, unknown> | null;
}

export interface ParticipantView {
  character_id: string;
  role: string;
}

export interface IntentView {
  author_character_id: string;
  detail?: Record<string, unknown> | null;
  family: string;
  id: string;
}

export interface AttemptView {
  actor_character_id: string;
  id: string;
  observable_summary: string;
  status: string;
}

export interface ReactionView {
  detail?: Record<string, unknown> | null;
  family: string;
  id: string;
  reactor_character_id: string;
}

export interface ResolutionView {
  outcome: string;
  rationale: string;
  resolver: string;
}

export interface SceneDetail {
  attempts?: AttemptView[] | null;
  beat_budget: number;
  event_id?: string | null;
  id: string;
  intents?: IntentView[] | null;
  participants?: ParticipantView[] | null;
  phase_run_id: string;
  reactions?: ReactionView[] | null;
  resolution?: ResolutionView | null;
  status: string;
  world_id: string;
}

export interface SceneSummary {
  event_id?: string | null;
  id: string;
  participant_ids?: string[] | null;
  status: string;
}

export interface BeatView {
  id: string;
  kind: string;
  source_event_id: string;
  speaker_id?: string | null;
  text: string;
}

export interface ModelRunView {
  actor_id?: string | null;
  call_id: string;
  completion_tokens?: number | null;
  manifest_id?: string | null;
  profile: string;
  prompt_tokens?: number | null;
  rendered_hash?: string | null;
  role: string;
  status: string;
}

export interface Stage1AdvanceRequest {
  absolute_index: number;
  player_intents?: Record<string, Record<string, unknown>> | null;
  world_id: string;
}

export interface Stage1SceneOutcome {
  event_id: string;
  narration: string;
  resolution_outcome: string;
  scene_id: string;
}

export interface Stage1AdvanceResponse {
  absolute_index: number;
  duplicate?: boolean | null;
  quiet?: boolean | null;
  run_id: string;
  scenes?: Stage1SceneOutcome[] | null;
  snapshot_id: string;
  world_id: string;
}

export interface PartyBeginRequest {
  character_class?: string | null;
  level?: number | null;
  name: string;
  race?: string | null;
  stats?: Record<string, number> | null;
  world_id: string;
}

export interface PartyMemberView {
  character_class: string;
  conditions?: string[] | null;
  hp_current?: number | null;
  hp_max?: number | null;
  id: string;
  level: number;
  name: string;
  version: number;
  world_id: string;
}

export interface PartyRosterResponse {
  members?: PartyMemberView[] | null;
  world_id: string;
}

export type WatcherHeaders = {
  "X-Worldsim-Role": "watcher";
};

export type PlayerHeaders = {
  "X-Worldsim-Role": "player";
  "X-Worldsim-Character": string;
};

export const ROUTES = {
  listCharacters: "GET /api/v1/stage1/characters",
  getCharacter: "GET /api/v1/stage1/characters/{character_id}",
  listScenes: "GET /api/v1/stage1/scenes",
  getScene: "GET /api/v1/stage1/scenes/{scene_id}",
  getNarration: "GET /api/v1/stage1/scenes/{scene_id}/narration",
  listModelRuns: "GET /api/v1/stage1/model-runs",
  advance: "POST /api/v1/stage1/advance",
  pause: "POST /api/v1/stage1/pause",
  resume: "POST /api/v1/stage1/resume",
  beginPartyMember: "POST /api/v1/stage1/party/begin",
  listParty: "GET /api/v1/stage1/party",
  listEvents: "GET /api/v1/world/events",
} as const;
