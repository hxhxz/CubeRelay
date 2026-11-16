"""Deterministic RGB-D geometry and multi-view sticker-state fusion."""

from __future__ import annotations

import math
from collections import Counter, defaultdict

import numpy as np

from cube_relay.cube.validation import validate_facelets

from .facelet_mapping import MappedFace
from .v2_types import CubeDetection, CubePose6D, FaceObservation, RGBDFrame, StickerEvidence


_LOCAL_FACE_FRAME = {
    # right, image-down, outward normal in cube-local coordinates
    # U/D follow the actual sticker_FACE_index ordering in the MuJoCo XML.
    "U": ((1, 0, 0), (0, 1, 0), (0, 0, 1)),
    "D": ((1, 0, 0), (0, -1, 0), (0, 0, -1)),
    "F": ((1, 0, 0), (0, 0, -1), (0, -1, 0)),
    "B": ((-1, 0, 0), (0, 0, -1), (0, 1, 0)),
    "R": ((0, 1, 0), (0, 0, -1), (1, 0, 0)),
    "L": ((0, -1, 0), (0, 0, -1), (-1, 0, 0)),
}


class DeterministicCubePose6DEstimator:
    """Recover full orientation from a mapped face and calibrated RGB-D pixels."""

    def __init__(self, cube_half_extent_m: float = .06) -> None:
        self.cube_half_extent_m = cube_half_extent_m

    @staticmethod
    def _world_at(frame: RGBDFrame, xy: tuple[float, float]) -> np.ndarray | None:
        x, y = (int(round(value)) for value in xy)
        y0, y1 = max(0, y - 3), min(frame.depth_m.shape[0], y + 4)
        x0, x1 = max(0, x - 3), min(frame.depth_m.shape[1], x + 4)
        depths = frame.depth_m[y0:y1, x0:x1]
        valid = depths[np.isfinite(depths) & (depths > 0)]
        if not len(valid):
            return None
        depth = float(np.median(valid))
        calibration = frame.calibration
        camera = np.array([
            (xy[0] - calibration.cx) * depth / calibration.fx,
            (xy[1] - calibration.cy) * depth / calibration.fy,
            depth, 1.0,
        ])
        return (calibration.camera_to_world @ camera)[:3]

    def estimate(self, frame: RGBDFrame, mapped: MappedFace) -> CubePose6D | None:
        if frame.depth_m is None:
            raise ValueError("metric depth is required for 6-D estimation")
        world_corners = [self._world_at(frame, point) for point in mapped.corners_xy]
        if any(point is None for point in world_corners):
            return None
        top_left, top_right, bottom_right, bottom_left = (
            np.asarray(point) for point in world_corners
        )
        right = (top_right - top_left) + (bottom_right - bottom_left)
        down = (bottom_left - top_left) + (bottom_right - top_right)
        right /= np.linalg.norm(right)
        down -= right * float(np.dot(right, down))
        down /= np.linalg.norm(down)
        # Image right x image down points away from the camera; visible outward
        # normal points toward it.
        normal = -np.cross(right, down)
        normal /= np.linalg.norm(normal)
        down = np.cross(normal, right)
        surface_center = np.mean(np.stack(world_corners), axis=0)
        center = surface_center - normal * self.cube_half_extent_m
        local = np.asarray(_LOCAL_FACE_FRAME[mapped.observation.face], dtype=float).T
        world = np.column_stack((right, down, normal))
        rotation = world @ local.T
        confidence = min(
            mapped.observation.confidence,
            float(np.mean(np.asarray(mapped.observation.sticker_confidences))),
        )
        return CubePose6D(
            tuple(float(value) for value in center),
            tuple(tuple(float(value) for value in row) for row in rotation),
            mapped.observation.face, confidence,
        )


class DeterministicCubeLocalizer:
    """Estimate position from camera pixels and calibrated metric depth only."""

    def __init__(self, min_chroma: int = 45, min_pixels: int = 30,
                 cube_half_extent_m: float = .06) -> None:
        self.min_chroma = min_chroma
        self.min_pixels = min_pixels
        self.cube_half_extent_m = cube_half_extent_m

    def locate(self, frame: RGBDFrame) -> CubeDetection | None:
        if frame.depth_m is None:
            raise ValueError("metric depth is required for 3-D localization")
        rgb = frame.rgb.astype(np.int16)
        chroma = rgb.max(axis=2) - rgb.min(axis=2)
        bright = rgb.max(axis=2) > 105
        white_sticker = (rgb.min(axis=2) > 155) & (chroma < 38)
        mask = (((chroma >= self.min_chroma) & bright) | white_sticker) & np.isfinite(frame.depth_m)
        rows, cols = np.nonzero(mask)
        if len(rows) < self.min_pixels:
            return None
        depths = frame.depth_m[rows, cols]
        median = float(np.median(depths))
        keep = np.abs(depths - median) < 0.08
        rows, cols, depths = rows[keep], cols[keep], depths[keep]
        if len(rows) < self.min_pixels:
            return None
        calibration = frame.calibration
        x_cam = (cols - calibration.cx) * depths / calibration.fx
        y_cam = (rows - calibration.cy) * depths / calibration.fy
        points = np.stack((x_cam, y_cam, depths, np.ones_like(depths)), axis=1)
        world = points @ calibration.camera_to_world.T
        surface_center = np.median(world[:, :3], axis=0)
        center = surface_center + calibration.camera_to_world[:3, 2] * self.cube_half_extent_m
        yaw, yaw_confidence = self._yaw_from_world_contour(world[:, :3])
        return CubeDetection(
            tuple(float(value) for value in center), yaw,
            min(1.0, len(rows) / 400.0), int(len(rows)),
            yaw_confidence=yaw_confidence,
        )

    @staticmethod
    def _convex_hull(points: np.ndarray) -> np.ndarray:
        unique = sorted({(float(x), float(y)) for x, y in points})
        if len(unique) < 3:
            return np.asarray(unique)

        def cross(origin: tuple[float, float], a: tuple[float, float],
                  b: tuple[float, float]) -> float:
            return (a[0] - origin[0]) * (b[1] - origin[1]) - \
                   (a[1] - origin[1]) * (b[0] - origin[0])

        lower: list[tuple[float, float]] = []
        for point in unique:
            while len(lower) >= 2 and cross(lower[-2], lower[-1], point) <= 0:
                lower.pop()
            lower.append(point)
        upper: list[tuple[float, float]] = []
        for point in reversed(unique):
            while len(upper) >= 2 and cross(upper[-2], upper[-1], point) <= 0:
                upper.pop()
            upper.append(point)
        return np.asarray(lower[:-1] + upper[:-1])

    @classmethod
    def _yaw_from_world_contour(cls, world_points: np.ndarray) -> tuple[float, float]:
        """Fit a minimum-area rectangle to the top-surface convex contour.

        This uses physical outline edges/corners and deliberately avoids the
        degenerate PCA principal axis of a square.
        """
        top = world_points[world_points[:, 2] >= world_points[:, 2].max() - .018, :2]
        if len(top) < 20:
            return 0.0, 0.0
        # Quantization removes thousands of collinear raster points without
        # changing the physical outline at millimetre scale.
        quantized = np.round(top / .0015) * .0015
        hull = cls._convex_hull(quantized)
        if len(hull) < 4:
            return 0.0, 0.0
        best: tuple[float, float, float, float] | None = None
        for first, second in zip(hull, np.roll(hull, -1, axis=0)):
            edge = second - first
            if np.linalg.norm(edge) < .004:
                continue
            angle = math.atan2(float(edge[1]), float(edge[0]))
            cosine, sine = math.cos(angle), math.sin(angle)
            rotation = np.array([[cosine, sine], [-sine, cosine]])
            aligned = hull @ rotation.T
            width, height = np.ptp(aligned, axis=0)
            area = float(width * height)
            squareness = float(min(width, height) / max(width, height)) if max(width, height) else 0
            candidate = (area, -squareness, angle, squareness)
            if best is None or candidate[:2] < best[:2]:
                best = candidate
        if best is None:
            return 0.0, 0.0
        yaw = (best[2] + math.pi / 4) % (math.pi / 2) - math.pi / 4
        return float(yaw), float(best[3])


class StickerStateFusion:
    """Fuse repeated visual face observations, then run independent legality checks."""

    def __init__(self) -> None:
        self._votes: dict[tuple[str, int], list[tuple[str, float]]] = defaultdict(list)
        self.evidence: list[StickerEvidence] = []

    def add(self, observation: FaceObservation) -> None:
        for index, color in enumerate(observation.stickers):
            confidence = (
                observation.sticker_confidences[index]
                if observation.sticker_confidences is not None else observation.confidence
            )
            self.evidence.append(StickerEvidence(
                observation.face, index, color, confidence, observation.source_view,
                observation.frame_index, color is None,
            ))
            if color is not None:
                self._votes[(observation.face, index)].append((color, confidence))

    @property
    def conflict_count(self) -> int:
        """Number of canonical sticker indices with disagreeing visual colors."""
        return sum(len({color for color, _ in votes}) > 1 for votes in self._votes.values())

    @property
    def conflicting_indices(self) -> tuple[str, ...]:
        return tuple(
            f"{face}{index}" for (face, index), votes in sorted(self._votes.items())
            if len({color for color, _ in votes}) > 1
        )

    @property
    def observed_sticker_count(self) -> int:
        return 54 - self.unknown_count

    @property
    def observed_face_count(self) -> int:
        return len({face for face, _ in self._votes})

    @property
    def unknown_count(self) -> int:
        return sum(1 for face in "URFDLB" for index in range(9)
                   if (face, index) not in self._votes)

    def fused_evidence(self) -> tuple[StickerEvidence, ...]:
        """Return exactly 54 records, explicitly materializing unobserved cells."""
        fused: list[StickerEvidence] = []
        for face in "URFDLB":
            for index in range(9):
                candidates = [item for item in self.evidence
                              if item.face == face and item.index == index and item.color is not None]
                if candidates:
                    fused.append(max(candidates, key=lambda item: item.confidence))
                else:
                    fused.append(StickerEvidence(
                        face, index, None, 0.0, "not_observed_or_occluded", -1, True
                    ))
        return tuple(fused)

    def facelets(self) -> str | None:
        if any((face, index) not in self._votes for face in "URFDLB" for index in range(9)):
            return None
        output: list[str] = []
        for face in "URFDLB":
            for index in range(9):
                weighted: Counter[str] = Counter()
                for color, confidence in self._votes[(face, index)]:
                    weighted[color] += confidence
                output.append(weighted.most_common(1)[0][0])
        return "".join(output)

    def validated_facelets(self) -> str:
        state = self.facelets()
        if state is None:
            raise ValueError("six complete faces have not been observed")
        try:
            return validate_facelets(state)
        except ValueError as exc:
            raise ValueError(f"visually reconstructed cube is illegal: {exc}") from exc
