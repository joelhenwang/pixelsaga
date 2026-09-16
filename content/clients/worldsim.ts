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

export interface ActivityStartRequest {
  character_id: string;
  duration_phases?: number | null;
  kind: string;
  skill?: string | null;
  to_location_id?: string | null;
  world_id: string;
}

export interface ActivityView {
  character_id: string;
  duration_phases: number;
  id: string;
  kind: string;
  progress_phases: number;
  start_absolute: number;
  status: string;
  version: number;
  world_id: string;
}

export interface ActivityListResponse {
  members?: ActivityView[] | null;
  world_id: string;
}

export interface RelationshipEvidenceRequest {
  delta: number;
  dimension: string;
  note?: string | null;
  source_id: string;
  target_id: string;
  world_id: string;
}

export interface RelationshipView {
  affection: number;
  direction: string;
  id: string;
  respect: number;
  source_id: string;
  summary: string;
  target_id: string;
  trust: number;
  version: number;
  world_id: string;
}

export interface RelationshipListResponse {
  character_id: string;
  members?: RelationshipView[] | null;
  world_id: string;
}

export interface ClaimRequest {
  audience_location_id?: string | null;
  proposition: string;
  refutes_claim_id?: string | null;
  speaker_id: string;
  world_id: string;
}

export interface ClaimView {
  audience_location_id: string;
  id: string;
  proposition: string;
  refutes_claim_id: string;
  speaker_id: string;
  version: number;
  world_id: string;
}

export interface ClaimListResponse {
  members?: ClaimView[] | null;
  viewer_id: string;
  world_id: string;
}

export interface BeliefView {
  confidence: unknown;
  holder_id: string;
  id: string;
  last_touched_absolute: number;
  proposition: string;
  version: number;
  world_id: string;
}

export interface BeliefListResponse {
  holder_id: string;
  members?: BeliefView[] | null;
  world_id: string;
}

export interface ItemGiveRequest {
  item_key: string;
  owner_id?: string | null;
  quantity?: number | null;
  world_id: string;
}

export interface ItemTransferRequest {
  to_owner_id?: string | null;
}

export interface ItemView {
  id: string;
  item_key: string;
  owner_id: string;
  quantity: number;
  version: number;
  world_id: string;
}

export interface ItemListResponse {
  members?: ItemView[] | null;
  owner_id: string;
  world_id: string;
}

export interface SkillView {
  progress: number;
  sessions: number;
  skill_key: string;
  version: number;
}

export interface SkillListResponse {
  character_id: string;
  members?: SkillView[] | null;
  world_id: string;
}

export interface RoleSelectRequest {
  character_id?: string | null;
  role: string;
  world_id: string;
}

export interface RoleGrantView {
  character_id: string;
  granted_absolute: number;
  id: string;
  role: string;
  version: number;
  world_id: string;
}

export interface DirectorProposalRequest {
  kind: string;
  participant_ids?: string[] | null;
  purpose?: string | null;
  requested_powers?: string[] | null;
  title: string;
  world_id: string;
}

export interface DirectorProposalView {
  id: string;
  kind: string;
  reason: string;
  title: string;
  world_id: string;
}

export interface DeityOverrideRequest {
  character_id: string;
  conditions?: string[] | null;
  life_status?: string | null;
  mana?: number | null;
  retcon?: boolean | null;
  stamina?: number | null;
  world_id: string;
}

export interface DeityOverrideView {
  character_id: string;
  event_id: string;
  retcon: boolean;
  world_id: string;
}

export interface TimelineEntry {
  absolute_index: number;
  event_id: string;
  event_type: string;
  sequence: number;
  snippet?: string | null;
}

export interface TimelineResponse {
  entries?: TimelineEntry[] | null;
  total: number;
  world_id: string;
}

export interface MapRoute {
  duration_phases: number;
  to_location_id: string;
}

export interface MapPlace {
  discovered: boolean;
  id: string;
  name: string;
  occupants?: string[] | null;
  region: string;
  routes?: MapRoute[] | null;
}

export interface MapResponse {
  places?: MapPlace[] | null;
  world_id: string;
}

export interface DiaryEntry {
  kind: string;
  phase: number;
  text: string;
}

export interface DiaryResponse {
  character_id: string;
  digests?: DiaryEntry[] | null;
  memories?: DiaryEntry[] | null;
  observations?: DiaryEntry[] | null;
  summaries?: DiaryEntry[] | null;
}

export interface HookView {
  id: string;
  status: string;
  title: string;
}

export interface ArcView {
  id: string;
  status: string;
  title: string;
}

export interface HookListResponse {
  arcs?: ArcView[] | null;
  hooks?: HookView[] | null;
  world_id: string;
}

export interface OperationsStatus {
  open_run_id: string;
  open_run_state: string;
  pending_outbox: number;
  total_events: number;
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
  startActivity: "POST /api/v1/stage2/activities",
  interruptActivity: "POST /api/v1/stage2/activities/{activity_id}/interrupt",
  resumeActivity: "POST /api/v1/stage2/activities/{activity_id}/resume",
  cancelActivity: "POST /api/v1/stage2/activities/{activity_id}/cancel",
  listActivities: "GET /api/v1/stage2/activities",
  recordRelationshipEvidence: "POST /api/v1/stage2/relationships/evidence",
  listRelationships: "GET /api/v1/stage2/relationships",
  assertClaim: "POST /api/v1/stage2/claims",
  listClaims: "GET /api/v1/stage2/claims",
  listBeliefs: "GET /api/v1/stage2/beliefs",
  giveItem: "POST /api/v1/stage2/items/give",
  transferItem: "POST /api/v1/stage2/items/{item_id}/transfer",
  listItems: "GET /api/v1/stage2/items",
  listSkills: "GET /api/v1/stage2/skills",
  selectRole: "POST /api/v1/stage2/roles/select",
  readRole: "GET /api/v1/stage2/roles",
  proposeDirectorHook: "POST /api/v1/stage2/director/proposals",
  applyDeityOverride: "POST /api/v1/stage2/deity/overrides",
  listTimeline: "GET /api/v1/stage2/timeline",
  readMap: "GET /api/v1/stage2/map",
  readDiary: "GET /api/v1/stage2/characters/{character_id}/diary",
  listCharacterActivities: "GET /api/v1/stage2/characters/{character_id}/activities",
  listDirectorHooks: "GET /api/v1/stage2/director/hooks",
  readOperationsStatus: "GET /api/v1/stage2/operations/status",
  listEvents: "GET /api/v1/world/events",
} as const;
