"""Optional OpenCV visible-face scanner; never infers hidden faces."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from cube_relay.cube.state import FACE_ORDER


@dataclass(frozen=True, slots=True)
class FaceScan:
    face: str
    symbols: str
    confidence: float


class OpenCVVisibleFaceScanner:
    """Calibrated four-corner warp and nearest-sample color classification."""

    def __init__(self, color_samples_rgb: dict[str, tuple[int, int, int]]) -> None:
        if set(color_samples_rgb) != set(FACE_ORDER):
            raise ValueError("color calibration requires one RGB sample for each URFDLB symbol")
        self.samples = {key: np.asarray(value, dtype=float) for key, value in color_samples_rgb.items()}
        self.scans: dict[str, FaceScan] = {}

    def scan_visible_face(self, rgb: np.ndarray, corners: np.ndarray, face: str) -> FaceScan:
        if face not in FACE_ORDER:
            raise ValueError("face must be one of URFDLB")
        try:
            import cv2
        except ImportError as exc:
            raise RuntimeError("OpenCV vision extra is not installed") from exc
        source = np.asarray(corners, dtype=np.float32)
        if source.shape != (4, 2):
            raise ValueError("corners must be four (x,y) points")
        target = np.asarray([[0, 0], [299, 0], [299, 299], [0, 299]], dtype=np.float32)
        transform = cv2.getPerspectiveTransform(source, target)
        patch = cv2.warpPerspective(rgb, transform, (300, 300))
        symbols, confidences = [], []
        for row in range(3):
            for col in range(3):
                sample = patch[row * 100 + 40:row * 100 + 60,
                               col * 100 + 40:col * 100 + 60].mean(axis=(0, 1))
                distances = {key: float(np.linalg.norm(sample - value))
                             for key, value in self.samples.items()}
                symbol, distance = min(distances.items(), key=lambda item: item[1])
                symbols.append(symbol)
                confidences.append(max(0.0, 1.0 - distance / 441.7))
        scan = FaceScan(face, "".join(symbols), sum(confidences) / 9)
        self.scans[face] = scan
        return scan

    def assembled_facelets(self) -> str | None:
        """Return all six scanned faces only; caller must still request human confirmation."""
        if set(self.scans) != set(FACE_ORDER):
            return None
        return "".join(self.scans[face].symbols for face in FACE_ORDER)

