"""Generate the TypeScript client from the served OpenAPI contract.

Usage:
    python backend/scripts/gen_ts_client.py --out content/clients/worldsim.ts
    python backend/scripts/gen_ts_client.py --check  (CI: fail on drift)

Only Stage 1 DTOs plus the routes the Vue surface consumes are emitted;
the generator is stdlib-only so contract generation never needs npm.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OPENAPI = ROOT / "content" / "schemas" / "openapi.json"
DEFAULT_OUT = ROOT / "content" / "clients" / "worldsim.ts"

#: Component schemas emitted as interfaces (Stage 1 surface).
WANTED = (
    "CharacterSummary",
    "CharacterDetail",
    "ParticipantView",
    "IntentView",
    "AttemptView",
    "ReactionView",
    "ResolutionView",
    "SceneDetail",
    "SceneSummary",
    "BeatView",
    "ModelRunView",
    "Stage1AdvanceRequest",
    "Stage1SceneOutcome",
    "Stage1AdvanceResponse",
    "PartyBeginRequest",
    "PartyMemberView",
    "PartyRosterResponse",
    "ActivityStartRequest",
    "ActivityView",
    "ActivityListResponse",
    "RelationshipEvidenceRequest",
    "RelationshipView",
    "RelationshipListResponse",
    "ClaimRequest",
    "ClaimView",
    "ClaimListResponse",
    "BeliefView",
    "BeliefListResponse",
    "ItemGiveRequest",
    "ItemTransferRequest",
    "ItemView",
    "ItemListResponse",
    "SkillView",
    "SkillListResponse",
    "RoleSelectRequest",
    "RoleGrantView",
    "DirectorProposalRequest",
    "DirectorProposalView",
    "DeityOverrideRequest",
    "DeityOverrideView",
    "TimelineEntry",
    "TimelineResponse",
    "MapRoute",
    "MapPlace",
    "MapResponse",
    "DiaryEntry",
    "DiaryResponse",
    "HookView",
    "ArcView",
    "HookListResponse",
    "OperationsStatus",
    "MacroEffectView",
    "MacroInterruptionView",
    "MacroRunView",
    "MacroRunsResponse",
    "LineageLinkView",
    "LineageRecordView",
    "LineageResponse",
    "FocusAssignmentView",
    "FocusResponse",
    "EraView",
    "ErasResponse",
    "EndingView",
    "EndingsResponse",
    "MacroAdvanceRequest",
    "MacroAdvanceResponse",
    "EraComposeRequest",
    "EndingsEvaluateRequest",
    "FocusAssignRequest",
    "ScheduleCancelResponse",
    "CharacterCreateRequest",
    "PartyLinkRequest",
    "ChronicleEntry",
    "ChronicleResponse",
    "PresentationCapabilities",
    "MapAnchorView",
    "MapManifestView",
    "CastEntry",
    "PresentationResponse",
)

#: Routes emitted into the ROUTES map (method, openapi path, const name).
ROUTES = (
    ("get", "/api/v1/stage1/characters", "listCharacters"),
    ("get", "/api/v1/stage1/characters/{character_id}", "getCharacter"),
    ("get", "/api/v1/stage1/scenes", "listScenes"),
    ("get", "/api/v1/stage1/scenes/{scene_id}", "getScene"),
    ("get", "/api/v1/stage1/scenes/{scene_id}/narration", "getNarration"),
    ("get", "/api/v1/stage1/model-runs", "listModelRuns"),
    ("post", "/api/v1/stage1/advance", "advance"),
    ("post", "/api/v1/stage1/pause", "pause"),
    ("post", "/api/v1/stage1/resume", "resume"),
    ("post", "/api/v1/stage1/party/begin", "beginPartyMember"),
    ("get", "/api/v1/stage1/party", "listParty"),
    ("post", "/api/v1/stage1/characters", "createCharacter"),
    ("post", "/api/v1/stage1/party/{member_id}/link", "linkPartyMember"),
    ("post", "/api/v1/stage2/activities", "startActivity"),
    ("post", "/api/v1/stage2/activities/{activity_id}/interrupt", "interruptActivity"),
    ("post", "/api/v1/stage2/activities/{activity_id}/resume", "resumeActivity"),
    ("post", "/api/v1/stage2/activities/{activity_id}/cancel", "cancelActivity"),
    ("get", "/api/v1/stage2/activities", "listActivities"),
    ("post", "/api/v1/stage2/relationships/evidence", "recordRelationshipEvidence"),
    ("get", "/api/v1/stage2/relationships", "listRelationships"),
    ("post", "/api/v1/stage2/claims", "assertClaim"),
    ("get", "/api/v1/stage2/claims", "listClaims"),
    ("get", "/api/v1/stage2/beliefs", "listBeliefs"),
    ("post", "/api/v1/stage2/items/give", "giveItem"),
    ("post", "/api/v1/stage2/items/{item_id}/transfer", "transferItem"),
    ("get", "/api/v1/stage2/items", "listItems"),
    ("get", "/api/v1/stage2/skills", "listSkills"),
    ("post", "/api/v1/stage2/roles/select", "selectRole"),
    ("get", "/api/v1/stage2/roles", "readRole"),
    ("post", "/api/v1/stage2/director/proposals", "proposeDirectorHook"),
    ("post", "/api/v1/stage2/deity/overrides", "applyDeityOverride"),
    ("get", "/api/v1/stage2/timeline", "listTimeline"),
    ("get", "/api/v1/stage2/map", "readMap"),
    ("get", "/api/v1/stage2/characters/{character_id}/diary", "readDiary"),
    ("get", "/api/v1/stage2/characters/{character_id}/activities", "listCharacterActivities"),
    ("get", "/api/v1/stage2/director/hooks", "listDirectorHooks"),
    ("get", "/api/v1/stage2/operations/status", "readOperationsStatus"),
    ("get", "/api/v1/world/events", "listEvents"),
    ("get", "/api/v1/world/presentation", "readPresentation"),
    ("get", "/api/v1/world/chronicle", "readChronicle"),
    ("get", "/api/v1/macro/runs", "listMacroRuns"),
    ("get", "/api/v1/macro/lineage", "readLineage"),
    ("get", "/api/v1/macro/focus", "listFocus"),
    ("get", "/api/v1/macro/eras", "listEras"),
    ("get", "/api/v1/macro/endings", "listEndings"),
    ("post", "/api/v1/macro/advance", "advanceMacro"),
    ("post", "/api/v1/macro/eras/compose", "composeEra"),
    ("post", "/api/v1/macro/endings/evaluate", "evaluateEndings"),
    ("post", "/api/v1/macro/focus/assign", "assignFocus"),
    ("post", "/api/v1/macro/schedules/{schedule_id}/cancel", "cancelSchedule"),
)


def _ts_type(schema: dict[str, object], required: bool) -> str:
    if "$ref" in schema:
        base = str(schema["$ref"]).split("/")[-1]
    elif isinstance(schema.get("anyOf"), list):
        options = [
            o
            for o in schema["anyOf"]
            if isinstance(o, dict) and (o.get("$ref") or o.get("type") not in (None, "null"))
        ]
        if len(options) == 1 and isinstance(options[0], dict):
            base = _ts_type(options[0], True)
        else:
            base = "unknown"
    elif schema.get("type") == "array":
        items = schema.get("items", {})
        assert isinstance(items, dict)
        base = f"{_ts_type(items, True)}[]"
    elif schema.get("type") == "string":
        base = "string"
    elif schema.get("type") == "integer":
        base = "number"
    elif schema.get("type") == "boolean":
        base = "boolean"
    elif schema.get("type") == "object":
        extra = schema.get("additionalProperties", {})
        if isinstance(extra, dict) and extra:
            base = f"Record<string, {_ts_type(extra, True)}>"
        else:
            base = "Record<string, unknown>"
    else:
        base = "unknown"
    return base if required else f"{base} | null"


def _interface(name: str, schema: dict[str, object]) -> str:
    properties = schema.get("properties", {})
    required = set(schema.get("required", []))
    assert isinstance(properties, dict)
    lines = [f"export interface {name} {{"]
    for prop, subschema in properties.items():
        assert isinstance(subschema, dict)
        ts = _ts_type(subschema, prop in required)
        mark = "" if prop in required else "?"
        lines.append(f"  {prop}{mark}: {ts};")
    lines.append("}")
    return "\n".join(lines)


def generate(spec: dict[str, object]) -> str:
    components = spec.get("components", {})
    assert isinstance(components, dict)
    schemas = components.get("schemas", {})
    assert isinstance(schemas, dict)
    paths = spec.get("paths", {})
    assert isinstance(paths, dict)
    for method, path, _name in ROUTES:
        assert path in paths, f"route missing from OpenAPI: {path}"
        assert method in paths[path], f"method missing: {method} {path}"
    blocks = [
        "// Generated TypeScript client for the worldsim HTTP boundary.",
        "//",
        "// Regenerate with `make contracts` (runs scripts/gen_ts_client.py).",
        "// Checked in so the Vue surface shares one typed contract.",
        "",
    ]
    for name in WANTED:
        assert name in schemas, f"schema missing from OpenAPI: {name}"
        schema = schemas[name]
        assert isinstance(schema, dict)
        blocks.append(_interface(name, schema))
        blocks.append("")
    blocks.append("export type WatcherHeaders = {")
    blocks.append('  "X-Worldsim-Role": "watcher";')
    blocks.append("};")
    blocks.append("")
    blocks.append("export type PlayerHeaders = {")
    blocks.append('  "X-Worldsim-Role": "player";')
    blocks.append('  "X-Worldsim-Character": string;')
    blocks.append("};")
    blocks.append("")
    blocks.append("export const ROUTES = {")
    for method, path, const in ROUTES:
        blocks.append(f'  {const}: "{method.upper()} {path}",')
    blocks.append("} as const;")
    blocks.append("")
    return "\n".join(blocks)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Generate the TypeScript client")
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args(argv)
    spec = json.loads(OPENAPI.read_text(encoding="utf-8"))
    assert isinstance(spec, dict)
    rendered = generate(spec)
    if args.check:
        current = args.out.read_text(encoding="utf-8")
        if current != rendered:
            raise SystemExit("TypeScript client drifted; run make contracts")
        return 0
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(rendered, encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
