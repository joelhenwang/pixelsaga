"""Perspective-safe context assembly checks (owned by S1-CTX-001)."""

from __future__ import annotations

import hashlib
import uuid

from worldsim.application.context.assembler import assemble, to_manifest_dict
from worldsim.domain.context import ContextRequest, SourceCandidate
from worldsim.domain.enums import Visibility

SECRET = "A davors the northern pass at dawn"
PUBLIC_FACT = "The market opens at dawn"


def _request(actor: uuid.UUID, **overrides: object) -> ContextRequest:
    base: dict[str, object] = {
        "role": "character_decision",
        "actor_id": actor,
        "world_id": uuid.uuid4(),
        "phase_run_id": uuid.uuid4(),
        "snapshot_id": uuid.uuid4(),
        "purpose": "decide next intent",
    }
    base.update(overrides)
    return ContextRequest(**base)  # type: ignore[arg-type]


def _candidates(a: uuid.UUID, b: uuid.UUID) -> list[SourceCandidate]:
    return [
        SourceCandidate(
            source_id="card-a",
            data_class="identity",
            visibility=Visibility.PRIVATE,
            owner_id=a,
            text="Wren the scout",
            score=1.0,
        ),
        SourceCandidate(
            source_id="card-b",
            data_class="identity",
            visibility=Visibility.PRIVATE,
            owner_id=b,
            text="Ash the keeper",
            score=1.0,
        ),
        SourceCandidate(
            source_id="secret-a",
            data_class="memories",
            visibility=Visibility.PRIVATE,
            owner_id=a,
            text=SECRET,
            score=0.9,
        ),
        SourceCandidate(
            source_id="lore-market",
            data_class="lore",
            visibility=Visibility.PUBLIC,
            text=PUBLIC_FACT,
            score=0.5,
        ),
    ]


def test_perspectives_share_snapshot_and_differ() -> None:
    a, b = uuid.uuid4(), uuid.uuid4()
    snapshot = uuid.uuid4()
    world = uuid.uuid4()
    run = uuid.uuid4()
    candidates = _candidates(a, b)

    envelope_a, _, _ = assemble(
        _request(a, world_id=world, phase_run_id=run, snapshot_id=snapshot), candidates
    )
    envelope_b, _, _ = assemble(
        _request(b, world_id=world, phase_run_id=run, snapshot_id=snapshot), candidates
    )

    assert envelope_a.snapshot_id == envelope_b.snapshot_id == snapshot
    assert SECRET in envelope_a.rendered
    assert SECRET not in envelope_b.rendered
    assert PUBLIC_FACT in envelope_a.rendered
    assert PUBLIC_FACT in envelope_b.rendered
    assert "Wren the scout" in envelope_a.rendered
    assert "Wren the scout" not in envelope_b.rendered


def test_excluded_secret_has_visibility_reason() -> None:
    a, b = uuid.uuid4(), uuid.uuid4()
    _, _, excluded = assemble(_request(b), _candidates(a, b))
    reasons = {s.source_id: s.reason for s in excluded}
    assert reasons["secret-a"] == "private to another owner"
    assert reasons["card-a"] == "private to another owner"


def test_assembly_is_deterministic() -> None:
    a, b = uuid.uuid4(), uuid.uuid4()
    request = _request(a)
    first, _, _ = assemble(request, _candidates(a, b))
    second, _, _ = assemble(request, list(reversed(_candidates(a, b))))
    assert first.rendered == second.rendered
    assert first.rendered_hash == second.rendered_hash
    assert first.rendered_hash == hashlib.sha256(first.rendered.encode()).hexdigest()


def test_section_budgets_truncate_and_record() -> None:
    a, b = uuid.uuid4(), uuid.uuid4()
    request = _request(a, section_budgets={"lore": 40})
    envelope, _, excluded = assemble(request, _candidates(a, b))
    lore = next(s for s in envelope.sections if s.name == "lore")
    assert lore.truncated_sources == ["lore-market"]
    assert lore.entries[0].endswith("...[truncated]")
    assert len(lore.entries[0]) == 40 + len("...[truncated]")
    # secret-a is A's own memory, so it renders; only B's card is excluded.
    assert {s.source_id for s in excluded} == {"card-b"}


def test_budget_exhaustion_excludes_low_rank() -> None:
    a, _b = uuid.uuid4(), uuid.uuid4()
    request = _request(a, section_budgets={"lore": 50}, allowed_classes=["lore"])
    candidates = [
        SourceCandidate(
            source_id=f"lore-{i}",
            data_class="lore",
            visibility=Visibility.PUBLIC,
            text=f"fact number {i}",
            score=float(i),
        )
        for i in range(5)
    ]
    envelope, included, excluded = assemble(request, candidates)
    assert envelope.rendered.count("<<untrusted:lore>>") == 1
    assert {s.source_id for s in included} == {"lore-4"}
    assert {s.source_id for s in excluded} == {f"lore-{i}" for i in range(4)}
    assert all(s.reason == "section budget exhausted" for s in excluded)


def test_untrusted_payloads_delimited() -> None:
    a, b = uuid.uuid4(), uuid.uuid4()
    envelope, _, _ = assemble(_request(a), _candidates(a, b))
    assert "<<untrusted:lore>>" in envelope.rendered
    assert envelope.sections[0].instruction == envelope.rendered.split("\n")[1]


def test_manifest_split_covers_every_candidate() -> None:
    a, b = uuid.uuid4(), uuid.uuid4()
    candidates = _candidates(a, b)
    _, included, excluded = assemble(_request(a), candidates)
    sources, dropped = to_manifest_dict(included, excluded)
    assert {s.source_id for s in sources} == {c.source_id for c in candidates}
    assert set(dropped) == {s.source_id for s in excluded}
