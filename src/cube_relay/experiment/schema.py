"""Unified data correlation, provenance, and experiment schemas for CubeRelay M4-C."""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

SCHEMA_VERSION = "m4c.v1"


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class DataSourceKind(str, Enum):
    """Explicit provenance taxonomy separating live sensors from simulator audit truth."""

    SENSOR_RGB = "SENSOR_RGB"
    SENSOR_DEPTH = "SENSOR_DEPTH"
    CALIBRATION = "CALIBRATION"
    VISUAL_POSE_ESTIMATE = "VISUAL_POSE_ESTIMATE"
    ROBOT_PROPRIOCEPTION = "ROBOT_PROPRIOCEPTION"
    CONTROLLER_STATE = "CONTROLLER_STATE"
    SIMULATOR_GROUND_TRUTH_AUDIT_ONLY = "SIMULATOR_GROUND_TRUTH_AUDIT_ONLY"
    FIXED_CONFIG = "FIXED_CONFIG"


class QualityStatus(str, Enum):
    VALID = "VALID"
    DEGRADED = "DEGRADED"
    MISSING = "MISSING"
    UNREACHABLE = "UNREACHABLE"
    INVALID = "INVALID"
    BLOCKED = "BLOCKED"


class ExperimentConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: str = SCHEMA_VERSION
    run_id: str
    session_id: str
    seed: int
    mission_type: str = "INSPECT_CUBE"
    planner_mode: str = "DETERMINISTIC_PLANNER"
    trajectory_sample_hz: float = Field(default=50.0, gt=0.0, le=500.0)
    max_disk_mb: float = Field(default=256.0, gt=1.0)
    include_audit_ground_truth: bool = True
    perturbation: dict[str, Any] = Field(default_factory=dict)
    git_commit: str | None = None
    scene_xml_path: str | None = None
    grasp_config: dict[str, Any] = Field(default_factory=dict)
    created_utc: str = Field(default_factory=utc_now_iso)
    source_kind: DataSourceKind = DataSourceKind.FIXED_CONFIG
    source_module: str = "cube_relay.experiment.recorder"


class CameraFrameRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: str = SCHEMA_VERSION
    frame_id: str
    run_id: str
    session_id: str
    mission_id: str | None = None
    skill_execution_id: str | None = None
    observation_id: str | None = None
    camera_id: str
    sim_time: float
    rgb_sim_time: float
    depth_sim_time: float | None = None
    rgb_depth_sim_time_delta_s: float = 0.0
    monotonic_wall_time: float
    utc_timestamp: str
    width: int
    height: int
    rgb_path: str | None = None
    depth_path: str | None = None
    depth_unit: str = "m"
    depth_dtype: str = "float32"
    rgb_sha256: str | None = None
    depth_sha256: str | None = None
    coordinate_frame: str = "camera"
    units: str = "pixel,m,s"
    source_kind: DataSourceKind = DataSourceKind.SENSOR_RGB
    depth_source_kind: DataSourceKind = DataSourceKind.SENSOR_DEPTH
    calibration_source_kind: DataSourceKind = DataSourceKind.CALIBRATION
    source_module: str = "cube_relay.embodied.mujoco_v2"
    quality_status: QualityStatus = QualityStatus.VALID


class PoseEstimateRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: str = SCHEMA_VERSION
    pose_estimate_id: str
    pose_version: int
    run_id: str
    session_id: str
    mission_id: str | None = None
    skill_execution_id: str | None = None
    observation_id: str | None = None
    frame_id: str | None = None
    camera_id: str
    sim_time: float
    monotonic_wall_time: float
    utc_timestamp: str
    coordinate_frame: str = "world"
    units: str = "m,rad"
    source_kind: DataSourceKind = DataSourceKind.VISUAL_POSE_ESTIMATE
    source_module: str = "cube_relay.embodied.perception_v2"
    quality_status: QualityStatus = QualityStatus.VALID
    detection_bbox_xyxy: list[int] | None = None
    pixel_centroid_xy: list[float] | None = None
    pixel_mean_xy: list[float] | None = None
    pixel_count: int = 0
    initial_mask_pixel_count: int = 0
    depth_stats: dict[str, float | int | None] = Field(default_factory=dict)
    camera_coords_surface_m: list[float] | None = None
    world_coords_surface_m: list[float] | None = None
    estimated_center_world_m: list[float] | None = None
    estimated_yaw_rad: float | None = None
    rotation_cube_to_world: list[list[float]] | None = None
    confidence: float | None = None
    yaw_confidence: float | None = None
    failure_reason: str | None = None


class GraspTargetRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: str = SCHEMA_VERSION
    grasp_target_id: str
    run_id: str
    session_id: str
    mission_id: str | None = None
    skill_execution_id: str | None = None
    pose_estimate_id: str
    pose_version: int
    pose_sim_time: float
    pose_age_sim_s: float
    sim_time: float
    monotonic_wall_time: float
    utc_timestamp: str
    coordinate_frame: str = "world"
    planning_frame: str = "cartesian_gantry_world"
    units: str = "m,rad"
    source_kind: DataSourceKind = DataSourceKind.CONTROLLER_STATE
    source_module: str = "cube_relay.embodied.mujoco_v2"
    quality_status: QualityStatus = QualityStatus.VALID
    object_center_world_m: list[float] | None = None
    object_yaw_rad: float | None = None
    object_rotation_world: list[list[float]] | None = None
    approach_direction_world: list[float] = Field(default_factory=lambda: [0.0, 0.0, -1.0])
    approach_offset_local_xy_m: list[float] = Field(default_factory=list)
    world_offset_xy_m: list[float] = Field(default_factory=list)
    target_end_effector_pose: dict[str, Any] = Field(default_factory=dict)
    target_gripper_width_m: float | None = None
    pregrasp_gap_m: float | None = None
    actual_end_effector_pose_at_plan: dict[str, Any] = Field(default_factory=dict)
    actual_end_effector_pose_at_contact: dict[str, Any] | None = None
    candidates: list[dict[str, Any]] = Field(default_factory=list)
    selected_candidate_index: int | None = None
    selected_face_pair: str | None = None
    selected_option_id: str | None = None
    ik_status: str = "UNKNOWN"
    reachability_status: str = "UNKNOWN"
    collision_check_status: str = "UNKNOWN"
    safety_parameters: dict[str, Any] = Field(default_factory=dict)
    failure_reason: str | None = None


class ContactPhaseWindowSummary(BaseModel):
    model_config = ConfigDict(extra="forbid")

    window_name: str
    sample_count: int = 0
    start_sim_time: float | None = None
    end_sim_time: float | None = None
    duration_s: float = 0.0
    bilateral_contact_duration_s: float = 0.0
    bilateral_contact_fraction: float | None = None
    left_contact_fraction: float | None = None
    right_contact_fraction: float | None = None
    left_normal_force_mean_n: float | None = None
    left_normal_force_min_n: float | None = None
    left_normal_force_max_n: float | None = None
    right_normal_force_mean_n: float | None = None
    right_normal_force_min_n: float | None = None
    right_normal_force_max_n: float | None = None
    max_relative_slip_m: float | None = None
    unexpected_contacts_count: int = 0
    unexpected_contacts_geoms: list[str] = Field(default_factory=list)


class ContactVerificationRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: str = SCHEMA_VERSION
    contact_verification_id: str
    run_id: str
    session_id: str
    mission_id: str | None = None
    skill_execution_id: str | None = None
    trajectory_id: str | None = None
    grasp_target_id: str | None = None
    pose_estimate_id: str | None = None
    skill_name: str
    sim_time: float
    monotonic_wall_time: float
    utc_timestamp: str
    coordinate_frame: str = "gripper"
    units: str = "m,N,s"
    source_kind: DataSourceKind = DataSourceKind.ROBOT_PROPRIOCEPTION
    source_module: str = "cube_relay.embodied.mujoco_v2"
    quality_status: QualityStatus = QualityStatus.VALID
    bilateral_contact_duration_s: float = 0.0
    bilateral_contact_fraction: float = 0.0
    left_contact_fraction: float = 0.0
    right_contact_fraction: float = 0.0
    left_normal_force_n: float = 0.0
    right_normal_force_n: float = 0.0
    relative_slip_m: float = 0.0
    gripper_width_m: float | None = None
    lift_height_m: float | None = None
    object_motion_relative_to_gripper_m: list[float] | None = None
    object_followed_end_effector: bool = False
    unintended_contacts: list[str] = Field(default_factory=list)
    grasp_stability_status: str = "UNVERIFIED"
    verification_thresholds: dict[str, Any] = Field(default_factory=dict)
    verification_result: bool = False
    failure_reason: str | None = None
    phase_windows: dict[str, ContactPhaseWindowSummary] = Field(default_factory=dict)


class ExperimentRunSummary(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: str = SCHEMA_VERSION
    run_id: str
    session_id: str
    seed: int
    mission_id: str | None = None
    mission_type: str
    planner_mode: str
    frame_source: str = "REAL_MUJOCO_RENDERER"
    recording_status: str = "IDLE"
    created_utc: str
    updated_utc: str
    sim_time: float = 0.0
    run_dir: str | None = None
    counts: dict[str, int] = Field(default_factory=dict)
    perturbation: dict[str, Any] = Field(default_factory=dict)
    has_audit_truth: bool = False
    has_rgbd: bool = False
    has_trajectory: bool = False
