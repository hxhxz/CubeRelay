"""MuJoCo implementation of the Embodied Simulation v2 backend.

Physical fidelity labels:
* free cube dynamics, robot joints, contacts, lift and whole-cube rotation: PHYSICS
* grasp retention: PHYSICS (parallel-jaw contact and friction; no robot weld)
* face turns: SIMPLIFIED_PHYSICAL_FIXTURE (measured hinge, not 26 cubies)
* perception: RGB-D pixels only; no cube qpos or logical state is exposed
"""

from __future__ import annotations

import math
import colorsys
import uuid
from collections import deque
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

import numpy as np

from cube_relay.cube import CubeEngine, SOLVED_FACELETS
from cube_relay.execution.action_chunk import (
    ActionChunk,
    ActionChunkExecutor,
    CancellationToken,
    ChunkExecutionResult,
    ChunkStatus,
)
from cube_relay.experiment.boundary import TruthAccessBoundary, TruthAccessCategory
from cube_relay.experiment.schema import QualityStatus

from .execution import ActionFeedback, ActionRequest
from .mujoco_executor import MuJoCoTurnExecutor
from .v2_types import (
    CameraCalibration,
    FaceObservation,
    GraspCandidate,
    GraspControlConfig,
    GraspTelemetry,
    RGBDFrame,
)


_COLORS = {
    "U": np.array([.92, .92, .92, 1.0]),
    "R": np.array([.86, .08, .05, 1.0]),
    "F": np.array([.03, .68, .12, 1.0]),
    "D": np.array([.95, .82, .04, 1.0]),
    "L": np.array([1.0, .34, .02, 1.0]),
    "B": np.array([.03, .20, .90, 1.0]),
}
_RGB8 = {face: rgba[:3] * 255 for face, rgba in _COLORS.items()}
_HSV = {face: colorsys.rgb_to_hsv(*(rgba[:3])) for face, rgba in _COLORS.items()}


@dataclass(frozen=True, slots=True)
class _MotionDiagnostics:
    bilateral_rate: float
    left_rate: float
    right_rate: float
    left_force_n: float
    right_force_n: float
    max_slip_m: float


class MuJoCoEmbodiedBackend:
    implementation_level = (
        "PHYSICS:free_body+parallel_jaw_friction_grasp+joint_motion; "
        "SIMPLIFIED_PHYSICS:hinge_face_fixture; MOCK:virtual_human_weld"
    )

    def __init__(
        self,
        model_path: str | Path | None = None,
        *,
        width: int = 480,
        height: int = 360,
        video_path: str | Path | None = None,
        grasp_config: GraspControlConfig | None = None,
        physical_u: bool = False,
        full_26_cubie: bool = False,
        video_timing: str = "sim_time",
    ) -> None:
        try:
            import mujoco
        except ImportError as exc:
            raise RuntimeError("install cube-relay[simulation] with Python 3.11-3.13") from exc
        self.mujoco = mujoco
        default = Path(__file__).resolve().parents[3] / "simulation" / "cube_relay_v2.xml"
        self.model_path = Path(model_path or default)
        self.physical_u = bool(physical_u and not full_26_cubie)
        self.full_26_cubie = bool(full_26_cubie)
        if self.full_26_cubie:
            from .physical_cube_26 import build_26_cubie_scene
            self.model = mujoco.MjModel.from_xml_string(build_26_cubie_scene(self.model_path))
        elif self.physical_u:
            from .physical_u import build_u_scene
            self.model = mujoco.MjModel.from_xml_string(build_u_scene(self.model_path))
        else:
            self.model = mujoco.MjModel.from_xml_path(str(self.model_path))
        self.data = mujoco.MjData(self.model)
        self.renderer = mujoco.Renderer(self.model, height=height, width=width)
        self.width, self.height = width, height
        self.video_path = Path(video_path) if video_path else None
        if video_timing not in {"legacy", "sim_time"}:
            raise ValueError("video_timing must be legacy or sim_time")
        self.video_timing = video_timing
        self.video_fps = 12
        self.video_camera = "overhead"
        self.grasp_config = grasp_config or GraspControlConfig()
        from .replay_timing import TimedFrames, MotionTiming
        self.frames = TimedFrames(self)
        self.motion_timing = MotionTiming(self)
        self.engine = CubeEngine()
        self._appearance_state = "".join(face * 9 for face in "URFDLB")
        self._turner = None if (self.physical_u or self.full_26_cubie) else MuJoCoTurnExecutor()
        self._sticker_colors_locked = False
        self.cube_26_turner: Any | None = None
        self.flip_controller: Any | None = None
        self.orientation_tracker: Any | None = None
        self._cube_26_location: str = "table"
        self._cube_26_center_xy: tuple[float, float] | None = None
        self._plan_version = 1
        self.active_cancellation_token: CancellationToken | None = None
        self.last_chunk_result: ChunkExecutionResult | None = None
        self._cached_cube_geom_model: object | None = None
        self._cached_cube_geom_ids: set[int] = set()
        self._cached_chunk_executor_model: object | None = None
        self._cached_chunk_executor: ActionChunkExecutor | None = None
        self.last_grasp_telemetry = GraspTelemetry(False, 0, 0, 0, 0, "not attempted")
        self.last_grasp_candidates: tuple[GraspCandidate, ...] = ()
        self.last_selected_grasp_candidate: GraspCandidate | None = None
        self.observation_action_trace: list[str] = []
        self.contact_debug_trace: list[dict[str, object]] = []
        self.contact_failure_class: str | None = None
        self.last_place_release_diagnostics: dict[str, object] = {}
        self.last_observation_diagnostics: list[dict[str, object]] = []
        self.facelet_mapping_diagnostics: list[dict[str, object]] = []
        self.debug_observation_frames: list[tuple[str, np.ndarray]] = []
        self.visual_world_state: dict[str, object] | None = None
        self._world_state_revision = 0
        self._predicted_cube_rotation: np.ndarray | None = None
        self._index_cube_to_world: np.ndarray | None = None
        self._trace_reference_cube_position: np.ndarray | None = None
        self._trace_contact_reference_relative: np.ndarray | None = None
        self._skill_start_height: float | None = None
        self._skill_phase_trace: list[str] = []
        self.experiment_run: object | None = None
        self.vision_fault_mode: str | None = None
        self.truth_boundary = TruthAccessBoundary()
        self._active_mission_id: str | None = None
        self._active_skill_execution_id: str | None = None
        self._active_pose_estimate: object | None = None
        self._active_grasp_target: object | None = None
        self._active_trajectory_id: str | None = None
        self._active_contact_verification_id: str | None = None
        self._last_skill_approach_diag: dict[str, object] | None = None
        self._last_skill_establish_diag: dict[str, object] | None = None
        self._last_skill_lift_diag: dict[str, object] | None = None
        self._last_skill_align_diag: dict[str, object] | None = None
        self._last_seed: int = 0
        self._apply_grasp_config_to_model()
        if self.full_26_cubie:
            from .flip_and_feed import CubeOrientationTracker, FlipAndFeedController
            from .physical_cube_26 import Physical26CubeTurnExecutor

            self.cube_26_turner = Physical26CubeTurnExecutor(
                self.model,
                self.data,
                self.mujoco,
                post_step_fn=self._after_chunk_step,
            )
            self.flip_controller = FlipAndFeedController(
                self.model,
                self.data,
                self.mujoco,
                executor=self._action_chunk_executor(),
                turn_executor=self.cube_26_turner,
                post_step_fn=self._after_chunk_step,
            )
            self.orientation_tracker = CubeOrientationTracker()
        self._set_sticker_colors(self._appearance_state)
        if self.full_26_cubie:
            self._sticker_colors_locked = True
        self.mujoco.mj_forward(self.model, self.data)
        self.motion_timing.install()

    def _after_chunk_step(self, _step_idx: int = 0) -> str | None:
        """Advance timing/video/trajectory hooks after an external ActionChunk step."""
        self.motion_timing.tick()
        self.frames.capture_due()
        if self.experiment_run is not None:
            self.experiment_run.trajectories.sample_backend_step(self)
        return None

    def step_physics(self) -> None:
        self.mujoco.mj_step(self.model, self.data)
        self.motion_timing.tick()
        self.frames.capture_due()
        if self.experiment_run is not None:
            self.experiment_run.trajectories.sample_backend_step(self)

    @property
    def legacy_recording(self) -> bool:
        return self.video_path is not None and self.video_timing == "legacy"

    def _apply_grasp_config_to_model(self) -> None:
        config = self.grasp_config
        for name in ("left_finger_ctrl", "right_finger_ctrl"):
            actuator = self._actuator(name)
            self.model.actuator_gainprm[actuator, 0] = config.finger_kp
            self.model.actuator_biasprm[actuator, 1] = -config.finger_kp
            if config.finger_force_limit_n is not None:
                self.model.actuator_forcelimited[actuator] = 1
                self.model.actuator_forcerange[actuator] = [
                    -config.finger_force_limit_n, config.finger_force_limit_n,
                ]
        if config.pad_sliding_friction is not None:
            for name in ("left_finger_pad", "right_finger_pad"):
                geom = self._id(self.mujoco.mjtObj.mjOBJ_GEOM, name)
                self.model.geom_friction[geom, 0] = config.pad_sliding_friction
        if config.contact_solref_timeconst is not None:
            for name in ("left_finger_pad", "right_finger_pad", "cube_core"):
                geom = self._id(self.mujoco.mjtObj.mjOBJ_GEOM, name)
                self.model.geom_solref[geom, 0] = config.contact_solref_timeconst

    def _id(self, kind: object, name: str) -> int:
        value = self.mujoco.mj_name2id(self.model, kind, name)
        if value < 0:
            raise KeyError(name)
        return value

    def _actuator(self, name: str) -> int:
        return self._id(self.mujoco.mjtObj.mjOBJ_ACTUATOR, name)

    def _joint(self, name: str) -> int:
        return self._id(self.mujoco.mjtObj.mjOBJ_JOINT, name)

    def _equality(self, name: str) -> int:
        return self._id(self.mujoco.mjtObj.mjOBJ_EQUALITY, name)

    def _set_sticker_colors(self, facelets: str) -> None:
        if self.full_26_cubie and getattr(self, "_sticker_colors_locked", False):
            raise RuntimeError(
                "Physical honesty violation: _set_sticker_colors is forbidden after reset in full_26_cubie mode"
            )
        if self.physical_u or self.full_26_cubie:
            from .physical_u import physical_color_layout
            facelets = physical_color_layout(facelets)
        for face_index, face in enumerate("URFDLB"):
            for sticker in range(9):
                geom = self._id(
                    self.mujoco.mjtObj.mjOBJ_GEOM, f"sticker_{face}_{sticker}"
                )
                self.model.geom_rgba[geom] = _COLORS[facelets[face_index * 9 + sticker]]

    def reset_random(
        self,
        seed: int,
        scramble_steps: int,
        *,
        scramble_moves: list[str] | tuple[str, ...] | None = None,
    ) -> dict[str, object]:
        with self.truth_boundary.scope(TruthAccessCategory.EXPERIMENT_INIT_ALLOWED, "reset_random"):
            rng = np.random.default_rng(seed)
            self._last_seed = int(seed)
            self.vision_fault_mode = None
            self._sticker_colors_locked = False
            self.mujoco.mj_resetData(self.model, self.data)
            if self.cube_26_turner is not None:
                self.cube_26_turner.reset_welds()
            if self.flip_controller is not None:
                self.flip_controller.sync_station_lattice_state()
            if self.orientation_tracker is not None:
                self.orientation_tracker.reset()
            self._cube_26_location = "table"
            self._cube_26_center_xy = None
            if scramble_moves is not None:
                moves = [str(m).strip() for m in scramble_moves]
                state = self.engine.apply_moves(SOLVED_FACELETS, moves)
            else:
                state, moves = self.engine.scramble(seed, scramble_steps)
            self._appearance_state = state
            self._set_sticker_colors(state)
            if self.full_26_cubie:
                self._sticker_colors_locked = True
            joint = self._joint("cube_free")
            address = self.model.jnt_qposadr[joint]
            x, y = rng.uniform(-.35, .35), rng.uniform(-.28, .28)
            yaw = rng.uniform(-math.pi, math.pi)
            if self.physical_u or self.full_26_cubie:
                # Avoid initial geometric overlap with turn_station pads (e.g. seed=10 vs base_pos_pad).
                def _overlaps_station_pad(cx: float, cy: float, cyaw: float) -> bool:
                    ux, uy = math.cos(cyaw), math.sin(cyaw)
                    vx, vy = -uy, ux
                    for pad_x, pad_y in ((0.35, -0.19), (0.35, -0.45)):
                        dx, dy = cx - pad_x, cy - pad_y
                        separated = False
                        for ax, ay in ((1.0, 0.0), (0.0, 1.0), (ux, uy), (vx, vy)):
                            proj_c = abs(dx * ax + dy * ay)
                            r_pad = 0.055 * abs(ax) + 0.010 * abs(ay)
                            r_cube = 0.060 * (abs(ux * ax + uy * ay) + abs(vx * ax + vy * ay))
                            if proj_c >= r_pad + r_cube + 0.015:
                                separated = True
                                break
                        if not separated:
                            return True
                    return False

                for _ in range(32):
                    if not _overlaps_station_pad(x, y, yaw):
                        break
                    x, y = rng.uniform(-.35, .35), rng.uniform(-.28, .28)
                    yaw = rng.uniform(-math.pi, math.pi)
            self.data.qpos[address:address + 7] = [
                x, y, .665, math.cos(yaw / 2), 0, 0, math.sin(yaw / 2),
            ]
            self.data.eq_active[self._equality("human_grasp_weld")] = 0
            self.mujoco.mj_forward(self.model, self.data)
            for _ in range(200):
                self.step_physics()
            self.frames.clear()
            self.motion_timing.reset()
            self.debug_observation_frames.clear()
            self.facelet_mapping_diagnostics.clear()
            self.last_observation_diagnostics.clear()
            self.visual_world_state = None
            self._world_state_revision = 0
            self._predicted_cube_rotation = None
            self._index_cube_to_world = None
            self.last_grasp_telemetry = GraspTelemetry(False, 0, 0, 0, 0, "not attempted")
            self.last_grasp_candidates = ()
            self.last_selected_grasp_candidate = None
            self.contact_debug_trace.clear()
            self.contact_failure_class = None
            self.observation_action_trace.clear()
            self.last_place_release_diagnostics = {}
            self._skill_start_height = None
            self._skill_phase_trace = []
            self._last_skill_approach_diag = None
            self._last_skill_establish_diag = None
            self._last_skill_lift_diag = None
            self._last_skill_align_diag = None
            self._active_pose_estimate = None
            self._active_grasp_target = None
            self._active_trajectory_id = None
            self._active_contact_verification_id = None
            # Evaluation-only metadata. The controller intentionally discards this return value.
            return {"seed": seed, "scramble": moves, "truth_for_evaluation_only": state}

    def reset_with_perturbation(
        self,
        seed: int,
        scramble_steps: int = 15,
        *,
        dx_m: float = 0.0,
        dy_m: float = 0.0,
        dyaw_rad: float = 0.0,
        vision_fault_mode: str | None = None,
    ) -> dict[str, object]:
        """Controlled experiment initialization applying cube pose perturbation before observation."""
        with self.truth_boundary.scope(TruthAccessCategory.EXPERIMENT_INIT_ALLOWED, "reset_with_perturbation"):
            meta = self.reset_random(seed, scramble_steps)
            joint = self._joint("cube_free")
            address = self.model.jnt_qposadr[joint]
            base_qpos = self.data.qpos[address:address + 7].copy()
            x0, y0, z0 = float(base_qpos[0]), float(base_qpos[1]), float(base_qpos[2])
            qw, qx, qy, qz = (float(v) for v in base_qpos[3:7])
            yaw0 = math.atan2(2.0 * (qw * qz + qx * qy), 1.0 - 2.0 * (qy * qy + qz * qz))
            x = x0 + float(dx_m)
            y = y0 + float(dy_m)
            yaw = yaw0 + float(dyaw_rad)
            self.data.qpos[address:address + 7] = [
                x, y, .665, math.cos(yaw / 2), 0.0, 0.0, math.sin(yaw / 2),
            ]
            self.data.qvel[self.model.jnt_dofadr[joint]:self.model.jnt_dofadr[joint] + 6] = 0.0
            self.mujoco.mj_forward(self.model, self.data)
            for _ in range(200):
                self.step_physics()
            cube_id = self._id(self.mujoco.mjtObj.mjOBJ_BODY, "cube")
            settled = self.data.xpos[cube_id].copy()
            sx, sy, sz = float(settled[0]), float(settled[1]), float(settled[2])
            ik_reachable = abs(sx) <= 0.64 and abs(sy) <= 0.51 and 0.60 <= sz <= 0.78
            table_supported = abs(sx) <= 0.74 and abs(sy) <= 0.59 and self._cube_touches_geom("table")
            radial_clearance = min(0.8 - abs(sx), 0.65 - abs(sy))
            palm_clearance_ok = radial_clearance >= 0.10
            station_overlap = bool((self.physical_u or self.full_26_cubie) and abs(sx - 0.35) < 0.14 and abs(sy + 0.32) < 0.21)
            reachable_and_safe = bool(ik_reachable and table_supported and palm_clearance_ok and not station_overlap)
            self.vision_fault_mode = vision_fault_mode
            if self.experiment_run is not None and self.experiment_run.config.include_audit_ground_truth:
                self.experiment_run.trajectories.record_audit_pose(self, phase="INIT_SETTLED")
            return {
                **meta,
                "perturbation": {
                    "dx_m": float(dx_m),
                    "dy_m": float(dy_m),
                    "dyaw_rad": float(dyaw_rad),
                    "vision_fault_mode": vision_fault_mode,
                },
                "initial_base_xy_m": [x0, y0],
                "initial_perturbed_gt_xyz_m": [sx, sy, sz],
                "initial_perturbed_gt_yaw_rad": yaw,
                "reachability_audit": {
                    "ik_reachable": ik_reachable,
                    "table_supported": table_supported,
                    "palm_clearance_ok": palm_clearance_ok,
                    "radial_clearance_m": radial_clearance,
                    "turn_station_overlap": station_overlap,
                    "reachable_and_safe": reachable_and_safe,
                },
            }

    def _camera_calibration(self, camera_name: str) -> CameraCalibration:
        camera = self._id(self.mujoco.mjtObj.mjOBJ_CAMERA, camera_name)
        fovy = float(self.model.cam_fovy[camera])
        fy = .5 * self.height / math.tan(math.radians(fovy) / 2)
        fx = fy
        rotation_mj = self.data.cam_xmat[camera].reshape(3, 3)
        rotation_cv = rotation_mj @ np.diag([1.0, -1.0, -1.0])
        transform = np.eye(4)
        transform[:3, :3] = rotation_cv
        transform[:3, 3] = self.data.cam_xpos[camera]
        return CameraCalibration(fx, fy, self.width / 2, self.height / 2, transform)

    def capture_rgbd(self, camera_name: str = "overhead") -> RGBDFrame:
        frame_id = f"frm-{uuid.uuid4().hex[:8]}"
        calibration = self._camera_calibration(camera_name)
        sim_t = float(self.data.time)
        if self.vision_fault_mode in {"occluded", "sensor_unavailable", "blackout"}:
            rgb = np.zeros((self.height, self.width, 3), dtype=np.uint8)
            depth = np.full((self.height, self.width), np.nan, dtype=np.float32)
            rgb_t = sim_t
            depth_t = sim_t
            q_status = QualityStatus.MISSING
        else:
            self.renderer.disable_depth_rendering()
            self.renderer.update_scene(self.data, camera=camera_name)
            rgb = self.renderer.render().copy()
            rgb_t = float(self.data.time)
            self.renderer.enable_depth_rendering()
            self.renderer.update_scene(self.data, camera=camera_name)
            depth = self.renderer.render().copy()
            depth_t = float(self.data.time)
            self.renderer.disable_depth_rendering()
            q_status = QualityStatus.VALID
        if self.experiment_run is not None:
            self.experiment_run.poses.record_camera_frame(
                frame_id=frame_id,
                camera_id=camera_name,
                rgb=rgb,
                depth_m=depth,
                fx=calibration.fx,
                fy=calibration.fy,
                cx=calibration.cx,
                cy=calibration.cy,
                camera_to_world=calibration.camera_to_world,
                sim_time=sim_t,
                rgb_sim_time=rgb_t,
                depth_sim_time=depth_t,
                mission_id=self._active_mission_id,
                skill_execution_id=self._active_skill_execution_id,
                quality_status=q_status,
            )
        return RGBDFrame(
            rgb, depth, calibration, camera_name, sim_t, frame_id=frame_id,
        )

    def _set_controls(self, targets: dict[str, float], seconds: float = .7) -> None:
        for name, target in targets.items():
            self.data.ctrl[self._actuator(name)] = target
        steps = int(seconds / self.model.opt.timestep)
        sample_every = max(1, steps // 6)
        for step in range(steps):
            self.step_physics()
            if self.legacy_recording and step % sample_every == 0:
                self.renderer.disable_depth_rendering()
                self.renderer.update_scene(self.data, camera="overhead")
                self.frames.append(self.renderer.render().copy())

    def _cube_geom_ids(self) -> set[int]:
        """Return all collision geom IDs belonging to the cube (single-core or 26-cubie)."""
        if getattr(self, "_cached_cube_geom_model", None) is not self.model:
            ids: set[int] = set()
            for idx in range(self.model.ngeom):
                name = self.mujoco.mj_id2name(self.model, self.mujoco.mjtObj.mjOBJ_GEOM, idx) or ""
                if name in {"cube_core", "u_layer_core"} or (
                    name.startswith("cubie_") and "_sticker_" not in name
                ):
                    ids.add(idx)
            self._cached_cube_geom_ids = ids
            self._cached_cube_geom_model = self.model
        return self._cached_cube_geom_ids

    def _cube_touches_geom(self, geom_name: str) -> bool:
        target = self._id(self.mujoco.mjtObj.mjOBJ_GEOM, geom_name)
        cube_ids = self._cube_geom_ids()
        for index in range(self.data.ncon):
            contact = self.data.contact[index]
            pair = {int(contact.geom1), int(contact.geom2)}
            if target in pair and bool(pair & cube_ids):
                return True
        return False

    def _action_chunk_executor(self) -> ActionChunkExecutor:
        if (
            getattr(self, "_cached_chunk_executor_model", None) is not self.model
            or self._cached_chunk_executor is None
            or self._cached_chunk_executor.data is not self.data
        ):
            self._cached_chunk_executor = ActionChunkExecutor(
                self.model,
                self.data,
                step_fn=self.step_physics,
                revision_provider_fn=lambda: (self._world_state_revision, self._plan_version),
                held_object_ok_fn=self._bilateral_finger_contact,
            )
            self._cached_chunk_executor_model = self.model
        return self._cached_chunk_executor

    def _finger_contacts(self) -> set[int]:
        cube_ids = self._cube_geom_ids()
        left = self._id(self.mujoco.mjtObj.mjOBJ_GEOM, "left_finger_pad")
        right = self._id(self.mujoco.mjtObj.mjOBJ_GEOM, "right_finger_pad")
        touched: set[int] = set()
        for index in range(self.data.ncon):
            contact = self.data.contact[index]
            pair = {int(contact.geom1), int(contact.geom2)}
            if pair & cube_ids:
                touched |= pair & {left, right}
        return touched

    def _finger_contact_forces(self) -> tuple[bool, bool, float, float]:
        """Read physical pad/cube contacts and solved normal forces."""
        cube_ids = self._cube_geom_ids()
        left = self._id(self.mujoco.mjtObj.mjOBJ_GEOM, "left_finger_pad")
        right = self._id(self.mujoco.mjtObj.mjOBJ_GEOM, "right_finger_pad")
        touched = {left: False, right: False}
        forces = {left: 0.0, right: 0.0}
        wrench = np.zeros(6)
        for index in range(self.data.ncon):
            contact = self.data.contact[index]
            pair = {int(contact.geom1), int(contact.geom2)}
            if not (pair & cube_ids):
                continue
            for pad in (left, right):
                if pad in pair:
                    touched[pad] = True
                    self.mujoco.mj_contactForce(self.model, self.data, index, wrench)
                    forces[pad] += max(0.0, float(wrench[0]))
        return touched[left], touched[right], forces[left], forces[right]

    def _contact_debug_sample(self, phase: str) -> dict[str, object]:
        """Capture contact-level state from MuJoCo without privileged control input."""
        cube = self._id(self.mujoco.mjtObj.mjOBJ_BODY, "cube")
        gripper = self._id(self.mujoco.mjtObj.mjOBJ_BODY, "gripper")
        cube_ids = self._cube_geom_ids()
        pad_ids = {
            "left": self._id(self.mujoco.mjtObj.mjOBJ_GEOM, "left_finger_pad"),
            "right": self._id(self.mujoco.mjtObj.mjOBJ_GEOM, "right_finger_pad"),
        }
        contacts: dict[str, list[dict[str, object]]] = {"left": [], "right": []}
        all_cube_contacts: list[dict[str, object]] = []
        wrench = np.zeros(6)
        for index in range(self.data.ncon):
            contact = self.data.contact[index]
            pair = {int(contact.geom1), int(contact.geom2)}
            if not (pair & cube_ids) or pair.issubset(cube_ids):
                continue
            other = next(iter(pair - cube_ids))
            self.mujoco.mj_contactForce(self.model, self.data, index, wrench)
            all_cube_contacts.append({
                "other_geom": self.mujoco.mj_id2name(
                    self.model, self.mujoco.mjtObj.mjOBJ_GEOM, other
                ),
                "point_world_m": np.asarray(contact.pos, dtype=float).tolist(),
                "distance_m": float(contact.dist),
                "normal_force_n": max(0.0, float(wrench[0])),
            })
            for side, pad in pad_ids.items():
                if pad not in pair:
                    continue
                self.mujoco.mj_contactForce(self.model, self.data, index, wrench)
                normal = np.asarray(contact.frame[:3], dtype=float)
                if int(contact.geom2) == pad:
                    normal = -normal
                contacts[side].append({
                    "point_world_m": np.asarray(contact.pos, dtype=float).tolist(),
                    "normal_toward_pad": normal.tolist(),
                    "distance_m": float(contact.dist),
                    "normal_force_n": max(0.0, float(wrench[0])),
                })
        left_pad = self.data.geom_xpos[pad_ids["left"]]
        right_pad = self.data.geom_xpos[pad_ids["right"]]
        jaw_gap = max(0.0, float(np.linalg.norm(left_pad - right_pad) - .024))
        cube_position = self.data.xpos[cube].copy()
        # MuJoCo spatial velocity ordering is angular xyz followed by linear xyz.
        cube_spatial_velocity = self.data.cvel[cube].copy()
        if self._trace_reference_cube_position is None:
            self._trace_reference_cube_position = cube_position.copy()
        relative = self._relative_cube_position()
        sample = {
            "time_s": float(self.data.time),
            "phase": phase,
            "contacts": contacts,
            "all_cube_contacts": all_cube_contacts,
            "unexpected_gripper_contacts": [
                item for item in all_cube_contacts
                if item["other_geom"] not in {
                    "left_finger_pad", "right_finger_pad", "table", "floor"
                }
            ],
            "left_contact_count": len(contacts["left"]),
            "right_contact_count": len(contacts["right"]),
            "left_normal_force_n": sum(float(item["normal_force_n"]) for item in contacts["left"]),
            "right_normal_force_n": sum(float(item["normal_force_n"]) for item in contacts["right"]),
            "minimum_left_distance_m": min(
                (float(item["distance_m"]) for item in contacts["left"]), default=None
            ),
            "minimum_right_distance_m": min(
                (float(item["distance_m"]) for item in contacts["right"]), default=None
            ),
            "cube_position_world_m": cube_position.tolist(),
            "cube_quaternion_wxyz": self.data.xquat[cube].copy().tolist(),
            "cube_rotation_world": self.data.xmat[cube].copy().reshape(3, 3).tolist(),
            "cube_linear_velocity_world_m_s": cube_spatial_velocity[3:].tolist(),
            "cube_angular_velocity_world_rad_s": cube_spatial_velocity[:3].tolist(),
            "cube_displacement_from_pregrasp_m": float(np.linalg.norm(
                cube_position - self._trace_reference_cube_position
            )),
            "gripper_position_world_m": self.data.xpos[gripper].copy().tolist(),
            "jaw_inner_gap_m": jaw_gap,
            "left_finger_qpos_m": float(
                self.data.qpos[self.model.jnt_qposadr[self._joint("left_finger_joint")]]
            ),
            "right_finger_qpos_m": float(
                self.data.qpos[self.model.jnt_qposadr[self._joint("right_finger_joint")]]
            ),
            "relative_cube_position_gripper_m": relative.tolist(),
            "relative_slip_from_pregrasp_m": float(np.linalg.norm(
                relative - np.asarray(self.contact_debug_trace[0][
                    "relative_cube_position_gripper_m"
                ])
            )) if self.contact_debug_trace else 0.0,
            "relative_slip_from_bilateral_contact_m": (
                float(np.linalg.norm(relative - self._trace_contact_reference_relative))
                if self._trace_contact_reference_relative is not None else None
            ),
        }
        self.contact_debug_trace.append(sample)
        if self.experiment_run is not None:
            self.experiment_run.contacts.record_sample(
                sample,
                trajectory_id=self._active_trajectory_id,
                grasp_target_id=(
                    self._active_grasp_target.grasp_target_id
                    if self._active_grasp_target is not None else None
                ),
                skill_execution_id=self._active_skill_execution_id,
                contact_verification_id=self._active_contact_verification_id,
            )
        return sample

    def classify_contact_failure(self) -> str | None:
        if self.last_grasp_telemetry.success:
            return None
        trace = self.contact_debug_trace
        if not trace:
            return "geometric_misalignment"
        max_displacement = max(float(item["cube_displacement_from_pregrasp_m"]) for item in trace)
        max_force = max(
            max(float(item["left_normal_force_n"]), float(item["right_normal_force_n"]))
            for item in trace
        )
        ever_left = any(int(item["left_contact_count"]) > 0 for item in trace)
        ever_right = any(int(item["right_contact_count"]) > 0 for item in trace)
        if any(item["unexpected_gripper_contacts"] for item in trace):
            return "geometric_misalignment"
        final = trace[-1]
        if self.last_grasp_telemetry.failure_reason and "trial lift" in self.last_grasp_telemetry.failure_reason:
            return "trial_lift_slip_or_contact_loss"
        if self.last_grasp_telemetry.failure_reason and "full lift" in self.last_grasp_telemetry.failure_reason:
            return "insufficient_grip_force" if min(
                self.last_grasp_telemetry.left_normal_force_n,
                self.last_grasp_telemetry.right_normal_force_n,
            ) < self.grasp_config.minimum_normal_force_n else "contact_numerical_instability"
        if ever_left != ever_right and max_displacement > .015:
            return "single_side_contact_pushed_object"
        if float(final["jaw_inner_gap_m"]) > .125:
            return "gripper_closure_insufficient"
        if max_force > 50 or sum(
            int(item["left_contact_count"] > 0) != int(item["right_contact_count"] > 0)
            for item in trace
        ) > 30:
            return "contact_numerical_instability"
        if not ever_left and not ever_right:
            return "geometric_misalignment"
        if min(
            self.last_grasp_telemetry.left_normal_force_n,
            self.last_grasp_telemetry.right_normal_force_n,
        ) < self.grasp_config.minimum_normal_force_n:
            return "insufficient_grip_force"
        return "bilateral_contact_not_sustained"

    def _geoms_touch(self, first_name: str, second_name: str) -> bool:
        first = self._id(self.mujoco.mjtObj.mjOBJ_GEOM, first_name)
        second = self._id(self.mujoco.mjtObj.mjOBJ_GEOM, second_name)
        for index in range(self.data.ncon):
            contact = self.data.contact[index]
            if {int(contact.geom1), int(contact.geom2)} == {first, second}:
                return True
        return False

    def _bilateral_finger_contact(self) -> bool:
        left = self._id(self.mujoco.mjtObj.mjOBJ_GEOM, "left_finger_pad")
        right = self._id(self.mujoco.mjtObj.mjOBJ_GEOM, "right_finger_pad")
        return self._finger_contacts() == {left, right}

    def _relative_cube_position(self) -> np.ndarray:
        gripper = self._id(self.mujoco.mjtObj.mjOBJ_BODY, "gripper")
        cube = self._id(self.mujoco.mjtObj.mjOBJ_BODY, "cube")
        rotation = self.data.xmat[gripper].reshape(3, 3)
        return rotation.T @ (self.data.xpos[cube] - self.data.xpos[gripper])

    def _cube_height(self) -> float:
        cube = self._id(self.mujoco.mjtObj.mjOBJ_BODY, "cube")
        return float(self.data.xpos[cube, 2])

    def _monitored_motion(
        self, targets: dict[str, float], seconds: float, phase: str = "MOTION"
    ) -> _MotionDiagnostics:
        for name, target in targets.items():
            self.data.ctrl[self._actuator(name)] = target
        initial = self._relative_cube_position().copy()
        bilateral = left_count = right_count = 0
        left_force = right_force = 0.0
        max_slip = 0.0
        steps = int(seconds / self.model.opt.timestep)
        for step in range(steps):
            self.step_physics()
            left, right, left_n, right_n = self._finger_contact_forces()
            left_count += int(left)
            right_count += int(right)
            bilateral += int(left and right)
            left_force += left_n
            right_force += right_n
            max_slip = max(max_slip, float(np.linalg.norm(self._relative_cube_position() - initial)))
            if step % max(1, steps // 20) == 0 or step == steps - 1:
                self._contact_debug_sample(phase)
            if self.legacy_recording and step % max(1, steps // 12) == 0:
                self.renderer.update_scene(self.data, camera="overhead")
                self.frames.append(self.renderer.render().copy())
        denominator = max(steps, 1)
        return _MotionDiagnostics(
            bilateral / denominator, left_count / denominator, right_count / denominator,
            left_force / denominator, right_force / denominator, max_slip,
        )

    def _monitored_rotation(self, actuator: str, target: float,
                            seconds: float = 4.0) -> _MotionDiagnostics:
        control = self._actuator(actuator)
        start_target = float(self.data.ctrl[control])
        initial = self._relative_cube_position().copy()
        bilateral = left_count = right_count = 0
        left_force = right_force = 0.0
        max_slip = 0.0
        steps = int(seconds / self.model.opt.timestep)
        for step in range(steps):
            phase = (step + 1) / steps
            smooth = phase * phase * (3 - 2 * phase)
            self.data.ctrl[control] = start_target + (target - start_target) * smooth
            self.step_physics()
            left, right, left_n, right_n = self._finger_contact_forces()
            left_count += int(left)
            right_count += int(right)
            bilateral += int(left and right)
            left_force += left_n
            right_force += right_n
            max_slip = max(max_slip, float(np.linalg.norm(self._relative_cube_position() - initial)))
            if step % max(1, steps // 20) == 0 or step == steps - 1:
                self._contact_debug_sample("ROTATE")
            if self.legacy_recording and step % max(1, steps // 18) == 0:
                self.renderer.update_scene(self.data, camera="overhead")
                self.frames.append(self.renderer.render().copy())
        denominator = max(steps, 1)
        return _MotionDiagnostics(
            bilateral / denominator, left_count / denominator, right_count / denominator,
            left_force / denominator, right_force / denominator, max_slip,
        )

    @staticmethod
    def _wrapped_angle_distance(first: float, second: float, period: float) -> float:
        return abs((first - second + period / 2) % period - period / 2)

    @staticmethod
    def _axis_rotation(axis: np.ndarray, radians: float) -> np.ndarray:
        axis = np.asarray(axis, dtype=float)
        axis /= np.linalg.norm(axis)
        x, y, z = axis
        skew = np.array([[0, -z, y], [z, 0, -x], [-y, x, 0]])
        return np.eye(3) + math.sin(radians) * skew + (1 - math.cos(radians)) * (skew @ skew)

    def _gripper_obstacle_clearance(
        self,
        target_x: float,
        target_y: float,
        target_z: float,
        wrist_yaw: float,
        *,
        margin_m: float = 0.020,
    ) -> tuple[bool, str | None]:
        """Exact 2D OBB Separating Axis Theorem check for open pregrasp pads against scene fixtures."""
        if not hasattr(self, "mujoco") or not hasattr(self.model, "geom_size"):
            return True, None
        config = self.grasp_config
        pregrasp_ctrl = min(.067, max(0.0, (.256 - config.pregrasp_gap_m) / 2))
        d = 0.14 - pregrasp_ctrl
        pad_hx = 0.075 + margin_m
        pad_hy = 0.012 + margin_m
        c, s = math.cos(wrist_yaw), math.sin(wrist_yaw)
        u_pad = np.array([c, s], dtype=float)
        v_pad = np.array([-s, c], dtype=float)
        z_pad_min = float(target_z) - 0.045
        z_pad_max = float(target_z) + 0.075

        pad_centers = (
            np.array([target_x - s * (-d), target_y + c * (-d)], dtype=float),
            np.array([target_x - s * d, target_y + c * d], dtype=float),
        )
        obstacle_names = (
            "base_pos_pad",
            "base_neg_pad",
            "turn_pos_pad",
            "turn_neg_pad",
            "human_left_pad",
            "human_right_pad",
        )
        for obs_name in obstacle_names:
            gid = self.mujoco.mj_name2id(self.model, self.mujoco.mjtObj.mjOBJ_GEOM, obs_name)
            if gid < 0 or int(self.model.geom_contype[gid]) == 0:
                continue
            opos = self.data.geom_xpos[gid]
            omat = self.data.geom_xmat[gid].reshape(3, 3)
            osize = self.model.geom_size[gid]
            oz_half = float(np.sum(np.abs(omat[2, :3]) * osize[:3]))
            if float(opos[2]) + oz_half < z_pad_min or float(opos[2]) - oz_half > z_pad_max:
                continue
            obs_c = np.array([float(opos[0]), float(opos[1])], dtype=float)
            u_obs = omat[:2, 0] / max(1e-9, float(np.linalg.norm(omat[:2, 0])))
            v_obs = omat[:2, 1] / max(1e-9, float(np.linalg.norm(omat[:2, 1])))
            ox, oy = float(osize[0]), float(osize[1])
            axes = (u_pad, v_pad, u_obs, v_obs)
            for p_c in pad_centers:
                delta = obs_c - p_c
                separated = False
                for ax in axes:
                    r_pad = pad_hx * abs(float(np.dot(u_pad, ax))) + pad_hy * abs(float(np.dot(v_pad, ax)))
                    r_obs = ox * abs(float(np.dot(u_obs, ax))) + oy * abs(float(np.dot(v_obs, ax)))
                    if abs(float(np.dot(delta, ax))) > r_pad + r_obs:
                        separated = True
                        break
                if not separated:
                    return False, f"pregrasp pad overlaps {obs_name}"
        return True, None

    def generate_grasp_candidates(
        self, target_xyz: tuple[float, float, float], cube_yaw: float
    ) -> tuple[GraspCandidate, ...]:
        """Generate opposing-face grasps and score IK, clearance and alignment.

        The gripper closes along its local Y axis. A square has two equivalent
        opposing face pairs, hence the two wrist-yaw candidates separated by 90°.
        """
        with self.truth_boundary.scope(
            TruthAccessCategory.RUNTIME_LOCALIZATION_FORBIDDEN, "generate_grasp_candidates"
        ):
            x, y, z = target_xyz
            current_yaw = float(self.data.qpos[self.model.jnt_qposadr[self._joint("wrist_yaw_joint")]])
            candidates: list[GraspCandidate] = []
            for offset, face_pair in ((0.0, "local_y_faces"), (math.pi / 2, "local_x_faces")):
                wrist_yaw = (cube_yaw + offset + math.pi) % (2 * math.pi) - math.pi
                ik_feasible = abs(x) <= .64 and abs(y) <= .51 and .60 <= z <= .78
                # The 15 cm wide palm and 12 cm cube must remain inside the table
                # throughout the vertical approach. This is a conservative analytic
                # collision check for this Cartesian arm.
                radial_clearance = min(.8 - abs(x), .65 - abs(y))
                obs_clear, obs_reason = (
                    self._gripper_obstacle_clearance(x, y, z, wrist_yaw)
                    if hasattr(self, "_gripper_obstacle_clearance")
                    else (True, None)
                )
                collision_free = radial_clearance >= .10 and obs_clear
                alignment_error = self._wrapped_angle_distance(wrist_yaw, cube_yaw + offset, math.pi)
                geometry_score = max(0.0, math.cos(2 * alignment_error))
                motion_cost = self._wrapped_angle_distance(wrist_yaw, current_yaw, 2 * math.pi)
                rejection = None
                if not ik_feasible:
                    rejection = "IK target outside Cartesian joint limits"
                elif not obs_clear:
                    rejection = obs_reason
                elif not collision_free:
                    rejection = "insufficient table-edge/palm clearance"
                candidates.append(GraspCandidate(
                    wrist_yaw, face_pair, ik_feasible, collision_free,
                    geometry_score, motion_cost, rejection,
                ))
            self.last_grasp_candidates = tuple(candidates)
            return self.last_grasp_candidates

    def select_grasp_candidate(
        self, target_xyz: tuple[float, float, float], cube_yaw: float
    ) -> GraspCandidate | None:
        feasible = [candidate for candidate in self.generate_grasp_candidates(target_xyz, cube_yaw)
                    if candidate.ik_feasible and candidate.collision_free]
        if not feasible:
            self.last_selected_grasp_candidate = None
            return None
        self.last_selected_grasp_candidate = max(
            feasible, key=lambda item: (item.contact_geometry_score, -item.motion_cost)
        )
        return self.last_selected_grasp_candidate

    def select_grasp_candidate_6d(self, pose: "CubePose6D") -> GraspCandidate | None:
        """Select a horizontal opposing-face grasp from a visual 6-D pose."""
        rotation = np.asarray(pose.rotation_cube_to_world, dtype=float)
        x, y, z = pose.center_world_m
        current_yaw = float(self.data.qpos[self.model.jnt_qposadr[self._joint("wrist_yaw_joint")]])
        candidates: list[GraspCandidate] = []
        for axis_index, face_pair in enumerate(("local_x_faces", "local_y_faces", "local_z_faces")):
            closure = rotation[:, axis_index]
            horizontal = float(np.linalg.norm(closure[:2]))
            wrist_yaw = math.atan2(float(closure[1]), float(closure[0])) - math.pi / 2
            wrist_yaw = (wrist_yaw + math.pi) % (2 * math.pi) - math.pi
            ik_feasible = abs(x) <= .64 and abs(y) <= .51 and .60 <= z <= .78
            radial_ok = min(.8 - abs(x), .65 - abs(y)) >= .10
            obs_clear, obs_reason = (
                self._gripper_obstacle_clearance(x, y, z, wrist_yaw)
                if hasattr(self, "_gripper_obstacle_clearance")
                else (True, None)
            )
            collision_free = radial_ok and obs_clear
            rejection = None
            if horizontal < .82:
                rejection = "opposing faces are too vertical for top-down gripper"
            elif not ik_feasible:
                rejection = "IK target outside Cartesian joint limits"
            elif not obs_clear:
                rejection = obs_reason
            elif not collision_free:
                rejection = "insufficient table-edge/palm clearance"
            candidates.append(GraspCandidate(
                wrist_yaw, face_pair, ik_feasible and horizontal >= .82,
                collision_free, horizontal,
                self._wrapped_angle_distance(wrist_yaw, current_yaw, 2 * math.pi), rejection,
            ))
        self.last_grasp_candidates = tuple(candidates)
        feasible = [item for item in candidates if item.ik_feasible and item.collision_free]
        self.last_selected_grasp_candidate = (
            max(feasible, key=lambda item: (item.contact_geometry_score, -item.motion_cost))
            if feasible else None
        )
        return self.last_selected_grasp_candidate

    def _halt_cartesian_stage(self) -> None:
        """Hold the measured Cartesian pose after a safety-stop condition."""
        for actuator_name, joint_name in (
            ("robot_x_ctrl", "robot_x_joint"),
            ("robot_y_ctrl", "robot_y_joint"),
            ("robot_z_ctrl", "robot_z_joint"),
            ("wrist_yaw_ctrl", "wrist_yaw_joint"),
        ):
            address = self.model.jnt_qposadr[self._joint(joint_name)]
            self.data.ctrl[self._actuator(actuator_name)] = self.data.qpos[address]

    def _guarded_stage_motion(
        self, targets: dict[str, float], seconds: float, phase: str,
        *, guarded: bool = True,
    ) -> tuple[bool, str | None]:
        """Move while enforcing approach collision and object-motion guards."""
        starts = {
            name: float(self.data.ctrl[self._actuator(name)]) for name in targets
        }
        reference = self.data.xpos[
            self._id(self.mujoco.mjtObj.mjOBJ_BODY, "cube")
        ].copy()
        steps = max(1, int(seconds / self.model.opt.timestep))
        for step in range(steps):
            progress = (step + 1) / steps
            smooth = progress * progress * (3 - 2 * progress)
            for name, target in targets.items():
                self.data.ctrl[self._actuator(name)] = (
                    starts[name] + (target - starts[name]) * smooth
                )
            self.step_physics()
            if guarded:
                cube_position = self.data.xpos[
                    self._id(self.mujoco.mjtObj.mjOBJ_BODY, "cube")
                ]
                displacement_now = float(np.linalg.norm(cube_position - reference))
                pad_contact_now = bool(self._finger_contacts())
                unexpected_now = self._cube_touches_geom("palm")
                if unexpected_now or pad_contact_now:
                    self._contact_debug_sample(phase)
                    self._halt_cartesian_stage()
                    return False, "APPROACH_UNEXPECTED_COLLISION"
                if displacement_now > self.grasp_config.approach_displacement_limit_m:
                    self._contact_debug_sample(phase)
                    self._halt_cartesian_stage()
                    return False, "APPROACH_OBJECT_DISPLACED"
                if step % max(1, steps // 20) == 0 or step == steps - 1:
                    sample = self._contact_debug_sample(phase)
                    displacement = float(np.linalg.norm(
                        np.asarray(sample["cube_position_world_m"]) - reference
                    ))
                    pad_contact = (
                        int(sample["left_contact_count"]) > 0
                        or int(sample["right_contact_count"]) > 0
                    )
                    unexpected = bool(sample["unexpected_gripper_contacts"])
                    if unexpected or pad_contact:
                        self._halt_cartesian_stage()
                        return False, "APPROACH_UNEXPECTED_COLLISION"
                    if displacement > self.grasp_config.approach_displacement_limit_m:
                        self._halt_cartesian_stage()
                        return False, "APPROACH_OBJECT_DISPLACED"
            if self.legacy_recording and step % max(1, steps // 12) == 0:
                self.renderer.update_scene(self.data, camera="overhead")
                self.frames.append(self.renderer.render().copy())
        return True, None

    def _guarded_xy_trapezoidal_motion(
        self,
        target_x: float,
        target_y: float,
        z_hover: float,
        phase: str,
        *,
        guarded: bool = True,
        v_max: float = 0.22,
        a_max: float = 0.85,
        kd_xy: float = 0.14,
        pos_tol: float = 0.004,
        vel_tol: float = 0.015,
        max_settle_seconds: float = 1.2,
    ) -> tuple[bool, str | None]:
        """Execute Euclidean trapezoidal XY planning with active damping and convergence gate."""
        x_joint = self._joint("robot_x_joint")
        y_joint = self._joint("robot_y_joint")
        x_qpos = int(self.model.jnt_qposadr[x_joint])
        y_qpos = int(self.model.jnt_qposadr[y_joint])
        x_qvel = int(self.model.jnt_dofadr[x_joint])
        y_qvel = int(self.model.jnt_dofadr[y_joint])
        x_low, x_high = (float(v) for v in self.model.jnt_range[x_joint])
        y_low, y_high = (float(v) for v in self.model.jnt_range[y_joint])
        goal_x = float(np.clip(target_x, x_low, x_high))
        goal_y = float(np.clip(target_y, y_low, y_high))
        start_x = float(self.data.qpos[x_qpos])
        start_y = float(self.data.qpos[y_qpos])
        z_joint = self._joint("robot_z_joint")
        z_qpos = int(self.model.jnt_qposadr[z_joint])
        # Ensure gripper is safely above the cube before traversing XY
        if float(self.data.qpos[z_qpos]) < z_hover - 0.06:
            if guarded:
                ok_lift, fail_lift = self._guarded_stage_motion(
                    {"robot_z_ctrl": float(z_hover)}, 0.35, phase,
                )
                if not ok_lift:
                    return False, fail_lift
            else:
                self._set_controls({"robot_z_ctrl": float(z_hover)}, 0.35)

        cube_body = self._id(self.mujoco.mjtObj.mjOBJ_BODY, "cube")
        reference = self.data.xpos[cube_body].copy()
        chunk = ActionChunk.trapezoidal_xy(
            chunk_id=f"{phase.lower()}_{uuid.uuid4().hex[:8]}",
            start_xy=(start_x, start_y),
            goal_xy=(goal_x, goal_y),
            dt=float(self.model.opt.timestep),
            v_max=v_max,
            a_max=a_max,
            min_duration_s=0.35,
            max_duration_s=2.0,
            hold_grip_on_interrupt=False,
            kd_xy=kd_xy,
            extra_ctrls={"robot_z_ctrl": float(z_hover)},
            world_revision=self._world_state_revision,
            goal_revision=self._plan_version,
        )
        total_steps = max(1, len(chunk.targets))
        sample_stride = max(1, total_steps // 20)

        def _guard_step(step_idx: int) -> str | None:
            if not guarded:
                return None
            cube_pos = self.data.xpos[cube_body]
            disp_now = float(np.linalg.norm(cube_pos - reference))
            if self._cube_touches_geom("palm") or bool(self._finger_contacts()):
                self._contact_debug_sample(phase)
                return "APPROACH_UNEXPECTED_COLLISION"
            if disp_now > self.grasp_config.approach_displacement_limit_m:
                self._contact_debug_sample(phase)
                return "APPROACH_OBJECT_DISPLACED"
            if step_idx % sample_stride == 0 or step_idx == total_steps - 1:
                sample = self._contact_debug_sample(phase)
                if bool(sample["unexpected_gripper_contacts"]) or (
                    int(sample["left_contact_count"]) > 0 or int(sample["right_contact_count"]) > 0
                ):
                    return "APPROACH_UNEXPECTED_COLLISION"
                if float(np.linalg.norm(np.asarray(sample["cube_position_world_m"]) - reference)) > self.grasp_config.approach_displacement_limit_m:
                    return "APPROACH_OBJECT_DISPLACED"
            if self.legacy_recording and step_idx % max(1, total_steps // 12) == 0:
                self.renderer.update_scene(self.data, camera="overhead")
                self.frames.append(self.renderer.render().copy())
            return None

        executor = self._action_chunk_executor()
        result = executor.execute(chunk, token=self.active_cancellation_token, post_step_fn=_guard_step)
        self.last_chunk_result = result
        if result.status == ChunkStatus.PREEMPTED_SAFE_HOLD:
            self._halt_cartesian_stage()
            return False, "PREEMPTED_SAFE_HOLD"
        if result.status != ChunkStatus.COMPLETED:
            self._halt_cartesian_stage()
            return False, result.safety_violation or "APPROACH_FAILED"

        # Strict XY position & velocity convergence gate before vertical Z descent
        settle_steps = max(1, int(round(max_settle_seconds / self.model.opt.timestep)))
        converged = 0
        for s_idx in range(settle_steps):
            px = float(self.data.qpos[x_qpos])
            py = float(self.data.qpos[y_qpos])
            vx = float(self.data.qvel[x_qvel])
            vy = float(self.data.qvel[y_qvel])
            if math.hypot(goal_x - px, goal_y - py) <= pos_tol and math.hypot(vx, vy) <= vel_tol:
                converged += 1
                if converged >= 2:
                    break
            else:
                converged = 0
            self.data.ctrl[self._actuator("robot_x_ctrl")] = float(np.clip(goal_x - kd_xy * vx, x_low, x_high))
            self.data.ctrl[self._actuator("robot_y_ctrl")] = float(np.clip(goal_y - kd_xy * vy, y_low, y_high))
            self.data.ctrl[self._actuator("robot_z_ctrl")] = float(z_hover)
            self.step_physics()
            if guarded:
                err = _guard_step(s_idx)
                if err is not None:
                    self._halt_cartesian_stage()
                    return False, err
        # Hold exact target at tail
        self.data.ctrl[self._actuator("robot_x_ctrl")] = goal_x
        self.data.ctrl[self._actuator("robot_y_ctrl")] = goal_y
        if guarded:
            self._contact_debug_sample(phase)
        return True, None

    def skill_approach_grasp(
        self,
        target_xyz: tuple[float, float, float],
        candidate: GraspCandidate,
        *,
        tangent_offset_m: float | None = None,
        closure_offset_m: float | None = None,
    ) -> dict[str, object]:
        """Execute a guarded pregrasp and approach without closing the fingers."""
        self.contact_debug_trace.clear()
        self.contact_failure_class = None
        self._trace_reference_cube_position = None
        self._trace_contact_reference_relative = None
        self._skill_start_height = self._cube_height()
        self._skill_phase_trace = ["PREGRASP"]
        self._last_skill_approach_diag = None
        self._last_skill_establish_diag = None
        self._last_skill_lift_diag = None
        self._last_skill_align_diag = None
        self.last_selected_grasp_candidate = candidate
        if not candidate.ik_feasible or not candidate.collision_free:
            self.last_grasp_telemetry = GraspTelemetry(
                False, 0.0, 0.0, 0.0, 0.0, "CANDIDATE_INFEASIBLE",
                selected_grasp_yaw_radians=candidate.wrist_yaw_radians,
                phase_trace=tuple(self._skill_phase_trace),
            )
            return {"success": False, "failure_code": "CANDIDATE_INFEASIBLE"}
        config = self.grasp_config
        tangent_default, closure_default = config.approach_offset_local_xy_m
        tangent = tangent_default if tangent_offset_m is None else tangent_offset_m
        closure = closure_default if closure_offset_m is None else closure_offset_m
        cosine, sine = math.cos(candidate.wrist_yaw_radians), math.sin(candidate.wrist_yaw_radians)
        offset_x = cosine * tangent - sine * closure
        offset_y = sine * tangent + cosine * closure
        x, y, _ = target_xyz
        target_x = x + offset_x
        target_y = y + offset_y
        if self.experiment_run is not None:
            cv_id = self.experiment_run.contacts.begin_verification()
            self._active_contact_verification_id = cv_id
            grasp_id = (
                self._active_grasp_target.grasp_target_id
                if self._active_grasp_target is not None else None
            )
            traj_id = self.experiment_run.trajectories.begin_trajectory(
                grasp_target_id=grasp_id,
                skill_execution_id=self._active_skill_execution_id,
                ee_target={
                    "x_m": float(target_x),
                    "y_m": float(target_y),
                    "z_m": float(config.contact_z_ctrl),
                    "yaw_rad": float(candidate.wrist_yaw_radians),
                },
                phase="PREGRASP",
            )
            self._active_trajectory_id = traj_id
            self.experiment_run.trajectories.sample_backend_step(self, force=True)
        pregrasp_ctrl = min(.067, max(0.0, (.256 - config.pregrasp_gap_m) / 2))
        if self.experiment_run is not None:
            self.experiment_run.trajectories.set_phase("PREGRASP")
            self.experiment_run.trajectories.record_command(
                sim_time=float(self.data.time),
                phase="PREGRASP",
                ctrl={"left_finger_ctrl": pregrasp_ctrl, "right_finger_ctrl": pregrasp_ctrl},
            )
        self._set_controls({
            "left_finger_ctrl": pregrasp_ctrl,
            "right_finger_ctrl": pregrasp_ctrl,
        }, .25)
        self._contact_debug_sample("PREGRASP")
        self._skill_phase_trace.append("ALIGN")
        if self.experiment_run is not None:
            self.experiment_run.trajectories.set_phase("ALIGN")
            self.experiment_run.trajectories.record_command(
                sim_time=float(self.data.time),
                phase="ALIGN",
                ctrl={"wrist_yaw_ctrl": candidate.wrist_yaw_radians, "wrist_pitch_ctrl": 0.0},
            )
        z_cur = float(self.data.qpos[self.model.jnt_qposadr[self._joint("robot_z_joint")]])
        if z_cur < -0.18:
            self._set_controls({"robot_z_ctrl": -0.145}, .35)
        self._set_controls({
            "robot_z_ctrl": -0.145,
            "wrist_yaw_ctrl": candidate.wrist_yaw_radians,
            "wrist_pitch_ctrl": 0.0,
        }, .7)
        self._skill_phase_trace.append("APPROACH")
        if self.experiment_run is not None:
            self.experiment_run.trajectories.set_phase("APPROACH")
            self.experiment_run.trajectories.record_command(
                sim_time=float(self.data.time),
                phase="APPROACH",
                ctrl={"robot_x_ctrl": target_x, "robot_y_ctrl": target_y, "robot_z_ctrl": -.145},
                cartesian_target=(target_x, target_y, -0.145),
            )
        ok, failure = self._guarded_xy_trapezoidal_motion(
            target_x, target_y, -.145, "APPROACH", guarded=True,
        )
        if ok:
            if self.experiment_run is not None:
                self.experiment_run.trajectories.record_command(
                    sim_time=float(self.data.time),
                    phase="APPROACH",
                    ctrl={"robot_z_ctrl": config.contact_z_ctrl},
                    cartesian_target=(target_x, target_y, float(config.contact_z_ctrl)),
                )
            ok, failure = self._guarded_stage_motion(
                {
                    "robot_x_ctrl": target_x,
                    "robot_y_ctrl": target_y,
                    "robot_z_ctrl": config.contact_z_ctrl,
                },
                .65,
                "APPROACH",
            )
        final = self.contact_debug_trace[-1]
        self._last_skill_approach_diag = {
            "success": ok,
            "failure_code": failure,
            "target_xy": [target_x, target_y],
            "cube_displacement_m": float(final["cube_displacement_from_pregrasp_m"]),
            "unexpected_contact_count": len(final["unexpected_gripper_contacts"]),
        }
        if not ok:
            self.last_grasp_telemetry = GraspTelemetry(
                False, 0.0, 0.0, 0.0, 0.0, failure or "APPROACH_FAILED",
                selected_grasp_yaw_radians=candidate.wrist_yaw_radians,
                phase_trace=tuple(self._skill_phase_trace),
            )
            self.contact_failure_class = self.classify_contact_failure()
        return {
            "success": ok,
            "failure_code": failure,
            "cube_displacement_m": float(final["cube_displacement_from_pregrasp_m"]),
            "unexpected_contact_count": len(final["unexpected_gripper_contacts"]),
            "left_contact_count": int(final["left_contact_count"]),
            "right_contact_count": int(final["right_contact_count"]),
        }

    def skill_establish_grasp(self) -> dict[str, object]:
        """Symmetrically close and require sustained solved bilateral contact."""
        config = self.grasp_config
        if not self._skill_phase_trace or self._skill_phase_trace[-1] != "APPROACH":
            return {"success": False, "failure_code": "APPROACH_NOT_COMPLETE"}
        self._skill_phase_trace.append("SLOW_CLOSE")
        if self.experiment_run is not None:
            self.experiment_run.trajectories.set_phase("SLOW_CLOSE")
            self.experiment_run.trajectories.record_command(
                sim_time=float(self.data.time),
                phase="SLOW_CLOSE",
                ctrl={"left_finger_ctrl": 0.074, "right_finger_ctrl": 0.074},
            )
        left_total = right_total = 0.0
        left_seen = right_seen = samples = settle = 0
        steps = max(1, int(config.close_duration_seconds / self.model.opt.timestep))
        confirm_steps = max(1, int(config.bilateral_confirm_seconds / self.model.opt.timestep))
        start = float(self.data.ctrl[self._actuator("left_finger_ctrl")])
        selected_yaw = (
            self.last_selected_grasp_candidate.wrist_yaw_radians
            if self.last_selected_grasp_candidate is not None else None
        )
        for step in range(steps):
            target = start + (.074 - start) * min(1.0, (step + 1) / (steps * .75))
            self.data.ctrl[self._actuator("left_finger_ctrl")] = target
            self.data.ctrl[self._actuator("right_finger_ctrl")] = target
            self.step_physics()
            left, right, left_n, right_n = self._finger_contact_forces()
            samples += 1
            left_seen += int(left)
            right_seen += int(right)
            left_total += left_n
            right_total += right_n
            if step % max(1, steps // 30) == 0 or step == steps - 1:
                self._contact_debug_sample("SLOW_CLOSE")
            settle = settle + 1 if left and right else 0
            if (
                settle >= confirm_steps
                and left_n >= config.minimum_normal_force_n
                and right_n >= config.minimum_normal_force_n
            ):
                self._skill_phase_trace.extend(["BILATERAL_CONTACT", "STABLE_HOLD"])
                self._trace_contact_reference_relative = self._relative_cube_position().copy()
                self._contact_debug_sample("BILATERAL_CONTACT")
                if self.experiment_run is not None:
                    self.experiment_run.trajectories.set_phase("STABLE_HOLD")
                    if self._active_grasp_target is not None:
                        axes = self.gripper_axes_world()
                        yaw_now = float(self.data.qpos[self.model.jnt_qposadr[self._joint("wrist_yaw_joint")]])
                        self.experiment_run.grasp_targets.update_actual_contact_pose(
                            self._active_grasp_target.grasp_target_id,
                            {
                                "position_world_m": axes["position_world_m"],
                                "wrist_yaw_rad": yaw_now,
                                "sim_time": float(self.data.time),
                            },
                        )
                hold = self._monitored_motion({}, config.stable_hold_seconds, "STABLE_HOLD")
                success = (
                    hold.bilateral_rate >= .95
                    and min(hold.left_force_n, hold.right_force_n)
                    >= config.minimum_normal_force_n
                )
                self._last_skill_establish_diag = {
                    "success": success,
                    "bilateral_rate": hold.bilateral_rate,
                    "left_rate": hold.left_rate,
                    "right_rate": hold.right_rate,
                    "left_force_n": hold.left_force_n,
                    "right_force_n": hold.right_force_n,
                    "max_slip_m": hold.max_slip_m,
                }
                if not success:
                    self.last_grasp_telemetry = GraspTelemetry(
                        False, hold.bilateral_rate, hold.max_slip_m, 0.0, 0.0,
                        "BILATERAL_CONTACT_UNSTABLE",
                        hold.left_rate, hold.right_rate, hold.left_force_n, hold.right_force_n,
                        False, False, False, selected_yaw, tuple(self._skill_phase_trace),
                    )
                    self.contact_failure_class = self.classify_contact_failure()
                return {
                    "success": success,
                    "failure_code": None if success else "BILATERAL_CONTACT_UNSTABLE",
                    "bilateral_contact_fraction": hold.bilateral_rate,
                    "left_contact_rate": hold.left_rate,
                    "right_contact_rate": hold.right_rate,
                    "left_normal_force_n": hold.left_force_n,
                    "right_normal_force_n": hold.right_force_n,
                    "max_slip_m": hold.max_slip_m,
                }
        left_rate = left_seen / max(samples, 1)
        right_rate = right_seen / max(samples, 1)
        left_f = left_total / max(samples, 1)
        right_f = right_total / max(samples, 1)
        self._last_skill_establish_diag = {
            "success": False,
            "bilateral_rate": 0.0,
            "left_rate": left_rate,
            "right_rate": right_rate,
            "left_force_n": left_f,
            "right_force_n": right_f,
            "max_slip_m": 0.0,
        }
        self.last_grasp_telemetry = GraspTelemetry(
            False, 0.0, 0.0, 0.0, 0.0, "BILATERAL_CONTACT_NOT_ESTABLISHED",
            left_rate, right_rate, left_f, right_f,
            False, False, False, selected_yaw, tuple(self._skill_phase_trace),
        )
        self.contact_failure_class = self.classify_contact_failure()
        return {
            "success": False,
            "failure_code": "BILATERAL_CONTACT_NOT_ESTABLISHED",
            "left_contact_rate": left_rate,
            "right_contact_rate": right_rate,
            "left_normal_force_n": left_f,
            "right_normal_force_n": right_f,
            "max_slip_m": 0.0,
        }

    def skill_test_lift(self) -> dict[str, object]:
        """Trial lift and full lift; impossible to call without bilateral hold."""
        config = self.grasp_config
        if not self._skill_phase_trace or self._skill_phase_trace[-1] != "STABLE_HOLD":
            return {"success": False, "failure_code": "BILATERAL_CONTACT_REQUIRED"}
        start_height = self._skill_start_height or self._cube_height()
        selected_yaw = (
            self.last_selected_grasp_candidate.wrist_yaw_radians
            if self.last_selected_grasp_candidate is not None else None
        )
        self._skill_phase_trace.append("TRIAL_LIFT")
        if self.experiment_run is not None:
            self.experiment_run.trajectories.set_phase("TRIAL_LIFT")
            self.experiment_run.trajectories.record_command(
                sim_time=float(self.data.time),
                phase="TRIAL_LIFT",
                ctrl={"robot_z_ctrl": config.trial_z_ctrl},
            )
        trial = self._monitored_motion(
            {"robot_z_ctrl": config.trial_z_ctrl}, config.trial_seconds, "TRIAL_LIFT"
        )
        trial_height = self._cube_height() - start_height
        trial_ok = (
            trial.bilateral_rate >= .80
            and trial.max_slip_m <= config.slip_limit_m
            and trial_height >= .012
        )
        if not trial_ok:
            reason = (
                f"trial lift unstable: contact={trial.bilateral_rate:.3f}, "
                f"slip={trial.max_slip_m:.4f}m, lift={trial_height:.4f}m"
            )
            self._last_skill_lift_diag = {
                "success": False,
                "trial_lift_success": False,
                "full_lift_success": False,
                "lift_height_m": trial_height,
                "bilateral_contact_fraction": trial.bilateral_rate,
                "left_contact_rate": trial.left_rate,
                "right_contact_rate": trial.right_rate,
                "left_normal_force_n": trial.left_force_n,
                "right_normal_force_n": trial.right_force_n,
                "max_slip_m": trial.max_slip_m,
            }
            self.last_grasp_telemetry = GraspTelemetry(
                False, trial.bilateral_rate, trial.max_slip_m, trial_height, 0.0, reason,
                trial.left_rate, trial.right_rate, trial.left_force_n, trial.right_force_n,
                False, False, False, selected_yaw, tuple(self._skill_phase_trace),
            )
            self.contact_failure_class = self.classify_contact_failure()
            return {
                "success": False,
                "failure_code": "TRIAL_LIFT_UNSTABLE",
                "trial_lift_success": False,
                "full_lift_success": False,
                "lift_height_m": trial_height,
                "bilateral_contact_fraction": trial.bilateral_rate,
                "left_contact_rate": trial.left_rate,
                "right_contact_rate": trial.right_rate,
                "left_normal_force_n": trial.left_force_n,
                "right_normal_force_n": trial.right_force_n,
                "max_slip_m": trial.max_slip_m,
            }
        self._skill_phase_trace.extend(["STABILITY_CHECK", "FULL_LIFT"])
        if self.experiment_run is not None:
            self.experiment_run.trajectories.set_phase("FULL_LIFT")
            self.experiment_run.trajectories.record_command(
                sim_time=float(self.data.time),
                phase="FULL_LIFT",
                ctrl={"robot_z_ctrl": config.full_lift_z_ctrl},
            )
        lift = self._monitored_motion(
            {"robot_z_ctrl": config.full_lift_z_ctrl}, config.full_lift_seconds, "FULL_LIFT"
        )
        height = self._cube_height() - start_height
        contact = min(trial.bilateral_rate, lift.bilateral_rate)
        left_rate = min(trial.left_rate, lift.left_rate)
        right_rate = min(trial.right_rate, lift.right_rate)
        left_force_n = (trial.left_force_n + lift.left_force_n) / 2.0
        right_force_n = (trial.right_force_n + lift.right_force_n) / 2.0
        slip = max(trial.max_slip_m, lift.max_slip_m)
        success = (
            lift.bilateral_rate >= .85
            and min(left_force_n, right_force_n) >= config.minimum_normal_force_n
            and slip <= config.slip_limit_m
            and height >= .06
        )
        reason = None if success else (
            f"full lift unstable: contact={contact:.3f}, slip={slip:.4f}m, lift={height:.4f}m"
        )
        self._last_skill_lift_diag = {
            "success": success,
            "trial_lift_success": True,
            "full_lift_success": success,
            "lift_height_m": height,
            "bilateral_contact_fraction": contact,
            "trial_bilateral_contact_fraction": trial.bilateral_rate,
            "lift_bilateral_contact_fraction": lift.bilateral_rate,
            "left_contact_rate": left_rate,
            "right_contact_rate": right_rate,
            "left_normal_force_n": left_force_n,
            "right_normal_force_n": right_force_n,
            "max_slip_m": slip,
        }
        self.last_grasp_telemetry = GraspTelemetry(
            success, contact, slip, height, 0.0, reason,
            left_rate, right_rate, left_force_n, right_force_n,
            True, success, False, selected_yaw, tuple(self._skill_phase_trace),
        )
        self.contact_failure_class = self.classify_contact_failure()
        return {
            "success": success,
            "failure_code": None if success else "FULL_LIFT_UNSTABLE",
            "trial_lift_success": True,
            "full_lift_success": success,
            "lift_height_m": height,
            "bilateral_contact_fraction": contact,
            "trial_bilateral_contact_fraction": trial.bilateral_rate,
            "lift_bilateral_contact_fraction": lift.bilateral_rate,
            "left_contact_rate": left_rate,
            "right_contact_rate": right_rate,
            "left_normal_force_n": left_force_n,
            "right_normal_force_n": right_force_n,
            "max_slip_m": slip,
        }

    def skill_retreat(self) -> dict[str, object]:
        """Open the gripper and move vertically clear; never moves the cube directly."""
        self._set_controls({"left_finger_ctrl": 0, "right_finger_ctrl": 0}, .35)
        self._set_controls({"robot_z_ctrl": -.12}, .6)
        released = not any(self._finger_contact_forces()[:2])
        self._skill_phase_trace = []
        return {"success": released, "failure_code": None if released else "RELEASE_FAILED"}

    def approach_grasp_lift(
        self, target_xyz: tuple[float, float, float], target_yaw: float | None = None,
        grasp_candidate: GraspCandidate | None = None,
    ) -> bool:
        config = self.grasp_config
        x, y, _ = target_xyz
        start_height = self._cube_height()
        self.contact_debug_trace.clear()
        self.contact_failure_class = None
        self._trace_reference_cube_position = None
        self._trace_contact_reference_relative = None
        phase_trace: list[str] = ["PREGRASP"]
        selected = grasp_candidate or self.select_grasp_candidate(target_xyz, target_yaw or 0.0)
        if selected is None:
            self.last_grasp_telemetry = GraspTelemetry(
                False, 0, 0, 0, 0, "no IK/collision-feasible grasp candidate",
                phase_trace=tuple(phase_trace),
            )
            self.contact_failure_class = self.classify_contact_failure()
            return False
        pregrasp_ctrl = min(.067, max(0.0, (.256 - config.pregrasp_gap_m) / 2))
        self._set_controls({
            "left_finger_ctrl": pregrasp_ctrl,
            "right_finger_ctrl": pregrasp_ctrl,
        }, .25)
        self._contact_debug_sample("PREGRASP")
        phase_trace.append("ALIGN")
        z_cur = float(self.data.qpos[self.model.jnt_qposadr[self._joint("robot_z_joint")]])
        if z_cur < -0.18:
            self._set_controls({"robot_z_ctrl": -0.145}, .35)
        self._set_controls({"robot_z_ctrl": -0.145, "wrist_yaw_ctrl": selected.wrist_yaw_radians}, .7)
        phase_trace.append("APPROACH")
        tangent, closure = config.approach_offset_local_xy_m
        cosine, sine = math.cos(selected.wrist_yaw_radians), math.sin(selected.wrist_yaw_radians)
        offset_x = cosine * tangent - sine * closure
        offset_y = sine * tangent + cosine * closure
        self._guarded_xy_trapezoidal_motion(
            x + offset_x, y + offset_y, -.145, "APPROACH", guarded=False,
        )
        # Keep pad bottoms 2 cm above the table to avoid parasitic table friction.
        self._guarded_stage_motion(
            {
                "robot_x_ctrl": x + offset_x,
                "robot_y_ctrl": y + offset_y,
                "robot_z_ctrl": config.contact_z_ctrl,
            },
            .65,
            "APPROACH",
            guarded=False,
        )
        self._contact_debug_sample("APPROACH")
        phase_trace.append("SLOW_CLOSE")
        contact_confirmed = False
        close_left = close_right = 0
        close_left_force = close_right_force = 0.0
        close_steps = int(config.close_duration_seconds / self.model.opt.timestep)
        confirm_steps = max(1, int(config.bilateral_confirm_seconds / self.model.opt.timestep))
        bilateral_settle_steps = 0
        close_samples = 0
        for step in range(close_steps):
            # Symmetric slow closure avoids translating the free cube. Stop as
            # soon as solved bilateral forces are sustained; do not keep
            # squeezing to the position limit after contact.
            target = pregrasp_ctrl + (.074 - pregrasp_ctrl) * min(
                1.0, (step + 1) / (close_steps * .75)
            )
            self.data.ctrl[self._actuator("left_finger_ctrl")] = target
            self.data.ctrl[self._actuator("right_finger_ctrl")] = target
            self.step_physics()
            if self.legacy_recording and step % max(1, close_steps // 6) == 0:
                self.renderer.update_scene(self.data, camera="overhead")
                self.frames.append(self.renderer.render().copy())
            left, right, left_n, right_n = self._finger_contact_forces()
            close_samples += 1
            close_left += int(left)
            close_right += int(right)
            close_left_force += left_n
            close_right_force += right_n
            if step % max(1, close_steps // 30) == 0 or step == close_steps - 1:
                self._contact_debug_sample("SLOW_CLOSE")
            if left and right:
                bilateral_settle_steps += 1
                # Require sustained solved contact forces, not a one-step touch.
                if (
                    left_n >= config.minimum_normal_force_n
                    and right_n >= config.minimum_normal_force_n
                    and bilateral_settle_steps >= confirm_steps
                ):
                    contact_confirmed = True
                    break
            else:
                bilateral_settle_steps = 0
        if not contact_confirmed:
            self.last_grasp_telemetry = GraspTelemetry(
                False, 0, 0, 0, 0, "bilateral pad contact was not established",
                close_left / max(close_samples, 1), close_right / max(close_samples, 1),
                close_left_force / max(close_samples, 1),
                close_right_force / max(close_samples, 1),
                selected_grasp_yaw_radians=selected.wrist_yaw_radians,
                phase_trace=tuple(phase_trace),
            )
            self.contact_failure_class = self.classify_contact_failure()
            return False
        phase_trace.append("BILATERAL_CONTACT")
        self._trace_contact_reference_relative = self._relative_cube_position().copy()
        self._contact_debug_sample("BILATERAL_CONTACT")
        phase_trace.append("STABLE_HOLD")
        hold = self._monitored_motion({}, config.stable_hold_seconds, "STABLE_HOLD")
        if (
            hold.bilateral_rate < .95
            or min(hold.left_force_n, hold.right_force_n) < config.minimum_normal_force_n
        ):
            reason = (
                f"stable hold failed: contact={hold.bilateral_rate:.3f}, "
                f"left_force={hold.left_force_n:.3f}N, right_force={hold.right_force_n:.3f}N"
            )
            self.last_grasp_telemetry = GraspTelemetry(
                False, hold.bilateral_rate, hold.max_slip_m, 0, 0, reason,
                hold.left_rate, hold.right_rate, hold.left_force_n, hold.right_force_n,
                False, False, False, selected.wrist_yaw_radians, tuple(phase_trace),
            )
            self.contact_failure_class = self.classify_contact_failure()
            return False
        phase_trace.append("TRIAL_LIFT")
        # The Cartesian stage has gravity sag under the palm/finger mass. A
        # -0.24 command produces an actual 2-3 cm clearance above the tabletop;
        # -0.27 only unloads pad/table contact and is not a physical trial lift.
        trial = self._monitored_motion(
            {"robot_z_ctrl": config.trial_z_ctrl}, config.trial_seconds, "TRIAL_LIFT"
        )
        trial_height = self._cube_height() - start_height
        # Relative motion includes the cube settling vertically inside the
        # 12-cm-tall pads as it leaves the table. Three centimetres is the same
        # conservative retention limit used during whole-cube rotation.
        trial_success = (
            trial.bilateral_rate >= .80
            and trial.max_slip_m <= config.slip_limit_m
            and trial_height >= .012
        )
        if not trial_success:
            reason = (
                f"trial lift failed: contact={trial.bilateral_rate:.3f}, "
                f"slip={trial.max_slip_m:.4f}m, lift={trial_height:.4f}m"
            )
            self.last_grasp_telemetry = GraspTelemetry(
                False, trial.bilateral_rate, trial.max_slip_m, trial_height, 0, reason,
                trial.left_rate, trial.right_rate, trial.left_force_n, trial.right_force_n,
                False, False, False, selected.wrist_yaw_radians, tuple(phase_trace),
            )
            self.contact_failure_class = self.classify_contact_failure()
            return False
        phase_trace.extend(["STABILITY_CHECK", "FULL_LIFT"])
        lift = self._monitored_motion(
            {"robot_z_ctrl": config.full_lift_z_ctrl},
            config.full_lift_seconds,
            "FULL_LIFT",
        )
        lift_height = self._cube_height() - start_height
        contact_fraction = min(trial.bilateral_rate, lift.bilateral_rate)
        slip = max(trial.max_slip_m, lift.max_slip_m)
        success = (
            lift.bilateral_rate >= .85
            and slip <= config.slip_limit_m
            and lift_height >= .06
        )
        reason = None if success else (
            f"full lift unstable: contact={contact_fraction:.3f}, "
            f"slip={slip:.4f}m, lift={lift_height:.4f}m"
        )
        self.last_grasp_telemetry = GraspTelemetry(
            success, contact_fraction, slip, lift_height, 0, reason,
            min(trial.left_rate, lift.left_rate), min(trial.right_rate, lift.right_rate),
            (trial.left_force_n + lift.left_force_n) / 2,
            (trial.right_force_n + lift.right_force_n) / 2,
            True, success, False, selected.wrist_yaw_radians, tuple(phase_trace),
        )
        self.contact_failure_class = self.classify_contact_failure()
        return success

    @staticmethod
    def _components(mask: np.ndarray) -> list[np.ndarray]:
        pending = mask.copy()
        components: list[np.ndarray] = []
        height, width = mask.shape
        while pending.any():
            start = tuple(np.argwhere(pending)[0])
            queue = deque([start])
            pending[start] = False
            pixels: list[tuple[int, int]] = []
            while queue:
                row, col = queue.popleft()
                pixels.append((row, col))
                for dr, dc in ((-1, 0), (1, 0), (0, -1), (0, 1)):
                    rr, cc = row + dr, col + dc
                    if 0 <= rr < height and 0 <= cc < width and pending[rr, cc]:
                        pending[rr, cc] = False
                        queue.append((rr, cc))
            if len(pixels) >= 12:
                components.append(np.asarray(pixels))
        return components

    def _read_visible_face(
        self, rgb: np.ndarray, frame_index: int, source_view: str = "unspecified"
    ) -> FaceObservation | None:
        # Perspective-correct mapper is the primary path. The legacy component
        # reader remains below as a compatibility fallback for partial crops.
        from .facelet_mapping import PerspectiveFaceletMapper
        mapped = PerspectiveFaceletMapper().map_face(
            rgb, frame_index=frame_index, source_view=source_view,
        )
        if mapped is not None:
            return mapped.observation
        pixels = rgb.astype(float)
        distances = np.stack([
            np.linalg.norm(pixels - reference, axis=2) for reference in _RGB8.values()
        ])
        mask = distances.min(axis=0) < 105
        # Only the calibrated center crop can contain the face at the scan station.
        mask[: self.height // 8] = False
        mask[7 * self.height // 8 :] = False
        mask[:, : self.width // 8] = False
        mask[:, 7 * self.width // 8 :] = False
        candidates: list[np.ndarray] = []
        for component in self._components(mask):
            row_span = int(np.ptp(component[:, 0])) + 1
            col_span = int(np.ptp(component[:, 1])) + 1
            ratio = row_span / col_span
            fill = len(component) / (row_span * col_span)
            if 120 <= len(component) <= 7000 and .45 <= ratio <= 2.2 and fill > .35:
                candidates.append(component)
        if len(candidates) < 5:
            return None
        # A direct face contains nine large square components. Thin slivers
        # from adjacent faces can be closer to image centre, so rank by area
        # first; the former centre-only ranking could replace corner stickers
        # with those slivers and even corrupt the centre-face identity.
        candidates.sort(key=len, reverse=True)
        chosen = candidates[:9]
        component_data: list[tuple[np.ndarray, str]] = []
        for component in chosen:
            mean = np.median(rgb[component[:, 0], component[:, 1]], axis=0)
            red, green, blue = (float(value) / 255 for value in mean)
            hue, saturation, value = colorsys.rgb_to_hsv(red, green, blue)
            if saturation < .22 and value > .45:
                symbol = "U"
            else:
                def color_distance(key: str) -> float:
                    ref_h, ref_s, _ = _HSV[key]
                    hue_distance = min(abs(hue - ref_h), 1 - abs(hue - ref_h))
                    return 4.0 * hue_distance + .15 * abs(saturation - ref_s)
                symbol = min((key for key in _HSV if key != "U"), key=color_distance)
            component_data.append((component, symbol))
        row_centers = np.array([item[0][:, 0].mean() for item in component_data])
        col_centers = np.array([item[0][:, 1].mean() for item in component_data])
        row_grid = np.linspace(row_centers.min(), row_centers.max(), 3)
        col_grid = np.linspace(col_centers.min(), col_centers.max(), 3)
        symbols: list[str | None] = [None] * 9
        confidences = [0.0] * 9
        for (component, symbol), row, col in zip(component_data, row_centers, col_centers):
            grid_row = int(np.argmin(np.abs(row_grid - row)))
            grid_col = int(np.argmin(np.abs(col_grid - col)))
            position = grid_row * 3 + grid_col
            symbols[position] = symbol
            confidences[position] = .72
        center_symbol = symbols[4]
        if center_symbol is None:
            return None
        return FaceObservation(
            center_symbol, tuple(symbols), .72, frame_index, tuple(confidences),
            source_view=source_view,
        )

    def _read_visible_face_frame(
        self, frame: RGBDFrame, frame_index: int, source_view: str,
    ) -> FaceObservation | None:
        """Shared released/held mapping through the single canonical geometry solver."""
        from .canonical_facelets import (
            predicted_visible_face, projected_face_corners,
            remap_observation_values, solve_canonical_mapping,
        )
        from .facelet_mapping import PerspectiveFaceletMapper

        mapped = PerspectiveFaceletMapper().map_face(
            frame.rgb, frame_index=frame_index, source_view=source_view,
        )
        corner_source = "vision_corners"
        if self.visual_world_state is not None:
            center = np.asarray(self.visual_world_state["center_world_m"])
            rotation = np.asarray(
                self._index_cube_to_world
                if source_view == "released:world_top"
                and self._index_cube_to_world is not None
                else self.visual_world_state["rotation_cube_to_world"]
            )
            predicted = predicted_visible_face(center, rotation, frame.calibration)
            if mapped is None or mapped.observation.face != predicted:
                try:
                    pose_corners = projected_face_corners(
                        predicted, center, rotation, frame.calibration,
                    )
                    projected = PerspectiveFaceletMapper().map_face(
                        frame.rgb, frame_index=frame_index, source_view=source_view,
                        corners_xy=pose_corners, face_hint=predicted,
                    )
                    # In an oblique U view the generic dominant-face detector
                    # may select an adjacent side. Refine only the projected
                    # quad translation from the observed white centre sticker;
                    # all nine colors still come from the camera image and the
                    # unchanged canonical solver remains the acceptance gate.
                    if (
                        predicted == "U"
                        and (projected is None or projected.observation.stickers[4] != "U")
                    ):
                        pixels = frame.rgb.astype(float)
                        chroma = pixels.max(axis=2) - pixels.min(axis=2)
                        white = (pixels.min(axis=2) > 125) & (chroma < 55)
                        predicted_center = np.mean(pose_corners, axis=0)
                        rows, cols = np.nonzero(white)
                        if len(rows):
                            distances = np.hypot(
                                cols - predicted_center[0], rows - predicted_center[1]
                            )
                            nearby = distances < 34
                            if int(np.count_nonzero(nearby)) >= 20:
                                observed_center = np.array([
                                    float(np.median(cols[nearby])),
                                    float(np.median(rows[nearby])),
                                ])
                                refined_corners = pose_corners + (
                                    observed_center - predicted_center
                                )
                                refined = PerspectiveFaceletMapper().map_face(
                                    frame.rgb, frame_index=frame_index,
                                    source_view=source_view, corners_xy=refined_corners,
                                    face_hint=predicted,
                                )
                                if (
                                    refined is not None
                                    and refined.observation.stickers[4] == predicted
                                ):
                                    projected = refined
                                    corner_source = (
                                        "pose_projected_corners_rgb_center_refined"
                                    )
                    # The logical center is invariant under every in-face D4
                    # transform and is therefore a safe validation gate.
                    if projected is not None and projected.observation.stickers[4] == predicted:
                        mapped = projected
                        if corner_source == "vision_corners":
                            corner_source = "pose_projected_corners_center_validated"
                except ValueError:
                    pass
        if mapped is None:
            fallback = self._read_visible_face(frame.rgb, frame_index, source_view)
            if fallback is None:
                return None
            # Without corners no face-internal orientation is observable. Only
            # the center identity is invariant under D4 and may be retained.
            colors: list[str | None] = [None] * 9
            confidences = [0.0] * 9
            colors[4] = fallback.face
            confidences[4] = fallback.confidence
            self.facelet_mapping_diagnostics.append({
                "frame_index": frame_index, "source_view": source_view,
                "face": fallback.face, "reliable": False,
                "reason": "corners_unavailable", "assignment": None,
            })
            return FaceObservation(
                fallback.face, tuple(colors), fallback.confidence, frame_index,
                tuple(confidences), source_view + ":canonical_unknown",
            )
        if self.visual_world_state is None:
            return FaceObservation(
                mapped.observation.face, (None, None, None, None,
                mapped.observation.face, None, None, None, None),
                mapped.observation.confidence, frame_index,
                (0.0, 0.0, 0.0, 0.0, mapped.observation.confidence,
                 0.0, 0.0, 0.0, 0.0), source_view + ":pose_unknown",
            )
        try:
            if source_view == "released:world_top" and mapped.observation.face == "U":
                # The centre sticker identifies U from pixels and world_top is
                # calibrated along world -Z. This directly observes the face
                # normal (+Z); the unchanged D4 solver still resolves in-face
                # rotation/mirror from the image grid.
                mapping_rotation = np.eye(3)
            else:
                mapping_rotation = np.asarray(
                    self._index_cube_to_world
                    if source_view == "released:world_top"
                    and self._index_cube_to_world is not None
                    else self.visual_world_state["rotation_cube_to_world"]
                )
            decision = solve_canonical_mapping(
                mapped.observation.face, np.asarray(mapped.corners_xy),
                self.visual_world_state["center_world_m"],
                mapping_rotation,
                frame.calibration,
            )
        except ValueError as exc:
            # A stale/recovering visual pose can project the detected face
            # behind a camera. Preserve only the D4-invariant center instead
            # of crashing or assigning indices from an invalid geometry.
            colors: list[str | None] = [None] * 9
            confidences = [0.0] * 9
            colors[4] = mapped.observation.face
            confidences[4] = mapped.observation.sticker_confidences[4]
            self.facelet_mapping_diagnostics.append({
                "frame_index": frame_index, "source_view": source_view,
                "face": mapped.observation.face, "reliable": False,
                "reason": f"projection_unavailable:{exc}",
                "assignment": None, "corner_source": corner_source,
            })
            return FaceObservation(
                mapped.observation.face, tuple(colors), mapped.observation.confidence,
                frame_index, tuple(confidences), source_view + ":canonical_unknown",
            )
        diagnostic = {
            "frame_index": frame_index, "source_view": source_view,
            "face": mapped.observation.face, "predicted_face": decision.predicted_face,
            "reliable": decision.reliable, "reason": decision.reason,
            "mirrored": decision.mirrored, "quarter_turns": decision.quarter_turns,
            "normalized_rms_error": decision.normalized_rms_error,
            "ambiguity_margin": decision.ambiguity_margin,
            "assignment": list(decision.observed_to_canonical),
            "corner_source": corner_source,
        }
        self.facelet_mapping_diagnostics.append(diagnostic)
        if not decision.reliable:
            colors = [None] * 9
            confidences = [0.0] * 9
            colors[4] = mapped.observation.face
            confidences[4] = mapped.observation.sticker_confidences[4]
        else:
            colors = list(remap_observation_values(
                mapped.observation.stickers, decision.observed_to_canonical
            ))
            confidences = list(remap_observation_values(
                mapped.observation.sticker_confidences, decision.observed_to_canonical
            ))
        return FaceObservation(
            mapped.observation.face, tuple(colors), mapped.observation.confidence,
            frame_index, tuple(float(value) for value in confidences),
            source_view + (":canonical" if decision.reliable else ":canonical_unknown"),
        )

    def _place_and_release(self, *, transport_to_scan_station: bool = False) -> bool:
        self.observation_action_trace.extend(["PLACE", "RELEASE"])
        # Transport the lifted cube to a calibrated scan station using contact
        # feedback, then lower while maintaining the friction grasp. In v7 the
        # inspection gantry is visually re-centred, so placement stays at the
        # stable grasp location instead of imposing a long lateral transport.
        if transport_to_scan_station:
            self._contact_debug_sample("DYNAMIC_SCAN_STATION_SELECTED")
            # Keep tabletop placement clear of turn_station pads if present in scene
            if self.mujoco.mj_name2id(self.model, self.mujoco.mjtObj.mjOBJ_GEOM, "base_pos_pad") >= 0:
                px = float(self.data.qpos[self.model.jnt_qposadr[self._joint("robot_x_joint")]])
                py = float(self.data.qpos[self.model.jnt_qposadr[self._joint("robot_y_joint")]])
                if 0.20 <= px <= 0.50 and -0.48 <= py <= -0.14:
                    self._set_controls({"robot_z_ctrl": -0.12}, 0.35)
                    self._move_gantry_xy_damped(min(px, 0.14), max(py, -0.10))
        pitch_address = self.model.jnt_qposadr[self._joint("wrist_pitch_joint")]
        sideways = abs(math.sin(float(self.data.qpos[pitch_address]))) > .5
        # A side-held cube centre is about 12 cm higher for the same stage
        # command. Lower farther so table contact, not an in-air release, bears
        # the object before the fingers open.
        place_target = -.56 if sideways else -.43
        supported = self._lower_until_table_supported(place_target, 1.8)
        self._contact_debug_sample("PLACE_SUPPORTED")
        if not supported:
            return False
        self._set_controls({"left_finger_ctrl": 0, "right_finger_ctrl": 0}, .8)
        self._contact_debug_sample("RELEASE_OPEN")
        if not transport_to_scan_station:
            self._set_controls({"robot_z_ctrl": -.18}, .5)
            self._set_controls({}, .25)
        elif sideways:
            # Observe before retreat. With the cube on its side, retreating the
            # pitched palm can sweep the free object across the table. The
            # vision layer explicitly marks any gripper-occluded cells unknown.
            self._set_controls({}, .5)
            self._contact_debug_sample("RELEASE_SETTLED_SIDEWAYS")
        else:
            # Lift clear of the cube while keeping the robot_z capsule below the
            # robot_base gantry beam (z_ctrl=-0.02 settles rz~=-0.089, fingers
            # ~0.90 m), then withdraw toward (-0.45, +0.45) away from both
            # human_receiver (+0.55, +0.35) and the overhead camera (0, -0.52).
            self._set_controls({"robot_z_ctrl": -0.02}, .8)
            self._set_controls({"robot_x_ctrl": -.45, "robot_y_ctrl": .45}, .8)
            self._set_controls({}, .25)
        released = not any(self._finger_contact_forces()[:2])
        return self._cube_height() <= .73 and released

    def _lower_until_table_supported(self, lowest_z_ctrl: float, seconds: float) -> bool:
        """Lower under contact feedback; never release an unsupported object."""
        control = self._actuator("robot_z_ctrl")
        start = float(self.data.ctrl[control])
        stable_steps = 0
        required = max(4, int(.08 / self.model.opt.timestep))
        steps = max(1, int(seconds / self.model.opt.timestep))
        for step in range(steps):
            progress = (step + 1) / steps
            smooth = progress * progress * (3 - 2 * progress)
            self.data.ctrl[control] = start + (lowest_z_ctrl - start) * smooth
            self.step_physics()
            supported = self._cube_touches_geom("table")
            cube = self._id(self.mujoco.mjtObj.mjOBJ_BODY, "cube")
            linear_speed = float(np.linalg.norm(self.data.cvel[cube, 3:]))
            stable_steps = stable_steps + 1 if supported and linear_speed < .08 else 0
            if step % max(1, steps // 30) == 0 or stable_steps == required:
                self._contact_debug_sample("LOWER_TO_SUPPORT")
            if self.legacy_recording and step % max(1, steps // 12) == 0:
                self.renderer.update_scene(self.data, camera="overhead")
                self.frames.append(self.renderer.render().copy())
            if stable_steps >= required:
                return True
        return False

    def _observe_released_cube(self, frame_offset: int) -> list[FaceObservation]:
        self.observation_action_trace.append("OBSERVE")
        observations: list[FaceObservation] = []
        from .perception_v2 import DeterministicCubeLocalizer
        if self.visual_world_state is not None:
            visual_center = self.visual_world_state["center_world_m"]
            self._set_controls({"robot_z_ctrl": 0.0}, .5)
            self._set_controls({
                "robot_x_ctrl": -.45 if float(visual_center[0]) >= 0 else .45,
                "robot_y_ctrl": -.45 if float(visual_center[1]) >= 0 else .45,
            }, .7)
        overhead = self.capture_rgbd("world_top")
        self.debug_observation_frames.append(("released:world_top", overhead.rgb.copy()))
        top_observation = self._read_visible_face_frame(
            overhead, frame_offset, source_view="released:world_top"
        )
        if top_observation is not None:
            observations.append(top_observation)
        detection = DeterministicCubeLocalizer().locate(self.capture_rgbd("overhead"))
        if detection is None:
            return observations
        self._set_controls({"robot_z_ctrl": 0.0}, .7)
        self._set_controls({
            "robot_x_ctrl": detection.center_world_m[0],
            "robot_y_ctrl": detection.center_world_m[1],
        }, .7)
        camera_names = (
            "inspection_x", "inspection_y", "inspection_neg_x",
            "inspection_neg_y",
        )
        for offset, camera_name in enumerate(camera_names, start=1):
            frame = self.capture_rgbd(camera_name)
            self.debug_observation_frames.append((f"released:{camera_name}", frame.rgb.copy()))
            observation = self._read_visible_face_frame(
                frame, frame_offset + offset, source_view=f"released:{camera_name}"
            )
            if observation is not None:
                observations.append(observation)
            self.frames.append(frame.rgb)
        return observations

    def _finalize_pending_grasp_verification(
        self,
        *,
        skill_name: str,
        success: bool,
        failure_reason: str | None = None,
    ) -> object | None:
        if self.experiment_run is None or self._active_contact_verification_id is None:
            return None
        gtel = self.last_grasp_telemetry
        left_pad = self.data.geom_xpos[self._id(self.mujoco.mjtObj.mjOBJ_GEOM, "left_finger_pad")]
        right_pad = self.data.geom_xpos[self._id(self.mujoco.mjtObj.mjOBJ_GEOM, "right_finger_pad")]
        jaw_gap = max(0.0, float(np.linalg.norm(left_pad - right_pad) - 0.024))
        rel_end = self._relative_cube_position().tolist()
        unexpected_geoms = sorted({
            str(u.get("other_geom") if isinstance(u, dict) else u)
            for item in self.contact_debug_trace
            for u in item.get("unexpected_gripper_contacts", [])
        })
        passed = bool(
            success
            and gtel.success
            and gtel.bilateral_contact_fraction >= 0.80
            and min(gtel.left_normal_force_n, gtel.right_normal_force_n)
            >= self.grasp_config.minimum_normal_force_n
            and gtel.max_relative_slip_m <= self.grasp_config.slip_limit_m
            and gtel.lift_height_m >= 0.06
            and not unexpected_geoms
        )
        cv_rec = self.experiment_run.contacts.finalize_verification(
            skill_name=skill_name,
            sim_time=float(self.data.time),
            trajectory_id=self._active_trajectory_id,
            grasp_target_id=(
                self._active_grasp_target.grasp_target_id
                if self._active_grasp_target is not None else None
            ),
            pose_estimate_id=(
                self._active_pose_estimate.pose_estimate_id
                if self._active_pose_estimate is not None else None
            ),
            skill_execution_id=self._active_skill_execution_id,
            bilateral_contact_fraction=float(gtel.bilateral_contact_fraction),
            left_contact_fraction=float(gtel.left_contact_rate),
            right_contact_fraction=float(gtel.right_contact_rate),
            left_normal_force_n=float(gtel.left_normal_force_n),
            right_normal_force_n=float(gtel.right_normal_force_n),
            relative_slip_m=float(gtel.max_relative_slip_m),
            gripper_width_m=jaw_gap,
            lift_height_m=float(gtel.lift_height_m),
            object_motion_relative_to_gripper_m=rel_end,
            object_followed_end_effector=bool(passed),
            unintended_contacts=unexpected_geoms,
            verification_thresholds={
                "min_bilateral_contact_fraction": 0.80,
                "min_normal_force_n": float(self.grasp_config.minimum_normal_force_n),
                "max_relative_slip_m": float(self.grasp_config.slip_limit_m),
                "min_lift_height_m": 0.06,
            },
            verification_result=passed,
            failure_reason=failure_reason or (None if passed else (self.contact_failure_class or gtel.failure_reason or "CONTACT_VERIFICATION_FAILED")),
            contact_verification_id=self._active_contact_verification_id,
        )
        self._active_contact_verification_id = None
        return cv_rec

    # Public task-level Skills. They deliberately expose observations and
    # contact outcomes, never simulator pose or the private logical cube state.
    def task_place_release(self) -> dict[str, object]:
        self._finalize_pending_grasp_verification(
            skill_name="initial_grasp",
            success=bool(self.last_grasp_telemetry.success),
            failure_reason=self.last_grasp_telemetry.failure_reason,
        )
        self.contact_debug_trace.clear()
        self._trace_reference_cube_position = None
        self._trace_contact_reference_relative = None
        start = self._contact_debug_sample("PLACE_START")
        before = self._cube_height()
        success = self._place_and_release(transport_to_scan_station=True)
        end = self._contact_debug_sample("PLACE_END")
        linear_speeds = [float(np.linalg.norm(item["cube_linear_velocity_world_m_s"]))
                         for item in self.contact_debug_trace]
        angular_speeds = [float(np.linalg.norm(item["cube_angular_velocity_world_rad_s"]))
                          for item in self.contact_debug_trace]
        table_contact_samples = sum(
            any(contact["other_geom"] == "table" for contact in item["all_cube_contacts"])
            for item in self.contact_debug_trace
        )
        self.last_place_release_diagnostics = {
            "start_pose": {
                "position_world_m": start["cube_position_world_m"],
                "quaternion_wxyz": start["cube_quaternion_wxyz"],
            },
            "end_pose": {
                "position_world_m": end["cube_position_world_m"],
                "quaternion_wxyz": end["cube_quaternion_wxyz"],
            },
            "max_linear_speed_m_s": max(linear_speeds, default=0.0),
            "max_angular_speed_rad_s": max(angular_speeds, default=0.0),
            "total_displacement_m": float(np.linalg.norm(
                np.asarray(end["cube_position_world_m"]) - np.asarray(start["cube_position_world_m"])
            )),
            "table_contact_sample_count": table_contact_samples,
            "sample_count": len(self.contact_debug_trace),
            "trace": tuple(self.contact_debug_trace),
        }
        released = not any(self._finger_contact_forces()[:2])
        failure_code = None
        if not success:
            if table_contact_samples == 0:
                failure_code = "PLACE_SUPPORT_NOT_REACHED"
            elif not released:
                failure_code = "RELEASE_CONTACT_RETAINED"
            else:
                failure_code = "PLACE_STABILITY_FAILED"
        result = {
            "success": success,
            "height_before_m": before,
            "height_after_m": self._cube_height(),
            "released": released,
            "failure_code": failure_code,
            "diagnostics": self.last_place_release_diagnostics,
        }
        if success:
            refresh = self.refresh_visual_world_state(
                "overhead", valid_after_skill="place_release"
            )
            result["world_state_refresh"] = refresh
            result["physical_success"] = True
            if not refresh["success"]:
                result["success"] = False
                result["failure_code"] = "WORLD_STATE_REFRESH_FAILED"
        return result

    def task_observe_released(self, frame_offset: int = 0) -> list[FaceObservation]:
        from .six_face_inspection import (
            SixFacePerception,
            estimate_orientation_from_centers,
        )

        capture = self.capture_released_views()
        if not capture.get("success"):
            return []
        perception = SixFacePerception()
        frames: list[RGBDFrame] = list(capture.get("frames", []))
        detections = [
            perception.detect(frame, f"released:{frame.camera_name}")
            for frame in frames
        ]
        estimate = estimate_orientation_from_centers(
            perception.orientation_constraints(detections),
            self._index_cube_to_world,
        )
        if estimate.unique and estimate.matrix is not None:
            self._index_cube_to_world = estimate.matrix
            self._predicted_cube_rotation = estimate.matrix
        rotation = self._index_cube_to_world
        if rotation is None:
            return []
        centers = [
            item.center_world_m for item in detections
            if item.center_world_m is not None
        ]
        fallback_center = (
            np.median(np.asarray(centers), axis=0) if centers else np.asarray(
                capture.get("localized_center_world_m", (0.0, 0.0, .665)), dtype=float
            )
        )
        observations: list[FaceObservation] = []
        self.last_observation_diagnostics = []
        for offset, detection in enumerate(detections):
            result = perception.map_detection(
                detection, rotation, fallback_center, frame_offset + offset
            )
            self.facelet_mapping_diagnostics.append({
                "frame_index": frame_offset + offset,
                "source_view": detection.view,
                "face": result.predicted_face,
                "predicted_face": result.predicted_face,
                "reliable": result.emitted,
                "reason": result.reason,
                "mirrored": result.mirrored,
                "quarter_turns": result.quarter_turns,
                "normalized_rms_error": result.d4_error,
                "ambiguity_margin": result.d4_margin,
                "assignment": (
                    list(range(9)) if result.emitted else None
                ),
                "corner_source": result.corner_source,
            })
            self.last_observation_diagnostics.append({
                "camera": detection.frame.camera_name,
                "observation_emitted": result.emitted,
                "visible_face_id": result.predicted_face if result.emitted else None,
                "mapping_reliable": result.emitted,
                "mapping_reason": result.reason,
                "mapping_corner_source": result.corner_source,
                "unknown_facelets": 9 - result.known_stickers,
            })
            if result.observation is not None:
                observations.append(result.observation)
        if self.physical_u or self.full_26_cubie:
            from .physical_u import physical_observations
            return physical_observations(observations)
        return observations

    # ------------------------------------------------------------------
    # v8 six-face inspection primitives. They only move the robot and return
    # calibrated RGB-D frames plus robot proprioception; all face identity,
    # orientation and facelet mapping is decided by the perception layer.
    RELEASED_SIDE_CAMERAS = (
        "inspection_x", "inspection_y", "inspection_neg_x", "inspection_neg_y",
    )
    HELD_CAMERAS = (
        "inspection_high_x", "inspection_high_y",
        "inspection_high_neg_x", "inspection_high_neg_y",
    )

    def gripper_axes_world(self) -> dict[str, list[float]]:
        """Robot forward kinematics (proprioception), never cube state."""
        gripper = self._id(self.mujoco.mjtObj.mjOBJ_BODY, "gripper")
        rotation = self.data.xmat[gripper].reshape(3, 3)
        return {
            "finger_closure_axis": rotation[:, 1].tolist(),
            "palm_direction": rotation[:, 2].tolist(),
            "position_world_m": self.data.xpos[gripper].tolist(),
        }

    def _record_capture(self, label: str, frame: RGBDFrame) -> None:
        self.debug_observation_frames.append((label, frame.rgb.copy()))
        self.frames.append(frame.rgb)

    def _move_gantry_xy_damped(
        self,
        target_x: float,
        target_y: float,
        *,
        max_seconds: float = 1.6,
        step_seconds: float = .02,
        kd: float = .12,
        pos_tol: float = .003,
        vel_tol: float = .015,
    ) -> None:
        """Move gantry XY with trapezoidal ActionChunk planning and active damping.

        The gantry slide actuators (kp=500, damping=2.0) are underdamped for
        large step targets. Planning an adaptive trapezoidal profile via
        ActionChunkExecutor and damping from robot joint encoders eliminates
        overshoot and settles within ~2 mm without touching object ground truth.
        """
        x_joint = self._joint("robot_x_joint")
        y_joint = self._joint("robot_y_joint")
        x_qpos = int(self.model.jnt_qposadr[x_joint])
        y_qpos = int(self.model.jnt_qposadr[y_joint])
        x_qvel = int(self.model.jnt_dofadr[x_joint])
        y_qvel = int(self.model.jnt_dofadr[y_joint])
        x_low, x_high = (float(v) for v in self.model.jnt_range[x_joint])
        y_low, y_high = (float(v) for v in self.model.jnt_range[y_joint])
        goal_x = float(np.clip(target_x, x_low, x_high))
        goal_y = float(np.clip(target_y, y_low, y_high))
        start_x = float(self.data.qpos[x_qpos])
        start_y = float(self.data.qpos[y_qpos])

        # Plan trapezoidal XY chunk sized inside max_seconds budget
        v_limit = 0.24
        chunk = ActionChunk.trapezoidal_xy(
            chunk_id=f"damped_xy_{uuid.uuid4().hex[:8]}",
            start_xy=(start_x, start_y),
            goal_xy=(goal_x, goal_y),
            dt=float(self.model.opt.timestep),
            v_max=v_limit,
            a_max=1.0,
            min_duration_s=min(0.18, max(0.04, max_seconds * 0.4)),
            max_duration_s=max(0.1, max_seconds * 0.7),
            hold_grip_on_interrupt=False,
            kd_xy=kd,
            world_revision=self._world_state_revision,
            goal_revision=self._plan_version,
        )
        res = self._action_chunk_executor().execute(chunk, token=self.active_cancellation_token)
        self.last_chunk_result = res

        settled = 0
        rem_seconds = max(0.1, max_seconds - len(chunk.targets) * float(self.model.opt.timestep))
        steps = max(1, int(round(rem_seconds / step_seconds)))
        converged = False
        iterations = 0
        if res.status == ChunkStatus.COMPLETED:
            for _ in range(steps):
                px = float(self.data.qpos[x_qpos])
                py = float(self.data.qpos[y_qpos])
                vx = float(self.data.qvel[x_qvel])
                vy = float(self.data.qvel[y_qvel])
                if (
                    abs(goal_x - px) <= pos_tol
                    and abs(goal_y - py) <= pos_tol
                    and abs(vx) <= vel_tol
                    and abs(vy) <= vel_tol
                ):
                    settled += 1
                    if settled >= 2:
                        converged = True
                        break
                else:
                    settled = 0
                ctrl_x = float(np.clip(goal_x - kd * vx, x_low, x_high))
                ctrl_y = float(np.clip(goal_y - kd * vy, y_low, y_high))
                self._set_controls({"robot_x_ctrl": ctrl_x, "robot_y_ctrl": ctrl_y}, step_seconds)
                iterations += 1
            self._set_controls({"robot_x_ctrl": goal_x, "robot_y_ctrl": goal_y}, .08)
        if self.motion_timing.stack:
            event = self.motion_timing.events[self.motion_timing.stack[-1]]
            event["gantry_controller"] = {
                "converged_before_tail":converged, "iterations":iterations,
                "max_seconds":max_seconds, "control_period":step_seconds,
                "kd_target_offset":kd, "position_tolerance_m":pos_tol,
                "velocity_tolerance_m_s":vel_tol, "fixed_tail_seconds":.08,
                "trajectory_velocity_limit":v_limit,
                "final_xy_error_m":[float(self.data.qpos[x_qpos]-goal_x),float(self.data.qpos[y_qpos]-goal_y)],
                "final_xy_velocity_m_s":[float(self.data.qvel[x_qvel]),float(self.data.qvel[y_qvel])],
            }

    def capture_released_views(self) -> dict[str, object]:
        """Clear the opened gripper and capture one top view plus four side views.

        The released cube is first localized from overhead RGB-D, then refined
        from horizontal eye-in-gantry side cameras (which lack overhead oblique
        Y bias). Keeping robot_z_ctrl at -0.02 clears the overhead gantry beam
        while keeping the open gripper 18 cm above the table cube, and damped
        XY motion avoids gantry overshoot under the offset downward cameras.
        """
        from .perception_v2 import DeterministicCubeLocalizer

        localizer = DeterministicCubeLocalizer()
        self.observation_action_trace.append("OBSERVE")
        if any(self._finger_contact_forces()[:2]):
            return {"success": False, "failure_code": "RELEASED_VIEW_GRIPPER_IN_CONTACT",
                    "frames": []}
        self._set_controls({"left_finger_ctrl": 0.0, "right_finger_ctrl": 0.0,
                            "robot_z_ctrl": -0.02}, .45)
        detection = localizer.locate(self.capture_rgbd("overhead"))
        if detection is None:
            return {"success": False, "failure_code": "RELEASED_LOCALIZATION_FAILED",
                    "frames": []}
        cx0, cy0, cz0 = (float(v) for v in detection.center_world_m)

        # First centre on overhead estimate and refine (cx, cy) from side views.
        self._move_gantry_xy_damped(cx0, cy0)
        dets_by_cam: dict[str, CubeDetection] = {}
        for camera in self.RELEASED_SIDE_CAMERAS:
            det = localizer.locate(self.capture_rgbd(camera))
            if det is not None:
                dets_by_cam[camera] = det

        xs = [
            float(dets_by_cam[c].center_world_m[0])
            for c in ("inspection_x", "inspection_neg_x") if c in dets_by_cam
        ]
        ys = [
            float(dets_by_cam[c].center_world_m[1])
            for c in ("inspection_y", "inspection_neg_y") if c in dets_by_cam
        ]
        if not xs and "inspection_y" in dets_by_cam and "inspection_neg_y" in dets_by_cam:
            xs = [
                float(dets_by_cam["inspection_y"].center_world_m[0]),
                float(dets_by_cam["inspection_neg_y"].center_world_m[0]),
            ]
        if not ys and "inspection_x" in dets_by_cam and "inspection_neg_x" in dets_by_cam:
            ys = [
                float(dets_by_cam["inspection_x"].center_world_m[1]),
                float(dets_by_cam["inspection_neg_x"].center_world_m[1]),
            ]
        cx = float(np.mean(xs)) if xs else cx0
        cy = float(np.mean(ys)) if ys else cy0
        cz = (
            float(np.median([float(d.center_world_m[2]) for d in dets_by_cam.values()]))
            if dets_by_cam else cz0
        )

        # Capture unobstructed downward U view from offset downward eye-in-gantry cameras.
        y_low, y_high = (float(value) for value in self.model.jnt_range[self._joint("robot_y_joint")])
        frames: list[RGBDFrame] = []
        top_camera = None
        for camera, offset in (
            ("inspection_down_pos_y", .22),
            ("inspection_down_neg_y", -.22),
            ("inspection_top", 0.0),
        ):
            candidate = cy - offset
            if not (y_low + .01 <= candidate <= y_high - .01):
                continue
            self._move_gantry_xy_damped(cx, candidate)
            frame = self.capture_rgbd(camera)
            self._record_capture(f"released:{camera}", frame)
            frames.append(frame)
            if localizer.locate(frame) is not None:
                top_camera = camera
                break

        # Re-centre over refined (cx, cy) and capture the four side views.
        self._move_gantry_xy_damped(cx, cy)
        for camera in self.RELEASED_SIDE_CAMERAS:
            frame = self.capture_rgbd(camera)
            self._record_capture(f"released:{camera}", frame)
            frames.append(frame)
        return {
            "success": True, "failure_code": None, "frames": frames,
            "localized_center_world_m": [cx, cy, cz],
            "top_camera": top_camera,
        }

    def capture_held_views(self) -> dict[str, object]:
        """Capture all horizontal views of a cube held by the gripper."""
        self.observation_action_trace.append("OBSERVE_HELD_VIEWS")
        held = all(self._finger_contact_forces()[:2])
        gripper = self.gripper_axes_world()
        closure = np.asarray(gripper["finger_closure_axis"], dtype=float)
        palm = np.asarray(gripper["palm_direction"], dtype=float)
        frames: list[RGBDFrame] = []
        for camera in self.HELD_CAMERAS:
            frame = self.capture_rgbd(camera)
            outward = -np.asarray(frame.calibration.camera_to_world[:3, 2], dtype=float)
            # Skip cameras looking into the two finger pads or into the back of
            # the palm when pitched.
            if abs(float(np.dot(outward, closure))) > .5 or float(np.dot(outward, palm)) > .5:
                continue
            self._record_capture(f"held:{camera}", frame)
            frames.append(frame)
        return {"success": held, "failure_code": None if held else "HELD_VIEW_GRASP_LOST",
                "frames": frames, "gripper": gripper}

    def task_observe_held(
        self, frame_offset: int = 0, *, use_fixed_external: bool = False,
    ) -> list[FaceObservation]:
        """Observe a reoriented lifted cube; occluded cells remain unknown."""
        from .six_face_inspection import (
            SixFacePerception,
            estimate_orientation_from_centers,
        )

        self.observation_action_trace.append("OBSERVE_HELD")
        capture = self.capture_held_views()
        perception = SixFacePerception()
        frames: list[RGBDFrame] = list(capture.get("frames", []))
        detections = [
            perception.detect(frame, f"held:{frame.camera_name}")
            for frame in frames
        ]
        estimate = estimate_orientation_from_centers(
            perception.orientation_constraints(detections),
            self._index_cube_to_world,
        )
        if estimate.unique and estimate.matrix is not None:
            self._index_cube_to_world = estimate.matrix
            self._predicted_cube_rotation = estimate.matrix
        rotation = self._index_cube_to_world
        if rotation is None:
            return []
        centers = [
            item.center_world_m for item in detections
            if item.center_world_m is not None
        ]
        fallback_center = (
            np.median(np.asarray(centers), axis=0) if centers else np.asarray(
                capture.get("gripper", {}).get("position_world_m", (0.0, 0.0, .80)),
                dtype=float,
            )
        )
        observations: list[FaceObservation] = []
        self.last_observation_diagnostics = []
        for offset, detection in enumerate(detections):
            result = perception.map_detection(
                detection, rotation, fallback_center, frame_offset + offset
            )
            self.facelet_mapping_diagnostics.append({
                "frame_index": frame_offset + offset,
                "source_view": detection.view,
                "face": result.predicted_face,
                "predicted_face": result.predicted_face,
                "reliable": result.emitted,
                "reason": result.reason,
                "mirrored": result.mirrored,
                "quarter_turns": result.quarter_turns,
                "normalized_rms_error": result.d4_error,
                "ambiguity_margin": result.d4_margin,
                "assignment": (
                    list(range(9)) if result.emitted else None
                ),
                "corner_source": result.corner_source,
            })
            self.last_observation_diagnostics.append({
                "camera": detection.frame.camera_name,
                "observation_emitted": result.emitted,
                "visible_face_id": result.predicted_face if result.emitted else None,
                "mapping_reliable": result.emitted,
                "mapping_reason": result.reason,
                "mapping_corner_source": result.corner_source,
                "unknown_facelets": 9 - result.known_stickers,
            })
            if result.observation is not None:
                observations.append(result.observation)
        if self.physical_u or self.full_26_cubie:
            from .physical_u import physical_observations
            return physical_observations(observations)
        return observations

    def _face_visibility_diagnostics(
        self, face: str, frame: RGBDFrame, colored_mask: np.ndarray,
    ) -> dict[str, object]:
        """Image-space visibility diagnostics; never supplies fusion values."""
        from .canonical_facelets import FACE_FRAMES, projected_face_corners

        if self.visual_world_state is None:
            return {"available": False, "reason": "visual_world_state_unavailable"}
        center = np.asarray(self.visual_world_state["center_world_m"], dtype=float)
        rotation = np.asarray(
            self._index_cube_to_world
            if self._index_cube_to_world is not None
            else self.visual_world_state["rotation_cube_to_world"],
            dtype=float,
        )
        normal_world = rotation @ np.asarray(FACE_FRAMES[face].normal, dtype=float)
        toward_camera = frame.calibration.camera_to_world[:3, 3] - center
        toward_camera /= max(float(np.linalg.norm(toward_camera)), 1e-9)
        cosine = float(np.clip(np.dot(normal_world, toward_camera), -1.0, 1.0))
        angle = math.degrees(math.acos(cosine))
        try:
            corners = projected_face_corners(face, center, rotation, frame.calibration)
        except ValueError:
            return {
                "available": False, "reason": "face_behind_camera",
                "normal_to_camera_angle_degrees": angle,
            }
        x0, y0 = np.floor(corners.min(axis=0)).astype(int)
        x1, y1 = np.ceil(corners.max(axis=0)).astype(int)
        polygon_area = .5 * abs(float(
            np.dot(corners[:, 0], np.roll(corners[:, 1], -1))
            - np.dot(corners[:, 1], np.roll(corners[:, 0], -1))
        ))
        clipped_x0, clipped_y0 = max(0, x0), max(0, y0)
        clipped_x1, clipped_y1 = min(frame.rgb.shape[1] - 1, x1), min(frame.rgb.shape[0] - 1, y1)
        in_frame = bool(
            x0 >= 0 and y0 >= 0
            and x1 < frame.rgb.shape[1] and y1 < frame.rgb.shape[0]
        )
        if clipped_x1 > clipped_x0 and clipped_y1 > clipped_y0:
            crop = colored_mask[clipped_y0:clipped_y1 + 1, clipped_x0:clipped_x1 + 1]
            colored_fraction = float(np.mean(crop))
        else:
            colored_fraction = 0.0
        return {
            "available": True,
            "normal_world": normal_world.tolist(),
            "camera_direction_world": toward_camera.tolist(),
            "normal_to_camera_angle_degrees": angle,
            "projected_corners_xy": corners.tolist(),
            "projected_bbox_xyxy": [int(x0), int(y0), int(x1), int(y1)],
            "projected_area_pixels": polygon_area,
            "fully_in_frame": in_frame,
            # Diagnostic estimate only. Black sticker gaps also contribute, so
            # this is deliberately not used as a success criterion or mapper input.
            "colored_fraction_in_projected_bbox": colored_fraction,
            "estimated_noncolored_or_occluded_fraction": 1.0 - colored_fraction,
        }

    def task_regrasp(
        self, *, exclude_face_pairs: set[str] | None = None,
    ) -> dict[str, object]:
        from cube_relay.experiment.recorder import ContactRecorder
        from .failure_aware_v6 import run_bounded_grasp_retry
        from .vlm import ChromaCubePresenceDetector

        refresh = self.refresh_visual_world_state(
            "overhead", valid_after_skill="before_regrasp"
        )
        excluded: set[str] = set(exclude_face_pairs or ())
        attempts: list[dict[str, object]] = []
        success = False
        aligned: dict[str, object] = {}
        if not excluded:
            # Execute the deterministic bounded grasp retry subroutine
            # (contact guards, trial lift, tangent/closure offset recovery)
            # without nesting a task-level agent or claiming real VLM provenance.
            v6 = run_bounded_grasp_retry(
                self,
                seed=self._last_seed,
                scramble_steps=15,
                reset_scene=False,
                presence_detector=ChromaCubePresenceDetector(),
            )
            for idx, record in enumerate(v6.attempt_memory, start=1):
                attempts.append({
                    "attempt": idx,
                    "face_pair": record.face_pair,
                    "success": record.failure_code is None,
                    "failure_code": record.failure_code,
                })
            if v6.final_success:
                aligned = self.task_align_scan_axes()
                success = bool(aligned.get("success"))
                if not attempts:
                    attempts.append({
                        "attempt": 1,
                        "face_pair": (
                            self.last_selected_grasp_candidate.face_pair
                            if self.last_selected_grasp_candidate else "local_y_faces"
                        ),
                        "success": success,
                        "failure_code": aligned.get("failure_code"),
                    })
        if not success:
            for attempt_index in range(2):
                success = self._regrasp_from_pixels(excluded)
                selected = self.last_selected_grasp_candidate
                attempts.append({
                    "attempt": len(attempts) + 1,
                    "face_pair": selected.face_pair if selected else None,
                    "success": success,
                    "failure_code": None if success else self.contact_failure_class,
                })
                if success:
                    aligned = self.task_align_scan_axes()
                    success = bool(aligned.get("success"))
                    break
                if selected is not None:
                    excluded.add(selected.face_pair)
                self.skill_retreat()
        telemetry = self.last_grasp_telemetry
        unexpected_geoms = sorted({
            str(item.get("other_geom") if isinstance(item, dict) else item)
            for sample in self.contact_debug_trace
            for item in sample.get("unexpected_gripper_contacts", [])
        })
        contact_verification_passed = bool(
            success
            and telemetry.success
            and telemetry.bilateral_contact_fraction >= 0.80
            and min(telemetry.left_normal_force_n, telemetry.right_normal_force_n)
            >= self.grasp_config.minimum_normal_force_n
            and telemetry.max_relative_slip_m <= self.grasp_config.slip_limit_m
            and telemetry.lift_height_m >= 0.06
            and not unexpected_geoms
        )
        failure_code = None if contact_verification_passed else (
            self.contact_failure_class
            or ("REGRASP_CONTACT_VERIFICATION_FAILED" if success else "REGRASP_FAILED")
        )
        success = bool(success and contact_verification_passed)
        raw_samples = [
            {
                "sim_time": float(s.get("time_s", 0.0)),
                "phase": str(s.get("phase", "")),
                "left_contact": int(s.get("left_contact_count", 0)) > 0,
                "right_contact": int(s.get("right_contact_count", 0)) > 0,
                "bilateral_contact": int(s.get("left_contact_count", 0)) > 0 and int(s.get("right_contact_count", 0)) > 0,
                "left_normal_force_n": float(s.get("left_normal_force_n", 0.0)),
                "right_normal_force_n": float(s.get("right_normal_force_n", 0.0)),
                "relative_slip_m": float(
                    s.get("relative_slip_from_bilateral_contact_m")
                    if s.get("relative_slip_from_bilateral_contact_m") is not None
                    else s.get("relative_slip_from_pregrasp_m", 0.0)
                ),
                "unexpected_contacts_count": len(s.get("unexpected_gripper_contacts", [])),
                "unexpected_contacts_geoms": ";".join(
                    str(u.get("other_geom") if isinstance(u, dict) else u)
                    for u in s.get("unexpected_gripper_contacts", [])
                ),
            }
            for s in self.contact_debug_trace
        ]
        windows = ContactRecorder.summarize_phase_windows(raw_samples)
        phase_summaries = {k: v.model_dump(mode="json") for k, v in windows.items()}
        cv_id: str | None = None
        if self.experiment_run is not None:
            left_pad = self.data.geom_xpos[self._id(self.mujoco.mjtObj.mjOBJ_GEOM, "left_finger_pad")]
            right_pad = self.data.geom_xpos[self._id(self.mujoco.mjtObj.mjOBJ_GEOM, "right_finger_pad")]
            jaw_gap = max(0.0, float(np.linalg.norm(left_pad - right_pad) - 0.024))
            rel_end = self._relative_cube_position().tolist()
            cv_rec = self.experiment_run.contacts.finalize_verification(
                skill_name="regrasp_cube",
                sim_time=float(self.data.time),
                trajectory_id=self._active_trajectory_id,
                grasp_target_id=(
                    self._active_grasp_target.grasp_target_id
                    if self._active_grasp_target is not None else None
                ),
                pose_estimate_id=(
                    self._active_pose_estimate.pose_estimate_id
                    if self._active_pose_estimate is not None else None
                ),
                skill_execution_id=self._active_skill_execution_id,
                bilateral_contact_fraction=telemetry.bilateral_contact_fraction,
                left_contact_fraction=telemetry.left_contact_rate,
                right_contact_fraction=telemetry.right_contact_rate,
                left_normal_force_n=telemetry.left_normal_force_n,
                right_normal_force_n=telemetry.right_normal_force_n,
                relative_slip_m=telemetry.max_relative_slip_m,
                gripper_width_m=jaw_gap,
                lift_height_m=telemetry.lift_height_m,
                object_motion_relative_to_gripper_m=rel_end,
                object_followed_end_effector=bool(telemetry.lift_height_m >= 0.06 and telemetry.max_relative_slip_m <= self.grasp_config.slip_limit_m),
                unintended_contacts=unexpected_geoms,
                verification_thresholds={
                    "min_bilateral_contact_fraction": 0.80,
                    "min_normal_force_n": self.grasp_config.minimum_normal_force_n,
                    "max_relative_slip_m": self.grasp_config.slip_limit_m,
                    "min_lift_height_m": 0.06,
                },
                verification_result=contact_verification_passed,
                failure_reason=failure_code,
                contact_verification_id=self._active_contact_verification_id,
            )
            cv_id = cv_rec.contact_verification_id
            self._active_contact_verification_id = None
        return {
            "success": success,
            "contact_verification_passed": contact_verification_passed,
            "contact_verification_id": cv_id,
            "bilateral_contact_fraction": telemetry.bilateral_contact_fraction,
            "left_contact_fraction": telemetry.left_contact_rate,
            "right_contact_fraction": telemetry.right_contact_rate,
            "left_normal_force_n": telemetry.left_normal_force_n,
            "right_normal_force_n": telemetry.right_normal_force_n,
            "max_relative_slip_m": telemetry.max_relative_slip_m,
            "lift_height_m": telemetry.lift_height_m,
            "unexpected_contacts": unexpected_geoms,
            "phase_summaries": phase_summaries,
            "align_diagnostics": aligned,
            "failure_code": failure_code,
            "attempts": attempts,
            "world_state_refresh": refresh,
        }

    def task_reorient(
        self, axis: str, radians: float, *, recenter: bool = True,
    ) -> dict[str, object]:
        if axis not in {"yaw", "pitch"}:
            raise ValueError("axis must be yaw or pitch")
        actuator = f"wrist_{axis}_ctrl"
        joint = self._joint(f"wrist_{axis}_joint")
        address = self.model.jnt_qposadr[joint]
        start_angle = float(self.data.qpos[address])
        target = start_angle + radians
        joint_limits = tuple(float(value) for value in self.model.jnt_range[joint])
        within_joint_limits = bool(joint_limits[0] <= target <= joint_limits[1])
        preflight = {
            "joint": f"wrist_{axis}_joint",
            "start_radians": start_angle,
            "requested_delta_radians": radians,
            "target_radians": target,
            "joint_limits_radians": joint_limits,
            "within_joint_limits": within_joint_limits,
            # This Cartesian arm has no numerical IK for a wrist-only rotation;
            # reachability is exactly the hinge-limit check above. Contacts and
            # unexpected collisions remain runtime safety gates.
            "ik_reachable": within_joint_limits,
            "collision_precheck": "runtime_contact_guard_required",
        }
        if not preflight["within_joint_limits"]:
            return {
                "success": False,
                "axis": axis,
                "radians": radians,
                "reorient_target_radians": target,
                "reorient_actual_radians": start_angle,
                "reorient_error_radians": radians,
                "preflight": preflight,
                "bilateral_contact_fraction": 1.0 if self._bilateral_finger_contact() else 0.0,
                "max_relative_slip_m": 0.0,
                "visual_center_before_recenter_m": None,
                "recentered_from_rgbd": False,
                "failure_code": "REORIENT_JOINT_LIMIT",
            }
        before_rotation = None
        world_axis = None
        if self.visual_world_state is not None or self._index_cube_to_world is not None:
            before_rotation = np.asarray(
                self._predicted_cube_rotation
                if self._predicted_cube_rotation is not None
                else (
                    self._index_cube_to_world
                    if self._index_cube_to_world is not None
                    else self.visual_world_state["rotation_cube_to_world"]
                )
            )
            yaw_address = self.model.jnt_qposadr[self._joint("wrist_yaw_joint")]
            wrist_yaw = float(self.data.qpos[yaw_address])
            world_axis = (
                np.array([0.0, 0.0, 1.0]) if axis == "yaw"
                else np.array([math.cos(wrist_yaw), math.sin(wrist_yaw), 0.0])
            )
        before_state = self._appearance_state
        if self.experiment_run is not None:
            cv_id = self.experiment_run.contacts.begin_verification()
            self._active_contact_verification_id = cv_id
            self.experiment_run.trajectories.set_phase("REORIENT")
            self.experiment_run.trajectories.record_command(
                sim_time=float(self.data.time),
                phase="REORIENT",
                ctrl={actuator: target},
            )
        diagnostics = self._monitored_rotation(actuator, target)
        actual_angle = float(self.data.qpos[address])
        if self._appearance_state != before_state:
            raise RuntimeError("whole-cube reorientation changed internal arrangement")
        contact_ok = diagnostics.bilateral_rate >= .8
        slip_ok = diagnostics.max_slip_m <= .03
        target_ok = abs(actual_angle - target) <= .08
        rotation_success = contact_ok and slip_ok and target_ok
        success = rotation_success
        failure_code = None
        if not contact_ok:
            failure_code = "REORIENT_BILATERAL_CONTACT_LOST"
        elif not slip_ok:
            failure_code = "REORIENT_SLIP_EXCEEDED"
        elif not target_ok:
            failure_code = "REORIENT_TARGET_NOT_REACHED"
        unexpected_contacts = sorted({
            str(name)
            for sample in self.contact_debug_trace
            for name in sample.get("unexpected_gripper_contacts", [])
        })
        if rotation_success and before_rotation is not None and world_axis is not None:
            self._predicted_cube_rotation = (
                self._axis_rotation(world_axis, radians) @ before_rotation
            )
        recentered = False
        visual_center: tuple[float, float, float] | None = None
        recenter_target: tuple[float, float] | None = None
        recenter_actual: tuple[float, float, float] | None = None
        recenter_diagnostics: dict[str, object] | None = None
        if rotation_success and recenter:
            # All eye-in-gantry cameras are mounted on robot_y alongside the
            # arm, so gantry XY motion translates the cube and cameras rigidly
            # together without changing relative framing and only risks slipping
            # the pitched grasp. Verify bilateral finger contact and visual
            # cube localization across overhead and eye-in-gantry cameras instead.
            from .perception_v2 import DeterministicCubeLocalizer
            detection = None
            seen_cameras: set[str] = set()
            for recenter_camera in (
                "overhead",
                "inspection_high_x",
                "inspection_high_y",
                "inspection_high_neg_x",
                "inspection_high_neg_y",
                "inspection_top_oblique",
                *self.HELD_CAMERAS,
            ):
                if recenter_camera in seen_cameras:
                    continue
                seen_cameras.add(recenter_camera)
                detection = DeterministicCubeLocalizer().locate(
                    self.capture_rgbd(recenter_camera)
                )
                if detection is not None:
                    break
            x_ctrl = float(self.data.ctrl[self._actuator("robot_x_ctrl")])
            y_ctrl = float(self.data.ctrl[self._actuator("robot_y_ctrl")])
            recenter_target = (x_ctrl, y_ctrl)
            if detection is not None:
                visual_center = detection.center_world_m
                recenter_actual = detection.center_world_m
            left_touch, right_touch = self._finger_contact_forces()[:2]
            bilateral = bool(left_touch and right_touch)
            recentered = bilateral and contact_ok and slip_ok and (detection is not None)
            recenter_diagnostics = {
                "bilateral_contact_fraction": float(diagnostics.bilateral_rate),
                "max_relative_slip_m": float(diagnostics.max_slip_m),
            }
            if not recentered:
                if not bilateral or not contact_ok:
                    failure_code = "RECENTER_BILATERAL_CONTACT_LOST"
                elif not slip_ok:
                    failure_code = "RECENTER_SLIP_EXCEEDED"
                else:
                    failure_code = "RECENTER_VISUAL_LOCALIZATION_FAILED"
            success = success and recentered
        if rotation_success:
            if self._index_cube_to_world is None:
                self._index_cube_to_world = np.eye(3)
            updated_index_rotation = (
                self._axis_rotation(world_axis, radians) @ self._index_cube_to_world
            )
            # Whole-cube actions are usually quarter turns, but the U-face
            # recovery deliberately uses an oblique physical view. Rounding a
            # 45-degree matrix destroys orthogonality (0.707 -> 1). Preserve
            # the continuous transform and remove only accumulated numerical
            # drift with a proper-rotation projection.
            u, _, vt = np.linalg.svd(updated_index_rotation)
            self._index_cube_to_world = u @ vt
        result = {
            "success": success,
            "axis": axis,
            "radians": radians,
            "reorient_target_radians": target,
            "reorient_actual_radians": actual_angle,
            "reorient_error_radians": actual_angle - target,
            "preflight": preflight,
            "bilateral_contact_fraction": diagnostics.bilateral_rate,
            "left_contact_fraction": diagnostics.left_rate,
            "right_contact_fraction": diagnostics.right_rate,
            "left_normal_force_n": diagnostics.left_force_n,
            "right_normal_force_n": diagnostics.right_force_n,
            "max_relative_slip_m": diagnostics.max_slip_m,
            "unexpected_contacts": unexpected_contacts,
            "visual_center_before_recenter_m": visual_center,
            "recenter_target_xy_ctrl": recenter_target,
            "visual_center_after_recenter_m": recenter_actual,
            "recenter_diagnostics": recenter_diagnostics,
            "recenter_requested": recenter,
            "recentered_from_rgbd": recentered,
            "failure_code": None if success else failure_code,
        }
        if success:
            refresh = self.refresh_visual_world_state(
                "inspection_high_x", valid_after_skill=f"reorient_{axis}"
            )
            result["world_state_refresh"] = refresh
            result["physical_success"] = True
            if not refresh["success"]:
                result["success"] = False
                result["failure_code"] = "WORLD_STATE_REFRESH_FAILED"
        if self.experiment_run is not None:
            left_pad = self.data.geom_xpos[self._id(self.mujoco.mjtObj.mjOBJ_GEOM, "left_finger_pad")]
            right_pad = self.data.geom_xpos[self._id(self.mujoco.mjtObj.mjOBJ_GEOM, "right_finger_pad")]
            jaw_gap = max(0.0, float(np.linalg.norm(left_pad - right_pad) - 0.024))
            rel_end = self._relative_cube_position().tolist()
            self.experiment_run.contacts.finalize_verification(
                skill_name="reorient_cube",
                sim_time=float(self.data.time),
                trajectory_id=self._active_trajectory_id,
                grasp_target_id=(
                    self._active_grasp_target.grasp_target_id
                    if self._active_grasp_target is not None else None
                ),
                pose_estimate_id=(
                    self._active_pose_estimate.pose_estimate_id
                    if self._active_pose_estimate is not None else None
                ),
                skill_execution_id=self._active_skill_execution_id,
                bilateral_contact_fraction=diagnostics.bilateral_rate,
                left_contact_fraction=diagnostics.left_rate,
                right_contact_fraction=diagnostics.right_rate,
                left_normal_force_n=diagnostics.left_force_n,
                right_normal_force_n=diagnostics.right_force_n,
                relative_slip_m=diagnostics.max_slip_m,
                gripper_width_m=jaw_gap,
                lift_height_m=None,
                object_motion_relative_to_gripper_m=rel_end,
                object_followed_end_effector=bool(contact_ok and slip_ok),
                unintended_contacts=unexpected_contacts,
                verification_thresholds={
                    "min_bilateral_contact_fraction": 0.80,
                    "max_relative_slip_m": 0.03,
                    "max_angle_error_rad": 0.08,
                },
                verification_result=bool(result["success"]),
                failure_reason=result.get("failure_code"),
                contact_verification_id=self._active_contact_verification_id,
            )
            self._active_contact_verification_id = None
        return result

    def refresh_visual_world_state(
        self, camera_name: str = "overhead", *, valid_after_skill: str,
    ) -> dict[str, object]:
        """Refresh pose/support from RGB-D and homography, never body truth."""
        from .facelet_mapping import PerspectiveFaceletMapper
        from .perception_v2 import DeterministicCubeLocalizer, DeterministicCubePose6DEstimator

        cameras = [camera_name]
        if valid_after_skill.startswith("reorient"):
            for name in (
                "inspection_high_y", "inspection_high_neg_x",
                "inspection_high_neg_y", "inspection_top_oblique", "overhead",
                *self.HELD_CAMERAS,
            ):
                if name not in cameras:
                    cameras.append(name)
        elif valid_after_skill in {"place_release", "before_regrasp"}:
            for name in (
                "world_top", "inspection_top", "inspection_x", "inspection_y",
                "inspection_neg_x", "inspection_neg_y",
            ):
                if name not in cameras:
                    cameras.append(name)
        frame = mapped = detection = pose = None
        fallback_observation = None
        first_frame = first_detection = None
        first_camera = camera_name
        used_camera = camera_name
        for candidate_camera in cameras:
            candidate_frame = self.capture_rgbd(candidate_camera)
            candidate_mapped = PerspectiveFaceletMapper().map_face(
                candidate_frame.rgb, frame_index=self._world_state_revision,
                source_view=f"world_refresh:{candidate_camera}",
            )
            candidate_detection = DeterministicCubeLocalizer().locate(candidate_frame)
            if candidate_detection is not None and first_detection is None:
                first_frame = candidate_frame
                first_detection = candidate_detection
                first_camera = candidate_camera
            candidate_pose = (
                DeterministicCubePose6DEstimator().estimate(candidate_frame, candidate_mapped)
                if candidate_mapped else None
            )
            candidate_observation = (
                candidate_mapped.observation if candidate_mapped is not None
                else self._read_visible_face(
                    candidate_frame.rgb, self._world_state_revision,
                    f"world_refresh_fallback:{candidate_camera}",
                )
            )
            if candidate_detection is not None and candidate_pose is not None:
                frame, mapped, detection, pose = (
                    candidate_frame, candidate_mapped, candidate_detection, candidate_pose
                )
                used_camera = candidate_camera
                break
            if candidate_detection is not None and candidate_observation is not None:
                frame, detection, fallback_observation = (
                    candidate_frame, candidate_detection, candidate_observation
                )
                used_camera = candidate_camera
                break
        normals = {
            "U": np.array([0, 0, 1]), "D": np.array([0, 0, -1]),
            "F": np.array([0, -1, 0]), "B": np.array([0, 1, 0]),
            "R": np.array([1, 0, 0]), "L": np.array([-1, 0, 0]),
        }
        reference_rotation = self._predicted_cube_rotation
        if reference_rotation is None and self._index_cube_to_world is not None:
            reference_rotation = np.asarray(self._index_cube_to_world)
        if reference_rotation is None and self.visual_world_state is not None:
            reference_rotation = np.asarray(self.visual_world_state["rotation_cube_to_world"])
        if detection is None or (pose is None and fallback_observation is None):
            if first_detection is not None and first_frame is not None and reference_rotation is not None:
                frame = first_frame
                detection = first_detection
                used_camera = first_camera
                rotation = np.asarray(reference_rotation, dtype=float)
                toward_camera = (
                    frame.calibration.camera_to_world[:3, 3]
                    - np.asarray(detection.center_world_m, dtype=float)
                )
                norm = float(np.linalg.norm(toward_camera))
                toward_camera = (
                    toward_camera / norm if norm > 1e-9
                    else -np.asarray(frame.calibration.camera_to_world[:3, 2], dtype=float)
                )
                local_toward = rotation.T @ toward_camera
                visible_face = max(normals, key=lambda f: float(np.dot(normals[f], local_toward)))
                pose_confidence = float(detection.confidence)
                pose_source = "rgbd_detection+action_history_orientation_anchor"
                ambiguity_turns, ambiguity_error = 0, 0.0
                self._predicted_cube_rotation = None
            else:
                return {
                    "success": False, "revision": self._world_state_revision,
                    "failure_code": "FULL_6D_VISUAL_POSE_UNAVAILABLE",
                    "camera": camera_name, "attempted_cameras": cameras,
                    "valid_after_skill": valid_after_skill,
                }
        else:
            if pose is not None:
                rotation = np.asarray(pose.rotation_cube_to_world)
                visible_face = pose.visible_face
                pose_confidence = pose.confidence
                pose_source = "rgbd_face_homography"
            else:
                # Approximate but complete 6-D fallback: calibrated camera axes and
                # the visually classified center face define the face frame; the
                # RGB-D contour supplies translation/yaw through `detection`.
                visible_face = fallback_observation.face
                local = np.asarray({
                    "U": ((1, 0, 0), (0, 1, 0), (0, 0, 1)),
                    "D": ((1, 0, 0), (0, -1, 0), (0, 0, -1)),
                    "F": ((1, 0, 0), (0, 0, -1), (0, -1, 0)),
                    "B": ((-1, 0, 0), (0, 0, -1), (0, 1, 0)),
                    "R": ((0, 1, 0), (0, 0, -1), (1, 0, 0)),
                    "L": ((0, -1, 0), (0, 0, -1), (-1, 0, 0)),
                }[visible_face], dtype=float).T
                camera_rotation = frame.calibration.camera_to_world[:3, :3]
                world_right = camera_rotation[:, 0]
                world_down = camera_rotation[:, 1]
                world_normal = -camera_rotation[:, 2]
                rotation = np.column_stack((world_right, world_down, world_normal)) @ local.T
                pose_confidence = fallback_observation.confidence
                pose_source = "rgbd_calibrated_face_frame_approximation"
            if reference_rotation is not None:
                from .canonical_facelets import align_face_rotation_to_reference
                _visual_candidate, ambiguity_turns, ambiguity_error = align_face_rotation_to_reference(
                    rotation, visible_face, reference_rotation,
                )
                # A single face cannot observe its in-plane D4 identity. The
                # calibrated align Skill and measured whole-cube 90-degree actions
                # are the authoritative orientation chain; vision validates it and
                # refreshes translation/visible face rather than overwriting it.
                rotation = np.asarray(reference_rotation)
                pose_source += "+action_history_orientation_anchor"
                self._predicted_cube_rotation = None
            else:
                ambiguity_turns, ambiguity_error = None, None
        local_down = rotation.T @ np.array([0.0, 0.0, -1.0])
        support_face = max(normals, key=lambda face: float(np.dot(normals[face], local_down)))
        self._world_state_revision += 1
        self.visual_world_state = {
            "success": True, "revision": self._world_state_revision,
            "valid_after_skill": valid_after_skill, "camera": used_camera,
            "center_world_m": list(detection.center_world_m),
            "rotation_cube_to_world": rotation.tolist(),
            "visible_face": visible_face, "support_face": support_face,
            "confidence": min(detection.confidence, pose_confidence),
            "source": pose_source,
            "pose_ambiguity_quarter_turns": ambiguity_turns,
            "pose_history_consistency_error": ambiguity_error,
        }
        return dict(self.visual_world_state)

    def task_align_scan_axes(self) -> dict[str, object]:
        """Physically align a grasped cube face pair to the four scan cameras."""
        joint = self._joint("wrist_yaw_joint")
        address = self.model.jnt_qposadr[joint]
        current = float(self.data.qpos[address])
        # Face pairs are symmetric every 90 degrees. Choose the nearest aligned
        # wrist target to minimize motion while preserving contact.
        target = round(current / (math.pi / 2)) * (math.pi / 2)
        before_state = self._appearance_state
        if self.experiment_run is not None:
            self.experiment_run.trajectories.set_phase("ALIGN_SCAN_AXES")
            self.experiment_run.trajectories.record_command(
                sim_time=float(self.data.time),
                phase="ALIGN_SCAN_AXES",
                ctrl={"wrist_yaw_ctrl": target},
            )
        diagnostics = self._monitored_rotation("wrist_yaw_ctrl", target)
        if before_state != self._appearance_state:
            raise RuntimeError("scan alignment changed internal arrangement")
        success = diagnostics.bilateral_rate >= .8 and diagnostics.max_slip_m <= .03
        if success and self._predicted_cube_rotation is None:
            # Initial calibration seed before any multi-view observation is
            # taken; once released/held views are captured, centre colours from
            # two orthogonal faces replace or validate this seed.
            self._predicted_cube_rotation = np.diag([-1.0, -1.0, 1.0])
        prev = self.last_grasp_telemetry
        if prev.phase_trace:
            self.last_grasp_telemetry = GraspTelemetry(
                bool(prev.success and success),
                min(prev.bilateral_contact_fraction, diagnostics.bilateral_rate),
                max(prev.max_relative_slip_m, diagnostics.max_slip_m),
                prev.lift_height_m,
                target,
                None if (prev.success and success) else (prev.failure_reason or "SCAN_ALIGNMENT_CONTACT_LOSS"),
                min(prev.left_contact_rate, diagnostics.left_rate),
                min(prev.right_contact_rate, diagnostics.right_rate),
                (prev.left_normal_force_n + diagnostics.left_force_n) / 2.0,
                (prev.right_normal_force_n + diagnostics.right_force_n) / 2.0,
                prev.trial_lift_success,
                prev.full_lift_success,
                prev.full_rotation_success,
                prev.selected_grasp_yaw_radians,
                prev.phase_trace,
            )
        self._last_skill_align_diag = {
            "success": success,
            "target_yaw_radians": target,
            "bilateral_contact_fraction": diagnostics.bilateral_rate,
            "left_contact_fraction": diagnostics.left_rate,
            "right_contact_fraction": diagnostics.right_rate,
            "left_normal_force_n": diagnostics.left_force_n,
            "right_normal_force_n": diagnostics.right_force_n,
            "max_relative_slip_m": diagnostics.max_slip_m,
        }
        return {
            "success": success,
            "target_yaw_radians": target,
            "bilateral_contact_fraction": diagnostics.bilateral_rate,
            "left_contact_fraction": diagnostics.left_rate,
            "right_contact_fraction": diagnostics.right_rate,
            "left_normal_force_n": diagnostics.left_force_n,
            "right_normal_force_n": diagnostics.right_force_n,
            "max_relative_slip_m": diagnostics.max_slip_m,
            "failure_code": None if success else "SCAN_ALIGNMENT_CONTACT_LOSS",
        }

    def _regrasp_from_pixels(self, excluded_face_pairs: set[str] | None = None) -> bool:
        from .facelet_mapping import PerspectiveFaceletMapper
        from .perception_v2 import DeterministicCubeLocalizer, DeterministicCubePose6DEstimator

        self.observation_action_trace.append("REGRASP")
        frame = self.capture_rgbd("overhead")
        detection = DeterministicCubeLocalizer().locate(frame)
        mapped = PerspectiveFaceletMapper().map_face(
            frame.rgb, frame_index=0, source_view="regrasp:overhead",
        )
        if mapped is not None:
            pose = DeterministicCubePose6DEstimator().estimate(frame, mapped)
            if pose is not None:
                self.select_grasp_candidate_6d(pose)
                excluded = excluded_face_pairs or set()
                feasible = [candidate for candidate in self.last_grasp_candidates
                            if candidate.ik_feasible and candidate.collision_free
                            and candidate.face_pair not in excluded]
                candidate = max(
                    feasible,
                    key=lambda item: (item.contact_geometry_score, -item.motion_cost),
                    default=None,
                )
                self.last_selected_grasp_candidate = candidate
                return candidate is not None and self.approach_grasp_lift(
                    # Robust centroid uses all segmented metric-depth pixels;
                    # face corners determine the full rotation. Both are camera
                    # estimates and neither reads simulator pose.
                    detection.center_world_m if detection is not None else pose.center_world_m,
                    grasp_candidate=candidate,
                )
        # Explicit degraded path for images where no complete face quadrilateral
        # can be mapped; result metadata makes the yaw-only fallback observable.
        if detection is None:
            return False
        excluded = excluded_face_pairs or set()
        if excluded:
            feasible = [
                candidate for candidate in self.generate_grasp_candidates(
                    detection.center_world_m, detection.yaw_radians
                )
                if candidate.ik_feasible and candidate.collision_free
                and candidate.face_pair not in excluded
            ]
            candidate = max(
                feasible,
                key=lambda item: (item.contact_geometry_score, -item.motion_cost),
                default=None,
            )
            self.last_selected_grasp_candidate = candidate
            return candidate is not None and self.approach_grasp_lift(
                detection.center_world_m, grasp_candidate=candidate,
            )
        return self.approach_grasp_lift(
            detection.center_world_m, detection.yaw_radians,
        )

    def active_scan(self) -> list[FaceObservation]:
        observations: list[FaceObservation] = []
        self.observation_action_trace.clear()
        # Four yaw placements expose side faces; pitch placements put the original
        # bottom on a side. Missing/occluded stickers remain None in the evidence.
        rotations = [
            ("wrist_yaw_ctrl", math.pi / 2),
            ("wrist_yaw_ctrl", math.pi),
            ("wrist_yaw_ctrl", -math.pi / 2),
            ("wrist_pitch_ctrl", math.pi / 2),
            ("wrist_pitch_ctrl", -math.pi / 2),
        ]
        for cycle in range(6):
            if not self._place_and_release():
                break
            observations.extend(self._observe_released_cube(cycle * 3))
            complete_faces = {
                item.face for item in observations if all(color is not None for color in item.stickers)
            }
            if len(complete_faces) == 6:
                break
            if cycle >= len(rotations) or not self._regrasp_from_pixels():
                break
            actuator, target = rotations[cycle]
            self.observation_action_trace.append("ROTATE")
            before_state = self._appearance_state
            diagnostics = self._monitored_rotation(actuator, target)
            if before_state != self._appearance_state:
                raise RuntimeError("whole-cube rotation changed internal cube state")
            if diagnostics.bilateral_rate < .8 or diagnostics.max_slip_m > .03:
                break
        return observations

    def rotate_whole_cube_and_reobserve(self, yaw_radians: float = math.pi / 2) -> RGBDFrame:
        """Physically rotate the grasped free body through the wrist joint, then capture RGB-D."""
        before_state = self._appearance_state
        diagnostics = self._monitored_rotation("wrist_yaw_ctrl", yaw_radians)
        if before_state != self._appearance_state:
            raise RuntimeError("whole-cube rotation must not change internal arrangement")
        previous = self.last_grasp_telemetry
        success = (
            previous.success and diagnostics.bilateral_rate >= .8
            and diagnostics.max_slip_m <= .03
        )
        self.last_grasp_telemetry = GraspTelemetry(
            success, min(previous.bilateral_contact_fraction, diagnostics.bilateral_rate),
            max(previous.max_relative_slip_m, diagnostics.max_slip_m), previous.lift_height_m,
            yaw_radians, None if success else "contact loss or slip during whole-cube rotation",
            min(previous.left_contact_rate, diagnostics.left_rate),
            min(previous.right_contact_rate, diagnostics.right_rate),
            (previous.left_normal_force_n + diagnostics.left_force_n) / 2,
            (previous.right_normal_force_n + diagnostics.right_force_n) / 2,
            previous.trial_lift_success, previous.full_lift_success, success,
            previous.selected_grasp_yaw_radians, previous.phase_trace + ("ROTATE",),
        )
        frame = self.capture_rgbd("overhead")
        self.frames.append(frame.rgb)
        return frame

    def execute_physical_turn(self, move: str) -> ActionFeedback:
        if getattr(self, "physical_u", False) or getattr(self, "full_26_cubie", False):
            raise RuntimeError("Use contact-driven fixture; symbolic appearance updates are forbidden")
        request = ActionRequest(move, self._appearance_state, self._plan_version)
        feedback = self._turner.execute(request)
        if feedback.success:
            self._appearance_state = self.engine.apply_move(self._appearance_state, move)
            self._set_sticker_colors(self._appearance_state)
            self.mujoco.mj_forward(self.model, self.data)
        return feedback

    def hand_over(self) -> bool:
        self._set_controls({"robot_x_ctrl": .55, "robot_y_ctrl": .35, "robot_z_ctrl": -.28}, 1.2)
        self.data.eq_active[self._equality("human_grasp_weld")] = 1
        self.step_physics()
        confirmed = bool(self.data.eq_active[self._equality("human_grasp_weld")])
        if confirmed:
            self._set_controls({"left_finger_ctrl": 0, "right_finger_ctrl": 0}, .3)
        return confirmed

    def wait_for_human_move(self, move: str | None) -> str | None:
        if move:
            feedback = self.execute_physical_turn(move)
            return move if feedback.success else None
        return None

    def take_back(self) -> bool:
        # Human receiver is an explicit Mock fixture. Robot reacquisition itself
        # must establish bilateral pad contact before the fixture releases.
        self._set_controls({"left_finger_ctrl": .074, "right_finger_ctrl": .074}, .3)
        confirmed = self._bilateral_finger_contact()
        if confirmed:
            self.data.eq_active[self._equality("human_grasp_weld")] = 0
            self._monitored_motion({"robot_z_ctrl": -.18}, .8)
        return confirmed

    def record_frame(self) -> None:
        try:
            self.frames.append(self.capture_rgbd("overhead").rgb)
        except Exception:
            pass

    def write_video(self, path: str | Path | None = None, fps: int = 12) -> Path | None:
        destination = Path(path) if path else self.video_path
        if destination is None or not self.frames:
            return None
        import imageio.v2 as imageio
        import json
        from .replay_timing import resample_indices
        destination.parent.mkdir(parents=True, exist_ok=True)
        indices = (list(range(len(self.frames))) if self.video_timing == "legacy"
                   else resample_indices(self.frames.timestamps, fps))
        with imageio.get_writer(destination, fps=fps) as writer:
            for index in indices:
                writer.append_data(self.frames[index])
        alignment = {"mode": self.video_timing, "fps": fps,
                     "source_sim_times": self.frames.timestamps,
                     "video_frames": [{"frame": i,"video_seconds": i/fps,
                                       "source_index": idx,"sim_time": self.frames.timestamps[idx]}
                                      for i,idx in enumerate(indices)],
                     "motion_segments": self.motion_timing.events,
                     "physics_steps": self.motion_timing.steps,
                     "physics_digest": self.motion_timing.digest.hexdigest()}
        destination.with_suffix(".timing.json").write_text(json.dumps(alignment, indent=2,
            default=lambda x: x.tolist() if isinstance(x,np.ndarray) else str(x)))
        return destination

    def write_debug_frame(self, frame: RGBDFrame, path: str | Path) -> Path:
        """Write an explicitly requested camera artifact; never includes privileged overlays."""
        import imageio.v2 as imageio
        destination = Path(path)
        destination.parent.mkdir(parents=True, exist_ok=True)
        imageio.imwrite(destination, frame.rgb)
        return destination

    def relocalize_cube_rgbd(
        self,
        *,
        approx_xy: tuple[float, float] = (0.35, -0.32),
        clear_station: bool = False,
        token: CancellationToken | None = None,
    ) -> tuple[float, float]:
        """Measure cube tabletop XY center strictly from RGB-D camera images (never cube qpos/xpos)."""
        if self.flip_controller is None:
            raise RuntimeError("relocalize_cube_rgbd requires full_26_cubie=True")
        ff = self.flip_controller
        prep: dict[str, float] = {"robot_z_ctrl": -0.145, "wrist_pitch_ctrl": 0.0}
        if clear_station:
            prep.update({"base_clear_ctrl": 0.25, "turn_z_ctrl": 0.0})
        ff._ramp("rgbd_reloc_prep", prep, 0.25, token=token)

        def _scan_with_down_cam(cx_est: float, cy_est: float) -> tuple[tuple[float, float], int, float | None]:
            from .perception_v2 import DeterministicCubeLocalizer

            ff._ramp("rgbd_reloc_z_safe", {"robot_z_ctrl": -0.145}, 0.16, token=token)
            ff._move_xy("rgbd_reloc_xy", (cx_est, cy_est + 0.22), token=token)
            ff._ramp("rgbd_reloc_z_up", {"robot_z_ctrl": -0.09}, 0.20, settle_s=0.10, token=token)
            frame = self.capture_rgbd("inspection_down_neg_y")
            det = DeterministicCubeLocalizer().locate(frame)
            if det is not None:
                cw = det.center_world_m
                yaw_val = float(det.yaw_radians) if det.yaw_radians is not None else None
                return (float(cw[0]), float(cw[1])), int(det.pixel_count), yaw_val
            depth = frame.depth_m
            cal = frame.calibration
            mask = (depth > 0.05) & (depth < 0.185)
            ys, xs = np.where(mask)
            zs = depth[ys, xs]
            if len(zs) < 50:
                return (cx_est, cy_est), 0, None
            px = (xs - cal.cx) / cal.fx * zs
            py = -(ys - cal.cy) / cal.fy * zs
            pts_cam = np.stack([px, py, -zs], axis=1)
            c2w = cal.camera_to_world
            pts_w = (pts_cam @ c2w[:3, :3].T) + c2w[:3, 3]
            center = np.mean(pts_w[:, :2], axis=0)
            return (float(center[0]), float(center[1])), int(len(zs)), None

        c_xy, n_pts, yaw_est = _scan_with_down_cam(float(approx_xy[0]), float(approx_xy[1]))
        if n_pts < 4000:
            # Coarse wide-FOV overhead look with gantry parked clear, then recenter downward camera
            ff._ramp("rgbd_coarse_z", {"robot_z_ctrl": -0.145}, 0.16, token=token)
            ff._move_xy("rgbd_coarse_park", (-0.42, 0.25), token=token)
            loc = self.refresh_visual_world_state("world_top", valid_after_skill="before_regrasp")
            if loc.get("success") and self.visual_world_state is not None:
                cw = self.visual_world_state["center_world_m"]
                c_xy2, n_pts2, yaw_est2 = _scan_with_down_cam(float(cw[0]), float(cw[1]))
                if n_pts2 >= n_pts:
                    c_xy = c_xy2
                    if yaw_est2 is not None:
                        yaw_est = yaw_est2
        self._last_reloc_yaw_rad = yaw_est
        self._cube_26_center_xy = c_xy
        return c_xy

    def recover_preempted_turn_slice(
        self,
        mode: str = "UNWIND_TO_ZERO",
        *,
        release_base_after: bool = True,
    ) -> dict[str, Any]:
        """Recover a preempted off-lattice top slice at the turn station via pure contact torque."""
        if not self.full_26_cubie or self.cube_26_turner is None or self.flip_controller is None:
            raise RuntimeError("recover_preempted_turn_slice requires MuJoCoEmbodiedBackend(full_26_cubie=True)")
        res = self.cube_26_turner.recover_preempted_turn_slice(
            mode=mode,  # type: ignore[arg-type]
            release_base_after=release_base_after,
        )
        aligned, res_deg = self.flip_controller.sync_station_lattice_state()
        if self.visual_world_state is not None and res.success:
            self.visual_world_state["pose_valid"] = True
        return {
            "success": bool(res.success),
            "mode": mode,
            "top_axis_name": res.top_axis_name,
            "target_angle_rad": res.target_angle_rad,
            "actual_angle_rad": res.actual_angle_rad,
            "max_slice_misalignment_deg": round(res.max_slice_misalignment_deg, 3),
            "contact_driven": res.contact_driven,
            "top_pad_contact_steps": res.top_pad_contact_steps,
            "base_pad_contact_steps": res.base_pad_contact_steps,
            "is_lattice_aligned": aligned,
            "residual_slice_angle_deg": round(res_deg, 3),
            "failure_code": res.failure_code,
            "failure_reason": res.failure_reason,
            "telemetry": dict(res.telemetry),
        }

    def execute_physical_face_turn(
        self,
        move: str,
        *,
        token: CancellationToken | None = None,
        contact_enabled: bool = True,
    ) -> dict[str, Any]:
        """Execute any of the 18 standard moves via Flip-and-Feed + contact-driven single top fixture."""
        from cube_relay.cube.moves import LEGAL_MOVES
        from .physical_cube_26 import move_to_top_fixture_angle_rad

        if not self.full_26_cubie or self.cube_26_turner is None or self.flip_controller is None or self.orientation_tracker is None:
            raise RuntimeError("execute_physical_face_turn requires MuJoCoEmbodiedBackend(full_26_cubie=True)")
        mv = str(move).strip()
        if mv not in LEGAL_MOVES:
            raise ValueError(f"Illegal Rubik's cube move: {move!r}")

        aligned, res_deg = self.flip_controller.sync_station_lattice_state()
        if not aligned:
            return {
                "success": False,
                "move": mv,
                "target_face": mv[0],
                "is_lattice_aligned": False,
                "residual_slice_angle_deg": round(res_deg, 3),
                "failure_code": "SLICE_MISALIGNED_JAM",
                "failure_reason": (
                    f"Turn station top slice is misaligned ({res_deg:+.2f} deg); "
                    "recover_preempted_turn_slice must execute before lifting or switching axes"
                ),
            }

        if self._cube_26_location == "station":
            xy = self.relocalize_cube_rgbd(approx_xy=(0.35, -0.32), clear_station=True, token=token)
        else:
            from .canonical_facelets import axis_rotation
            from .perception_v2 import DeterministicCubeLocalizer

            if (
                self.visual_world_state is None
                or not self.visual_world_state.get("center_world_m")
                or self.orientation_tracker.source == "initial"
            ):
                # Park gantry out of overhead view before localizing so the arm never occludes cube yaw
                self.flip_controller._ramp("init_park_z", {"robot_z_ctrl": -0.145, "wrist_pitch_ctrl": 0.0}, 0.16, token=token)
                self.flip_controller._move_xy("init_park_xy", (-0.42, 0.25), token=token)
                det = DeterministicCubeLocalizer().locate(self.capture_rgbd("overhead"))
                if det is None:
                    return {
                        "success": False,
                        "move": mv,
                        "is_lattice_aligned": True,
                        "residual_slice_angle_deg": 0.0,
                        "failure_code": "VISUAL_LOCALIZATION_FAILED",
                        "failure_reason": "Cube not visually localized from overhead RGB-D",
                    }
                refined_xy = self.relocalize_cube_rgbd(
                    approx_xy=(float(det.center_world_m[0]), float(det.center_world_m[1])),
                    clear_station=False,
                    token=token,
                )
                fine_yaw = (
                    float(self._last_reloc_yaw_rad)
                    if getattr(self, "_last_reloc_yaw_rad", None) is not None
                    else float(det.yaw_radians or 0.0)
                )
                obs_rel: list[FaceObservation] = []
                if self._index_cube_to_world is None:
                    near_station = refined_xy[0] > 0.14 and refined_xy[1] < -0.02
                    near_edge = abs(refined_xy[0]) > 0.30 or abs(refined_xy[1]) > 0.20
                    yaw_folded = ((fine_yaw + math.pi * 0.25) % (math.pi * 0.5)) - math.pi * 0.25
                    off_axis = abs(yaw_folded) > math.radians(10.0)
                    if not near_station and not near_edge and not off_axis:
                        obs_rel = self.task_observe_released()
                    if self._index_cube_to_world is None:
                        grasp_yaw = self.flip_controller.select_collision_free_table_yaw(refined_xy, yaw_folded)
                        ok_sq, st_sq, rsn_sq = self.flip_controller._pick_up_cube(
                            refined_xy,
                            grasp_yaw,
                            z_grasp=-0.282,
                            is_station=False,
                            token=token,
                        )
                        if not ok_sq:
                            preempted_sq = st_sq in (ChunkStatus.PREEMPTED_SAFE_HOLD, ChunkStatus.SAFETY_ABORTED)
                            return {
                                "success": False,
                                "move": mv,
                                "target_face": mv[0],
                                "flips_required": 0,
                                "flips_executed": 0,
                                "regrasps_executed": 0,
                                "preempted": preempted_sq,
                                "chunk_status": st_sq.value,
                                "is_lattice_aligned": True,
                                "residual_slice_angle_deg": 0.0,
                                "failure_code": "FLIP_PREEMPTED" if preempted_sq else "FLIP_AND_FEED_FAILED",
                                "failure_reason": rsn_sq,
                            }
                        self.flip_controller._ramp(
                            "init_sq_lift",
                            {"robot_z_ctrl": -0.145},
                            0.30,
                            settle_s=0.06,
                            hold_grip=True,
                            token=token,
                        )
                        self.flip_controller._ramp(
                            "init_sq_yaw",
                            {"wrist_yaw_ctrl": 0.0},
                            0.30,
                            settle_s=0.06,
                            hold_grip=True,
                            token=token,
                        )
                        self.flip_controller._move_xy(
                            "init_sq_move",
                            (0.0, 0.0),
                            hold_grip=True,
                            extra_ctrls={"wrist_yaw_ctrl": 0.0},
                            token=token,
                        )
                        pm = self.flip_controller.pad_midpoint_world()
                        self.flip_controller._ramp(
                            "init_sq_place",
                            {
                                "robot_x_ctrl": self.flip_controller._ctrl("robot_x_ctrl") - float(pm[0]),
                                "robot_y_ctrl": self.flip_controller._ctrl("robot_y_ctrl") - float(pm[1]),
                                "robot_z_ctrl": -0.272,
                            },
                            0.34,
                            settle_s=0.06,
                            hold_grip=True,
                            token=token,
                        )
                        self.flip_controller._ramp(
                            "init_sq_open",
                            {"left_finger_ctrl": 0.0, "right_finger_ctrl": 0.0},
                            0.16,
                            settle_s=0.06,
                            token=token,
                        )
                        self.flip_controller._ramp(
                            "init_sq_clear_z",
                            {"robot_z_ctrl": -0.145, "base_clear_ctrl": 0.0},
                            0.45,
                            settle_s=0.10,
                            token=token,
                        )
                        obs_rel = self.task_observe_released()
                        refined_xy = self.relocalize_cube_rgbd(
                            approx_xy=(0.0, 0.0),
                            clear_station=False,
                            token=token,
                        )
                        fine_yaw = (
                            float(self._last_reloc_yaw_rad)
                            if getattr(self, "_last_reloc_yaw_rad", None) is not None
                            else 0.0
                        )
                discrete_rot = (
                    np.asarray(self._index_cube_to_world, dtype=float)
                    if self._index_cube_to_world is not None
                    else (
                        np.asarray(self.visual_world_state["rotation_cube_to_world"], dtype=float)
                        if self.visual_world_state and "rotation_cube_to_world" in self.visual_world_state
                        else np.eye(3, dtype=float)
                    )
                )
                # Fold continuous box yaw onto nearest 90-deg lattice resolved from center colors
                horiz_cols = [discrete_rot[:, k] for k in range(3) if abs(float(discrete_rot[2, k])) < 0.5]
                yaw_d = (
                    math.atan2(float(horiz_cols[0][1]), float(horiz_cols[0][0]))
                    if horiz_cols
                    else math.atan2(float(discrete_rot[1, 0]), float(discrete_rot[0, 0]))
                )
                yaw_err = ((fine_yaw - yaw_d + math.pi * 0.25) % (math.pi * 0.5)) - math.pi * 0.25
                rot = axis_rotation(np.array([0.0, 0.0, 1.0]), yaw_err) @ discrete_rot
                self._world_state_revision += 1
                self.visual_world_state = {
                    "center_world_m": [refined_xy[0], refined_xy[1], float(det.center_world_m[2])],
                    "rotation_cube_to_world": rot,
                    "pose_valid": True,
                    "observed_initial_faces": [o.face for o in obs_rel],
                    "source": "overhead_plus_center_cv_rgbd",
                    "revision": self._world_state_revision,
                }
                self.orientation_tracker.update_from_visual_pose(rot, source="initial_visual_localize")
                xy = refined_xy
            else:
                cw = self.visual_world_state["center_world_m"]
                xy = (float(cw[0]), float(cw[1]))

        def _relocalize_laid_cube() -> tuple[tuple[float, float], np.ndarray | None]:
            from .canonical_facelets import axis_rotation

            xy_laid = self.relocalize_cube_rgbd(approx_xy=(0.0, 0.0), clear_station=False, token=token)
            yaw_laid = getattr(self, "_last_reloc_yaw_rad", None)
            if yaw_laid is None:
                return xy_laid, None
            cur_rot = self.orientation_tracker.snapshot().rotation_cube_to_world
            horiz_cols = [cur_rot[:, k] for k in range(3) if abs(float(cur_rot[2, k])) < 0.5]
            if not horiz_cols:
                return xy_laid, None
            yaw_cur = math.atan2(float(horiz_cols[0][1]), float(horiz_cols[0][0]))
            yaw_corr = ((float(yaw_laid) - yaw_cur + math.pi * 0.25) % (math.pi * 0.5)) - math.pi * 0.25
            return xy_laid, axis_rotation(np.array([0.0, 0.0, 1.0]), yaw_corr) @ cur_rot

        ff_res = self.flip_controller.orient_face_up_and_dock(
            mv[0],
            self.orientation_tracker,
            current_location=self._cube_26_location,
            current_center_xy=xy,
            visual_relocalize_fn=_relocalize_laid_cube,
            token=token,
        )
        if not ff_res.success:
            aligned_now, res_deg_now = self.flip_controller.sync_station_lattice_state()
            return {
                "success": False,
                "move": mv,
                "target_face": mv[0],
                "flips_required": ff_res.flips_required,
                "flips_executed": ff_res.flips_executed,
                "regrasps_executed": ff_res.regrasps_executed,
                "preempted": ff_res.preempted,
                "chunk_status": ff_res.chunk_status,
                "is_lattice_aligned": aligned_now,
                "residual_slice_angle_deg": round(res_deg_now, 3),
                "interrupt_to_hold_sim_ms": getattr(ff_res, "interrupt_to_hold_sim_ms", None),
                "failure_code": "FLIP_PREEMPTED" if ff_res.preempted else "FLIP_AND_FEED_FAILED",
                "failure_reason": ff_res.failure_reason,
            }

        turn_res = self.cube_26_turner.execute_top_face_turn(
            move_to_top_fixture_angle_rad(mv),
            contact_enabled=contact_enabled,
            token=token,
            release_base_after=True,
        )
        aligned_after, res_deg_after = self.flip_controller.sync_station_lattice_state()
        self._cube_26_location = "station"
        self._cube_26_center_xy = (0.35, -0.32)

        snap = self.orientation_tracker.snapshot()
        self._index_cube_to_world = snap.rotation_cube_to_world.copy()
        self._predicted_cube_rotation = snap.rotation_cube_to_world.copy()
        self._world_state_revision += 1
        self.visual_world_state = {
            "center_world_m": [0.35, -0.32, 0.66],
            "rotation_cube_to_world": snap.rotation_cube_to_world.copy(),
            "pose_valid": bool(turn_res.success and aligned_after),
            "source": "turn_station_tracked",
            "revision": self._world_state_revision,
        }
        return {
            "success": bool(turn_res.success),
            "move": mv,
            "target_face": mv[0],
            "flips_required": ff_res.flips_required,
            "flips_executed": ff_res.flips_executed,
            "regrasps_executed": ff_res.regrasps_executed,
            "target_angle_rad": turn_res.target_angle_rad,
            "actual_angle_rad": turn_res.actual_angle_rad,
            "angle_error_deg": round(math.degrees(abs(turn_res.actual_angle_rad - turn_res.target_angle_rad)), 3),
            "max_slice_misalignment_deg": round(turn_res.max_slice_misalignment_deg, 3),
            "is_lattice_aligned": aligned_after,
            "residual_slice_angle_deg": round(res_deg_after, 3),
            "contact_driven": turn_res.contact_driven,
            "top_pad_contact_steps": turn_res.top_pad_contact_steps,
            "base_pad_contact_steps": turn_res.base_pad_contact_steps,
            "preempted": turn_res.preempted,
            "chunk_status": turn_res.chunk_status,
            "failure_code": turn_res.failure_code,
            "failure_reason": turn_res.failure_reason,
            "interrupt_to_hold_sim_ms": (turn_res.telemetry or {}).get("interrupt_to_hold_sim_ms"),
            "interrupt_to_hold_wall_ms": (turn_res.telemetry or {}).get("interrupt_to_hold_wall_ms"),
            "orientation": {
                "top_face": snap.top_face,
                "bottom_face": snap.bottom_face,
                "total_flips": snap.flips_executed,
                "total_regrasps": snap.regrasps_executed,
                "total_flip_time_s": snap.flip_time_s,
            },
        }

    def inspect_26_cubie_via_independent_cameras(
        self,
        *,
        token: CancellationToken | None = None,
    ) -> dict[str, Any]:
        """Verify all 54 stickers strictly through independent RGB-D camera scans (2 tabletop poses)."""
        from .six_face_inspection import StickerStateFusion

        if not self.full_26_cubie or self.flip_controller is None or self.orientation_tracker is None:
            raise RuntimeError("inspect_26_cubie_via_independent_cameras requires full_26_cubie=True")

        aligned, res_deg = self.flip_controller.sync_station_lattice_state()
        if not aligned:
            return {
                "success": False,
                "observed_count": 0,
                "failure_code": "SLICE_MISALIGNED_JAM",
                "reason": (
                    f"Turn station top slice is misaligned ({res_deg:+.2f} deg); "
                    "recover_preempted_turn_slice is required before independent camera scan"
                ),
            }

        ff = self.flip_controller
        # 1. Move cube cleanly from current position to open table (0.0, 0.0) without turning any layer
        if self._cube_26_location == "station":
            xy = self.relocalize_cube_rgbd(approx_xy=(0.35, -0.32), clear_station=True, token=token)
            yaw_0 = self.orientation_tracker.canonical_table_yaw()
            ok, st, rsn = ff._pick_up_cube(xy, yaw_0, z_grasp=-0.272, is_station=True, token=token)
            if not ok:
                return {"success": False, "observed_count": 0, "reason": rsn or st.value}
            ff._ramp("scan_lift", {"robot_z_ctrl": -0.145, "base_clear_ctrl": 0.0}, 0.28, hold_grip=True, token=token)
            ff._move_xy("scan_carry", (0.0, 0.0), hold_grip=True, extra_ctrls={"wrist_yaw_ctrl": 0.0}, token=token)
            pm = ff.pad_midpoint_world()
            ff._ramp(
                "scan_place",
                {
                    "robot_x_ctrl": ff._ctrl("robot_x_ctrl") - float(pm[0]),
                    "robot_y_ctrl": ff._ctrl("robot_y_ctrl") - float(pm[1]),
                    "robot_z_ctrl": -0.272,
                },
                0.34,
                settle_s=0.08,
                hold_grip=True,
                token=token,
            )
            ff._ramp("scan_release", {"left_finger_ctrl": 0.0, "right_finger_ctrl": 0.0}, 0.16, settle_s=0.06, token=token)
            ff._ramp("scan_raise", {"robot_z_ctrl": -0.145}, 0.45, settle_s=0.14, token=token)
            self._cube_26_location = "table"
            self._cube_26_center_xy = (0.0, 0.0)

        # Pass 1: observe top + 4 sides (45 stickers) via independent released views
        obs_1 = self.task_observe_released(frame_offset=0)
        fusion = StickerStateFusion()
        for o in obs_1:
            fusion.add(o)

        # Pass 2: pick up cleanly at table center, pitch -90 deg, and observe bottom/free faces via HELD_CAMERAS
        c_xy = self.relocalize_cube_rgbd(approx_xy=(0.0, 0.0), clear_station=False, token=token)
        if self._index_cube_to_world is not None and self.orientation_tracker.source == "initial":
            from .canonical_facelets import axis_rotation

            discrete_rot = np.asarray(self._index_cube_to_world, dtype=float)
            fine_yaw = getattr(self, "_last_reloc_yaw_rad", None)
            if fine_yaw is not None:
                horiz_cols = [discrete_rot[:, k] for k in range(3) if abs(float(discrete_rot[2, k])) < 0.5]
                yaw_d = (
                    math.atan2(float(horiz_cols[0][1]), float(horiz_cols[0][0]))
                    if horiz_cols
                    else math.atan2(float(discrete_rot[1, 0]), float(discrete_rot[0, 0]))
                )
                yaw_err = ((float(fine_yaw) - yaw_d + math.pi * 0.25) % (math.pi * 0.5)) - math.pi * 0.25
                rot_vis = axis_rotation(np.array([0.0, 0.0, 1.0]), yaw_err) @ discrete_rot
            else:
                rot_vis = discrete_rot
            self.orientation_tracker.update_from_visual_pose(rot_vis, source="independent_scan_pass1_cv")

        yaw_p = self.orientation_tracker.canonical_table_yaw()
        ok, st, rsn = ff._pick_up_cube(c_xy, yaw_p, z_grasp=-0.272, is_station=False, token=token)
        obs_2: list[FaceObservation] = []
        if ok:
            from .canonical_facelets import axis_rotation

            ff._ramp("inspect_held_lift", {"robot_z_ctrl": -0.145}, 0.30, hold_grip=True, token=token)
            ff._ramp(
                "inspect_held_pitch",
                {"wrist_pitch_ctrl": -math.pi * 0.5, "wrist_yaw_ctrl": 0.0},
                0.42,
                settle_s=0.12,
                hold_grip=True,
                token=token,
            )
            self.orientation_tracker.record_verified_flip(
                axis_rotation(np.array([1.0, 0.0, 0.0]), -math.pi * 0.5)
                @ axis_rotation(np.array([0.0, 0.0, 1.0]), -yaw_p),
                is_flip=True,
                source="inspect_held_pitch",
            )
            self._index_cube_to_world = self.orientation_tracker.snapshot().rotation_cube_to_world.copy()
            self._predicted_cube_rotation = self._index_cube_to_world.copy()
            obs_2 = self.task_observe_held(frame_offset=len(obs_1))
            for o in obs_2:
                fusion.add(o)
            # Re-seat back onto table cleanly and open fingers so workspace remains clean
            ff._ramp(
                "inspect_unpitch",
                {"wrist_pitch_ctrl": 0.0, "wrist_yaw_ctrl": 0.0},
                0.38,
                settle_s=0.06,
                hold_grip=True,
                token=token,
            )
            ff._ramp("inspect_re_seat", {"robot_z_ctrl": -0.272}, 0.34, settle_s=0.06, hold_grip=True, token=token)
            ff._ramp("inspect_open", {"left_finger_ctrl": 0.0, "right_finger_ctrl": 0.0}, 0.16, settle_s=0.04, token=token)
            ff._ramp("inspect_clear_z", {"robot_z_ctrl": -0.145}, 0.45, settle_s=0.10, token=token)
            ff._move_xy("inspect_park_clear", (-0.42, 0.25), token=token)
            self.orientation_tracker.record_verified_flip(
                axis_rotation(np.array([1.0, 0.0, 0.0]), math.pi * 0.5),
                is_flip=True,
                source="inspect_held_unpitch",
            )
            self._cube_26_location = "table"
            self._cube_26_center_xy = c_xy

        try:
            facelets_str = fusion.validated_facelets()
        except ValueError:
            facelets_str = fusion.facelets()
        return {
            "success": bool(fusion.unknown_count == 0 and fusion.conflict_count == 0 and facelets_str is not None),
            "observed_count": int(fusion.observed_sticker_count),
            "observed_faces": int(fusion.observed_face_count),
            "unknown_count": int(fusion.unknown_count),
            "conflict_count": int(fusion.conflict_count),
            "facelets": facelets_str,
            "pass1_faces": [o.face for o in obs_1],
            "pass2_faces": [o.face for o in obs_2],
        }

    def park_arm_standby(self, *, token: CancellationToken | None = None) -> dict[str, Any]:
        """Park gantry arm cleanly at (-0.42, 0.25) leaving overhead & tabletop handover area unobstructed."""
        if not self.full_26_cubie or self.flip_controller is None:
            raise RuntimeError("park_arm_standby requires full_26_cubie=True")
        ff = self.flip_controller
        ok1, st1, rsn1 = ff._ramp(
            "standby_raise",
            {
                "robot_z_ctrl": -0.145,
                "wrist_pitch_ctrl": 0.0,
                "wrist_yaw_ctrl": 0.0,
                "left_finger_ctrl": 0.0,
                "right_finger_ctrl": 0.0,
                "base_clear_ctrl": 0.0,
                "turn_z_ctrl": 0.0,
                "turn_pos_ctrl": 0.0,
                "turn_neg_ctrl": 0.0,
            },
            0.28,
            settle_s=0.04,
            token=token,
        )
        if not ok1:
            return {"success": False, "failure_reason": rsn1 or st1.value}
        ok2, st2, rsn2 = ff._move_xy("standby_park_xy", (-0.42, 0.25), token=token)
        return {"success": bool(ok2), "failure_reason": None if ok2 else (rsn2 or st2.value)}

    def handover_26_cubie_to_table(self, *, token: CancellationToken | None = None) -> dict[str, Any]:
        """Extract cube from gripper or turn_station (if held/docked), release at desktop handover center, and park arm at (-0.42, 0.25)."""
        from .perception_v2 import DeterministicCubeLocalizer

        if not self.full_26_cubie or self.flip_controller is None or self.orientation_tracker is None:
            raise RuntimeError("handover_26_cubie_to_table requires full_26_cubie=True")
        ff = self.flip_controller
        aligned, res_deg = ff.sync_station_lattice_state()
        if not aligned:
            return {
                "success": False,
                "failure_code": "SLICE_MISALIGNED_JAM",
                "failure_reason": f"Station slice misaligned ({res_deg:+.2f} deg); recover_preempted_turn_slice required first",
            }

        # Case 1: Gripper is already holding the cube (e.g. preempted mid-transport/flip) -> place at (0, 0).
        if self._bilateral_finger_contact():
            pitch_val = float(self.data.qpos[self.model.jnt_qposadr[self._joint("wrist_pitch_joint")]])
            if abs(math.sin(pitch_val)) > 0.25:
                ff._ramp("handover_unpitch_z", {"robot_z_ctrl": -0.145}, 0.24, hold_grip=True, token=token)
                ff._ramp("handover_unpitch", {"wrist_pitch_ctrl": 0.0}, 0.30, settle_s=0.06, hold_grip=True, token=token)
            else:
                ff._ramp("handover_held_lift", {"robot_z_ctrl": -0.145, "base_clear_ctrl": 0.0}, 0.24, hold_grip=True, token=token)
            ff._move_xy("handover_held_carry", (0.0, 0.0), hold_grip=True, extra_ctrls={"wrist_yaw_ctrl": 0.0}, token=token)
            pm = ff.pad_midpoint_world()
            ff._ramp(
                "handover_held_place",
                {
                    "robot_x_ctrl": ff._ctrl("robot_x_ctrl") - float(pm[0]),
                    "robot_y_ctrl": ff._ctrl("robot_y_ctrl") - float(pm[1]),
                    "robot_z_ctrl": -0.272,
                },
                0.34,
                settle_s=0.08,
                hold_grip=True,
                token=token,
            )
            ff._ramp("handover_held_release", {"left_finger_ctrl": 0.0, "right_finger_ctrl": 0.0}, 0.16, settle_s=0.06, token=token)
            ff._ramp("handover_held_raise", {"robot_z_ctrl": -0.145}, 0.38, settle_s=0.08, token=token)
            self._cube_26_location = "table"
            self._cube_26_center_xy = (0.0, 0.0)
        else:
            # Determine via RGB-D whether cube sits in turn_station even if interrupted mid-dock
            det_oh = DeterministicCubeLocalizer().locate(self.capture_rgbd("overhead"))
            in_station_rgbd = bool(
                det_oh is not None
                and float(det_oh.center_world_m[0]) > 0.18
                and float(det_oh.center_world_m[1]) < -0.10
            )
            if self._cube_26_location == "station" or in_station_rgbd:
                xy = self.relocalize_cube_rgbd(approx_xy=(0.35, -0.32), clear_station=True, token=token)
                yaw_0 = self.orientation_tracker.canonical_table_yaw()
                ok, st, rsn = ff._pick_up_cube(xy, yaw_0, z_grasp=-0.272, is_station=True, token=token)
                if not ok:
                    return {"success": False, "failure_code": "HANDOVER_PICKUP_FAILED", "failure_reason": rsn or st.value}
                ff._ramp("handover_lift", {"robot_z_ctrl": -0.145, "base_clear_ctrl": 0.0}, 0.28, hold_grip=True, token=token)
                ff._move_xy("handover_carry", (0.0, 0.0), hold_grip=True, extra_ctrls={"wrist_yaw_ctrl": 0.0}, token=token)
                pm = ff.pad_midpoint_world()
                ff._ramp(
                    "handover_place",
                    {
                        "robot_x_ctrl": ff._ctrl("robot_x_ctrl") - float(pm[0]),
                        "robot_y_ctrl": ff._ctrl("robot_y_ctrl") - float(pm[1]),
                        "robot_z_ctrl": -0.272,
                    },
                    0.34,
                    settle_s=0.08,
                    hold_grip=True,
                    token=token,
                )
                ff._ramp("handover_release", {"left_finger_ctrl": 0.0, "right_finger_ctrl": 0.0}, 0.16, settle_s=0.06, token=token)
                ff._ramp("handover_raise", {"robot_z_ctrl": -0.145}, 0.40, settle_s=0.08, token=token)
                self._cube_26_location = "table"
                self._cube_26_center_xy = (0.0, 0.0)

        park_res = self.park_arm_standby(token=token)
        if not park_res.get("success"):
            return {
                "success": False,
                "failure_code": "HANDOVER_PARK_FAILED",
                "failure_reason": str(park_res.get("failure_reason") or "park failed"),
            }

        # Capture private human-workspace handover reference pose directly from cube_free body
        # ONLY for external human interaction bounds (never written to robot scene_state/tracker).
        with self.truth_boundary.scope(TruthAccessCategory.EXPERIMENT_INIT_ALLOWED, "human_handover_pose_anchor"):
            cube_id = self._id(self.mujoco.mjtObj.mjOBJ_BODY, "cube")
            pos = np.asarray(self.data.xpos[cube_id], dtype=float).copy()
            quat = np.asarray(self.data.xquat[cube_id], dtype=float).copy()
        return {
            "success": True,
            "handover_xy": [round(float(pos[0]), 4), round(float(pos[1]), 4)],
            "park_xy": [-0.42, 0.25],
            "_human_private_base_xy": (float(pos[0]), float(pos[1])),
            "_human_private_base_quat": quat.tolist(),
        }

    def human_apply_26_cubie_move(
        self,
        move: str,
        *,
        duration_s: float = 0.25,
        frame_callback: Callable[[int, int], None] | None = None,
    ) -> dict[str, Any]:
        """Human physical 26-cubie layer turn on tabletop cube without changing RGBA or leaking to robot."""
        if not self.full_26_cubie or self.cube_26_turner is None:
            raise RuntimeError("human_apply_26_cubie_move requires full_26_cubie=True")
        init_rgba = self.model.geom_rgba.copy()
        res = self.cube_26_turner.execute_human_layer_turn(
            move,
            duration_s=duration_s,
            frame_callback=frame_callback,
        )
        no_recolor = bool(np.array_equal(init_rgba, self.model.geom_rgba))
        return {
            "success": bool(res.success and no_recolor),
            "move": str(move).strip(),
            "target_angle_rad": res.target_angle_rad,
            "actual_angle_rad": res.actual_angle_rad,
            "max_slice_misalignment_deg": round(res.max_slice_misalignment_deg, 3),
            "is_lattice_aligned": bool(self.cube_26_turner.is_lattice_aligned),
            "no_recolor": no_recolor,
            "failure_code": res.failure_code if no_recolor else "PHYSICAL_INTEGRITY_VIOLATION",
            "failure_reason": res.failure_reason,
            "telemetry": dict(res.telemetry),
        }

    def human_perturb_26_cubie_pose(
        self,
        *,
        dx_m: float = 0.0,
        dy_m: float = 0.0,
        dyaw_deg: float = 0.0,
        base_xy: tuple[float, float] = (0.0, 0.0),
        base_quat: tuple[float, float, float, float] | list[float] | np.ndarray = (1.0, 0.0, 0.0, 0.0),
        frame_callback: Callable[[], None] | None = None,
    ) -> dict[str, Any]:
        """Physically translate/rotate the tabletop 26-cubie cube within safe collision-free bounds."""
        from .physical_cube_26 import _quat_mul

        if not self.full_26_cubie or self.cube_26_turner is None:
            raise RuntimeError("human_perturb_26_cubie_pose requires full_26_cubie=True")

        dx = float(np.clip(dx_m, -0.08, 0.08))
        dy = float(np.clip(dy_m, -0.08, 0.08))
        dyaw = float(np.clip(dyaw_deg, -40.0, 40.0))

        tx = float(np.clip(float(base_xy[0]) + dx, -0.24, 0.20))
        ty = float(np.clip(float(base_xy[1]) + dy, -0.15, 0.24))
        # Ensure strict clearance from turn_station base pads at (0.35, -0.19) & (0.35, -0.45)
        for pad_x, pad_y in ((0.35, -0.19), (0.35, -0.45)):
            dist = math.hypot(tx - pad_x, ty - pad_y)
            if dist < 0.17:
                ux = (tx - pad_x) / max(dist, 1e-6)
                uy = (ty - pad_y) / max(dist, 1e-6)
                tx = float(np.clip(pad_x + ux * 0.17, -0.24, 0.20))
                ty = float(np.clip(pad_y + uy * 0.17, -0.15, 0.24))

        dyaw_rad = math.radians(dyaw)
        q_rot_z = np.array([math.cos(dyaw_rad * 0.5), 0.0, 0.0, math.sin(dyaw_rad * 0.5)], dtype=float)
        q_base = np.asarray(base_quat, dtype=float)
        q_target = _quat_mul(q_rot_z, q_base)

        joint = self._joint("cube_free")
        qadr = int(self.model.jnt_qposadr[joint])
        dadr = int(self.model.jnt_dofadr[joint])

        with self.truth_boundary.scope(TruthAccessCategory.EXPERIMENT_INIT_ALLOWED, "human_pose_perturbation"):
            start_qpos = self.data.qpos[qadr : qadr + 7].copy()
            x_start, y_start, z_start = float(start_qpos[0]), float(start_qpos[1]), float(start_qpos[2])
            q_start = start_qpos[3:7].copy()
            if float(np.dot(q_start, q_target)) < 0.0:
                q_target = -q_target

            steps = 16
            for s in range(1, steps + 1):
                u = float(s) / float(steps)
                alpha = 3.0 * u * u - 2.0 * u * u * u
                xi = x_start + (tx - x_start) * alpha
                yi = y_start + (ty - y_start) * alpha
                zi = max(z_start, 0.662)
                qi = (1.0 - alpha) * q_start + alpha * q_target
                qi = qi / max(float(np.linalg.norm(qi)), 1e-12)
                self.data.qpos[qadr : qadr + 3] = [xi, yi, zi]
                self.data.qpos[qadr + 3 : qadr + 7] = qi
                self.data.qvel[dadr : dadr + 6] = 0.0
                self.mujoco.mj_forward(self.model, self.data)
                for _ in range(3):
                    self.step_physics()
                if frame_callback is not None and s in (steps // 2, steps):
                    frame_callback()

            for _ in range(30):
                self.step_physics()

        ok_lat, mis_deg = self.cube_26_turner.refresh_lattice_status(tol_deg=self.cube_26_turner.LATTICE_RECOVERY_TOL_DEG)
        return {
            "success": bool(ok_lat),
            "applied_dx_m": round(tx - float(base_xy[0]), 4),
            "applied_dy_m": round(ty - float(base_xy[1]), 4),
            "applied_dyaw_deg": round(dyaw, 2),
            "is_lattice_aligned": bool(ok_lat),
            "max_slice_misalignment_deg": round(mis_deg, 3),
        }

    def observe_tabletop_rapid_26_cubie(
        self,
        *,
        clear_prior: bool = True,
        token: CancellationToken | None = None,
    ) -> dict[str, Any]:
        """Fast (<1s, zero arm-cube contact) 5-camera tabletop rapid glance yielding up to 45/54 stickers."""
        import time
        from .canonical_facelets import (
            FACE_FRAMES,
            axis_rotation,
            canonical_local_centers,
            cube_rotations_24,
            project_points,
        )
        from .facelet_mapping import classify_color
        from .perception_v2 import DeterministicCubeLocalizer
        from .physical_u import physical_observations
        from .six_face_inspection import (
            SixFacePerception,
            StickerStateFusion,
            estimate_orientation_from_centers,
        )
        from .v2_types import FaceObservation

        if not self.full_26_cubie or self.flip_controller is None or self.orientation_tracker is None:
            raise RuntimeError("observe_tabletop_rapid_26_cubie requires full_26_cubie=True")

        aligned, res_deg = self.flip_controller.sync_station_lattice_state()
        if not aligned:
            return {
                "success": False,
                "failure_code": "SLICE_MISALIGNED_JAM",
                "failure_reason": (
                    f"Turn station top slice is misaligned ({res_deg:+.2f} deg); "
                    "recover_preempted_turn_slice is required before rapid observation"
                ),
            }

        det_oh_pre = DeterministicCubeLocalizer().locate(self.capture_rgbd("overhead"))
        in_station_rgbd = bool(
            det_oh_pre is not None
            and float(det_oh_pre.center_world_m[0]) > 0.18
            and float(det_oh_pre.center_world_m[1]) < -0.10
        )
        if self._cube_26_location == "station" or in_station_rgbd:
            return {
                "success": False,
                "failure_code": "CUBE_NOT_ON_TABLE",
                "failure_reason": "魔方当前位于机械转面工位内部，请先移交桌面 (handover_to_human) 或执行 scan_occluded_bottom_face。",
            }

        if clear_prior:
            self.visual_world_state = None
            self._index_cube_to_world = None
            self._predicted_cube_rotation = None
            self.orientation_tracker.reset()
            self._cube_26_location = "table"
            self._cube_26_center_xy = None

        t_wall0 = time.perf_counter()
        t_sim0 = float(self.data.time)
        ff = self.flip_controller
        # Raise open gripper well clear above cube without disturbing tabletop pose
        self._set_controls({"wrist_pitch_ctrl": 0.0, "wrist_yaw_ctrl": 0.0, "left_finger_ctrl": 0.0, "right_finger_ctrl": 0.0}, 0.12)
        cap = self.capture_released_views()
        if not cap.get("success"):
            return {
                "success": False,
                "failure_code": str(cap.get("failure_code") or "RAPID_LOCALIZATION_FAILED"),
                "failure_reason": "桌面 5 相机快瞄定位失败，建议按需唤醒 VLM 诊断或执行完整主动扫描。",
            }

        frames: list[RGBDFrame] = list(cap["frames"])
        cx, cy, cz = (float(v) for v in cap["localized_center_world_m"])
        fb_c = np.array([cx, cy, max(cz, 0.660)], dtype=float)
        loc = DeterministicCubeLocalizer()
        det_top = loc.locate(frames[0])
        raw_yaw = (
            float(det_top.yaw_radians)
            if det_top is not None and det_top.yaw_radians is not None
            else float(det_oh_pre.yaw_radians or 0.0 if det_oh_pre is not None else 0.0)
        )
        yaw_folded = ((raw_yaw + math.pi * 0.25) % (math.pi * 0.5)) - math.pi * 0.25

        def _classify_patch(rgb_med: np.ndarray) -> tuple[str | None, float]:
            lbl, conf = classify_color(rgb_med)
            if lbl is not None:
                return lbl, float(conf)
            vals = np.asarray(rgb_med, dtype=float) / 255.0
            mx, mn = float(np.max(vals)), float(np.min(vals))
            if mx >= 0.30 and (mx - mn) / max(mx, 1e-6) < 0.25:
                return "U", 0.65
            return None, 0.0

        perc = SixFacePerception()
        dets = [perc.detect(f, f"released:{f.camera_name}") for f in frames]
        rz = axis_rotation(np.array([0.0, 0.0, 1.0]), yaw_folded)
        rz_inv = axis_rotation(np.array([0.0, 0.0, 1.0]), -yaw_folded)
        constraints = [
            (fc, rz_inv @ np.asarray(dw, dtype=float), vw)
            for fc, dw, vw in perc.orientation_constraints(dets)
        ]
        est = estimate_orientation_from_centers(constraints, None)
        base_rot = est.matrix
        if not est.unique or base_rot is None:
            cands: list[tuple[int, float, np.ndarray]] = []
            for r24 in cube_rotations_24():
                rot_c = rz @ r24
                score = 0
                conf_sum = 0.0
                for d in dets:
                    scores = {
                        f: float(np.dot(rot_c @ np.asarray(FACE_FRAMES[f].normal, dtype=float), d.outward))
                        for f in "URFDLB"
                    }
                    pf = max(scores, key=scores.get)
                    if scores[pf] < 0.70:
                        continue
                    px = project_points(canonical_local_centers(pf), fb_c, rot_c, d.frame.calibration)[4]
                    xi, yi = int(round(float(px[0]))), int(round(float(px[1])))
                    h_img, w_img = d.frame.rgb.shape[:2]
                    if 0 <= xi < w_img and 0 <= yi < h_img:
                        patch = d.frame.rgb[max(0, yi - 1) : min(h_img, yi + 2), max(0, xi - 1) : min(w_img, xi + 2)].reshape(-1, 3)
                        lbl, cval = _classify_patch(np.median(patch, axis=0))
                        if lbl == pf:
                            score += 1
                            conf_sum += cval
                cands.append((score, conf_sum, r24))
            cands.sort(key=lambda item: (item[0], item[1]), reverse=True)
            base_rot = cands[0][2]

        rot = rz @ np.asarray(base_rot, dtype=float)
        obs: list[FaceObservation] = []
        skip_d4 = abs(yaw_folded) >= 0.48
        for idx, d in enumerate(dets):
            scores = {
                face: float(np.dot(rot @ np.asarray(FACE_FRAMES[face].normal, dtype=float), d.outward))
                for face in "URFDLB"
            }
            pred = max(scores, key=scores.get)
            if scores[pred] < 0.70:
                continue
            if not skip_d4:
                res = perc.map_detection(d, rot, fb_c, idx)
                if res.observation is not None:
                    obs.append(res.observation)
                    continue
            pts_xy = project_points(canonical_local_centers(pred), fb_c, rot, d.frame.calibration)
            rgb = d.frame.rgb
            h_img, w_img = rgb.shape[:2]
            labels: list[str | None] = []
            confs: list[float] = []
            for px_x, px_y in pts_xy:
                xi, yi = int(round(float(px_x))), int(round(float(px_y)))
                patch = rgb[max(0, yi - 1) : min(h_img, yi + 2), max(0, xi - 1) : min(w_img, xi + 2)].reshape(-1, 3)
                if len(patch) == 0:
                    labels.append(None)
                    confs.append(0.0)
                    continue
                lbl, cval = _classify_patch(np.median(patch, axis=0))
                labels.append(lbl)
                confs.append(float(cval))
            if labels[4] == pred and all(s is not None for s in labels):
                obs.append(
                    FaceObservation(
                        face=pred,
                        stickers=tuple(labels),
                        sticker_confidences=tuple(confs),
                        source_view=d.view,
                        frame_index=idx,
                        confidence=float(min(confs)),
                    )
                )

        obs = physical_observations(obs)
        fus = StickerStateFusion()
        for o in obs:
            fus.add(o)

        # Quick park away from overhead without touching cube
        ff._move_xy("rapid_park_clear", (-0.42, 0.25), token=token)

        self.orientation_tracker.update_from_visual_pose(rot, source="tabletop_rapid_glance_cv")
        snap = self.orientation_tracker.snapshot()
        self._index_cube_to_world = snap.rotation_cube_to_world.copy()
        self._predicted_cube_rotation = snap.rotation_cube_to_world.copy()
        self._cube_26_location = "table"
        self._cube_26_center_xy = (float(cx), float(cy))
        self._world_state_revision += 1
        self.visual_world_state = {
            "center_world_m": [float(fb_c[0]), float(fb_c[1]), float(fb_c[2])],
            "rotation_cube_to_world": rot.copy(),
            "pose_valid": True,
            "source": "rgbd_rapid_5face_glance",
            "revision": self._world_state_revision,
        }

        ev_map = {(e.face, e.index): e.color for e in fus.fused_evidence()}
        partial_str = "".join(ev_map.get((fc, si)) or "?" for fc in "URFDLB" for si in range(9))
        return {
            "success": bool(fus.observed_sticker_count > 0 and fus.conflict_count == 0),
            "partial_facelets": partial_str,
            "observed_count": int(fus.observed_sticker_count),
            "observed_faces": int(fus.observed_face_count),
            "unknown_count": int(fus.unknown_count),
            "conflict_count": int(fus.conflict_count),
            "occluded_face": snap.bottom_face,
            "top_face": snap.top_face,
            "bottom_face": snap.bottom_face,
            "relocalized_xy_m": [round(float(cx), 4), round(float(cy), 4)],
            "relocalized_yaw_deg": round(math.degrees(yaw_folded), 2),
            "wall_time_s": round(time.perf_counter() - t_wall0, 3),
            "sim_dt_s": round(float(self.data.time) - t_sim0, 3),
        }

    def rescan_and_relocalize_26_cubie(self, *, token: CancellationToken | None = None) -> dict[str, Any]:
        """Zero-leakage RGB-D relocalization, squaring, and full 6-face 54-sticker scan after handover."""
        from .canonical_facelets import axis_rotation
        from .perception_v2 import DeterministicCubeLocalizer

        if not self.full_26_cubie or self.flip_controller is None or self.orientation_tracker is None:
            raise RuntimeError("rescan_and_relocalize_26_cubie requires full_26_cubie=True")

        # Strictly invalidate all cached robot pose & orientation priors (Zero Action/Pose Leakage)
        self.visual_world_state = None
        self._index_cube_to_world = None
        self._predicted_cube_rotation = None
        self.orientation_tracker.reset()
        self._cube_26_location = "table"
        self._cube_26_center_xy = None

        if self._bilateral_finger_contact():
            self.handover_26_cubie_to_table(token=token)

        ff = self.flip_controller
        park_res = self.park_arm_standby(token=token)
        if not park_res.get("success"):
            return {
                "success": False,
                "failure_code": "PARK_FAILED",
                "failure_reason": str(park_res.get("failure_reason") or "standby park failed"),
            }

        det = DeterministicCubeLocalizer().locate(self.capture_rgbd("overhead"))
        if det is None:
            return {
                "success": False,
                "failure_code": "VISUAL_LOCALIZATION_FAILED",
                "failure_reason": "Overhead RGB-D could not localize cube after handover",
            }

        in_station_rgbd = float(det.center_world_m[0]) > 0.18 and float(det.center_world_m[1]) < -0.10
        if in_station_rgbd:
            self._cube_26_location = "station"
            refined_xy = (float(det.center_world_m[0]), float(det.center_world_m[1]))
            yaw_folded = 0.0
        else:
            refined_xy = self.relocalize_cube_rgbd(
                approx_xy=(float(det.center_world_m[0]), float(det.center_world_m[1])),
                clear_station=False,
                token=token,
            )
            fine_yaw = (
                float(self._last_reloc_yaw_rad)
                if getattr(self, "_last_reloc_yaw_rad", None) is not None
                else float(det.yaw_radians or 0.0)
            )
            yaw_folded = ((fine_yaw + math.pi * 0.25) % (math.pi * 0.5)) - math.pi * 0.25

        # Square off-center or rotated tabletop cube cleanly to (0.0, 0.0, yaw~0) before 6-face multi-view scan
        if (not in_station_rgbd) and (
            math.hypot(refined_xy[0], refined_xy[1]) > 0.020 or abs(yaw_folded) > math.radians(5.0)
        ):
            grasp_yaw = ff.select_collision_free_table_yaw(refined_xy, yaw_folded)
            ok_sq, st_sq, rsn_sq = ff._pick_up_cube(
                refined_xy,
                grasp_yaw,
                z_grasp=-0.282,
                is_station=False,
                token=token,
            )
            if not ok_sq:
                return {
                    "success": False,
                    "failure_code": "RESCAN_PICKUP_FAILED",
                    "failure_reason": rsn_sq or st_sq.value,
                    "relocalized_xy_m": [round(refined_xy[0], 4), round(refined_xy[1], 4)],
                    "relocalized_yaw_deg": round(math.degrees(yaw_folded), 2),
                }
            ff._ramp("rescan_sq_lift", {"robot_z_ctrl": -0.145}, 0.28, settle_s=0.04, hold_grip=True, token=token)
            ff._ramp("rescan_sq_yaw", {"wrist_yaw_ctrl": 0.0}, 0.28, settle_s=0.05, hold_grip=True, token=token)
            ff._move_xy(
                "rescan_sq_move",
                (0.0, 0.0),
                hold_grip=True,
                extra_ctrls={"wrist_yaw_ctrl": 0.0},
                token=token,
            )
            pm = ff.pad_midpoint_world()
            ff._ramp(
                "rescan_sq_place",
                {
                    "robot_x_ctrl": ff._ctrl("robot_x_ctrl") - float(pm[0]),
                    "robot_y_ctrl": ff._ctrl("robot_y_ctrl") - float(pm[1]),
                    "robot_z_ctrl": -0.272,
                },
                0.34,
                settle_s=0.06,
                hold_grip=True,
                token=token,
            )
            ff._ramp("rescan_sq_open", {"left_finger_ctrl": 0.0, "right_finger_ctrl": 0.0}, 0.16, settle_s=0.06, token=token)
            ff._ramp("rescan_sq_clear_z", {"robot_z_ctrl": -0.145, "base_clear_ctrl": 0.0}, 0.42, settle_s=0.08, token=token)
            ff._move_xy("rescan_sq_park", (-0.42, 0.25), token=token)

        # Reset orientation hypothesis once more so inspect_26_cubie_via_independent_cameras resolves 100% from Pass 1 centers
        self._index_cube_to_world = None
        self._predicted_cube_rotation = None
        self.orientation_tracker.reset()

        cam_res = self.inspect_26_cubie_via_independent_cameras(token=token)
        if not cam_res.get("success"):
            return {
                **cam_res,
                "relocalized_xy_m": [round(refined_xy[0], 4), round(refined_xy[1], 4)],
                "relocalized_yaw_deg": round(math.degrees(yaw_folded), 2),
            }

        snap = self.orientation_tracker.snapshot()
        self._world_state_revision += 1
        c_xy = self._cube_26_center_xy or (0.0, 0.0)
        self.visual_world_state = {
            "center_world_m": [float(c_xy[0]), float(c_xy[1]), 0.66],
            "rotation_cube_to_world": snap.rotation_cube_to_world.copy(),
            "pose_valid": True,
            "source": "rgbd_independent_6face_rescan",
            "revision": self._world_state_revision,
        }
        return {
            **cam_res,
            "relocalized_xy_m": [round(refined_xy[0], 4), round(refined_xy[1], 4)],
            "relocalized_yaw_deg": round(math.degrees(yaw_folded), 2),
            "top_face": snap.top_face,
            "bottom_face": snap.bottom_face,
        }
