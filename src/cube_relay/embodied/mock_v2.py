"""Explicit v2 test double. Never report results from this backend as physics."""

from __future__ import annotations

import numpy as np

from cube_relay.cube import SOLVED_FACELETS

from .execution import ActionFeedback
from .v2_types import CameraCalibration, FaceObservation, RGBDFrame


class MockEmbodiedBackend:
    implementation_level = "MOCK:deterministic_unit_test_double"

    def __init__(self, *, fail_first_search: bool = False, facelets: str = SOLVED_FACELETS) -> None:
        self.fail_first_search = fail_first_search
        self.facelets = facelets
        self.captures = 0
        self.recorded = 0

    def reset_random(self, seed: int, scramble_steps: int) -> dict[str, object]:
        return {"seed": seed, "mock": True}

    def capture_rgbd(self) -> RGBDFrame:
        self.captures += 1
        rgb = np.zeros((40, 40, 3), dtype=np.uint8)
        if not self.fail_first_search or self.captures > 1:
            rgb[15:25, 15:25] = [240, 20, 20]
        depth = np.ones((40, 40), dtype=float)
        calibration = CameraCalibration(40, 40, 20, 20, np.eye(4))
        return RGBDFrame(rgb, depth, calibration, "mock", float(self.captures))

    def approach_grasp_lift(
        self, target_xyz: tuple[float, float, float], target_yaw: float | None = None
    ) -> bool:
        return True

    def active_scan(self) -> list[FaceObservation]:
        return [
            FaceObservation(face, tuple(self.facelets[index * 9:(index + 1) * 9]), 1.0, index)
            for index, face in enumerate("URFDLB")
        ]

    def execute_physical_turn(self, move: str) -> ActionFeedback:
        return ActionFeedback(True, move, 0, 0, "mock", "unit test double")

    def hand_over(self) -> bool:
        return True

    def wait_for_human_move(self, move: str | None) -> str | None:
        return move

    def take_back(self) -> bool:
        return True

    def record_frame(self) -> None:
        self.recorded += 1
