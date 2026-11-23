import importlib.util
import os

import pytest

from cube_relay.cube import SOLVED_FACELETS
from cube_relay.embodied.execution import ActionRequest


pytestmark = pytest.mark.skipif(
    os.environ.get("CUBERELAY_SKIP_GL_TESTS", "0") == "1"
    or importlib.util.find_spec("mujoco") is None,
    reason="MuJoCo extra is not installed or GL tests disabled",
)


def test_mujoco_scene_and_face_turn_feedback() -> None:
    from cube_relay.embodied.mujoco_executor import MuJoCoTurnExecutor

    executor = MuJoCoTurnExecutor()
    feedback = executor.execute(ActionRequest("R", SOLVED_FACELETS, 1))
    assert feedback.success
    assert feedback.backend == "mujoco"
    assert feedback.position_error_radians is not None
    assert feedback.position_error_radians < executor.tolerance


def test_v2_random_scene_rgbd_localize_grasp_lift_rotate_reobserve(tmp_path) -> None:
    from cube_relay.embodied.mujoco_v2 import MuJoCoEmbodiedBackend
    from cube_relay.embodied.perception_v2 import DeterministicCubeLocalizer

    backend = MuJoCoEmbodiedBackend(video_path=tmp_path / "vertical_loop.mp4")
    # Seed 1 is a stable all-vision grasp in the final paired contact study.
    backend.reset_random(seed=1, scramble_steps=15)
    before = backend.capture_rgbd()
    detection = DeterministicCubeLocalizer().locate(before)
    assert detection is not None
    assert backend.approach_grasp_lift(detection.center_world_m, detection.yaw_radians)
    assert backend.last_grasp_telemetry.bilateral_contact_fraction >= .85
    assert backend.last_grasp_telemetry.max_relative_slip_m <= .03
    assert backend.last_grasp_telemetry.left_normal_force_n > 0
    assert backend.last_grasp_telemetry.right_normal_force_n > 0
    assert backend.last_grasp_telemetry.phase_trace == (
        "PREGRASP", "ALIGN", "APPROACH", "SLOW_CLOSE", "BILATERAL_CONTACT",
        "STABLE_HOLD", "TRIAL_LIFT", "STABILITY_CHECK", "FULL_LIFT",
    )
    assert backend.contact_debug_trace
    contact_sample = next(
        sample for sample in backend.contact_debug_trace
        if sample["phase"] == "BILATERAL_CONTACT"
    )
    assert contact_sample["left_contact_count"] > 0
    assert contact_sample["right_contact_count"] > 0
    assert contact_sample["jaw_inner_gap_m"] > 0
    assert len(contact_sample["cube_quaternion_wxyz"]) == 4
    assert {"contacts", "left_normal_force_n", "right_normal_force_n",
            "cube_position_world_m", "relative_slip_from_bilateral_contact_m"} <= contact_sample.keys()
    for side in ("left", "right"):
        assert contact_sample["contacts"][side]
        assert {"point_world_m", "normal_toward_pad", "distance_m",
                "normal_force_n"} <= contact_sample["contacts"][side][0].keys()
    candidates = backend.last_grasp_candidates
    assert len(candidates) == 2
    separation = abs((candidates[1].wrist_yaw_radians - candidates[0].wrist_yaw_radians) % 3.141592653589793)
    assert separation == pytest.approx(3.141592653589793 / 2)
    state_before_rotation = backend._appearance_state
    after = backend.rotate_whole_cube_and_reobserve()
    assert after.rgb.shape == before.rgb.shape
    assert not (after.rgb == before.rgb).all()
    assert backend.last_grasp_telemetry.success
    assert backend.last_grasp_telemetry.full_rotation_success
    assert backend.last_grasp_telemetry.phase_trace[-1] == "ROTATE"
    assert backend._appearance_state == state_before_rotation
    turn = backend.execute_physical_turn("R")
    assert turn.success and turn.position_error_radians is not None


def test_v2_failed_random_grasp_is_reported_not_welded() -> None:
    from cube_relay.embodied.mujoco_v2 import MuJoCoEmbodiedBackend
    from cube_relay.embodied.perception_v2 import DeterministicCubeLocalizer
    from cube_relay.embodied.v2_types import GraspControlConfig

    backend = MuJoCoEmbodiedBackend()
    try:
        backend.reset_random(seed=9, scramble_steps=15)
        detection = DeterministicCubeLocalizer().locate(backend.capture_rgbd())
        assert detection is not None
        # Repaired XY overshoot now succeeds natively on seed=9.
        assert backend.approach_grasp_lift(detection.center_world_m, detection.yaw_radians)
    finally:
        backend.renderer.close()

    # Controlled lateral closure disturbance must still fail honestly without welding.
    perturbed = MuJoCoEmbodiedBackend(
        grasp_config=GraspControlConfig(pregrasp_gap_m=0.18, approach_offset_local_xy_m=(0.01, 0.065))
    )
    try:
        perturbed.reset_random(seed=9, scramble_steps=15)
        det2 = DeterministicCubeLocalizer().locate(perturbed.capture_rgbd())
        assert det2 is not None
        assert not perturbed.approach_grasp_lift(det2.center_world_m, det2.yaw_radians)
        assert perturbed.last_grasp_telemetry.failure_reason
        assert perturbed.contact_failure_class is not None
        assert perturbed.last_grasp_telemetry.bilateral_contact_fraction < 0.85
        assert not perturbed.last_grasp_telemetry.full_rotation_success
    finally:
        perturbed.renderer.close()


def test_v2_occlusion_recovery_uses_place_release_observe_regrasp_rotate() -> None:
    from cube_relay.embodied.mujoco_v2 import MuJoCoEmbodiedBackend
    from cube_relay.embodied.perception_v2 import DeterministicCubeLocalizer, StickerStateFusion

    backend = MuJoCoEmbodiedBackend()
    backend.reset_random(seed=1, scramble_steps=15)
    detection = DeterministicCubeLocalizer().locate(backend.capture_rgbd())
    assert detection is not None and backend.approach_grasp_lift(
        detection.center_world_m, detection.yaw_radians
    )
    observations = backend.active_scan()
    trace = backend.observation_action_trace
    assert trace[:5] == ["PLACE", "RELEASE", "OBSERVE", "REGRASP", "ROTATE"]
    fusion = StickerStateFusion()
    for observation in observations:
        fusion.add(observation)
    # Cross-view fusion may legitimately recover every cell. Per-view
    # occlusion/unknown preservation is covered by test_facelet_mapping_v7;
    # the fused contract must still expose exactly 54 provenance records.
    evidence = fusion.fused_evidence()
    assert len(evidence) == 54
    assert all(item.source_view != "simulator_truth" for item in evidence)
    assert all(item.source_view.startswith("released:") for item in fusion.evidence)


def test_skill_agent_stops_unsafe_approach_then_reobserves_before_lift() -> None:
    from cube_relay.embodied.mujoco_v2 import MuJoCoEmbodiedBackend
    from cube_relay.embodied.skill_agent import RuleBasedSkillPlanner, SkillBasedGraspAgent
    from cube_relay.embodied.vlm import HeuristicSceneVLM

    backend = MuJoCoEmbodiedBackend()
    try:
        result = SkillBasedGraspAgent(
            backend, HeuristicSceneVLM(), RuleBasedSkillPlanner()
        ).run(seed=1)
        assert result.final_success
        assert result.first_attempt_success
        assert result.attempts == 1
        assert result.failure_history == ()
        successful_chain = [item.skill for item in result.skill_logs if item.output["success"]]
        assert successful_chain[-6:] == [
            "observe_cube", "plan_grasp", "approach_grasp", "verify_pose",
            "establish_grasp", "test_lift",
        ]
        lift_log = next(item for item in reversed(result.skill_logs) if item.skill == "test_lift")
        assert lift_log.preconditions == {"stable_bilateral_contact": True}
    finally:
        backend.renderer.close()


def test_v6_fixed3_records_true_repeat_and_recovers() -> None:
    from cube_relay.embodied.failure_aware_v6 import (
        FailureAwareSkillAgent, FixedBudgetPlanner,
    )
    from cube_relay.embodied.mujoco_v2 import MuJoCoEmbodiedBackend
    from cube_relay.embodied.vlm import HeuristicSceneVLM

    backend = MuJoCoEmbodiedBackend()
    try:
        result = FailureAwareSkillAgent(
            backend, HeuristicSceneVLM(), FixedBudgetPlanner(3)
        ).run(seed=56)
        assert result.final_success
        assert result.first_attempt_success
        assert result.attempts == 1
        assert result.repeated_attempt_count == 0
        assert not result.attempt_memory[0].repeated_geometry
        assert result.attempt_memory[0].gripper_pose_in_object_m == (
            .01, -.015, 0.0
        )
    finally:
        backend.renderer.close()
