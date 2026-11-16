from __future__ import annotations

import numpy as np

from cube_relay.cube import CubeEngine
from cube_relay.embodied.canonical_facelets import (
    FACE_FRAMES,
    canonical_local_centers,
    cube_rotations_24,
    project_points,
    remap_observation_values,
    solve_canonical_mapping,
)
from cube_relay.embodied.facelet_mapping import order_quad
from cube_relay.embodied.v2_types import CameraCalibration


SCRAMBLED = CubeEngine().apply_moves(
    "UUUUUUUUURRRRRRRRRFFFFFFFFFDDDDDDDDDLLLLLLLLLBBBBBBBBB",
    "R U2 F' L D B2 R' U F2",
)


def _camera_for_face(rotation: np.ndarray, face: str, oblique: float = 0.0) -> CameraCalibration:
    normal = rotation @ np.asarray(FACE_FRAMES[face].normal, dtype=float)
    row = rotation @ np.asarray(FACE_FRAMES[face].row, dtype=float)
    camera_position = normal * .62 + row * oblique
    forward = -camera_position / np.linalg.norm(camera_position)
    up_hint = np.array([0.0, 0.0, 1.0])
    if abs(float(np.dot(forward, up_hint))) > .92:
        up_hint = np.array([0.0, 1.0, 0.0])
    right = np.cross(forward, up_hint)
    right /= np.linalg.norm(right)
    down = np.cross(forward, right)
    camera_to_world = np.eye(4)
    camera_to_world[:3, :3] = np.column_stack((right, down, forward))
    camera_to_world[:3, 3] = camera_position
    return CameraCalibration(420, 420, 160, 120, camera_to_world)


def _face_corners(rotation: np.ndarray, face: str,
                  calibration: CameraCalibration) -> np.ndarray:
    frame = FACE_FRAMES[face]
    normal = np.asarray(frame.normal, dtype=float) * .061
    row = np.asarray(frame.row, dtype=float) * .061
    column = np.asarray(frame.column, dtype=float) * .061
    local = np.stack((normal - row - column, normal - row + column,
                      normal + row + column, normal + row - column))
    return order_quad(project_points(local, np.zeros(3), rotation, calibration))


def _expected_assignment(rotation: np.ndarray, face: str,
                         calibration: CameraCalibration, corners: np.ndarray) -> tuple[int, ...]:
    projected = project_points(canonical_local_centers(face), np.zeros(3), rotation, calibration)
    # Independent nearest-neighbour grid labeling for the exact synthetic setup.
    from cube_relay.embodied.canonical_facelets import _observed_grid_centers
    observed = _observed_grid_centers(corners)
    return tuple(int(np.argmin(np.linalg.norm(projected - point, axis=1))) for point in observed)


def test_all_24_orientations_six_faces_and_oblique_projection() -> None:
    mirrored_seen = False
    for rotation in cube_rotations_24():
        for face in "URFDLB":
            for oblique in (0.0, .12):
                calibration = _camera_for_face(rotation, face, oblique)
                corners = _face_corners(rotation, face, calibration)
                decision = solve_canonical_mapping(
                    face, corners, np.zeros(3), rotation, calibration,
                )
                assert decision.reliable, (face, oblique, decision)
                assert decision.observed_to_canonical == _expected_assignment(
                    rotation, face, calibration, corners
                )
                mirrored_seen |= decision.mirrored
    assert mirrored_seen


def test_fixed_scramble_distinguishes_rotation_mirror_and_color_errors() -> None:
    rotation = cube_rotations_24()[7]
    face = "R"
    calibration = _camera_for_face(rotation, face, .10)
    corners = _face_corners(rotation, face, calibration)
    decision = solve_canonical_mapping(face, corners, np.zeros(3), rotation, calibration)
    expected = SCRAMBLED[9:18]
    observed = [None] * 9
    for observed_index, canonical_index in enumerate(decision.observed_to_canonical):
        observed[observed_index] = expected[canonical_index]
    assert "".join(remap_observation_values(tuple(observed), decision.observed_to_canonical)) == expected
    wrong_rotation = tuple(np.roll(observed, 1))
    assert remap_observation_values(wrong_rotation, decision.observed_to_canonical) != tuple(expected)


def test_face_identity_mismatch_is_unknown_not_forced_assignment() -> None:
    rotation = np.eye(3)
    calibration = _camera_for_face(rotation, "F")
    corners = _face_corners(rotation, "F", calibration)
    decision = solve_canonical_mapping("B", corners, np.zeros(3), rotation, calibration)
    assert not decision.reliable
    assert decision.reason == "face_identity_mismatch:B!=F"


def test_cube_engine_to_mujoco_coordinate_convention_is_explicit() -> None:
    assert FACE_FRAMES["U"].normal == (0, 0, 1)
    assert FACE_FRAMES["F"].normal == (0, -1, 0)
    assert FACE_FRAMES["R"].normal == (1, 0, 0)
    handedness = {"U": 1, "D": 1, "F": -1, "B": -1, "R": -1, "L": -1}
    for face, frame in FACE_FRAMES.items():
        normal, row, column = map(np.asarray, (frame.normal, frame.row, frame.column))
        assert np.dot(normal, row) == np.dot(normal, column) == np.dot(row, column) == 0
        assert np.array_equal(np.cross(column, row), handedness[face] * normal), face
