"""Real MuJoCo SimulationSession integrating Mission, SkillRegistry, Planner, and DecisionEvents."""

from __future__ import annotations

import base64
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict
import io
import math
import threading
import time
from pathlib import Path
from typing import Any, Callable
import uuid

import numpy as np
from PIL import Image

from cube_relay.cube import CubeEngine, CubeSolver, SOLVED_FACELETS
from cube_relay.cube.validation import StateValidator
from cube_relay.embodied.active_inspection_v7 import ContinuousActiveInspector
from cube_relay.embodied.perception_v2 import DeterministicCubeLocalizer
from cube_relay.embodied.physical_u import ContactUTurn
from cube_relay.embodied.visual_turn_loop import compare_observations

from .events import (
    DecisionEvent,
    DecisionEventLog,
    DecisionEventType,
    TraceEventLog,
    TraceEventType,
    now_wall_time,
)
from .models import (
    AgentObservabilityState,
    MissionState,
    MissionStatus,
    MissionType,
    ObservationReference,
    PlanState,
    PlanStep,
    PlanStepStatus,
    SkillExecutionState,
)
from .planner import MISSION_SPECS, DecisionPolicy, DeterministicMissionPlanner
from .skill_registry import SkillRegistry

FACE_ORDER = ("U", "R", "F", "D", "L", "B")
BACKEND_TO_UI_COLOR = {
    "U": "W",
    "R": "R",
    "F": "G",
    "D": "Y",
    "L": "O",
    "B": "B",
}

CAMERA_PRESET_SPECS: dict[str, dict[str, Any]] = {
    "overview": {
        "label": "场景总览",
        "lookat": [0.10, -0.10, 0.72],
        "az": 135.0,
        "el": -28.0,
        "dist": 1.15,
    },
    "gripper_closeup": {
        "label": "夹爪特写",
        "track_body": "gripper",
        "az": 148.0,
        "el": -20.0,
        "dist": 0.48,
    },
    "cube_closeup": {
        "label": "魔方特写",
        "track_body": "cube",
        "az": 125.0,
        "el": -32.0,
        "dist": 0.36,
    },
    "top_ortho": {
        "label": "俯视相机",
        "lookat": [0.05, -0.05, 0.70],
        "az": 90.0,
        "el": -86.0,
        "dist": 0.95,
    },
}


def _face_char_to_ui(ch: str | None) -> str:
    if ch is None or ch == "?":
        return "UNKNOWN"
    return BACKEND_TO_UI_COLOR.get(ch, "UNKNOWN")


def _encode_jpeg_data_url(rgb: np.ndarray, quality: int = 84) -> str:
    buf = io.BytesIO()
    Image.fromarray(np.asarray(rgb, dtype=np.uint8)).save(buf, format="JPEG", quality=quality)
    b64 = base64.b64encode(buf.getvalue()).decode("ascii")
    return f"data:image/jpeg;base64,{b64}"


def _depth_to_colormap_rgb(depth_m: np.ndarray, zmin: float = 0.35, zmax: float = 2.25) -> np.ndarray:
    """Convert metric depth [m] to an informative pseudo-color RGB image."""
    d = np.asarray(depth_m, dtype=np.float32)
    valid = np.isfinite(d) & (d > 0.0) & (d < 10.0)
    norm = np.zeros_like(d, dtype=np.float32)
    span = max(zmax - zmin, 1e-4)
    norm[valid] = np.clip((d[valid] - zmin) / span, 0.0, 1.0)
    # Near=warm cyan/green, far=deep blue/slate
    r = np.clip(1.5 - np.abs(4.0 * norm - 3.0), 0.0, 1.0)
    g = np.clip(1.5 - np.abs(4.0 * norm - 2.0), 0.0, 1.0)
    b = np.clip(1.5 - np.abs(4.0 * norm - 1.0), 0.0, 1.0)
    rgb = np.stack([r, g, b], axis=-1)
    rgb[~valid] = [0.06, 0.09, 0.16]
    return (np.clip(rgb, 0.0, 1.0) * 255.0).astype(np.uint8)


def _format_facelets_for_ui(
    facelets_str: str | None,
    *,
    conflicts: set[str] | None = None,
    observation_counts: dict[int, int] | None = None,
) -> list[dict[str, Any]]:
    conflicts = conflicts or set()
    observation_counts = observation_counts or {}
    out: list[dict[str, Any]] = []
    for idx in range(54):
        face = FACE_ORDER[idx // 9]
        local_idx = idx % 9
        ch = facelets_str[idx] if facelets_str and len(facelets_str) == 54 else None
        color = _face_char_to_ui(ch)
        out.append({
            "index": idx,
            "face": face,
            "localIdx": local_idx,
            "color": color,
            "confidence": 0.98 if color != "UNKNOWN" else None,
            "observationCount": observation_counts.get(idx, 1 if color != "UNKNOWN" else 0),
            "hasConflict": f"{face}{local_idx}" in conflicts,
        })
    return out


def _plan_step_to_legacy_stage(step: PlanStep) -> dict[str, Any]:
    status = step.status.value
    if status == "BLOCKED":
        legacy_status = "FAILED"
    else:
        legacy_status = status
    return {
        "id": step.step_id,
        "index": step.index,
        "title": step.title,
        "skillName": step.skill_id,
        "status": legacy_status,
        "implemented": step.implemented,
        "elapsedSec": step.elapsed_sec,
    }


class SimulationSession:
    """Thread-safe controller owning a real MuJoCo backend and Mission orchestrator."""

    def __init__(
        self,
        *,
        seed: int = 0,
        width: int = 480,
        height: int = 320,
        use_dedicated_thread: bool = False,
        planner: DecisionPolicy | None = None,
        registry: SkillRegistry | None = None,
        stream_interval_sec: float = 0.4,
        stream_sim_interval_sec: float = 0.25,
        video_path: Path | None = None,
    ) -> None:
        self.seed = int(seed)
        self.width = int(width)
        self.height = int(height)
        self.use_dedicated_thread = use_dedicated_thread
        self.stream_interval_sec = float(stream_interval_sec)
        self.stream_sim_interval_sec = float(stream_sim_interval_sec)
        self.video_path = video_path
        self.session_id = f"LIVE-SEED{self.seed}-{uuid.uuid4().hex[:6].upper()}"

        self.registry = registry or SkillRegistry()
        self.planner: DecisionPolicy = planner or DeterministicMissionPlanner()
        self.event_log = DecisionEventLog()
        self.trace_log = TraceEventLog()
        self._mission_trace_event_id: str | None = None
        self._active_composite_trace_event_id: str | None = None

        self._executor: ThreadPoolExecutor | None = (
            ThreadPoolExecutor(max_workers=1, thread_name_prefix="cuberelay-gl")
            if use_dedicated_thread
            else None
        )
        self._lock = threading.Lock()
        self._stop_event = threading.Event()
        self._subscribers: set[Callable[[dict[str, Any]], None]] = set()
        self._running = False
        self._backend: Any = None
        self._initial_rgba: np.ndarray | None = None
        self._initial_sentinel: str | None = None
        self._initial_model_id: int | None = None
        self._initial_data_id: int | None = None

        # Camera & debug state
        self.active_camera = "overview"
        self.camera_azimuth_deg = CAMERA_PRESET_SPECS["overview"]["az"]
        self.camera_elevation_deg = CAMERA_PRESET_SPECS["overview"]["el"]
        self.camera_distance_m = CAMERA_PRESET_SPECS["overview"]["dist"]
        self.debug_overlays: dict[str, bool] = {
            "contactForces": True,
            "collisionGeoms": False,
            "tcpFrame": True,
            "hudVisible": True,
        }

        # Mission / Plan / Execution state
        self.selected_mission_type = MissionType.INSPECT_CUBE
        self.mission: MissionState | None = None
        self.plan: PlanState | None = None
        self.skill_executions: list[SkillExecutionState] = []
        self.agent_state = AgentObservabilityState(
            planner_mode=self.planner.mode,
            planner_name=self.planner.name,
            llm_connected=self.planner.llm_connected,
            llm_model=self.planner.llm_model,
            status_label=self.planner.status_label(),
        )
        self.last_observation_ref: ObservationReference | None = None
        self.observed_facelets_str: str | None = None
        self.predicted_facelets_str: str | None = None
        self.conflict_set: set[str] = set()
        self.cube_validation_status = "UNVERIFIED"
        self.physical_verification: dict[str, Any] | None = None
        self.last_turn_angle_deg: float | None = None
        self.last_contact_force_n: float | None = None
        self.last_base_contact_n: float | None = None
        self.last_turn_contact_n: float | None = None
        self.scene_state: dict[str, Any] = {}

        # Latest rendered frame URLs & snapshot
        self._main_frame_url: str | None = None
        self._wrist_rgb_url: str | None = None
        self._wrist_depth_url: str | None = None
        self._depth_range_m: list[float] = [0.35, 2.25]
        self._latest_snapshot: dict[str, Any] = {}
        self._last_stream_wall = 0.0
        self._last_stream_sim = 0.0

        self._run_on_gl_thread(self._init_backend_sync)

    # ------------------------------------------------------------------
    # Threading & subscription helpers
    # ------------------------------------------------------------------

    def _run_on_gl_thread(self, fn: Callable[[], Any]) -> Any:
        if self._executor is not None:
            return self._executor.submit(fn).result()
        return fn()

    def _stream_update_due(self, *, now_wall: float, now_sim: float) -> bool:
        """Return whether a live frame refresh is due during physics stepping.

        Wall-clock throttling alone is unsafe here: a software-rendered RGB-D
        refresh can take longer than the throttle interval, which makes the
        very next 2 ms physics step refresh again. Requiring simulation-time
        progress prevents that feedback loop while retaining live updates.
        """
        return (
            self.stream_interval_sec > 0
            and self.stream_sim_interval_sec > 0
            and now_wall - self._last_stream_wall >= self.stream_interval_sec
            and now_sim - self._last_stream_sim >= self.stream_sim_interval_sec
        )

    def subscribe(self, callback: Callable[[dict[str, Any]], None]) -> None:
        with self._lock:
            self._subscribers.add(callback)

    def unsubscribe(self, callback: Callable[[dict[str, Any]], None]) -> None:
        with self._lock:
            self._subscribers.discard(callback)

    def _emit_snapshot(self, *, refresh_frames: bool = False) -> dict[str, Any]:
        if refresh_frames:
            self._render_live_frames()
        snap = self._build_snapshot()
        with self._lock:
            self._latest_snapshot = snap
            subs = list(self._subscribers)
        for cb in subs:
            try:
                cb(snap)
            except Exception:
                pass
        return snap

    def get_snapshot(self) -> dict[str, Any]:
        with self._lock:
            return dict(self._latest_snapshot)

    def _snapshot_with_current_camera(self) -> dict[str, Any]:
        """Update cached camera metadata without touching MuJoCo off the GL thread."""
        with self._lock:
            snap = dict(self._latest_snapshot)
            snap.update(
                active_camera=self.active_camera,
                camera_azimuth_deg=self.camera_azimuth_deg,
                camera_elevation_deg=self.camera_elevation_deg,
                camera_distance_m=self.camera_distance_m,
            )
            self._latest_snapshot = snap
            return dict(snap)

    def get_capabilities(self) -> dict[str, Any]:
        return self.registry.snapshot().model_dump(mode="json")

    def get_events(self) -> list[dict[str, Any]]:
        return [ev.model_dump(mode="json") for ev in self.event_log.events]

    # ------------------------------------------------------------------
    # MuJoCo lifecycle & real rendering (runs strictly on GL thread)
    # ------------------------------------------------------------------

    def _init_backend_sync(self) -> None:
        from cube_relay.embodied.mujoco_v2 import MuJoCoEmbodiedBackend

        self._backend = MuJoCoEmbodiedBackend(
            physical_u=True,
            width=self.width,
            height=self.height,
            video_path=self.video_path,
            video_timing="sim_time",
        )
        self._reset_backend_scene(self.seed)
        self._emit_snapshot(refresh_frames=True)

    def _reset_backend_scene(self, seed: int) -> None:
        b = self._backend
        self.seed = int(seed)
        self.session_id = f"LIVE-SEED{self.seed}-{uuid.uuid4().hex[:6].upper()}"
        # Restore original unpatched methods if previously locked
        if hasattr(self, "_orig_set_sticker_colors"):
            b._set_sticker_colors = self._orig_set_sticker_colors
            b.engine.apply_move = self._orig_engine_apply_move
            b.reset_random = self._orig_reset_random
        b.reset_random(self.seed, 15)
        self._orig_set_sticker_colors = b._set_sticker_colors
        self._orig_engine_apply_move = b.engine.apply_move
        self._orig_reset_random = b.reset_random
        self._initial_rgba = b.model.geom_rgba.copy()
        self._initial_sentinel = b._appearance_state
        self._initial_model_id = id(b.model)
        self._initial_data_id = id(b.data)

        self.mission = None
        self.plan = None
        self.skill_executions.clear()
        self.event_log.clear()
        self.trace_log.clear()
        self._mission_trace_event_id = None
        self._active_composite_trace_event_id = None
        self.last_observation_ref = None
        self.observed_facelets_str = None
        self.predicted_facelets_str = None
        self.conflict_set.clear()
        self.cube_validation_status = "UNVERIFIED"
        self.physical_verification = None
        self.last_turn_angle_deg = None
        self.last_contact_force_n = None
        self.last_base_contact_n = None
        self.last_turn_contact_n = None
        self.scene_state = {
            "simulation_initialized": True,
            "physical_u_scene_enabled": bool(b.physical_u),
            "turn_station_available": bool(b.physical_u),
            "cube_localized": False,
            "scan_attempted": False,
            "cube_localized_and_scanned": False,
            "cube_state_validated": False,
            "symbolic_plan_available": False,
            "u_turns_completed": 0,
            "physical_u_turn_executed": False,
            "turn_station_cleared": False,
            "symbolic_solution": [],
        }
        self.agent_state = AgentObservabilityState(
            planner_mode=self.planner.mode,
            planner_name=self.planner.name,
            llm_connected=self.planner.llm_connected,
            llm_model=self.planner.llm_model,
            status_label=self.planner.status_label(),
        )
        # Create an initial preview plan for the selected mission so UI shows what will run
        preview_mission = self._new_mission_object(self.selected_mission_type)
        self.mission = preview_mission
        self.plan = self.planner.create_plan(
            preview_mission,
            self.registry,
            plan_id=f"plan-{preview_mission.mission_id}",
        )
        self.mission.current_plan_id = self.plan.plan_id

    def _lock_backend_anti_cheat(self) -> None:
        b = self._backend

        def _forbidden(*args: Any, **kwargs: Any) -> None:
            raise AssertionError("Post-initialization software recolor / symbolic mutation / reset is forbidden")

        b._set_sticker_colors = _forbidden
        b.engine.apply_move = _forbidden
        b.reset_random = _forbidden

    def _render_live_frames(self) -> None:
        b = self._backend
        if b is None:
            return
        mj = b.mujoco
        cam = mj.MjvCamera()
        mj.mjv_defaultFreeCamera(b.model, cam)
        spec = CAMERA_PRESET_SPECS.get(self.active_camera, CAMERA_PRESET_SPECS["overview"])
        if "track_body" in spec:
            bid = b._id(mj.mjtObj.mjOBJ_BODY, spec["track_body"])
            cam.lookat[:] = b.data.xpos[bid]
        else:
            cam.lookat[:] = spec["lookat"]
        cam.azimuth = float(self.camera_azimuth_deg)
        cam.elevation = float(self.camera_elevation_deg)
        cam.distance = float(self.camera_distance_m)

        opt = mj.MjvOption()
        mj.mjv_defaultOption(opt)
        opt.flags[mj.mjtVisFlag.mjVIS_CONTACTFORCE] = 1 if self.debug_overlays.get("contactForces") else 0
        opt.flags[mj.mjtVisFlag.mjVIS_CONTACTPOINT] = 1 if self.debug_overlays.get("collisionGeoms") else 0
        if self.debug_overlays.get("tcpFrame"):
            opt.frame = mj.mjtFrame.mjFRAME_WORLD
        else:
            opt.frame = mj.mjtFrame.mjFRAME_NONE

        b.renderer.disable_depth_rendering()
        b.renderer.update_scene(b.data, camera=cam, scene_option=opt)
        main_rgb = b.renderer.render().copy()
        self._main_frame_url = _encode_jpeg_data_url(main_rgb, quality=85)

        # Auxiliary RGB + Metric Depth from fixed overhead / scan_top camera
        aux_cam = "overhead" if self.active_camera != "top_ortho" else "scan_top"
        rgbd = b.capture_rgbd(aux_cam)
        self._wrist_rgb_url = _encode_jpeg_data_url(rgbd.rgb, quality=82)
        if rgbd.depth_m is not None:
            valid = rgbd.depth_m[np.isfinite(rgbd.depth_m) & (rgbd.depth_m > 0.0) & (rgbd.depth_m < 10.0)]
            if len(valid):
                zmin = float(np.percentile(valid, 2))
                zmax = max(zmin + 0.25, float(np.percentile(valid, 95)))
            else:
                zmin, zmax = 0.35, 2.25
            self._depth_range_m = [round(zmin, 2), round(zmax, 2)]
            depth_rgb = _depth_to_colormap_rgb(rgbd.depth_m, zmin=zmin, zmax=zmax)
            self._wrist_depth_url = _encode_jpeg_data_url(depth_rgb, quality=82)

    def _read_telemetry(self) -> dict[str, Any]:
        b = self._backend
        if b is None:
            return {
                "contactForceN": None,
                "gripperWidthMm": None,
                "gripperState": "UNKNOWN",
                "jointPositionsRad": None,
                "cubePositionMm": None,
                "layerTurnAngleDeg": None,
                "targetLayer": None,
                "collisionDetected": None,
                "slipDetected": None,
                "renderFps": None,
                "failureReason": None,
            }
        mj = b.mujoco
        left_touch, right_touch, left_f, right_f = b._finger_contact_forces()
        contact_force = max(left_f, right_f, self.last_contact_force_n or 0.0)
        lq = float(b.data.qpos[b.model.jnt_qposadr[b._joint("left_finger_joint")]])
        rq = float(b.data.qpos[b.model.jnt_qposadr[b._joint("right_finger_joint")]])
        # XML defines inner opening = 2*(0.14 - 0.012) - lq - rq = 0.256 - lq - rq
        width_mm = max(0.0, (0.256 - lq - rq) * 1000.0)
        if left_touch and right_touch and contact_force > 0.3:
            gripper_state = "GRASPED"
        elif lq + rq > 0.02:
            gripper_state = "CLOSING"
        else:
            gripper_state = "OPEN"

        joints = {
            "robot_x": round(float(b.data.qpos[b.model.jnt_qposadr[b._joint("robot_x_joint")]]), 4),
            "robot_y": round(float(b.data.qpos[b.model.jnt_qposadr[b._joint("robot_y_joint")]]), 4),
            "robot_z": round(float(b.data.qpos[b.model.jnt_qposadr[b._joint("robot_z_joint")]]), 4),
            "wrist_yaw": round(float(b.data.qpos[b.model.jnt_qposadr[b._joint("wrist_yaw_joint")]]), 4),
            "u_layer": round(float(b.data.qpos[b.model.jnt_qposadr[b._joint("u_layer_joint")]]), 4),
        }
        cube_id = b._id(mj.mjtObj.mjOBJ_BODY, "cube")
        cube_mm = [round(float(v) * 1000.0, 1) for v in b.data.xpos[cube_id]]
        u_deg = round(-math.degrees(joints["u_layer"]), 2)
        return {
            "contactForceN": round(float(contact_force), 2),
            "gripperWidthMm": round(float(width_mm), 1),
            "gripperState": gripper_state,
            "jointPositionsRad": joints,
            "cubePositionMm": cube_mm,
            "layerTurnAngleDeg": self.last_turn_angle_deg if self.last_turn_angle_deg is not None else u_deg,
            "targetLayer": "U" if self.selected_mission_type == MissionType.VERIFY_PHYSICAL_U_TURN else None,
            "collisionDetected": False,
            "slipDetected": False,
            "renderFps": 30.0,
            "failureReason": self.mission.failure_reason if self.mission else None,
        }

    def _build_snapshot(self) -> dict[str, Any]:
        b = self._backend
        sim_time = round(float(b.data.time), 3) if b is not None else 0.0
        wall_time = now_wall_time()
        mission_dump = self.mission.model_dump(mode="json") if self.mission else None
        plan_dump = self.plan.model_dump(mode="json") if self.plan else None

        # Derive top-level task_status compatible with v4 UI
        m_status = self.mission.status if self.mission else MissionStatus.CREATED
        if m_status == MissionStatus.CREATED:
            task_status = "IDLE"
        elif m_status in {
            MissionStatus.OBSERVING,
            MissionStatus.PLANNING,
            MissionStatus.EXECUTING,
            MissionStatus.VERIFYING,
        }:
            task_status = "RUNNING"
        elif m_status == MissionStatus.COMPLETED:
            task_status = "COMPLETED"
        elif m_status == MissionStatus.CANCELLED:
            task_status = "STOPPED"
        else:
            # FAILED or BLOCKED_CAPABILITY
            task_status = "FAILED"

        current_step = None
        if self.plan and self.plan.current_step_id:
            current_step = next(
                (s for s in self.plan.steps if s.step_id == self.plan.current_step_id),
                None,
            )
        stages = [_plan_step_to_legacy_stage(s) for s in (self.plan.steps if self.plan else [])]

        telemetry = self._read_telemetry()
        timeline = [
            {
                "event_id": ev.event_id,
                "short_label": f"{int(ev.sim_time or 0):02d}:{(ev.sim_time or 0)%60:05.2f} {ev.event_type.value}",
                "sim_time": ev.sim_time or 0.0,
                "wall_time": ev.wall_time,
                "skill_name": ev.skill_id or ev.event_type.value,
                "stage_id": current_step.step_id if current_step else "",
                "status": "FAILED"
                if ev.event_type in {DecisionEventType.SKILL_FAILED, DecisionEventType.CAPABILITY_BLOCKED, DecisionEventType.MISSION_FAILED}
                else "VERIFIED",
                "failure_reason": ev.failure_reason,
                "summary": ev.summary,
                "turn_angle_deg": telemetry["layerTurnAngleDeg"] or 0.0,
                "contact_force_n": telemetry["contactForceN"] or 0.0,
                "gripper_width_mm": telemetry["gripperWidthMm"] or 0.0,
                "gripper_state": telemetry["gripperState"],
                "completed_stage_index": sum(1 for s in (self.plan.steps if self.plan else []) if s.status == PlanStepStatus.VERIFIED),
            }
            for ev in self.event_log.events
            if ev.event_type
            in {
                DecisionEventType.MISSION_CREATED,
                DecisionEventType.OBSERVATION_RECEIVED,
                DecisionEventType.SKILL_COMPLETED,
                DecisionEventType.SKILL_FAILED,
                DecisionEventType.CAPABILITY_BLOCKED,
                DecisionEventType.VERIFICATION_COMPLETED,
                DecisionEventType.MISSION_COMPLETED,
                DecisionEventType.MISSION_FAILED,
            }
        ]
        structured_observations = [
            {
                "observation_id": event.evidence.get("observation_id"),
                "camera_ids": event.evidence.get("camera_ids", []),
                "frame_refs": event.evidence.get("frame_refs", []),
                "visual_summary": event.evidence.get("visual_summary", ""),
                "coverage": event.evidence.get("coverage_after", 0),
                "sim_time": event.end_sim_time if event.end_sim_time is not None else event.sim_time,
            }
            for event in self.trace_log.events
            if event.event_type == TraceEventType.PERCEPTION
        ]

        return {
            "session_id": self.session_id,
            "seed": self.seed,
            "sim_time": sim_time,
            "wall_time": wall_time,
            "frame_source": "REAL_MUJOCO_RENDERER",
            "active_camera": self.active_camera,
            "camera_azimuth_deg": self.camera_azimuth_deg,
            "camera_elevation_deg": self.camera_elevation_deg,
            "camera_distance_m": self.camera_distance_m,
            "main_frame_url": self._main_frame_url,
            "wrist_rgb_url": self._wrist_rgb_url,
            "wrist_depth_url": self._wrist_depth_url,
            "depth_range_m": self._depth_range_m,
            "detections": [],
            "task_status": task_status,
            "current_stage_id": current_step.step_id if current_step else "",
            "current_skill": current_step.skill_id if current_step else "IDLE",
            "stages": stages,
            "observed_facelets": _format_facelets_for_ui(
                self.observed_facelets_str,
                conflicts=self.conflict_set,
            ),
            "predicted_facelets": [
                _face_char_to_ui(ch)
                for ch in (
                    self.predicted_facelets_str
                    if self.predicted_facelets_str and len(self.predicted_facelets_str) == 54
                    else "?" * 54
                )
            ],
            "cube_validation_status": self.cube_validation_status,
            "telemetry": telemetry,
            "timeline": timeline,
            # M3-D First-class objects
            "selected_mission_type": self.selected_mission_type.value,
            "mission": mission_dump,
            "plan": plan_dump,
            "skill_executions": [ex.model_dump(mode="json") for ex in self.skill_executions],
            "decision_events": [ev.model_dump(mode="json") for ev in self.event_log.events],
            "trace_events": [ev.model_dump(mode="json") for ev in self.trace_log.events],
            "observations": structured_observations,
            "capabilities": self.get_capabilities(),
            "agent_state": self.agent_state.model_dump(mode="json"),
            "physical_verification": self.physical_verification,
            "last_observation_ref": self.last_observation_ref.model_dump(mode="json")
            if self.last_observation_ref
            else None,
            "running": self._running,
        }

    # ------------------------------------------------------------------
    # Camera / UI controls
    # ------------------------------------------------------------------

    def select_mission(self, mission_type: MissionType | str) -> dict[str, Any]:
        mtype = MissionType(mission_type)
        def _do() -> dict[str, Any]:
            if self._running:
                return self.get_snapshot()
            self.selected_mission_type = mtype
            preview_mission = self._new_mission_object(mtype)
            self.mission = preview_mission
            self.plan = self.planner.create_plan(
                preview_mission,
                self.registry,
                plan_id=f"plan-{preview_mission.mission_id}",
            )
            self.mission.current_plan_id = self.plan.plan_id
            return self._emit_snapshot(refresh_frames=False)
        return self._run_on_gl_thread(_do)

    def reset_scene(self, seed: int | None = None, mission_type: MissionType | str | None = None) -> dict[str, Any]:
        if mission_type is not None:
            self.selected_mission_type = MissionType(mission_type)
        target_seed = self.seed if seed is None else int(seed)
        self._stop_event.set()
        def _do() -> dict[str, Any]:
            self._stop_event.clear()
            self._reset_backend_scene(target_seed)
            return self._emit_snapshot(refresh_frames=True)
        return self._run_on_gl_thread(_do)

    def set_camera_preset(self, preset: str) -> dict[str, Any]:
        if preset not in CAMERA_PRESET_SPECS:
            return self.get_snapshot()
        spec = CAMERA_PRESET_SPECS[preset]
        self.active_camera = preset
        self.camera_azimuth_deg = float(spec["az"])
        self.camera_elevation_deg = float(spec["el"])
        self.camera_distance_m = float(spec["dist"])
        if self._running:
            return self._snapshot_with_current_camera()
        return self._run_on_gl_thread(lambda: self._emit_snapshot(refresh_frames=True))

    def orbit_camera(self, delta_azimuth: float, delta_elevation: float) -> dict[str, Any]:
        self.camera_azimuth_deg = (self.camera_azimuth_deg + float(delta_azimuth)) % 360.0
        self.camera_elevation_deg = max(-89.0, min(-5.0, self.camera_elevation_deg + float(delta_elevation)))
        if self._running:
            return self._snapshot_with_current_camera()
        return self._run_on_gl_thread(lambda: self._emit_snapshot(refresh_frames=True))

    def zoom_camera(self, delta_distance: float) -> dict[str, Any]:
        self.camera_distance_m = max(0.24, min(2.4, self.camera_distance_m + float(delta_distance)))
        if self._running:
            return self._snapshot_with_current_camera()
        return self._run_on_gl_thread(lambda: self._emit_snapshot(refresh_frames=True))

    def set_render_flags(self, flags: dict[str, bool]) -> dict[str, Any]:
        for k in ("contactForces", "collisionGeoms", "tcpFrame", "hudVisible"):
            if k in flags:
                self.debug_overlays[k] = bool(flags[k])
        if self._running:
            return self.get_snapshot()
        return self._run_on_gl_thread(lambda: self._emit_snapshot(refresh_frames=True))

    def stop_mission(self) -> dict[str, Any]:
        self._stop_event.set()
        return self.get_snapshot()

    # ------------------------------------------------------------------
    # Mission Orchestration & Real Skill Execution
    # ------------------------------------------------------------------

    def _new_mission_object(self, mtype: MissionType) -> MissionState:
        spec = MISSION_SPECS[mtype]
        return MissionState(
            mission_id=f"msn-{uuid.uuid4().hex[:8]}",
            session_id=self.session_id,
            mission_type=mtype,
            user_goal=spec["user_goal"],
            success_criteria=spec["success_criteria"],
            status=MissionStatus.CREATED,
            created_at=now_wall_time(),
        )

    def start_mission_async(
        self,
        mission_type: MissionType | str,
        *,
        seed: int | None = None,
    ) -> dict[str, Any]:
        if self._executor is None:
            return self.run_mission(mission_type, seed=seed)
        if self._running:
            return {"accepted": False, "reason": "mission_already_running", "snapshot": self.get_snapshot()}
        mtype = MissionType(mission_type)
        self._executor.submit(self._run_mission_sync, mtype, seed)
        return {"accepted": True, "mission_type": mtype.value, "seed": self.seed if seed is None else int(seed)}

    def run_mission(
        self,
        mission_type: MissionType | str,
        *,
        seed: int | None = None,
    ) -> dict[str, Any]:
        mtype = MissionType(mission_type)
        return self._run_on_gl_thread(lambda: self._run_mission_sync(mtype, seed))

    def _sim_time(self) -> float:
        return round(float(self._backend.data.time), 4) if self._backend is not None else 0.0

    def _record_decision(
        self,
        *,
        event_type: DecisionEventType,
        source: str,
        summary: str,
        rationale: str,
        status: str,
        selected_action: str | None = None,
        skill_id: str | None = None,
        input_reference: str | None = None,
        output_reference: str | None = None,
        failure_reason: str | None = None,
    ) -> DecisionEvent:
        assert self.mission is not None
        return self.event_log.append(
            session_id=self.session_id,
            mission_id=self.mission.mission_id,
            plan_id=self.plan.plan_id if self.plan else None,
            event_type=event_type,
            source=source,
            sim_time=self._sim_time(),
            summary=summary,
            decision_rationale_summary=rationale,
            status=status,
            selected_action=selected_action,
            skill_id=skill_id,
            input_reference=input_reference,
            output_reference=output_reference,
            failure_reason=failure_reason,
        )

    def _record_scan_trace(self, payload: dict[str, Any]) -> None:
        """Persist one inspector callback immediately; never infer it in the UI."""
        assert self.mission is not None
        event_type = TraceEventType(str(payload["event_type"]))
        evidence = dict(payload.get("evidence", {}))
        if event_type == TraceEventType.PERCEPTION:
            frame_images: list[dict[str, str]] = []
            debug_frames = list(getattr(self._backend, "debug_observation_frames", []))
            for camera_id, frame_ref in zip(
                evidence.get("camera_ids", []), evidence.get("frame_refs", [])
            ):
                match = next(
                    (frame for label, frame in reversed(debug_frames) if label.endswith(f":{camera_id}")),
                    None,
                )
                if match is not None:
                    image = Image.fromarray(np.asarray(match, dtype=np.uint8))
                    image.thumbnail((240, 160))
                    frame_images.append({
                        "camera_id": str(camera_id),
                        "frame_ref": str(frame_ref),
                        "image_url": _encode_jpeg_data_url(np.asarray(image), quality=72),
                    })
            evidence["frame_images"] = frame_images
        self.trace_log.append(
            mission_id=self.mission.mission_id,
            session_id=self.session_id,
            parent_event_id=self._active_composite_trace_event_id,
            skill_id="active_six_face_scan",
            event_type=event_type,
            name=str(payload["name"]),
            source=str(payload["source"]),
            status=str(payload["status"]),
            sim_time=float(payload.get("start_sim_time", self._sim_time())),
            end_sim_time=float(payload.get("end_sim_time", self._sim_time())),
            evidence=evidence,
            failure_reason=payload.get("failure_reason"),
        )
        # This lightweight snapshot streams the event while the composite is
        # still running. It deliberately reuses cached images and does not
        # introduce another EGL render into the physics loop.
        self._emit_snapshot(refresh_frames=False)

    def _run_mission_sync(self, mission_type: MissionType, seed: int | None) -> dict[str, Any]:
        target_seed = self.seed if seed is None else int(seed)
        self._stop_event.clear()
        self._running = True
        try:
            self.selected_mission_type = mission_type
            self._reset_backend_scene(target_seed)
            self._lock_backend_anti_cheat()

            mission = self._new_mission_object(mission_type)
            self.mission = mission
            self.plan = None
            self.skill_executions.clear()
            self.event_log.clear()
            self.trace_log.clear()
            mission_trace = self.trace_log.append(
                mission_id=mission.mission_id,
                session_id=self.session_id,
                event_type=TraceEventType.MISSION,
                name=mission_type.value,
                source="MissionController",
                status="RUNNING",
                sim_time=self._sim_time(),
                evidence={"user_goal": mission.user_goal, "success_criteria": mission.success_criteria},
            )
            self._mission_trace_event_id = mission_trace.event_id

            self._record_decision(
                event_type=DecisionEventType.MISSION_CREATED,
                source="MissionController",
                summary=f"创建任务 [{MISSION_SPECS[mission_type]['title']}] ({mission_type.value})",
                rationale=f"接收用户目标：{mission.user_goal}",
                status=MissionStatus.CREATED.value,
                selected_action=mission_type.value,
            )

            mission.status = MissionStatus.PLANNING
            plan = self.planner.create_plan(
                mission,
                self.registry,
                plan_id=f"plan-{mission.mission_id}",
            )
            self.plan = plan
            mission.current_plan_id = plan.plan_id

            self._record_decision(
                event_type=DecisionEventType.PLAN_CREATED,
                source=self.planner.name,
                summary=f"生成 {len(plan.steps)} 步任务计划 ({', '.join(s.skill_id for s in plan.steps)})",
                rationale=plan.rationale_summary,
                status="PLAN_READY",
                selected_action=plan.steps[0].skill_id if plan.steps else None,
                output_reference=plan.plan_id,
            )
            self._emit_snapshot(refresh_frames=True)

            # Optional throttled streaming hook during long physics skills
            b = self._backend
            orig_step_physics = b.step_physics
            self._last_stream_wall = time.monotonic()
            self._last_stream_sim = self._sim_time()

            def _streaming_step_physics() -> None:
                orig_step_physics()
                now_wall = time.monotonic()
                now_sim = self._sim_time()
                if self._stream_update_due(now_wall=now_wall, now_sim=now_sim):
                    self._emit_snapshot(refresh_frames=True)
                    # Mark completion, rather than start, so render time cannot
                    # consume the interval and trigger another refresh at once.
                    self._last_stream_wall = time.monotonic()
                    self._last_stream_sim = self._sim_time()

            if (
                self.stream_interval_sec > 0
                and self.stream_sim_interval_sec > 0
                and self._subscribers
            ):
                b.step_physics = _streaming_step_physics

            try:
                while True:
                    if self._stop_event.is_set():
                        mission.status = MissionStatus.CANCELLED
                        mission.completed_at = now_wall_time()
                        mission.failure_reason = "USER_STOP_REQUESTED"
                        mission.result_summary = "用户主动安全停止当前任务。"
                        self._record_decision(
                            event_type=DecisionEventType.MISSION_FAILED,
                            source="MissionController",
                            summary="任务被安全停止",
                            rationale="收到用户 STOP_MISSION 指令，安全中止后续动作。",
                            status=MissionStatus.CANCELLED.value,
                            failure_reason="USER_STOP_REQUESTED",
                        )
                        self._emit_snapshot(refresh_frames=True)
                        break

                    decision = self.planner.select_next_action(
                        mission,
                        plan,
                        self.registry,
                        self.scene_state,
                        self.last_observation_ref,
                    )
                    self.agent_state.selected_action = decision.skill_id or decision.decision_kind
                    self.agent_state.selection_rationale = decision.rationale_summary

                    if decision.decision_kind == "COMPLETE_MISSION":
                        mission.status = MissionStatus.COMPLETED
                        mission.completed_at = now_wall_time()
                        if not mission.result_summary:
                            mission.result_summary = "任务计划全部步骤执行并验证通过。"
                        self._record_decision(
                            event_type=DecisionEventType.MISSION_COMPLETED,
                            source=self.planner.name,
                            summary=mission.result_summary,
                            rationale=decision.rationale_summary,
                            status=MissionStatus.COMPLETED.value,
                            input_reference=decision.input_reference,
                        )
                        self._emit_snapshot(refresh_frames=True)
                        break

                    if decision.decision_kind == "BLOCK_CAPABILITY":
                        self._handle_capability_block(
                            step_id=decision.step_id,
                            skill_id=decision.skill_id,
                            blocked_move=decision.blocked_move,
                            blocked_moves=list(decision.blocked_moves),
                            blocked_reason=decision.blocked_reason or decision.rationale_summary,
                            rationale=decision.rationale_summary,
                            input_reference=decision.input_reference,
                        )
                        self._emit_snapshot(refresh_frames=True)
                        break

                    assert decision.step_id is not None and decision.skill_id is not None
                    step = next(s for s in plan.steps if s.step_id == decision.step_id)
                    plan.current_step_id = step.step_id
                    plan.updated_at = now_wall_time()

                    self._record_decision(
                        event_type=DecisionEventType.ACTION_SELECTED,
                        source=self.planner.name,
                        summary=f"选择动作 [{step.title}] ({step.skill_id})",
                        rationale=decision.rationale_summary,
                        status="SELECTED",
                        selected_action=step.skill_id,
                        skill_id=step.skill_id,
                        input_reference=decision.input_reference,
                    )

                    outcome = self._execute_plan_step(step, decision.input_reference)
                    if outcome == "BLOCKED_CAPABILITY":
                        self._emit_snapshot(refresh_frames=True)
                        break
                    if outcome == "FAILED":
                        mission.status = MissionStatus.FAILED
                        mission.completed_at = now_wall_time()
                        mission.failure_reason = step.failure_reason
                        mission.result_summary = f"步骤 [{step.title}] 执行失败：{step.failure_reason}"
                        self._record_decision(
                            event_type=DecisionEventType.MISSION_FAILED,
                            source="MissionController",
                            summary=mission.result_summary,
                            rationale=f"Skill {step.skill_id} 未通过前置或验证条件：{step.failure_reason}",
                            status=MissionStatus.FAILED.value,
                            skill_id=step.skill_id,
                            failure_reason=step.failure_reason,
                        )
                        self._emit_snapshot(refresh_frames=True)
                        break

                    self._emit_snapshot(refresh_frames=True)
            finally:
                b.step_physics = orig_step_physics
        finally:
            self._running = False

        if self._mission_trace_event_id is not None and self.mission is not None:
            final_status = self.mission.status.value
            self.trace_log.finish(
                self._mission_trace_event_id,
                status=final_status,
                end_sim_time=self._sim_time(),
                evidence={"result_summary": self.mission.result_summary},
                failure_reason=self.mission.failure_reason,
            )
        return self._emit_snapshot(refresh_frames=False)

    def _handle_capability_block(
        self,
        *,
        step_id: str | None,
        skill_id: str | None,
        blocked_move: str | None,
        blocked_moves: list[str],
        blocked_reason: str,
        rationale: str,
        input_reference: str | None,
    ) -> None:
        assert self.mission is not None and self.plan is not None
        if step_id:
            for s in self.plan.steps:
                if s.step_id == step_id:
                    s.status = PlanStepStatus.BLOCKED
                    s.ended_sim_time = self._sim_time()
                    s.ended_wall_time = now_wall_time()
                    s.failure_reason = blocked_reason
                    s.result_summary = f"能力阻塞：{blocked_move or skill_id}"
        self.mission.status = MissionStatus.BLOCKED_CAPABILITY
        self.mission.completed_at = now_wall_time()
        self.mission.blocked_move = blocked_move
        self.mission.blocked_moves = blocked_moves
        self.mission.blocked_reason = blocked_reason
        self.mission.result_summary = (
            f"规划已完成（符号序列共 {len(self.mission.symbolic_solution)} 步），"
            f"但物理执行在动作 {blocked_move or '未知'} 处受阻（CAPABILITY_BLOCKED）。"
        )
        self.agent_state.blocked_or_replan_reason = blocked_reason
        self._record_decision(
            event_type=DecisionEventType.CAPABILITY_BLOCKED,
            source=self.planner.name,
            summary=f"物理能力阻塞：动作 {blocked_move or skill_id} 无法在当前模型中执行",
            rationale=rationale,
            status=MissionStatus.BLOCKED_CAPABILITY.value,
            selected_action=blocked_move or skill_id,
            skill_id=skill_id,
            input_reference=input_reference,
            failure_reason=blocked_reason,
        )

    def _execute_plan_step(self, step: PlanStep, input_ref: str | None) -> str:
        assert self.mission is not None and self.plan is not None
        b = self._backend
        step.status = PlanStepStatus.RUNNING
        step.started_sim_time = self._sim_time()
        step.started_wall_time = now_wall_time()
        step.input_reference = input_ref

        if step.skill_id in {"observe_workspace", "active_six_face_scan"}:
            self.mission.status = MissionStatus.OBSERVING
        elif step.skill_id in {"validate_cube_state", "verify_post_turn_state"}:
            self.mission.status = MissionStatus.VERIFYING
        elif step.skill_id in {"compute_symbolic_plan", "check_physical_capability"}:
            self.mission.status = MissionStatus.PLANNING
        else:
            self.mission.status = MissionStatus.EXECUTING

        exec_state = SkillExecutionState(
            execution_id=f"exec-{len(self.skill_executions) + 1:03d}",
            mission_id=self.mission.mission_id,
            plan_id=self.plan.plan_id,
            step_id=step.step_id,
            skill_id=step.skill_id,
            skill_title=step.title,
            status=PlanStepStatus.RUNNING,
            started_sim_time=step.started_sim_time,
            started_wall_time=step.started_wall_time,
            parameters=dict(step.parameters),
        )
        self.skill_executions.append(exec_state)
        self.agent_state.last_skill_call = step.skill_id

        self._record_decision(
            event_type=DecisionEventType.SKILL_STARTED,
            source="SkillExecutor",
            summary=f"开始执行 Skill [{step.skill_id}]",
            rationale=f"按照当前计划执行步骤 {step.index}：{step.title}",
            status="RUNNING",
            selected_action=step.skill_id,
            skill_id=step.skill_id,
            input_reference=input_ref,
        )
        self._emit_snapshot(refresh_frames=True)

        success = False
        failure_code: str | None = None
        failure_reason: str | None = None
        output_data: dict[str, Any] = {}
        result_summary = ""
        output_ref: str | None = None

        if step.skill_id == "observe_workspace":
            frame = b.capture_rgbd("overhead")
            det = DeterministicCubeLocalizer().locate(frame)
            frame_id = f"frm-{uuid.uuid4().hex[:8]}"
            obs_id = f"obs-{uuid.uuid4().hex[:8]}"
            if det is None:
                failure_code = "CUBE_NOT_LOCALIZED"
                failure_reason = "顶部 RGB-D 相机未能在桌面区域定位到魔方。"
            else:
                success = True
                self.scene_state["cube_localized"] = True
                obs_ref = ObservationReference(
                    observation_id=obs_id,
                    frame_id=frame_id,
                    sim_time=self._sim_time(),
                    camera_name="overhead",
                    observed_count=0,
                    unknown_count=54,
                    conflict_count=0,
                    validation_status="UNVERIFIED",
                    cube_center_world_m=tuple(round(float(v), 4) for v in det.center_world_m),
                    summary=f"工作站顶部 RGB-D 定位魔方中心 {tuple(round(float(v), 3) for v in det.center_world_m)} m",
                )
                self.last_observation_ref = obs_ref
                output_ref = obs_id
                output_data = {"center_world_m": list(obs_ref.cube_center_world_m), "yaw_radians": det.yaw_radians, "frame_id": frame_id}
                result_summary = obs_ref.summary
                self._record_decision(
                    event_type=DecisionEventType.OBSERVATION_RECEIVED,
                    source="DeterministicCubeLocalizer",
                    summary=obs_ref.summary,
                    rationale="通过校准相机像素与深度中值恢复魔方 3D 中心坐标，未读取任何真值 pose。",
                    status="OBSERVED",
                    skill_id=step.skill_id,
                    output_reference=obs_id,
                )

        elif step.skill_id == "active_six_face_scan":
            self.scene_state["scan_attempted"] = True
            composite = self.trace_log.append(
                mission_id=self.mission.mission_id,
                session_id=self.session_id,
                parent_event_id=self._mission_trace_event_id,
                skill_id=step.skill_id,
                event_type=TraceEventType.COMPOSITE_SKILL,
                name=step.skill_id,
                source="ContinuousActiveInspector",
                status="RUNNING",
                sim_time=self._sim_time(),
                evidence={"mode": "sequential", "live": True},
            )
            self._active_composite_trace_event_id = composite.event_id
            try:
                scan = ContinuousActiveInspector(
                    b, "sequential", event_sink=self._record_scan_trace,
                ).run(self.seed, reset_scene=False)
            except Exception as exc:
                self.trace_log.finish(
                    composite.event_id,
                    status="FAILED",
                    end_sim_time=self._sim_time(),
                    failure_reason=str(exc),
                )
                raise
            finally:
                self._active_composite_trace_event_id = None
            self.trace_log.finish(
                composite.event_id,
                status="COMPLETED" if scan.success else "FAILED",
                end_sim_time=self._sim_time(),
                evidence={"action_count": scan.action_count, "legal": scan.legal},
                failure_reason=scan.first_failure_stage,
            )
            facelets = scan.reconstructed_facelets
            if facelets is None:
                # Materialize observed vs unknown honestly from evidence
                chars = []
                for item in scan.evidence:
                    chars.append(item.get("color") or "?")
                partial = "".join(chars) if len(chars) == 54 else "?" * 54
                self.observed_facelets_str = partial
                unknown_cnt = partial.count("?")
            else:
                self.observed_facelets_str = facelets
                unknown_cnt = 0
            observed_cnt = 54 - unknown_cnt
            obs_id = f"obs-{uuid.uuid4().hex[:8]}"
            frame_id = f"frm-{uuid.uuid4().hex[:8]}"
            obs_ref = ObservationReference(
                observation_id=obs_id,
                frame_id=frame_id,
                sim_time=self._sim_time(),
                camera_name="scan_and_inspection_rig",
                observed_count=observed_cnt,
                unknown_count=unknown_cnt,
                conflict_count=0,
                validation_status="UNVERIFIED" if unknown_cnt else "CANDIDATE_COMPLETE",
                reconstructed_facelets=self.observed_facelets_str,
                cube_center_world_m=self.last_observation_ref.cube_center_world_m if self.last_observation_ref else None,
                summary=f"六面主动扫描结束：已观测 {observed_cnt}/54 贴片，未知 {unknown_cnt} 格",
            )
            self.last_observation_ref = obs_ref
            output_ref = obs_id
            output_data = {
                "observed_count": observed_cnt,
                "unknown_count": unknown_cnt,
                "action_count": scan.action_count,
                "legal": scan.legal,
                "reconstructed_facelets": facelets,
                "first_failure_stage": scan.first_failure_stage,
                "trace_events": [asdict(item) for item in scan.events],
            }
            if scan.success and facelets is not None:
                success = True
                self.scene_state["cube_localized_and_scanned"] = True
                result_summary = f"完成六面主动扫描：{observed_cnt}/54 贴片观测完整（{scan.action_count} 个物理子动作）。"
                self._record_decision(
                    event_type=DecisionEventType.OBSERVATION_RECEIVED,
                    source="ContinuousActiveInspector",
                    summary=obs_ref.summary,
                    rationale="完成释放态 + 持握旋转多视角扫描与融合。",
                    status="OBSERVED",
                    skill_id=step.skill_id,
                    output_reference=obs_id,
                )
            else:
                failure_code = scan.first_failure_stage or "SCAN_INCOMPLETE"
                failure_reason = f"六面扫描未能完成 54 格合法融合（first_failure={failure_code}, unknown={unknown_cnt}）。"

        elif step.skill_id == "validate_cube_state":
            obs = self.observed_facelets_str
            if not obs or "?" in obs or len(obs) != 54:
                self.cube_validation_status = "INCOMPLETE"
                failure_code = "INCOMPLETE_OBSERVATION"
                failure_reason = f"实测状态不完整（unknown={obs.count('?') if obs else 54}），拒绝进行合法性确认。"
            else:
                report = StateValidator().validate(obs, check_solvable=True)
                if report.valid:
                    success = True
                    self.cube_validation_status = "VALID_SOLVABLE"
                    self.scene_state["cube_state_validated"] = True
                    if self.last_observation_ref:
                        self.last_observation_ref = self.last_observation_ref.model_copy(
                            update={"validation_status": "VALID_SOLVABLE"}
                        )
                    result_summary = "54 格贴片通过数量、中心块唯一性与 Kociemba 群论可解性校验。"
                    output_data = {"valid": True, "facelets": obs}
                    if self.mission.mission_type == MissionType.INSPECT_CUBE:
                        self.mission.result_summary = (
                            f"六面扫描完成：54/54 贴片已观测、0 冲突、合法可解；"
                            f"未执行任何物理转面。"
                        )
                    self._record_decision(
                        event_type=DecisionEventType.VERIFICATION_COMPLETED,
                        source="StateValidator",
                        summary="54 格魔方状态校验通过 (VALID_SOLVABLE)",
                        rationale="独立校验器确认观测结果满足 3x3 魔方群论可解条件。",
                        status="VERIFIED",
                        skill_id=step.skill_id,
                        input_reference=input_ref,
                    )
                else:
                    self.cube_validation_status = "INVALID_STATE"
                    failure_code = "INVALID_CUBE_STATE"
                    failure_reason = f"状态合法性校验失败：{report.error}"

        elif step.skill_id == "compute_symbolic_plan":
            assert self.observed_facelets_str is not None
            target_mode = step.parameters.get("target_mode", "solve")
            engine = CubeEngine()
            if target_mode == "single_u_expectation":
                expected = engine.apply_move(self.observed_facelets_str, "U")
                self.predicted_facelets_str = expected
                self.mission.symbolic_solution = ["U"]
                self.scene_state["symbolic_solution"] = ["U"]
                self.scene_state["symbolic_plan_available"] = True
                success = True
                result_summary = "已基于实测 54 格状态计算单步 U 顺时针转面后的符号期望状态。"
                output_data = {"target_move": "U", "expected_facelets": expected}
            else:
                solver = CubeSolver()
                moves = solver.solve(self.observed_facelets_str)
                self.mission.symbolic_solution = list(moves)
                self.scene_state["symbolic_solution"] = list(moves)
                self.scene_state["symbolic_plan_available"] = True
                self.predicted_facelets_str = SOLVED_FACELETS
                success = True
                result_summary = (
                    f"Kociemba 求解完成，共 {len(moves)} 步：{moves[:8]}{'...' if len(moves) > 8 else ''}"
                    if moves
                    else "当前魔方已处于还原态（0 步）。"
                )
                output_data = {"moves": moves, "move_count": len(moves)}

        elif step.skill_id == "check_physical_capability":
            moves = list(self.scene_state.get("symbolic_solution") or [])
            audit = self.registry.audit_move_sequence(moves, self.scene_state)
            output_data = audit
            if not audit["all_supported"]:
                step.ended_sim_time = self._sim_time()
                step.ended_wall_time = now_wall_time()
                step.elapsed_sec = round(step.ended_sim_time - step.started_sim_time, 3)
                step.output_reference = f"cap-audit-{step.step_id}"
                exec_state.status = PlanStepStatus.BLOCKED
                exec_state.ended_sim_time = step.ended_sim_time
                exec_state.ended_wall_time = step.ended_wall_time
                exec_state.elapsed_sec = step.elapsed_sec
                exec_state.output_data = output_data
                exec_state.verification_passed = False
                exec_state.failure_code = "CAPABILITY_UNSUPPORTED"
                exec_state.failure_reason = audit["first_blocked_reason"]
                self.agent_state.last_execution_feedback = audit["first_blocked_reason"]
                self._handle_capability_block(
                    step_id=step.step_id,
                    skill_id=step.skill_id,
                    blocked_move=audit["first_blocked_move"],
                    blocked_moves=list(audit["blocked_moves"]),
                    blocked_reason=audit["first_blocked_reason"],
                    rationale=(
                        f"求解器生成序列 {moves}，其中首个不可执行动作为 {audit['first_blocked_move']}。"
                        f"{audit['first_blocked_reason']}"
                    ),
                    input_reference=input_ref,
                )
                return "BLOCKED_CAPABILITY"

            success = True
            if len(moves) == 0:
                result_summary = "魔方已还原，无需执行物理转面。"
                self.mission.result_summary = "扫描并校验确认魔方已处于还原状态（0 步）。"
            elif moves == ["U"]:
                result_summary = "能力核查通过：求解序列仅含 ['U']，满足当前单层物理能力，动态追加物理转面与复核步骤。"
                next_idx = len(self.plan.steps) + 1
                s_turn = PlanStep(
                    step_id=f"{self.plan.plan_id}-s{next_idx}",
                    index=next_idx,
                    title="接触驱动 U 层物理转动",
                    skill_id="execute_physical_u_turn",
                    description=self.registry.get("execute_physical_u_turn").description,  # type: ignore[union-attr]
                    parameters={"move": "U"},
                )
                s_verify = PlanStep(
                    step_id=f"{self.plan.plan_id}-s{next_idx + 1}",
                    index=next_idx + 1,
                    title="转后 21 格视觉复核",
                    skill_id="verify_post_turn_state",
                    description=self.registry.get("verify_post_turn_state").description,  # type: ignore[union-attr]
                    parameters={},
                )
                self.plan.steps.extend([s_turn, s_verify])
                self.plan.replan_count += 1
                self.plan.replan_reason = "单步 U 求解通过物理能力核查，追加物理执行与视觉复核步骤。"
                self._record_decision(
                    event_type=DecisionEventType.PLAN_UPDATED,
                    source=self.planner.name,
                    summary="计划已扩展：追加 execute_physical_u_turn 与 verify_post_turn_state",
                    rationale=self.plan.replan_reason,
                    status="PLAN_UPDATED",
                    selected_action="execute_physical_u_turn",
                )

        elif step.skill_id == "execute_physical_u_turn":
            controller = ContactUTurn(b)
            turn_res = controller.dock_and_turn()
            turning_rows = [r for r in controller.trace if r.get("phase") == "CONTACT_TURN"]
            min_base_n = min(
                (
                    min(
                        (
                            c["normal_force"]
                            for c in r.get("contacts", [])
                            if set(c.get("geoms", [])) in ({"base_pos_pad", "cube_core"}, {"base_neg_pad", "cube_core"})
                        ),
                        default=0.0,
                    )
                    for r in turning_rows
                ),
                default=0.0,
            )
            min_turn_n = min(
                (
                    min(
                        (
                            c["normal_force"]
                            for c in r.get("contacts", [])
                            if set(c.get("geoms", [])) in ({"turn_pos_pad", "u_layer_core"}, {"turn_neg_pad", "u_layer_core"})
                        ),
                        default=0.0,
                    )
                    for r in turning_rows
                ),
                default=0.0,
            )
            max_brake = max((abs(float(r.get("layer_brake_torque", 0.0))) for r in turning_rows), default=0.0)
            self.last_base_contact_n = round(float(min_base_n), 3)
            self.last_turn_contact_n = round(float(min_turn_n), 3)
            self.last_contact_force_n = round(float(max(min_base_n, min_turn_n)), 3)

            if turn_res.get("success"):
                actual_delta = float(turn_res["actual_delta"])
                layer_error = float(turn_res["layer_error"])
                base_disp = float(turn_res["base_displacement"])
                self.last_turn_angle_deg = round(-math.degrees(actual_delta), 3)
                self.scene_state["u_turns_completed"] = int(self.scene_state.get("u_turns_completed", 0)) + 1
                self.scene_state["physical_u_turn_executed"] = True
                self.scene_state["turn_station_cleared"] = True
                success = True
                output_data = {
                    "target_delta_rad": float(turn_res["target_delta"]),
                    "actual_delta_rad": actual_delta,
                    "actual_angle_deg": self.last_turn_angle_deg,
                    "layer_error_rad": layer_error,
                    "base_displacement_m": base_disp,
                    "min_base_contact_n": self.last_base_contact_n,
                    "min_turn_contact_n": self.last_turn_contact_n,
                    "max_turn_brake_torque": max_brake,
                    "trace_rows": len(controller.trace),
                }
                self.physical_verification = dict(output_data)
                result_summary = (
                    f"接触式 U 层转动完成：实测转角 {self.last_turn_angle_deg:.2f}° "
                    f"(误差 {layer_error:.2e} rad, 底座力≥{self.last_base_contact_n:.2f}N, 拧头力≥{self.last_turn_contact_n:.2f}N)"
                )
            else:
                failure_code = str(turn_res.get("failure") or "PHYSICAL_TURN_FAILED")
                failure_reason = f"物理 U 层转动失败：{failure_code}"
                output_data = dict(turn_res)

        elif step.skill_id == "verify_post_turn_state":
            expected = self.predicted_facelets_str
            if not expected or len(expected) != 54:
                failure_code = "EXPECTED_STATE_MISSING"
                failure_reason = "缺少转后预期状态，无法执行视觉复核。"
            else:
                observations = b.task_observe_released(3000)
                comparison = compare_observations(expected, observations)
                affected = list(range(9)) + [
                    "URFDLB".index(face) * 9 + i for face in "RFLB" for i in range(3)
                ]
                observed_state = comparison["observed_state"]
                self.observed_facelets_str = observed_state
                self.conflict_set = set(comparison["conflicts"])
                missing = [i for i in affected if observed_state[i] == "?"]
                mismatch = [i for i in affected if observed_state[i] not in ("?", expected[i])]
                affected_ok = (
                    not missing
                    and not mismatch
                    and not comparison["conflicts"]
                    and not comparison["differences"]
                )
                no_recolor = bool(self._initial_rgba is not None and np.array_equal(self._initial_rgba, b.model.geom_rgba))
                logical_unchanged = self._initial_sentinel == b._appearance_state
                same_model_data = (self._initial_model_id, self._initial_data_id) == (id(b.model), id(b.data))
                active_eq = np.flatnonzero(b.data.eq_active).tolist()

                unknown_total = observed_state.count("?")
                observed_total = 54 - unknown_total
                self.cube_validation_status = (
                    "CONFLICT"
                    if comparison["conflicts"]
                    else "INCOMPLETE"
                    if unknown_total > 0
                    else "VALID_SOLVABLE"
                )
                obs_id = f"obs-{uuid.uuid4().hex[:8]}"
                frame_id = f"frm-{uuid.uuid4().hex[:8]}"
                self.last_observation_ref = ObservationReference(
                    observation_id=obs_id,
                    frame_id=frame_id,
                    sim_time=self._sim_time(),
                    camera_name="released_scan_cameras",
                    observed_count=observed_total,
                    unknown_count=unknown_total,
                    conflict_count=len(comparison["conflicts"]),
                    validation_status=self.cube_validation_status,
                    reconstructed_facelets=observed_state,
                    cube_center_world_m=self.last_observation_ref.cube_center_world_m if self.last_observation_ref else None,
                    summary=f"转后独立相机复核：观测 {observed_total}/54 格（D 面 {unknown_total} 格保持未知），受影响 21 格{'全部匹配' if affected_ok else '存在偏差'}",
                )
                output_ref = obs_id
                verification_payload = {
                    "affected_21_verified": affected_ok,
                    "affected_observed_count": len(affected) - len(missing),
                    "affected_missing": missing,
                    "affected_mismatch": mismatch,
                    "comparison_status": comparison["status"],
                    "observed_state": observed_state,
                    "expected_state": expected,
                    "no_recolor": no_recolor,
                    "logical_state_unchanged": logical_unchanged,
                    "same_model_and_data": same_model_data,
                    "active_equalities": active_eq,
                }
                if self.physical_verification is None:
                    self.physical_verification = {}
                self.physical_verification.update(verification_payload)
                output_data = dict(self.physical_verification)

                if affected_ok and no_recolor and logical_unchanged and same_model_data and not active_eq:
                    success = True
                    result_summary = (
                        f"视觉复核通过：U 层受影响 21/21 贴片全部匹配，0 冲突，D 面 9 格保持未知，"
                        f"且确认无运行时改色或状态篡改。"
                    )
                    self.mission.result_summary = (
                        f"物理 U 层验证成功：实测转角 {self.last_turn_angle_deg:.2f}°，"
                        f"接触证据完整，21/21 受影响贴片视觉复核通过。"
                    )
                    self._record_decision(
                        event_type=DecisionEventType.VERIFICATION_COMPLETED,
                        source="VisualTurnVerifier",
                        summary=result_summary,
                        rationale="转后独立相机观察与符号预期在 21 个受影响格上完全一致，底层模型与 geom_rgba 未被篡改。",
                        status="VERIFIED",
                        skill_id=step.skill_id,
                        output_reference=obs_id,
                    )
                else:
                    failure_code = comparison["status"]
                    failure_reason = (
                        f"转后视觉或防作弊复核未通过：status={failure_code}, "
                        f"missing={len(missing)}, mismatch={len(mismatch)}, no_recolor={no_recolor}"
                    )

        else:
            failure_code = "UNKNOWN_SKILL"
            failure_reason = f"未实现执行器分发：{step.skill_id}"

        step.ended_sim_time = self._sim_time()
        step.ended_wall_time = now_wall_time()
        step.elapsed_sec = round(step.ended_sim_time - step.started_sim_time, 3)
        step.output_reference = output_ref
        exec_state.ended_sim_time = step.ended_sim_time
        exec_state.ended_wall_time = step.ended_wall_time
        exec_state.elapsed_sec = step.elapsed_sec
        exec_state.output_data = output_data
        exec_state.verification_passed = success

        if success:
            step.status = PlanStepStatus.VERIFIED
            step.result_summary = result_summary
            exec_state.status = PlanStepStatus.VERIFIED
            exec_state.result_summary = result_summary
            self.agent_state.last_execution_feedback = result_summary
            self._record_decision(
                event_type=DecisionEventType.SKILL_COMPLETED,
                source="SkillExecutor",
                summary=result_summary,
                rationale=f"Skill [{step.skill_id}] 在真实仿真中执行并验证通过。",
                status="VERIFIED",
                skill_id=step.skill_id,
                input_reference=input_ref,
                output_reference=output_ref,
            )
            return "VERIFIED"

        step.status = PlanStepStatus.FAILED
        step.failure_reason = failure_reason
        step.result_summary = failure_reason
        exec_state.status = PlanStepStatus.FAILED
        exec_state.failure_code = failure_code
        exec_state.failure_reason = failure_reason
        exec_state.result_summary = failure_reason or "FAILED"
        self.agent_state.last_execution_feedback = failure_reason
        self._record_decision(
            event_type=DecisionEventType.SKILL_FAILED,
            source="SkillExecutor",
            summary=f"Skill [{step.skill_id}] 失败：{failure_code}",
            rationale=failure_reason or "执行失败",
            status="FAILED",
            skill_id=step.skill_id,
            input_reference=input_ref,
            failure_reason=failure_reason,
        )
        return "FAILED"

    def close(self) -> None:
        def _close_gl() -> None:
            if self._backend is not None:
                try:
                    self._backend.renderer.close()
                except Exception:
                    pass
                self._backend = None

        try:
            self._run_on_gl_thread(_close_gl)
        finally:
            if self._executor is not None:
                self._executor.shutdown(wait=False)
                self._executor = None
