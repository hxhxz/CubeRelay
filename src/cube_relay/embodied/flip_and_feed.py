from __future__ import annotations

import math
import time
from dataclasses import dataclass, field
from typing import Any, Callable

import numpy as np

from cube_relay.execution.action_chunk import (
    ActionChunk,
    ActionChunkExecutor,
    CancellationToken,
    ChunkStatus,
)
from .canonical_facelets import FACE_FRAMES, axis_rotation, cube_rotations_24
from .physical_cube_26 import STATION_POS
from .six_face_inspection import estimate_orientation_from_centers


def _wrap_pi(rad: float) -> float:
    return float((rad + math.pi) % (2.0 * math.pi) - math.pi)


def _canonical_table_yaw(raw_angle_rad: float) -> float:
    """Fold an arbitrary yaw into [-pi/4, +pi/4] exploiting 4-fold cube symmetry."""
    return float((raw_angle_rad + math.pi * 0.25) % (math.pi * 0.5) - math.pi * 0.25)


@dataclass
class OrientationSnapshot:
    rotation_cube_to_world: np.ndarray
    continuous_rotation: np.ndarray
    top_face: str
    bottom_face: str
    face_normals_world: dict[str, tuple[float, float, float]]
    source: str
    flips_executed: int = 0
    regrasps_executed: int = 0
    flip_time_s: float = 0.0


class CubeOrientationTracker:
    """Tracks the 3D orientation of all 6 logical cube faces using CV + verified flips only.

    Never reads MuJoCo cube `qpos`, `xpos`, or `xmat`.
    """

    def __init__(self, initial_rotation: np.ndarray | None = None) -> None:
        self._rots_24 = [np.asarray(r, dtype=float) for r in cube_rotations_24()]
        self.flips_executed = 0
        self.regrasps_executed = 0
        self.flip_time_s = 0.0
        self.source = "initial"
        r0 = np.eye(3, dtype=float) if initial_rotation is None else np.asarray(initial_rotation, dtype=float)
        self._continuous_rot = self._orthonormalize(r0)
        self._discrete_rot = self._nearest_rot_24(self._continuous_rot)

    @staticmethod
    def _orthonormalize(r: np.ndarray) -> np.ndarray:
        u, _, vt = np.linalg.svd(np.asarray(r, dtype=float))
        out = u @ vt
        if np.linalg.det(out) < 0.0:
            u[:, -1] *= -1.0
            out = u @ vt
        return out

    def _nearest_rot_24(self, r: np.ndarray) -> np.ndarray:
        return min(self._rots_24, key=lambda cand: float(np.linalg.norm(r - cand, ord="fro")))

    def reset(self, initial_rotation: np.ndarray | None = None) -> None:
        r0 = np.eye(3, dtype=float) if initial_rotation is None else np.asarray(initial_rotation, dtype=float)
        self._continuous_rot = self._orthonormalize(r0)
        self._discrete_rot = self._nearest_rot_24(self._continuous_rot)
        self.flips_executed = 0
        self.regrasps_executed = 0
        self.flip_time_s = 0.0
        self.source = "initial"

    def update_from_visual_pose(self, rotation_cube_to_world: np.ndarray, *, source: str = "visual_pose") -> OrientationSnapshot:
        r = self._orthonormalize(rotation_cube_to_world)
        self._continuous_rot = r
        self._discrete_rot = self._nearest_rot_24(r)
        self.source = source
        return self.snapshot()

    def update_from_centers(
        self,
        constraints: list[tuple[str, np.ndarray, str]],
        *,
        prior: np.ndarray | None = None,
        source: str = "center_cv",
    ) -> OrientationSnapshot:
        est = estimate_orientation_from_centers(
            constraints,
            prior=self._continuous_rot if prior is None else prior,
        )
        r = self._orthonormalize(np.asarray(est.matrix, dtype=float))
        self._continuous_rot = r
        self._discrete_rot = self._nearest_rot_24(r)
        self.source = source
        return self.snapshot()

    def record_verified_flip(
        self,
        delta_world_rotation: np.ndarray,
        *,
        is_flip: bool = True,
        is_regrasp: bool = False,
        duration_s: float = 0.0,
        source: str = "verified_flip",
    ) -> OrientationSnapshot:
        r_new = self._orthonormalize(np.asarray(delta_world_rotation, dtype=float) @ self._continuous_rot)
        self._continuous_rot = r_new
        self._discrete_rot = self._nearest_rot_24(r_new)
        if is_flip:
            self.flips_executed += 1
        if is_regrasp:
            self.regrasps_executed += 1
        self.flip_time_s += float(duration_s)
        self.source = source
        return self.snapshot()

    def face_world_normal(self, face: str) -> np.ndarray:
        n_local = np.asarray(FACE_FRAMES[face].normal, dtype=float)
        return self._continuous_rot @ n_local

    def top_face(self) -> str:
        z_world = np.array([0.0, 0.0, 1.0], dtype=float)
        return max(
            "URFDLB",
            key=lambda f: float(np.dot(self.face_world_normal(f), z_world)),
        )

    def bottom_face(self) -> str:
        z_neg = np.array([0.0, 0.0, -1.0], dtype=float)
        return max(
            "URFDLB",
            key=lambda f: float(np.dot(self.face_world_normal(f), z_neg)),
        )

    def estimated_flips(self, target_face: str) -> int:
        f = target_face.strip()[0]
        if f not in "URFDLB":
            raise ValueError(f"Unknown face {target_face!r}")
        if f == self.top_face():
            return 0
        if f == self.bottom_face():
            return 2
        return 1

    def canonical_table_yaw(self) -> float:
        x_world = self._continuous_rot @ np.array([1.0, 0.0, 0.0], dtype=float)
        if abs(float(x_world[2])) >= 0.5:
            # Local X axis (L/R) points vertically when L or R faces up; use a horizontal axis to avoid atan2 gimbal lock.
            x_world = min(
                (self._continuous_rot[:, k] for k in range(3)),
                key=lambda vec: abs(float(vec[2])),
            )
        raw = math.atan2(float(x_world[1]), float(x_world[0]))
        return _canonical_table_yaw(raw)

    def snapshot(self) -> OrientationSnapshot:
        normals = {
            f: tuple(round(float(x), 4) for x in self.face_world_normal(f))
            for f in "URFDLB"
        }
        return OrientationSnapshot(
            rotation_cube_to_world=self._discrete_rot.copy(),
            continuous_rotation=self._continuous_rot.copy(),
            top_face=self.top_face(),
            bottom_face=self.bottom_face(),
            face_normals_world=normals,
            source=self.source,
            flips_executed=self.flips_executed,
            regrasps_executed=self.regrasps_executed,
            flip_time_s=round(self.flip_time_s, 4),
        )


@dataclass
class FlipAndFeedResult:
    success: bool
    target_face: str
    flips_required: int
    flips_executed: int
    regrasps_executed: int
    elapsed_sim_s: float
    preempted: bool = False
    chunk_status: str = ChunkStatus.COMPLETED.value
    failure_reason: str | None = None
    orientation: OrientationSnapshot | None = None
    telemetry: dict[str, Any] = field(default_factory=dict)


class FlipAndFeedController:
    """Single-arm Flip-and-Feed controller built on interruptible ActionChunkExecutor.

    Uses ONLY robot proprioception (joint controls/positions, pad FK, tactile contact)
    and caller-supplied visual localization callbacks. Never reads cube qpos/xpos/xmat.
    """

    def __init__(
        self,
        model: Any,
        data: Any,
        mujoco_mod: Any,
        *,
        executor: ActionChunkExecutor | None = None,
        turn_executor: Any | None = None,
        record_ctrl_fn: Callable[[dict[str, float]], None] | None = None,
        post_step_fn: Callable[[], None] | None = None,
    ) -> None:
        self.model = model
        self.data = data
        self.mujoco = mujoco_mod
        self.turn_executor = turn_executor
        self.record_ctrl_fn = record_ctrl_fn
        self.post_step_fn = post_step_fn
        self.dt = float(self.model.opt.timestep)
        self.is_lattice_aligned: bool = True
        self.residual_slice_angle_deg: float = 0.0

        self._act_ids = {
            name: self._act(name)
            for name in (
                "robot_x_ctrl",
                "robot_y_ctrl",
                "robot_z_ctrl",
                "wrist_yaw_ctrl",
                "wrist_pitch_ctrl",
                "left_finger_ctrl",
                "right_finger_ctrl",
                "base_clear_ctrl",
                "base_pos_ctrl",
                "base_neg_ctrl",
                "turn_pos_ctrl",
                "turn_neg_ctrl",
                "turn_z_ctrl",
                "turn_rotor_ctrl",
            )
        }
        self._jnt_qadr = {
            name: int(self.model.jnt_qposadr[self._joint(name)])
            for name in (
                "robot_x_joint",
                "robot_y_joint",
                "robot_z_joint",
                "wrist_yaw_joint",
                "wrist_pitch_joint",
                "left_finger_joint",
                "right_finger_joint",
            )
        }
        self._left_pad_body = self._body("left_finger")
        self._right_pad_body = self._body("right_finger")
        self._left_pad_geom = self._geom("left_finger_pad")
        self._right_pad_geom = self._geom("right_finger_pad")
        self._wrist_body = self._body("wrist")
        self._table_geom = self._geom("table")
        self._cube_geoms = self._resolve_cube_geoms()

        self.executor = executor or ActionChunkExecutor(
            self.model,
            self.data,
            record_command_fn=self.record_ctrl_fn,
            post_step_fn=self._wrap_post_step(),
            held_object_ok_fn=self.has_bilateral_finger_contact,
        )

    def _wrap_post_step(self) -> Callable[[int], str | None]:
        def _cb(_step_idx: int) -> str | None:
            if self.post_step_fn is not None:
                self.post_step_fn()
            return None

        return _cb

    def _act(self, name: str) -> int:
        aid = int(self.mujoco.mj_name2id(self.model, self.mujoco.mjtObj.mjOBJ_ACTUATOR, name))
        if aid < 0:
            raise KeyError(f"Missing actuator {name!r}")
        return aid

    def _joint(self, name: str) -> int:
        jid = int(self.mujoco.mj_name2id(self.model, self.mujoco.mjtObj.mjOBJ_JOINT, name))
        if jid < 0:
            raise KeyError(f"Missing joint {name!r}")
        return jid

    def _body(self, name: str) -> int:
        bid = int(self.mujoco.mj_name2id(self.model, self.mujoco.mjtObj.mjOBJ_BODY, name))
        if bid < 0:
            raise KeyError(f"Missing body {name!r}")
        return bid

    def _geom(self, name: str) -> int:
        gid = int(self.mujoco.mj_name2id(self.model, self.mujoco.mjtObj.mjOBJ_GEOM, name))
        if gid < 0:
            raise KeyError(f"Missing geom {name!r}")
        return gid

    def _resolve_cube_geoms(self) -> set[int]:
        ids: set[int] = set()
        for k in range(26):
            gid = int(self.mujoco.mj_name2id(self.model, self.mujoco.mjtObj.mjOBJ_GEOM, f"cubie_geom_{k:02d}"))
            if gid >= 0:
                ids.add(gid)
        if not ids:
            gid = int(self.mujoco.mj_name2id(self.model, self.mujoco.mjtObj.mjOBJ_GEOM, "cube_core"))
            if gid >= 0:
                ids.add(gid)
        return ids

    def pad_midpoint_world(self) -> np.ndarray:
        """Gripper pad midpoint strictly from robot forward kinematics."""
        lp = np.asarray(self.data.geom_xpos[self._left_pad_geom], dtype=float)
        rp = np.asarray(self.data.geom_xpos[self._right_pad_geom], dtype=float)
        return 0.5 * (lp + rp)

    def has_bilateral_finger_contact(self) -> bool:
        left_hit = False
        right_hit = False
        for c in self.data.contact[: self.data.ncon]:
            g1, g2 = int(c.geom1), int(c.geom2)
            if g1 not in self._cube_geoms and g2 not in self._cube_geoms:
                continue
            other = g2 if g1 in self._cube_geoms else g1
            if other == self._left_pad_geom:
                left_hit = True
            elif other == self._right_pad_geom:
                right_hit = True
        return left_hit and right_hit

    def _table_touching_cube(self) -> bool:
        for c in self.data.contact[: self.data.ncon]:
            g1, g2 = int(c.geom1), int(c.geom2)
            if (g1 == self._table_geom and g2 in self._cube_geoms) or (
                g2 == self._table_geom and g1 in self._cube_geoms
            ):
                return True
        return False

    def _ctrl(self, name: str) -> float:
        return float(self.data.ctrl[self._act_ids[name]])

    def _qpos(self, jnt: str) -> float:
        return float(self.data.qpos[self._jnt_qadr[jnt]])

    def _ramp(
        self,
        chunk_id: str,
        goals: dict[str, float],
        duration_s: float,
        *,
        settle_s: float = 0.0,
        hold_grip: bool = False,
        token: CancellationToken | None = None,
    ) -> tuple[bool, ChunkStatus, str | None]:
        start = {k: self._ctrl(k) for k in goals}
        steps = max(5, int(round(duration_s / self.dt)))
        settle_steps = max(0, int(round(settle_s / self.dt)))
        chunk = ActionChunk.linear_ramp(
            chunk_id=chunk_id,
            start=start,
            goal=goals,
            steps=steps,
            settle_steps=settle_steps,
            dt=self.dt,
            hold_grip_on_interrupt=hold_grip,
            held_grip_ctrl=self._ctrl("left_finger_ctrl") if hold_grip else 0.070,
        )
        res = self.executor.execute(chunk, token=token)
        if res.status in (ChunkStatus.PREEMPTED_SAFE_HOLD, ChunkStatus.SAFETY_ABORTED):
            return False, res.status, res.cancel_reason
        if res.status == ChunkStatus.FAILED:
            return False, res.status, (res.safety_violation or res.cancel_reason)
        return True, res.status, None

    def _move_xy(
        self,
        chunk_id: str,
        goal_xy: tuple[float, float],
        *,
        v_max: float = 0.28,
        a_max: float = 1.2,
        hold_grip: bool = False,
        extra_ctrls: dict[str, float] | None = None,
        token: CancellationToken | None = None,
    ) -> tuple[bool, ChunkStatus, str | None]:
        start_xy = (self._ctrl("robot_x_ctrl"), self._ctrl("robot_y_ctrl"))
        chunk = ActionChunk.trapezoidal_xy(
            chunk_id=chunk_id,
            start_xy=start_xy,
            goal_xy=goal_xy,
            dt=self.dt,
            v_max=v_max,
            a_max=a_max,
            min_duration_s=0.18,
            hold_grip_on_interrupt=hold_grip,
            held_grip_ctrl=self._ctrl("left_finger_ctrl") if hold_grip else 0.070,
            extra_ctrls=extra_ctrls,
        )
        res = self.executor.execute(chunk, token=token)
        if res.status in (ChunkStatus.PREEMPTED_SAFE_HOLD, ChunkStatus.SAFETY_ABORTED):
            return False, res.status, res.cancel_reason
        if res.status == ChunkStatus.FAILED:
            return False, res.status, (res.safety_violation or res.cancel_reason)

        # Converge XY position & velocity cleanly via short hold chunks before Z descent
        x_goal, y_goal = float(goal_xy[0]), float(goal_xy[1])
        x_qvel_adr = int(self.model.jnt_dofadr[self._joint("robot_x_joint")])
        y_qvel_adr = int(self.model.jnt_dofadr[self._joint("robot_y_joint")])
        hold_target: dict[str, float] = {"robot_x_ctrl": x_goal, "robot_y_ctrl": y_goal}
        if extra_ctrls:
            for ck, cv in extra_ctrls.items():
                hold_target[ck] = float(cv)
        held_g = max(self._ctrl("left_finger_ctrl"), self._ctrl("right_finger_ctrl"), 0.068) if hold_grip else 0.0
        for sub_idx in range(75):
            pm = self.pad_midpoint_world()
            pos_err = math.hypot(float(pm[0]) - x_goal, float(pm[1]) - y_goal)
            jnt_err = math.hypot(self._qpos("robot_x_joint") - x_goal, self._qpos("robot_y_joint") - y_goal)
            vel_err = math.hypot(float(self.data.qvel[x_qvel_adr]), float(self.data.qvel[y_qvel_adr]))
            check_err = pos_err if abs(self._qpos("wrist_pitch_joint")) < 0.2 else jnt_err
            if check_err < 0.004 and vel_err < 0.015:
                break
            hold_chunk = ActionChunk(
                chunk_id=f"{chunk_id}_settle_{sub_idx}",
                targets=[dict(hold_target) for _ in range(10)],
                dt=self.dt,
                hold_grip_on_interrupt=hold_grip,
                held_grip_ctrl=held_g if hold_grip else 0.070,
            )
            h_res = self.executor.execute(hold_chunk, token=token)
            if h_res.status in (ChunkStatus.PREEMPTED_SAFE_HOLD, ChunkStatus.SAFETY_ABORTED):
                return False, h_res.status, h_res.cancel_reason
            if h_res.status == ChunkStatus.FAILED:
                return False, h_res.status, (h_res.safety_violation or h_res.cancel_reason)
        return True, res.status, None

    def _park_wrist_up(self, *, horizontal_retract: bool = False, token: CancellationToken | None = None) -> tuple[bool, ChunkStatus, str | None]:
        if horizontal_retract:
            # Horizontal fingers (pitch=-pi/2) must pull straight back in +Y first to clear turn_pads
            ok, st, rsn = self._ramp(
                "retract_y",
                {"robot_y_ctrl": 0.05},
                0.65,
                settle_s=0.15,
                token=token,
            )
            if not ok:
                return ok, st, rsn
        ok, st, rsn = self._ramp(
            "park_wrist_up",
            {
                "robot_z_ctrl": -0.145,
                "wrist_pitch_ctrl": 0.0,
                "wrist_yaw_ctrl": 0.0,
                "left_finger_ctrl": 0.0,
                "right_finger_ctrl": 0.0,
            },
            0.35,
            settle_s=0.05,
            token=token,
        )
        if not ok:
            return ok, st, rsn
        return self._move_xy(
            "park_clear_xy",
            (0.0, 0.15),
            token=token,
        )

    def sync_station_lattice_state(self) -> tuple[bool, float]:
        """Synchronize station lattice alignment guard state from turn_executor."""
        if self.turn_executor is not None:
            self.is_lattice_aligned = bool(getattr(self.turn_executor, "is_lattice_aligned", True))
            self.residual_slice_angle_deg = float(getattr(self.turn_executor, "residual_slice_angle_deg", 0.0))
        return self.is_lattice_aligned, self.residual_slice_angle_deg

    def select_collision_free_table_yaw(
        self,
        center_xy: tuple[float, float],
        base_yaw: float,
    ) -> float:
        """Pick among 4-fold symmetric tabletop grasp yaws to maximize station/pad clearance."""
        cx, cy = float(center_xy[0]), float(center_xy[1])
        cur_yaw = self._qpos("wrist_yaw_joint")
        pad_centers = (
            (float(STATION_POS[0]), float(STATION_POS[1]) + 0.13),
            (float(STATION_POS[0]), float(STATION_POS[1]) - 0.13),
        )
        best_yaw = _wrap_pi(base_yaw)
        best_score = -1e9
        for k in range(4):
            cand = _wrap_pi(base_yaw + k * math.pi * 0.5)
            # Pad midpoint offset axis is (-sin(cand), cos(cand)) * 0.14
            px_off = -math.sin(cand) * 0.14
            py_off = math.cos(cand) * 0.14
            pads = ((cx + px_off, cy + py_off), (cx - px_off, cy - py_off))
            min_edge_clear = min(0.75 - abs(px) for px, _ in pads)
            min_edge_clear = min(min_edge_clear, *(0.60 - abs(py) for _, py in pads))
            min_station_dist = min(
                math.hypot(px - sx, py - sy)
                for px, py in pads
                for sx, sy in pad_centers
            )
            yaw_cost = abs(_wrap_pi(cand - cur_yaw))
            score = min(min_station_dist, 0.25) * 4.0 + min(min_edge_clear, 0.20) * 2.0 - 0.05 * yaw_cost
            if score > best_score:
                best_score = score
                best_yaw = cand
        return best_yaw

    def _pick_up_cube(
        self,
        center_xy: tuple[float, float],
        grasp_yaw: float,
        *,
        z_grasp: float = -0.282,
        is_station: bool = False,
        grip_ctrl: float = 0.082,
        token: CancellationToken | None = None,
    ) -> tuple[bool, ChunkStatus, str | None]:
        aligned, res_deg = self.sync_station_lattice_state()
        if not aligned:
            return (
                False,
                ChunkStatus.FAILED,
                f"SLICE_MISALIGNED_JAM: unrecovered half-turned slice ({res_deg:+.2f} deg); "
                "call recover_preempted_turn_slice before lifting or flipping",
            )
        near_station = float(center_xy[0]) > 0.10 and float(center_xy[1]) < -0.02
        # Clear base pads whenever picking from or near turn station so fingers cannot clip base_pads
        prep: dict[str, float] = {
            "robot_z_ctrl": -0.145,
            "wrist_pitch_ctrl": 0.0,
            "left_finger_ctrl": 0.0,
            "right_finger_ctrl": 0.0,
            "turn_z_ctrl": 0.0,
            "turn_pos_ctrl": 0.0,
            "turn_neg_ctrl": 0.0,
        }
        if is_station or near_station:
            prep["base_pos_ctrl"] = 0.0
            prep["base_neg_ctrl"] = 0.0
            prep["base_clear_ctrl"] = 0.25
        ok, st, rsn = self._ramp("pick_prep_raise", prep, 0.30, settle_s=0.04, token=token)
        if not ok:
            return ok, st, rsn

        ok, st, rsn = self._move_xy(
            "pick_move_xy",
            (float(center_xy[0]), float(center_xy[1])),
            extra_ctrls={"wrist_yaw_ctrl": float(_wrap_pi(grasp_yaw))},
            token=token,
        )
        if not ok:
            return ok, st, rsn

        # Wait briefly for yaw stabilization before descent
        ok, st, rsn = self._ramp(
            "pick_yaw_settle",
            {"wrist_yaw_ctrl": float(_wrap_pi(grasp_yaw))},
            0.14,
            settle_s=0.04,
            token=token,
        )
        if not ok:
            return ok, st, rsn

        ok, st, rsn = self._ramp("pick_descend", {"robot_z_ctrl": float(z_grasp)}, 0.50, settle_s=0.18, token=token)
        if not ok:
            return ok, st, rsn

        ok, st, rsn = self._ramp(
            "pick_close_fingers",
            {"left_finger_ctrl": float(grip_ctrl), "right_finger_ctrl": float(grip_ctrl)},
            0.28,
            settle_s=0.16,
            token=token,
        )
        if not ok:
            return ok, st, rsn

        if not self.has_bilateral_finger_contact():
            return False, ChunkStatus.FAILED, "Bilateral finger contact not established during pickup"
        return True, ChunkStatus.COMPLETED, None

    def _deliver_flipped_held_cube_to_station(
        self,
        *,
        cube_pitch_y_offset: float = 0.014,
        token: CancellationToken | None = None,
    ) -> tuple[bool, ChunkStatus, str | None]:
        """Deliver cube held with wrist_pitch=-pi/2, wrist_yaw=0 into open turn_station and seat onto table."""
        ok, st, rsn = self._ramp("flipA_lift", {"robot_z_ctrl": -0.125}, 0.34, settle_s=0.08, hold_grip=True, token=token)
        if not ok:
            return ok, st, rsn

        if abs(self._ctrl("wrist_yaw_ctrl")) > 0.03:
            ok, st, rsn = self._ramp(
                "flipA_yaw_to_zero",
                {
                    "wrist_yaw_ctrl": 0.0,
                    "turn_z_ctrl": 0.0,
                    "turn_pos_ctrl": 0.0,
                    "turn_neg_ctrl": 0.0,
                    "base_pos_ctrl": 0.0,
                    "base_neg_ctrl": 0.0,
                },
                0.52,
                settle_s=0.08,
                hold_grip=True,
                token=token,
            )
            if not ok:
                return ok, st, rsn

        ok, st, rsn = self._ramp(
            "flipA_pitch_neg90",
            {
                "wrist_pitch_ctrl": -math.pi * 0.5,
                "wrist_yaw_ctrl": 0.0,
                "turn_z_ctrl": 0.0,
                "turn_pos_ctrl": 0.0,
                "turn_neg_ctrl": 0.0,
                "base_pos_ctrl": 0.0,
                "base_neg_ctrl": 0.0,
                "base_clear_ctrl": 0.0,
            },
            0.42,
            settle_s=0.08,
            hold_grip=True,
            token=token,
        )
        if not ok:
            return ok, st, rsn

        # Approach just in +Y of station, then align cube center strictly to [0.35, -0.32, 0.805]
        # Note: z_grasp=-0.282 places pad midpoint ~14 mm above cube center; after pitch=-pi/2,
        # cube center sits 14 mm in -Y of pad midpoint, so target pm_y = STATION_POS[1] + offset.
        ok, st, rsn = self._move_xy(
            "flipA_approach_station",
            (float(STATION_POS[0]), float(STATION_POS[1]) + 0.10),
            hold_grip=True,
            extra_ctrls={"robot_z_ctrl": -0.08},
            token=token,
        )
        if not ok:
            return ok, st, rsn

        # Iterative robot-FK trim to align held cube center precisely with [0.35, -0.32, 0.805]
        target_pm_y = float(STATION_POS[1]) + float(cube_pitch_y_offset)
        for trim_i in range(2):
            pm = self.pad_midpoint_world()
            dx = float(STATION_POS[0]) - float(pm[0])
            dy = target_pm_y - float(pm[1])
            dz = 0.805 - float(pm[2])
            ok, st, rsn = self._ramp(
                f"flipA_fk_trim_{trim_i}",
                {
                    "robot_x_ctrl": self._ctrl("robot_x_ctrl") + dx,
                    "robot_y_ctrl": self._ctrl("robot_y_ctrl") + dy,
                    "robot_z_ctrl": float(np.clip(self._ctrl("robot_z_ctrl") + dz, -0.58, 0.0)),
                },
                0.24,
                settle_s=0.06,
                hold_grip=True,
                token=token,
            )
            if not ok:
                return ok, st, rsn

        pm = self.pad_midpoint_world()
        turn_z_align = float(np.clip(1.205 - (float(pm[2]) + 0.036), 0.0, 0.49))
        ok, st, rsn = self._ramp("flipA_lower_top_fixture", {"turn_z_ctrl": turn_z_align}, 0.30, settle_s=0.04, hold_grip=True, token=token)
        if not ok:
            return ok, st, rsn

        ok, st, rsn = self._ramp(
            "flipA_engage_top_pads",
            {"turn_pos_ctrl": 0.051, "turn_neg_ctrl": 0.051},
            0.22,
            settle_s=0.06,
            hold_grip=True,
            token=token,
        )
        if not ok:
            return ok, st, rsn

        # Open fingers safely to 0.052 clearing pads while turn_pads hold cube
        ok, st, rsn = self._ramp(
            "flipA_open_fingers",
            {"left_finger_ctrl": 0.052, "right_finger_ctrl": 0.052},
            0.16,
            settle_s=0.04,
            token=token,
        )
        if not ok:
            return ok, st, rsn

        ok, st, rsn = self._park_wrist_up(horizontal_retract=True, token=token)
        if not ok:
            return ok, st, rsn

        # Keep base pads wide open (±95 mm) while lowering onto station table so edges never catch a pad top,
        # then release top clamp and square smoothly with base pads.
        ok, st, rsn = self._ramp(
            "flipA_prefunnel_lower",
            {"base_pos_ctrl": 0.025, "base_neg_ctrl": 0.025},
            0.18,
            token=token,
        )
        if not ok:
            return ok, st, rsn

        ok, st, rsn = self._ramp("flipA_set_cube_on_station", {"turn_z_ctrl": 0.50}, 0.42, settle_s=0.18, token=token)
        if not ok:
            return ok, st, rsn

        ok, st, rsn = self._ramp(
            "flipA_release_top_after_seat",
            {"turn_pos_ctrl": 0.0, "turn_neg_ctrl": 0.0},
            0.16,
            settle_s=0.08,
            token=token,
        )
        if not ok:
            return ok, st, rsn

        ok, st, rsn = self._ramp(
            "flipA_square_base",
            {"base_pos_ctrl": 0.064, "base_neg_ctrl": 0.064},
            0.16,
            settle_s=0.08,
            token=token,
        )
        if not ok:
            return ok, st, rsn

        ok, st, rsn = self._ramp(
            "flipA_open_base_ready",
            {"base_pos_ctrl": 0.0, "base_neg_ctrl": 0.0},
            0.14,
            settle_s=0.06,
            token=token,
        )
        if not ok:
            return ok, st, rsn

        return True, ChunkStatus.COMPLETED, None

    def _deliver_upright_held_cube_to_station(
        self,
        *,
        grasp_yaw: float,
        token: CancellationToken | None = None,
    ) -> tuple[bool, ChunkStatus, str | None]:
        """Transport an already-correctly-oriented cube to turn_station at yaw=0."""
        ok, st, rsn = self._ramp("zero_lift", {"robot_z_ctrl": -0.145}, 0.28, hold_grip=True, token=token)
        if not ok:
            return ok, st, rsn

        ok, st, rsn = self._ramp(
            "zero_clear_station",
            {
                "wrist_yaw_ctrl": 0.0,
                "base_pos_ctrl": 0.0,
                "base_neg_ctrl": 0.0,
                "base_clear_ctrl": 0.25,
                "turn_z_ctrl": 0.0,
                "turn_pos_ctrl": 0.0,
                "turn_neg_ctrl": 0.0,
            },
            0.25,
            hold_grip=True,
            token=token,
        )
        if not ok:
            return ok, st, rsn

        ok, st, rsn = self._move_xy(
            "zero_move_to_station",
            (float(STATION_POS[0]), float(STATION_POS[1])),
            hold_grip=True,
            token=token,
        )
        if not ok:
            return ok, st, rsn

        # Pad midpoint FK trim in XY and gentle lower onto table surface
        pm = self.pad_midpoint_world()
        ok, st, rsn = self._ramp(
            "zero_xy_trim_and_lower",
            {
                "robot_x_ctrl": self._ctrl("robot_x_ctrl") + (float(STATION_POS[0]) - float(pm[0])),
                "robot_y_ctrl": self._ctrl("robot_y_ctrl") + (float(STATION_POS[1]) - float(pm[1])),
                "robot_z_ctrl": -0.272,
            },
            0.34,
            settle_s=0.06,
            hold_grip=True,
            token=token,
        )
        if not ok:
            return ok, st, rsn

        ok, st, rsn = self._ramp(
            "zero_release_fingers",
            {"left_finger_ctrl": 0.0, "right_finger_ctrl": 0.0},
            0.16,
            settle_s=0.06,
            token=token,
        )
        if not ok:
            return ok, st, rsn

        ok, st, rsn = self._ramp("zero_lift_clear", {"robot_z_ctrl": -0.145}, 0.55, settle_s=0.18, token=token)
        if not ok:
            return ok, st, rsn
        # Wait until gripper finger bottom safely clears cube top (0.720 + 0.060 + margin => pm_z >= 0.81)
        for idx in range(25):
            if float(self.pad_midpoint_world()[2]) >= 0.810:
                break
            h_res = self.executor.execute(
                ActionChunk(chunk_id=f"zero_z_wait_{idx}", targets=[{"robot_z_ctrl": -0.145}] * 10, dt=self.dt),
                token=token,
            )
            if h_res.status in (ChunkStatus.PREEMPTED_SAFE_HOLD, ChunkStatus.SAFETY_ABORTED):
                return False, h_res.status, h_res.cancel_reason

        ok, st, rsn = self._park_wrist_up(horizontal_retract=False, token=token)
        if not ok:
            return ok, st, rsn

        return self._ramp("zero_restore_base_carriage", {"base_clear_ctrl": 0.0}, 0.22, settle_s=0.06, token=token)

    def _lay_cube_90deg_on_table(
        self,
        *,
        from_xy: tuple[float, float],
        grasp_yaw: float,
        is_station: bool,
        place_xy: tuple[float, float] = (0.0, 0.0),
        token: CancellationToken | None = None,
    ) -> tuple[bool, ChunkStatus, str | None]:
        """Pick cube cleanly with high grasp (-0.246), pitch +66 deg, seat on open table, release & retract."""
        ok, st, rsn = self._pick_up_cube(
            from_xy,
            grasp_yaw,
            z_grasp=-0.246,
            is_station=is_station,
            grip_ctrl=0.082,
            token=token,
        )
        if not ok:
            return ok, st, rsn

        ok, st, rsn = self._ramp(
            "flipB_lift",
            {"robot_z_ctrl": -0.145},
            0.28,
            hold_grip=True,
            token=token,
        )
        if not ok:
            return ok, st, rsn

        if abs(self._ctrl("wrist_yaw_ctrl")) > 0.03:
            ok, st, rsn = self._ramp(
                "flipB_yaw_to_zero",
                {"wrist_yaw_ctrl": 0.0},
                0.52,
                settle_s=0.08,
                hold_grip=True,
                token=token,
            )
            if not ok:
                return ok, st, rsn

        ok, st, rsn = self._move_xy(
            "flipB_move_table",
            (float(place_xy[0]), float(place_xy[1])),
            hold_grip=True,
            token=token,
        )
        if not ok:
            return ok, st, rsn

        pitch_goals: dict[str, float] = {
            "wrist_pitch_ctrl": math.radians(90.0),
            "wrist_yaw_ctrl": 0.0,
        }
        if is_station:
            pitch_goals["base_clear_ctrl"] = 0.0
        ok, st, rsn = self._ramp(
            "flipB_pitch_90deg",
            pitch_goals,
            0.40,
            settle_s=0.06,
            hold_grip=True,
            token=token,
        )
        if not ok:
            return ok, st, rsn

        # Descend gently in 10ms chunks through ActionChunkExecutor until table touches cube
        z_start = self._ctrl("robot_z_ctrl")
        z_floor = -0.58
        n_chunks = 50
        for s in range(1, n_chunks + 1):
            if self._table_touching_cube() or float(self.data.geom_xpos[self._right_pad_geom][2]) <= 0.630:
                break
            frac = float(s) / float(n_chunks)
            z_next = z_start + frac * (z_floor - z_start)
            ok, st, rsn = self._ramp(
                f"flipB_descend_{s}",
                {"robot_z_ctrl": z_next, "left_finger_ctrl": 0.082, "right_finger_ctrl": 0.082},
                0.01,
                hold_grip=True,
                token=token,
            )
            if not ok:
                return ok, st, rsn

        # Symmetric finger opening while close to table avoids yaw twist/drag
        ok, st, rsn = self._ramp(
            "flipB_open_both_fingers",
            {"left_finger_ctrl": 0.0, "right_finger_ctrl": 0.0},
            0.16,
            settle_s=0.14,
            token=token,
        )
        if not ok:
            return ok, st, rsn

        # Low lift just clear of table (-0.22), fast horizontal retract, then level wrist
        wrist_xy = np.asarray(self.data.xpos[self._wrist_body][:2], dtype=float)
        pm_xy = self.pad_midpoint_world()[:2]
        diff = wrist_xy - pm_xy
        norm = float(np.linalg.norm(diff))
        away = diff / norm if norm > 1e-6 else np.array([0.0, -1.0], dtype=float)

        ok, st, rsn = self._ramp(
            "flipB_lift_clear",
            {"robot_z_ctrl": -0.22},
            0.22,
            settle_s=0.04,
            token=token,
        )
        if not ok:
            return ok, st, rsn

        ok, st, rsn = self._ramp(
            "flipB_retract_clear",
            {
                "robot_x_ctrl": float(np.clip(self._ctrl("robot_x_ctrl") + float(away[0]) * 0.20, -0.5, 0.5)),
                "robot_y_ctrl": float(np.clip(self._ctrl("robot_y_ctrl") + float(away[1]) * 0.20, -0.5, 0.5)),
            },
            0.12,
            settle_s=0.08,
            token=token,
        )
        if not ok:
            return ok, st, rsn

        ok, st, rsn = self._ramp(
            "flipB_lift_and_level",
            {"robot_z_ctrl": -0.145, "wrist_pitch_ctrl": 0.0},
            0.28,
            settle_s=0.14,
            token=token,
        )
        if not ok:
            return ok, st, rsn

        return True, ChunkStatus.COMPLETED, None

    def orient_face_up_and_dock(
        self,
        target_face: str,
        tracker: CubeOrientationTracker,
        *,
        current_location: str,
        current_center_xy: tuple[float, float],
        visual_relocalize_fn: Callable[[], tuple[tuple[float, float], np.ndarray | None]] | None = None,
        token: CancellationToken | None = None,
    ) -> FlipAndFeedResult:
        """Bring any target cube face (`U/D/F/B/L/R`) to +Z_world and seat inside turn_station."""
        t0 = float(self.data.time)
        face = target_face.strip()[0]
        if face not in "URFDLB":
            raise ValueError(f"Unsupported face {target_face!r}")

        aligned, res_deg = self.sync_station_lattice_state()
        if not aligned:
            return FlipAndFeedResult(
                success=False,
                target_face=face,
                flips_required=tracker.estimated_flips(face),
                flips_executed=0,
                regrasps_executed=0,
                elapsed_sim_s=0.0,
                preempted=False,
                chunk_status=ChunkStatus.FAILED.value,
                failure_reason=(
                    f"SLICE_MISALIGNED_JAM: station top slice misaligned by {res_deg:+.2f} deg; "
                    "recover_preempted_turn_slice is required before arm extraction or flipping"
                ),
                orientation=tracker.snapshot(),
                telemetry={
                    "failure_code": "SLICE_MISALIGNED_JAM",
                    "is_lattice_aligned": False,
                    "residual_slice_angle_deg": round(res_deg, 3),
                },
            )

        flips_needed = tracker.estimated_flips(face)
        flips_done = 0
        regrasps_done = 0

        if flips_needed == 0:
            if current_location == "station":
                ok, st, rsn = self._ramp("zero_ensure_base_home", {"base_clear_ctrl": 0.0}, 0.12, token=token)
            else:
                grasp_yaw = self.select_collision_free_table_yaw(
                    current_center_xy, tracker.canonical_table_yaw()
                )
                ok, st, rsn = self._pick_up_cube(
                    current_center_xy,
                    grasp_yaw,
                    z_grasp=-0.282,
                    is_station=False,
                    token=token,
                )
                if ok:
                    ok, st, rsn = self._deliver_upright_held_cube_to_station(grasp_yaw=grasp_yaw, token=token)
                    if ok:
                        tracker.record_verified_flip(
                            axis_rotation(np.array([0.0, 0.0, 1.0]), -grasp_yaw),
                            is_flip=False,
                            duration_s=float(self.data.time) - t0,
                            source="dock_upright",
                        )
            return FlipAndFeedResult(
                success=ok,
                target_face=face,
                flips_required=0,
                flips_executed=0,
                regrasps_executed=0,
                elapsed_sim_s=float(self.data.time) - t0,
                preempted=st in (ChunkStatus.PREEMPTED_SAFE_HOLD, ChunkStatus.SAFETY_ABORTED),
                chunk_status=st.value,
                failure_reason=rsn,
                orientation=tracker.snapshot(),
            )

        if flips_needed == 1:
            d_world = tracker.face_world_normal(face)
            yaw_1 = math.atan2(float(d_world[0]), -float(d_world[1]))
            ok, st, rsn = self._pick_up_cube(
                current_center_xy,
                yaw_1,
                z_grasp=-0.282,
                is_station=(current_location == "station"),
                token=token,
            )
            if ok:
                ok, st, rsn = self._deliver_flipped_held_cube_to_station(token=token)
            if ok:
                delta_r = axis_rotation(np.array([1.0, 0.0, 0.0]), -math.pi * 0.5) @ axis_rotation(
                    np.array([0.0, 0.0, 1.0]), -yaw_1
                )
                tracker.record_verified_flip(
                    delta_r,
                    is_flip=True,
                    duration_s=float(self.data.time) - t0,
                    source="flip_primitive_a",
                )
                flips_done = 1
            return FlipAndFeedResult(
                success=ok,
                target_face=face,
                flips_required=1,
                flips_executed=flips_done,
                regrasps_executed=0,
                elapsed_sim_s=float(self.data.time) - t0,
                preempted=st in (ChunkStatus.PREEMPTED_SAFE_HOLD, ChunkStatus.SAFETY_ABORTED),
                chunk_status=st.value,
                failure_reason=rsn,
                orientation=tracker.snapshot(),
            )

        # 2-flip bottom face combo: lay 90 deg on table -> release -> visual relocalize -> regrasp -> Flip A
        yaw_1 = self.select_collision_free_table_yaw(
            current_center_xy, tracker.canonical_table_yaw()
        )
        ok, st, rsn = self._lay_cube_90deg_on_table(
            from_xy=current_center_xy,
            grasp_yaw=yaw_1,
            is_station=(current_location == "station"),
            place_xy=(0.0, 0.0),
            token=token,
        )
        if not ok:
            return FlipAndFeedResult(
                success=False,
                target_face=face,
                flips_required=2,
                flips_executed=0,
                regrasps_executed=0,
                elapsed_sim_s=float(self.data.time) - t0,
                preempted=st in (ChunkStatus.PREEMPTED_SAFE_HOLD, ChunkStatus.SAFETY_ABORTED),
                chunk_status=st.value,
                failure_reason=rsn,
                orientation=tracker.snapshot(),
            )

        delta_r1 = axis_rotation(np.array([1.0, 0.0, 0.0]), math.pi * 0.5) @ axis_rotation(
            np.array([0.0, 0.0, 1.0]), -yaw_1
        )
        tracker.record_verified_flip(
            delta_r1,
            is_flip=True,
            is_regrasp=False,
            duration_s=float(self.data.time) - t0,
            source="flip_b_table_lay",
        )
        flips_done = 1

        # Independent visual re-localization of laid cube on table
        if visual_relocalize_fn is not None:
            reloc_xy, reloc_rot = visual_relocalize_fn()
            if reloc_rot is not None:
                tracker.update_from_visual_pose(reloc_rot, source="visual_regrasp_reloc")
        else:
            reloc_xy = (0.0, -0.04)

        d_world = tracker.face_world_normal(face)
        yaw_2 = math.atan2(float(d_world[0]), -float(d_world[1]))
        t_pick = float(self.data.time)
        ok, st, rsn = self._pick_up_cube(
            reloc_xy,
            yaw_2,
            z_grasp=-0.282,
            is_station=False,
            token=token,
        )
        if ok:
            regrasps_done = 1
            ok, st, rsn = self._deliver_flipped_held_cube_to_station(token=token)
        if ok:
            delta_r2 = axis_rotation(np.array([1.0, 0.0, 0.0]), -math.pi * 0.5) @ axis_rotation(
                np.array([0.0, 0.0, 1.0]), -yaw_2
            )
            tracker.record_verified_flip(
                delta_r2,
                is_flip=True,
                is_regrasp=True,
                duration_s=float(self.data.time) - t_pick,
                source="flip_b_second_flip",
            )
            flips_done = 2

        return FlipAndFeedResult(
            success=ok,
            target_face=face,
            flips_required=2,
            flips_executed=flips_done,
            regrasps_executed=regrasps_done,
            elapsed_sim_s=float(self.data.time) - t0,
            preempted=st in (ChunkStatus.PREEMPTED_SAFE_HOLD, ChunkStatus.SAFETY_ABORTED),
            chunk_status=st.value,
            failure_reason=rsn,
            orientation=tracker.snapshot(),
            telemetry={"relocalized_xy": [round(float(x), 4) for x in reloc_xy]},
        )
