"""Non-invasive buffered experiment recorder for CubeRelay M4-C causal audit."""

from __future__ import annotations

import atexit
import csv
import hashlib
import io
import json
import math
import queue
import re
import subprocess
import threading
import time
import uuid
import weakref
from pathlib import Path
from typing import Any

import numpy as np
from PIL import Image

from .schema import (
    SCHEMA_VERSION,
    CameraFrameRecord,
    ContactPhaseWindowSummary,
    ContactVerificationRecord,
    DataSourceKind,
    ExperimentConfig,
    ExperimentRunSummary,
    GraspTargetRecord,
    PoseEstimateRecord,
    QualityStatus,
    utc_now_iso,
)

ROOT = Path(__file__).resolve().parents[3]
DEFAULT_EXPERIMENTS_DIR = ROOT / "runs" / "experiments"
_RUN_ID_RE = re.compile(r"^[A-Za-z0-9_.-]+$")

_SECRET_PATTERN = re.compile(
    r"(?i)(api[_-]?key|authorization|bearer\s+[A-Za-z0-9._-]+|enable_password|password)"
)


def _current_git_commit() -> str | None:
    try:
        proc = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            cwd=ROOT,
            capture_output=True,
            text=True,
            timeout=2.0,
            check=False,
        )
        if proc.returncode == 0:
            return proc.stdout.strip() or None
    except Exception:
        pass
    return None


def redact_secrets(value: Any) -> Any:
    """Recursively scrub API keys, bearer tokens, and passwords from exported payloads."""
    if isinstance(value, dict):
        out: dict[str, Any] = {}
        for k, v in value.items():
            ks = str(k).lower()
            if any(tok in ks for tok in ("api_key", "apikey", "password", "secret", "authorization", "token")):
                if ks in {"total_input_tokens", "total_output_tokens", "input_tokens", "output_tokens", "token_usage", "token_budget"}:
                    out[k] = redact_secrets(v)
                else:
                    out[k] = "<REDACTED>"
            else:
                out[k] = redact_secrets(v)
        return out
    if isinstance(value, list):
        return [redact_secrets(item) for item in value]
    if isinstance(value, tuple):
        return [redact_secrets(item) for item in value]
    if isinstance(value, str):
        return re.sub(r"(?i)bearer\s+[A-Za-z0-9._\-]+", "Bearer <REDACTED>", value)
    return value


def validate_run_id(run_id: str) -> str:
    if not run_id or not _RUN_ID_RE.match(run_id) or ".." in run_id:
        raise ValueError(f"Invalid run_id: {run_id!r}")
    return run_id


def map_phase_to_window(phase: str) -> str:
    p = str(phase).upper()
    if p in {"PREGRASP", "ALIGN", "APPROACH"}:
        return "Approach"
    if p in {"SLOW_CLOSE", "BILATERAL_CONTACT"}:
        return "Initial Contact"
    if p in {"STABLE_HOLD"}:
        return "Grasp Closure"
    if p in {
        "TRIAL_LIFT",
        "STABILITY_CHECK",
        "FULL_LIFT",
        "ALIGN_SCAN_AXES",
        "PLACE_START",
        "PLACE_SUPPORTED",
        "LOWER_TO_SUPPORT",
        "DYNAMIC_SCAN_STATION_SELECTED",
        "RELEASE_OPEN",
        "RELEASE_SETTLED_SIDEWAYS",
        "PLACE_END",
    }:
        return "Lift / Hold"
    if p in {"ROTATE", "REORIENT", "REORIENT_PITCH", "REORIENT_YAW"}:
        return "Reorientation"
    return "Lift / Hold"


class _AsyncDiskWriter:
    """Thread-safe buffered background writer ensuring physics loops never block on disk I/O."""

    def __init__(self, run_dir: Path, *, max_disk_mb: float = 256.0) -> None:
        self.run_dir = run_dir
        self.max_disk_bytes = int(max_disk_mb * 1024 * 1024)
        self.bytes_written = 0
        self.disk_budget_exceeded = False
        self._queue: queue.Queue[tuple[str, Any]] = queue.Queue()
        self._closed = False
        self._csv_headers_written: set[Path] = set()
        self._thread = threading.Thread(
            target=self._worker,
            name=f"cuberelay-rec-{run_dir.name[:16]}",
            daemon=True,
        )
        self.run_dir.mkdir(parents=True, exist_ok=True)
        self._thread.start()

    def _can_write(self, est_bytes: int) -> bool:
        if self.bytes_written + est_bytes > self.max_disk_bytes:
            self.disk_budget_exceeded = True
            return False
        return True

    def _worker(self) -> None:
        while True:
            item = self._queue.get()
            kind, payload = item
            try:
                if kind == "__STOP__":
                    break
                if kind == "__FLUSH__":
                    payload.set()
                    continue
                if kind == "jsonl":
                    rel_path, row_json = payload
                    target = self.run_dir / rel_path
                    data = (row_json + "\n").encode("utf-8")
                    if self._can_write(len(data)):
                        target.parent.mkdir(parents=True, exist_ok=True)
                        with target.open("ab") as fh:
                            fh.write(data)
                            fh.flush()
                        self.bytes_written += len(data)
                elif kind == "csv":
                    rel_path, fieldnames, row = payload
                    target = self.run_dir / rel_path
                    buf = io.StringIO()
                    writer = csv.DictWriter(buf, fieldnames=fieldnames)
                    if target not in self._csv_headers_written and not target.exists():
                        writer.writeheader()
                        self._csv_headers_written.add(target)
                    writer.writerow(row)
                    data = buf.getvalue().encode("utf-8")
                    if self._can_write(len(data)):
                        target.parent.mkdir(parents=True, exist_ok=True)
                        with target.open("ab") as fh:
                            fh.write(data)
                            fh.flush()
                        self.bytes_written += len(data)
                elif kind == "bytes":
                    rel_path, raw_bytes = payload
                    target = self.run_dir / rel_path
                    if self._can_write(len(raw_bytes)):
                        target.parent.mkdir(parents=True, exist_ok=True)
                        target.write_bytes(raw_bytes)
                        self.bytes_written += len(raw_bytes)
                elif kind == "text":
                    rel_path, text = payload
                    target = self.run_dir / rel_path
                    raw_bytes = text.encode("utf-8")
                    if self._can_write(len(raw_bytes)):
                        target.parent.mkdir(parents=True, exist_ok=True)
                        target.write_bytes(raw_bytes)
                        self.bytes_written += len(raw_bytes)
            except Exception:
                # Never crash simulation loop due to disk I/O errors
                pass
            finally:
                self._queue.task_done()

    def enqueue_jsonl(self, rel_path: str, record: dict[str, Any]) -> None:
        if self._closed:
            return
        safe_json = json.dumps(redact_secrets(record), ensure_ascii=False, separators=(",", ":"))
        self._queue.put(("jsonl", (rel_path, safe_json)))

    def enqueue_csv(self, rel_path: str, fieldnames: list[str], row: dict[str, Any]) -> None:
        if self._closed:
            return
        self._queue.put(("csv", (rel_path, fieldnames, row)))

    def enqueue_bytes(self, rel_path: str, data: bytes) -> None:
        if self._closed:
            return
        self._queue.put(("bytes", (rel_path, data)))

    def enqueue_text(self, rel_path: str, text: str) -> None:
        if self._closed:
            return
        self._queue.put(("text", (rel_path, text)))

    def flush(self, timeout: float = 10.0) -> None:
        if self._closed:
            return
        ev = threading.Event()
        self._queue.put(("__FLUSH__", ev))
        ev.wait(timeout=timeout)

    def close(self, timeout: float = 10.0) -> None:
        if self._closed:
            return
        self.flush(timeout=timeout)
        self._closed = True
        self._queue.put(("__STOP__", None))
        if self._thread.is_alive():
            self._thread.join(timeout=timeout)


class EventStore:
    """Buffered append-only event store for DecisionEvents, TraceEvents, and Observations."""

    def __init__(self, writer: _AsyncDiskWriter) -> None:
        self._writer = writer
        self._lock = threading.Lock()
        self.decision_events: list[dict[str, Any]] = []
        self.trace_events: list[dict[str, Any]] = []
        self.observations: list[dict[str, Any]] = []

    def record_decision_event(self, event: dict[str, Any]) -> None:
        payload = {
            **event,
            "monotonic_wall_time": event.get("monotonic_wall_time", time.monotonic()),
            "utc_timestamp": event.get("utc_timestamp", utc_now_iso()),
            "source_kind": event.get("source_kind", DataSourceKind.CONTROLLER_STATE.value),
        }
        with self._lock:
            self.decision_events.append(payload)
        self._writer.enqueue_jsonl("decision_events.jsonl", payload)

    def record_trace_event(self, event: dict[str, Any]) -> None:
        payload = {
            **event,
            "monotonic_wall_time": event.get("monotonic_wall_time", time.monotonic()),
            "utc_timestamp": event.get("utc_timestamp", utc_now_iso()),
            "source_kind": event.get("source_kind", DataSourceKind.CONTROLLER_STATE.value),
        }
        with self._lock:
            self.trace_events.append(payload)
        self._writer.enqueue_jsonl("trace_events.jsonl", payload)

    def record_observation(self, obs: dict[str, Any]) -> None:
        payload = {
            **obs,
            "monotonic_wall_time": obs.get("monotonic_wall_time", time.monotonic()),
            "utc_timestamp": obs.get("utc_timestamp", utc_now_iso()),
        }
        with self._lock:
            self.observations.append(payload)
        self._writer.enqueue_jsonl("observations.jsonl", payload)

    def replace_decision_events(self, events: list[dict[str, Any]]) -> None:
        with self._lock:
            self.decision_events = list(events)
        text = "".join(json.dumps(redact_secrets(e), ensure_ascii=False) + "\n" for e in events)
        self._writer.enqueue_text("decision_events.jsonl", text)

    def replace_trace_events(self, events: list[dict[str, Any]]) -> None:
        with self._lock:
            self.trace_events = list(events)
        text = "".join(json.dumps(redact_secrets(e), ensure_ascii=False) + "\n" for e in events)
        self._writer.enqueue_text("trace_events.jsonl", text)

    def replace_observations(self, observations: list[dict[str, Any]]) -> None:
        with self._lock:
            self.observations = list(observations)
        text = "".join(json.dumps(redact_secrets(o), ensure_ascii=False) + "\n" for o in observations)
        self._writer.enqueue_text("observations.jsonl", text)


class PoseEstimateRecorder:
    """Records raw RGB-D frames (.png + float32 .npy), calibrations, and visual pose estimates."""

    def __init__(
        self,
        writer: _AsyncDiskWriter,
        *,
        run_id: str,
        session_id: str,
        save_rgbd_frames: bool = True,
    ) -> None:
        self._writer = writer
        self.run_id = run_id
        self.session_id = session_id
        self.save_rgbd_frames = save_rgbd_frames
        self._lock = threading.Lock()
        self._pose_version = 0
        self.frames: list[CameraFrameRecord] = []
        self.calibrations: dict[str, dict[str, Any]] = {}
        self.pose_estimates: list[PoseEstimateRecord] = []
        self._latest_pose_by_mission: PoseEstimateRecord | None = None

    def record_camera_frame(
        self,
        *,
        frame_id: str,
        camera_id: str,
        rgb: np.ndarray,
        depth_m: np.ndarray | None,
        fx: float,
        fy: float,
        cx: float,
        cy: float,
        camera_to_world: np.ndarray,
        sim_time: float,
        rgb_sim_time: float | None = None,
        depth_sim_time: float | None = None,
        mission_id: str | None = None,
        skill_execution_id: str | None = None,
        observation_id: str | None = None,
        source_module: str = "cube_relay.embodied.mujoco_v2",
        quality_status: QualityStatus = QualityStatus.VALID,
    ) -> CameraFrameRecord:
        height, width = int(rgb.shape[0]), int(rgb.shape[1])
        rgb_rel: str | None = None
        depth_rel: str | None = None
        rgb_sha: str | None = None
        depth_sha: str | None = None

        if self.save_rgbd_frames:
            rgb_buf = io.BytesIO()
            Image.fromarray(np.asarray(rgb, dtype=np.uint8)).save(rgb_buf, format="PNG")
            rgb_bytes = rgb_buf.getvalue()
            rgb_sha = hashlib.sha256(rgb_bytes).hexdigest()
            rgb_rel = f"frames/{frame_id}_rgb.png"
            self._writer.enqueue_bytes(rgb_rel, rgb_bytes)

            if depth_m is not None:
                depth_arr = np.asarray(depth_m, dtype=np.float32)
                depth_buf = io.BytesIO()
                np.save(depth_buf, depth_arr, allow_pickle=False)
                depth_bytes = depth_buf.getvalue()
                depth_sha = hashlib.sha256(depth_bytes).hexdigest()
                depth_rel = f"frames/{frame_id}_depth.npy"
                self._writer.enqueue_bytes(depth_rel, depth_bytes)

        r_sim = float(sim_time if rgb_sim_time is None else rgb_sim_time)
        d_sim = float(sim_time if depth_sim_time is None else depth_sim_time) if depth_m is not None else None
        delta_s = abs(r_sim - d_sim) if d_sim is not None else 0.0
        cal_payload = {
            "camera_id": camera_id,
            "width": width,
            "height": height,
            "fx": float(fx),
            "fy": float(fy),
            "cx": float(cx),
            "cy": float(cy),
            "camera_to_world": np.asarray(camera_to_world, dtype=float).tolist(),
            "coordinate_frame": "world",
            "units": "pixel,m",
            "source_kind": DataSourceKind.CALIBRATION.value,
            "sim_time": float(sim_time),
            "frame_id": frame_id,
        }
        rec = CameraFrameRecord(
            frame_id=frame_id,
            run_id=self.run_id,
            session_id=self.session_id,
            mission_id=mission_id,
            skill_execution_id=skill_execution_id,
            observation_id=observation_id,
            camera_id=camera_id,
            sim_time=float(sim_time),
            rgb_sim_time=r_sim,
            depth_sim_time=d_sim,
            rgb_depth_sim_time_delta_s=delta_s,
            monotonic_wall_time=time.monotonic(),
            utc_timestamp=utc_now_iso(),
            width=width,
            height=height,
            rgb_path=rgb_rel,
            depth_path=depth_rel,
            rgb_sha256=rgb_sha,
            depth_sha256=depth_sha,
            source_module=source_module,
            quality_status=quality_status,
        )
        with self._lock:
            self.frames.append(rec)
            self.calibrations[f"{frame_id}:{camera_id}"] = cal_payload
        self._writer.enqueue_jsonl("frames.jsonl", rec.model_dump(mode="json"))
        self._writer.enqueue_text(
            "camera_calibration.json",
            json.dumps(
                {"schema_version": SCHEMA_VERSION, "calibrations": self.calibrations},
                indent=2,
                ensure_ascii=False,
            ),
        )
        return rec

    def record_pose_estimate(
        self,
        *,
        frame_id: str | None,
        camera_id: str,
        sim_time: float,
        diagnostics: dict[str, Any],
        mission_id: str | None = None,
        skill_execution_id: str | None = None,
        observation_id: str | None = None,
        rotation_cube_to_world: list[list[float]] | None = None,
        source_module: str = "cube_relay.embodied.perception_v2",
    ) -> PoseEstimateRecord:
        with self._lock:
            self._pose_version += 1
            version = self._pose_version
            pose_id = f"pose-{version:04d}-{uuid.uuid4().hex[:6]}"
        detected = diagnostics.get("estimated_center_world_m") is not None
        status = QualityStatus(
            str(diagnostics.get("quality_status") or (QualityStatus.VALID.value if detected else QualityStatus.MISSING.value))
        )
        rec = PoseEstimateRecord(
            pose_estimate_id=pose_id,
            pose_version=version,
            run_id=self.run_id,
            session_id=self.session_id,
            mission_id=mission_id,
            skill_execution_id=skill_execution_id,
            observation_id=observation_id,
            frame_id=frame_id,
            camera_id=camera_id,
            sim_time=float(sim_time),
            monotonic_wall_time=time.monotonic(),
            utc_timestamp=utc_now_iso(),
            source_module=source_module,
            quality_status=status,
            detection_bbox_xyxy=diagnostics.get("detection_bbox_xyxy"),
            pixel_centroid_xy=diagnostics.get("pixel_centroid_xy"),
            pixel_mean_xy=diagnostics.get("pixel_mean_xy"),
            pixel_count=int(diagnostics.get("pixel_count", 0)),
            initial_mask_pixel_count=int(diagnostics.get("initial_mask_pixel_count", 0)),
            depth_stats=dict(diagnostics.get("depth_stats") or {}),
            camera_coords_surface_m=diagnostics.get("camera_coords_surface_m"),
            world_coords_surface_m=diagnostics.get("world_coords_surface_m"),
            estimated_center_world_m=diagnostics.get("estimated_center_world_m"),
            estimated_yaw_rad=diagnostics.get("estimated_yaw_rad"),
            rotation_cube_to_world=rotation_cube_to_world,
            confidence=diagnostics.get("position_confidence"),
            yaw_confidence=diagnostics.get("yaw_confidence"),
            failure_reason=diagnostics.get("failure_reason"),
        )
        with self._lock:
            self.pose_estimates.append(rec)
            if rec.quality_status == QualityStatus.VALID:
                self._latest_pose_by_mission = rec
        self._writer.enqueue_jsonl("pose_estimates.jsonl", rec.model_dump(mode="json"))
        return rec

    @property
    def latest_valid_pose(self) -> PoseEstimateRecord | None:
        with self._lock:
            return self._latest_pose_by_mission


class GraspTargetRecorder:
    """Records Pose -> Grasp Target transformations and candidate/IK/collision audits."""

    def __init__(self, writer: _AsyncDiskWriter, *, run_id: str, session_id: str) -> None:
        self._writer = writer
        self.run_id = run_id
        self.session_id = session_id
        self._lock = threading.Lock()
        self.grasp_targets: list[GraspTargetRecord] = []

    def record_grasp_target(
        self,
        *,
        pose_estimate: PoseEstimateRecord | None,
        sim_time: float,
        mission_id: str | None = None,
        skill_execution_id: str | None = None,
        object_center_world_m: list[float] | None,
        object_yaw_rad: float | None,
        object_rotation_world: list[list[float]] | None = None,
        approach_direction_world: list[float] | None = None,
        approach_offset_local_xy_m: list[float] | None = None,
        world_offset_xy_m: list[float] | None = None,
        target_end_effector_pose: dict[str, Any] | None = None,
        target_gripper_width_m: float | None = None,
        pregrasp_gap_m: float | None = None,
        actual_end_effector_pose_at_plan: dict[str, Any] | None = None,
        candidates: list[dict[str, Any]] | None = None,
        selected_candidate_index: int | None = None,
        selected_face_pair: str | None = None,
        selected_option_id: str | None = None,
        ik_status: str = "UNKNOWN",
        reachability_status: str = "UNKNOWN",
        collision_check_status: str = "UNKNOWN",
        safety_parameters: dict[str, Any] | None = None,
        quality_status: QualityStatus = QualityStatus.VALID,
        failure_reason: str | None = None,
        source_module: str = "cube_relay.embodied.mujoco_v2",
    ) -> GraspTargetRecord:
        with self._lock:
            idx = len(self.grasp_targets) + 1
        grasp_id = f"grasp-{idx:04d}-{uuid.uuid4().hex[:6]}"
        pose_id = pose_estimate.pose_estimate_id if pose_estimate else "MISSING_POSE_ESTIMATE"
        pose_version = pose_estimate.pose_version if pose_estimate else 0
        pose_sim = pose_estimate.sim_time if pose_estimate else sim_time
        rec = GraspTargetRecord(
            grasp_target_id=grasp_id,
            run_id=self.run_id,
            session_id=self.session_id,
            mission_id=mission_id,
            skill_execution_id=skill_execution_id,
            pose_estimate_id=pose_id,
            pose_version=pose_version,
            pose_sim_time=float(pose_sim),
            pose_age_sim_s=max(0.0, float(sim_time) - float(pose_sim)),
            sim_time=float(sim_time),
            monotonic_wall_time=time.monotonic(),
            utc_timestamp=utc_now_iso(),
            source_module=source_module,
            quality_status=quality_status,
            object_center_world_m=object_center_world_m,
            object_yaw_rad=object_yaw_rad,
            object_rotation_world=object_rotation_world,
            approach_direction_world=approach_direction_world or [0.0, 0.0, -1.0],
            approach_offset_local_xy_m=approach_offset_local_xy_m or [],
            world_offset_xy_m=world_offset_xy_m or [],
            target_end_effector_pose=target_end_effector_pose or {},
            target_gripper_width_m=target_gripper_width_m,
            pregrasp_gap_m=pregrasp_gap_m,
            actual_end_effector_pose_at_plan=actual_end_effector_pose_at_plan or {},
            candidates=candidates or [],
            selected_candidate_index=selected_candidate_index,
            selected_face_pair=selected_face_pair,
            selected_option_id=selected_option_id,
            ik_status=ik_status,
            reachability_status=reachability_status,
            collision_check_status=collision_check_status,
            safety_parameters=safety_parameters or {},
            failure_reason=failure_reason,
        )
        with self._lock:
            self.grasp_targets.append(rec)
        self._writer.enqueue_jsonl("grasp_targets.jsonl", rec.model_dump(mode="json"))
        return rec

    def update_actual_contact_pose(self, grasp_target_id: str, actual_pose: dict[str, Any]) -> None:
        with self._lock:
            for item in self.grasp_targets:
                if item.grasp_target_id == grasp_target_id:
                    item.actual_end_effector_pose_at_contact = dict(actual_pose)
                    break
            snapshot_rows = [item.model_dump(mode="json") for item in self.grasp_targets]
        text = "".join(json.dumps(redact_secrets(r), ensure_ascii=False) + "\n" for r in snapshot_rows)
        self._writer.enqueue_text("grasp_targets.jsonl", text)


ROBOT_STATE_FIELDS = [
    "trajectory_id",
    "grasp_target_id",
    "skill_execution_id",
    "run_id",
    "sim_time",
    "monotonic_wall_time",
    "utc_timestamp",
    "controller_phase",
    "joint_robot_x",
    "joint_robot_y",
    "joint_robot_z",
    "joint_wrist_yaw",
    "joint_wrist_pitch",
    "joint_left_finger",
    "joint_right_finger",
    "vel_robot_x",
    "vel_robot_y",
    "vel_robot_z",
    "vel_wrist_yaw",
    "vel_wrist_pitch",
    "ctrl_robot_x",
    "ctrl_robot_y",
    "ctrl_robot_z",
    "ctrl_wrist_yaw",
    "ctrl_wrist_pitch",
    "ctrl_left_finger",
    "ctrl_right_finger",
    "ee_target_x_m",
    "ee_target_y_m",
    "ee_target_z_m",
    "ee_target_yaw_rad",
    "ee_actual_x_m",
    "ee_actual_y_m",
    "ee_actual_z_m",
    "ee_actual_yaw_rad",
    "ee_actual_pitch_rad",
    "gripper_inner_gap_m",
    "coordinate_frame",
    "units",
    "source_kind",
    "quality_status",
]

TRAJECTORY_CMD_FIELDS = [
    "trajectory_id",
    "grasp_target_id",
    "skill_execution_id",
    "run_id",
    "sim_time",
    "monotonic_wall_time",
    "utc_timestamp",
    "controller_phase",
    "cmd_robot_x",
    "cmd_robot_y",
    "cmd_robot_z",
    "cmd_wrist_yaw",
    "cmd_wrist_pitch",
    "cmd_left_finger",
    "cmd_right_finger",
    "cartesian_target_x_m",
    "cartesian_target_y_m",
    "cartesian_target_z_m",
    "coordinate_frame",
    "units",
    "source_kind",
    "quality_status",
]

AUDIT_POSE_FIELDS = [
    "run_id",
    "session_id",
    "sim_time",
    "monotonic_wall_time",
    "utc_timestamp",
    "phase",
    "cube_gt_x_m",
    "cube_gt_y_m",
    "cube_gt_z_m",
    "cube_gt_qw",
    "cube_gt_qx",
    "cube_gt_qy",
    "cube_gt_qz",
    "cube_gt_yaw_rad",
    "cube_gt_vx_m_s",
    "cube_gt_vy_m_s",
    "cube_gt_vz_m_s",
    "coordinate_frame",
    "units",
    "source_kind",
]


class TrajectoryRecorder:
    """Samples robot proprioception, actuator commands, EE poses, and optional audit GT."""

    def __init__(
        self,
        writer: _AsyncDiskWriter,
        *,
        run_id: str,
        session_id: str,
        sample_hz: float = 50.0,
        include_audit_ground_truth: bool = True,
    ) -> None:
        self._writer = writer
        self.run_id = run_id
        self.session_id = session_id
        self.sample_hz = float(sample_hz)
        self.include_audit_ground_truth = bool(include_audit_ground_truth)
        self._lock = threading.Lock()
        self.robot_states: list[dict[str, Any]] = []
        self.trajectory_commands: list[dict[str, Any]] = []
        self.audit_only_poses: list[dict[str, Any]] = []
        self._last_sample_sim_time: float | None = None
        self._traj_counter = 0
        self.active_trajectory_id: str | None = None
        self.active_grasp_target_id: str | None = None
        self.active_skill_execution_id: str | None = None
        self.active_ee_target: dict[str, float | None] = {}
        self.active_phase: str = "IDLE"

    def begin_trajectory(
        self,
        *,
        grasp_target_id: str | None = None,
        skill_execution_id: str | None = None,
        ee_target: dict[str, float | None] | None = None,
        phase: str = "APPROACH",
    ) -> str:
        with self._lock:
            self._traj_counter += 1
            traj_id = f"traj-{self._traj_counter:04d}-{uuid.uuid4().hex[:6]}"
            self.active_trajectory_id = traj_id
            self.active_grasp_target_id = grasp_target_id
            self.active_skill_execution_id = skill_execution_id
            self.active_ee_target = dict(ee_target or {})
            self.active_phase = phase
        return traj_id

    def set_phase(self, phase: str) -> None:
        with self._lock:
            self.active_phase = phase

    def record_command(
        self,
        *,
        sim_time: float,
        phase: str,
        ctrl: dict[str, float | None],
        cartesian_target: tuple[float, float, float] | None = None,
        trajectory_id: str | None = None,
        grasp_target_id: str | None = None,
        skill_execution_id: str | None = None,
    ) -> None:
        row = {
            "trajectory_id": trajectory_id or self.active_trajectory_id or "",
            "grasp_target_id": grasp_target_id or self.active_grasp_target_id or "",
            "skill_execution_id": skill_execution_id or self.active_skill_execution_id or "",
            "run_id": self.run_id,
            "sim_time": round(float(sim_time), 6),
            "monotonic_wall_time": round(time.monotonic(), 6),
            "utc_timestamp": utc_now_iso(),
            "controller_phase": phase,
            "cmd_robot_x": ctrl.get("robot_x_ctrl", ""),
            "cmd_robot_y": ctrl.get("robot_y_ctrl", ""),
            "cmd_robot_z": ctrl.get("robot_z_ctrl", ""),
            "cmd_wrist_yaw": ctrl.get("wrist_yaw_ctrl", ""),
            "cmd_wrist_pitch": ctrl.get("wrist_pitch_ctrl", ""),
            "cmd_left_finger": ctrl.get("left_finger_ctrl", ""),
            "cmd_right_finger": ctrl.get("right_finger_ctrl", ""),
            "cartesian_target_x_m": cartesian_target[0] if cartesian_target else "",
            "cartesian_target_y_m": cartesian_target[1] if cartesian_target else "",
            "cartesian_target_z_m": cartesian_target[2] if cartesian_target else "",
            "coordinate_frame": "world",
            "units": "m,rad,s",
            "source_kind": DataSourceKind.CONTROLLER_STATE.value,
            "quality_status": QualityStatus.VALID.value,
        }
        with self._lock:
            self.trajectory_commands.append(row)
        self._writer.enqueue_csv("trajectory_commands.csv", TRAJECTORY_CMD_FIELDS, row)

    def sample_backend_step(self, backend: Any, *, force: bool = False) -> None:
        sim_t = float(backend.data.time)
        min_dt = 1.0 / max(self.sample_hz, 1e-3)
        if not force and self._last_sample_sim_time is not None:
            if sim_t - self._last_sample_sim_time + 1e-9 < min_dt:
                return
        self._last_sample_sim_time = sim_t
        mj = backend.mujoco
        model = backend.model
        data = backend.data

        def _qpos(name: str) -> float:
            return float(data.qpos[model.jnt_qposadr[backend._joint(name)]])

        def _qvel(name: str) -> float:
            return float(data.qvel[model.jnt_dofadr[backend._joint(name)]])

        def _ctrl(name: str) -> float:
            return float(data.ctrl[backend._actuator(name)])

        gripper_id = backend._id(mj.mjtObj.mjOBJ_BODY, "gripper")
        ee_pos = data.xpos[gripper_id]
        left_pad = data.geom_xpos[backend._id(mj.mjtObj.mjOBJ_GEOM, "left_finger_pad")]
        right_pad = data.geom_xpos[backend._id(mj.mjtObj.mjOBJ_GEOM, "right_finger_pad")]
        jaw_gap = max(0.0, float(np.linalg.norm(left_pad - right_pad) - 0.024))

        with self._lock:
            traj_id = self.active_trajectory_id or ""
            grasp_id = self.active_grasp_target_id or ""
            skill_id = self.active_skill_execution_id or ""
            phase = self.active_phase
            ee_tgt = dict(self.active_ee_target)

        state_row = {
            "trajectory_id": traj_id,
            "grasp_target_id": grasp_id,
            "skill_execution_id": skill_id,
            "run_id": self.run_id,
            "sim_time": round(sim_t, 6),
            "monotonic_wall_time": round(time.monotonic(), 6),
            "utc_timestamp": utc_now_iso(),
            "controller_phase": phase,
            "joint_robot_x": round(_qpos("robot_x_joint"), 6),
            "joint_robot_y": round(_qpos("robot_y_joint"), 6),
            "joint_robot_z": round(_qpos("robot_z_joint"), 6),
            "joint_wrist_yaw": round(_qpos("wrist_yaw_joint"), 6),
            "joint_wrist_pitch": round(_qpos("wrist_pitch_joint"), 6),
            "joint_left_finger": round(_qpos("left_finger_joint"), 6),
            "joint_right_finger": round(_qpos("right_finger_joint"), 6),
            "vel_robot_x": round(_qvel("robot_x_joint"), 6),
            "vel_robot_y": round(_qvel("robot_y_joint"), 6),
            "vel_robot_z": round(_qvel("robot_z_joint"), 6),
            "vel_wrist_yaw": round(_qvel("wrist_yaw_joint"), 6),
            "vel_wrist_pitch": round(_qvel("wrist_pitch_joint"), 6),
            "ctrl_robot_x": round(_ctrl("robot_x_ctrl"), 6),
            "ctrl_robot_y": round(_ctrl("robot_y_ctrl"), 6),
            "ctrl_robot_z": round(_ctrl("robot_z_ctrl"), 6),
            "ctrl_wrist_yaw": round(_ctrl("wrist_yaw_ctrl"), 6),
            "ctrl_wrist_pitch": round(_ctrl("wrist_pitch_ctrl"), 6),
            "ctrl_left_finger": round(_ctrl("left_finger_ctrl"), 6),
            "ctrl_right_finger": round(_ctrl("right_finger_ctrl"), 6),
            "ee_target_x_m": ee_tgt.get("x_m", ""),
            "ee_target_y_m": ee_tgt.get("y_m", ""),
            "ee_target_z_m": ee_tgt.get("z_m", ""),
            "ee_target_yaw_rad": ee_tgt.get("yaw_rad", ""),
            "ee_actual_x_m": round(float(ee_pos[0]), 6),
            "ee_actual_y_m": round(float(ee_pos[1]), 6),
            "ee_actual_z_m": round(float(ee_pos[2]), 6),
            "ee_actual_yaw_rad": round(_qpos("wrist_yaw_joint"), 6),
            "ee_actual_pitch_rad": round(_qpos("wrist_pitch_joint"), 6),
            "gripper_inner_gap_m": round(jaw_gap, 6),
            "coordinate_frame": "world",
            "units": "m,rad,s",
            "source_kind": DataSourceKind.ROBOT_PROPRIOCEPTION.value,
            "quality_status": QualityStatus.VALID.value,
        }
        with self._lock:
            self.robot_states.append(state_row)
        self._writer.enqueue_csv("robot_states.csv", ROBOT_STATE_FIELDS, state_row)

        if self.include_audit_ground_truth:
            self.record_audit_pose(backend, phase=phase)

    def record_audit_pose(self, backend: Any, *, phase: str = "AUDIT") -> dict[str, Any]:
        """Audit-only simulator ground-truth pose; strictly isolated from perception/planning."""
        mj = backend.mujoco
        cube_id = backend._id(mj.mjtObj.mjOBJ_BODY, "cube")
        pos = backend.data.xpos[cube_id]
        quat = backend.data.xquat[cube_id]
        mat = backend.data.xmat[cube_id].reshape(3, 3)
        yaw = math.atan2(float(mat[1, 0]), float(mat[0, 0]))
        cvel = backend.data.cvel[cube_id]
        row = {
            "run_id": self.run_id,
            "session_id": self.session_id,
            "sim_time": round(float(backend.data.time), 6),
            "monotonic_wall_time": round(time.monotonic(), 6),
            "utc_timestamp": utc_now_iso(),
            "phase": phase,
            "cube_gt_x_m": round(float(pos[0]), 6),
            "cube_gt_y_m": round(float(pos[1]), 6),
            "cube_gt_z_m": round(float(pos[2]), 6),
            "cube_gt_qw": round(float(quat[0]), 6),
            "cube_gt_qx": round(float(quat[1]), 6),
            "cube_gt_qy": round(float(quat[2]), 6),
            "cube_gt_qz": round(float(quat[3]), 6),
            "cube_gt_yaw_rad": round(yaw, 6),
            "cube_gt_vx_m_s": round(float(cvel[3]), 6),
            "cube_gt_vy_m_s": round(float(cvel[4]), 6),
            "cube_gt_vz_m_s": round(float(cvel[5]), 6),
            "coordinate_frame": "world",
            "units": "m,rad,m/s,s",
            "source_kind": DataSourceKind.SIMULATOR_GROUND_TRUTH_AUDIT_ONLY.value,
        }
        with self._lock:
            self.audit_only_poses.append(row)
        self._writer.enqueue_csv("audit_only_poses.csv", AUDIT_POSE_FIELDS, row)
        return row


CONTACT_SAMPLE_FIELDS = [
    "contact_verification_id",
    "trajectory_id",
    "grasp_target_id",
    "skill_execution_id",
    "run_id",
    "sim_time",
    "monotonic_wall_time",
    "utc_timestamp",
    "phase",
    "phase_window",
    "left_contact",
    "right_contact",
    "bilateral_contact",
    "left_contact_count",
    "right_contact_count",
    "left_normal_force_n",
    "right_normal_force_n",
    "gripper_width_m",
    "cube_rel_x_m",
    "cube_rel_y_m",
    "cube_rel_z_m",
    "relative_slip_m",
    "unexpected_contacts_count",
    "unexpected_contacts_geoms",
    "coordinate_frame",
    "units",
    "source_kind",
    "quality_status",
]


class ContactRecorder:
    """Records physical contact samples and phase-windowed verification evidence."""

    def __init__(self, writer: _AsyncDiskWriter, *, run_id: str, session_id: str) -> None:
        self._writer = writer
        self.run_id = run_id
        self.session_id = session_id
        self._lock = threading.Lock()
        self.samples: list[dict[str, Any]] = []
        self.verifications: list[ContactVerificationRecord] = []
        self._current_verification_id: str | None = None
        self._current_samples: list[dict[str, Any]] = []

    def begin_verification(self) -> str:
        with self._lock:
            idx = len(self.verifications) + 1
            cv_id = f"cv-{idx:04d}-{uuid.uuid4().hex[:6]}"
            self._current_verification_id = cv_id
            self._current_samples = []
        return cv_id

    def record_sample(
        self,
        sample: dict[str, Any],
        *,
        trajectory_id: str | None = None,
        grasp_target_id: str | None = None,
        skill_execution_id: str | None = None,
        contact_verification_id: str | None = None,
    ) -> dict[str, Any]:
        phase = str(sample.get("phase", "UNKNOWN"))
        window = map_phase_to_window(phase)
        left_c = int(sample.get("left_contact_count", 0))
        right_c = int(sample.get("right_contact_count", 0))
        left_bool = left_c > 0
        right_bool = right_c > 0
        rel = sample.get("relative_cube_position_gripper_m") or [None, None, None]
        slip = sample.get("relative_slip_from_bilateral_contact_m")
        if slip is None:
            slip = sample.get("relative_slip_from_pregrasp_m", 0.0)
        unexp = sample.get("unexpected_gripper_contacts") or []
        unexp_geoms = [
            str(u.get("other_geom") if isinstance(u, dict) else u) for u in unexp
        ]
        cv_id = contact_verification_id or self._current_verification_id or ""
        row = {
            "contact_verification_id": cv_id,
            "trajectory_id": trajectory_id or "",
            "grasp_target_id": grasp_target_id or "",
            "skill_execution_id": skill_execution_id or "",
            "run_id": self.run_id,
            "sim_time": round(float(sample.get("time_s", 0.0)), 6),
            "monotonic_wall_time": round(time.monotonic(), 6),
            "utc_timestamp": utc_now_iso(),
            "phase": phase,
            "phase_window": window,
            "left_contact": left_bool,
            "right_contact": right_bool,
            "bilateral_contact": bool(left_bool and right_bool),
            "left_contact_count": left_c,
            "right_contact_count": right_c,
            "left_normal_force_n": round(float(sample.get("left_normal_force_n", 0.0)), 6),
            "right_normal_force_n": round(float(sample.get("right_normal_force_n", 0.0)), 6),
            "gripper_width_m": round(float(sample.get("jaw_inner_gap_m", 0.0)), 6),
            "cube_rel_x_m": round(float(rel[0]), 6) if rel[0] is not None else "",
            "cube_rel_y_m": round(float(rel[1]), 6) if rel[1] is not None else "",
            "cube_rel_z_m": round(float(rel[2]), 6) if rel[2] is not None else "",
            "relative_slip_m": round(float(slip), 6) if slip is not None else 0.0,
            "unexpected_contacts_count": len(unexp_geoms),
            "unexpected_contacts_geoms": ";".join(unexp_geoms),
            "coordinate_frame": "gripper",
            "units": "m,N,s",
            "source_kind": DataSourceKind.ROBOT_PROPRIOCEPTION.value,
            "quality_status": QualityStatus.VALID.value,
        }
        with self._lock:
            self.samples.append(row)
            self._current_samples.append(row)
        self._writer.enqueue_csv("contact_samples.csv", CONTACT_SAMPLE_FIELDS, row)
        return row

    @staticmethod
    def summarize_phase_windows(samples: list[dict[str, Any]]) -> dict[str, ContactPhaseWindowSummary]:
        windows_order = ("Approach", "Initial Contact", "Grasp Closure", "Lift / Hold", "Reorientation")
        grouped: dict[str, list[dict[str, Any]]] = {w: [] for w in windows_order}
        for row in samples:
            w = str(row.get("phase_window") or map_phase_to_window(str(row.get("phase", ""))))
            grouped.setdefault(w, []).append(row)
        summaries: dict[str, ContactPhaseWindowSummary] = {}
        for w, rows in grouped.items():
            if not rows:
                summaries[w] = ContactPhaseWindowSummary(window_name=w)
                continue
            rows_sorted = sorted(rows, key=lambda r: float(r["sim_time"]))
            t0 = float(rows_sorted[0]["sim_time"])
            t1 = float(rows_sorted[-1]["sim_time"])
            duration = max(0.0, t1 - t0)
            bilat_dur = 0.0
            for prev, curr in zip(rows_sorted, rows_sorted[1:]):
                if bool(prev["bilateral_contact"]) and bool(curr["bilateral_contact"]):
                    bilat_dur += max(0.0, float(curr["sim_time"]) - float(prev["sim_time"]))
            n = len(rows_sorted)
            lf = [float(r["left_normal_force_n"]) for r in rows_sorted]
            rf = [float(r["right_normal_force_n"]) for r in rows_sorted]
            slips = [float(r["relative_slip_m"]) for r in rows_sorted]
            geoms = sorted({
                g
                for r in rows_sorted
                for g in str(r.get("unexpected_contacts_geoms") or "").split(";")
                if g
            })
            unexp_cnt = sum(int(r.get("unexpected_contacts_count", 0)) for r in rows_sorted)
            summaries[w] = ContactPhaseWindowSummary(
                window_name=w,
                sample_count=n,
                start_sim_time=t0,
                end_sim_time=t1,
                duration_s=round(duration, 6),
                bilateral_contact_duration_s=round(bilat_dur, 6),
                bilateral_contact_fraction=round(sum(bool(r["bilateral_contact"]) for r in rows_sorted) / n, 6),
                left_contact_fraction=round(sum(bool(r["left_contact"]) for r in rows_sorted) / n, 6),
                right_contact_fraction=round(sum(bool(r["right_contact"]) for r in rows_sorted) / n, 6),
                left_normal_force_mean_n=round(sum(lf) / n, 6),
                left_normal_force_min_n=round(min(lf), 6),
                left_normal_force_max_n=round(max(lf), 6),
                right_normal_force_mean_n=round(sum(rf) / n, 6),
                right_normal_force_min_n=round(min(rf), 6),
                right_normal_force_max_n=round(max(rf), 6),
                max_relative_slip_m=round(max(slips), 6),
                unexpected_contacts_count=unexp_cnt,
                unexpected_contacts_geoms=geoms,
            )
        return summaries

    def finalize_verification(
        self,
        *,
        skill_name: str,
        sim_time: float,
        trajectory_id: str | None,
        grasp_target_id: str | None,
        pose_estimate_id: str | None,
        skill_execution_id: str | None,
        bilateral_contact_fraction: float,
        left_contact_fraction: float,
        right_contact_fraction: float,
        left_normal_force_n: float,
        right_normal_force_n: float,
        relative_slip_m: float,
        gripper_width_m: float | None,
        lift_height_m: float | None,
        object_motion_relative_to_gripper_m: list[float] | None,
        object_followed_end_effector: bool,
        unintended_contacts: list[str],
        verification_thresholds: dict[str, Any],
        verification_result: bool,
        failure_reason: str | None,
        contact_verification_id: str | None = None,
    ) -> ContactVerificationRecord:
        with self._lock:
            cv_id = contact_verification_id or self._current_verification_id or f"cv-{len(self.verifications) + 1:04d}"
            samples = list(self._current_samples)
        windows = self.summarize_phase_windows(samples)
        bilat_dur = sum(
            w.bilateral_contact_duration_s
            for name, w in windows.items()
            if name in {"Initial Contact", "Grasp Closure", "Lift / Hold", "Reorientation"}
        )
        rec = ContactVerificationRecord(
            contact_verification_id=cv_id,
            run_id=self.run_id,
            session_id=self.session_id,
            skill_execution_id=skill_execution_id,
            trajectory_id=trajectory_id,
            grasp_target_id=grasp_target_id,
            pose_estimate_id=pose_estimate_id,
            skill_name=skill_name,
            sim_time=float(sim_time),
            monotonic_wall_time=time.monotonic(),
            utc_timestamp=utc_now_iso(),
            quality_status=QualityStatus.VALID if verification_result else QualityStatus.INVALID,
            bilateral_contact_duration_s=round(bilat_dur, 6),
            bilateral_contact_fraction=round(float(bilateral_contact_fraction), 6),
            left_contact_fraction=round(float(left_contact_fraction), 6),
            right_contact_fraction=round(float(right_contact_fraction), 6),
            left_normal_force_n=round(float(left_normal_force_n), 6),
            right_normal_force_n=round(float(right_normal_force_n), 6),
            relative_slip_m=round(float(relative_slip_m), 6),
            gripper_width_m=round(float(gripper_width_m), 6) if gripper_width_m is not None else None,
            lift_height_m=round(float(lift_height_m), 6) if lift_height_m is not None else None,
            object_motion_relative_to_gripper_m=object_motion_relative_to_gripper_m,
            object_followed_end_effector=bool(object_followed_end_effector),
            unintended_contacts=list(unintended_contacts),
            grasp_stability_status="STABLE_VERIFIED" if verification_result else (failure_reason or "UNSTABLE_OR_FAILED"),
            verification_thresholds=dict(verification_thresholds),
            verification_result=bool(verification_result),
            failure_reason=failure_reason,
            phase_windows=windows,
        )
        with self._lock:
            self.verifications.append(rec)
            self._current_verification_id = None
            self._current_samples = []
        self._writer.enqueue_jsonl("contact_verifications.jsonl", rec.model_dump(mode="json"))
        return rec


class ExperimentRun:
    """Single experiment run owning dedicated EventStore & causal recorders."""

    def __init__(
        self,
        *,
        config: ExperimentConfig,
        run_dir: Path,
        save_rgbd_frames: bool = True,
    ) -> None:
        self.config = config
        self.run_dir = Path(run_dir)
        self.writer = _AsyncDiskWriter(self.run_dir, max_disk_mb=config.max_disk_mb)
        self.events = EventStore(self.writer)
        self.poses = PoseEstimateRecorder(
            self.writer,
            run_id=config.run_id,
            session_id=config.session_id,
            save_rgbd_frames=save_rgbd_frames,
        )
        self.grasp_targets = GraspTargetRecorder(
            self.writer, run_id=config.run_id, session_id=config.session_id
        )
        self.trajectories = TrajectoryRecorder(
            self.writer,
            run_id=config.run_id,
            session_id=config.session_id,
            sample_hz=config.trajectory_sample_hz,
            include_audit_ground_truth=config.include_audit_ground_truth,
        )
        self.contacts = ContactRecorder(
            self.writer, run_id=config.run_id, session_id=config.session_id
        )
        self.skill_executions: list[dict[str, Any]] = []
        self.session_snapshot: dict[str, Any] = {}
        self.metrics: dict[str, Any] = {}
        self.status: str = "RECORDING"
        self.mission_id: str | None = None
        self._closed = False
        self.writer.enqueue_text(
            "config.json",
            json.dumps(redact_secrets(config.model_dump(mode="json")), indent=2, ensure_ascii=False),
        )
        self._write_summary(sim_time=0.0)
        ref = weakref.ref(self)
        atexit.register(lambda: ref() and ref().close())  # type: ignore[arg-type]

    def set_skill_executions(self, executions: list[dict[str, Any]]) -> None:
        self.skill_executions = list(executions)
        self.writer.enqueue_text(
            "skill_executions.json",
            json.dumps(redact_secrets(self.skill_executions), indent=2, ensure_ascii=False),
        )

    def set_snapshot(self, snapshot: dict[str, Any]) -> None:
        self.session_snapshot = dict(snapshot)
        if snapshot.get("mission") and isinstance(snapshot["mission"], dict):
            self.mission_id = snapshot["mission"].get("mission_id")
        self.writer.enqueue_text(
            "session_snapshot.json",
            json.dumps(redact_secrets(self.session_snapshot), indent=2, ensure_ascii=False),
        )
        self._write_summary(sim_time=float(snapshot.get("sim_time") or 0.0))

    def finalize(self, *, metrics: dict[str, Any] | None = None, report_md: str | None = None, status: str = "FINALIZED") -> None:
        self.status = status
        if metrics is not None:
            self.metrics = dict(metrics)
            self.writer.enqueue_text(
                "metrics.json",
                json.dumps(redact_secrets(self.metrics), indent=2, ensure_ascii=False),
            )
        if report_md is not None:
            self.writer.enqueue_text("report.md", report_md)
        self._write_summary(sim_time=float(self.session_snapshot.get("sim_time") or 0.0))
        self.writer.flush()

    def _write_summary(self, *, sim_time: float) -> None:
        summary = ExperimentRunSummary(
            run_id=self.config.run_id,
            session_id=self.config.session_id,
            seed=self.config.seed,
            mission_id=self.mission_id,
            mission_type=self.config.mission_type,
            planner_mode=self.config.planner_mode,
            frame_source=str(self.session_snapshot.get("frame_source") or "REAL_MUJOCO_RENDERER"),
            recording_status=self.status,
            created_utc=self.config.created_utc,
            updated_utc=utc_now_iso(),
            sim_time=sim_time,
            run_dir=str(self.run_dir),
            counts={
                "frames": len(self.poses.frames),
                "pose_estimates": len(self.poses.pose_estimates),
                "grasp_targets": len(self.grasp_targets.grasp_targets),
                "trajectory_commands": len(self.trajectories.trajectory_commands),
                "robot_states": len(self.trajectories.robot_states),
                "contact_samples": len(self.contacts.samples),
                "contact_verifications": len(self.contacts.verifications),
                "decision_events": len(self.events.decision_events),
                "trace_events": len(self.events.trace_events),
                "observations": len(self.events.observations),
            },
            perturbation=dict(self.config.perturbation),
            has_audit_truth=bool(self.trajectories.audit_only_poses),
            has_rgbd=bool(self.poses.frames),
            has_trajectory=bool(self.trajectories.robot_states or self.trajectories.trajectory_commands),
        )
        self.writer.enqueue_text(
            "run_summary.json",
            json.dumps(summary.model_dump(mode="json"), indent=2, ensure_ascii=False),
        )

    def flush(self) -> None:
        self.writer.flush()

    def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        if self.status == "RECORDING":
            self.status = "FLUSHED"
            self._write_summary(sim_time=float(self.session_snapshot.get("sim_time") or 0.0))
        self.writer.close()


class ExperimentRecorder:
    """Lifecycle manager creating and indexing ExperimentRuns on disk."""

    def __init__(self, base_dir: str | Path | None = None) -> None:
        self.base_dir = Path(base_dir or DEFAULT_EXPERIMENTS_DIR).resolve()
        self.base_dir.mkdir(parents=True, exist_ok=True)
        self.current_run: ExperimentRun | None = None
        self._runs: dict[str, ExperimentRun] = {}

    def start_run(
        self,
        *,
        session_id: str,
        seed: int,
        mission_type: str = "INSPECT_CUBE",
        planner_mode: str = "DETERMINISTIC_PLANNER",
        trajectory_sample_hz: float = 50.0,
        max_disk_mb: float = 256.0,
        include_audit_ground_truth: bool = True,
        save_rgbd_frames: bool = True,
        perturbation: dict[str, Any] | None = None,
        scene_xml_path: str | None = None,
        grasp_config: dict[str, Any] | None = None,
        run_id: str | None = None,
    ) -> ExperimentRun:
        if self.current_run is not None:
            self.current_run.flush()
        rid = validate_run_id(run_id or f"run-{int(time.time())}-{uuid.uuid4().hex[:8]}")
        run_dir = (self.base_dir / rid).resolve()
        if self.base_dir not in run_dir.parents:
            raise ValueError("Unsafe run directory")
        cfg = ExperimentConfig(
            run_id=rid,
            session_id=session_id,
            seed=int(seed),
            mission_type=mission_type,
            planner_mode=planner_mode,
            trajectory_sample_hz=trajectory_sample_hz,
            max_disk_mb=max_disk_mb,
            include_audit_ground_truth=include_audit_ground_truth,
            perturbation=dict(perturbation or {}),
            git_commit=_current_git_commit(),
            scene_xml_path=scene_xml_path,
            grasp_config=dict(grasp_config or {}),
        )
        run = ExperimentRun(config=cfg, run_dir=run_dir, save_rgbd_frames=save_rgbd_frames)
        self.current_run = run
        self._runs[rid] = run
        return run

    def get_run(self, run_id: str) -> ExperimentRun | None:
        validate_run_id(run_id)
        return self._runs.get(run_id)

    def resolve_run_dir(self, run_id: str) -> Path:
        validate_run_id(run_id)
        target = (self.base_dir / run_id).resolve()
        if self.base_dir not in target.parents:
            raise ValueError("Directory traversal blocked")
        if not target.exists():
            raise FileNotFoundError(f"Run {run_id!r} not found")
        return target

    def list_runs(self) -> list[dict[str, Any]]:
        if not self.base_dir.exists():
            return []
        summaries: list[dict[str, Any]] = []
        for child in sorted(self.base_dir.iterdir(), key=lambda p: p.stat().st_mtime, reverse=True):
            if not child.is_dir():
                continue
            summary_file = child / "run_summary.json"
            if summary_file.exists():
                try:
                    summaries.append(json.loads(summary_file.read_text(encoding="utf-8")))
                    continue
                except Exception:
                    pass
            summaries.append({
                "run_id": child.name,
                "recording_status": "DISK_ONLY",
                "run_dir": str(child),
            })
        return summaries

    def close(self) -> None:
        for run in list(self._runs.values()):
            run.close()
