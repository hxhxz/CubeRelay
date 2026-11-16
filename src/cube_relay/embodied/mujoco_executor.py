"""MuJoCo-backed approximate face-turn mechanism with measured joint feedback."""

from __future__ import annotations

import math
import time
from pathlib import Path
import numpy as np

from .execution import ActionFeedback, ActionRequest
from cube_relay.cube.state import LEGAL_MOVES


class MuJoCoTurnExecutor:
    """REAL SIMULATION / APPROXIMATE CUBE: steps MuJoCo and checks joint arrival."""

    def __init__(self, model_path: str | Path | None = None, tolerance: float = 0.03) -> None:
        try:
            import mujoco
        except ImportError as exc:
            raise RuntimeError(
                "MuJoCo is not installed; use Python 3.11-3.13 and install .[simulation]"
            ) from exc
        self.mujoco = mujoco
        default = Path(__file__).resolve().parents[3] / "simulation" / "cube_relay.xml"
        self.model_path = Path(model_path or default)
        self.model = mujoco.MjModel.from_xml_path(str(self.model_path))
        self.data = mujoco.MjData(self.model)
        self.tolerance = tolerance
        self.stopped = False
        self.targets = {face: 0.0 for face in "URFDLB"}
        self.last_trace: list[dict] = []
        self.frame_callback = None
        self.require_scene_safety = True

    def execute(self, request: ActionRequest) -> ActionFeedback:
        if request.move not in LEGAL_MOVES:
            raise ValueError(f"illegal move: {request.move}")
        self.last_trace = []
        if self.stopped:
            return ActionFeedback(False, request.move, 0.0, None, "mujoco", "emergency stop")
        face = request.move[0]
        turns = 2 if request.move.endswith("2") else -1 if request.move.endswith("'") else 1
        # Hinges point OUTWARD. Standard Singmaster clockwise is negative
        # by the right-hand rule when looking at the face from outside.
        self.targets[face] -= turns * math.pi / 2
        actuator = self.mujoco.mj_name2id(
            self.model, self.mujoco.mjtObj.mjOBJ_ACTUATOR, f"turn_{face}"
        )
        joint = self.mujoco.mj_name2id(
            self.model, self.mujoco.mjtObj.mjOBJ_JOINT, f"face_{face}"
        )
        self.data.ctrl[actuator] = self.targets[face]
        qpos_index = self.model.jnt_qposadr[joint]
        body = self.model.jnt_bodyid[joint]
        plate_geoms = np.flatnonzero(self.model.geom_bodyid == body)
        collision_enabled = bool(any(self.model.geom_contype[g] or
                                     self.model.geom_conaffinity[g] for g in plate_geoms))
        started = time.perf_counter()
        error = float("inf")
        max_steps = int(2.0 / self.model.opt.timestep)
        velocity = float("inf")
        collision = False
        for step in range(max_steps):
            self.mujoco.mj_step(self.model, self.data)
            error = abs(self.data.qpos[qpos_index] - self.targets[face])
            velocity = abs(float(self.data.qvel[self.model.jnt_dofadr[joint]]))
            contacts = []
            for contact_index in range(self.data.ncon):
                force = np.zeros(6)
                self.mujoco.mj_contactForce(self.model, self.data, contact_index, force)
                contact = self.data.contact[contact_index]
                if contact.geom1 in plate_geoms or contact.geom2 in plate_geoms:
                    collision = True
                if self.require_scene_safety and (
                    not np.isfinite(force).all() or contact.dist < -.01 or abs(force[0]) > 1e4
                ):
                    collision = True
                contacts.append({"geom1": int(contact.geom1), "geom2": int(contact.geom2),
                                 "body1": self.mujoco.mj_id2name(self.model, self.mujoco.mjtObj.mjOBJ_BODY,
                                                                self.model.geom_bodyid[contact.geom1]),
                                 "body2": self.mujoco.mj_id2name(self.model, self.mujoco.mjtObj.mjOBJ_BODY,
                                                                self.model.geom_bodyid[contact.geom2]),
                                 "distance_m": float(contact.dist),
                                 "normal_force_n": float(force[0])})
            self.last_trace.append({"step": step, "time": float(self.data.time),
                "joint": f"face_{face}", "target_radians": self.targets[face],
                "actual_radians": float(self.data.qpos[qpos_index]),
                "velocity_radians_s": velocity, "contacts": contacts,
                "plate_collision_enabled": collision_enabled,
                "unexpected_plate_contact": collision,
                "boundary": "separate constrained hinge; plate contacts disabled in existing model"})
            if self.frame_callback is not None and step % 5 == 0:
                self.frame_callback(self.model, self.data)
            if collision:
                self.data.ctrl[actuator] = self.data.qpos[qpos_index]
                break
            if error <= self.tolerance and velocity < 0.08:
                break
        success = not collision and error <= self.tolerance and velocity < 0.08
        return ActionFeedback(
            success, request.move, time.perf_counter() - started, error, "mujoco",
            "UNSAFE_SCENE_CONTACT" if collision else
            "joint target reached" if success else "joint target timeout",
        )

    def emergency_stop(self) -> None:
        self.stopped = True
        self.data.ctrl[:] = 0
