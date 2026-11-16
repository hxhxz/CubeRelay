import numpy as np

from cube_relay.cube import SOLVED_FACELETS
from cube_relay.embodied.mock_v2 import MockEmbodiedBackend
from cube_relay.embodied.perception_v2 import DeterministicCubeLocalizer, StickerStateFusion
from cube_relay.embodied.v2_controller import EmbodiedV2Controller
from cube_relay.embodied.v2_types import (
    CameraCalibration,
    EmbodiedState,
    FaceObservation,
    RGBDFrame,
)
from cube_relay.embodied.vlm import HeuristicSceneVLM


def test_contour_corner_yaw_estimator_avoids_square_pca_ambiguity() -> None:
    angle = .37
    edge = np.linspace(-.06, .06, 50)
    square = np.concatenate([
        np.column_stack((edge, np.full_like(edge, -.06))),
        np.column_stack((edge, np.full_like(edge, .06))),
        np.column_stack((np.full_like(edge, -.06), edge)),
        np.column_stack((np.full_like(edge, .06), edge)),
    ])
    rotation = np.array([
        [np.cos(angle), -np.sin(angle)],
        [np.sin(angle), np.cos(angle)],
    ])
    xy = square @ rotation.T
    points = np.column_stack((xy, np.full(len(xy), .72)))
    estimated, confidence = DeterministicCubeLocalizer._yaw_from_world_contour(points)
    error = abs((estimated - angle + np.pi / 4) % (np.pi / 2) - np.pi / 4)
    assert error < .02
    assert confidence > .95


def test_v2_declares_required_states_and_recovery_states() -> None:
    required = {
        "SEARCHING", "GRASPING", "ACTIVE_SCANNING", "STATE_VALIDATING", "SOLVING",
        "ROBOT_MANIPULATING", "HANDING_OVER", "HUMAN_MANIPULATING", "TAKING_BACK",
        "REOBSERVING", "COMPLETED",
    }
    assert required <= {state.value for state in EmbodiedState}
    assert any(state.value.startswith("RECOVERING_") for state in EmbodiedState)


def test_rgbd_localizer_backprojects_pixels_without_simulator_state() -> None:
    rgb = np.zeros((20, 20, 3), dtype=np.uint8)
    rgb[5:15, 5:15] = [230, 20, 20]
    depth = np.full((20, 20), 2.0)
    calibration = CameraCalibration(100, 100, 10, 10, np.eye(4))
    detection = DeterministicCubeLocalizer(min_pixels=20).locate(
        RGBDFrame(rgb, depth, calibration, "synthetic", 0)
    )
    assert detection is not None
    assert np.allclose(detection.center_world_m, (-.01, -.01, 2.06), atol=.011)
    assert detection.source == "rgbd_deterministic"


def test_six_face_fusion_and_independent_legality_validation() -> None:
    fusion = StickerStateFusion()
    for index, face in enumerate("URFDLB"):
        fusion.add(FaceObservation(face, tuple(face * 9), .9, index))
    assert fusion.observed_face_count == 6
    assert fusion.validated_facelets() == SOLVED_FACELETS


def test_occluded_stickers_remain_unknown_until_pixel_reobservation() -> None:
    fusion = StickerStateFusion()
    partial = ("U", "U", None, "U", "U", "U", "U", "U", "U")
    fusion.add(FaceObservation(
        "U", partial, .8, 1, (0.8,) * 9, "gripper_occluded_view"
    ))
    assert fusion.unknown_count == 46
    assert fusion.evidence[2].occluded
    assert len(fusion.fused_evidence()) == 54
    fusion.add(FaceObservation(
        "U", tuple("U" * 9), .9, 2, (0.9,) * 9, "released_reobservation"
    ))
    for index, face in enumerate("RFDLB", start=1):
        source = "side_placed_bottom_view" if face == "D" else "released_side_view"
        fusion.add(FaceObservation(face, tuple(face * 9), .9, index + 2,
                                   (0.9,) * 9, source))
    assert fusion.unknown_count == 0
    assert fusion.validated_facelets() == SOLVED_FACELETS
    assert any(item.face == "D" and item.source_view == "side_placed_bottom_view"
               for item in fusion.evidence)


def test_controller_runs_pixel_to_completed_closed_loop_with_explicit_mock() -> None:
    backend = MockEmbodiedBackend()
    result = EmbodiedV2Controller(backend, HeuristicSceneVLM()).run(scramble_steps=0)
    assert result.solved
    assert result.terminal_state is EmbodiedState.COMPLETED
    states = [event.state for event in result.events]
    assert states[:5] == [
        "SEARCHING", "GRASPING", "ACTIVE_SCANNING", "STATE_VALIDATING", "SOLVING"
    ]
    assert result.metrics.extra["implementation_level"].startswith("MOCK")


def test_controller_records_search_recovery() -> None:
    backend = MockEmbodiedBackend(fail_first_search=True)
    result = EmbodiedV2Controller(backend, HeuristicSceneVLM()).run(scramble_steps=0)
    assert result.solved
    assert result.metrics.recoveries == 1
    assert "RECOVERING_SEARCH" in [event.state for event in result.events]
