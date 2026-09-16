"""Hybrid ResolutionGraph checks (owned by S1-RESOLVE-001)."""

from __future__ import annotations

import asyncio
import json
import uuid
from typing import Any

from worldsim.application.graphs.resolve import (
    RESOLVER_PROMPT_VERSION,
    ResolverGraphDeps,
    build_resolve_graph,
    load_resolver_prompt,
)
from worldsim.application.graphs.runtime import invoke
from worldsim.application.graphs.state import GraphInvocation
from worldsim.application.ports.model_gateway import ModelTimeoutError
from worldsim.infrastructure.model_gateway.fake import FakeGateway
from worldsim.infrastructure.model_gateway.profiles import RESOLVER_FAKE_PROFILE


def _ids() -> dict[str, uuid.UUID]:
    route = uuid.uuid4()
    return {
        "world": uuid.uuid4(),
        "phase": uuid.uuid4(),
        "scene": uuid.uuid4(),
        "snapshot": uuid.uuid4(),
        "hearth": uuid.uuid4(),
        "market": uuid.uuid4(),
        "wren": uuid.uuid4(),
        "ash": uuid.uuid4(),
        "route": route,
    }


def _characters(ids: dict[str, uuid.UUID], wren_stamina: int = 80) -> list[dict[str, Any]]:
    return [
        {
            "id": str(ids["wren"]),
            "world_id": str(ids["world"]),
            "name": "Wren",
            "card_version": 1,
            "location_id": str(ids["hearth"]),
            "stamina": wren_stamina,
            "mana": 40,
            "version": 0,
        },
        {
            "id": str(ids["ash"]),
            "world_id": str(ids["world"]),
            "name": "Ash",
            "card_version": 1,
            "location_id": str(ids["market"]),
            "stamina": 70,
            "mana": 60,
            "version": 0,
        },
    ]


def _locations(ids: dict[str, uuid.UUID]) -> list[dict[str, Any]]:
    return [
        {
            "id": str(ids["hearth"]),
            "world_id": str(ids["world"]),
            "name": "Hearth",
            "routes": [
                {
                    "id": str(ids["route"]),
                    "destination_location_id": str(ids["market"]),
                    "duration_phases": 1,
                    "stamina_cost": 10,
                }
            ],
        },
        {"id": str(ids["market"]), "world_id": str(ids["world"]), "name": "Market"},
    ]


def _versions(ids: dict[str, uuid.UUID]) -> dict[str, int]:
    return {f"character:{ids['wren']}": 0, f"character:{ids['ash']}": 0}


def _invocation(
    ids: dict[str, uuid.UUID], intents: list[dict[str, Any]], **overrides: Any
) -> GraphInvocation:
    payload: dict[str, Any] = {
        "intents_json": intents,
        "characters_json": overrides.pop("characters_json", _characters(ids)),
        "locations_json": _locations(ids),
        "expected_versions": overrides.pop("expected_versions", _versions(ids)),
    }
    payload.update(overrides)
    return GraphInvocation(
        graph_name="resolve",
        graph_version="v1",
        task_run_id=uuid.uuid4(),
        world_id=ids["world"],
        phase_run_id=ids["phase"],
        snapshot_id=ids["snapshot"],
        scene_id=ids["scene"],
        role="resolver",
        profile_version=RESOLVER_FAKE_PROFILE.version,
        prompt_version=RESOLVER_PROMPT_VERSION,
        input=payload,
    )


def _intent_dict(
    ids: dict[str, uuid.UUID],
    author: str,
    action: dict[str, Any],
    intent_id: uuid.UUID | None = None,
) -> dict[str, Any]:
    return {
        "id": str(intent_id or uuid.uuid4()),
        "world_id": str(ids["world"]),
        "snapshot_id": str(ids["snapshot"]),
        "phase_run_id": str(ids["phase"]),
        "author_character_id": str(ids[author]),
        "action": action,
        "desired_effects": [],
        "idempotency_key": f"test:{uuid.uuid4()}",
    }


def _action(ids: dict[str, uuid.UUID], author: str, family: str, **extra: Any) -> dict[str, Any]:
    base: dict[str, Any] = {
        "family": family,
        "character_id": str(ids[author]),
        "snapshot_id": str(ids["snapshot"]),
    }
    base.update(extra)
    return base


def _deps(gateway: FakeGateway) -> ResolverGraphDeps:
    return ResolverGraphDeps(
        gateway=gateway, profile=RESOLVER_FAKE_PROFILE, system_template=load_resolver_prompt()
    )


def test_deterministic_success_needs_no_model() -> None:
    ids = _ids()
    gateway = FakeGateway(profile=RESOLVER_FAKE_PROFILE)
    intents = [
        _intent_dict(ids, "wren", _action(ids, "wren", "wait")),
        _intent_dict(ids, "ash", _action(ids, "ash", "wait")),
    ]

    result = asyncio.run(invoke(build_resolve_graph(_deps(gateway)), _invocation(ids, intents)))

    assert result["status"] == "resolved"
    assert result["proposal"]["fallback"] is False
    resolution = result["proposal"]["resolution"]
    assert resolution["outcome"] == "success"
    assert resolution["effects"] == []
    assert resolution["resolver"] == "deterministic"
    assert resolution["random_seed"] != 0
    assert gateway.sent_requests == []


def test_rest_plans_bounded_recovery() -> None:
    ids = _ids()
    gateway = FakeGateway(profile=RESOLVER_FAKE_PROFILE)
    intents = [_intent_dict(ids, "wren", _action(ids, "wren", "rest", duration_phases=1))]

    result = asyncio.run(invoke(build_resolve_graph(_deps(gateway)), _invocation(ids, intents)))

    resolution = result["proposal"]["resolution"]
    assert resolution["outcome"] == "success"
    kinds = {(e["resource"], e["delta"]) for e in resolution["effects"]}
    assert ("stamina", 10) in kinds
    assert ("mana", 5) in kinds


def test_move_plans_entity_and_cost() -> None:
    ids = _ids()
    gateway = FakeGateway(profile=RESOLVER_FAKE_PROFILE)
    intents = [
        _intent_dict(
            ids,
            "wren",
            _action(
                ids,
                "wren",
                "move",
                destination_location_id=str(ids["market"]),
                route_id=str(ids["route"]),
            ),
        )
    ]

    result = asyncio.run(invoke(build_resolve_graph(_deps(gateway)), _invocation(ids, intents)))

    resolution = result["proposal"]["resolution"]
    assert resolution["outcome"] == "success"
    types = {e["effect_type"] for e in resolution["effects"]}
    assert types == {"move_entity", "resource_adjusted"}


def test_exhausted_mover_cannot_attempt() -> None:
    ids = _ids()
    gateway = FakeGateway(profile=RESOLVER_FAKE_PROFILE)
    intents = [
        _intent_dict(
            ids,
            "wren",
            _action(
                ids,
                "wren",
                "move",
                destination_location_id=str(ids["market"]),
                route_id=str(ids["route"]),
            ),
        )
    ]
    invocation = _invocation(ids, intents, characters_json=_characters(ids, wren_stamina=5))

    result = asyncio.run(invoke(build_resolve_graph(_deps(gateway)), invocation))

    assert result["status"] == "resolved"
    assert result["proposal"]["resolution"]["outcome"] == "impossible"
    assert result["proposal"]["resolution"]["effects"] == []
    assert gateway.sent_requests == []


def test_routeless_move_is_impossible() -> None:
    ids = _ids()
    gateway = FakeGateway(profile=RESOLVER_FAKE_PROFILE)
    intents = [
        _intent_dict(
            ids,
            "wren",
            _action(ids, "wren", "move", destination_location_id=str(ids["market"])),
        )
    ]

    result = asyncio.run(invoke(build_resolve_graph(_deps(gateway)), _invocation(ids, intents)))

    assert result["proposal"]["resolution"]["outcome"] == "impossible"
    assert gateway.sent_requests == []


def test_stale_target_fails_without_model() -> None:
    ids = _ids()
    gateway = FakeGateway(profile=RESOLVER_FAKE_PROFILE)
    intents = [_intent_dict(ids, "wren", _action(ids, "wren", "rest", duration_phases=1))]
    versions = _versions(ids)
    versions[f"character:{ids['wren']}"] = 4

    result = asyncio.run(
        invoke(
            build_resolve_graph(_deps(gateway)),
            _invocation(ids, intents, expected_versions=versions),
        )
    )

    assert result["proposal"]["resolution"]["outcome"] == "failure"
    assert "stale" in result["proposal"]["reason"] or "stale" in json.dumps(result)
    assert gateway.sent_requests == []


def _communicate(ids: dict[str, uuid.UUID]) -> dict[str, Any]:
    return _intent_dict(
        ids,
        "wren",
        _action(ids, "wren", "communicate", target_character_id=str(ids["ash"]), topic="dawn"),
    )


def _disclosure_proposal(ids: dict[str, uuid.UUID], outcome: str) -> str:
    return json.dumps(
        {
            "outcome": outcome,
            "effects": [
                {
                    "schema_version": 1,
                    "affected_ids": [str(ids["ash"])],
                    "expected_versions": {str(ids["ash"]): 0},
                    "effect_type": "record_observation",
                    "observer_character_id": str(ids["ash"]),
                    "facts": [{"key": "greeting", "value": "Wren nods"}],
                }
            ],
            "rationale": "Ash hears the greeting at the market.",
        }
    )


def test_ambiguous_dialogue_resolved_by_model() -> None:
    ids = _ids()
    gateway = FakeGateway(profile=RESOLVER_FAKE_PROFILE)
    gateway.enqueue_text(_disclosure_proposal(ids, "success"))

    result = asyncio.run(
        invoke(build_resolve_graph(_deps(gateway)), _invocation(ids, [_communicate(ids)]))
    )

    assert result["status"] == "resolved"
    assert result["proposal"]["fallback"] is False
    resolution = result["proposal"]["resolution"]
    assert resolution["outcome"] == "success"
    assert resolution["resolver"] == "model"
    assert resolution["profile_version"] == "resolve-fake-v1"
    assert resolution["effects"][0]["effect_type"] == "record_observation"
    assert len(gateway.sent_requests) == 1


def test_partial_outcome_accepted() -> None:
    ids = _ids()
    gateway = FakeGateway(profile=RESOLVER_FAKE_PROFILE)
    gateway.enqueue_text(_disclosure_proposal(ids, "partial"))

    result = asyncio.run(
        invoke(build_resolve_graph(_deps(gateway)), _invocation(ids, [_communicate(ids)]))
    )

    assert result["proposal"]["resolution"]["outcome"] == "partial"


def test_outside_envelope_repaired_then_accepted() -> None:
    ids = _ids()
    gateway = FakeGateway(profile=RESOLVER_FAKE_PROFILE)
    gateway.enqueue_text(
        json.dumps(
            {
                "outcome": "success",
                "effects": [
                    {
                        "schema_version": 1,
                        "affected_ids": [str(uuid.uuid4())],
                        "expected_versions": {},
                        "effect_type": "record_observation",
                        "observer_character_id": str(ids["ash"]),
                        "facts": [{"key": "greeting", "value": "hi"}],
                    }
                ],
                "rationale": "outsider effect",
            }
        )
    )
    gateway.enqueue_text(_disclosure_proposal(ids, "success"))

    result = asyncio.run(
        invoke(build_resolve_graph(_deps(gateway)), _invocation(ids, [_communicate(ids)]))
    )

    assert result["status"] == "resolved"
    assert result["repair_count"] == 1
    assert result["proposal"]["resolution"]["outcome"] == "success"


def test_malformed_model_falls_back() -> None:
    ids = _ids()
    gateway = FakeGateway(profile=RESOLVER_FAKE_PROFILE)
    gateway.enqueue_text("{broken")
    gateway.enqueue_text("{broken again")

    result = asyncio.run(
        invoke(build_resolve_graph(_deps(gateway)), _invocation(ids, [_communicate(ids)]))
    )

    assert result["status"] == "fallback"
    assert result["proposal"]["fallback"] is True
    assert result["proposal"]["resolution"]["resolver"] == "deterministic"
    assert result["proposal"]["resolution"]["random_seed"] != 0


def test_provider_error_falls_back_with_determined_parts() -> None:
    ids = _ids()
    gateway = FakeGateway(profile=RESOLVER_FAKE_PROFILE)
    gateway.enqueue_error(ModelTimeoutError("timed out"))
    intents = [
        _intent_dict(ids, "ash", _action(ids, "ash", "wait")),
        _communicate(ids),
    ]

    result = asyncio.run(invoke(build_resolve_graph(_deps(gateway)), _invocation(ids, intents)))

    assert result["status"] == "fallback"
    assert result["proposal"]["fallback"] is True
    # The determined wait still succeeds inside the fallback merge.
    assert result["proposal"]["resolution"]["outcome"] == "success"


def test_seed_evidence_is_deterministic() -> None:
    ids = _ids()
    first = asyncio.run(
        invoke(
            build_resolve_graph(
                _deps(
                    FakeGateway(
                        profile=RESOLVER_FAKE_PROFILE,
                        default_text=_disclosure_proposal(ids, "success"),
                    )
                )
            ),
            _invocation(ids, [_communicate(ids)]),
        )
    )
    second = asyncio.run(
        invoke(
            build_resolve_graph(
                _deps(
                    FakeGateway(
                        profile=RESOLVER_FAKE_PROFILE,
                        default_text=_disclosure_proposal(ids, "success"),
                    )
                )
            ),
            _invocation(ids, [_communicate(ids)]),
        )
    )
    assert (
        first["proposal"]["resolution"]["random_seed"]
        == second["proposal"]["resolution"]["random_seed"]
    )
