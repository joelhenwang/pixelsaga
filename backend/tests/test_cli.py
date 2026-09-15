"""S0-API-001: CLI mirrors the boundary (owned by S0-API-001)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from worldsim.interfaces.cli import main

SEED_DIR = str(Path(__file__).parent.parent.parent / "content" / "seeds" / "stage0")


def test_cli_seed_advance_inspect_reconcile(
    migrated_db: None, capsys: pytest.CaptureFixture[str]
) -> None:
    assert main(["seed", "--seed-dir", SEED_DIR]) == 0
    seeded = json.loads(str(capsys.readouterr().out))
    assert seeded["seed_version"] == "stage0-v1"
    assert seeded["duplicate"] is False
    world_id = seeded["world_id"]

    assert main(["advance", "--world", world_id, "--key", "cli-key-1"]) == 0
    advanced = json.loads(str(capsys.readouterr().out))
    assert advanced["idempotent_replay"] is False
    assert advanced["event_cursor"] == 2

    assert main(["advance", "--world", world_id, "--key", "cli-key-1"]) == 0
    replay = json.loads(str(capsys.readouterr().out))
    assert replay["idempotent_replay"] is True
    assert replay["event_id"] == advanced["event_id"]

    assert main(["inspect", "world", "--world", world_id]) == 0
    inspected = json.loads(str(capsys.readouterr().out))
    assert inspected["world"]["phase"] == "sunrise"
    assert len(inspected["characters"]) == 2
    assert len(inspected["locations"]) == 2
    assert inspected["open_run"] is None

    assert main(["inspect", "events", "--world", world_id, "--after", "0"]) == 0
    timeline = json.loads(str(capsys.readouterr().out))
    assert timeline["next_after"] == 2
    assert [entry["sequence"] for entry in timeline["entries"]] == [1, 2]

    assert main(["reconcile", "--world", world_id]) == 0
    reconciled = json.loads(str(capsys.readouterr().out))
    assert reconciled["open_run_id"] is None

    assert main(["inspect", "task", "--task", advanced["task_id"]]) == 0
    task = json.loads(str(capsys.readouterr().out))
    assert task["state"] == "succeeded"
    assert task["kind"] == "phase_advance"


def test_cli_unknown_world_fails_cleanly(
    migrated_db: None, capsys: pytest.CaptureFixture[str]
) -> None:
    code = main(["advance", "--world", "10000000-0000-4000-8000-000000009999", "--key", "k"])
    assert code == 1
    err = str(capsys.readouterr().err)
    assert "NOT_FOUND" in err
