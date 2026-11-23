"""Contracts for the Embodied Simulation v2 closed loop.

The types deliberately separate camera-derived estimates from simulator truth.
Simulator truth may be used by evaluation code, but is never an input to the
perception or planning interfaces in this module.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any

import numpy as np


class EmbodiedState(str, Enum):
    SEARCHING = "SEARCHING"
    GRASPING = "GRASPING"
    ACTIVE_SCANNING = "ACTIVE_SCANNING"
    STATE_VALIDATING = "STATE_VALIDATING"
    SOLVING = "SOLVING"
    ROBOT_MANIPULATING = "ROBOT_MANIPULATING"
    HANDING_OVER = "HANDING_OVER"
    HUMAN_MANIPULATING = "HUMAN_MANIPULATING"
    TAKING_BACK = "TAKING_BACK"
    REOBSERVING = "REOBSERVING"
    PLACING = "PLACING"
    RELEASING = "RELEASING"
    OBSERVING = "OBSERVING"
    REGRASPING = "REGRASPING"
    ROTATING = "ROTATING"
    COMPLETED = "COMPLETED"
    RECOVERING_SEARCH = "RECOVERING_SEARCH"
    RECOVERING_GRASP = "RECOVERING_GRASP"
    RECOVERING_OBSERVATION = "RECOVERING_OBSERVATION"
    RECOVERING_MANIPULATION = "RECOVERING_MANIPULATION"
    ERROR = "ERROR"


@dataclass(frozen=True, slots=True)
class CameraCalibration:
    fx: float
    fy: float
    cx: float
    cy: float
    camera_to_world: np.ndarray

    def __post_init__(self) -> None:
        if self.camera_to_world.shape != (4, 4):
            raise ValueError("camera_to_world must be 4x4")


@dataclass(frozen=True, slots=True)
class RGBDFrame:
    rgb: np.ndarray
    depth_m: np.ndarray | None
    calibration: CameraCalibration
    camera_name: str
    timestamp_seconds: float
    frame_id: str | None = None


@dataclass(frozen=True, slots=True)
class SceneSemantics:
    cube_visible: bool
    confidence: float
    description: str
    provider: str


@dataclass(frozen=True, slots=True)
class CubeDetection:
    center_world_m: tuple[float, float, float]
    yaw_radians: float
    confidence: float
    pixel_count: int
    source: str = "rgbd_deterministic"
    yaw_confidence: float = 0.0


@dataclass(frozen=True, slots=True)
class CubePose6D:
    """Camera-derived cube pose; never populated from simulator body state."""

    center_world_m: tuple[float, float, float]
    rotation_cube_to_world: tuple[tuple[float, float, float], ...]
    visible_face: str
    confidence: float
    source: str = "rgbd_face_homography"

    def __post_init__(self) -> None:
        rotation = np.asarray(self.rotation_cube_to_world)
        if rotation.shape != (3, 3):
            raise ValueError("rotation_cube_to_world must be 3x3")
        if self.visible_face not in "URFDLB":
            raise ValueError("visible_face must be one of URFDLB")


@dataclass(frozen=True, slots=True)
class GraspCandidate:
    wrist_yaw_radians: float
    face_pair: str
    ik_feasible: bool
    collision_free: bool
    contact_geometry_score: float
    motion_cost: float
    rejection_reason: str | None = None


@dataclass(frozen=True, slots=True)
class GraspControlConfig:
    """Contact-controller parameters, separated from perception and scene truth."""

    contact_z_ctrl: float = -0.29
    approach_offset_local_xy_m: tuple[float, float] = (0.01, 0.0)
    pregrasp_gap_m: float = 0.256
    close_duration_seconds: float = 1.5
    finger_kp: float = 500.0
    finger_force_limit_n: float | None = 8.0
    bilateral_confirm_seconds: float = 0.08
    stable_hold_seconds: float = 0.15
    minimum_normal_force_n: float = 0.35
    trial_z_ctrl: float = -0.24
    trial_seconds: float = 0.8
    full_lift_z_ctrl: float = -0.16
    full_lift_seconds: float = 1.4
    slip_limit_m: float = 0.03
    pad_sliding_friction: float | None = None
    contact_solref_timeconst: float | None = None
    approach_displacement_limit_m: float = 0.012
    # Post-approach top-camera localization is partially occluded by the open
    # gripper. This remains a bounded visual consistency gate; the independent
    # 12 mm physical displacement guard is much tighter.
    pose_verification_position_tolerance_m: float = 0.090
    pose_verification_yaw_tolerance_rad: float = 0.15


@dataclass(frozen=True, slots=True)
class FaceObservation:
    face: str
    stickers: tuple[str | None, ...]
    confidence: float
    frame_index: int
    sticker_confidences: tuple[float, ...] | None = None
    source_view: str = "unspecified"

    def __post_init__(self) -> None:
        if self.face not in "URFDLB" or len(self.stickers) != 9:
            raise ValueError("face observation must contain nine stickers for URFDLB")
        if self.sticker_confidences is not None and len(self.sticker_confidences) != 9:
            raise ValueError("sticker confidences must contain nine values")


@dataclass(frozen=True, slots=True)
class StickerEvidence:
    face: str
    index: int
    color: str | None
    confidence: float
    source_view: str
    frame_index: int
    occluded: bool


@dataclass(frozen=True, slots=True)
class GraspTelemetry:
    success: bool
    bilateral_contact_fraction: float
    max_relative_slip_m: float
    lift_height_m: float
    rotation_radians: float
    failure_reason: str | None = None
    left_contact_rate: float = 0.0
    right_contact_rate: float = 0.0
    left_normal_force_n: float = 0.0
    right_normal_force_n: float = 0.0
    trial_lift_success: bool = False
    full_lift_success: bool = False
    full_rotation_success: bool = False
    selected_grasp_yaw_radians: float | None = None
    phase_trace: tuple[str, ...] = ()


@dataclass(slots=True)
class V2Metrics:
    state_transitions: int = 0
    search_attempts: int = 0
    grasp_attempts: int = 0
    regrasp_count: int = 0
    observations: int = 0
    validation_failures: int = 0
    replans: int = 0
    physical_turn_attempts: int = 0
    verified_turns: int = 0
    handovers: int = 0
    recoveries: int = 0
    elapsed_seconds: float = 0.0
    extra: dict[str, Any] = field(default_factory=dict)
