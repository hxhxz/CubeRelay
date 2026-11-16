from datetime import UTC, datetime

import pytest

from cube_relay.adapters.dryrun_robot import DryRunRobotAdapter
from cube_relay.adapters.sim_robot import SimRobotAdapter
from cube_relay.agent import TurnCoordinator
from cube_relay.cube import CubeEngine, SOLVED_FACELETS
from cube_relay.models import CubeObservation


def scrambled(seed=1):
    return CubeEngine().scramble(seed, 10)[0]


def test_unexpected_human_move_replans_from_actual() -> None:
    coordinator = TurnCoordinator(SimRobotAdapter())
    state = coordinator.start(scrambled())
    old_plan, old_version = state.planned_moves.copy(), state.plan_version
    unexpected = next(move for move in ("F", "R", "U") if move != old_plan[0])
    expected_actual = CubeEngine().apply_move(state.actual_state, unexpected)
    coordinator.submit_human_move(unexpected)
    assert state.actual_state == expected_actual
    assert state.plan_version == old_version + 1
    assert state.planned_moves != old_plan[1:]
    assert CubeEngine().is_solved(CubeEngine().apply_moves(state.actual_state, state.planned_moves))


def test_stale_robot_action_is_rejected_and_version_changes_only_on_replan() -> None:
    coordinator = TurnCoordinator(SimRobotAdapter())
    state = coordinator.start(scrambled(2))
    recommended = state.planned_moves[0]
    coordinator.submit_human_move(recommended)
    assert state.plan_version == 1
    with pytest.raises(RuntimeError, match="stale"):
        coordinator.execute_robot_turn(plan_version=0)


@pytest.mark.parametrize("fault", ["no-op", "F"])
def test_robot_fault_uses_observed_state_and_repairs(fault: str) -> None:
    coordinator = TurnCoordinator(SimRobotAdapter(faults=[fault]))
    state = coordinator.start(scrambled(3))
    coordinator.submit_human_move(state.planned_moves[0])
    before, version = state.actual_state, state.plan_version
    coordinator.execute_robot_turn()
    assert state.plan_version == version + 1
    assert any(event.kind == "STATE_MISMATCH" for event in coordinator.events)
    assert any(event.kind == "PLANNING_STARTED" for event in coordinator.events)
    assert any(event.kind == "PLANNING_FINISHED" for event in coordinator.events)
    assert CubeEngine().is_solved(CubeEngine().apply_moves(state.actual_state, state.planned_moves))
    if fault == "no-op":
        assert state.actual_state == before


def test_dry_run_never_updates_actual_state() -> None:
    adapter = DryRunRobotAdapter()
    coordinator = TurnCoordinator(adapter, "dry_run")
    state = coordinator.start(scrambled(4))
    coordinator.submit_human_move(state.planned_moves[0])
    before = state.actual_state
    coordinator.execute_robot_turn()
    assert state.actual_state == before
    assert state.status == "paused"
    assert adapter.requests[0]["safety_mode"] == "disabled-output"


def test_manual_override_requires_confidence_confirmation_and_replans_from_override() -> None:
    coordinator = TurnCoordinator(SimRobotAdapter())
    state = coordinator.start(scrambled(5))
    target = scrambled(6)
    timestamp = datetime.now(UTC).isoformat()
    low = CubeObservation(facelets=target, source="manual", confidence=.2,
                          timestamp=timestamp, confirmed=True)
    coordinator.override_observation(low)
    assert state.status == "paused"
    assert state.actual_state != target
    confirmed = CubeObservation(facelets=target, source="manual", confidence=1,
                                timestamp=timestamp, confirmed=True)
    coordinator.override_observation(confirmed)
    assert state.actual_state == target
    assert state.status == "running"
    assert CubeEngine().is_solved(CubeEngine().apply_moves(target, state.planned_moves))


def test_solved_session_refuses_more_moves() -> None:
    coordinator = TurnCoordinator(SimRobotAdapter())
    coordinator.start(SOLVED_FACELETS)
    with pytest.raises(RuntimeError, match="already solved"):
        coordinator.submit_human_move("R")


def test_machine_status_and_execution_events_are_exposed() -> None:
    coordinator = TurnCoordinator(SimRobotAdapter())
    state = coordinator.start(scrambled(10))
    coordinator.submit_human_move(state.planned_moves[0])
    assert state.machine_status == "ready"
    coordinator.execute_robot_turn()
    assert state.machine_status == "idle"
    kinds = [event.kind for event in coordinator.events]
    assert "ROBOT_EXECUTION_STARTED" in kinds
    assert "ROBOT_VERIFYING" in kinds
