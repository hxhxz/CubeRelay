"""Unit and MuJoCo integration tests for complete six-face active perception."""

from __future__ import annotations

import importlib.util
import os

import numpy as np
import pytest

from cube_relay.embodied.canonical_facelets import FACE_FRAMES, cube_rotations_24
from cube_relay.embodied.mujoco_v2 import MuJoCoEmbodiedBackend
from cube_relay.embodied.six_face_inspection import (
    InformationGainViewPlanner,
    SixFaceActiveInspector,
    estimate_orientation_from_centers,
    face_normal_world,
    held_visible_faces,
)
from cube_relay.embodied.task_agent_v7 import EmbodiedTaskAgent, RuleTaskPlanner

_SKIP_MUJOCO_GL = (
    os.environ.get("CUBERELAY_SKIP_GL_TESTS", "0") == "1"
    or importlib.util.find_spec("mujoco") is None
)


def test_two_orthogonal_center_colors_uniquely_determine_all_24_orientations() -> None:
    for rotation in cube_rotations_24():
        constraints = [
            ("U", face_normal_world("U", rotation), "top"),
            ("F", face_normal_world("F", rotation), "front"),
        ]
        estimate = estimate_orientation_from_centers(constraints)
        assert estimate.unique
        assert estimate.consistent_constraints == 2
        assert estimate.matrix is not None
        np.testing.assert_allclose(estimate.matrix, rotation, atol=1e-6)


def test_information_gain_planner_selects_pitch_to_expose_missing_bottom_face() -> None:
    planner = InformationGainViewPlanner()
    rotation = np.eye(3)
    # In gripper frame, +Z points from the cube toward the palm (upward when unpitched).
    gripper = {
        "finger_closure_axis": [0.0, 1.0, 0.0],
        "palm_direction": [0.0, 0.0, 1.0],
    }
    assert set(held_visible_faces(
        rotation,
        np.asarray(gripper["finger_closure_axis"]),
        np.asarray(gripper["palm_direction"]),
    )) == {"R", "L"}
    needed = {"U": 0, "R": 0, "F": 0, "D": 9, "L": 0, "B": 0}
    options = planner.options(rotation, gripper, pitch_angle=0.0, yaw_angle=0.0, needed=needed)
    assert options[0].axis == "pitch"
    assert options[0].gain == 9
    assert "D" in options[0].visible_faces


@pytest.mark.skipif(_SKIP_MUJOCO_GL, reason="MuJoCo GL tests skipped or mujoco not installed")
def test_six_face_active_inspector_reconstructs_exact_54_facelets_without_truth() -> None:
    backend = MuJoCoEmbodiedBackend(width=320, height=240)
    try:
        metadata = backend.reset_random(seed=0, scramble_steps=15)
        truth = str(metadata["truth_for_evaluation_only"])
        result = SixFaceActiveInspector(backend).run(seed=0, reset_scene=False)
        assert result.success
        assert result.complete
        assert result.legal
        assert result.reconstructed_facelets == truth
        assert all(item["source_view"] != "simulator_truth" for item in result.evidence)
    finally:
        backend.renderer.close()


@pytest.mark.skipif(_SKIP_MUJOCO_GL, reason="MuJoCo GL tests skipped or mujoco not installed")
def test_embodied_task_agent_completes_54_sticker_reconstruction_on_random_scene() -> None:
    backend = MuJoCoEmbodiedBackend(width=320, height=240)
    try:
        metadata = backend.reset_random(seed=1, scramble_steps=15)
        truth = str(metadata["truth_for_evaluation_only"])
        result = EmbodiedTaskAgent(backend, RuleTaskPlanner()).run(seed=1, reset_scene=False)
        assert result.success
        assert result.legal
        assert result.unknown_stickers == 0
        assert result.observed_faces == 6
        assert result.reconstructed_facelets == truth
    finally:
        backend.renderer.close()
