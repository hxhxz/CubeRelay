import math
from types import SimpleNamespace

import pytest

from cube_relay.cube import CubeEngine, SOLVED_FACELETS, LEGAL_MOVES
from cube_relay.embodied.visual_turn_loop import plan_visual_state, compare_observations
from cube_relay.embodied.execution import ActionRequest, ActionFeedback


def observations(state):
    return [SimpleNamespace(face=face, stickers=list(state[i*9:(i+1)*9]),
                            confidence=1., sticker_confidences=None,
                            source_view="camera:test", frame_index=i)
            for i, face in enumerate("URFDLB")]


def test_visual_solution_independent_symbolic_rollout():
    state = CubeEngine().apply_moves(SOLVED_FACELETS, "R U F2 L D' B")
    plan = plan_visual_state(state)
    assert plan["input_state"] == state
    assert plan["symbolic_final"] == SOLVED_FACELETS


def test_missing_conflict_and_mismatch_are_not_success():
    obs = observations(SOLVED_FACELETS)
    assert compare_observations(SOLVED_FACELETS, obs)["status"] == "VISUALLY_VERIFIED"
    assert compare_observations(SOLVED_FACELETS, obs[:5])["status"] == "UNVERIFIED_INSUFFICIENT_EVIDENCE"
    wrong = observations(CubeEngine().apply_move(SOLVED_FACELETS, "R"))
    assert compare_observations(SOLVED_FACELETS, wrong)["status"] == "VISUAL_MISMATCH"
    assert compare_observations(SOLVED_FACELETS, obs + wrong)["status"] == "UNVERIFIED_CONFLICT"


@pytest.mark.parametrize("move", LEGAL_MOVES)
def test_all_hinge_directions_and_feedback(move):
    from cube_relay.embodied.mujoco_executor import MuJoCoTurnExecutor
    executor = MuJoCoTurnExecutor()
    feedback = executor.execute(ActionRequest(move, SOLVED_FACELETS, 1))
    assert feedback.success
    final = executor.last_trace[-1]
    turns = 2 if move.endswith("2") else -1 if move.endswith("'") else 1
    assert final["target_radians"] == pytest.approx(-turns * math.pi / 2)
    assert final["actual_radians"] == pytest.approx(final["target_radians"], abs=.03)
    assert final["velocity_radians_s"] < .08
    assert not final["plate_collision_enabled"]  # Explicit model boundary, not contact verification.


def test_failed_feedback_cannot_commit_appearance():
    from cube_relay.embodied.mujoco_v2 import MuJoCoEmbodiedBackend
    backend = object.__new__(MuJoCoEmbodiedBackend)
    backend._appearance_state = SOLVED_FACELETS
    backend._plan_version = 1
    backend._turner = SimpleNamespace(execute=lambda request:
        ActionFeedback(False, request.move, 0, 1, "test", "timeout"))
    assert not backend.execute_physical_turn("R").success
    assert backend._appearance_state == SOLVED_FACELETS


def test_strict_scene_audit_blocks_legacy_fixture_penetration(tmp_path):
    from cube_relay.embodied.mujoco_executor import MuJoCoTurnExecutor
    from pathlib import Path
    model = Path(__file__).resolve().parents[1] / "simulation/cube_relay.xml"
    broken = tmp_path / "legacy.xml"
    broken.write_text(model.read_text().replace('fromto="0 0 .06 0 0 .42"', 'fromto="0 0 0 0 0 .42"'))
    executor = MuJoCoTurnExecutor(broken)
    executor.require_scene_safety = True
    feedback = executor.execute(ActionRequest("U'", SOLVED_FACELETS, 1))
    assert not feedback.success
    assert feedback.detail == "UNSAFE_SCENE_CONTACT"
    assert len(executor.last_trace) == 1


def test_repaired_fixture_passes_strict_scene_check():
    from cube_relay.embodied.mujoco_executor import MuJoCoTurnExecutor
    executor = MuJoCoTurnExecutor()
    executor.require_scene_safety = True
    assert executor.execute(ActionRequest("U'", SOLVED_FACELETS, 1)).success
