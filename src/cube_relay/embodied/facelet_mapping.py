"""Deterministic perspective-correct facelet mapping from camera pixels.

The module never accepts simulator state. Ground truth is intentionally absent
from all APIs and may only be used by external evaluation code.
"""

from __future__ import annotations

import colorsys
from dataclasses import dataclass

import numpy as np

from .v2_types import FaceObservation


_REFERENCE_RGB = {
    "U": np.array([.92, .92, .92]), "R": np.array([.86, .08, .05]),
    "F": np.array([.03, .68, .12]), "D": np.array([.95, .82, .04]),
    "L": np.array([1.0, .34, .02]), "B": np.array([.03, .20, .90]),
}
_REFERENCE_HSV = {
    key: colorsys.rgb_to_hsv(*value) for key, value in _REFERENCE_RGB.items()
}


@dataclass(frozen=True, slots=True)
class MappedFace:
    observation: FaceObservation
    corners_xy: tuple[tuple[float, float], ...]
    homography_image_from_canonical: tuple[tuple[float, float, float], ...]
    canonical_rgb: np.ndarray


def classify_color(rgb: np.ndarray) -> tuple[str | None, float]:
    """Illumination-tolerant deterministic color classification."""
    value = np.asarray(rgb, dtype=float) / 255.0
    red, green, blue = np.clip(value, 0, 1)
    hue, saturation, brightness = colorsys.rgb_to_hsv(red, green, blue)
    if brightness < .18:
        return None, 0.0
    if saturation < .20:
        confidence = min(1.0, max(0.0, (brightness - .35) / .45))
        return ("U", confidence) if confidence >= .25 else (None, confidence)
    scores: dict[str, float] = {}
    for key, (ref_h, ref_s, _ref_v) in _REFERENCE_HSV.items():
        if key == "U":
            continue
        hue_distance = min(abs(hue - ref_h), 1 - abs(hue - ref_h))
        scores[key] = 4.5 * hue_distance + .12 * abs(saturation - ref_s)
    symbol, distance = min(scores.items(), key=lambda item: item[1])
    confidence = max(0.0, min(1.0, 1.0 - distance / .42))
    return (symbol, confidence) if confidence >= .22 else (None, confidence)


def order_quad(points_xy: np.ndarray) -> np.ndarray:
    points = np.asarray(points_xy, dtype=float)
    if points.shape != (4, 2):
        raise ValueError("four 2-D corners are required")
    sums = points.sum(axis=1)
    differences = points[:, 0] - points[:, 1]
    return np.array([
        points[np.argmin(sums)],       # top-left
        points[np.argmax(differences)],  # top-right
        points[np.argmax(sums)],       # bottom-right
        points[np.argmin(differences)],  # bottom-left
    ])


def homography(source_xy: np.ndarray, destination_xy: np.ndarray) -> np.ndarray:
    """Return H such that destination ~ H * source using normalized DLT scale."""
    source = np.asarray(source_xy, dtype=float)
    destination = np.asarray(destination_xy, dtype=float)
    if source.shape != (4, 2) or destination.shape != (4, 2):
        raise ValueError("homography needs four source and destination points")
    rows = []
    for (x, y), (u, v) in zip(source, destination):
        rows.extend([
            [-x, -y, -1, 0, 0, 0, u * x, u * y, u],
            [0, 0, 0, -x, -y, -1, v * x, v * y, v],
        ])
    _, _, vh = np.linalg.svd(np.asarray(rows))
    matrix = vh[-1].reshape(3, 3)
    return matrix / matrix[2, 2]


def warp_perspective(rgb: np.ndarray, image_from_canonical: np.ndarray,
                     size: int = 180) -> np.ndarray:
    """Bilinearly sample image into a square canonical face."""
    yy, xx = np.mgrid[0:size, 0:size]
    canonical = np.stack((xx.ravel(), yy.ravel(), np.ones(size * size)))
    image = image_from_canonical @ canonical
    image /= image[2]
    x, y = image[0], image[1]
    x0 = np.floor(x).astype(int)
    y0 = np.floor(y).astype(int)
    x1, y1 = x0 + 1, y0 + 1
    valid = (x0 >= 0) & (y0 >= 0) & (x1 < rgb.shape[1]) & (y1 < rgb.shape[0])
    output = np.zeros((size * size, 3), dtype=float)
    if valid.any():
        dx, dy = x[valid] - x0[valid], y[valid] - y0[valid]
        p00 = rgb[y0[valid], x0[valid]].astype(float)
        p10 = rgb[y0[valid], x1[valid]].astype(float)
        p01 = rgb[y1[valid], x0[valid]].astype(float)
        p11 = rgb[y1[valid], x1[valid]].astype(float)
        output[valid] = (
            p00 * ((1 - dx) * (1 - dy))[:, None]
            + p10 * (dx * (1 - dy))[:, None]
            + p01 * ((1 - dx) * dy)[:, None]
            + p11 * (dx * dy)[:, None]
        )
    return np.clip(output.reshape(size, size, 3), 0, 255).astype(np.uint8)


def canonical_index(row: int, col: int, rotation_quarter_turns: int,
                    mirrored: bool = False) -> int:
    """Map an image-grid cell into the canonical cube-local face index."""
    grid = np.arange(9).reshape(3, 3)
    if mirrored:
        grid = np.fliplr(grid)
    # np.rot90 is CCW; rotate the observed grid back into cube-local order.
    grid = np.rot90(grid, k=rotation_quarter_turns % 4)
    inverse = np.empty(9, dtype=int)
    for canonical, observed in enumerate(grid.ravel()):
        inverse[observed] = canonical
    return int(inverse[row * 3 + col])


class PerspectiveFaceletMapper:
    def __init__(self, canonical_size: int = 180, sample_half_width: int = 11) -> None:
        self.canonical_size = canonical_size
        self.sample_half_width = sample_half_width

    @staticmethod
    def detect_face_corners(rgb: np.ndarray) -> np.ndarray | None:
        """Detect a dominant single-face colored quadrilateral in a controlled crop."""
        pixels = rgb.astype(float)
        chroma = pixels.max(axis=2) - pixels.min(axis=2)
        white = (pixels.min(axis=2) > 125) & (chroma < 55)
        mask = ((chroma > 42) & (pixels.max(axis=2) > 70)) | white
        rows, cols = np.nonzero(mask)
        if len(rows) < 150:
            return None
        # Select the nine largest connected sticker regions. Adjacent faces are
        # oblique slivers; using every chromatic pixel turns the whole cube
        # silhouette into a false face quadrilateral.
        pending = mask.copy()
        components: list[np.ndarray] = []
        height, width = mask.shape
        for start_row, start_col in zip(rows, cols):
            if not pending[start_row, start_col]:
                continue
            pending[start_row, start_col] = False
            queue = [(int(start_row), int(start_col))]
            pixels_in_component: list[tuple[int, int]] = []
            while queue:
                row, col = queue.pop()
                pixels_in_component.append((row, col))
                for dr, dc in ((-1, 0), (1, 0), (0, -1), (0, 1)):
                    rr, cc = row + dr, col + dc
                    if 0 <= rr < height and 0 <= cc < width and pending[rr, cc]:
                        pending[rr, cc] = False
                        queue.append((rr, cc))
            if len(pixels_in_component) >= 12:
                components.append(np.asarray(pixels_in_component))
        if len(components) >= 5:
            components.sort(key=len, reverse=True)
            chosen = components[:9]
            points = np.concatenate([
                np.column_stack((component[:, 1], component[:, 0])) for component in chosen
            ]).astype(float)
        else:
            points = np.column_stack((cols, rows)).astype(float)
        # Robust extrema ignore sparse adjacent-face/lighting outliers.
        center = np.median(points, axis=0)
        distance = np.linalg.norm(points - center, axis=1)
        points = points[distance <= np.quantile(distance, .96)]
        sums = points.sum(axis=1)
        diffs = points[:, 0] - points[:, 1]
        corners = np.array([
            points[np.argmin(sums)], points[np.argmax(diffs)],
            points[np.argmax(sums)], points[np.argmin(diffs)],
        ])
        first = corners[1] - corners[0]
        second = corners[3] - corners[0]
        pair_distances = [
            np.linalg.norm(corners[first_index] - corners[second_index])
            for first_index in range(4) for second_index in range(first_index + 1, 4)
        ]
        if min(pair_distances) < 8 or abs(first[0] * second[1] - first[1] * second[0]) < 100:
            return None
        return order_quad(corners)

    def map_face(
        self,
        rgb: np.ndarray,
        *,
        frame_index: int,
        source_view: str,
        corners_xy: np.ndarray | None = None,
        face_hint: str | None = None,
        rotation_quarter_turns: int = 0,
        mirrored: bool = False,
    ) -> MappedFace | None:
        corners = self.detect_face_corners(rgb) if corners_xy is None else order_quad(corners_xy)
        if corners is None:
            return None
        size = self.canonical_size
        canonical_corners = np.array([[0, 0], [size - 1, 0],
                                      [size - 1, size - 1], [0, size - 1]], dtype=float)
        image_from_canonical = homography(canonical_corners, corners)
        canonical = warp_perspective(rgb, image_from_canonical, size)
        colors: list[str | None] = [None] * 9
        confidences = [0.0] * 9
        for row in range(3):
            for col in range(3):
                cy = int((row + .5) * size / 3)
                cx = int((col + .5) * size / 3)
                half = self.sample_half_width
                patch = canonical[cy - half:cy + half + 1, cx - half:cx + half + 1]
                # Black gripper/facelet gaps and low-light occlusion stay unknown.
                bright = patch[patch.max(axis=2) > 45]
                # A sparse visible fragment is not a sticker observation. This
                # prevents gripper/table pixels from being promoted into a
                # confident color merely because their median is chromatic.
                if len(bright) < patch.shape[0] * patch.shape[1] * .62:
                    symbol, confidence = None, 0.0
                else:
                    symbol, confidence = classify_color(np.median(bright, axis=0))
                index = canonical_index(row, col, rotation_quarter_turns, mirrored)
                colors[index], confidences[index] = symbol, confidence
        face = face_hint or colors[4]
        if face is None or face not in "URFDLB":
            return None
        observation = FaceObservation(
            face, tuple(colors), float(np.mean(confidences)), frame_index,
            tuple(confidences), source_view,
        )
        return MappedFace(
            observation,
            tuple(tuple(float(value) for value in point) for point in corners),
            tuple(tuple(float(value) for value in row) for row in image_from_canonical),
            canonical,
        )
