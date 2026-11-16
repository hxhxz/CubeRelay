"""Observation boundaries that keep pixels separate from privileged simulator state."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

import numpy as np


@dataclass(frozen=True, slots=True)
class CameraFrame:
    rgb: np.ndarray
    camera_name: str
    timestamp_seconds: float


@dataclass(frozen=True, slots=True)
class VisionObservation:
    frame: CameraFrame
    facelets: str | None
    confidence: float
    estimator: str | None
    error: str | None = None


class FaceletEstimator(Protocol):
    def estimate(self, rgb: np.ndarray) -> tuple[str, float]: ...


class VisionObservationAdapter:
    """Calls an estimator with pixels only; never exposes MjData to recognition."""

    def __init__(self, estimator: FaceletEstimator | None = None) -> None:
        self.estimator = estimator

    def observe(self, frame: CameraFrame) -> VisionObservation:
        if self.estimator is None:
            return VisionObservation(
                frame, None, 0.0, None,
                "no visual facelet estimator configured; frame is pixels only",
            )
        facelets, confidence = self.estimator.estimate(frame.rgb)
        return VisionObservation(
            frame, facelets, confidence, type(self.estimator).__name__, None
        )


class MuJoCoCamera:
    def __init__(self, executor: object, width: int = 320, height: int = 240) -> None:
        mujoco = executor.mujoco  # type: ignore[attr-defined]
        self.executor = executor
        self.renderer = mujoco.Renderer(executor.model, height=height, width=width)  # type: ignore[attr-defined]

    def capture(self, camera_name: str = "overhead") -> CameraFrame:
        self.renderer.update_scene(self.executor.data, camera=camera_name)  # type: ignore[attr-defined]
        rgb = self.renderer.render().copy()
        return CameraFrame(rgb, camera_name, float(self.executor.data.time))  # type: ignore[attr-defined]

