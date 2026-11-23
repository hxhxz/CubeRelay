"""Real MuJoCo SimulationSession integrating Mission, SkillRegistry, Planner, and DecisionEvents."""

from __future__ import annotations

import base64
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict, dataclass, field
import hashlib
import io
import math
import random
import threading
import time
from pathlib import Path
from typing import Any, Callable
import uuid

import numpy as np
from PIL import Image

from cube_relay.cube import CubeEngine, CubeSolver, SOLVED_FACELETS
from cube_relay.cube.state import LEGAL_MOVES, inverse_move
from cube_relay.cube.validation import StateValidator
from cube_relay.embodied.active_inspection_v7 import ContinuousActiveInspector
from cube_relay.embodied.failure_aware_v6 import run_bounded_grasp_retry
from cube_relay.embodied.perception_v2 import DeterministicCubeLocalizer, StickerStateFusion
from cube_relay.embodied.physical_u import ContactUTurn
from cube_relay.embodied.visual_turn_loop import compare_observations
from cube_relay.embodied.vlm import ChromaCubePresenceDetector
from cube_relay.execution.action_chunk import CancellationToken, InterruptMode
from cube_relay.experiment import (
    ArtifactExporter,
    ExperimentRecorder,
    ExperimentRun,
    QualityStatus,
    TruthAccessCategory,
)

from .events import (
    DecisionEvent,
    DecisionEventLog,
    DecisionEventType,
    TraceEventLog,
    TraceEventType,
    now_wall_time,
)
from .models import (
    AgentObservation,
    AgentObservabilityState,
    MissionState,
    MissionStatus,
    MissionType,
    ObservationReference,
    PlanState,
    PlanStep,
    PlanStepStatus,
    PlannerMode,
    RelayPhase,
    SkillExecutionState,
)
from .relay_cognition import (
    BeliefConservationAnalyzer,
    ExecutionContractSpec,
    FlipCostProfile,
    HRIDialogueInterpreter,
    HumanUtteranceSemantics,
    StaleResponseGuard,
    compute_candidate_solve_paths,
)
from .planner import (
    MISSION_SPECS,
    DecisionPolicy,
    DeterministicMissionPlanner,
    GeminiMissionPlanner,
    LLMAgentDecisionPolicy,
    VLMInspectionLimits,
)
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
        "az": 146.0,
        "el": -22.0,
        "dist": 0.36,
    },
    "cube_closeup": {
        "label": "魔方特写",
        "track_body": "cube",
        "az": 132.0,
        "el": -28.0,
        "dist": 0.28,
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


@dataclass
class _HumanPrivateTruth:
    """Strictly external human action/pose workspace truth; NEVER read by scene_state, AgentObservation, Tracker, or Planner."""

    moves_this_turn: list[str] = field(default_factory=list)
    base_handover_xy: tuple[float, float] = (0.0, 0.0)
    base_handover_quat: tuple[float, float, float, float] = (1.0, 0.0, 0.0, 0.0)
    applied_dx_m: float = 0.0
    applied_dy_m: float = 0.0
    applied_dyaw_deg: float = 0.0
    dirty_since_handover: bool = False


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
        experiments_dir: Path | str | None = None,
        trajectory_sample_hz: float = 50.0,
        include_audit_ground_truth: bool = True,
        allow_agent_failure_recovery: bool = False,
        full_26_cubie: bool = False,
        scramble_steps: int = 15,
        relay_scramble_steps: int | str = 5,
        record_video_frames: bool = False,
        hri_interpreter: HRIDialogueInterpreter | None = None,
    ) -> None:
        self.seed = int(seed)
        self.width = int(width)
        self.height = int(height)
        self.full_26_cubie = bool(full_26_cubie)
        self.scramble_steps = int(scramble_steps)
        self.relay_scramble_steps: int | str = relay_scramble_steps
        self._pending_relay_scramble_moves: list[str] | None = None
        self.record_video_frames = bool(record_video_frames)
        self.recorded_video_frames: list[np.ndarray] = []
        self._flip_cost_profile = FlipCostProfile.from_file()
        self._belief_analyzer = BeliefConservationAnalyzer()
        self._stale_guard = StaleResponseGuard()
        self._hri_interpreter = hri_interpreter or HRIDialogueInterpreter()
        self._hri_lock = threading.Lock()
        self._active_cancellation_token: CancellationToken | None = None
        self._active_execution_contract: ExecutionContractSpec | None = None
        self._human_private = _HumanPrivateTruth()
        self.use_dedicated_thread = use_dedicated_thread
        self.stream_interval_sec = float(stream_interval_sec)
        self.stream_sim_interval_sec = float(stream_sim_interval_sec)
        self.video_path = video_path
        self.trajectory_sample_hz = float(trajectory_sample_hz)
        self.include_audit_ground_truth = bool(include_audit_ground_truth)
        self.allow_agent_failure_recovery = bool(allow_agent_failure_recovery)
        self.session_id = f"LIVE-SEED{self.seed}-{uuid.uuid4().hex[:6].upper()}"

        self.experiment_recorder = ExperimentRecorder(base_dir=experiments_dir)
        self.exporter = ArtifactExporter(self.experiment_recorder)
        self._current_run: ExperimentRun | None = None
        self._pending_perturbation: dict[str, Any] | None = None

        self.registry = registry or SkillRegistry(physical_full_cube=self.full_26_cubie)
        self.planner: DecisionPolicy = planner or DeterministicMissionPlanner()
        self.event_log = DecisionEventLog()
        self.trace_log = TraceEventLog()
        self._timeline_events: list[dict[str, Any]] = []
        self._recorded_observations: list[dict[str, Any]] = []
        self._evidence_bundles: list[dict[str, Any]] = []
        self._active_decision_id: str | None = None
        self._active_evidence_bundle_id: str | None = None
        self._active_request_id: str | None = None
        self._active_prompt_sha256: str | None = None
        self._active_perception_provenance: dict[str, Any] = {}
        self._active_evidence_conflicts: list[str] = []
        self._active_evidence_validity: dict[str, Any] = {}
        self._active_semantic_provided: bool | None = None
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
        self._user_camera_locked = False
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
            model_provider=getattr(self.planner, "model_provider", None),
            status_label=self.planner.status_label(),
        )
        self._sync_dual_model_agent_state()
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

        # Mode B (VLM-Controlled Inspection) & timing metrics
        self._scan_fusion = StickerStateFusion()
        self._scan_frame_offset = 0
        self._scan_obs_seq = 0
        self._last_skill_result: dict[str, Any] | None = None
        self._vlm_decision_rounds = 0
        self._vlm_observe_calls = 0
        self._vlm_reorient_calls = 0
        self._vlm_calls_count = 0
        self._total_vlm_latency_ms = 0.0
        self._total_input_tokens = 0
        self._total_output_tokens = 0
        self._total_reasoning_tokens = 0
        self._skill_duration_sim_s = 0.0
        self._total_execution_wall_s = 0.0
        self._latest_agent_observation: AgentObservation | None = None
        self._agent_observation_history: list[dict[str, Any]] = []
        self._current_obs_image_url: str | None = None
        self._current_obs_frame_id: str | None = None
        self._current_obs_camera_id: str | None = None

        # Latest rendered frame URLs & snapshot
        self._main_frame_url: str | None = None
        self._wrist_rgb_url: str | None = None
        self._wrist_depth_url: str | None = None
        self._depth_range_m: list[float] = [0.35, 2.25]
        self._latest_snapshot: dict[str, Any] = {}
        self._last_stream_wall = 0.0
        self._last_stream_sim = 0.0
        self._init_relay_episode_state(clear_video=True)

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
            physical_u=not self.full_26_cubie,
            full_26_cubie=self.full_26_cubie,
            width=self.width,
            height=self.height,
            video_path=self.video_path,
            video_timing="sim_time",
        )
        self._reset_backend_scene(self.seed)
        self._emit_snapshot(refresh_frames=True)

    def _apply_full_26_cubie_sync(self, full_26_cubie: bool | None) -> bool:
        """Switch physical backend mode on the GL thread when `full_26_cubie` changes."""
        if full_26_cubie is None:
            return False
        target = bool(full_26_cubie)
        if target == self.full_26_cubie and self._backend is not None:
            return False
        if self._current_run is not None:
            self._current_run.close()
            self._current_run = None
        if self._backend is not None:
            try:
                self._backend.renderer.close()
            except Exception:
                pass
            self._backend = None
        for attr in (
            "_orig_set_sticker_colors",
            "_orig_engine_apply_move",
            "_orig_reset_random",
            "_orig_reset_with_perturbation",
        ):
            if hasattr(self, attr):
                delattr(self, attr)
        self.full_26_cubie = target
        self.registry = SkillRegistry(physical_full_cube=self.full_26_cubie)
        self._init_backend_sync()
        return True

    def reconfigure_full_26_cubie(self, full_26_cubie: bool) -> dict[str, Any]:
        """Reconfigure this live session between 26-cubie mode and legacy U-only mode."""
        target = bool(full_26_cubie)
        self._stop_event.set()

        def _do() -> dict[str, Any]:
            self._stop_event.clear()
            self._apply_full_26_cubie_sync(target)
            return self.get_snapshot()

        return self._run_on_gl_thread(_do)

    def _reset_backend_scene(self, seed: int, *, perturbation: dict[str, Any] | None = None) -> dict[str, Any] | None:
        b = self._backend
        self.seed = int(seed)
        self.session_id = f"LIVE-SEED{self.seed}-{uuid.uuid4().hex[:6].upper()}"
        # Restore original unpatched methods if previously locked
        if hasattr(self, "_orig_set_sticker_colors"):
            b._set_sticker_colors = self._orig_set_sticker_colors
            b.engine.apply_move = self._orig_engine_apply_move
            b.reset_random = self._orig_reset_random
            if hasattr(self, "_orig_reset_with_perturbation"):
                b.reset_with_perturbation = self._orig_reset_with_perturbation
        if self._current_run is not None:
            self._current_run.close()
            self._current_run = None
        b.experiment_run = None
        pert_meta: dict[str, Any] | None = None
        self._pending_perturbation = dict(perturbation) if perturbation else None
        if perturbation:
            pert_meta = b.reset_with_perturbation(
                self.seed,
                self.scramble_steps,
                dx_m=float(perturbation.get("dx_m", 0.0)),
                dy_m=float(perturbation.get("dy_m", 0.0)),
                dyaw_rad=float(perturbation.get("dyaw_rad", 0.0)),
                vision_fault_mode=perturbation.get("vision_fault_mode"),
            )
        elif self.selected_mission_type == MissionType.RELAY_SOLVE_CUBE:
            eff_steps = self._resolved_relay_scramble_count(self.seed)
            if self._pending_relay_scramble_moves:
                b.reset_random(self.seed, eff_steps, scramble_moves=self._pending_relay_scramble_moves)
            else:
                b.reset_random(self.seed, eff_steps)
        else:
            b.reset_random(self.seed, self.scramble_steps)
        self._init_relay_episode_state(clear_video=False)
        self._orig_set_sticker_colors = b._set_sticker_colors
        self._orig_engine_apply_move = b.engine.apply_move
        self._orig_reset_random = b.reset_random
        self._orig_reset_with_perturbation = b.reset_with_perturbation
        self._initial_rgba = b.model.geom_rgba.copy()
        self._initial_sentinel = b._appearance_state
        self._initial_model_id = id(b.model)
        self._initial_data_id = id(b.data)

        self.mission = None
        self.plan = None
        self.skill_executions.clear()
        self.event_log.clear()
        self.trace_log.clear()
        self._timeline_events.clear()
        self._recorded_observations.clear()
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
        self._scan_fusion = StickerStateFusion()
        self._scan_frame_offset = 0
        self._scan_obs_seq = 0
        self._last_skill_result = None
        self._vlm_decision_rounds = 0
        self._vlm_observe_calls = 0
        self._vlm_reorient_calls = 0
        self._vlm_calls_count = 0
        self._total_vlm_latency_ms = 0.0
        self._total_input_tokens = 0
        self._total_output_tokens = 0
        self._total_reasoning_tokens = 0
        self._skill_duration_sim_s = 0.0
        self._total_execution_wall_s = 0.0
        self._latest_agent_observation = None
        self._agent_observation_history = []
        self._evidence_bundles.clear()
        self._active_decision_id = None
        self._active_evidence_bundle_id = None
        self._active_request_id = None
        self._active_prompt_sha256 = None
        self._active_perception_provenance = {}
        self._active_evidence_conflicts = []
        self._active_evidence_validity = {}
        self._active_semantic_provided = None
        self._current_obs_image_url = None
        self._current_obs_frame_id = None
        self._current_obs_camera_id = None
        self.scene_state = {
            "simulation_initialized": True,
            "physical_u_scene_enabled": bool(b.physical_u),
            "full_26_cubie_scene_enabled": bool(getattr(b, "full_26_cubie", False)),
            "turn_station_available": bool(b.physical_u or getattr(b, "full_26_cubie", False)),
            "cube_localized": False,
            "scan_attempted": False,
            "cube_released_on_table": False,
            "cube_held_in_gripper": False,
            "all_54_facelets_observed": False,
            "finish_inspection_done": False,
            "cube_localized_and_scanned": False,
            "cube_state_validated": False,
            "symbolic_plan_available": False,
            "capability_checked": False,
            "u_turns_completed": 0,
            "physical_u_turn_executed": False,
            "physical_face_turn_executed": False,
            "executed_physical_moves": [],
            "cube_top_face": "U",
            "cube_bottom_face": "D",
            "turn_station_cleared": False,
            "is_lattice_aligned": True,
            "residual_slice_angle_deg": 0.0,
            "post_turn_verified": False,
            "symbolic_solution": [],
            "fallback_triggered": False,
            "needs_rescan": False,
            "is_solved": False,
            "post_solve_independent_verified": False,
            "vlm_awakening_requested": False,
            "relay_cognitive_context": {},
        }
        self.agent_state = AgentObservabilityState(
            planner_mode=self.planner.mode,
            planner_name=self.planner.name,
            llm_connected=self.planner.llm_connected,
            llm_model=self.planner.llm_model,
            model_provider=getattr(self.planner, "model_provider", None),
            status_label=self.planner.status_label(),
        )
        self._sync_dual_model_agent_state()
        # Create an initial preview plan for the selected mission so UI shows what will run
        preview_mission = self._new_mission_object(self.selected_mission_type)
        self.mission = preview_mission
        self.plan = self.planner.create_plan(
            preview_mission,
            self.registry,
            plan_id=f"plan-{preview_mission.mission_id}",
        )
        self.mission.current_plan_id = self.plan.plan_id
        return pert_meta

    def _lock_backend_anti_cheat(self) -> None:
        b = self._backend

        def _forbidden(*args: Any, **kwargs: Any) -> None:
            raise AssertionError("Post-initialization software recolor / symbolic mutation / reset is forbidden")

        b._set_sticker_colors = _forbidden
        b.engine.apply_move = _forbidden
        b.reset_random = _forbidden
        b.reset_with_perturbation = _forbidden

    def _register_observation(self, record: dict[str, Any]) -> None:
        """Append an observation record chronologically and persist to ExperimentRun."""
        entry = dict(record)
        self._recorded_observations.append(entry)
        if self._current_run is not None:
            self._current_run.events.record_observation(entry)

    def _record_timeline_from_decision(self, ev: DecisionEvent) -> None:
        """Capture an immutable historical timeline entry at event creation time."""
        if ev.event_type not in {
            DecisionEventType.MISSION_CREATED,
            DecisionEventType.OBSERVATION_RECEIVED,
            DecisionEventType.SKILL_COMPLETED,
            DecisionEventType.SKILL_FAILED,
            DecisionEventType.CAPABILITY_BLOCKED,
            DecisionEventType.VERIFICATION_COMPLETED,
            DecisionEventType.MISSION_COMPLETED,
            DecisionEventType.MISSION_FAILED,
        }:
            return
        steps = self.plan.steps if self.plan else []
        running_step = next((s for s in steps if s.status == PlanStepStatus.RUNNING), None)
        last_step = steps[-1] if steps else None
        active_step = running_step or (
            next((s for s in reversed(steps) if s.skill_id == ev.skill_id), None)
            if ev.skill_id
            else None
        ) or last_step
        telemetry = self._read_telemetry()
        self._timeline_events.append({
            "event_id": ev.event_id,
            "short_label": f"{int(ev.sim_time or 0):02d}:{(ev.sim_time or 0)%60:05.2f} {ev.event_type.value}",
            "sim_time": ev.sim_time or 0.0,
            "wall_time": ev.wall_time,
            "skill_name": ev.skill_id or ev.event_type.value,
            "stage_id": active_step.step_id if active_step else "",
            "status": (
                "FAILED"
                if ev.event_type
                in {
                    DecisionEventType.SKILL_FAILED,
                    DecisionEventType.CAPABILITY_BLOCKED,
                    DecisionEventType.MISSION_FAILED,
                }
                else "VERIFIED"
            ),
            "failure_reason": ev.failure_reason,
            "summary": ev.summary,
            "turn_angle_deg": telemetry["layerTurnAngleDeg"] or 0.0,
            "contact_force_n": telemetry["contactForceN"] or 0.0,
            "gripper_width_mm": telemetry["gripperWidthMm"] or 0.0,
            "gripper_state": telemetry["gripperState"],
            "completed_stage_index": sum(
                1 for s in steps if s.status == PlanStepStatus.VERIFIED
            ),
        })

    def _sync_run_artifacts(self) -> None:
        if self._current_run is None:
            return
        self._current_run.events.replace_decision_events(
            [ev.model_dump(mode="json") for ev in self.event_log.events]
        )
        self._current_run.events.replace_trace_events(
            [ev.model_dump(mode="json") for ev in self.trace_log.events]
        )
        self._current_run.events.replace_observations(list(self._recorded_observations))
        self._current_run.set_skill_executions(
            [ex.model_dump(mode="json") for ex in self.skill_executions]
        )

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
        if self.record_video_frames:
            self.recorded_video_frames.append(main_rgb)

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
        }
        if getattr(b, "physical_u", False):
            joints["u_layer"] = round(float(b.data.qpos[b.model.jnt_qposadr[b._joint("u_layer_joint")]]), 4)
        elif getattr(b, "full_26_cubie", False):
            joints["turn_rotor"] = round(float(b.data.qpos[b.model.jnt_qposadr[b._joint("turn_rotor_joint")]]), 4)
        cube_id = b._id(mj.mjtObj.mjOBJ_BODY, "cube")
        cube_mm = [round(float(v) * 1000.0, 1) for v in b.data.xpos[cube_id]]
        u_deg = round(-math.degrees(joints.get("u_layer", joints.get("turn_rotor", 0.0))), 2)
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
        elif m_status == MissionStatus.WAITING_FOR_HUMAN_TURN:
            task_status = "WAITING_FOR_HUMAN_TURN"
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
        timeline = list(self._timeline_events)
        structured_observations = list(self._recorded_observations)
        recording_state: dict[str, Any]
        if self._current_run is not None:
            run = self._current_run
            recording_state = {
                "run_id": run.config.run_id,
                "status": run.status,
                "include_audit_ground_truth": run.config.include_audit_ground_truth,
                "trajectory_sample_hz": run.config.trajectory_sample_hz,
                "counts": {
                    "frames": len(run.poses.frames),
                    "pose_estimates": len(run.poses.pose_estimates),
                    "grasp_targets": len(run.grasp_targets.grasp_targets),
                    "robot_states": len(run.trajectories.robot_states),
                    "trajectory_commands": len(run.trajectories.trajectory_commands),
                    "contact_samples": len(run.contacts.samples),
                    "contact_verifications": len(run.contacts.verifications),
                    "decision_events": len(run.events.decision_events),
                    "trace_events": len(run.events.trace_events),
                    "observations": len(run.events.observations),
                },
            }
        else:
            recording_state = {
                "run_id": None,
                "status": "IDLE",
                "include_audit_ground_truth": self.include_audit_ground_truth,
                "trajectory_sample_hz": self.trajectory_sample_hz,
                "counts": {},
            }

        self.agent_state.latest_observation = self.last_observation_ref
        return {
            "session_id": self.session_id,
            "seed": self.seed,
            "full_26_cubie": self.full_26_cubie,
            "physical_full_cube": bool(self.registry.physical_full_cube),
            "is_lattice_aligned": bool(self.scene_state.get("is_lattice_aligned", True)),
            "residual_slice_angle_deg": float(self.scene_state.get("residual_slice_angle_deg", 0.0)),
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
            "timing_metrics": {
                "sim_time": sim_time,
                "skill_duration_sim_s": round(self._skill_duration_sim_s, 4),
                "total_execution_wall_s": round(self._total_execution_wall_s, 4),
                "model_latency_ms": round(self._total_vlm_latency_ms, 2),
                "vlm_calls": self._vlm_calls_count,
                "input_tokens": self._total_input_tokens,
                "output_tokens": self._total_output_tokens,
                "reasoning_tokens": self._total_reasoning_tokens,
            },
            "evidence_bundles": list(self._evidence_bundles),
            "running": self._running,
            "run_id": self._current_run.config.run_id if self._current_run is not None else None,
            "experiment_recording": recording_state,
            "relay_phase": self._relay_phase.value,
            "relay_state": self._build_relay_state_snapshot(),
        }

    # ------------------------------------------------------------------
    # Camera / UI controls
    # ------------------------------------------------------------------

    # ------------------------------------------------------------------
    # M5 Agent Relay cognition & HRI helpers (Strict Zero Action/Pose Leakage)
    # ------------------------------------------------------------------

    def _init_relay_episode_state(self, *, clear_video: bool = True) -> None:
        self._stale_guard.reset()
        self._active_cancellation_token = None
        self._active_execution_contract = None
        if clear_video:
            self.recorded_video_frames.clear()
        with self._hri_lock:
            self._human_private = _HumanPrivateTruth()
            self._relay_phase = RelayPhase.IDLE
            self._relay_round_number = 0
            self._relay_last_verified_54: str | None = None
            self._relay_state_history: list[str] = []
            self._relay_last_suggested_moves: list[str] = []
            self._relay_delegation_reason_zh = ""
            self._relay_handover_message_zh = ""
            self._relay_human_dialog: list[dict[str, Any]] = []
            self._relay_active_constraints: list[str] = []
            self._relay_latest_human_reply: str | None = None
            self._relay_clarification_pending = False
            self._relay_clarification_question_zh: str | None = None
            self._relay_clarification_options: list[str] = []
            self._relay_clarification_topic: str | None = None
            self._relay_initial_optimal_steps: int | None = None
            self._relay_robot_moves_count = 0
            self._relay_human_turns_count = 0
            self._relay_human_inferred_moves_count = 0
            self._relay_round_tags: list[str] = []
            self._relay_latest_preemption: dict[str, Any] | None = None
            self._relay_vlm_diagnosis: dict[str, Any] | None = None
            self._relay_latest_belief_result: dict[str, Any] | None = None
            self._relay_candidate_paths: dict[str, Any] = {}
            self._relay_cognitive_stats: dict[str, int] = {
                "rapid_glance_deduction_successes": 0,
                "full_bottom_scans": 0,
                "on_demand_vlm_calls": 0,
                "fast_loop_contract_interceptions": 0,
                "stale_responses_discarded": 0,
                "clarifications_requested": 0,
                "saved_high_cost_flips": 0,
            }
            self._relay_transient_retries = 0
            self._relay_mission_wall_started = 0.0
            self._relay_paused_by_interrupt = False
            self._relay_auto_resume_after_pause = False
            self._relay_latest_hri_semantics: dict[str, Any] | None = None

    def _resolved_relay_scramble_count(self, seed: int) -> int:
        val = self.relay_scramble_steps
        if isinstance(val, str) and val.strip().lower() == "random":
            return int(random.Random(seed).choice([4, 5, 6, 7, 8]))
        try:
            n = int(val)
        except (TypeError, ValueError):
            n = 5
        return max(1, min(25, n))

    def _ensure_relay_agent_planner(self) -> None:
        if isinstance(self.planner, LLMAgentDecisionPolicy):
            if self.planner.guide_mode != "GUIDE_MINIMAL":
                self.planner.guide_mode = "GUIDE_MINIMAL"
            if self.planner.use_vlm_perception:
                self.planner.use_vlm_perception = False
                self._sync_dual_model_agent_state()
            if self.planner.limits.max_decision_rounds < 64:
                self.planner.limits = self.planner.limits.model_copy(
                    update={
                        "max_decision_rounds": max(self.planner.limits.max_decision_rounds, 64),
                        "max_vlm_calls": max(self.planner.limits.max_vlm_calls, 64),
                        "max_sim_time_sec": max(self.planner.limits.max_sim_time_sec, 600.0),
                        "allow_cv_only_on_vlm_failure": True,
                    }
                )
            return
        candidate = LLMAgentDecisionPolicy(
            guide_mode="GUIDE_MINIMAL",
            use_vlm_perception=False,
            limits=VLMInspectionLimits(
                max_vlm_calls=64,
                max_decision_rounds=64,
                max_sim_time_sec=600.0,
                allow_cv_only_on_vlm_failure=True,
            ),
        )
        if candidate.agent_provider.client.is_configured():
            self.planner = candidate
            self._sync_dual_model_agent_state()

    def _get_hri_interpreter(self) -> HRIDialogueInterpreter:
        interp = getattr(self, "_hri_interpreter", None)
        if interp is None:
            interp = HRIDialogueInterpreter()
            self._hri_interpreter = interp
        return interp

    def _append_relay_dialog(
        self,
        role: str,
        text: str,
        *,
        topic: str | None = None,
        semantics: dict[str, Any] | None = None,
    ) -> None:
        clean = str(text or "").strip()
        if not clean:
            return
        entry: dict[str, Any] = {
            "role": role,
            "text": clean,
            "topic": topic,
            "sim_time": self._sim_time(),
            "wall_time": now_wall_time(),
        }
        if semantics is not None:
            entry["semantics"] = dict(semantics)
        with self._hri_lock:
            self._relay_human_dialog.append(entry)
            if len(self._relay_human_dialog) > 30:
                self._relay_human_dialog = self._relay_human_dialog[-30:]

    def _refresh_relay_cognitive_context(self) -> dict[str, Any]:
        """Assemble strict Zero-Leakage cognitive summary for LLMAgentDecisionPolicy."""
        belief = dict(self._relay_latest_belief_result or {})
        known_54 = (
            self._relay_last_verified_54
            if (
                self._relay_last_verified_54
                and len(self._relay_last_verified_54) == 54
                and "?" not in self._relay_last_verified_54
                and not self.scene_state.get("needs_rescan", False)
            )
            else None
        )
        top_face = str(self.scene_state.get("cube_top_face") or "U")
        bottom_face = str(self.scene_state.get("cube_bottom_face") or "D")
        if known_54 is not None:
            try:
                paths = compute_candidate_solve_paths(
                    known_54,
                    top_face=top_face,
                    bottom_face=bottom_face,
                    flip_profile=self._flip_cost_profile,
                    inferred_human_moves=belief.get("inferred_human_moves") or [],
                    state_history=self._relay_state_history,
                )
            except Exception:
                paths = {}
            self._relay_candidate_paths = paths
            solved_now = bool(paths.get("is_solved", False))
            self.scene_state["is_solved"] = solved_now
            sol = list(paths.get("primary_kociemba_solution") or [])
            self.scene_state["symbolic_solution"] = sol
            if self.mission is not None:
                self.mission.symbolic_solution = sol
            if self._relay_initial_optimal_steps is None:
                self._relay_initial_optimal_steps = len(sol)
        else:
            paths = dict(self._relay_candidate_paths or {}) if not self.scene_state.get("needs_rescan") else {}

        b = self._backend
        cube_loc = getattr(b, "_cube_26_location", "table") if b is not None else "table"
        with self._hri_lock:
            dialog = list(self._relay_human_dialog[-10:])
            constraints = list(self._relay_active_constraints[-8:])
            latest_reply = self._relay_latest_human_reply
            clar_pending = bool(self._relay_clarification_pending)
            paused_by_interrupt = bool(getattr(self, "_relay_paused_by_interrupt", False))
            latest_hri_sem = dict(self._relay_latest_hri_semantics) if getattr(self, "_relay_latest_hri_semantics", None) else None
            preempt_info = dict(self._relay_latest_preemption) if self._relay_latest_preemption else None
            vlm_diag = dict(self._relay_vlm_diagnosis) if self._relay_vlm_diagnosis else None
            last_suggested = list(self._relay_last_suggested_moves)

        ctx = {
            "needs_rescan": bool(self.scene_state.get("needs_rescan", False)),
            "belief_state": {
                "previous_belief_54_known": bool(self._relay_last_verified_54 and len(self._relay_last_verified_54) == 54),
                "current_54_known": known_54 is not None,
                "deduced_54_unique": bool(belief.get("deduced_54_unique", known_54 is not None)),
                "ambiguous_facelet_count": int(belief.get("ambiguous_facelet_count", 54 if known_54 is None else 0)),
                "ambiguous_facelet_indices": list(belief.get("ambiguous_facelet_indices") or []),
                "occluded_face": belief.get("occluded_face"),
                "inferred_human_moves": list(belief.get("inferred_human_moves") or []),
                "human_deviation_detected": bool(belief.get("human_deviation_detected", False)),
                "suggested_moves_last_handover": last_suggested,
                "post_solve_independent_verified": bool(self.scene_state.get("post_solve_independent_verified", False)),
                "conservation_summary_zh": belief.get("reasoning_summary_zh", ""),
            },
            "candidate_paths_and_embodied_costs": {
                "is_solved": bool(paths.get("is_solved", False)),
                "primary_kociemba_solution": list(paths.get("primary_kociemba_solution") or []),
                "remaining_optimal_steps": paths.get("remaining_optimal_steps"),
                "alternative_non_undo_solution": paths.get("alternative_non_undo_solution"),
                "undo_conflict_risk": bool(paths.get("undo_conflict_risk", False)),
                "undo_target_move": paths.get("undo_target_move"),
                "primary_move_costs": list(paths.get("primary_move_costs") or []),
                "alternative_move_costs": list(paths.get("alternative_move_costs") or []),
                "next_high_cost_2flip_move": paths.get("next_high_cost_2flip_move"),
                "calibration_priors_marginal": self._flip_cost_profile.to_agent_priors(),
            },
            "hri_context": {
                "human_dialog_history": dialog,
                "active_human_constraints": constraints,
                "clarification_pending": clar_pending,
                "latest_human_reply": latest_reply,
                "paused_by_interrupt": paused_by_interrupt,
                "latest_hri_semantics": latest_hri_sem,
            },
            "execution_and_contract_state": {
                "cube_top_face": top_face,
                "cube_bottom_face": bottom_face,
                "cube_location": cube_loc,
                "is_lattice_aligned": bool(self.scene_state.get("is_lattice_aligned", True)),
                "residual_slice_angle_deg": float(self.scene_state.get("residual_slice_angle_deg", 0.0)),
                "latest_preemption": preempt_info,
                "vlm_semantic_diagnosis": vlm_diag,
            },
        }
        self.scene_state["relay_cognitive_context"] = ctx
        return ctx

    def _build_turn_indicator(self, phase: RelayPhase) -> dict[str, Any]:
        """Build explicit turn ownership and 6-stage pipeline metadata for UI indicators."""
        stages = ["开局扫面", "机器人操作", "交接/澄清", "人类回合", "快瞄/修复", "复原核验"]
        is_post_human = bool(self._relay_human_turns_count > 0 or self._relay_round_number > 1)
        if phase == RelayPhase.WAITING_FOR_HUMAN_TURN:
            owner, stage_idx = "HUMAN", 3
            label = "🧑 当前回合：人类操作中（轮到你了）"
            hint = "点击右侧 18 动作盘 / 微扰放回位置，或直接在对话发送「我不玩了，你复原吧」立即交回。"
        elif phase == RelayPhase.AWAITING_HUMAN_CLARIFICATION:
            owner, stage_idx = "CLARIFY", 2
            label = "🟣 当前回合：等待你的意图确认"
            hint = "请选择快捷回复或输入说明（如「保留动作继续解」），发送后机械臂立即继续。"
        elif phase == RelayPhase.ROBOT_ACTING:
            owner, stage_idx = "ROBOT", 1
            label = "🦾 当前回合：机器人机械臂操作中"
            hint = "快环 50Hz 契约实时守护中，可随时输入指令或点击「紧急刹车/中断」。"
        elif phase == RelayPhase.ROBOT_PERCEIVING:
            owner = "ROBOT"
            stage_idx = 4 if is_post_human else 0
            label = "👁️ 当前回合：机器人视觉感知中"
            hint = "正在通过桌面快瞄或六面扫描定位并推导魔方 54 格状态。"
        elif phase == RelayPhase.AGENT_REASONING:
            owner = "ROBOT"
            if is_post_human and self.scene_state.get("needs_rescan"):
                stage_idx = 4
            elif not self._relay_last_verified_54:
                stage_idx = 0
            else:
                stage_idx = 1
            label = "🤖 当前回合：机器人 Agent 思考中"
            hint = "Gemini-3.8-Flash 正在权衡翻面代价、信息收益与你的自然语言约束。"
        elif phase == RelayPhase.PREEMPTED_RECOVERING:
            owner, stage_idx = "ROBOT", 1
            label = "⚡ 当前回合：紧急刹停并恢复对齐"
            hint = "快环已中断机械臂并纯接触回正晶格，完成后将移交控制权。"
        elif phase == RelayPhase.VERIFYING_SOLVED:
            owner, stage_idx = "ROBOT", 5
            label = "🔎 当前回合：机器人 6 面独立核验"
            hint = "机械臂正在释放夹具并用独立视角核对 54/54 完全复原。"
        elif phase == RelayPhase.RELAY_COMPLETED_VERIFIED:
            owner, stage_idx = "DONE", 5
            label = "🎉 回合结束：100% 物理复原已核验"
            hint = "54/54 贴片全部复原，可通过左侧导出或重置开启新一局。"
        elif phase == RelayPhase.FAILED:
            owner, stage_idx = "FAILED", 1
            label = "⚠️ 回合中止"
            hint = (self.mission.failure_reason if self.mission else None) or "请查看事件记录后重置场景。"
        else:
            owner, stage_idx = "IDLE", 0
            label = "⏸️ 待命：等待启动"
            hint = "选择打乱步数并点击右下角「开始任务」启动人机接力。"
        return {
            "owner": owner,
            "owner_label_zh": label,
            "stage_index": stage_idx,
            "stage_labels": stages,
            "next_action_hint_zh": hint,
            "is_terminal": phase in {RelayPhase.RELAY_COMPLETED_VERIFIED, RelayPhase.FAILED},
        }

    def _build_relay_state_snapshot(self) -> dict[str, Any]:
        phase = self._relay_phase
        b = self._backend
        aligned = bool(self.scene_state.get("is_lattice_aligned", True))
        res_deg = float(self.scene_state.get("residual_slice_angle_deg", 0.0))

        banner_map = {
            RelayPhase.IDLE: ("slate", "等待启动人机接力求解", "选择打乱步数或发送自然语言约束，点击启动任务由 Gemini Agent 自主领航。"),
            RelayPhase.AGENT_REASONING: ("blue", "🧠 Agent 正在推理与权衡代价...", "Gemini-3.8-Flash 正在综合 1s/25s 感知收益、翻面边际耗时与人类对话约束。"),
            RelayPhase.ROBOT_ACTING: ("blue", "🤖 机器人执行承诺动作中（快环契约守护已开启）", "50Hz 执行契约实时守约监控，支持随时自然语言打断或紧急刹车安全停泊。"),
            RelayPhase.ROBOT_PERCEIVING: ("violet", "🔍 机器人视觉感知与信念推导中...", "通过真实 RGB-D 重定位并校验 45 格桌面快瞄 / 6 面独立扫描状态。"),
            RelayPhase.WAITING_FOR_HUMAN_TURN: ("amber", "🧑 人类接力回合（请点击动作盘、微扰位置或发送指令）", "魔方已安全停放于桌面中央，机械臂已退回 (-0.42, 0.25)。"),
            RelayPhase.AWAITING_HUMAN_CLARIFICATION: ("amber", "💬 Agent 请求意图澄清（等待人类回复）", self._relay_clarification_question_zh or "请在对话框确认操作意图或选择下方快捷回复。"),
            RelayPhase.PREEMPTED_RECOVERING: ("violet", "⚡ 触发快环契约抢占！正在纯接触恢复晶格对齐...", "安全刹停并消除半拧错层偏角后，将控制权交还 Agent 大脑善后规划。"),
            RelayPhase.VERIFYING_SOLVED: ("violet", "🔎 正在执行 54/54 独立六面视觉复核...", "机械臂已清空夹具约束，正在逐面确认 100% 物理复原。"),
            RelayPhase.RELAY_COMPLETED_VERIFIED: ("emerald", "🎉 100% 物理复原（独立 54/54 视觉核验通过）", "零贴片改色、零动作/位姿真值泄漏，人机协作完美收官！"),
            RelayPhase.FAILED: ("red", "⚠️ 接力任务异常中止", (self.mission.failure_reason if self.mission else None) or "请查看决策事件与执行日志。"),
        }
        tone, title_zh, subtitle_zh = banner_map.get(phase, banner_map[RelayPhase.IDLE])
        with self._hri_lock:
            clicks = list(self._human_private.moves_this_turn)
            suggested = list(self._relay_last_suggested_moves)
            pref_done = 0
            for idx, mv in enumerate(clicks):
                if idx < len(suggested) and mv == suggested[idx]:
                    pref_done += 1
                else:
                    break
            deviated_ui = bool(clicks) and any(
                i >= len(suggested) or mv != suggested[i] for i, mv in enumerate(clicks)
            )
            hl_next = suggested[pref_done] if (not deviated_ui and pref_done < len(suggested)) else None
            dx_ui = round(float(self._human_private.applied_dx_m), 4)
            dy_ui = round(float(self._human_private.applied_dy_m), 4)
            dyaw_ui = round(float(self._human_private.applied_dyaw_deg), 2)
            dialog_copy = list(self._relay_human_dialog)
            constraints_copy = list(self._relay_active_constraints)
            clar_q = self._relay_clarification_question_zh
            clar_opts = list(self._relay_clarification_options)
            clar_topic = self._relay_clarification_topic
            clar_pending = bool(self._relay_clarification_pending)
            latest_hri_sem_copy = dict(self._relay_latest_hri_semantics) if getattr(self, "_relay_latest_hri_semantics", None) else None
            stats_copy = dict(self._relay_cognitive_stats)
            stats_copy["stale_responses_discarded"] = int(self._stale_guard.stale_responses_discarded)
            tags_copy = list(self._relay_round_tags)
            preempt_copy = dict(self._relay_latest_preemption) if self._relay_latest_preemption else None
            vlm_copy = dict(self._relay_vlm_diagnosis) if self._relay_vlm_diagnosis else None

        init_steps = self._relay_initial_optimal_steps
        rem_steps = self._relay_candidate_paths.get("remaining_optimal_steps")
        if self.scene_state.get("is_solved"):
            rem_steps = 0
            pct = 100.0
        elif init_steps and init_steps > 0 and rem_steps is not None:
            pct = round(max(0.0, min(99.0, ((init_steps - rem_steps) / float(init_steps)) * 100.0)), 1)
        elif phase == RelayPhase.RELAY_COMPLETED_VERIFIED:
            pct = 100.0
            rem_steps = 0
        else:
            pct = 0.0

        belief = dict(self._relay_latest_belief_result or {})
        waiting = bool(self.mission is not None and self.mission.status == MissionStatus.WAITING_FOR_HUMAN_TURN)
        turn_indicator = self._build_turn_indicator(phase)
        return {
            "enabled": self.selected_mission_type == MissionType.RELAY_SOLVE_CUBE,
            "phase": phase.value,
            "turn_indicator": turn_indicator,
            "scramble_steps": self.relay_scramble_steps,
            "resolved_scramble_steps": self._resolved_relay_scramble_count(self.seed),
            "round_number": self._relay_round_number,
            "banner": {
                "tone": tone,
                "title_zh": title_zh,
                "subtitle_zh": subtitle_zh,
            },
            "delegation": {
                "suggested_moves": suggested,
                "completed_prefix_count": pref_done,
                "deviated_this_turn": deviated_ui,
                "delegation_reason_zh": self._relay_delegation_reason_zh,
                "message_zh": self._relay_handover_message_zh,
                "saved_high_cost_flips_count": stats_copy.get("saved_high_cost_flips", 0),
            },
            "human_pad": {
                "active": waiting and (not clar_pending or phase == RelayPhase.WAITING_FOR_HUMAN_TURN),
                "waiting_for_human": waiting,
                "clicks_this_turn": clicks,
                "can_undo": waiting and len(clicks) > 0,
                "highlighted_next_move": hl_next,
            },
            "perturbation": {
                "dx_m": dx_ui,
                "dy_m": dy_ui,
                "dyaw_deg": dyaw_ui,
                "bounds": {
                    "dx_min_m": -0.08,
                    "dx_max_m": 0.08,
                    "dy_min_m": -0.08,
                    "dy_max_m": 0.08,
                    "dyaw_min_deg": -40.0,
                    "dyaw_max_deg": 40.0,
                },
            },
            "hri": {
                "dialog_history": dialog_copy,
                "active_constraints": constraints_copy,
                "clarification_pending": clar_pending,
                "clarification_question_zh": clar_q,
                "clarification_options": clar_opts,
                "clarification_topic": clar_topic,
                "latest_semantics": latest_hri_sem_copy,
            },
            "progress": {
                "initial_optimal_steps": init_steps,
                "remaining_optimal_steps": rem_steps,
                "completion_pct": pct,
                "robot_moves_count": self._relay_robot_moves_count,
                "human_turns_count": self._relay_human_turns_count,
                "human_moves_inferred_count": self._relay_human_inferred_moves_count,
                "is_solved": bool(self.scene_state.get("is_solved", False)),
                "post_solve_independent_verified": bool(self.scene_state.get("post_solve_independent_verified", False)),
                "round_tags": tags_copy,
            },
            "belief": {
                "deduced_54_unique": bool(belief.get("deduced_54_unique", bool(self._relay_last_verified_54))),
                "ambiguous_facelet_count": int(belief.get("ambiguous_facelet_count", 0)),
                "ambiguous_facelet_indices": list(belief.get("ambiguous_facelet_indices") or []),
                "occluded_face": belief.get("occluded_face"),
                "inferred_human_moves": list(belief.get("inferred_human_moves") or []),
                "human_deviation_detected": bool(belief.get("human_deviation_detected", False)),
                "undo_conflict_risk": bool(self._relay_candidate_paths.get("undo_conflict_risk", False)),
                "reasoning_summary_zh": belief.get("reasoning_summary_zh", ""),
            },
            "contract": {
                "active_contract": (
                    self._active_execution_contract.model_dump(mode="json")
                    if self._active_execution_contract is not None
                    else None
                ),
                "is_lattice_aligned": aligned,
                "residual_slice_angle_deg": res_deg,
                "latest_preemption": preempt_copy,
                "stale_guard": self._stale_guard.snapshot(),
                "vlm_semantic_diagnosis": vlm_copy,
            },
            "cognitive_stats": stats_copy,
            "flip_cost_priors": self._flip_cost_profile.to_agent_priors(),
            "cube_location": getattr(b, "_cube_26_location", "table") if b is not None else "table",
        }

    def _sync_dual_model_agent_state(self) -> None:
        if not isinstance(self.planner, LLMAgentDecisionPolicy):
            return
        pp = self.planner.perception_provider
        ap = self.planner.agent_provider
        use_vlm = bool(self.planner.use_vlm_perception)
        self.agent_state.use_vlm_perception = use_vlm
        self.agent_state.guide_mode = getattr(self.planner, "guide_mode", None)
        if use_vlm:
            self.agent_state.perception_model_provider = pp.client.provider_name
            self.agent_state.perception_model_name = pp.client.model
            self.agent_state.perception_connected = pp.client.has_completed_valid_call
            self.agent_state.perception_latency_ms = getattr(self.planner.client, "last_perception_latency_ms", None)
            self.agent_state.latest_semantic_observation = (
                getattr(self.planner.client, "last_semantic_observation", None) or pp.latest
            )
        else:
            self.agent_state.perception_model_provider = None
            self.agent_state.perception_model_name = "DISABLED(CV_ONLY)"
            self.agent_state.perception_connected = False
            self.agent_state.perception_latency_ms = 0.0
            self.agent_state.latest_semantic_observation = None
        self.agent_state.agent_model_provider = ap.client.provider_name
        self.agent_state.agent_model_name = ap.client.model
        self.agent_state.agent_connected = ap.client.has_completed_valid_call
        self.agent_state.agent_latency_ms = getattr(self.planner.client, "last_agent_latency_ms", None)
        last_bundle = getattr(self.planner.client, "last_evidence_bundle", None)
        if last_bundle is not None:
            self.agent_state.current_evidence_bundle_id = last_bundle.bundle_id
            self.agent_state.perception_provenance = last_bundle.provenance.model_dump(mode="json")
            self.agent_state.evidence_conflicts = list(last_bundle.detected_conflicts)
            self.agent_state.evidence_validity = last_bundle.validity.model_dump(mode="json")
            self.agent_state.semantic_provided_to_agent = bool(last_bundle.provenance.semantic_provided_to_agent)
        if self._active_decision_id is not None:
            self.agent_state.last_decision_id = self._active_decision_id

    def set_planner_mode(
        self,
        planner_mode: PlannerMode | str,
        *,
        model: str | None = None,
        context_mode: str = "vision_plus_structured_state",
        limits: VLMInspectionLimits | None = None,
        use_vlm_perception: bool = True,
        guide_mode: str = "GUIDE_FULL",
    ) -> dict[str, Any]:
        mode_enum = PlannerMode(planner_mode)

        def _do() -> dict[str, Any]:
            if self._running:
                return self.get_snapshot()
            if mode_enum == PlannerMode.LLM_AGENT:
                policy = LLMAgentDecisionPolicy(
                    limits=limits,
                    context_mode=context_mode,
                    guide_mode=guide_mode,
                    use_vlm_perception=use_vlm_perception,
                )
                if model:
                    policy.agent_provider.client.model = str(model)
                    policy.client.model = (
                        f"perception={policy.perception_provider.client.model};agent={policy.agent_provider.client.model}"
                        if policy.use_vlm_perception
                        else f"perception=NONE;agent={policy.agent_provider.client.model}"
                    )
                self.planner = policy
            else:
                self.planner = DeterministicMissionPlanner()
            self.agent_state = AgentObservabilityState(
                planner_mode=self.planner.mode,
                planner_name=self.planner.name,
                llm_connected=self.planner.llm_connected,
                llm_model=self.planner.llm_model,
                model_provider=getattr(self.planner, "model_provider", None),
                status_label=self.planner.status_label(),
                use_vlm_perception=(
                    bool(self.planner.use_vlm_perception)
                    if isinstance(self.planner, LLMAgentDecisionPolicy)
                    else None
                ),
                guide_mode=getattr(self.planner, "guide_mode", None),
            )
            self._sync_dual_model_agent_state()
            preview_mission = self._new_mission_object(self.selected_mission_type)
            self.mission = preview_mission
            self.plan = self.planner.create_plan(
                preview_mission,
                self.registry,
                plan_id=f"plan-{preview_mission.mission_id}",
            )
            self.mission.current_plan_id = self.plan.plan_id
            return self._emit_snapshot(refresh_frames=False)

        return self._run_on_gl_thread(_do)

    def build_agent_observation(self, *, camera_id: str = "overhead") -> AgentObservation:
        """Capture a live real MuJoCo RGB frame and assemble AgentObservation without leaking truth."""
        assert self._backend is not None
        frame = self._backend.capture_rgbd(camera_id)
        data_url = _encode_jpeg_data_url(frame.rgb, quality=86)
        img_sha = hashlib.sha256(data_url.encode("utf-8")).hexdigest()
        sim_t = self._sim_time()
        obs_id = f"obs-{uuid.uuid4().hex[:8]}"
        frame_id = frame.frame_id or f"frm-{uuid.uuid4().hex[:8]}"

        if self.observed_facelets_str and len(self.observed_facelets_str) == 54:
            unknown_indices = [idx for idx, ch in enumerate(self.observed_facelets_str) if ch == "?"]
        else:
            unknown_indices = list(range(54))
        observed_cnt = 54 - len(unknown_indices)

        self._current_obs_image_url = data_url
        self._current_obs_frame_id = frame_id
        self._current_obs_camera_id = camera_id
        self.scene_state["latest_sim_time"] = sim_t

        mission_id = self.mission.mission_id if self.mission else "preview"
        available_skills = [
            {
                "skill_id": desc.skill_id,
                "title": desc.title,
                "description": desc.description,
                "implemented": desc.implemented,
                "is_physical_action": desc.is_physical_action,
                "required_preconditions": list(desc.required_preconditions),
                "supported_parameters": dict(desc.supported_parameters),
            }
            for desc in self.registry.list_skills()
            if desc.skill_id != "active_six_face_scan"
        ]
        b = self._backend
        pose_est = getattr(b, "_active_pose_estimate", None) if b is not None else None
        pose_est_id = getattr(pose_est, "pose_estimate_id", None) if pose_est is not None else None
        cube_center = (
            list(self.last_observation_ref.cube_center_world_m)
            if self.last_observation_ref and self.last_observation_ref.cube_center_world_m is not None
            else None
        )
        cube_localized = bool(self.scene_state.get("cube_localized", False))
        pose_valid = bool(pose_est_id is not None or cube_center is not None or cube_localized)
        obs = AgentObservation(
            observation_id=obs_id,
            mission_id=mission_id,
            session_id=self.session_id,
            sim_time=sim_t,
            frame_id=frame_id,
            camera_id=camera_id,
            rgb_image_data_url=data_url,
            image_sha256=img_sha,
            camera_metadata={
                "fx": float(frame.calibration.fx),
                "fy": float(frame.calibration.fy),
                "cx": float(frame.calibration.cx),
                "cy": float(frame.calibration.cy),
                "width": self.width,
                "height": self.height,
                "frame_source": "REAL_MUJOCO_RENDERER",
                "pose_estimate_id": pose_est_id,
            },
            observed_facelets=self.observed_facelets_str,
            observed_count=observed_cnt,
            unknown_facelet_indices=unknown_indices,
            observation_conflicts=sorted(self.conflict_set),
            latest_skill_result=dict(self._last_skill_result) if self._last_skill_result else None,
            available_skill_descriptions=available_skills,
            capability_constraints={
                "physical_supported_moves": list(self.registry.snapshot().physical_supported_moves),
                "symbolic_supported_moves_count": 18,
                "limitations_summary": self.registry.snapshot().physical_limitations_summary,
            },
            context_mode=getattr(self.planner, "context_mode", "vision_plus_structured_state"),
            scene_summary={
                "cube_localized": cube_localized,
                "cube_detected": bool(cube_localized or observed_cnt > 0 or self.scene_state.get("cube_held_in_gripper", False)),
                "pose_valid": pose_valid,
                "rgbd_valid": pose_valid,
                "pose_estimate_id": pose_est_id,
                "cube_center_world_m": cube_center,
                "cube_released_on_table": bool(self.scene_state.get("cube_released_on_table", False)),
                "cube_held_in_gripper": bool(self.scene_state.get("cube_held_in_gripper", False)),
                "cube_state_validated": bool(self.scene_state.get("cube_state_validated", False)),
                "state_valid": bool(self.scene_state.get("cube_state_validated", False)),
                "validation_status": self.cube_validation_status,
            },
        )
        self._latest_agent_observation = obs
        obs_record = {
            "observation_id": obs_id,
            "frame_id": frame_id,
            "camera_ids": [camera_id],
            "frame_refs": [frame_id],
            "visual_summary": "M4-B real RGB input frame",
            "coverage": observed_cnt,
            "sim_time": sim_t,
            "image_url": data_url,
            "frame_source": "REAL_MUJOCO_RENDERER",
        }
        self._agent_observation_history.append(dict(obs_record))
        self._agent_observation_history = self._agent_observation_history[-32:]
        self._register_observation(obs_record)
        self.agent_state.current_observation_id = obs_id
        self.agent_state.current_frame_id = frame_id
        self.agent_state.current_camera_id = camera_id
        self.agent_state.current_observation_image_url = data_url
        if self.mission is not None and self._running:
            self._record_decision(
                event_type=DecisionEventType.OBSERVATION_CAPTURED,
                source="mujoco_renderer",
                summary=f"捕获真实 MuJoCo RGB 帧 {frame_id}",
                rationale="为独立 VLM Perception Provider 提供当前时刻视觉输入。",
                status="CAPTURED",
                observation_id=obs_id,
                input_frame_ids=[frame_id],
                output_reference=obs_id,
            )
        return obs

    def select_mission(
        self,
        mission_type: MissionType | str,
        *,
        scramble_steps: int | str | None = None,
    ) -> dict[str, Any]:
        mtype = MissionType(mission_type)
        if scramble_steps is not None:
            self.relay_scramble_steps = scramble_steps

        def _do() -> dict[str, Any]:
            if self._running:
                return self.get_snapshot()
            self.selected_mission_type = mtype
            if mtype == MissionType.RELAY_SOLVE_CUBE:
                if not self.full_26_cubie:
                    self._apply_full_26_cubie_sync(True)
                self._ensure_relay_agent_planner()
                self._maybe_apply_relay_closeup_camera()
                if scramble_steps is not None:
                    self._reset_backend_scene(self.seed)
            preview_mission = self._new_mission_object(mtype)
            self.mission = preview_mission
            self.plan = self.planner.create_plan(
                preview_mission,
                self.registry,
                plan_id=f"plan-{preview_mission.mission_id}",
            )
            self.mission.current_plan_id = self.plan.plan_id
            return self._emit_snapshot(refresh_frames=True if mtype == MissionType.RELAY_SOLVE_CUBE else False)
        return self._run_on_gl_thread(_do)

    def set_scramble_steps(self, scramble_steps: int | str) -> dict[str, Any]:
        if isinstance(scramble_steps, str) and scramble_steps.strip().lower() == "random":
            self.relay_scramble_steps = "random"
        else:
            steps_int = int(scramble_steps)
            if not (1 <= steps_int <= 25):
                raise ValueError(f"scramble_steps must be in 1..25 or 'random', got {scramble_steps!r}")
            self.relay_scramble_steps = steps_int

        def _do() -> dict[str, Any]:
            if not self._running and (self.mission is None or self.mission.status == MissionStatus.CREATED):
                self._reset_backend_scene(self.seed)
                return self._emit_snapshot(refresh_frames=True)
            return self._emit_snapshot(refresh_frames=False)

        return self._run_on_gl_thread(_do)

    def reset_scene(
        self,
        seed: int | None = None,
        mission_type: MissionType | str | None = None,
        *,
        perturbation: dict[str, Any] | None = None,
        full_26_cubie: bool | None = None,
        scramble_steps: int | str | None = None,
        scramble_moves: list[str] | None = None,
    ) -> dict[str, Any]:
        if mission_type is not None:
            self.selected_mission_type = MissionType(mission_type)
        if scramble_steps is not None:
            self.relay_scramble_steps = scramble_steps
        self._pending_relay_scramble_moves = list(scramble_moves) if scramble_moves else None
        if full_26_cubie is None and self.selected_mission_type == MissionType.RELAY_SOLVE_CUBE and not self.full_26_cubie:
            full_26_cubie = True
        target_seed = self.seed if seed is None else int(seed)
        self._stop_event.set()
        if self._active_cancellation_token is not None:
            self._active_cancellation_token.cancel("SCENE_RESET", mode=InterruptMode.IMMEDIATE_HOLD, sim_time_s=self._sim_time())

        def _do() -> dict[str, Any]:
            self._stop_event.clear()
            self.seed = target_seed
            rebuilt = self._apply_full_26_cubie_sync(full_26_cubie)
            if not rebuilt or perturbation is not None or scramble_steps is not None or scramble_moves is not None:
                self._reset_backend_scene(target_seed, perturbation=perturbation)
            if self.selected_mission_type == MissionType.RELAY_SOLVE_CUBE:
                self._ensure_relay_agent_planner()
            return self._emit_snapshot(refresh_frames=True)
        return self._run_on_gl_thread(_do)

    def _maybe_apply_relay_closeup_camera(self) -> None:
        """Auto-frame the cube cleanly in close-up for RELAY_SOLVE_CUBE unless user locked a preset."""
        if getattr(self, "_user_camera_locked", False):
            return
        if getattr(self, "active_camera", "overview") == "overview":
            spec = CAMERA_PRESET_SPECS["cube_closeup"]
            self.active_camera = "cube_closeup"
            self.camera_azimuth_deg = float(spec["az"])
            self.camera_elevation_deg = float(spec["el"])
            self.camera_distance_m = float(spec["dist"])

    def set_camera_preset(self, preset: str) -> dict[str, Any]:
        if preset not in CAMERA_PRESET_SPECS:
            return self.get_snapshot()
        spec = CAMERA_PRESET_SPECS[preset]
        self._user_camera_locked = True
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
        self.camera_distance_m = max(0.14, min(2.2, self.camera_distance_m + float(delta_distance)))
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
        if self._active_cancellation_token is not None:
            self._active_cancellation_token.cancel(
                "USER_STOP_REQUESTED",
                mode=InterruptMode.IMMEDIATE_HOLD,
                sim_time_s=self._sim_time(),
            )
        return self.get_snapshot()

    def urgent_interrupt(self, reason: str = "USER_URGENT_INTERRUPT") -> dict[str, Any]:
        """Thread-safe <5ms contract preemption triggering safe hold & StaleResponseGuard invalidation."""
        epoch = self._stale_guard.invalidate(reason)
        if self._active_cancellation_token is not None:
            self._active_cancellation_token.cancel(
                reason,
                mode=InterruptMode.IMMEDIATE_HOLD,
                sim_time_s=self._sim_time(),
            )
        with self._hri_lock:
            self._relay_paused_by_interrupt = True
            self._relay_auto_resume_after_pause = False
            self._relay_latest_human_reply = f"停（{reason}）"
            pause_note = "人类触发紧急刹车/打断，请确保晶格对齐后安全交回桌面等待人类指令。"
            if len(self._relay_active_constraints) >= 6:
                self._relay_active_constraints = self._relay_active_constraints[-5:]
            self._relay_active_constraints.append(pause_note)
        self._append_relay_dialog("human", f"⚡ 紧急刹车/中断：{reason}", topic="PREEMPT")
        self._record_decision(
            event_type=DecisionEventType.PREEMPTION_TRIGGERED,
            source="FastLoopContractWatchdog",
            summary=f"触发快环紧急抢占 ({reason})",
            rationale="收到人类实时打断指令：立刻保压刹停并使在途慢环决策失效。",
            status="PREEMPT_REQUESTED",
        )
        snap = self.get_snapshot()
        snap["preempt_dispatched_epoch"] = epoch
        return snap

    # ------------------------------------------------------------------
    # Human Relay Physical Controls & HRI Dialog (Zero Action/Pose Leakage)
    # ------------------------------------------------------------------

    def _assert_waiting_for_human(self) -> None:
        if self.mission is None or self.mission.status != MissionStatus.WAITING_FOR_HUMAN_TURN:
            raise RuntimeError(
                f"当前任务状态 ({self.mission.status.value if self.mission else 'NONE'}) 未处于等待人类接力回合 (WAITING_FOR_HUMAN_TURN)"
            )

    def human_apply_move(self, move: str) -> dict[str, Any]:
        mv = str(move).strip()
        if mv not in LEGAL_MOVES:
            raise ValueError(f"非法魔方动作 {mv!r}，必须属于 18 种标准符号之一")
        self._assert_waiting_for_human()

        def _do() -> dict[str, Any]:
            b = self._backend
            assert b is not None
            self._assert_waiting_for_human()
            # Stream intermediate 26-cubie rotation frames cleanly without updating robot tracker/scene_state
            res = b.human_apply_26_cubie_move(
                mv,
                duration_s=0.25,
                frame_callback=lambda _s, _tot: self._emit_snapshot(refresh_frames=True),
            )
            if not res.get("success"):
                raise RuntimeError(f"人类物理转层 {mv} 失败: {res.get('failure_reason') or res.get('failure_code')}")
            with self._hri_lock:
                self._human_private.moves_this_turn.append(mv)
                self._human_private.dirty_since_handover = True
                self._relay_clarification_pending = False
            self.scene_state["is_lattice_aligned"] = bool(res.get("is_lattice_aligned", True))
            self.scene_state["residual_slice_angle_deg"] = float(res.get("max_slice_misalignment_deg", 0.0))
            return self._emit_snapshot(refresh_frames=True)

        return self._run_on_gl_thread(_do)

    def human_undo_move(self) -> dict[str, Any]:
        self._assert_waiting_for_human()
        with self._hri_lock:
            if not self._human_private.moves_this_turn:
                raise ValueError("本回合尚未点击任何可撤销的人类动作")
            last_mv = self._human_private.moves_this_turn.pop()
        inv_mv = inverse_move(last_mv)

        def _do() -> dict[str, Any]:
            b = self._backend
            assert b is not None
            res = b.human_apply_26_cubie_move(
                inv_mv,
                duration_s=0.22,
                frame_callback=lambda _s, _tot: self._emit_snapshot(refresh_frames=True),
            )
            if not res.get("success"):
                with self._hri_lock:
                    self._human_private.moves_this_turn.append(last_mv)
                raise RuntimeError(f"撤销物理转层 {inv_mv} 失败: {res.get('failure_reason')}")
            return self._emit_snapshot(refresh_frames=True)

        return self._run_on_gl_thread(_do)

    def human_perturb_pose(self, dx_m: float = 0.0, dy_m: float = 0.0, dyaw_deg: float = 0.0) -> dict[str, Any]:
        self._assert_waiting_for_human()

        def _do() -> dict[str, Any]:
            b = self._backend
            assert b is not None
            self._assert_waiting_for_human()
            with self._hri_lock:
                base_xy = self._human_private.base_handover_xy
                base_quat = self._human_private.base_handover_quat
            res = b.human_perturb_26_cubie_pose(
                dx_m=float(dx_m),
                dy_m=float(dy_m),
                dyaw_deg=float(dyaw_deg),
                base_xy=base_xy,
                base_quat=base_quat,
                frame_callback=lambda: self._emit_snapshot(refresh_frames=True),
            )
            with self._hri_lock:
                self._human_private.applied_dx_m = float(res.get("applied_dx_m", 0.0))
                self._human_private.applied_dy_m = float(res.get("applied_dy_m", 0.0))
                self._human_private.applied_dyaw_deg = float(res.get("applied_dyaw_deg", 0.0))
                self._human_private.dirty_since_handover = True
            return self._emit_snapshot(refresh_frames=True)

        return self._run_on_gl_thread(_do)

    def _apply_hri_constraint_updates(self, semantics: HumanUtteranceSemantics) -> None:
        """Update persistent collaboration constraints cleanly without leaking transient pause phrases."""
        if semantics.constraints_to_clear:
            clear_targets = [c.strip() for c in semantics.constraints_to_clear if c.strip()]
            self._relay_active_constraints = [
                existing
                for existing in self._relay_active_constraints
                if not any(target == existing or target in existing for target in clear_targets)
            ]
        for item in semantics.persistent_constraints_to_add:
            c = item.strip()
            if c and c not in self._relay_active_constraints:
                self._relay_active_constraints.append(c)
        if len(self._relay_active_constraints) > 8:
            self._relay_active_constraints = self._relay_active_constraints[-8:]

    def human_send_chat(
        self,
        text: str,
        *,
        auto_resume: bool | None = None,
    ) -> dict[str, Any]:
        clean = str(text or "").strip()
        if not clean:
            raise ValueError("自然语言指令不能为空")

        token = self._active_cancellation_token if self._running else None
        pause = token is not None and not HRIDialogueInterpreter.is_reflex_estop(clean)
        if pause:
            with token.speculative_route():
                return self._route_human_chat(clean, auto_resume=auto_resume)
        return self._route_human_chat(clean, auto_resume=auto_resume)

    def _route_human_chat(self, clean: str, *, auto_resume: bool | None) -> dict[str, Any]:
        waiting_now = bool(self.mission is not None and self.mission.status == MissionStatus.WAITING_FOR_HUMAN_TURN)
        with self._hri_lock:
            was_clarification = bool(self._relay_clarification_pending)
            relay_phase_val = self._relay_phase.value if hasattr(self._relay_phase, "value") else str(self._relay_phase)
            recent_dialog = list(self._relay_human_dialog[-3:])
            active_constraints_snapshot = list(self._relay_active_constraints)
        current_action = getattr(getattr(self, "agent_state", None), "last_skill_call", None)

        semantics = self._get_hri_interpreter().interpret(
            clean,
            relay_phase=relay_phase_val,
            robot_running=bool(self._running),
            clarification_pending=was_clarification,
            current_action=current_action,
            recent_dialog=recent_dialog,
            active_constraints=active_constraints_snapshot,
        )
        sem_payload = semantics.model_dump(mode="json")
        is_pause_or_stop = semantics.speech_act in {"EMERGENCY_STOP", "PAUSE_AND_HANDOVER"}

        with self._hri_lock:
            self._relay_latest_human_reply = clean
            self._relay_latest_hri_semantics = sem_payload
            self._apply_hri_constraint_updates(semantics)
            if was_clarification and semantics.speech_act in {"ANSWER_CLARIFICATION", "YIELD_TURN_TO_ROBOT"}:
                self._relay_clarification_pending = False
            if self._running:
                if semantics.requires_immediate_motion_interrupt:
                    self._relay_paused_by_interrupt = True
                    self._relay_auto_resume_after_pause = False
                elif semantics.should_wake_robot_from_human_turn:
                    # Finish parking before consuming a continuation received in flight.
                    self._relay_auto_resume_after_pause = True
            elif is_pause_or_stop:
                self._relay_paused_by_interrupt = True
                self._relay_auto_resume_after_pause = False

        self._append_relay_dialog("human", clean, semantics=sem_payload)
        self._record_decision(
            event_type=DecisionEventType.HUMAN_CHAT_RECEIVED,
            source="HRIDialogueInterpreter",
            summary=f"人类指令 [{semantics.speech_act}]：{clean}",
            rationale=semantics.rationale_zh,
            status="INTERRUPT_REQUESTED" if semantics.requires_immediate_motion_interrupt else "RECEIVED",
            selected_action=semantics.speech_act,
            parameters={
                "speech_act": semantics.speech_act,
                "requires_immediate_motion_interrupt": semantics.requires_immediate_motion_interrupt,
                "should_wake_robot_from_human_turn": semantics.should_wake_robot_from_human_turn,
                "persistent_constraints_to_add": list(semantics.persistent_constraints_to_add),
                "constraints_to_clear": list(semantics.constraints_to_clear),
                "deviation_intent": semantics.deviation_intent,
                "provenance": semantics.provenance,
            },
            confidence=semantics.confidence,
            model_latency_ms=semantics.latency_ms,
            model_provider=semantics.provider_name,
            model_name=semantics.model_name,
        )

        # Mid-execution handling: ONLY interrupt robot motion when semantics.requires_immediate_motion_interrupt is True.
        if self._running:
            if not semantics.requires_immediate_motion_interrupt:
                return self.get_snapshot()
            self._stale_guard.invalidate(f"HUMAN_CHAT_INTERRUPT ({semantics.speech_act}): {clean[:60]}")
            contract = self._active_execution_contract
            if contract is None or contract.interrupt_on_human_chat_command:
                if self._active_cancellation_token is not None:
                    self._active_cancellation_token.cancel(
                        f"HUMAN_CHAT_INTERRUPT ({semantics.speech_act}): {clean[:80]}",
                        mode=InterruptMode.IMMEDIATE_HOLD,
                        sim_time_s=self._sim_time(),
                    )
                self._record_decision(
                    event_type=DecisionEventType.PREEMPTION_TRIGGERED,
                    source="FastLoopContractWatchdog",
                    summary=f"语义路由判定需立即中断 [{semantics.speech_act}]：{clean[:48]}",
                    rationale=f"{semantics.rationale_zh}（依据 ExecutionContract 立即刹停当前物理动作）。",
                    status="PREEMPT_REQUESTED",
                    model_latency_ms=semantics.latency_ms,
                )
            return self.get_snapshot()

        should_resume = (
            bool(
                semantics.should_wake_robot_from_human_turn
                or (was_clarification and semantics.speech_act == "ANSWER_CLARIFICATION")
            )
            if auto_resume is None
            else bool(auto_resume)
        )
        if waiting_now and should_resume:
            if self.use_dedicated_thread:
                ack = self.human_finish_turn_async()
                if isinstance(ack, dict) and isinstance(ack.get("snapshot"), dict):
                    return ack["snapshot"]
                return self.get_snapshot()
            return self.human_finish_turn()

        if self._subscribers:
            return self._emit_snapshot(refresh_frames=False)
        return self.get_snapshot()

    def _prepare_human_finish_turn(self, *, note: str | None = None) -> None:
        self._assert_waiting_for_human()
        if note:
            clean = str(note).strip()
            if clean:
                with self._hri_lock:
                    self._relay_latest_human_reply = clean
                    if clean not in self._relay_active_constraints:
                        self._relay_active_constraints.append(clean)
                self._append_relay_dialog("human", clean)

        with self._hri_lock:
            dirty = bool(
                self._human_private.dirty_since_handover
                or self._human_private.moves_this_turn
                or getattr(self, "_relay_paused_by_interrupt", False)
            )
            # Prune only system e-stop banner notes; persistent constraints extracted by HRIDialogueInterpreter stay intact.
            self._relay_active_constraints = [
                c
                for c in self._relay_active_constraints
                if "紧急刹车" not in c
            ]
            # Wipe private human click & perturbation truth BEFORE handing back to Agent!
            self._human_private.moves_this_turn.clear()
            self._human_private.applied_dx_m = 0.0
            self._human_private.applied_dy_m = 0.0
            self._human_private.applied_dyaw_deg = 0.0
            self._human_private.dirty_since_handover = False
            self._relay_paused_by_interrupt = False
            self._relay_auto_resume_after_pause = False
            self._relay_clarification_pending = False
            self._relay_human_turns_count += 1
            self._relay_phase = RelayPhase.AGENT_REASONING

        self._stale_guard.invalidate("HUMAN_FINISH_TURN")
        if dirty:
            # Force fresh RGB-D vision on robot turn (Zero Action/Pose Leakage)
            self.scene_state["needs_rescan"] = True
            self.scene_state["post_solve_independent_verified"] = False
            self.scene_state["cube_localized"] = False
            self.scene_state["cube_localized_and_scanned"] = False
            self.scene_state["cube_state_validated"] = False
        self._record_decision(
            event_type=DecisionEventType.HUMAN_TURN_FINISHED,
            source="HumanOperator",
            summary="人类完成桌面接力回合，交回 Agent 视觉重扫与决策",
            rationale="重置机器人局部定位先验为待视觉重扫 (needs_rescan=True)，严禁泄露人类操作真值。",
            status="HANDED_BACK",
        )

    def human_finish_turn_async(self, *, note: str | None = None) -> dict[str, Any]:
        if self._executor is None:
            return self.human_finish_turn(note=note)
        if self._running:
            return {"accepted": False, "reason": "mission_already_running", "snapshot": self.get_snapshot()}
        self._prepare_human_finish_turn(note=note)
        self._executor.submit(self._resume_relay_sync_impl)
        return {"accepted": True, "resumed": True, "snapshot": self.get_snapshot()}

    def human_finish_turn(self, *, note: str | None = None) -> dict[str, Any]:
        self._prepare_human_finish_turn(note=note)
        return self._run_on_gl_thread(self._resume_relay_sync_impl)

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
        perturbation: dict[str, Any] | None = None,
        full_26_cubie: bool | None = None,
        scramble_steps: int | str | None = None,
        scramble_moves: list[str] | None = None,
    ) -> dict[str, Any]:
        mtype = MissionType(mission_type)
        if scramble_steps is not None:
            self.relay_scramble_steps = scramble_steps
        self._pending_relay_scramble_moves = list(scramble_moves) if scramble_moves else None
        eff_full26 = True if (full_26_cubie is None and mtype == MissionType.RELAY_SOLVE_CUBE) else full_26_cubie
        if mtype == MissionType.RELAY_SOLVE_CUBE:
            self._maybe_apply_relay_closeup_camera()
        if self._executor is None:
            return self.run_mission(
                mtype,
                seed=seed,
                perturbation=perturbation,
                full_26_cubie=eff_full26,
                scramble_steps=scramble_steps,
                scramble_moves=scramble_moves,
            )
        if self._running:
            return {"accepted": False, "reason": "mission_already_running", "snapshot": self.get_snapshot()}
        self._executor.submit(
            self._run_mission_sync,
            mtype,
            seed,
            perturbation,
            full_26_cubie=eff_full26,
        )
        return {
            "accepted": True,
            "mission_type": mtype.value,
            "seed": self.seed if seed is None else int(seed),
            "full_26_cubie": self.full_26_cubie if eff_full26 is None else bool(eff_full26),
        }

    def run_mission(
        self,
        mission_type: MissionType | str,
        *,
        seed: int | None = None,
        perturbation: dict[str, Any] | None = None,
        reset_before_run: bool = True,
        full_26_cubie: bool | None = None,
        scramble_steps: int | str | None = None,
        scramble_moves: list[str] | None = None,
    ) -> dict[str, Any]:
        mtype = MissionType(mission_type)
        if scramble_steps is not None:
            self.relay_scramble_steps = scramble_steps
        self._pending_relay_scramble_moves = list(scramble_moves) if scramble_moves else None
        eff_full26 = True if (full_26_cubie is None and mtype == MissionType.RELAY_SOLVE_CUBE) else full_26_cubie
        if mtype == MissionType.RELAY_SOLVE_CUBE:
            self._maybe_apply_relay_closeup_camera()
        return self._run_on_gl_thread(
            lambda: self._run_mission_sync(
                mtype,
                seed,
                perturbation,
                reset_before_run=reset_before_run,
                full_26_cubie=eff_full26,
            )
        )

    def _sim_time(self) -> float:
        return round(float(self._backend.data.time), 4) if self._backend is not None else 0.0

    def _planner_event_source(self, *, fallback_used: bool = False) -> str:
        if fallback_used:
            return "deterministic_policy"
        if isinstance(self.planner, LLMAgentDecisionPolicy):
            return "llm_agent_planner"
        if self.planner.mode == PlannerMode.LLM_AGENT:
            return "gemini_vlm"
        return "deterministic_policy"

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
        planner_mode: str | None = None,
        model_provider: str | None = None,
        model_name: str | None = None,
        observation_id: str | None = None,
        input_frame_ids: list[str] | None = None,
        action_candidates: list[str] | None = None,
        parameters: dict[str, Any] | None = None,
        expected_information_gain: str | None = None,
        confidence: float | None = None,
        validation_result: str | None = None,
        skill_execution_id: str | None = None,
        feedback_observation_id: str | None = None,
        model_latency_ms: float | None = None,
        token_usage: dict[str, Any] | None = None,
        decision_id: str | None = None,
        evidence_bundle_id: str | None = None,
        request_id: str | None = None,
        prompt_sha256: str | None = None,
        perception_provenance: dict[str, Any] | None = None,
        evidence_conflicts: list[str] | None = None,
        evidence_validity: dict[str, Any] | None = None,
        semantic_provided_to_agent: bool | None = None,
    ) -> DecisionEvent:
        assert self.mission is not None
        ev = self.event_log.append(
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
            planner_mode=planner_mode or self.planner.mode.value,
            model_provider=model_provider if model_provider is not None else getattr(self.planner, "model_provider", None),
            model_name=model_name if model_name is not None else self.planner.llm_model,
            observation_id=observation_id,
            input_frame_ids=input_frame_ids,
            action_candidates=action_candidates,
            parameters=parameters,
            expected_information_gain=expected_information_gain,
            confidence=confidence,
            validation_result=validation_result,
            skill_execution_id=skill_execution_id,
            feedback_observation_id=feedback_observation_id,
            model_latency_ms=model_latency_ms,
            token_usage=token_usage,
            decision_id=decision_id,
            evidence_bundle_id=evidence_bundle_id,
            request_id=request_id,
            prompt_sha256=prompt_sha256,
            perception_provenance=perception_provenance,
            evidence_conflicts=evidence_conflicts,
            evidence_validity=evidence_validity,
            semantic_provided_to_agent=semantic_provided_to_agent,
        )
        self._record_timeline_from_decision(ev)
        if self._current_run is not None:
            self._current_run.events.record_decision_event(ev.model_dump(mode="json"))
        return ev

    def _record_dual_model_phase(self, phase: str, payload: dict[str, Any]) -> None:
        """Persist dual-model phases at the instant each provider starts/completes."""
        if self.mission is None:
            return
        event_type = DecisionEventType(phase)
        is_perception = phase.startswith("VLM_")
        is_completed = phase.endswith("COMPLETED")
        model = str(payload.get("model") or "")
        source = "vlm_perception" if is_perception else "llm_agent_planner"
        summary = (
            f"VLM 感知{'完成' if is_completed else '开始'} ({model})"
            if is_perception
            else f"Agent 决策{'完成' if is_completed else '开始'} ({model})"
        )
        token_usage = None
        if payload.get("input_tokens") is not None or payload.get("output_tokens") is not None:
            token_usage = {
                "input_tokens": int(payload.get("input_tokens") or 0),
                "output_tokens": int(payload.get("output_tokens") or 0),
            }
        self._record_decision(
            event_type=event_type,
            source=source,
            summary=summary,
            rationale=(
                (payload.get("semantic") or {}).get("summary", "视觉语义推理")
                if is_perception
                else (payload.get("decision") or {}).get("reason_summary", "任务规划推理")
            ),
            status="COMPLETED" if is_completed and not payload.get("error_code") else ("FAILED" if payload.get("error_code") else "STARTED"),
            observation_id=payload.get("observation_id"),
            input_frame_ids=[payload["frame_id"]] if payload.get("frame_id") else None,
            model_provider=payload.get("provider"),
            model_name=model,
            selected_action=(payload.get("decision") or {}).get("skill_id"),
            parameters=(payload.get("decision") or {}).get("parameters"),
            confidence=(payload.get("decision") or payload.get("semantic") or {}).get("confidence"),
            model_latency_ms=payload.get("latency_ms"),
            token_usage=token_usage,
            failure_reason=payload.get("error_code"),
            evidence_bundle_id=payload.get("evidence_bundle_id"),
            request_id=payload.get("request_id"),
            evidence_conflicts=list(payload.get("detected_conflicts") or []),
            semantic_provided_to_agent=payload.get("semantic_provided_to_agent"),
        )
        if phase == "VLM_INFERENCE_COMPLETED" and payload.get("semantic"):
            semantic = payload["semantic"]
            self._record_decision(
                event_type=DecisionEventType.PERCEPTION_UPDATED,
                source="perception_fusion",
                summary="融合 VLM 场景语义与传统 CV 观测（保留独立来源）",
                rationale=str(semantic.get("summary") or ""),
                status="UPDATED",
                observation_id=payload.get("observation_id"),
                input_frame_ids=[payload["frame_id"]] if payload.get("frame_id") else None,
                model_provider=payload.get("provider"),
                model_name=model,
                confidence=semantic.get("confidence"),
                request_id=payload.get("request_id"),
                evidence_bundle_id=payload.get("evidence_bundle_id"),
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
        tev = self.trace_log.append(
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
        if self._current_run is not None:
            self._current_run.events.record_trace_event(tev.model_dump(mode="json"))
        if event_type == TraceEventType.PERCEPTION:
            self._register_observation({
                "observation_id": evidence.get("observation_id"),
                "frame_id": evidence.get("frame_id"),
                "camera_ids": evidence.get("camera_ids", []),
                "frame_refs": evidence.get("frame_refs", []),
                "visual_summary": evidence.get("visual_summary", ""),
                "coverage": evidence.get("coverage_after", 0),
                "sim_time": tev.end_sim_time if tev.end_sim_time is not None else tev.sim_time,
                "frame_source": "REAL_MUJOCO_RENDERER",
            })
        # This lightweight snapshot streams the event while the composite is
        # still running. It deliberately reuses cached images and does not
        # introduce another EGL render into the physics loop.
        self._emit_snapshot(refresh_frames=False)

    def _ensure_vlm_scan_composite_trace(self) -> str:
        assert self.mission is not None
        if self._active_composite_trace_event_id is None:
            composite = self.trace_log.append(
                mission_id=self.mission.mission_id,
                session_id=self.session_id,
                parent_event_id=self._mission_trace_event_id,
                skill_id="vlm_controlled_inspection",
                event_type=TraceEventType.COMPOSITE_SKILL,
                name="vlm_controlled_inspection",
                source=self._planner_event_source(),
                status="RUNNING",
                sim_time=self._sim_time(),
                evidence={"mode": "vlm_controlled", "live": True},
            )
            if self._current_run is not None:
                self._current_run.events.record_trace_event(composite.model_dump(mode="json"))
            self._active_composite_trace_event_id = composite.event_id
        return self._active_composite_trace_event_id

    def _emit_mode_b_action_trace(
        self,
        *,
        name: str,
        skill_id: str,
        success: bool,
        start_sim: float,
        evidence: dict[str, Any],
        failure_reason: str | None = None,
    ) -> None:
        assert self.mission is not None
        parent_id = self._ensure_vlm_scan_composite_trace()
        tev = self.trace_log.append(
            mission_id=self.mission.mission_id,
            session_id=self.session_id,
            parent_event_id=parent_id,
            skill_id=skill_id,
            event_type=TraceEventType.ACTION,
            name=name,
            source="physical_skill",
            status="COMPLETED" if success else "FAILED",
            sim_time=start_sim,
            end_sim_time=self._sim_time(),
            evidence=evidence,
            failure_reason=failure_reason,
        )
        if self._current_run is not None:
            self._current_run.events.record_trace_event(tev.model_dump(mode="json"))

    def _fuse_mode_b_observations(
        self,
        observations: list[Any],
        *,
        trace_name: str,
        skill_id: str,
        camera_id_label: str,
        start_sim: float,
    ) -> tuple[int, int, int, str, str]:
        assert self.mission is not None
        before_items = self._scan_fusion.fused_evidence()
        before = {(item.face, item.index): item.color for item in before_items}
        unknown_before = self._scan_fusion.unknown_count
        known = {key for key, color in before.items() if color is not None}
        camera_contributions: dict[str, list[int]] = {}
        for observation in observations:
            source_parts = str(observation.source_view).split(":")
            camera = source_parts[1] if len(source_parts) > 1 else source_parts[0]
            contribution = camera_contributions.setdefault(camera, [])
            for index, color in enumerate(observation.stickers):
                key = (observation.face, index)
                if color is not None and key not in known:
                    canonical_index = FACE_ORDER.index(observation.face) * 9 + index
                    contribution.append(canonical_index)
                    known.add(key)
        for observation in observations:
            self._scan_fusion.add(observation)
        after_items = self._scan_fusion.fused_evidence()
        newly_observed_indices = sorted(
            FACE_ORDER.index(item.face) * 9 + item.index
            for item in after_items
            if before[(item.face, item.index)] is None and item.color is not None
        )
        newly_observed = len(newly_observed_indices)
        unknown_after = self._scan_fusion.unknown_count
        conflict_after = self._scan_fusion.conflict_count
        self.conflict_set = set(self._scan_fusion.conflicting_indices)
        if unknown_after == 0:
            self.observed_facelets_str = self._scan_fusion.facelets()
        else:
            self.observed_facelets_str = "".join(item.color or "?" for item in after_items)

        self.scene_state["scan_attempted"] = True
        self.scene_state["all_54_facelets_observed"] = (unknown_after == 0 and conflict_after == 0)

        self._scan_obs_seq += 1
        obs_id = f"obs-{uuid.uuid4().hex[:8]}"
        frame_id = f"frm-{uuid.uuid4().hex[:8]}"
        camera_ids = list(camera_contributions)
        frame_refs = [f"frame:{obs_id}:{camera}" for camera in camera_ids]

        frame_images: list[dict[str, str]] = []
        debug_frames = list(getattr(self._backend, "debug_observation_frames", []))
        for camera_id, frame_ref in zip(camera_ids, frame_refs):
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

        observed_cnt = 54 - unknown_after
        obs_ref = ObservationReference(
            observation_id=obs_id,
            frame_id=frame_id,
            sim_time=self._sim_time(),
            camera_name=camera_id_label,
            observed_count=observed_cnt,
            unknown_count=unknown_after,
            conflict_count=conflict_after,
            validation_status="UNVERIFIED" if unknown_after else "CANDIDATE_COMPLETE",
            reconstructed_facelets=self.observed_facelets_str,
            cube_center_world_m=self.last_observation_ref.cube_center_world_m if self.last_observation_ref else None,
            summary=(
                f"{trace_name}: 新增 {newly_observed} 格，已观测 {observed_cnt}/54，"
                f"unknown {unknown_before} → {unknown_after}"
            ),
        )
        self.last_observation_ref = obs_ref

        parent_id = self._ensure_vlm_scan_composite_trace()
        tev = self.trace_log.append(
            mission_id=self.mission.mission_id,
            session_id=self.session_id,
            parent_event_id=parent_id,
            skill_id=skill_id,
            event_type=TraceEventType.PERCEPTION,
            name=trace_name,
            source="camera_perception",
            status="COMPLETED" if observations else "FAILED",
            sim_time=start_sim,
            end_sim_time=self._sim_time(),
            evidence={
                "observation_id": obs_id,
                "frame_id": frame_id,
                "camera_ids": camera_ids,
                "camera_contributions": camera_contributions,
                "frame_refs": frame_refs,
                "frame_images": frame_images,
                "newly_observed": newly_observed,
                "newly_observed_facelet_indices": newly_observed_indices,
                "coverage_before": 54 - unknown_before,
                "coverage_after": observed_cnt,
                "unknown_before": unknown_before,
                "unknown_after": unknown_after,
                "conflicts": conflict_after,
                "conflicting_indices": sorted(self.conflict_set),
                "visual_summary": (
                    f"{len(camera_ids)} cameras added {newly_observed} unique canonical facelets; "
                    f"unknown {unknown_before} -> {unknown_after}"
                ),
            },
            failure_reason=None if observations else "NO_VALID_OBSERVATIONS",
        )
        if self._current_run is not None:
            self._current_run.events.record_trace_event(tev.model_dump(mode="json"))
        self._register_observation({
            "observation_id": obs_id,
            "frame_id": frame_id,
            "camera_ids": camera_ids,
            "frame_refs": frame_refs,
            "visual_summary": tev.evidence.get("visual_summary", ""),
            "coverage": observed_cnt,
            "unknown_after": unknown_after,
            "conflicts": conflict_after,
            "sim_time": tev.end_sim_time if tev.end_sim_time is not None else tev.sim_time,
            "frame_source": "REAL_MUJOCO_RENDERER",
        })
        self._record_decision(
            event_type=DecisionEventType.OBSERVATION_RECEIVED,
            source="SixFacePerception",
            summary=obs_ref.summary,
            rationale=f"多相机感知新增 {newly_observed} 个规范贴片，剩余 unknown={unknown_after}。",
            status="OBSERVED" if observations else "NO_OBSERVATION",
            skill_id=skill_id,
            output_reference=obs_id,
            observation_id=obs_id,
            input_frame_ids=frame_refs,
        )
        return newly_observed, unknown_before, unknown_after, obs_id, frame_id

    def _fail_mission_with_reason(
        self,
        *,
        mission: MissionState,
        failure_code: str,
        summary: str,
        rationale: str,
        source: str,
        skill_id: str | None = None,
        agent_obs: AgentObservation | None = None,
        decision: Any = None,
    ) -> None:
        mission.status = MissionStatus.FAILED
        mission.completed_at = now_wall_time()
        mission.failure_reason = failure_code
        mission.result_summary = summary
        self.agent_state.blocked_or_replan_reason = rationale
        if decision is not None and getattr(decision, "validation_result", None):
            self.agent_state.safety_gate_status = decision.validation_result
            self.agent_state.safety_gate_detail = rationale
        self._record_decision(
            event_type=DecisionEventType.MISSION_FAILED,
            source=source,
            summary=summary,
            rationale=rationale,
            status=MissionStatus.FAILED.value,
            skill_id=skill_id,
            input_reference=agent_obs.observation_id if agent_obs else None,
            failure_reason=failure_code,
            observation_id=agent_obs.observation_id if agent_obs else None,
            input_frame_ids=[agent_obs.frame_id] if agent_obs else None,
            action_candidates=list(decision.action_candidates) if decision is not None else None,
            parameters=dict(decision.parameters) if decision is not None else None,
            expected_information_gain=getattr(decision, "expected_information_gain", None),
            confidence=getattr(decision, "confidence", None),
            validation_result=getattr(decision, "validation_result", None) or f"FAILED:{failure_code}",
            model_latency_ms=getattr(decision, "model_latency_ms", None),
            token_usage=getattr(decision, "token_usage", None),
            decision_id=getattr(decision, "decision_id", None) or self._active_decision_id,
            evidence_bundle_id=getattr(decision, "evidence_bundle_id", None) or self._active_evidence_bundle_id,
            request_id=getattr(decision, "request_id", None) or self._active_request_id,
            prompt_sha256=getattr(decision, "prompt_sha256", None) or self._active_prompt_sha256,
            perception_provenance=(
                dict(getattr(decision, "perception_provenance", None) or {})
                or dict(self._active_perception_provenance)
            ),
            evidence_conflicts=(
                list(getattr(decision, "evidence_conflicts", None) or ())
                or list(self._active_evidence_conflicts)
            ),
            evidence_validity=(
                dict(getattr(decision, "evidence_validity", None) or {})
                or dict(self._active_evidence_validity)
            ),
            semantic_provided_to_agent=(
                getattr(decision, "semantic_provided_to_agent", None)
                if getattr(decision, "semantic_provided_to_agent", None) is not None
                else self._active_semantic_provided
            ),
        )
        self._emit_snapshot(refresh_frames=True)

    def _run_mission_sync(
        self,
        mission_type: MissionType,
        seed: int | None,
        perturbation: dict[str, Any] | None = None,
        *,
        reset_before_run: bool = True,
        full_26_cubie: bool | None = None,
    ) -> dict[str, Any]:
        target_seed = self.seed if seed is None else int(seed)
        mission_wall_started = time.perf_counter()
        self._stop_event.clear()
        self._running = True
        run: ExperimentRun | None = None
        mission: MissionState | None = None
        try:
            self.selected_mission_type = mission_type
            if mission_type == MissionType.RELAY_SOLVE_CUBE:
                if not self.full_26_cubie:
                    eff_flag = True if full_26_cubie is None else bool(full_26_cubie)
                    full_26_cubie = eff_flag
                self._ensure_relay_agent_planner()
            pert_meta: dict[str, Any] | None = None
            if full_26_cubie is not None and bool(full_26_cubie) != self.full_26_cubie:
                if reset_before_run:
                    self.seed = target_seed
                rebuilt = self._apply_full_26_cubie_sync(full_26_cubie)
                if reset_before_run:
                    if perturbation is not None or not rebuilt:
                        pert_meta = self._reset_backend_scene(target_seed, perturbation=perturbation)
                    self._lock_backend_anti_cheat()
            elif reset_before_run:
                pert_meta = self._reset_backend_scene(target_seed, perturbation=perturbation)
                self._lock_backend_anti_cheat()
            else:
                if self._current_run is not None:
                    self._current_run.close()
                    self._current_run = None
                self._vlm_decision_rounds = 0
                self._vlm_observe_calls = 0
                self._vlm_reorient_calls = 0
                self._vlm_calls_count = 0
                self._total_vlm_latency_ms = 0.0
                self._total_input_tokens = 0
                self._total_output_tokens = 0
                self._total_reasoning_tokens = 0
                self._skill_duration_sim_s = 0.0
                self._total_execution_wall_s = 0.0
                self._active_composite_trace_event_id = None
                self.agent_state = AgentObservabilityState(
                    planner_mode=self.planner.mode,
                    planner_name=self.planner.name,
                    llm_connected=self.planner.llm_connected,
                    llm_model=self.planner.llm_model,
                    model_provider=getattr(self.planner, "model_provider", None),
                    status_label=self.planner.status_label(),
                    latest_observation=self.last_observation_ref,
                )
                self._sync_dual_model_agent_state()

            self._relay_mission_wall_started = mission_wall_started
            if mission_type == MissionType.RELAY_SOLVE_CUBE:
                self._relay_phase = RelayPhase.AGENT_REASONING
                self._relay_round_number = 1
                self._relay_round_tags = []

            mission = self._new_mission_object(mission_type)
            self.mission = mission
            self.plan = None
            self.skill_executions.clear()
            self.event_log.clear()
            self.trace_log.clear()
            self._timeline_events.clear()
            self._recorded_observations.clear()
            self._evidence_bundles.clear()
            self._active_decision_id = None
            self._active_evidence_bundle_id = None
            self._active_request_id = None
            self._active_prompt_sha256 = None
            self._active_perception_provenance = {}
            self._active_evidence_conflicts = []
            self._active_evidence_validity = {}
            self._active_semantic_provided = None

            pert_cfg = dict(perturbation or {})
            if pert_meta is not None:
                pert_cfg["perturbation_metadata"] = pert_meta
            run = self.experiment_recorder.start_run(
                session_id=self.session_id,
                seed=target_seed,
                mission_type=mission_type.value,
                planner_mode=self.planner.mode.value,
                trajectory_sample_hz=self.trajectory_sample_hz,
                include_audit_ground_truth=self.include_audit_ground_truth,
                perturbation=pert_cfg,
                scene_xml_path=str(getattr(self._backend, "model_path", "")),
            )
            run.mission_id = mission.mission_id
            self._current_run = run
            self._backend.experiment_run = run
            self._backend._active_mission_id = mission.mission_id
            if self.include_audit_ground_truth:
                run.trajectories.record_audit_pose(self._backend, phase="INIT_SETTLED")

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
            run.events.record_trace_event(mission_trace.model_dump(mode="json"))
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
                source=self._planner_event_source(),
                summary=(
                    f"初始化 VLM 闭环动态规划 ({self.planner.llm_model or 'unconfigured'})"
                    if self.planner.mode == PlannerMode.LLM_AGENT
                    else f"生成 {len(plan.steps)} 步任务计划 ({', '.join(s.skill_id for s in plan.steps)})"
                ),
                rationale=plan.rationale_summary,
                status="PLAN_READY",
                selected_action=plan.steps[0].skill_id if plan.steps else None,
                output_reference=plan.plan_id,
            )
            self._emit_snapshot(refresh_frames=True)
            self._execute_mission_segment_sync(mission, plan, run, mission_wall_started)
        finally:
            self._running = False

        return self._finalize_mission_run(run, perturbation=perturbation)

    def _resume_relay_sync_impl(self) -> dict[str, Any]:
        mission = self.mission
        plan = self.plan
        if mission is None or plan is None:
            raise RuntimeError("No active relay mission to resume")
        self._stop_event.clear()
        self._running = True
        with self._hri_lock:
            self._relay_round_number += 1
            self._relay_phase = RelayPhase.AGENT_REASONING
        run = self._current_run
        mission_wall_started = self._relay_mission_wall_started or time.perf_counter()
        try:
            self._execute_mission_segment_sync(mission, plan, run, mission_wall_started)
        finally:
            self._running = False
        return self._finalize_mission_run(run, perturbation=self._pending_perturbation)

    def _finalize_mission_run(
        self,
        run: ExperimentRun | None,
        *,
        perturbation: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        if self.mission is not None and self.mission.status == MissionStatus.WAITING_FOR_HUMAN_TURN:
            return self._emit_snapshot(refresh_frames=False)

        if self._mission_trace_event_id is not None and self.mission is not None:
            final_status = self.mission.status.value
            self.trace_log.finish(
                self._mission_trace_event_id,
                status=final_status,
                end_sim_time=self._sim_time(),
                evidence={
                    "result_summary": self.mission.result_summary,
                    "vlm_calls": self._vlm_calls_count,
                    "total_execution_wall_s": self._total_execution_wall_s,
                    "skill_duration_sim_s": round(self._skill_duration_sim_s, 4),
                },
                failure_reason=self.mission.failure_reason,
            )
        final_snap = self._emit_snapshot(refresh_frames=False)
        if run is not None:
            self._sync_run_artifacts()
            run.set_snapshot(final_snap)
            mission_status = self.mission.status.value if self.mission is not None else "UNKNOWN"
            metrics_payload = {
                "mission_status": mission_status,
                "failure_reason": self.mission.failure_reason if self.mission is not None else None,
                "timing_metrics": final_snap.get("timing_metrics", {}),
                "physical_verification": self.physical_verification,
                "counts": (final_snap.get("experiment_recording") or {}).get("counts", {}),
                "perturbation": dict(perturbation or {}),
            }
            run.finalize(
                metrics=metrics_payload,
                status="FINALIZED" if mission_status == MissionStatus.COMPLETED.value else mission_status,
            )
            final_snap = self._emit_snapshot(refresh_frames=False)
        return final_snap

    def _execute_mission_segment_sync(
        self,
        mission: MissionState,
        plan: PlanState,
        run: ExperimentRun | None,
        mission_wall_started: float,
    ) -> None:
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
                self._last_stream_wall = time.monotonic()
                self._last_stream_sim = self._sim_time()

        if (
            self.stream_interval_sec > 0
            and self.stream_sim_interval_sec > 0
            and (self._subscribers or self.record_video_frames)
        ):
            b.step_physics = _streaming_step_physics

        if mission.mission_type == MissionType.RELAY_SOLVE_CUBE:
            self._active_cancellation_token = b.active_cancellation_token = CancellationToken()

        try:
            while True:
                if self._stop_event.is_set():
                    mission.status = MissionStatus.CANCELLED
                    mission.completed_at = now_wall_time()
                    mission.failure_reason = "USER_STOP_REQUESTED"
                    mission.result_summary = "用户主动安全停止当前任务。"
                    if mission.mission_type == MissionType.RELAY_SOLVE_CUBE:
                        self._relay_phase = RelayPhase.FAILED
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

                decision_epoch = self._stale_guard.issue_epoch()
                limits: VLMInspectionLimits | None = getattr(self.planner, "limits", None)
                agent_obs: AgentObservation | None = None
                parking_for_interrupt = False
                if mission.mission_type == MissionType.RELAY_SOLVE_CUBE:
                    self._relay_phase = RelayPhase.AGENT_REASONING
                    context = self._refresh_relay_cognitive_context()
                    parking_for_interrupt = context["hri_context"]["paused_by_interrupt"]
                    # A stop during inference has no executing skill to retire its token.
                    # Recovery and parking must be independently interruptible.
                    token = self._active_cancellation_token
                    if parking_for_interrupt and token is not None and token.is_cancelled():
                        self._active_cancellation_token = b.active_cancellation_token = CancellationToken()
                    # Automatic anomaly VLM awakening if CV localization failed or sticker conflict occurred
                    if (
                        len(self.conflict_set) > 0
                        or (
                            self._last_skill_result
                            and not self._last_skill_result.get("success", True)
                            and self._last_skill_result.get("failure_code")
                            in {"CUBE_NOT_LOCALIZED", "RAPID_LOCALIZATION_FAILED", "VISUAL_LOCALIZATION_FAILED"}
                        )
                    ):
                        self.scene_state["vlm_awakening_requested"] = True

                if self.planner.mode == PlannerMode.LLM_AGENT:
                    if limits is not None:
                        if not parking_for_interrupt and self._vlm_decision_rounds >= limits.max_decision_rounds:
                            self._relay_phase = RelayPhase.FAILED if mission.mission_type == MissionType.RELAY_SOLVE_CUBE else self._relay_phase
                            self._fail_mission_with_reason(
                                mission=mission,
                                failure_code="MAX_DECISION_ROUNDS_EXCEEDED",
                                summary=f"超过最大决策轮数限制 ({limits.max_decision_rounds})，安全中止任务。",
                                rationale="执行层确定性限制触发：VLM 决策轮数耗尽。",
                                source="MissionController",
                            )
                            break
                        if not parking_for_interrupt and self._vlm_calls_count >= limits.max_vlm_calls:
                            self._relay_phase = RelayPhase.FAILED if mission.mission_type == MissionType.RELAY_SOLVE_CUBE else self._relay_phase
                            self._fail_mission_with_reason(
                                mission=mission,
                                failure_code="MAX_VLM_CALLS_EXCEEDED",
                                summary=f"超过最大在线模型调用次数限制 ({limits.max_vlm_calls})，安全中止任务。",
                                rationale="执行层确定性限制触发：VLM 调用次数上限已达。",
                                source="MissionController",
                            )
                            break
                        if self._sim_time() > limits.max_sim_time_sec:
                            self._relay_phase = RelayPhase.FAILED if mission.mission_type == MissionType.RELAY_SOLVE_CUBE else self._relay_phase
                            self._fail_mission_with_reason(
                                mission=mission,
                                failure_code="MAX_SIM_TIME_EXCEEDED",
                                summary=f"超过最大仿真时间限制 ({limits.max_sim_time_sec:.1f}s)，安全中止任务。",
                                rationale="执行层确定性限制触发：仿真时间超限。",
                                source="MissionController",
                            )
                            break

                    agent_obs = self.build_agent_observation(camera_id="overhead")
                    self.scene_state["observation_history"] = [
                        {
                            "observation_id": row.get("observation_id"),
                            "frame_id": row.get("frame_id"),
                            "sim_time": row.get("sim_time"),
                            "coverage": row.get("coverage"),
                            "unknown_after": row.get("unknown_after"),
                            "conflicts": row.get("conflicts"),
                            "visual_summary": row.get("visual_summary"),
                        }
                        for row in self._recorded_observations[-10:]
                    ]
                    self.scene_state["failure_feedback"] = (
                        dict(self._last_skill_result)
                        if self._last_skill_result and not self._last_skill_result.get("success", True)
                        else None
                    )
                    self._emit_snapshot(refresh_frames=False)

                # Simulation stepping is paused while awaiting Gemini VLM inference.
                sim_before_policy = self._sim_time()
                dual_client = getattr(self.planner, "client", None)
                if hasattr(dual_client, "event_callback"):
                    dual_client.event_callback = self._record_dual_model_phase
                decision = self.planner.select_next_action(
                    mission,
                    plan,
                    self.registry,
                    self.scene_state,
                    self.last_observation_ref,
                    agent_observation=agent_obs,
                )
                sim_after_policy = self._sim_time()
                assert abs(sim_after_policy - sim_before_policy) < 1e-9, (
                    "Physics sim_time must remain paused during VLM inference"
                )
                if mission.mission_type == MissionType.RELAY_SOLVE_CUBE and self.scene_state.get("vlm_awakening_requested"):
                    self.scene_state["vlm_awakening_requested"] = False
                    if getattr(decision, "semantic_provided_to_agent", False):
                        self._relay_cognitive_stats["on_demand_vlm_calls"] += 1

                if mission.mission_type == MissionType.RELAY_SOLVE_CUBE and not self._stale_guard.accept(decision_epoch):
                    self._relay_cognitive_stats["stale_responses_discarded"] = int(
                        self._stale_guard.stale_responses_discarded
                    )
                    self._record_decision(
                        event_type=DecisionEventType.STALE_RESPONSE_DISCARDED,
                        source="StaleResponseGuard",
                        summary=f"拦截并丢弃过期慢环决策 (epoch={decision_epoch} < {self._stale_guard.current_epoch})",
                        rationale=f"推理期间收到新的人类指令或抢占信号 ({self._stale_guard.last_invalidation_reason})，禁止执行过期决策。",
                        status="DISCARDED_STALE",
                        selected_action=getattr(decision, "skill_id", None) or getattr(decision, "decision_kind", None),
                    )
                    self._emit_snapshot(refresh_frames=False)
                    continue

                self._active_decision_id = getattr(decision, "decision_id", None)
                self._active_evidence_bundle_id = getattr(decision, "evidence_bundle_id", None)
                self._active_request_id = getattr(decision, "request_id", None)
                self._active_prompt_sha256 = getattr(decision, "prompt_sha256", None)
                dec_prov = dict(getattr(decision, "perception_provenance", None) or {})
                if not dec_prov and self.planner.mode == PlannerMode.DETERMINISTIC_PLANNER:
                    dec_prov = {
                        "geometric_source": "DETERMINISTIC_CV",
                        "semantic_source": "NONE",
                        "is_real_vlm": False,
                        "semantic_provided_to_agent": False,
                    }
                self._active_perception_provenance = dec_prov
                self._active_evidence_conflicts = list(getattr(decision, "evidence_conflicts", None) or ())
                self._active_evidence_validity = dict(getattr(decision, "evidence_validity", None) or {})
                self._active_semantic_provided = getattr(decision, "semantic_provided_to_agent", None)
                if self._active_semantic_provided is None and self.planner.mode == PlannerMode.DETERMINISTIC_PLANNER:
                    self._active_semantic_provided = False

                last_bundle = getattr(dual_client, "last_evidence_bundle", None) if dual_client is not None else None
                if last_bundle is not None and not parking_for_interrupt:
                    self._evidence_bundles.append(last_bundle.model_dump(mode="json"))

                if self.planner.mode == PlannerMode.LLM_AGENT:
                    if not parking_for_interrupt:
                        self._vlm_decision_rounds += 1
                    if isinstance(self.planner, LLMAgentDecisionPolicy):
                        self._vlm_calls_count = (
                            len(self.planner.perception_provider.client.traces)
                            + len(self.planner.agent_provider.client.traces)
                        )
                    else:
                        self._vlm_calls_count = len(getattr(self.planner, "call_traces", []))
                    self._total_vlm_latency_ms += float(decision.model_latency_ms or 0.0)
                    if decision.token_usage:
                        self._total_input_tokens += int(decision.token_usage.get("input_tokens") or 0)
                        self._total_output_tokens += int(decision.token_usage.get("output_tokens") or 0)
                        self._total_reasoning_tokens += int(decision.token_usage.get("reasoning_tokens") or 0)
                    self.agent_state.llm_connected = self.planner.llm_connected
                    self.agent_state.llm_model = self.planner.llm_model
                    self.agent_state.model_provider = getattr(self.planner, "model_provider", None)
                    self.agent_state.status_label = self.planner.status_label()
                    self.agent_state.selected_parameters = dict(decision.parameters)
                    self.agent_state.expected_information_gain = decision.expected_information_gain
                    self.agent_state.confidence = decision.confidence
                    self.agent_state.safety_gate_status = decision.validation_result
                    self.agent_state.safety_gate_detail = decision.blocked_reason or decision.rationale_summary
                    self.agent_state.model_latency_ms = decision.model_latency_ms
                    self.agent_state.total_vlm_calls = self._vlm_calls_count
                    self.agent_state.total_input_tokens = self._total_input_tokens
                    self.agent_state.total_output_tokens = self._total_output_tokens
                    self.agent_state.total_reasoning_tokens = self._total_reasoning_tokens
                    self._sync_dual_model_agent_state()

                self.agent_state.selected_action = decision.skill_id or decision.decision_kind
                self.agent_state.selection_rationale = decision.rationale_summary
                decision_source = (
                    "FastLoopContractWatchdog" if parking_for_interrupt
                    else self._planner_event_source(fallback_used=decision.fallback_used)
                )

                if decision.fallback_used:
                    self.agent_state.fallback_triggered = True
                    self.agent_state.fallback_reason = decision.failure_code
                    self.scene_state["fallback_triggered"] = True
                    self._record_decision(
                        event_type=DecisionEventType.REPLAN_REQUESTED,
                        source="deterministic_policy",
                        summary=f"VLM 异常触发显式确定性 Fallback ({decision.failure_code})",
                        rationale=decision.rationale_summary,
                        status="FALLBACK_TRIGGERED",
                        selected_action=decision.skill_id or decision.decision_kind,
                        skill_id=decision.skill_id,
                        input_reference=decision.input_reference,
                        failure_reason=decision.failure_code,
                        observation_id=agent_obs.observation_id if agent_obs else None,
                        input_frame_ids=[agent_obs.frame_id] if agent_obs else None,
                        validation_result=decision.validation_result,
                    )

                if decision.decision_kind == "FAIL_MISSION":
                    if (
                        mission.mission_type == MissionType.RELAY_SOLVE_CUBE
                        and self._relay_transient_retries < 2
                        and decision.failure_code
                        in {
                            "INVALID_JSON",
                            "SCHEMA_VALIDATION_FAILED",
                            "MODEL_TIMEOUT",
                            "API_UNAVAILABLE",
                            "PARAMETER_OUT_OF_BOUNDS",
                            "DISALLOWED_ACTION",
                            "PREMATURE_FINISH",
                        }
                    ):
                        self._relay_transient_retries += 1
                        self._last_skill_result = {
                            "skill_id": decision.skill_id,
                            "success": False,
                            "failure_code": decision.failure_code,
                            "result_summary": decision.rationale_summary,
                            "sim_time": self._sim_time(),
                        }
                        self._record_decision(
                            event_type=DecisionEventType.REPLAN_REQUESTED,
                            source="skill_registry_safety_gate",
                            summary=f"Relay Agent 决策校验重试 ({self._relay_transient_retries}/2): {decision.failure_code}",
                            rationale=decision.rationale_summary,
                            status="RETRYING",
                            failure_reason=decision.failure_code,
                        )
                        time.sleep(0.3)
                        continue

                    if mission.mission_type == MissionType.RELAY_SOLVE_CUBE:
                        self._relay_phase = RelayPhase.FAILED
                    self._record_decision(
                        event_type=DecisionEventType.SKILL_REJECTED,
                        source="skill_registry_safety_gate",
                        summary=f"Safety Gate 拒绝动作 {decision.skill_id or decision.raw_vlm_action or 'unknown'}",
                        rationale=decision.rationale_summary,
                        status="REJECTED",
                        selected_action=decision.skill_id or decision.raw_vlm_action,
                        skill_id=decision.skill_id,
                        observation_id=agent_obs.observation_id if agent_obs else None,
                        input_frame_ids=[agent_obs.frame_id] if agent_obs else None,
                        validation_result=decision.validation_result,
                        failure_reason=decision.failure_code,
                        decision_id=self._active_decision_id,
                        evidence_bundle_id=self._active_evidence_bundle_id,
                        request_id=self._active_request_id,
                        prompt_sha256=self._active_prompt_sha256,
                        perception_provenance=self._active_perception_provenance,
                        evidence_conflicts=self._active_evidence_conflicts,
                        evidence_validity=self._active_evidence_validity,
                        semantic_provided_to_agent=self._active_semantic_provided,
                    )
                    self._fail_mission_with_reason(
                        mission=mission,
                        failure_code=decision.failure_code or "VLM_DECISION_FAILED",
                        summary=f"VLM 决策或安全校验失败：{decision.failure_code or 'FAILED'}",
                        rationale=decision.rationale_summary,
                        source=decision_source,
                        skill_id=decision.skill_id,
                        agent_obs=agent_obs,
                        decision=decision,
                    )
                    break

                self._relay_transient_retries = 0
                if decision.decision_kind == "COMPLETE_MISSION":
                    mission.status = MissionStatus.COMPLETED
                    mission.completed_at = now_wall_time()
                    if mission.mission_type == MissionType.RELAY_SOLVE_CUBE:
                        self._relay_phase = RelayPhase.RELAY_COMPLETED_VERIFIED
                        self._relay_round_tags.append("🎉 54/54物理复原")
                        mission.result_summary = "🎉 Agent 全自主人机接力复原成功：全六面 54/54 独立视觉核验 100% 物理复原！"
                    elif not mission.result_summary:
                        mission.result_summary = "任务计划全部步骤执行并验证通过。"
                    if self.scene_state.get("fallback_triggered"):
                        mission.result_summary += " [注意：执行中发生过确定性 Fallback，不计为纯 VLM 自主完成]"
                    self._total_execution_wall_s = round(time.perf_counter() - mission_wall_started, 4)
                    self._record_decision(
                        event_type=DecisionEventType.MISSION_COMPLETED,
                        source=decision_source,
                        summary=mission.result_summary,
                        rationale=decision.rationale_summary,
                        status=MissionStatus.COMPLETED.value,
                        selected_action=decision.raw_vlm_action or "FINISH",
                        input_reference=decision.input_reference,
                        observation_id=agent_obs.observation_id if agent_obs else None,
                        input_frame_ids=[agent_obs.frame_id] if agent_obs else None,
                        action_candidates=list(decision.action_candidates),
                        parameters=dict(decision.parameters),
                        expected_information_gain=decision.expected_information_gain,
                        confidence=decision.confidence,
                        validation_result=decision.validation_result,
                        model_latency_ms=decision.model_latency_ms,
                        token_usage=decision.token_usage,
                    )
                    self._emit_snapshot(refresh_frames=True)
                    break

                if decision.decision_kind == "BLOCK_CAPABILITY":
                    self._total_execution_wall_s = round(time.perf_counter() - mission_wall_started, 4)
                    self._handle_capability_block(
                        step_id=decision.step_id,
                        skill_id=decision.skill_id,
                        blocked_move=decision.blocked_move,
                        blocked_moves=list(decision.blocked_moves),
                        blocked_reason=decision.blocked_reason or decision.rationale_summary,
                        rationale=decision.rationale_summary,
                        input_reference=decision.input_reference,
                        source=decision_source,
                        agent_obs=agent_obs,
                        decision=decision,
                    )
                    self._emit_snapshot(refresh_frames=True)
                    break

                if decision.decision_kind == "REQUEST_REPLAN":
                    plan.replan_count += 1
                    plan.replan_reason = decision.rationale_summary
                    plan.updated_at = now_wall_time()
                    self._record_decision(
                        event_type=DecisionEventType.REPLAN_TRIGGERED,
                        source=decision_source,
                        summary="Agent 请求重新规划 (REQUEST_REPLAN)",
                        rationale=decision.rationale_summary,
                        status="REPLAN_REQUESTED",
                        selected_action=decision.raw_vlm_action or "REQUEST_REPLAN",
                        input_reference=decision.input_reference,
                        observation_id=agent_obs.observation_id if agent_obs else None,
                        input_frame_ids=[agent_obs.frame_id] if agent_obs else None,
                        validation_result=decision.validation_result,
                        model_latency_ms=decision.model_latency_ms,
                        token_usage=decision.token_usage,
                    )
                    self._emit_snapshot(refresh_frames=False)
                    if not self.allow_agent_failure_recovery:
                        self._fail_mission_with_reason(
                            mission=mission,
                            failure_code="REPLAN_REQUESTED_STOP",
                            summary="Agent 请求重新规划，当前单步策略模式中止。",
                            rationale=decision.rationale_summary,
                            source=decision_source,
                            agent_obs=agent_obs,
                            decision=decision,
                        )
                        break
                    continue

                assert decision.step_id is not None and decision.skill_id is not None
                self._record_decision(
                    event_type=DecisionEventType.SKILL_VALIDATED,
                    source="skill_registry_safety_gate",
                    summary=f"Safety Gate 通过动作 {decision.skill_id}",
                    rationale=decision.rationale_summary,
                    status="VALIDATED",
                    selected_action=decision.skill_id,
                    skill_id=decision.skill_id,
                    parameters=dict(decision.parameters),
                    observation_id=agent_obs.observation_id if agent_obs else None,
                    input_frame_ids=[agent_obs.frame_id] if agent_obs else None,
                    validation_result=decision.validation_result,
                    decision_id=self._active_decision_id,
                    evidence_bundle_id=self._active_evidence_bundle_id,
                    request_id=self._active_request_id,
                    prompt_sha256=self._active_prompt_sha256,
                    perception_provenance=self._active_perception_provenance,
                    evidence_conflicts=self._active_evidence_conflicts,
                    evidence_validity=self._active_evidence_validity,
                    semantic_provided_to_agent=self._active_semantic_provided,
                )
                if limits is not None and self.planner.mode == PlannerMode.LLM_AGENT:
                    if decision.skill_id == "observe_visible_faces" and self._vlm_observe_calls >= limits.max_observe_calls:
                        self._fail_mission_with_reason(
                            mission=mission,
                            failure_code="MAX_OBSERVE_CALLS_EXCEEDED",
                            summary=f"超过最大观察次数限制 ({limits.max_observe_calls})，安全中止任务。",
                            rationale="执行层确定性限制触发：observe_visible_faces 次数上限已达。",
                            source="MissionController",
                            skill_id=decision.skill_id,
                            agent_obs=agent_obs,
                            decision=decision,
                        )
                        break
                    if decision.skill_id == "reorient_cube" and self._vlm_reorient_calls >= limits.max_reorient_calls:
                        self._fail_mission_with_reason(
                            mission=mission,
                            failure_code="MAX_REORIENT_CALLS_EXCEEDED",
                            summary=f"超过最大物理重定位次数限制 ({limits.max_reorient_calls})，安全中止任务。",
                            rationale="执行层确定性限制触发：reorient_cube 次数上限已达。",
                            source="MissionController",
                            skill_id=decision.skill_id,
                            agent_obs=agent_obs,
                            decision=decision,
                        )
                        break

                step = next((s for s in plan.steps if s.step_id == decision.step_id), None)
                if step is None:
                    desc = self.registry.get(decision.skill_id)
                    step = PlanStep(
                        step_id=decision.step_id,
                        index=len(plan.steps) + 1,
                        title=desc.title if desc else decision.skill_id,
                        skill_id=decision.skill_id,
                        description=desc.description if desc else decision.skill_id,
                        status=PlanStepStatus.PENDING,
                        implemented=bool(desc.implemented) if desc else False,
                        parameters=dict(decision.parameters),
                    )
                    plan.steps.append(step)

                plan.current_step_id = step.step_id
                plan.updated_at = now_wall_time()

                selected_ev = self._record_decision(
                    event_type=DecisionEventType.ACTION_SELECTED,
                    source=decision_source,
                    summary=f"选择动作 [{step.title}] ({step.skill_id})",
                    rationale=decision.rationale_summary,
                    status="SELECTED",
                    selected_action=step.skill_id,
                    skill_id=step.skill_id,
                    input_reference=decision.input_reference,
                    observation_id=agent_obs.observation_id if agent_obs else None,
                    input_frame_ids=[agent_obs.frame_id] if agent_obs else None,
                    action_candidates=list(decision.action_candidates),
                    parameters=dict(decision.parameters),
                    expected_information_gain=decision.expected_information_gain,
                    confidence=decision.confidence,
                    validation_result=decision.validation_result,
                    model_latency_ms=decision.model_latency_ms,
                    token_usage=decision.token_usage,
                    decision_id=self._active_decision_id,
                    evidence_bundle_id=self._active_evidence_bundle_id,
                    request_id=self._active_request_id,
                    prompt_sha256=self._active_prompt_sha256,
                    perception_provenance=self._active_perception_provenance,
                    evidence_conflicts=self._active_evidence_conflicts,
                    evidence_validity=self._active_evidence_validity,
                    semantic_provided_to_agent=self._active_semantic_provided,
                )

                if self.planner.mode == PlannerMode.LLM_AGENT:
                    dec_tev = self.trace_log.append(
                        mission_id=mission.mission_id,
                        session_id=self.session_id,
                        parent_event_id=self._active_composite_trace_event_id or self._mission_trace_event_id,
                        skill_id=step.skill_id,
                        event_type=TraceEventType.DECISION,
                        name=f"vlm_select:{step.skill_id}",
                        source=decision_source,
                        status="COMPLETED",
                        sim_time=self._sim_time(),
                        end_sim_time=self._sim_time(),
                        evidence={
                            "decision_id": self._active_decision_id,
                            "evidence_bundle_id": self._active_evidence_bundle_id,
                            "request_id": self._active_request_id,
                            "observation_id": agent_obs.observation_id if agent_obs else None,
                            "frame_id": agent_obs.frame_id if agent_obs else None,
                            "camera_id": agent_obs.camera_id if agent_obs else None,
                            "selected_action": step.skill_id,
                            "parameters": dict(decision.parameters),
                            "reason": decision.rationale_summary,
                            "expected_information_gain": decision.expected_information_gain,
                            "confidence": decision.confidence,
                            "remaining_unknown_facelets": len(agent_obs.unknown_facelet_indices) if agent_obs else None,
                            "model_latency_ms": decision.model_latency_ms,
                            "perception_provenance": self._active_perception_provenance,
                            "evidence_conflicts": self._active_evidence_conflicts,
                            "semantic_provided_to_agent": self._active_semantic_provided,
                        },
                    )
                    if run is not None:
                        run.events.record_trace_event(dec_tev.model_dump(mode="json"))

                outcome = self._execute_plan_step(step, decision.input_reference)
                if self._active_cancellation_token and self._active_cancellation_token.is_cancelled():
                    self._active_cancellation_token = b.active_cancellation_token = CancellationToken()
                self._skill_duration_sim_s += float(step.elapsed_sec or 0.0)
                self._total_execution_wall_s = round(time.perf_counter() - mission_wall_started, 4)
                if self.skill_executions:
                    latest_exec = self.skill_executions[-1]
                    selected_ev.skill_execution_id = latest_exec.execution_id
                    # Only link observations actually produced by this skill execution (fixes stale feedback ref).
                    selected_ev.feedback_observation_id = latest_exec.feedback_observation_id
                    self._sync_run_artifacts()
                if outcome == "BLOCKED_CAPABILITY":
                    self._emit_snapshot(refresh_frames=True)
                    break
                if mission.status == MissionStatus.WAITING_FOR_HUMAN_TURN:
                    if getattr(self, "_relay_auto_resume_after_pause", False):
                        self._relay_auto_resume_after_pause = False
                        self._prepare_human_finish_turn()
                        mission.status = MissionStatus.EXECUTING
                        self._relay_phase = RelayPhase.AGENT_REASONING
                        self._emit_snapshot(refresh_frames=True)
                        continue
                    self._emit_snapshot(refresh_frames=True)
                    break
                if outcome == "FAILED":
                    recoverable_relay = (
                        mission.mission_type == MissionType.RELAY_SOLVE_CUBE
                        and step.failure_code in {"SOLVED_VERIFICATION_FAILED", "FLIP_AND_FEED_FAILED"}
                    )
                    if (self.allow_agent_failure_recovery or recoverable_relay) and self.planner.mode == PlannerMode.LLM_AGENT:
                        if step.failure_code == "FLIP_AND_FEED_FAILED":
                            self.scene_state["needs_rescan"] = True
                        self.agent_state.blocked_or_replan_reason = step.failure_reason
                        self._emit_snapshot(refresh_frames=True)
                        continue
                    if mission.mission_type == MissionType.RELAY_SOLVE_CUBE:
                        self._relay_phase = RelayPhase.FAILED
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
            self._active_cancellation_token = b.active_cancellation_token = None
            b.step_physics = orig_step_physics
            self._total_execution_wall_s = round(time.perf_counter() - mission_wall_started, 4)
            if self._active_composite_trace_event_id is not None:
                self.trace_log.finish(
                    self._active_composite_trace_event_id,
                    status=mission.status.value if mission else "COMPLETED",
                    end_sim_time=self._sim_time(),
                    failure_reason=mission.failure_reason if mission else None,
                )
                self._active_composite_trace_event_id = None

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
        source: str | None = None,
        agent_obs: AgentObservation | None = None,
        decision: Any = None,
    ) -> None:
        assert self.mission is not None and self.plan is not None
        matched = False
        if step_id:
            for s in self.plan.steps:
                if s.step_id == step_id:
                    matched = True
                    s.status = PlanStepStatus.BLOCKED
                    s.ended_sim_time = self._sim_time()
                    s.ended_wall_time = now_wall_time()
                    s.failure_reason = blocked_reason
                    s.result_summary = f"能力阻塞：{blocked_move or skill_id}"
        if not matched and skill_id:
            desc = self.registry.get(skill_id)
            self.plan.steps.append(
                PlanStep(
                    step_id=step_id or f"{self.plan.plan_id}-blk{len(self.plan.steps) + 1}",
                    index=len(self.plan.steps) + 1,
                    title=desc.title if desc else skill_id,
                    skill_id=skill_id,
                    description=desc.description if desc else skill_id,
                    status=PlanStepStatus.BLOCKED,
                    implemented=bool(desc.implemented) if desc else False,
                    parameters=dict(decision.parameters) if decision is not None else {},
                    started_sim_time=self._sim_time(),
                    ended_sim_time=self._sim_time(),
                    started_wall_time=now_wall_time(),
                    ended_wall_time=now_wall_time(),
                    elapsed_sec=0.0,
                    failure_reason=blocked_reason,
                    result_summary=f"能力阻塞：{blocked_move or skill_id}",
                )
            )
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
        self.agent_state.safety_gate_status = "CAPABILITY_BLOCKED"
        self.agent_state.safety_gate_detail = blocked_reason
        self._record_decision(
            event_type=DecisionEventType.CAPABILITY_BLOCKED,
            source=source or self._planner_event_source(),
            summary=f"物理能力阻塞：动作 {blocked_move or skill_id} 无法在当前模型中执行",
            rationale=rationale,
            status=MissionStatus.BLOCKED_CAPABILITY.value,
            selected_action=blocked_move or skill_id,
            skill_id=skill_id,
            input_reference=input_reference,
            failure_reason=blocked_reason,
            observation_id=agent_obs.observation_id if agent_obs else None,
            input_frame_ids=[agent_obs.frame_id] if agent_obs else None,
            action_candidates=list(decision.action_candidates) if decision is not None else None,
            parameters=dict(decision.parameters) if decision is not None else None,
            expected_information_gain=getattr(decision, "expected_information_gain", None),
            confidence=getattr(decision, "confidence", None),
            validation_result=getattr(decision, "validation_result", None) or "CAPABILITY_BLOCKED",
            model_latency_ms=getattr(decision, "model_latency_ms", None),
            token_usage=getattr(decision, "token_usage", None),
        )

    def _execute_plan_step(self, step: PlanStep, input_ref: str | None) -> str:
        assert self.mission is not None and self.plan is not None
        b = self._backend
        step.status = PlanStepStatus.RUNNING
        step.started_sim_time = self._sim_time()
        step.started_wall_time = now_wall_time()
        step.input_reference = input_ref

        if step.skill_id in {
            "observe_workspace",
            "active_six_face_scan",
            "observe_visible_faces",
            "observe_tabletop_rapid",
            "scan_occluded_bottom_face",
            "request_vlm_scene_semantics",
        }:
            self.mission.status = MissionStatus.OBSERVING
        elif step.skill_id in {
            "validate_cube_state",
            "verify_post_turn_state",
            "verify_solved_cube_independent",
            "finish_inspection",
        }:
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
            input_observation_id=(
                str(input_ref)
                if input_ref and str(input_ref).startswith("obs-")
                else (self.last_observation_ref.observation_id if self.last_observation_ref else None)
            ),
            decision_id=self._active_decision_id,
            evidence_bundle_id=self._active_evidence_bundle_id,
        )
        self.skill_executions.append(exec_state)
        self.agent_state.last_skill_call = step.skill_id
        b._active_skill_execution_id = exec_state.execution_id

        self._record_decision(
            event_type=DecisionEventType.SKILL_STARTED,
            source="SkillExecutor",
            summary=f"开始执行 Skill [{step.skill_id}]",
            rationale=f"按照当前计划执行步骤 {step.index}：{step.title}",
            status="RUNNING",
            selected_action=step.skill_id,
            skill_id=step.skill_id,
            input_reference=input_ref,
            skill_execution_id=exec_state.execution_id,
            decision_id=self._active_decision_id,
            evidence_bundle_id=self._active_evidence_bundle_id,
            request_id=self._active_request_id,
            perception_provenance=self._active_perception_provenance,
            evidence_conflicts=self._active_evidence_conflicts,
            semantic_provided_to_agent=self._active_semantic_provided,
        )
        self._emit_snapshot(refresh_frames=True)

        success = False
        failure_code: str | None = None
        failure_reason: str | None = None
        output_data: dict[str, Any] = {}
        result_summary = ""
        output_ref: str | None = None
        step_produced_obs_id: str | None = None
        step_causal_refs: dict[str, Any] = {}

        if step.skill_id == "observe_workspace":
            with b.truth_boundary.scope(
                TruthAccessCategory.RUNTIME_LOCALIZATION_FORBIDDEN,
                "observe_workspace_perception",
            ):
                frame = b.capture_rgbd("overhead")
                det, diag = DeterministicCubeLocalizer().locate_with_diagnostics(frame)
            frame_id = frame.frame_id or f"frm-{uuid.uuid4().hex[:8]}"
            obs_id = f"obs-{uuid.uuid4().hex[:8]}"
            pose_rec = None
            if self._current_run is not None:
                pose_rec = self._current_run.poses.record_pose_estimate(
                    frame_id=frame_id,
                    camera_id="overhead",
                    sim_time=frame.timestamp_seconds,
                    diagnostics=diag,
                    mission_id=self.mission.mission_id,
                    skill_execution_id=exec_state.execution_id,
                    observation_id=obs_id,
                    source_module="cube_relay.embodied.perception_v2.DeterministicCubeLocalizer",
                )
            if det is None:
                self.scene_state["cube_localized"] = False
                self.last_observation_ref = None
                b._active_pose_estimate = None
                failure_code = "CUBE_NOT_LOCALIZED"
                failure_reason = str(diag.get("failure_reason") or "顶部 RGB-D 相机未能在桌面区域定位到魔方。")
                step_causal_refs = {
                    "frame_id": frame_id,
                    "pose_estimate_id": pose_rec.pose_estimate_id if pose_rec is not None else None,
                }
            else:
                success = True
                self.scene_state["cube_localized"] = True
                b._active_pose_estimate = pose_rec
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
                step_produced_obs_id = obs_id
                step_causal_refs = {
                    "frame_id": frame_id,
                    "observation_id": obs_id,
                    "pose_estimate_id": pose_rec.pose_estimate_id if pose_rec is not None else None,
                }
                self._register_observation({
                    "observation_id": obs_id,
                    "frame_id": frame_id,
                    "camera_ids": ["overhead"],
                    "frame_refs": [frame_id],
                    "visual_summary": obs_ref.summary,
                    "coverage": 0,
                    "cube_center_world_m": list(obs_ref.cube_center_world_m),
                    "pose_estimate_id": pose_rec.pose_estimate_id if pose_rec is not None else None,
                    "sim_time": obs_ref.sim_time,
                    "frame_source": "REAL_MUJOCO_RENDERER",
                })
                output_data = {
                    "center_world_m": list(obs_ref.cube_center_world_m),
                    "yaw_radians": det.yaw_radians,
                    "frame_id": frame_id,
                    "observation_id": obs_id,
                    "pose_estimate_id": pose_rec.pose_estimate_id if pose_rec is not None else None,
                }
                result_summary = obs_ref.summary
                self._record_decision(
                    event_type=DecisionEventType.OBSERVATION_RECEIVED,
                    source="DeterministicCubeLocalizer",
                    summary=obs_ref.summary,
                    rationale="通过校准相机像素与深度中值恢复魔方 3D 中心坐标，未读取任何真值 pose。",
                    status="OBSERVED",
                    skill_id=step.skill_id,
                    observation_id=obs_id,
                    input_frame_ids=[frame_id],
                    output_reference=obs_id,
                    skill_execution_id=exec_state.execution_id,
                    feedback_observation_id=obs_id,
                )

        elif step.skill_id == "place_and_release":
            self.scene_state["scan_attempted"] = True
            self._ensure_vlm_scan_composite_trace()
            action_ok = True
            if not self.scene_state.get("cube_held_in_gripper", False):
                t0 = self._sim_time()
                grasp = run_bounded_grasp_retry(
                    b,
                    seed=self.seed,
                    scramble_steps=15,
                    reset_scene=False,
                    presence_detector=ChromaCubePresenceDetector(),
                )
                exec_state.subroutine_provenance = "HEURISTIC_VISION"
                step_causal_refs["subroutine_provenance"] = "HEURISTIC_VISION"
                step_causal_refs["subroutine_uses_real_vlm"] = False
                self._emit_mode_b_action_trace(
                    name="initial_grasp",
                    skill_id=step.skill_id,
                    success=bool(grasp.final_success),
                    start_sim=t0,
                    evidence={
                        "attempts": grasp.attempts,
                        "final_success": grasp.final_success,
                        "subroutine_provenance": "HEURISTIC_VISION",
                        "subroutine_uses_real_vlm": False,
                    },
                    failure_reason=None if grasp.final_success else "INITIAL_GRASP_FAILED",
                )
                if not grasp.final_success:
                    action_ok = False
                    failure_code = "INITIAL_GRASP_FAILED"
                    failure_reason = "抓取魔方失败，无法移动至扫描工位。"
                else:
                    t1 = self._sim_time()
                    aligned = b.task_align_scan_axes()
                    self._emit_mode_b_action_trace(
                        name="align_scan_axes",
                        skill_id=step.skill_id,
                        success=bool(aligned["success"]),
                        start_sim=t1,
                        evidence=dict(aligned),
                        failure_reason=aligned.get("failure_code"),
                    )
                    if not aligned["success"]:
                        action_ok = False
                        failure_code = str(aligned.get("failure_code") or "ALIGN_SCAN_AXES_FAILED")
                        failure_reason = f"对齐扫描轴失败：{failure_code}"
                if self._current_run is not None and getattr(b, "_active_contact_verification_id", None) is not None:
                    gtel = b.last_grasp_telemetry
                    left_pad = b.data.geom_xpos[b._id(b.mujoco.mjtObj.mjOBJ_GEOM, "left_finger_pad")]
                    right_pad = b.data.geom_xpos[b._id(b.mujoco.mjtObj.mjOBJ_GEOM, "right_finger_pad")]
                    jaw_gap = max(0.0, float(np.linalg.norm(left_pad - right_pad) - 0.024))
                    rel_end = b._relative_cube_position().tolist()
                    cv_rec = self._current_run.contacts.finalize_verification(
                        skill_name="place_and_release:initial_grasp",
                        sim_time=float(b.data.time),
                        trajectory_id=getattr(b, "_active_trajectory_id", None),
                        grasp_target_id=(
                            b._active_grasp_target.grasp_target_id
                            if getattr(b, "_active_grasp_target", None) is not None else None
                        ),
                        pose_estimate_id=(
                            b._active_pose_estimate.pose_estimate_id
                            if getattr(b, "_active_pose_estimate", None) is not None else None
                        ),
                        skill_execution_id=exec_state.execution_id,
                        bilateral_contact_fraction=float(gtel.bilateral_contact_fraction),
                        left_contact_fraction=float(gtel.left_contact_rate),
                        right_contact_fraction=float(gtel.right_contact_rate),
                        left_normal_force_n=float(gtel.left_normal_force_n),
                        right_normal_force_n=float(gtel.right_normal_force_n),
                        relative_slip_m=float(gtel.max_relative_slip_m),
                        gripper_width_m=jaw_gap,
                        lift_height_m=float(gtel.lift_height_m),
                        object_motion_relative_to_gripper_m=rel_end,
                        object_followed_end_effector=bool(action_ok and gtel.lift_height_m >= 0.06),
                        unintended_contacts=[],
                        verification_thresholds={
                            "min_bilateral_contact_fraction": 0.80,
                            "min_normal_force_n": float(b.grasp_config.minimum_normal_force_n),
                            "max_relative_slip_m": float(b.grasp_config.slip_limit_m),
                            "min_lift_height_m": 0.06,
                        },
                        verification_result=bool(action_ok and gtel.success),
                        failure_reason=failure_code,
                        contact_verification_id=b._active_contact_verification_id,
                    )
                    b._active_contact_verification_id = None
                    step_causal_refs["contact_verification_id"] = cv_rec.contact_verification_id
                step_causal_refs.update({
                    "pose_estimate_id": (
                        b._active_pose_estimate.pose_estimate_id
                        if getattr(b, "_active_pose_estimate", None) is not None else None
                    ),
                    "grasp_target_id": (
                        b._active_grasp_target.grasp_target_id
                        if getattr(b, "_active_grasp_target", None) is not None else None
                    ),
                    "trajectory_id": getattr(b, "_active_trajectory_id", None),
                })
            if action_ok:
                t2 = self._sim_time()
                placed = b.task_place_release()
                self._emit_mode_b_action_trace(
                    name="place_release_refresh",
                    skill_id=step.skill_id,
                    success=bool(placed["success"]),
                    start_sim=t2,
                    evidence={
                        "released": placed.get("released"),
                        "height_before_m": placed.get("height_before_m"),
                        "height_after_m": placed.get("height_after_m"),
                    },
                    failure_reason=placed.get("failure_code"),
                )
                if placed["success"]:
                    success = True
                    self.scene_state["cube_released_on_table"] = True
                    self.scene_state["cube_held_in_gripper"] = False
                    output_data = {
                        "released": bool(placed.get("released")),
                        "height_after_m": placed.get("height_after_m"),
                    }
                    result_summary = "已将魔方抓取对齐并安全释放至桌面扫描工位。"
                else:
                    failure_code = str(placed.get("failure_code") or "PLACE_RELEASE_FAILED")
                    failure_reason = f"放置释放失败：{failure_code}"

        elif step.skill_id == "observe_visible_faces":
            self._ensure_vlm_scan_composite_trace()
            req_mode = str(step.parameters.get("view_mode", "auto"))
            if req_mode == "auto":
                view_mode = "held" if self.scene_state.get("cube_held_in_gripper", False) else "released"
            else:
                view_mode = req_mode
            t_obs = self._sim_time()
            if view_mode == "held":
                observations = b.task_observe_held(self._scan_frame_offset)
                trace_name = "observe_held"
                cam_label = "held_scan_cameras"
            else:
                observations = b.task_observe_released(self._scan_frame_offset)
                trace_name = "observe_released"
                cam_label = "released_scan_cameras"
            self._scan_frame_offset += 5
            newly_obs, unk_before, unk_after, obs_id, frame_id = self._fuse_mode_b_observations(
                observations,
                trace_name=trace_name,
                skill_id=step.skill_id,
                camera_id_label=cam_label,
                start_sim=t_obs,
            )
            output_ref = obs_id
            step_produced_obs_id = obs_id
            step_causal_refs = {"observation_id": obs_id, "frame_id": frame_id}
            output_data = {
                "view_mode": view_mode,
                "observation_count": len(observations),
                "newly_observed": newly_obs,
                "observed_count": 54 - unk_after,
                "unknown_before": unk_before,
                "unknown_after": unk_after,
                "conflict_count": len(self.conflict_set),
                "observation_id": obs_id,
                "frame_id": frame_id,
            }
            if observations:
                success = True
                self._vlm_observe_calls += 1
                result_summary = (
                    f"完成 {view_mode} 多相机观测：新增 {newly_obs} 格，"
                    f"已观测 {54 - unk_after}/54，unknown {unk_before} → {unk_after}"
                )
            else:
                failure_code = "HELD_VIEW_GRASP_LOST" if view_mode == "held" else "NO_VALID_OBSERVATIONS"
                failure_reason = f"{view_mode} 观测未采集到有效魔方贴片（unknown={unk_after}）。"

        elif step.skill_id == "regrasp_cube":
            self._ensure_vlm_scan_composite_trace()
            t_reg = self._sim_time()
            regrasp = b.task_regrasp()
            self._emit_mode_b_action_trace(
                name="refresh_plan_regrasp",
                skill_id=step.skill_id,
                success=bool(regrasp["success"] and regrasp.get("contact_verification_passed", False)),
                start_sim=t_reg,
                evidence={
                    "contact_verification_passed": regrasp.get("contact_verification_passed"),
                    "contact_verification_id": regrasp.get("contact_verification_id"),
                    "bilateral_contact_fraction": regrasp.get("bilateral_contact_fraction"),
                    "left_normal_force_n": regrasp.get("left_normal_force_n"),
                    "right_normal_force_n": regrasp.get("right_normal_force_n"),
                    "max_relative_slip_m": regrasp.get("max_relative_slip_m"),
                    "lift_height_m": regrasp.get("lift_height_m"),
                    "phase_summaries": regrasp.get("phase_summaries"),
                    "attempts": regrasp.get("attempts"),
                },
                failure_reason=regrasp.get("failure_code"),
            )
            exec_state.subroutine_provenance = "HEURISTIC_VISION"
            step_causal_refs = {
                "contact_verification_id": regrasp.get("contact_verification_id"),
                "pose_estimate_id": (
                    b._active_pose_estimate.pose_estimate_id
                    if getattr(b, "_active_pose_estimate", None) is not None else None
                ),
                "grasp_target_id": (
                    b._active_grasp_target.grasp_target_id
                    if getattr(b, "_active_grasp_target", None) is not None else None
                ),
                "trajectory_id": getattr(b, "_active_trajectory_id", None),
                "subroutine_provenance": "HEURISTIC_VISION",
                "subroutine_uses_real_vlm": False,
            }
            regrasp_contact_ok = bool(
                regrasp["success"]
                and regrasp.get("contact_verification_passed", False)
                and float(regrasp.get("bilateral_contact_fraction", 0.0)) >= 0.80
            )
            if regrasp_contact_ok:
                self.scene_state["cube_held_in_gripper"] = True
                self.scene_state["cube_released_on_table"] = False
                # Refresh held orientation anchor from the side cameras before pitch/yaw reorient
                t_held = self._sim_time()
                held_initial = b.task_observe_held(self._scan_frame_offset)
                self._scan_frame_offset += 5
                newly_obs, unk_before, unk_after, obs_id, held_frame_id = self._fuse_mode_b_observations(
                    held_initial,
                    trace_name="observe_held_after_regrasp",
                    skill_id=step.skill_id,
                    camera_id_label="held_scan_cameras",
                    start_sim=t_held,
                )
                success = True
                output_ref = obs_id
                step_produced_obs_id = obs_id
                step_causal_refs["observation_id"] = obs_id
                step_causal_refs["frame_id"] = held_frame_id
                output_data = {
                    "contact_verification_passed": True,
                    "contact_verification_id": regrasp.get("contact_verification_id"),
                    "bilateral_contact_fraction": regrasp.get("bilateral_contact_fraction"),
                    "max_relative_slip_m": regrasp.get("max_relative_slip_m"),
                    "lift_height_m": regrasp.get("lift_height_m"),
                    "phase_summaries": regrasp.get("phase_summaries"),
                    "newly_observed": newly_obs,
                    "unknown_after": unk_after,
                }
                result_summary = (
                    f"安全重抓并刷新持握姿态锚点成功（双侧接触率 {regrasp.get('bilateral_contact_fraction', 0.0):.2f}，"
                    f"滑移 {regrasp.get('max_relative_slip_m', 0.0):.4f} m，unknown {unk_before} → {unk_after}）。"
                )
            else:
                failure_code = str(regrasp.get("failure_code") or "REGRASP_CONTACT_VERIFICATION_FAILED")
                failure_reason = f"重抓魔方未通过物理接触验证：{failure_code}"

        elif step.skill_id == "reorient_cube":
            self._ensure_vlm_scan_composite_trace()
            axis = str(step.parameters.get("axis", "pitch"))
            degrees = float(step.parameters.get("degrees", -90.0 if axis == "pitch" else 90.0))
            radians = math.radians(degrees)
            t_rot = self._sim_time()
            reoriented = b.task_reorient(axis, radians)
            if (
                not reoriented["success"]
                and reoriented.get("failure_code") == "REORIENT_JOINT_LIMIT"
                and axis == "pitch"
                and radians < 0
            ):
                for segment in (1, 2):
                    t_seg = self._sim_time()
                    reoriented = b.task_reorient("pitch", math.pi / 2, recenter=(segment == 2))
                    self._emit_mode_b_action_trace(
                        name=f"reorient_pitch_alternate_segment_{segment}",
                        skill_id=step.skill_id,
                        success=bool(reoriented["success"]),
                        start_sim=t_seg,
                        evidence={"axis": "pitch", "segment": segment, "raw": reoriented},
                        failure_reason=reoriented.get("failure_code"),
                    )
                    if not reoriented["success"]:
                        break
            else:
                self._emit_mode_b_action_trace(
                    name=f"reorient_{axis}",
                    skill_id=step.skill_id,
                    success=bool(reoriented["success"]),
                    start_sim=t_rot,
                    evidence={
                        "target_parameters": {"axis": axis, "degrees": degrees, "radians": radians},
                        "measured_parameters": {
                            "radians": reoriented.get("reorient_actual_radians"),
                            "degrees": (
                                round(math.degrees(float(reoriented["reorient_actual_radians"])), 2)
                                if reoriented.get("reorient_actual_radians") is not None
                                else None
                            ),
                            "error_radians": reoriented.get("reorient_error_radians"),
                            "bilateral_contact_fraction": reoriented.get("bilateral_contact_fraction"),
                            "max_relative_slip_m": reoriented.get("max_relative_slip_m"),
                        },
                    },
                    failure_reason=reoriented.get("failure_code"),
                )
            output_data = dict(reoriented)
            step_causal_refs = {
                "pose_estimate_id": (
                    b._active_pose_estimate.pose_estimate_id
                    if getattr(b, "_active_pose_estimate", None) is not None else None
                ),
                "grasp_target_id": (
                    b._active_grasp_target.grasp_target_id
                    if getattr(b, "_active_grasp_target", None) is not None else None
                ),
                "trajectory_id": getattr(b, "_active_trajectory_id", None),
            }
            if reoriented["success"]:
                success = True
                self._vlm_reorient_calls += 1
                self.scene_state["cube_held_in_gripper"] = True
                self.scene_state["cube_released_on_table"] = False
                actual_deg = (
                    round(math.degrees(float(reoriented["reorient_actual_radians"])), 2)
                    if reoriented.get("reorient_actual_radians") is not None
                    else degrees
                )
                result_summary = f"持握整体翻转完成：{axis} 目标 {degrees:.1f}°，实测腕角 {actual_deg:.1f}°。"
            else:
                failure_code = str(reoriented.get("failure_code") or "REORIENT_FAILED")
                failure_reason = f"持握翻转失败：{failure_code}"

        elif step.skill_id == "finish_inspection":
            unknown_cnt = self._scan_fusion.unknown_count
            conflict_cnt = self._scan_fusion.conflict_count
            facelets = self._scan_fusion.facelets()
            if unknown_cnt == 0 and conflict_cnt == 0 and facelets is not None:
                success = True
                self.observed_facelets_str = facelets
                self.scene_state["cube_localized_and_scanned"] = True
                self.scene_state["finish_inspection_done"] = True
                output_data = {
                    "observed_count": 54,
                    "unknown_count": 0,
                    "conflict_count": 0,
                    "reconstructed_facelets": facelets,
                }
                result_summary = "VLM 主动感知扫描完成：54/54 贴片完整融合且 0 冲突。"
                if self._active_composite_trace_event_id is not None:
                    self.trace_log.append(
                        mission_id=self.mission.mission_id,
                        session_id=self.session_id,
                        parent_event_id=self._active_composite_trace_event_id,
                        skill_id=step.skill_id,
                        event_type=TraceEventType.VERIFICATION,
                        name="vlm_scan_termination_check",
                        source="deterministic_validator",
                        status="COMPLETED",
                        sim_time=self._sim_time(),
                        end_sim_time=self._sim_time(),
                        evidence=output_data,
                    )
                    self.trace_log.finish(
                        self._active_composite_trace_event_id,
                        status="COMPLETED",
                        end_sim_time=self._sim_time(),
                        evidence=output_data,
                    )
                    self._active_composite_trace_event_id = None
            else:
                failure_code = "SCAN_INCOMPLETE" if unknown_cnt > 0 else "UNRESOLVED_CONFLICTS"
                failure_reason = f"扫描尚未满足完成条件：unknown={unknown_cnt}, conflicts={conflict_cnt}"

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
            step_produced_obs_id = obs_id
            step_causal_refs = {"observation_id": obs_id, "frame_id": frame_id}
            self._register_observation({
                "observation_id": obs_id,
                "frame_id": frame_id,
                "camera_ids": ["scan_and_inspection_rig"],
                "frame_refs": [frame_id],
                "visual_summary": obs_ref.summary,
                "coverage": observed_cnt,
                "unknown_after": unknown_cnt,
                "conflicts": 0,
                "sim_time": obs_ref.sim_time,
                "frame_source": "REAL_MUJOCO_RENDERER",
            })
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
                if hasattr(b, "_finalize_pending_grasp_verification"):
                    b._finalize_pending_grasp_verification(
                        skill_name="active_six_face_scan:grasp",
                        success=False,
                        failure_reason=failure_code,
                    )

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
            self.scene_state["capability_checked"] = True
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
            elif self.full_26_cubie:
                result_summary = (
                    f"全六面 26-cubie 能力核查通过：求解序列 {moves}（共 {len(moves)} 步），"
                    "动态追加物理翻面喂料与单工位接触转面步骤。"
                )
                next_idx = len(self.plan.steps) + 1
                new_steps: list[PlanStep] = []
                sim_top = str(self.scene_state.get("cube_top_face") or "U")
                sim_bot = str(self.scene_state.get("cube_bottom_face") or "D")
                for offset, mv in enumerate(moves):
                    est_flips = self.registry.estimate_move_flips(
                        mv, {"cube_top_face": sim_top, "cube_bottom_face": sim_bot}
                    )
                    new_steps.append(
                        PlanStep(
                            step_id=f"{self.plan.plan_id}-s{next_idx + offset}",
                            index=next_idx + offset,
                            title=f"物理翻面并执行 {mv}（预计翻面 {est_flips} 次）",
                            skill_id="execute_physical_face_turn",
                            description=self.registry.get("execute_physical_face_turn").description,  # type: ignore[union-attr]
                            parameters={"move": mv},
                        )
                    )
                    sim_top = mv[0]
                    sim_bot = {"U": "D", "D": "U", "F": "B", "B": "F", "R": "L", "L": "R"}[sim_top]
                v_idx = next_idx + len(moves)
                new_steps.append(
                    PlanStep(
                        step_id=f"{self.plan.plan_id}-s{v_idx}",
                        index=v_idx,
                        title="全六面独立相机 54 格视觉复核",
                        skill_id="verify_post_turn_state",
                        description=self.registry.get("verify_post_turn_state").description,  # type: ignore[union-attr]
                        parameters={},
                    )
                )
                self.plan.steps.extend(new_steps)
                self.plan.replan_count += 1
                self.plan.replan_reason = f"26-cubie 物理能力校验通过，展开 {len(moves)} 步物理转面与最终独立相机复核。"
                self._record_decision(
                    event_type=DecisionEventType.PLAN_UPDATED,
                    source=self._planner_event_source(),
                    summary=f"计划已扩展：追加 {len(moves)} 步 execute_physical_face_turn 与 verify_post_turn_state",
                    rationale=self.plan.replan_reason,
                    status="PLAN_UPDATED",
                    selected_action="execute_physical_face_turn",
                )
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
                    source=self._planner_event_source(),
                    summary="计划已扩展：追加 execute_physical_u_turn 与 verify_post_turn_state",
                    rationale=self.plan.replan_reason,
                    status="PLAN_UPDATED",
                    selected_action="execute_physical_u_turn",
                )

        elif step.skill_id == "execute_physical_u_turn":
            if self.scene_state.get("cube_released_on_table") and not self.scene_state.get("cube_held_in_gripper"):
                regrasp_pre = b.task_regrasp()
                if regrasp_pre.get("success"):
                    b.task_observe_held(self._scan_frame_offset)
                    self._scan_frame_offset += 5
                    self.scene_state["cube_held_in_gripper"] = True
                    self.scene_state["cube_released_on_table"] = False
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

        elif step.skill_id == "execute_physical_face_turn":
            move = str(step.parameters.get("move") or "U").strip()
            if b._bilateral_finger_contact() or (
                self.scene_state.get("cube_held_in_gripper") and not self.scene_state.get("cube_released_on_table")
            ):
                if b.flip_controller is not None:
                    pitch_val = float(b.data.qpos[b.model.jnt_qposadr[b._joint("wrist_pitch_joint")]])
                    if abs(math.sin(pitch_val)) > 0.5:
                        b.flip_controller._ramp(
                            "pre_turn_unpitch_lift",
                            {"robot_z_ctrl": -0.145},
                            0.24,
                            hold_grip=True,
                        )
                        b.flip_controller._ramp(
                            "pre_turn_unpitch_level",
                            {"wrist_pitch_ctrl": 0.0},
                            0.32,
                            settle_s=0.06,
                            hold_grip=True,
                        )
                rel_res = b.task_place_release()
                if rel_res.get("success"):
                    b._cube_26_location = "table"
                    b._index_cube_to_world = None
                    b._predicted_cube_rotation = None
                    b.task_observe_released(self._scan_frame_offset)
                    self._scan_frame_offset += 5
                    if b._index_cube_to_world is not None and b.orientation_tracker is not None:
                        b.orientation_tracker.update_from_visual_pose(
                            b._index_cube_to_world, source="post_scan_place_cv"
                        )
                        if b.visual_world_state is not None:
                            b.visual_world_state["rotation_cube_to_world"] = b._index_cube_to_world.copy()
                    self.scene_state["cube_held_in_gripper"] = False
                    self.scene_state["cube_released_on_table"] = True
            turn_res = b.execute_physical_face_turn(
                move,
                token=getattr(b, "active_cancellation_token", None),
            )
            self.scene_state["is_lattice_aligned"] = bool(
                turn_res.get("is_lattice_aligned", bool(turn_res.get("success")))
            )
            self.scene_state["residual_slice_angle_deg"] = float(
                turn_res.get("residual_slice_angle_deg", turn_res.get("max_slice_misalignment_deg", 0.0))
            )
            no_recolor = bool(self._initial_rgba is not None and np.array_equal(self._initial_rgba, b.model.geom_rgba))
            logical_unchanged = self._initial_sentinel == b._appearance_state
            same_model_data = (self._initial_model_id, self._initial_data_id) == (id(b.model), id(b.data))
            if turn_res.get("success") and no_recolor and logical_unchanged and same_model_data:
                self.scene_state["physical_face_turn_executed"] = True
                if move == "U":
                    self.scene_state["physical_u_turn_executed"] = True
                self.scene_state["turn_station_cleared"] = True
                self.scene_state["cube_released_on_table"] = True
                self.scene_state["cube_held_in_gripper"] = False
                self.scene_state["post_turn_verified"] = False
                self.scene_state["executed_physical_moves"] = list(
                    self.scene_state.get("executed_physical_moves") or []
                ) + [move]
                orient = turn_res.get("orientation") or {}
                if orient.get("top_face"):
                    self.scene_state["cube_top_face"] = orient["top_face"]
                if orient.get("bottom_face"):
                    self.scene_state["cube_bottom_face"] = orient["bottom_face"]
                self.last_turn_angle_deg = round(math.degrees(float(turn_res.get("actual_angle_rad") or 0.0)), 3)
                success = True
                output_data = dict(turn_res)
                output_data.update({
                    "no_recolor": no_recolor,
                    "logical_state_unchanged": logical_unchanged,
                    "same_model_and_data": same_model_data,
                })
                self.physical_verification = dict(output_data)
                result_summary = (
                    f"26-cubie 物理转面 {move} 完成：翻面 {turn_res.get('flips_executed', 0)} 次，"
                    f"实测转角 {self.last_turn_angle_deg:.2f}°（误差 {turn_res.get('angle_error_deg', 0.0):.3f}°），"
                    f"晶格最大偏角 {turn_res.get('max_slice_misalignment_deg', 0.0):.3f}°"
                )
            else:
                failure_code = str(turn_res.get("failure_code") or "PHYSICAL_FACE_TURN_FAILED")
                failure_reason = str(turn_res.get("failure_reason") or f"物理转面 {move} 失败：{failure_code}")
                if not no_recolor or not logical_unchanged or not same_model_data:
                    failure_code = "PHYSICAL_INTEGRITY_VIOLATION"
                    failure_reason = "检测到禁止的贴片改色或符号篡改"
                output_data = dict(turn_res)

        elif step.skill_id == "recover_preempted_turn_slice":
            mode = str(step.parameters.get("mode", "UNWIND_TO_ZERO"))
            rec_res = b.recover_preempted_turn_slice(
                mode=mode,
                release_base_after=bool(step.parameters.get("release_base_after", True)),
            )
            self.scene_state["is_lattice_aligned"] = bool(rec_res.get("is_lattice_aligned", False))
            self.scene_state["residual_slice_angle_deg"] = float(
                rec_res.get("residual_slice_angle_deg", rec_res.get("max_slice_misalignment_deg", 0.0))
            )
            if rec_res.get("success"):
                self.scene_state["turn_station_cleared"] = bool(step.parameters.get("release_base_after", True))
                success = True
                output_data = dict(rec_res)
                result_summary = (
                    f"半拧抢占恢复完成 ({mode})：残余偏角 {rec_res.get('max_slice_misalignment_deg', 0.0):.3f}°，"
                    f"is_lattice_aligned={rec_res.get('is_lattice_aligned')}"
                )
            else:
                failure_code = str(rec_res.get("failure_code") or "SLICE_RECOVERY_FAILED")
                failure_reason = str(rec_res.get("failure_reason") or f"半拧恢复失败：{failure_code}")
                output_data = dict(rec_res)

        elif step.skill_id == "verify_post_turn_state":
            expected = self.predicted_facelets_str
            if not expected or len(expected) != 54:
                failure_code = "EXPECTED_STATE_MISSING"
                failure_reason = "缺少转后预期状态，无法执行视觉复核。"
            elif getattr(b, "full_26_cubie", False):
                cam_res = b.inspect_26_cubie_via_independent_cameras(
                    token=getattr(b, "active_cancellation_token", None),
                )
                observed_state = str(cam_res.get("facelets") or "")
                self.observed_facelets_str = observed_state
                no_recolor = bool(self._initial_rgba is not None and np.array_equal(self._initial_rgba, b.model.geom_rgba))
                logical_unchanged = self._initial_sentinel == b._appearance_state
                same_model_data = (self._initial_model_id, self._initial_data_id) == (id(b.model), id(b.data))
                carrier_active = [
                    name
                    for idx in np.flatnonzero(b.data.eq_active).tolist()
                    for name in [str(b.mujoco.mj_id2name(b.model, b.mujoco.mjtObj.mjOBJ_EQUALITY, int(idx)) or "")]
                    if name.startswith("w_car_") or name == "human_grasp_weld"
                ]
                exact_match = bool(cam_res.get("success") and observed_state == expected)
                obs_id = f"obs-{uuid.uuid4().hex[:8]}"
                frame_id = f"frm-{uuid.uuid4().hex[:8]}"
                unknown_total = observed_state.count("?") if observed_state else 54
                observed_total = 54 - unknown_total
                self.cube_validation_status = (
                    "CONFLICT"
                    if int(cam_res.get("conflict_count") or 0) > 0
                    else "INCOMPLETE"
                    if unknown_total > 0
                    else "VALID_SOLVABLE"
                )
                self.last_observation_ref = ObservationReference(
                    observation_id=obs_id,
                    frame_id=frame_id,
                    sim_time=self._sim_time(),
                    camera_name="released_and_held_scan_cameras",
                    observed_count=observed_total,
                    unknown_count=unknown_total,
                    conflict_count=int(cam_res.get("conflict_count") or 0),
                    validation_status=self.cube_validation_status,
                    reconstructed_facelets=observed_state,
                    cube_center_world_m=self.last_observation_ref.cube_center_world_m if self.last_observation_ref else None,
                    summary=f"26-cubie 全六面独立相机复核：观测 {observed_total}/54 格，与预期{'完全一致' if exact_match else '存在偏差'}",
                )
                output_ref = obs_id
                step_produced_obs_id = obs_id
                step_causal_refs = {"observation_id": obs_id, "frame_id": frame_id}
                self._register_observation({
                    "observation_id": obs_id,
                    "frame_id": frame_id,
                    "camera_ids": ["released_and_held_scan_cameras"],
                    "frame_refs": [frame_id],
                    "visual_summary": self.last_observation_ref.summary,
                    "coverage": observed_total,
                    "unknown_after": unknown_total,
                    "conflicts": int(cam_res.get("conflict_count") or 0),
                    "sim_time": self.last_observation_ref.sim_time,
                    "frame_source": "REAL_MUJOCO_RENDERER",
                })
                output_data = {
                    "exact_54_match": exact_match,
                    "observed_count": observed_total,
                    "conflict_count": int(cam_res.get("conflict_count") or 0),
                    "observed_state": observed_state,
                    "expected_state": expected,
                    "no_recolor": no_recolor,
                    "logical_state_unchanged": logical_unchanged,
                    "same_model_and_data": same_model_data,
                    "active_non_core_welds": carrier_active,
                }
                if self.physical_verification is None:
                    self.physical_verification = {}
                self.physical_verification.update(output_data)
                if exact_match and no_recolor and logical_unchanged and same_model_data and not carrier_active:
                    success = True
                    self.scene_state["post_turn_verified"] = True
                    result_summary = "全六面独立相机复核通过：54/54 贴片全部匹配预期，0 冲突且确认零改色/零瞬移。"
                    self.mission.result_summary = result_summary
                    self._record_decision(
                        event_type=DecisionEventType.VERIFICATION_COMPLETED,
                        source="VisualTurnVerifier",
                        summary=result_summary,
                        rationale="全六面独立多视角重扫描 54/54 与符号预期完全一致，核心焊接以外无激活夹持/载具约束。",
                        status="VERIFIED",
                    )
                else:
                    failure_code = "VISUAL_MISMATCH"
                    failure_reason = f"26-cubie 全六面复核失败：match={exact_match}, conflicts={cam_res.get('conflict_count')}, carrier_active={carrier_active}"
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
                step_produced_obs_id = obs_id
                step_causal_refs = {"observation_id": obs_id, "frame_id": frame_id}
                self._register_observation({
                    "observation_id": obs_id,
                    "frame_id": frame_id,
                    "camera_ids": ["released_scan_cameras"],
                    "frame_refs": [frame_id],
                    "visual_summary": self.last_observation_ref.summary,
                    "coverage": observed_total,
                    "unknown_after": unknown_total,
                    "conflicts": len(comparison["conflicts"]),
                    "sim_time": self.last_observation_ref.sim_time,
                    "frame_source": "REAL_MUJOCO_RENDERER",
                })
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
                    self.scene_state["post_turn_verified"] = True
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

        elif step.skill_id == "observe_tabletop_rapid":
            self._relay_phase = RelayPhase.ROBOT_PERCEIVING
            self._emit_snapshot(refresh_frames=False)
            rapid_res = b.observe_tabletop_rapid_26_cubie(
                clear_prior=bool(self.scene_state.get("needs_rescan", False) or not self.scene_state.get("cube_localized")),
                token=getattr(b, "active_cancellation_token", None),
            )
            if not rapid_res.get("success"):
                failure_code = str(rapid_res.get("failure_code") or "RAPID_LOCALIZATION_FAILED")
                failure_reason = str(rapid_res.get("failure_reason") or f"桌面 1s 快瞄失败: {failure_code}")
                if failure_code in {"RAPID_LOCALIZATION_FAILED", "CUBE_NOT_LOCALIZED"}:
                    self.scene_state["vlm_awakening_requested"] = True
                output_data = dict(rapid_res)
            else:
                partial = str(rapid_res.get("partial_facelets") or ("?" * 54))
                prev_belief = self._relay_last_verified_54
                belief_res = self._belief_analyzer.analyze(
                    partial,
                    previous_belief_54=prev_belief,
                    last_suggested_moves=self._relay_last_suggested_moves,
                )
                belief_dict = belief_res.to_dict()
                self._relay_latest_belief_result = belief_dict
                self.observed_facelets_str = belief_res.deduced_facelets
                self.conflict_set.clear()
                self.scene_state["cube_localized"] = True
                self.scene_state["cube_released_on_table"] = True
                self.scene_state["cube_held_in_gripper"] = False
                self.scene_state["needs_rescan"] = False
                if rapid_res.get("top_face"):
                    self.scene_state["cube_top_face"] = rapid_res["top_face"]
                if rapid_res.get("bottom_face"):
                    self.scene_state["cube_bottom_face"] = rapid_res["bottom_face"]

                obs_id = f"obs-{uuid.uuid4().hex[:8]}"
                frame_id = f"frm-{uuid.uuid4().hex[:8]}"
                unk_cnt = belief_res.deduced_facelets.count("?")
                obs_cnt = 54 - unk_cnt
                self.cube_validation_status = "VALID_SOLVABLE" if belief_res.deduced_54_unique else "INCOMPLETE"
                center_xy = rapid_res.get("relocalized_xy_m") or [0.0, 0.0]
                self.last_observation_ref = ObservationReference(
                    observation_id=obs_id,
                    frame_id=frame_id,
                    sim_time=self._sim_time(),
                    camera_name="released_5face_rapid_glance",
                    observed_count=int(rapid_res.get("observed_count") or 45),
                    unknown_count=unk_cnt,
                    conflict_count=int(rapid_res.get("conflict_count") or 0),
                    validation_status=self.cube_validation_status,
                    reconstructed_facelets=belief_res.deduced_facelets,
                    cube_center_world_m=(float(center_xy[0]), float(center_xy[1]), 0.66),
                    summary=belief_res.reasoning_summary_zh,
                )
                output_ref = obs_id
                step_produced_obs_id = obs_id
                step_causal_refs = {"observation_id": obs_id, "frame_id": frame_id}
                self._register_observation({
                    "observation_id": obs_id,
                    "frame_id": frame_id,
                    "camera_ids": ["released_5face_rapid_glance"],
                    "frame_refs": [frame_id],
                    "visual_summary": belief_res.reasoning_summary_zh,
                    "coverage": obs_cnt,
                    "unknown_after": unk_cnt,
                    "conflicts": 0,
                    "sim_time": self.last_observation_ref.sim_time,
                    "frame_source": "REAL_MUJOCO_RENDERER",
                })
                if belief_res.inferred_human_moves:
                    inf_txt = " ".join(belief_res.inferred_human_moves)
                    tag = f"🧑 {inf_txt}" + (" (偏离)" if belief_res.human_deviation_detected else "")
                    if not self._relay_round_tags or self._relay_round_tags[-1] != tag:
                        self._relay_round_tags.append(tag)
                    self._relay_human_inferred_moves_count += len(belief_res.inferred_human_moves)
                if belief_res.deduced_54_unique:
                    self._relay_last_verified_54 = belief_res.deduced_facelets
                    if belief_res.deduced_facelets not in self._relay_state_history[-1:]:
                        self._relay_state_history.append(belief_res.deduced_facelets)
                    self.scene_state["all_54_facelets_observed"] = True
                    self.scene_state["finish_inspection_done"] = True
                    self.scene_state["cube_localized_and_scanned"] = True
                    self.scene_state["cube_state_validated"] = True
                    self.scene_state["is_solved"] = belief_res.deduced_facelets == SOLVED_FACELETS
                    self.scene_state["post_solve_independent_verified"] = False
                    if int(rapid_res.get("unknown_count") or 0) > 0:
                        self._relay_cognitive_stats["rapid_glance_deduction_successes"] += 1
                    self._record_decision(
                        event_type=DecisionEventType.RAPID_GLANCE_DEDUCED,
                        source="BeliefConservationAnalyzer",
                        summary=f"1s 桌面快瞄唯一锁定 54/54 状态（跳过 ~25s 翻底面扫；耗时 {rapid_res.get('wall_time_s')}s）",
                        rationale=belief_res.reasoning_summary_zh,
                        status="LOCKED_54",
                        output_reference=obs_id,
                    )
                else:
                    self.scene_state["all_54_facelets_observed"] = False
                    self.scene_state["cube_localized_and_scanned"] = False
                    self.scene_state["cube_state_validated"] = False
                    self.scene_state["is_solved"] = False
                self._refresh_relay_cognitive_context()
                success = True
                output_data = {
                    **{k: v for k, v in rapid_res.items() if k != "partial_facelets"},
                    **belief_dict,
                }
                result_summary = (
                    f"1s 桌面快瞄观测 {rapid_res.get('observed_count')}/54 格："
                    f"{'块守恒唯一锁定 54/54!' if belief_res.deduced_54_unique else f'存在 {belief_res.ambiguous_facelet_count} 格真歧义'}"
                )

        elif step.skill_id in {"scan_occluded_bottom_face", "verify_solved_cube_independent"}:
            is_verify_only = step.skill_id == "verify_solved_cube_independent"
            self._relay_phase = RelayPhase.VERIFYING_SOLVED if is_verify_only else RelayPhase.ROBOT_PERCEIVING
            self._emit_snapshot(refresh_frames=True)
            cam_res = b.rescan_and_relocalize_26_cubie(token=getattr(b, "active_cancellation_token", None))
            observed_state = str(cam_res.get("facelets") or "")
            no_recolor = bool(self._initial_rgba is not None and np.array_equal(self._initial_rgba, b.model.geom_rgba))
            logical_unchanged = self._initial_sentinel == b._appearance_state
            same_model_data = (self._initial_model_id, self._initial_data_id) == (id(b.model), id(b.data))
            carrier_active = [
                name
                for idx in np.flatnonzero(b.data.eq_active).tolist()
                for name in [str(b.mujoco.mj_id2name(b.model, b.mujoco.mjtObj.mjOBJ_EQUALITY, int(idx)) or "")]
                if name.startswith("w_car_") or name == "human_grasp_weld"
            ]
            unknown_total = observed_state.count("?") if observed_state else 54
            observed_total = 54 - unknown_total
            conflict_cnt = int(cam_res.get("conflict_count") or 0)
            valid_54 = bool(
                cam_res.get("success")
                and len(observed_state) == 54
                and unknown_total == 0
                and conflict_cnt == 0
                and no_recolor
                and logical_unchanged
                and same_model_data
                and not carrier_active
            )
            if valid_54:
                self._relay_cognitive_stats["full_bottom_scans"] += 1
                self.observed_facelets_str = observed_state
                self.conflict_set.clear()
                self.cube_validation_status = "VALID_SOLVABLE"
                prev_belief = self._relay_last_verified_54
                belief_res = self._belief_analyzer.analyze(
                    observed_state,
                    previous_belief_54=prev_belief,
                    last_suggested_moves=self._relay_last_suggested_moves,
                )
                self._relay_latest_belief_result = belief_res.to_dict()
                if belief_res.inferred_human_moves and not is_verify_only:
                    inf_txt = " ".join(belief_res.inferred_human_moves)
                    tag = f"🧑 {inf_txt}" + (" (偏离)" if belief_res.human_deviation_detected else "")
                    if not self._relay_round_tags or self._relay_round_tags[-1] != tag:
                        self._relay_round_tags.append(tag)
                    self._relay_human_inferred_moves_count += len(belief_res.inferred_human_moves)
                elif not self._relay_round_tags and not is_verify_only:
                    self._relay_round_tags.append("🤖 开局六面扫描")
                self._relay_last_verified_54 = observed_state
                if observed_state not in self._relay_state_history[-1:]:
                    self._relay_state_history.append(observed_state)
                self.scene_state["cube_localized"] = True
                self.scene_state["scan_attempted"] = True
                self.scene_state["cube_released_on_table"] = True
                self.scene_state["cube_held_in_gripper"] = False
                self.scene_state["all_54_facelets_observed"] = True
                self.scene_state["finish_inspection_done"] = True
                self.scene_state["cube_localized_and_scanned"] = True
                self.scene_state["cube_state_validated"] = True
                self.scene_state["needs_rescan"] = False
                if cam_res.get("top_face"):
                    self.scene_state["cube_top_face"] = cam_res["top_face"]
                if cam_res.get("bottom_face"):
                    self.scene_state["cube_bottom_face"] = cam_res["bottom_face"]

                obs_id = f"obs-{uuid.uuid4().hex[:8]}"
                frame_id = f"frm-{uuid.uuid4().hex[:8]}"
                center_xy = cam_res.get("relocalized_xy_m") or [0.0, 0.0]
                self.last_observation_ref = ObservationReference(
                    observation_id=obs_id,
                    frame_id=frame_id,
                    sim_time=self._sim_time(),
                    camera_name="released_and_held_scan_cameras",
                    observed_count=observed_total,
                    unknown_count=unknown_total,
                    conflict_count=conflict_cnt,
                    validation_status="VALID_SOLVABLE",
                    reconstructed_facelets=observed_state,
                    cube_center_world_m=(float(center_xy[0]), float(center_xy[1]), 0.66),
                    summary=f"完整六面独立相机扫描 54/54 完成（reloc={center_xy}, yaw={cam_res.get('relocalized_yaw_deg')}°）",
                )
                output_ref = obs_id
                step_produced_obs_id = obs_id
                step_causal_refs = {"observation_id": obs_id, "frame_id": frame_id}
                self._register_observation({
                    "observation_id": obs_id,
                    "frame_id": frame_id,
                    "camera_ids": ["released_and_held_scan_cameras"],
                    "frame_refs": [frame_id],
                    "visual_summary": self.last_observation_ref.summary,
                    "coverage": observed_total,
                    "unknown_after": unknown_total,
                    "conflicts": conflict_cnt,
                    "sim_time": self.last_observation_ref.sim_time,
                    "frame_source": "REAL_MUJOCO_RENDERER",
                })
                is_solved_now = observed_state == SOLVED_FACELETS
                self.scene_state["is_solved"] = is_solved_now
                self.scene_state["post_solve_independent_verified"] = bool(is_solved_now)
                self._refresh_relay_cognitive_context()
                output_data = {
                    **cam_res,
                    "exact_54_solved": is_solved_now,
                    "no_recolor": no_recolor,
                    "logical_state_unchanged": logical_unchanged,
                    "same_model_and_data": same_model_data,
                    "active_non_core_welds": carrier_active,
                }
                if is_verify_only or is_solved_now:
                    if self.physical_verification is None:
                        self.physical_verification = {}
                    self.physical_verification.update(output_data)
                if is_verify_only and not is_solved_now:
                    failure_code = "SOLVED_VERIFICATION_FAILED"
                    failure_reason = "独立六面扫描确认魔方尚未完全复原（仍存在未还原格），已刷新最新状态供 Agent 继续求解。"
                else:
                    success = True
                    result_summary = (
                        "🎉 独立六面多视角视觉核验通过：54/54 全部复原，0 unknown/conflict，确认零改色零作弊！"
                        if is_solved_now
                        else f"完整六面主动扫描完成：54/54 贴片唯一锁定（重定位 {center_xy} / {cam_res.get('relocalized_yaw_deg')}°）。"
                    )
                    if is_solved_now:
                        self._record_decision(
                            event_type=DecisionEventType.VERIFICATION_COMPLETED,
                            source="Independent6FaceVerifier",
                            summary=result_summary,
                            rationale="释放态与持握翻转态双盲融合确认 54/54 复原且核心外零约束焊点。",
                            status="VERIFIED_SOLVED",
                            output_reference=obs_id,
                        )
            else:
                failure_code = str(cam_res.get("failure_code") or "SCAN_OR_VERIFICATION_FAILED")
                failure_reason = str(cam_res.get("failure_reason") or cam_res.get("reason") or f"六面主动扫描失败: {failure_code}")
                if not no_recolor or not logical_unchanged or not same_model_data:
                    failure_code = "PHYSICAL_INTEGRITY_VIOLATION"
                    failure_reason = "检测到禁止的贴片改色或符号篡改"
                output_data = dict(cam_res)

        elif step.skill_id == "request_vlm_scene_semantics":
            cam_id = str(step.parameters.get("camera_id", "overhead"))
            frame = b.capture_rgbd(cam_id)
            img_url = _encode_jpeg_data_url(frame.rgb, quality=86)
            sem_summary = "传统 CV 状态正常"
            sem_dict: dict[str, Any] = {"camera_id": cam_id, "reason_requested": step.parameters.get("reason", "agent_on_demand")}
            if isinstance(self.planner, LLMAgentDecisionPolicy) and self.planner.perception_provider.client.is_configured():
                obs_proxy = self.build_agent_observation(camera_id=cam_id)
                env, trace, ref_mm = self.planner.perception_provider.perceive_envelope(obs_proxy, img_url)
                self._relay_cognitive_stats["on_demand_vlm_calls"] += 1
                self._vlm_calls_count += 1
                if trace is not None:
                    self._total_vlm_latency_ms += float(trace.latency_ms or 0.0)
                    self._total_input_tokens += int(trace.input_tokens or 0)
                    self._total_output_tokens += int(trace.output_tokens or 0)
                if env is not None and not ref_mm:
                    sem_dict = env.semantic.model_dump(mode="json")
                    sem_summary = env.semantic.summary
            else:
                self._relay_cognitive_stats["on_demand_vlm_calls"] += 1
            self._relay_vlm_diagnosis = sem_dict
            self.scene_state["vlm_awakening_requested"] = False
            success = True
            output_data = sem_dict
            result_summary = f"按需唤醒 VLM 诊断完成 ({cam_id})：{sem_summary}"

        elif step.skill_id == "commit_physical_moves":
            moves = [str(m).strip() for m in (step.parameters.get("moves") or [])]
            contract = ExecutionContractSpec.model_validate(step.parameters.get("contract") or {})
            self._active_execution_contract = contract
            previous_token = self._active_cancellation_token
            token = previous_token or CancellationToken()
            self._active_cancellation_token = token
            b.active_cancellation_token = token
            self._relay_phase = RelayPhase.ROBOT_ACTING
            self._emit_snapshot(refresh_frames=True)

            executed_here: list[str] = []
            preempt_info: dict[str, Any] | None = None
            aborted = False
            try:
                for mv in moves:
                    if token.is_cancelled() or self._stop_event.is_set():
                        preempt_info = {
                            "preempted": True,
                            "chunk_status": "PREEMPTED_SAFE_HOLD",
                            "cancel_reason": token.reason or "USER_STOP_REQUESTED",
                            "executed_before_preempt": list(executed_here),
                            "interrupt_to_hold_sim_ms": 0.0,
                            "interrupt_to_hold_wall_ms": (
                                round(max(0.0, (time.monotonic() - token.requested_at_wall_s) * 1000.0), 3)
                                if token.requested_at_wall_s is not None
                                else 0.0
                            ),
                            "recovery_mode": contract.mid_turn_recovery_mode,
                            "is_lattice_aligned_after": bool(self.scene_state.get("is_lattice_aligned", True)),
                            "residual_slice_angle_deg_after": float(self.scene_state.get("residual_slice_angle_deg", 0.0)),
                        }
                        break

                    if b._bilateral_finger_contact() or (
                        self.scene_state.get("cube_held_in_gripper") and not self.scene_state.get("cube_released_on_table")
                    ):
                        rel_res = b.task_place_release()
                        if rel_res.get("success"):
                            b._cube_26_location = "table"
                            self.scene_state["cube_held_in_gripper"] = False
                            self.scene_state["cube_released_on_table"] = True

                    turn_res = b.execute_physical_face_turn(mv, token=token)
                    aligned_now = bool(turn_res.get("is_lattice_aligned", bool(turn_res.get("success"))))
                    res_deg_now = float(turn_res.get("residual_slice_angle_deg", turn_res.get("max_slice_misalignment_deg", 0.0)))
                    self.scene_state["is_lattice_aligned"] = aligned_now
                    self.scene_state["residual_slice_angle_deg"] = res_deg_now

                    if turn_res.get("preempted") or token.is_cancelled():
                        self._relay_cognitive_stats["fast_loop_contract_interceptions"] += 1
                        hold_sim_ms = turn_res.get("interrupt_to_hold_sim_ms")
                        hold_wall_ms = turn_res.get("interrupt_to_hold_wall_ms")
                        if hold_wall_ms is None and token.requested_at_wall_s is not None:
                            hold_wall_ms = round(max(0.0, (time.monotonic() - token.requested_at_wall_s) * 1000.0), 3)
                        rec_aligned = aligned_now
                        rec_deg = res_deg_now
                        if not aligned_now:
                            self._relay_phase = RelayPhase.PREEMPTED_RECOVERING
                            self._emit_snapshot(refresh_frames=True)
                            rec = b.recover_preempted_turn_slice(
                                mode=contract.mid_turn_recovery_mode,
                                release_base_after=True,
                            )
                            rec_aligned = bool(rec.get("is_lattice_aligned", False))
                            rec_deg = float(rec.get("residual_slice_angle_deg", rec.get("max_slice_misalignment_deg", 0.0)))
                            self.scene_state["is_lattice_aligned"] = rec_aligned
                            self.scene_state["residual_slice_angle_deg"] = rec_deg
                            self.scene_state["turn_station_cleared"] = True
                        preempt_info = {
                            "preempted": True,
                            "chunk_status": str(turn_res.get("chunk_status") or "PREEMPTED_SAFE_HOLD"),
                            "cancel_reason": token.reason or turn_res.get("failure_reason"),
                            "interrupted_move": mv,
                            "executed_before_preempt": list(executed_here),
                            "interrupt_to_hold_sim_ms": hold_sim_ms,
                            "interrupt_to_hold_wall_ms": hold_wall_ms,
                            "recovery_mode": contract.mid_turn_recovery_mode,
                            "is_lattice_aligned_after": rec_aligned,
                            "residual_slice_angle_deg_after": rec_deg,
                        }
                        self._relay_latest_preemption = dict(preempt_info)
                        self._record_decision(
                            event_type=DecisionEventType.PREEMPTION_TRIGGERED,
                            source="FastLoopContractWatchdog",
                            summary=f"物理动作 {mv} 中途被快环契约抢占并恢复 ({contract.mid_turn_recovery_mode})",
                            rationale=(
                                f"hold_sim={hold_sim_ms}ms, hold_wall={hold_wall_ms}ms, "
                                f"残余偏角={rec_deg:.3f}°, aligned={rec_aligned}"
                            ),
                            status="PREEMPTED_RECOVERED" if rec_aligned else "PREEMPTED_UNALIGNED",
                        )
                        if executed_here:
                            self._relay_round_tags.append(f"🤖 {' '.join(executed_here)} (中断)")
                        else:
                            self._relay_round_tags.append(f"⚡ {mv} 中途刹停恢复")
                        break

                    no_recolor = bool(self._initial_rgba is not None and np.array_equal(self._initial_rgba, b.model.geom_rgba))
                    logical_unchanged = self._initial_sentinel == b._appearance_state
                    same_model_data = (self._initial_model_id, self._initial_data_id) == (id(b.model), id(b.data))
                    if turn_res.get("success") and no_recolor and logical_unchanged and same_model_data:
                        executed_here.append(mv)
                        self._relay_robot_moves_count += 1
                        self.scene_state["physical_face_turn_executed"] = True
                        self.scene_state["executed_physical_moves"] = list(
                            self.scene_state.get("executed_physical_moves") or []
                        ) + [mv]
                        self.scene_state["post_solve_independent_verified"] = False
                        orient = turn_res.get("orientation") or {}
                        if orient.get("top_face"):
                            self.scene_state["cube_top_face"] = orient["top_face"]
                        if orient.get("bottom_face"):
                            self.scene_state["cube_bottom_face"] = orient["bottom_face"]
                        if self._relay_last_verified_54 and len(self._relay_last_verified_54) == 54:
                            self._relay_last_verified_54 = CubeEngine().apply_move(self._relay_last_verified_54, mv)
                            self._relay_state_history.append(self._relay_last_verified_54)
                            self.observed_facelets_str = self._relay_last_verified_54
                        self.last_turn_angle_deg = round(math.degrees(float(turn_res.get("actual_angle_rad") or 0.0)), 3)
                    else:
                        aborted = True
                        failure_code = str(turn_res.get("failure_code") or "PHYSICAL_FACE_TURN_FAILED")
                        failure_reason = str(turn_res.get("failure_reason") or f"物理转面 {mv} 失败: {failure_code}")
                        if not no_recolor or not logical_unchanged or not same_model_data:
                            failure_code = "PHYSICAL_INTEGRITY_VIOLATION"
                            failure_reason = "检测到禁止的贴片改色或符号篡改"
                        output_data = dict(turn_res)
                        break
            finally:
                self._active_execution_contract = None
                if previous_token is None and b.active_cancellation_token is token:
                    b.active_cancellation_token = None
                if previous_token is None and self._active_cancellation_token is token:
                    self._active_cancellation_token = None

            if not aborted:
                if preempt_info is not None:
                    success = bool(preempt_info.get("is_lattice_aligned_after", False))
                    output_data = dict(preempt_info)
                    if not success:
                        failure_code = "SLICE_RECOVERY_FAILED"
                        failure_reason = "快环抢占后未能将晶格偏角恢复至容差内"
                    else:
                        result_summary = (
                            f"⚡ 物理动作中途响应人类指令安全刹停 (hold={preempt_info.get('interrupt_to_hold_sim_ms')}ms) "
                            f"并已执行 {preempt_info.get('recovery_mode')} 对齐恢复！"
                        )
                else:
                    success = True
                    self._relay_round_tags.append(f"🤖 {' '.join(executed_here)}")
                    output_data = {
                        "executed_moves": executed_here,
                        "contract": contract.model_dump(mode="json"),
                        "is_lattice_aligned": bool(self.scene_state.get("is_lattice_aligned", True)),
                        "preempted": False,
                    }
                    result_summary = f"机械臂已完成承诺物理动作 [{ ' '.join(executed_here) }]（26-cubie 纯接触驱动）。"
                self._refresh_relay_cognitive_context()

        elif step.skill_id == "handover_to_human":
            self._relay_phase = RelayPhase.ROBOT_ACTING
            self._emit_snapshot(refresh_frames=True)
            ho_res = b.handover_26_cubie_to_table(token=getattr(b, "active_cancellation_token", None))
            if not ho_res.get("success"):
                failure_code = str(ho_res.get("failure_code") or "HANDOVER_FAILED")
                failure_reason = str(ho_res.get("failure_reason") or "桌面交接失败")
                output_data = dict(ho_res)
            else:
                # Isolate handover pose strictly into _human_private (ZERO leakage into Agent/Tracker/scene_state)
                with self._hri_lock:
                    self._human_private = _HumanPrivateTruth(
                        base_handover_xy=tuple(float(v) for v in ho_res.get("_human_private_base_xy", (0.0, 0.0))),  # type: ignore[arg-type]
                        base_handover_quat=tuple(float(v) for v in ho_res.get("_human_private_base_quat", (1.0, 0.0, 0.0, 0.0))),  # type: ignore[arg-type]
                    )
                    suggested = [str(m).strip() for m in (step.parameters.get("suggested_moves") or [])][:3]
                    msg_zh = str(step.parameters.get("message_zh") or "魔方已安全停放于桌面中央交接区，请操作后交回。")
                    reason_zh = str(step.parameters.get("delegation_reason_zh") or "当前朝向下高代价翻面交由人类接力可显著节省耗时。")
                    self._relay_last_suggested_moves = suggested
                    self._relay_handover_message_zh = msg_zh
                    self._relay_delegation_reason_zh = reason_zh
                    self._relay_clarification_pending = False
                    top_f = str(self.scene_state.get("cube_top_face") or "U")
                    bot_f = str(self.scene_state.get("cube_bottom_face") or "D")
                    saved_2f = sum(
                        1
                        for m in suggested
                        if self._flip_cost_profile.flips_for_move(m, top_face=top_f, bottom_face=bot_f) == 2
                    )
                    self._relay_cognitive_stats["saved_high_cost_flips"] += int(saved_2f)
                    self._relay_phase = RelayPhase.WAITING_FOR_HUMAN_TURN

                self.scene_state["cube_held_in_gripper"] = False
                self.scene_state["cube_released_on_table"] = True
                self.scene_state["turn_station_cleared"] = True
                self.scene_state["needs_rescan"] = False
                self.mission.status = MissionStatus.WAITING_FOR_HUMAN_TURN
                self._append_relay_dialog("agent", f"{msg_zh}（{reason_zh}）", topic="HANDOVER")
                clean_ho = {k: v for k, v in ho_res.items() if not k.startswith("_human_private_")}
                success = True
                output_data = {
                    **clean_ho,
                    "suggested_moves": suggested,
                    "delegation_reason_zh": reason_zh,
                    "waiting_for_human": True,
                }
                result_summary = f"已完成安全桌面交接（机械臂停泊于 -0.42, 0.25）；推荐：{suggested or '自由接力'}。"
                self._record_decision(
                    event_type=DecisionEventType.HANDOVER_COMPLETED,
                    source="RelayHandoverExecutor",
                    summary=result_summary,
                    rationale=reason_zh,
                    status="WAITING_FOR_HUMAN_TURN",
                    skill_id=step.skill_id,
                    parameters={"suggested_moves": suggested},
                )

        elif step.skill_id == "ask_human_clarification":
            q_zh = str(step.parameters.get("question_zh") or "请确认当前协作意图。")
            opts = [str(o) for o in (step.parameters.get("options") or [])]
            topic = str(step.parameters.get("clarification_topic") or "INTENT_DEVIATION")
            with self._hri_lock:
                self._relay_clarification_pending = True
                self._relay_clarification_question_zh = q_zh
                self._relay_clarification_options = opts
                self._relay_clarification_topic = topic
                self._relay_cognitive_stats["clarifications_requested"] += 1
                self._relay_phase = RelayPhase.AWAITING_HUMAN_CLARIFICATION
            self.mission.status = MissionStatus.WAITING_FOR_HUMAN_TURN
            self._append_relay_dialog("agent", f"[澄清] {q_zh}", topic=topic)
            success = True
            output_data = {"clarification_pending": True, "question_zh": q_zh, "options": opts, "topic": topic}
            result_summary = f"Agent 发起意图/歧义澄清：{q_zh}"
            self._record_decision(
                event_type=DecisionEventType.CLARIFICATION_REQUESTED,
                source="LLMAgentDecisionPolicy",
                summary=result_summary,
                rationale="在存在逆向抵消风险或真歧义时拒绝盲目猜测，主动向人类确认意图。",
                status="AWAITING_HUMAN_CLARIFICATION",
                skill_id=step.skill_id,
                parameters=output_data,
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
        if self._active_decision_id is not None:
            step_causal_refs.setdefault("decision_id", self._active_decision_id)
        if self._active_evidence_bundle_id is not None:
            step_causal_refs.setdefault("evidence_bundle_id", self._active_evidence_bundle_id)
        if self._active_request_id is not None:
            step_causal_refs.setdefault("request_id", self._active_request_id)
        exec_state.causal_refs = dict(step_causal_refs)
        exec_state.feedback_observation_id = step_produced_obs_id
        if step_causal_refs:
            output_data = {**output_data, "causal_refs": dict(step_causal_refs)}
        exec_state.output_data = output_data
        exec_state.verification_passed = success
        b._active_skill_execution_id = None

        self._last_skill_result = {
            "skill_id": step.skill_id,
            "success": success,
            "result_summary": result_summary if success else failure_reason,
            "failure_code": failure_code,
            "output_reference": output_ref,
            "feedback_observation_id": step_produced_obs_id,
            "causal_refs": dict(step_causal_refs),
            "sim_time": step.ended_sim_time,
        }
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
                skill_execution_id=exec_state.execution_id,
                feedback_observation_id=step_produced_obs_id,
                decision_id=self._active_decision_id,
                evidence_bundle_id=self._active_evidence_bundle_id,
                request_id=self._active_request_id,
                perception_provenance=self._active_perception_provenance,
                evidence_conflicts=self._active_evidence_conflicts,
                semantic_provided_to_agent=self._active_semantic_provided,
            )
            self._sync_run_artifacts()
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
            skill_execution_id=exec_state.execution_id,
            feedback_observation_id=step_produced_obs_id,
            failure_reason=failure_reason,
            decision_id=self._active_decision_id,
            evidence_bundle_id=self._active_evidence_bundle_id,
            request_id=self._active_request_id,
            perception_provenance=self._active_perception_provenance,
            evidence_conflicts=self._active_evidence_conflicts,
            semantic_provided_to_agent=self._active_semantic_provided,
        )
        self._sync_run_artifacts()
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
            self.experiment_recorder.close()
        finally:
            try:
                self._run_on_gl_thread(_close_gl)
            finally:
                if self._executor is not None:
                    self._executor.shutdown(wait=False)
                    self._executor = None
