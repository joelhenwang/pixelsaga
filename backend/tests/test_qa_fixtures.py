import socket
from typing import Any

import pytest
from fixtures.clocks import FakeOperationalClock, FictionalClock
from fixtures.fake_model_gateway import FakeModelError, FakeModelGateway, ModelErrorKind
from fixtures.faults import FaultHooks
from fixtures.randomness import SeededRandomSource
from fixtures.scenario import StageScenario
from psycopg import Connection


def test_operational_clock_advances_deterministically(
    operational_clock: FakeOperationalClock,
) -> None:
    assert operational_clock.now_ms() == 0
    assert operational_clock.advance_ms(1500) == 1500
    assert operational_clock.now_ms() == 1500


def test_clocks_are_isolated_per_test(
    operational_clock: FakeOperationalClock, fictional_clock: FictionalClock
) -> None:
    assert operational_clock.now_ms() == 0
    assert fictional_clock.position() == {"day": 1, "phase_index": 0}


def test_fictional_clock_phase_order_and_day_rollover(
    fictional_clock: FictionalClock,
) -> None:
    assert fictional_clock.phase == "dawn"
    for _ in range(9):
        fictional_clock.advance_phase()
    assert fictional_clock.phase == "midnight"
    assert fictional_clock.advance_phase() == "dawn"
    assert fictional_clock.position() == {"day": 2, "phase_index": 0}


def test_seeded_random_reproducible(random_source: SeededRandomSource) -> None:
    first = [random_source.integers(1, 100) for _ in range(5)]
    twin = SeededRandomSource(seed=1234)
    assert [twin.integers(1, 100) for _ in range(5)] == first
    other = SeededRandomSource(seed=999)
    assert [other.integers(1, 100) for _ in range(5)] != first


def test_fake_gateway_scripts_and_records(model_gateway: FakeModelGateway) -> None:
    model_gateway.enqueue_response("hello", prompt_tokens=3, completion_tokens=2)
    model_gateway.enqueue_error(ModelErrorKind.RATE_LIMITED, "slow down")
    first = model_gateway.request("say hi")
    assert first.text == "hello"
    with pytest.raises(FakeModelError) as excinfo:
        model_gateway.request("again")
    assert excinfo.value.kind is ModelErrorKind.RATE_LIMITED
    assert [call.prompt for call in model_gateway.calls] == ["say hi", "again"]
    assert model_gateway.pending_count() == 0


def test_external_network_blocked_but_loopback_allowed() -> None:
    with pytest.raises(OSError, match="blocked"):
        socket.create_connection(("example.com", 80), timeout=2)
    server = socket.socket()
    try:
        server.bind(("127.0.0.1", 0))
        server.listen(1)
        port = server.getsockname()[1]
        client = socket.create_connection(("127.0.0.1", port), timeout=2)
        client.close()
    finally:
        server.close()


def test_postgres_transaction_rolls_back_between_tests_a(
    pg_conn: Connection[Any],
) -> None:
    pg_conn.execute("INSERT INTO qa_rollback_probe (note) VALUES ('probe-a')")
    assert pg_conn.execute("SELECT count(*) FROM qa_rollback_probe").fetchone() == (1,)


def test_postgres_transaction_rolls_back_between_tests_b(
    pg_conn: Connection[Any],
) -> None:
    assert pg_conn.execute("SELECT count(*) FROM qa_rollback_probe").fetchone() == (0,)


def test_pg_prior_connections_released(
    pg_conn: Connection[Any], tracked_connections: list[Connection[Any]]
) -> None:
    assert not pg_conn.closed
    for previous in tracked_connections[:-1]:
        assert previous.closed


def test_fault_hooks_inject_and_run(fault_hooks: FaultHooks) -> None:
    assert not fault_hooks.is_set("crash_after_commit")
    seen: list[str] = []
    fault_hooks.on("after_commit", lambda: seen.append("ack"))
    with fault_hooks.inject("crash_after_commit"):
        assert fault_hooks.is_set("crash_after_commit")
        assert fault_hooks.run("after_commit") == 1
    assert not fault_hooks.is_set("crash_after_commit")
    assert seen == ["ack"]


def test_scenario_skeleton_collects_evidence(stage_scenario: StageScenario) -> None:
    stage_scenario.add_step("first", lambda: "one")
    stage_scenario.add_step("second", lambda: 2)
    assert stage_scenario.run() == {
        "scenario": "qa-selftest",
        "step_count": 2,
        "steps": [
            {"name": "first", "result": "one"},
            {"name": "second", "result": 2},
        ],
    }
