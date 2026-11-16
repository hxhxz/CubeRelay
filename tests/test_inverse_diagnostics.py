from pathlib import Path

from cube_relay.adapters.sim_robot import SimRobotAdapter
from cube_relay.agent import TurnCoordinator
from cube_relay.cube import CubeEngine, SOLVED_FACELETS, inverse_move
from cube_relay.experiments.inverse_diagnostics import random_scramble_cases
from cube_relay.policy import ActionIntent


def test_turn_diagnostic_contains_complete_actual_state_chain() -> None:
    engine = CubeEngine()
    initial, _ = engine.scramble(31, 18)
    coordinator = TurnCoordinator(SimRobotAdapter(engine), engine=engine)
    state = coordinator.start(initial)
    human_move = next(move for move in ("R", "F", "U") if move != state.planned_moves[0])
    before = state.actual_state
    coordinator.submit_human_move(human_move)
    after_human = state.actual_state
    coordinator.execute_robot_turn()
    detail = next(e.detail for e in coordinator.events if e.kind == "TURN_DIAGNOSTIC")
    assert detail["initial_cube_state"] == initial
    assert detail["state_before_human"] == before
    assert detail["human_move"] == human_move
    assert detail["state_after_human"] == after_human
    assert detail["solver_input_state"] == after_human
    assert detail["solver_solution"][0] == detail["robot_selected_move"]
    assert detail["is_inverse_of_human_move"] == (
        detail["robot_selected_move"] == inverse_move(human_move)
    )
    assert detail["state_after_robot"] == engine.apply_move(
        after_human, detail["robot_selected_move"]
    )


def test_random_diagnostic_generation_is_reproducible() -> None:
    left = random_scramble_cases(3, 9)
    right = random_scramble_cases(3, 9)
    assert [record.as_dict() for record in left] == [record.as_dict() for record in right]
    assert all(record.scramble_length in range(15, 21) for record in left)


def test_visual_direction_contract_matches_engine_notation() -> None:
    engine = CubeEngine()
    for face in "URFDLB":
        assert ActionIntent(face=face, turn="CW90", confidence=1, source="test").standard_move() == face
        assert ActionIntent(face=face, turn="CCW90", confidence=1, source="test").standard_move() == face + "'"
        assert ActionIntent(face=face, turn="HALF_TURN", confidence=1, source="test").standard_move() == face + "2"
        moved = engine.apply_move(SOLVED_FACELETS, face)
        assert engine.apply_move(moved, inverse_move(face)) == SOLVED_FACELETS
    css = (Path(__file__).resolve().parents[1] / "web" / "style.css").read_text()
    app = (Path(__file__).resolve().parents[1] / "web" / "app.js").read_text()
    assert "rotate(90deg)" in css and "rotate(-90deg)" in css and "rotate(180deg)" in css
    assert 'move.endsWith("2")' in app
    assert '?"ccw":"cw"' in app
    assert "s.actual_state" in app and "fi*9+i" in app
