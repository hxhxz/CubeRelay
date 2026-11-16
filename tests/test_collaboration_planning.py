import json
from pathlib import Path

from cube_relay.adapters.sim_robot import SimRobotAdapter
from cube_relay.agent import TurnCoordinator
from cube_relay.cube import CubeEngine, CubeSolver, inverse_move
from cube_relay.experiments.collaboration_audit import run_episode


FIXTURE = Path(__file__).resolve().parents[1] / "docs" / "cube-22c86967-d798-4c6b-8d04-8aa2eb3ce8a7.json"


def fixture_events():
    data = json.loads(FIXTURE.read_text(encoding="utf-8"))
    return {event["sequence"]: event for event in data["events"]}


def test_fixture_reproduces_both_solver_inverse_first_moves() -> None:
    events = fixture_events()
    solver, engine = CubeSolver(), CubeEngine()
    expected = {
        21: ["U", "F2", "U'", "F2", "L2", "U'", "D'", "F2"],
        28: ["R'", "F2", "U'", "F2", "L2", "U'", "D'", "F2"],
    }
    for human_sequence, robot_sequence, pre_human_sequence in ((21, 27, 20), (28, 34, 27)):
        human = events[human_sequence]
        robot = events[robot_sequence]
        solution = solver.solve(human["actual_state"])
        assert solution == expected[human_sequence]
        assert robot["move"] == solution[0] == inverse_move(human["move"])
        assert engine.apply_move(human["actual_state"], robot["move"]) == events[pre_human_sequence]["actual_state"]


def test_guided_shared_plan_requests_confirmation_for_two_consecutive_undos() -> None:
    initial = fixture_events()[20]["actual_state"]
    coordinator = TurnCoordinator(
        SimRobotAdapter(), collaboration_mode="guided_shared_plan"
    )
    state = coordinator.start(initial)
    assert state.planned_moves[0] == "F2"
    for human_move, robot_inverse in (("U'", "U"), ("R", "R'")):
        before = state.actual_state
        coordinator.submit_human_move(human_move)
        coordinator.execute_robot_turn()
        assert state.status == "paused"
        assert state.confirmation_reason == "UNDO_CONFLICT"
        assert state.pending_robot_move == robot_inverse
        coordinator.resolve_confirmation("allow_inverse")
        assert state.actual_state == before
        assert state.status == "running"
    conflicts = [event for event in coordinator.events if event.kind == "UNDO_CONFLICT"]
    assert len(conflicts) >= 2


def test_free_collaboration_executes_legal_inverse_then_pauses_on_repeat() -> None:
    initial = fixture_events()[20]["actual_state"]
    coordinator = TurnCoordinator(
        SimRobotAdapter(), collaboration_mode="free_collaboration"
    )
    state = coordinator.start(initial)
    coordinator.submit_human_move("U'")
    coordinator.execute_robot_turn()
    assert state.actual_state == initial
    assert state.status == "paused"
    assert state.confirmation_reason == "REPEATED_STATE"
    assert any(event.kind == "UNDO_CONFLICT" for event in coordinator.events)
    assert any(event.kind == "REPEATED_STATE" for event in coordinator.events)
    coordinator.resolve_confirmation("continue")
    assert state.status == "running" and state.next_actor == "human"


def test_guided_user_can_keep_human_move_and_get_valid_non_inverse_plan() -> None:
    initial = fixture_events()[20]["actual_state"]
    engine = CubeEngine()
    coordinator = TurnCoordinator(
        SimRobotAdapter(engine), engine=engine, collaboration_mode="guided_shared_plan"
    )
    state = coordinator.start(initial)
    coordinator.submit_human_move("U'")
    coordinator.execute_robot_turn()
    coordinator.resolve_confirmation("keep_human_move")
    assert state.status == "running"
    assert state.next_actor == "robot"
    assert state.planned_moves[0] != "U"
    assert engine.is_solved(engine.apply_moves(state.actual_state, state.planned_moves))


def test_normal_shared_plan_does_not_raise_undo_conflict() -> None:
    engine = CubeEngine()
    initial, _ = engine.scramble(44, 18)
    coordinator = TurnCoordinator(
        SimRobotAdapter(engine), engine=engine, collaboration_mode="guided_shared_plan"
    )
    state = coordinator.start(initial)
    coordinator.submit_human_move(state.planned_moves[0])
    coordinator.execute_robot_turn()
    assert state.status in {"running", "solved"}
    assert not any(event.kind == "UNDO_CONFLICT" for event in coordinator.events)


def test_random_interventions_remain_solvable_in_both_modes() -> None:
    engine = CubeEngine()
    for seed in range(10):
        initial, _ = engine.scramble(seed, 15 + seed % 6)
        before = run_episode(initial, policy="before_unconditional", seed=seed)
        after = run_episode(initial, policy="after_guided", seed=seed)
        assert before.success
        assert after.success
        assert after.undo_count == 0
