"""Interruptible ActionChunk execution substrate for classical skills and VLA policies.

Provides a unified execution contract (``ActionChunk``, ``CancellationToken``,
``ActionChunkExecutor``, ``ChunkExecutionResult``) supporting:
  - Trajectory / waypoint execution with active gantry damping;
  - Immediate or checkpointed preemption via thread-safe ``CancellationToken``;
  - Safe-hold braking (< 100 ms sim stop) when unloaded;
  - Pressurized finger grip preservation (no accidental drop) when holding a cube;
  - World/goal revision staleness & step-jump safety invariant checks.
"""

from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass, field
from enum import Enum
import math
import threading
import time
from typing import TYPE_CHECKING, Any, Callable, Literal, Sequence

import numpy as np

if TYPE_CHECKING:
    import mujoco


class InterruptMode(str, Enum):
    """How a cancellation request preempts an active ActionChunk."""

    IMMEDIATE_HOLD = "IMMEDIATE_HOLD"
    SAFE_CHECKPOINT = "SAFE_CHECKPOINT"


class ChunkStatus(str, Enum):
    """Terminal status of an ActionChunk execution."""

    COMPLETED = "COMPLETED"
    PREEMPTED_SAFE_HOLD = "PREEMPTED_SAFE_HOLD"
    SAFETY_ABORTED = "SAFETY_ABORTED"
    FAILED = "FAILED"


_DAMPED_XY_JOINTS: dict[str, str] = {
    "robot_x_ctrl": "robot_x_joint",
    "robot_y_ctrl": "robot_y_joint",
}
_FINGER_CTRLS = ("left_finger_ctrl", "right_finger_ctrl")
_ARM_JOINT_MAP: dict[str, str] = {
    "robot_x_ctrl": "robot_x_joint",
    "robot_y_ctrl": "robot_y_joint",
    "robot_z_ctrl": "robot_z_joint",
    "wrist_yaw_ctrl": "wrist_yaw_joint",
    "wrist_pitch_ctrl": "wrist_pitch_joint",
    "left_finger_ctrl": "left_finger_joint",
    "right_finger_ctrl": "right_finger_joint",
}


class CancellationToken:
    """Thread-safe cancellation token shared between controller, monitor, and executor."""

    def __init__(
        self,
        *,
        expected_world_revision: int | None = None,
        expected_goal_revision: int | None = None,
    ) -> None:
        self._lock = threading.Lock()
        self._speculative_pause = False
        self._pending_routes = 0
        self._event = threading.Event()
        self._cancelled = False
        self._reason: str | None = None
        self._interrupt_mode = InterruptMode.IMMEDIATE_HOLD
        self._requested_at_sim_s: float | None = None
        self._requested_at_wall_s: float | None = None
        self.expected_world_revision = expected_world_revision
        self.expected_goal_revision = expected_goal_revision

    def set_speculative_pause(self, paused: bool) -> None:
        with self._lock:
            self._speculative_pause = paused

    @contextmanager
    def speculative_route(self):
        """Keep the cursor parked until every concurrent chat has resolved."""
        with self._lock:
            self._pending_routes += 1
        try:
            yield
        finally:
            with self._lock:
                self._pending_routes -= 1

    @property
    def speculative_pause(self) -> bool:
        with self._lock:
            return (self._speculative_pause or self._pending_routes > 0) and not self._cancelled

    def cancel(
        self,
        reason: str = "USER_INTERRUPT",
        *,
        mode: InterruptMode = InterruptMode.IMMEDIATE_HOLD,
        sim_time_s: float | None = None,
    ) -> None:
        """Request preemption of the executing ActionChunk."""
        with self._lock:
            if not self._cancelled:
                self._cancelled = True
                self._reason = reason
                self._interrupt_mode = mode
                self._requested_at_sim_s = sim_time_s
                self._requested_at_wall_s = time.monotonic()
                self._event.set()

    def is_cancelled(self) -> bool:
        """Return whether preemption has been requested."""
        return self._event.is_set()

    @property
    def reason(self) -> str | None:
        with self._lock:
            return self._reason

    @property
    def interrupt_mode(self) -> InterruptMode:
        with self._lock:
            return self._interrupt_mode

    @property
    def requested_at_sim_s(self) -> float | None:
        with self._lock:
            return self._requested_at_sim_s

    @property
    def requested_at_wall_s(self) -> float | None:
        with self._lock:
            return self._requested_at_wall_s

    def snapshot(self) -> dict[str, Any]:
        """Return a thread-safe snapshot of token state."""
        with self._lock:
            return {
                "cancelled": self._cancelled,
                "reason": self._reason,
                "interrupt_mode": self._interrupt_mode.value,
                "requested_at_sim_s": self._requested_at_sim_s,
                "requested_at_wall_s": self._requested_at_wall_s,
                "expected_world_revision": self.expected_world_revision,
                "expected_goal_revision": self.expected_goal_revision,
            }


@dataclass(slots=True)
class ActionChunk:
    """Unified interruptible control sequence emitted by classical skills or VLA policies."""

    chunk_id: str
    targets: list[dict[str, float]]
    source_type: Literal["CLASSICAL_SKILL", "VLA_POLICY"] = "CLASSICAL_SKILL"
    dt: float = 0.002
    substeps_per_target: int = 1
    hold_grip_on_interrupt: bool = False
    held_grip_ctrl: float = 0.070
    kd_xy: float = 0.14
    kd_z: float = 0.10
    world_revision: int = 0
    goal_revision: int = 0
    pose_estimate_id: str | None = None
    max_xy_step_m: float | None = None
    max_z_step_m: float | None = None
    safe_checkpoints: set[int] = field(default_factory=set)
    metadata: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def linear_ramp(
        cls,
        *,
        chunk_id: str,
        start: dict[str, float],
        goal: dict[str, float],
        steps: int,
        settle_steps: int = 0,
        dt: float = 0.002,
        source_type: Literal["CLASSICAL_SKILL", "VLA_POLICY"] = "CLASSICAL_SKILL",
        hold_grip_on_interrupt: bool = False,
        held_grip_ctrl: float = 0.070,
        kd_xy: float = 0.14,
        kd_z: float = 0.10,
        world_revision: int = 0,
        goal_revision: int = 0,
        pose_estimate_id: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> ActionChunk:
        """Build a linearly interpolated ActionChunk with optional post-ramp settle steps."""
        n_ramp = max(1, int(steps))
        n_settle = max(0, int(settle_steps))
        targets: list[dict[str, float]] = []
        for idx in range(1, n_ramp + n_settle + 1):
            alpha = min(1.0, idx / float(n_ramp))
            step_cmd: dict[str, float] = {}
            for key, end_val in goal.items():
                s_val = float(start.get(key, end_val))
                step_cmd[key] = s_val + alpha * (float(end_val) - s_val)
            targets.append(step_cmd)
        return cls(
            chunk_id=chunk_id,
            targets=targets,
            source_type=source_type,
            dt=dt,
            substeps_per_target=1,
            hold_grip_on_interrupt=hold_grip_on_interrupt,
            held_grip_ctrl=held_grip_ctrl,
            kd_xy=kd_xy,
            kd_z=kd_z,
            world_revision=world_revision,
            goal_revision=goal_revision,
            pose_estimate_id=pose_estimate_id,
            metadata=dict(metadata or {}),
        )

    @classmethod
    def trapezoidal_xy(
        cls,
        *,
        chunk_id: str,
        start_xy: tuple[float, float],
        goal_xy: tuple[float, float],
        dt: float = 0.002,
        v_max: float = 0.26,
        a_max: float = 1.20,
        min_duration_s: float = 0.16,
        max_duration_s: float = 2.40,
        hold_grip_on_interrupt: bool = False,
        held_grip_ctrl: float = 0.070,
        kd_xy: float = 0.14,
        extra_ctrls: dict[str, float] | None = None,
        world_revision: int = 0,
        goal_revision: int = 0,
        pose_estimate_id: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> ActionChunk:
        """Plan an adaptive Euclidean-distance trapezoidal-velocity XY trajectory."""
        dx = float(goal_xy[0]) - float(start_xy[0])
        dy = float(goal_xy[1]) - float(start_xy[1])
        dist = math.hypot(dx, dy)
        if dist < 1e-6:
            total_s = min_duration_s
            n_steps = max(1, int(round(total_s / dt)))
            base = {"robot_x_ctrl": float(goal_xy[0]), "robot_y_ctrl": float(goal_xy[1])}
            if extra_ctrls:
                base.update({k: float(v) for k, v in extra_ctrls.items()})
            return cls(
                chunk_id=chunk_id,
                targets=[dict(base) for _ in range(n_steps)],
                dt=dt,
                hold_grip_on_interrupt=hold_grip_on_interrupt,
                held_grip_ctrl=held_grip_ctrl,
                kd_xy=kd_xy,
                world_revision=world_revision,
                goal_revision=goal_revision,
                pose_estimate_id=pose_estimate_id,
                metadata={"distance_m": 0.0, "planned_duration_s": total_s, **(metadata or {})},
            )

        t_acc = v_max / max(a_max, 1e-6)
        d_acc = 0.5 * a_max * t_acc * t_acc
        if 2.0 * d_acc >= dist:
            # Triangular profile (never hits cruise velocity)
            t_acc = math.sqrt(dist / max(a_max, 1e-6))
            t_flat = 0.0
            v_peak = a_max * t_acc
        else:
            v_peak = v_max
            t_flat = (dist - 2.0 * d_acc) / max(v_peak, 1e-6)
        total_s = max(min_duration_s, min(max_duration_s, 2.0 * t_acc + t_flat))
        scale_t = total_s / max(2.0 * t_acc + t_flat, 1e-6)
        t_acc *= scale_t
        t_flat *= scale_t
        # Recompute peak acceleration so integral matches exact dist
        a_eff = dist / max(t_acc * (t_acc + t_flat), 1e-9)

        n_steps = max(2, int(math.ceil(total_s / dt)))
        ux, uy = dx / dist, dy / dist
        targets: list[dict[str, float]] = []
        for idx in range(1, n_steps + 1):
            t = min(total_s, idx * dt)
            if t <= t_acc:
                s = 0.5 * a_eff * t * t
            elif t <= t_acc + t_flat:
                s = 0.5 * a_eff * t_acc * t_acc + a_eff * t_acc * (t - t_acc)
            else:
                dt_rem = max(0.0, total_s - t)
                s = dist - 0.5 * a_eff * dt_rem * dt_rem
            s = max(0.0, min(dist, s))
            cmd = {
                "robot_x_ctrl": float(start_xy[0]) + ux * s,
                "robot_y_ctrl": float(start_xy[1]) + uy * s,
            }
            if extra_ctrls:
                cmd.update({k: float(v) for k, v in extra_ctrls.items()})
            targets.append(cmd)
        return cls(
            chunk_id=chunk_id,
            targets=targets,
            dt=dt,
            hold_grip_on_interrupt=hold_grip_on_interrupt,
            held_grip_ctrl=held_grip_ctrl,
            kd_xy=kd_xy,
            world_revision=world_revision,
            goal_revision=goal_revision,
            pose_estimate_id=pose_estimate_id,
            metadata={
                "distance_m": dist,
                "planned_duration_s": total_s,
                **(metadata or {}),
            },
        )


@dataclass(slots=True)
class ChunkExecutionResult:
    """Structured outcome and interrupt-latency telemetry for an ActionChunk."""

    chunk_id: str
    source_type: str
    status: ChunkStatus
    steps_executed: int
    total_steps: int
    sim_time_start_s: float
    sim_time_end_s: float
    interrupt_sim_s: float | None = None
    interrupt_to_hold_sim_ms: float | None = None
    final_ee_vel_norm: float = 0.0
    final_gripper_closure: tuple[float, float] = (0.0, 0.0)
    hold_grip_preserved: bool = False
    object_drop_detected: bool = False
    cancel_reason: str | None = None
    safety_violation: str | None = None
    telemetry: dict[str, Any] = field(default_factory=dict)


class ActionChunkExecutor:
    """MuJoCo real-time interruptible ActionChunk executor with safe-hold semantics."""

    def __init__(
        self,
        model: mujoco.MjModel,
        data: mujoco.MjData,
        *,
        record_command_fn: Callable[[float, dict[str, float]], None] | None = None,
        post_step_fn: Callable[[int], str | None] | None = None,
        revision_provider_fn: Callable[[], tuple[int, int]] | None = None,
        held_object_ok_fn: Callable[[], bool] | None = None,
        step_fn: Callable[[], None] | None = None,
    ) -> None:
        self.model = model
        self.data = data
        self.record_command_fn = record_command_fn
        self.post_step_fn = post_step_fn
        self.revision_provider_fn = revision_provider_fn
        self.held_object_ok_fn = held_object_ok_fn
        import mujoco as _mujoco

        self._mujoco = _mujoco
        self._step_fn = step_fn or (lambda: _mujoco.mj_step(self.model, self.data))
        self._actuator_ids: dict[str, int] = {}
        self._joint_qpos_adr: dict[str, int] = {}
        self._joint_dof_adr: dict[str, int] = {}
        for i in range(model.nu):
            name = _mujoco.mj_id2name(model, _mujoco.mjtObj.mjOBJ_ACTUATOR, i)
            if name:
                self._actuator_ids[name] = i
        for i in range(model.njnt):
            name = _mujoco.mj_id2name(model, _mujoco.mjtObj.mjOBJ_JOINT, i)
            if name:
                self._joint_qpos_adr[name] = int(model.jnt_qposadr[i])
                self._joint_dof_adr[name] = int(model.jnt_dofadr[i])

    def _ee_vel_norm(self) -> float:
        vx = float(self.data.qvel[self._joint_dof_adr["robot_x_joint"]])
        vy = float(self.data.qvel[self._joint_dof_adr["robot_y_joint"]])
        vz = float(self.data.qvel[self._joint_dof_adr["robot_z_joint"]])
        return math.sqrt(vx * vx + vy * vy + vz * vz)

    def _finger_closures(self) -> tuple[float, float]:
        lq = float(self.data.qpos[self._joint_qpos_adr["left_finger_joint"]])
        rq = float(self.data.qpos[self._joint_qpos_adr["right_finger_joint"]])
        return (lq, rq)

    def _apply_step_target(self, target: dict[str, float], *, kd_xy: float, kd_z: float) -> None:
        for act_name, cmd_val in target.items():
            aid = self._actuator_ids.get(act_name)
            if aid is None:
                continue
            val = float(cmd_val)
            if act_name in _DAMPED_XY_JOINTS:
                jn = _DAMPED_XY_JOINTS[act_name]
                vel = float(self.data.qvel[self._joint_dof_adr[jn]])
                val = val - kd_xy * vel
            elif act_name == "robot_z_ctrl":
                vel = float(self.data.qvel[self._joint_dof_adr["robot_z_joint"]])
                val = val - kd_z * vel
            self.data.ctrl[aid] = val

    def _validate_invariants(
        self,
        chunk: ActionChunk,
        step_idx: int,
        target: dict[str, float],
        prev_target: dict[str, float] | None,
        token: CancellationToken | None,
    ) -> str | None:
        if not (np.all(np.isfinite(self.data.qpos)) and np.all(np.isfinite(self.data.qvel))):
            return "NON_FINITE_SIM_STATE"
        if any(not math.isfinite(float(v)) for v in target.values()):
            return f"NON_FINITE_TARGET_AT_STEP_{step_idx}"
        if chunk.max_xy_step_m is not None and prev_target is not None:
            dx = abs(float(target.get("robot_x_ctrl", 0.0)) - float(prev_target.get("robot_x_ctrl", 0.0)))
            dy = abs(float(target.get("robot_y_ctrl", 0.0)) - float(prev_target.get("robot_y_ctrl", 0.0)))
            if math.hypot(dx, dy) > float(chunk.max_xy_step_m):
                return f"XY_STEP_JUMP_EXCEEDED_AT_{step_idx}"
        if chunk.max_z_step_m is not None and prev_target is not None:
            dz = abs(float(target.get("robot_z_ctrl", 0.0)) - float(prev_target.get("robot_z_ctrl", 0.0)))
            if dz > float(chunk.max_z_step_m):
                return f"Z_STEP_JUMP_EXCEEDED_AT_{step_idx}"
        if self.revision_provider_fn is not None:
            cur_world_rev, cur_goal_rev = self.revision_provider_fn()
            exp_w = token.expected_world_revision if (token and token.expected_world_revision is not None) else chunk.world_revision
            exp_g = token.expected_goal_revision if (token and token.expected_goal_revision is not None) else chunk.goal_revision
            if exp_w and cur_world_rev != exp_w:
                return f"STALE_WORLD_REVISION:{chunk.world_revision}!={cur_world_rev}"
            if exp_g and cur_goal_rev != exp_g:
                return f"STALE_GOAL_REVISION:{chunk.goal_revision}!={cur_goal_rev}"
        return None

    def _enter_safe_hold(
        self,
        *,
        hold_grip: bool,
        held_grip_ctrl: float,
        max_hold_steps: int = 48,
        vel_tol: float = 0.020,
        kd_brake: float = 0.65,
    ) -> tuple[bool, bool]:
        """Engage active viscous braking & safe finger pressure hold within < 100 ms sim time."""
        # Balance static gravity bias (qfrc_bias / kp_z) so Z brakes cleanly toward 0 vel instead of drifting.
        z_cur_q = float(self.data.qpos[self._joint_qpos_adr["robot_z_joint"]])
        z_cur_ctrl = float(self.data.ctrl[self._actuator_ids["robot_z_ctrl"]])
        aid_z = self._actuator_ids["robot_z_ctrl"]
        dof_z = self._joint_dof_adr["robot_z_joint"]
        kp_z = float(self.model.actuator_gainprm[aid_z, 0])
        if kp_z > 1e-6:
            eq_sag = float(np.clip(float(self.data.qfrc_bias[dof_z]) / kp_z, 0.0, 0.060))
        else:
            eq_sag = min(0.042, max(0.020, z_cur_ctrl - z_cur_q)) if hold_grip else min(0.042, max(0.0, z_cur_ctrl - z_cur_q))
        z_hold_ref = z_cur_q + eq_sag

        if hold_grip:
            for fn in _FINGER_CTRLS:
                aid = self._actuator_ids[fn]
                self.data.ctrl[aid] = max(float(self.data.ctrl[aid]), float(held_grip_ctrl))
        else:
            # Keep fingers gently parked at current non-clamping pose (or open if already open).
            for fn in _FINGER_CTRLS:
                aid = self._actuator_ids[fn]
                self.data.ctrl[aid] = min(float(self.data.ctrl[aid]), 0.04)

        hold_anchors = {
            "wrist_yaw_ctrl": float(self.data.qpos[self._joint_qpos_adr["wrist_yaw_joint"]]),
            "wrist_pitch_ctrl": float(self.data.qpos[self._joint_qpos_adr["wrist_pitch_joint"]]),
        }
        if "turn_rotor_ctrl" in self._actuator_ids and "turn_rotor_joint" in self._joint_qpos_adr:
            hold_anchors["turn_rotor_ctrl"] = float(
                self.data.qpos[self._joint_qpos_adr["turn_rotor_joint"]]
            )
        xy_anchors = {
            act_name: float(self.data.qpos[self._joint_qpos_adr[jn]])
            for act_name, jn in _DAMPED_XY_JOINTS.items()
        }
        for act_name, val in hold_anchors.items():
            self.data.ctrl[self._actuator_ids[act_name]] = val

        for _ in range(max(1, int(max_hold_steps))):
            for act_name, jn in _DAMPED_XY_JOINTS.items():
                qd_now = float(self.data.qvel[self._joint_dof_adr[jn]])
                self.data.ctrl[self._actuator_ids[act_name]] = xy_anchors[act_name] - kd_brake * qd_now
            qzd_now = float(self.data.qvel[self._joint_dof_adr["robot_z_joint"]])
            self.data.ctrl[self._actuator_ids["robot_z_ctrl"]] = z_hold_ref - kd_brake * qzd_now
            if hold_grip:
                for fn in _FINGER_CTRLS:
                    aid = self._actuator_ids[fn]
                    self.data.ctrl[aid] = max(float(self.data.ctrl[aid]), float(held_grip_ctrl))
            self._step_fn()
            if self._ee_vel_norm() <= vel_tol:
                break

        closures = self._finger_closures()
        grip_preserved = bool(hold_grip and closures[0] > 0.03 and closures[1] > 0.03)
        drop_detected = False
        if hold_grip:
            if self.held_object_ok_fn is not None:
                drop_detected = not bool(self.held_object_ok_fn())
            elif closures[0] > 0.073 or closures[1] > 0.073 or closures[0] < 0.02 or closures[1] < 0.02:
                # Over-closed empty squeeze or lost grip width indicates object drop
                drop_detected = True
        return grip_preserved, drop_detected

    def _hold_until_routed(self, chunk: ActionChunk, token: CancellationToken) -> None:
        saved_ctrl = self.data.ctrl.copy()
        anchors = {}
        joints = {
            **_ARM_JOINT_MAP,
            "turn_rotor_ctrl": "turn_rotor_joint",
            "turn_z_ctrl": "turn_z_joint",
            "base_clear_ctrl": "base_clear_joint",
        }
        for actuator, joint in joints.items():
            if actuator in _FINGER_CTRLS or actuator not in self._actuator_ids:
                continue
            aid = self._actuator_ids[actuator]
            dof = self._joint_dof_adr[joint]
            anchor = float(self.data.qpos[self._joint_qpos_adr[joint]])
            kp = float(self.model.actuator_gainprm[aid, 0])
            damping = 0.65 if actuator in (*_DAMPED_XY_JOINTS, "robot_z_ctrl") else 0.0
            anchors[aid] = (anchor, self._joint_qpos_adr[joint], dof, damping, kp)
        if chunk.hold_grip_on_interrupt:
            for finger in _FINGER_CTRLS:
                aid = self._actuator_ids[finger]
                self.data.ctrl[aid] = max(saved_ctrl[aid], chunk.held_grip_ctrl)
        try:
            while token.speculative_pause:
                for aid, (anchor, qpos, dof, damping, kp) in anchors.items():
                    # Feed forward gravity and contact load while damping motion toward the entry pose.
                    load = self.data.qfrc_bias[dof] - self.data.qfrc_constraint[dof]
                    bias = float(load) / kp if kp > 0 else 0.0
                    current = self.data.qpos[qpos]
                    gain = 0.12 if damping else 1.0
                    self.data.ctrl[aid] = current + gain * (anchor - current) + bias - damping * self.data.qvel[dof]
                self._step_fn()
        finally:
            self.data.ctrl[:] = saved_ctrl

    def execute(
        self,
        chunk: ActionChunk,
        *,
        token: CancellationToken | None = None,
        async_monitor_fn: Callable[[int, float], None] | None = None,
        post_step_fn: Callable[[int], str | None] | None = None,
    ) -> ChunkExecutionResult:
        """Execute an ActionChunk synchronously with real-time preemption and safety checks."""
        t_start = float(self.data.time)
        total_steps = len(chunk.targets)
        prev_target: dict[str, float] | None = None
        substeps = max(1, int(chunk.substeps_per_target))
        active_post_step = post_step_fn if post_step_fn is not None else self.post_step_fn

        for step_idx, target in enumerate(chunk.targets):
            if async_monitor_fn is not None:
                async_monitor_fn(step_idx, float(self.data.time))

            violation = self._validate_invariants(chunk, step_idx, target, prev_target, token)
            if violation is not None:
                grip_ok, drop_det = self._enter_safe_hold(
                    hold_grip=chunk.hold_grip_on_interrupt,
                    held_grip_ctrl=chunk.held_grip_ctrl,
                )
                return ChunkExecutionResult(
                    chunk_id=chunk.chunk_id,
                    source_type=chunk.source_type,
                    status=ChunkStatus.SAFETY_ABORTED,
                    steps_executed=step_idx,
                    total_steps=total_steps,
                    sim_time_start_s=t_start,
                    sim_time_end_s=float(self.data.time),
                    final_ee_vel_norm=self._ee_vel_norm(),
                    final_gripper_closure=self._finger_closures(),
                    hold_grip_preserved=grip_ok,
                    object_drop_detected=drop_det,
                    safety_violation=violation,
                )

            for substep in range(substeps):
                if token is not None and token.speculative_pause:
                    self._hold_until_routed(chunk, token)
                if token is not None and token.is_cancelled():
                    can_stop = (
                        token.interrupt_mode == InterruptMode.IMMEDIATE_HOLD
                        or not chunk.safe_checkpoints
                        or step_idx in chunk.safe_checkpoints
                    )
                    if can_stop:
                        t_req = token.requested_at_sim_s
                        if t_req is None:
                            t_req = float(self.data.time)
                        grip_ok, drop_det = self._enter_safe_hold(
                            hold_grip=chunk.hold_grip_on_interrupt,
                            held_grip_ctrl=chunk.held_grip_ctrl,
                        )
                        t_end = float(self.data.time)
                        return ChunkExecutionResult(
                            chunk_id=chunk.chunk_id,
                            source_type=chunk.source_type,
                            status=ChunkStatus.PREEMPTED_SAFE_HOLD,
                            steps_executed=step_idx,
                            total_steps=total_steps,
                            sim_time_start_s=t_start,
                            sim_time_end_s=t_end,
                            interrupt_sim_s=t_req,
                            interrupt_to_hold_sim_ms=max(0.0, (t_end - t_req) * 1000.0),
                            final_ee_vel_norm=self._ee_vel_norm(),
                            final_gripper_closure=self._finger_closures(),
                            hold_grip_preserved=grip_ok,
                            object_drop_detected=drop_det,
                            cancel_reason=token.reason,
                        )

                if substep == 0:
                    self._apply_step_target(target, kd_xy=chunk.kd_xy, kd_z=chunk.kd_z)
                    if self.record_command_fn is not None:
                        self.record_command_fn(float(self.data.time), target)
                self._step_fn()
            if active_post_step is not None:
                post_err = active_post_step(step_idx)
                if post_err is not None:
                    grip_ok, drop_det = self._enter_safe_hold(
                        hold_grip=chunk.hold_grip_on_interrupt,
                        held_grip_ctrl=chunk.held_grip_ctrl,
                    )
                    return ChunkExecutionResult(
                        chunk_id=chunk.chunk_id,
                        source_type=chunk.source_type,
                        status=ChunkStatus.SAFETY_ABORTED,
                        steps_executed=step_idx + 1,
                        total_steps=total_steps,
                        sim_time_start_s=t_start,
                        sim_time_end_s=float(self.data.time),
                        final_ee_vel_norm=self._ee_vel_norm(),
                        final_gripper_closure=self._finger_closures(),
                        hold_grip_preserved=grip_ok,
                        object_drop_detected=drop_det,
                        safety_violation=post_err,
                    )
            prev_target = target

        return ChunkExecutionResult(
            chunk_id=chunk.chunk_id,
            source_type=chunk.source_type,
            status=ChunkStatus.COMPLETED,
            steps_executed=total_steps,
            total_steps=total_steps,
            sim_time_start_s=t_start,
            sim_time_end_s=float(self.data.time),
            final_ee_vel_norm=self._ee_vel_norm(),
            final_gripper_closure=self._finger_closures(),
            hold_grip_preserved=bool(chunk.hold_grip_on_interrupt),
            object_drop_detected=False,
        )
