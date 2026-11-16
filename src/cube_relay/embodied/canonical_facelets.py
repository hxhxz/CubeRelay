"""Single canonical face-coordinate convention for every camera path.

CubeEngine coordinates are (R, U, F), but facelet indices here are defined by
the actual ``sticker_FACE_0..8`` geometry in the MuJoCo XML. All frames below
are in MuJoCo cube-local coordinates. U/D and the four side faces intentionally
have different image-frame handedness; no global axis-swap shortcut is used.

Column direction points from canonical index 0 to 2; row direction points from
index 0 to 6. A cube-to-world matrix left-multiplies cube-local column vectors.
CameraCalibration.camera_to_world left-multiplies OpenCV camera vectors, so
world-to-camera is its rigid inverse.
"""

from __future__ import annotations

from dataclasses import dataclass
from itertools import permutations, product

import numpy as np

from .facelet_mapping import canonical_index, homography
from .v2_types import CameraCalibration


@dataclass(frozen=True, slots=True)
class CanonicalFaceFrame:
    normal: tuple[int, int, int]
    row: tuple[int, int, int]
    column: tuple[int, int, int]


FACE_FRAMES: dict[str, CanonicalFaceFrame] = {
    "U": CanonicalFaceFrame((0, 0, 1), (0, 1, 0), (1, 0, 0)),
    "D": CanonicalFaceFrame((0, 0, -1), (0, -1, 0), (1, 0, 0)),
    "F": CanonicalFaceFrame((0, -1, 0), (0, 0, -1), (1, 0, 0)),
    "B": CanonicalFaceFrame((0, 1, 0), (0, 0, -1), (-1, 0, 0)),
    "R": CanonicalFaceFrame((1, 0, 0), (0, 0, -1), (0, 1, 0)),
    "L": CanonicalFaceFrame((-1, 0, 0), (0, 0, -1), (0, -1, 0)),
}


@dataclass(frozen=True, slots=True)
class CanonicalMappingDecision:
    observed_to_canonical: tuple[int, ...]
    reliable: bool
    predicted_face: str
    face_identity_matches: bool
    mirrored: bool
    quarter_turns: int
    normalized_rms_error: float
    ambiguity_margin: float
    reason: str | None


def cube_rotations_24() -> tuple[np.ndarray, ...]:
    """The 24 proper signed-permutation rotations of a cube."""
    rotations = []
    for order in permutations(range(3)):
        for signs in product((-1, 1), repeat=3):
            matrix = np.zeros((3, 3))
            for column, row in enumerate(order):
                matrix[row, column] = signs[column]
            if round(np.linalg.det(matrix)) == 1:
                rotations.append(matrix)
    return tuple(rotations)


def axis_rotation(axis: np.ndarray, radians: float) -> np.ndarray:
    axis = np.asarray(axis, dtype=float)
    axis /= np.linalg.norm(axis)
    x, y, z = axis
    skew = np.array([[0, -z, y], [z, 0, -x], [-y, x, 0]])
    return np.eye(3) + np.sin(radians) * skew + (1 - np.cos(radians)) * (skew @ skew)


def align_face_rotation_to_reference(
    base_cube_to_world: np.ndarray, face: str, reference_cube_to_world: np.ndarray,
) -> tuple[np.ndarray, int, float]:
    """Resolve single-face fourfold pose ambiguity using an action-history anchor."""
    normal = np.asarray(FACE_FRAMES[face].normal, dtype=float)
    candidates = [
        np.asarray(base_cube_to_world) @ axis_rotation(normal, turn * np.pi / 2)
        for turn in range(4)
    ]
    errors = [float(np.linalg.norm(candidate - reference_cube_to_world))
              for candidate in candidates]
    best = int(np.argmin(errors))
    return candidates[best], best, errors[best]


def canonical_local_centers(face: str, sticker_offset_m: float = .039,
                            face_offset_m: float = .061) -> np.ndarray:
    frame = FACE_FRAMES[face]
    normal = np.asarray(frame.normal, dtype=float)
    row = np.asarray(frame.row, dtype=float)
    column = np.asarray(frame.column, dtype=float)
    return np.stack([
        normal * face_offset_m + row * ((r - 1) * sticker_offset_m)
        + column * ((c - 1) * sticker_offset_m)
        for r in range(3) for c in range(3)
    ])


def project_points(points_cube: np.ndarray, center_world_m: np.ndarray,
                   cube_to_world: np.ndarray,
                   calibration: CameraCalibration) -> np.ndarray:
    points_world = points_cube @ cube_to_world.T + center_world_m
    world_to_camera = np.linalg.inv(calibration.camera_to_world)
    homogeneous = np.column_stack((points_world, np.ones(len(points_world))))
    camera = homogeneous @ world_to_camera.T
    if np.any(camera[:, 2] <= 1e-6):
        raise ValueError("canonical face lies behind camera")
    return np.column_stack((
        calibration.fx * camera[:, 0] / camera[:, 2] + calibration.cx,
        calibration.fy * camera[:, 1] / camera[:, 2] + calibration.cy,
    ))


def _observed_grid_centers(corners_xy: np.ndarray) -> np.ndarray:
    canonical_quad = np.array([[0, 0], [1, 0], [1, 1], [0, 1]], dtype=float)
    image_from_unit = homography(canonical_quad, np.asarray(corners_xy, dtype=float))
    unit = np.array([[(c + .5) / 3, (r + .5) / 3, 1.0]
                     for r in range(3) for c in range(3)])
    image = unit @ image_from_unit.T
    return image[:, :2] / image[:, 2, None]


def predicted_visible_face(center_world_m: np.ndarray, cube_to_world: np.ndarray,
                           calibration: CameraCalibration) -> str:
    camera_world = calibration.camera_to_world[:3, 3]
    toward_camera = camera_world - center_world_m
    toward_camera /= np.linalg.norm(toward_camera)
    return max(FACE_FRAMES, key=lambda face: float(np.dot(
        cube_to_world @ np.asarray(FACE_FRAMES[face].normal), toward_camera
    )))


def projected_face_corners(face: str, center_world_m: np.ndarray,
                           cube_to_world: np.ndarray,
                           calibration: CameraCalibration,
                           half_extent_m: float = .061) -> np.ndarray:
    frame = FACE_FRAMES[face]
    normal = np.asarray(frame.normal, dtype=float) * half_extent_m
    row = np.asarray(frame.row, dtype=float) * half_extent_m
    column = np.asarray(frame.column, dtype=float) * half_extent_m
    local = np.stack((normal - row - column, normal - row + column,
                      normal + row + column, normal + row - column))
    from .facelet_mapping import order_quad
    return order_quad(project_points(
        local, np.asarray(center_world_m), np.asarray(cube_to_world), calibration
    ))


def solve_canonical_mapping(
    face: str,
    corners_xy: np.ndarray,
    center_world_m: tuple[float, float, float] | np.ndarray,
    cube_to_world: np.ndarray,
    calibration: CameraCalibration,
    *,
    max_normalized_error: float = .24,
    minimum_ambiguity_margin: float = .018,
) -> CanonicalMappingDecision:
    """Resolve observed grid cells to canonical indices via projected geometry."""
    center = np.asarray(center_world_m, dtype=float)
    rotation = np.asarray(cube_to_world, dtype=float)
    predicted_face = predicted_visible_face(center, rotation, calibration)
    projected = project_points(canonical_local_centers(face), center, rotation, calibration)
    observed = _observed_grid_centers(corners_xy)
    diagonal = max(float(np.linalg.norm(corners_xy[2] - corners_xy[0])), 1.0)
    candidates: list[tuple[float, bool, int, tuple[int, ...]]] = []
    for mirrored in (False, True):
        for quarter_turns in range(4):
            assignment = tuple(
                canonical_index(r, c, quarter_turns, mirrored)
                for r in range(3) for c in range(3)
            )
            residual = observed - projected[np.asarray(assignment)]
            error = float(np.sqrt(np.mean(np.sum(residual * residual, axis=1))) / diagonal)
            candidates.append((error, mirrored, quarter_turns, assignment))
    candidates.sort(key=lambda item: item[0])
    best, second = candidates[:2]
    identity_matches = predicted_face == face
    margin = second[0] - best[0]
    reliable = identity_matches and best[0] <= max_normalized_error \
        and margin >= minimum_ambiguity_margin
    reason = None
    if not identity_matches:
        reason = f"face_identity_mismatch:{face}!={predicted_face}"
    elif best[0] > max_normalized_error:
        reason = "projection_error"
    elif margin < minimum_ambiguity_margin:
        reason = "rotation_or_mirror_ambiguous"
    return CanonicalMappingDecision(
        best[3], reliable, predicted_face, identity_matches, best[1], best[2],
        best[0], margin, reason,
    )


def remap_observation_values(values: tuple[object, ...],
                             observed_to_canonical: tuple[int, ...]) -> tuple[object, ...]:
    output: list[object] = [None] * 9
    for observed_index, canonical in enumerate(observed_to_canonical):
        output[canonical] = values[observed_index]
    return tuple(output)
