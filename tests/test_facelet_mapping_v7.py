from __future__ import annotations

import numpy as np

from cube_relay.embodied.facelet_mapping import (
    PerspectiveFaceletMapper,
    homography,
    warp_perspective,
)
from cube_relay.embodied.perception_v2 import DeterministicCubePose6DEstimator
from cube_relay.embodied.v2_types import CameraCalibration, RGBDFrame


PALETTE = {
    "U": (235, 235, 235), "R": (220, 20, 13), "F": (8, 174, 31),
    "D": (242, 209, 10), "L": (255, 87, 5), "B": (8, 51, 230),
}
FACE = ("U", "R", "F", "L", "U", "B", "D", "F", "R")


def _canonical_face(size: int = 180) -> np.ndarray:
    image = np.zeros((size, size, 3), dtype=np.uint8)
    margin = 5
    for index, symbol in enumerate(FACE):
        row, col = divmod(index, 3)
        y0, y1 = row * size // 3 + margin, (row + 1) * size // 3 - margin
        x0, x1 = col * size // 3 + margin, (col + 1) * size // 3 - margin
        image[y0:y1, x0:x1] = PALETTE[symbol]
    return image


def _project(image: np.ndarray, corners: np.ndarray, output_size: int = 240) -> np.ndarray:
    size = image.shape[0]
    canonical = np.array([[0, 0], [size - 1, 0], [size - 1, size - 1], [0, size - 1]])
    canonical_from_output = homography(corners, canonical)
    return warp_perspective(image, canonical_from_output, output_size)


def test_maps_frontal_face_to_canonical_cube_indices() -> None:
    mapper = PerspectiveFaceletMapper()
    image = _canonical_face()
    corners = np.array([[0, 0], [179, 0], [179, 179], [0, 179]], dtype=float)
    mapped = mapper.map_face(
        image, frame_index=4, source_view="controlled:front",
        corners_xy=corners, face_hint="U",
    )
    assert mapped is not None
    assert mapped.observation.stickers == FACE
    assert mapped.observation.source_view == "controlled:front"


def test_homography_recovers_oblique_face() -> None:
    corners = np.array([[39, 26], [203, 49], [183, 211], [21, 183]], dtype=float)
    projected = _project(_canonical_face(), corners)
    mapped = PerspectiveFaceletMapper().map_face(
        projected, frame_index=0, source_view="controlled:oblique",
        corners_xy=corners, face_hint="U",
    )
    assert mapped is not None
    assert mapped.observation.stickers == FACE


def test_flipped_view_uses_explicit_cube_local_rotation() -> None:
    image = np.rot90(_canonical_face(), k=2)
    corners = np.array([[0, 0], [179, 0], [179, 179], [0, 179]], dtype=float)
    mapped = PerspectiveFaceletMapper().map_face(
        image, frame_index=1, source_view="controlled:flip",
        corners_xy=corners, face_hint="U", rotation_quarter_turns=2,
    )
    assert mapped is not None
    assert mapped.observation.stickers == FACE


def test_occluded_cell_remains_unknown_and_is_not_filled() -> None:
    image = _canonical_face()
    image[65:115, 5:55] = 0
    corners = np.array([[0, 0], [179, 0], [179, 179], [0, 179]], dtype=float)
    mapped = PerspectiveFaceletMapper().map_face(
        image, frame_index=2, source_view="controlled:occluded",
        corners_xy=corners, face_hint="U",
    )
    assert mapped is not None
    assert mapped.observation.stickers[3] is None
    assert mapped.observation.sticker_confidences[3] == 0.0
    assert all(
        actual == expected for index, (actual, expected) in enumerate(
            zip(mapped.observation.stickers, FACE)
        ) if index != 3
    )


def test_mapped_face_and_metric_depth_produce_full_6d_pose() -> None:
    image = _canonical_face()
    corners = np.array([[40, 40], [160, 40], [160, 160], [40, 160]], dtype=float)
    mapped = PerspectiveFaceletMapper().map_face(
        image, frame_index=3, source_view="controlled:rgbd",
        corners_xy=np.array([[0, 0], [179, 0], [179, 179], [0, 179]], dtype=float),
        face_hint="F",
    )
    assert mapped is not None
    # Use the desired calibrated image corners while retaining the controlled
    # face observation. This isolates pose geometry from the color test above.
    mapped = type(mapped)(mapped.observation, tuple(map(tuple, corners)),
                          mapped.homography_image_from_canonical, mapped.canonical_rgb)
    frame = RGBDFrame(
        np.zeros((200, 200, 3), dtype=np.uint8), np.ones((200, 200), dtype=float),
        CameraCalibration(1000, 1000, 100, 100, np.eye(4)), "controlled", 0.0,
    )
    pose = DeterministicCubePose6DEstimator().estimate(frame, mapped)
    assert pose is not None
    rotation = np.asarray(pose.rotation_cube_to_world)
    np.testing.assert_allclose(rotation.T @ rotation, np.eye(3), atol=1e-6)
    np.testing.assert_allclose(pose.center_world_m, (0.0, 0.0, 1.06), atol=2e-3)
    # F outward normal is local -Y and must point toward the camera (-world Z).
    np.testing.assert_allclose(rotation @ np.array([0, -1, 0]), (0, 0, -1), atol=1e-6)
