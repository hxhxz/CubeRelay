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
from collections import deque
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from cube_relay.cube import CubeEngine

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
        video_timing: str = "sim_time",
    ) -> None:
        try:
            import mujoco
        except ImportError as exc:
            raise RuntimeError("install cube-relay[simulation] with Python 3.11-3.13") from exc
        self.mujoco = mujoco
        default = Path(__file__).resolve().parents[3] / "simulation" / "cube_relay_v2.xml"
        self.model_path = Path(model_path or default)
        self.physical_u = physical_u
        if physical_u:
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
        self._turner = None if physical_u else MuJoCoTurnExecutor()
        self._plan_version = 1
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
        self._apply_grasp_config_to_model()
        self._set_sticker_colors(self._appearance_state)
        mujoco.mj_forward(self.model, self.data)
        self.motion_timing.install()

    def step_physics(self) -> None:
        self.mujoco.mj_step(self.model, self.data)
        self.motion_timing.tick()
        self.frames.capture_due()

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
        if self.physical_u:
            from .physical_u import physical_color_layout
            facelets = physical_color_layout(facelets)
        for face_index, face in enumerate("URFDLB"):
            for sticker in range(9):
                geom = self._id(
                    self.mujoco.mjtObj.mjOBJ_GEOM, f"sticker_{face}_{sticker}"
                )
                self.model.geom_rgba[geom] = _COLORS[facelets[face_index * 9 + sticker]]

    def reset_random(self, seed: int, scramble_steps: int) -> dict[str, object]:
        rng = np.random.default_rng(seed)
        self.mujoco.mj_resetData(self.model, self.data)
        state, moves = self.engine.scramble(seed, scramble_steps)
        self._appearance_state = state
        self._set_sticker_colors(state)
        joint = self._joint("cube_free")
        address = self.model.jnt_qposadr[joint]
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
        self._predicted_cube_rotation = None
        self._index_cube_to_world = None
        # Evaluation-only metadata. The controller intentionally discards this return value.
        return {"seed": seed, "scramble": moves, "truth_for_evaluation_only": state}

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
        self.renderer.disable_depth_rendering()
        self.renderer.update_scene(self.data, camera=camera_name)
        rgb = self.renderer.render().copy()
        self.renderer.enable_depth_rendering()
        self.renderer.update_scene(self.data, camera=camera_name)
        depth = self.renderer.render().copy()
        self.renderer.disable_depth_rendering()
        return RGBDFrame(
            rgb, depth, self._camera_calibration(camera_name), camera_name, float(self.data.time)
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

    def _finger_contacts(self) -> set[int]:
        core = self._id(self.mujoco.mjtObj.mjOBJ_GEOM, "cube_core")
        left = self._id(self.mujoco.mjtObj.mjOBJ_GEOM, "left_finger_pad")
        right = self._id(self.mujoco.mjtObj.mjOBJ_GEOM, "right_finger_pad")
        touched: set[int] = set()
        for index in range(self.data.ncon):
            contact = self.data.contact[index]
            pair = {int(contact.geom1), int(contact.geom2)}
            if core in pair:
                touched |= pair & {left, right}
        return touched

    def _finger_contact_forces(self) -> tuple[bool, bool, float, float]:
        """Read physical pad/core contacts and solved normal forces."""
        core = self._id(self.mujoco.mjtObj.mjOBJ_GEOM, "cube_core")
        left = self._id(self.mujoco.mjtObj.mjOBJ_GEOM, "left_finger_pad")
        right = self._id(self.mujoco.mjtObj.mjOBJ_GEOM, "right_finger_pad")
        touched = {left: False, right: False}
        forces = {left: 0.0, right: 0.0}
        wrench = np.zeros(6)
        for index in range(self.data.ncon):
            contact = self.data.contact[index]
            pair = {int(contact.geom1), int(contact.geom2)}
            if core not in pair:
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
        core = self._id(self.mujoco.mjtObj.mjOBJ_GEOM, "cube_core")
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
            if core not in pair:
                continue
            other = int(contact.geom2) if int(contact.geom1) == core else int(contact.geom1)
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

    def generate_grasp_candidates(
        self, target_xyz: tuple[float, float, float], cube_yaw: float
    ) -> tuple[GraspCandidate, ...]:
        """Generate opposing-face grasps and score IK, clearance and alignment.

        The gripper closes along its local Y axis. A square has two equivalent
        opposing face pairs, hence the two wrist-yaw candidates separated by 90°.
        """
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
            collision_free = radial_clearance >= .10
            alignment_error = self._wrapped_angle_distance(wrist_yaw, cube_yaw + offset, math.pi)
            geometry_score = max(0.0, math.cos(2 * alignment_error))
            motion_cost = self._wrapped_angle_distance(wrist_yaw, current_yaw, 2 * math.pi)
            rejection = None
            if not ik_feasible:
                rejection = "IK target outside Cartesian joint limits"
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
            collision_free = min(.8 - abs(x), .65 - abs(y)) >= .10
            rejection = None
            if horizontal < .82:
                rejection = "opposing faces are too vertical for top-down gripper"
            elif not ik_feasible:
                rejection = "IK target outside Cartesian joint limits"
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
            cube_position = self.data.xpos[
                self._id(self.mujoco.mjtObj.mjOBJ_BODY, "cube")
            ]
            displacement_now = float(np.linalg.norm(cube_position - reference))
            pad_contact_now = bool(self._finger_contacts())
            unexpected_now = self._geoms_touch("palm", "cube_core")
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
        self.last_selected_grasp_candidate = candidate
        if not candidate.ik_feasible or not candidate.collision_free:
            return {"success": False, "failure_code": "CANDIDATE_INFEASIBLE"}
        config = self.grasp_config
        pregrasp_ctrl = min(.067, max(0.0, (.256 - config.pregrasp_gap_m) / 2))
        self._set_controls({
            "left_finger_ctrl": pregrasp_ctrl,
            "right_finger_ctrl": pregrasp_ctrl,
        }, .25)
        self._contact_debug_sample("PREGRASP")
        self._skill_phase_trace.append("ALIGN")
        self._set_controls({
            "wrist_yaw_ctrl": candidate.wrist_yaw_radians,
            "wrist_pitch_ctrl": 0.0,
        }, .7)
        self._skill_phase_trace.append("APPROACH")
        tangent_default, closure_default = config.approach_offset_local_xy_m
        tangent = tangent_default if tangent_offset_m is None else tangent_offset_m
        closure = closure_default if closure_offset_m is None else closure_offset_m
        cosine, sine = math.cos(candidate.wrist_yaw_radians), math.sin(candidate.wrist_yaw_radians)
        offset_x = cosine * tangent - sine * closure
        offset_y = sine * tangent + cosine * closure
        x, y, _ = target_xyz
        ok, failure = self._guarded_stage_motion({
            "robot_x_ctrl": x + offset_x,
            "robot_y_ctrl": y + offset_y,
            "robot_z_ctrl": -.22,
        }, .8, "APPROACH")
        if ok:
            ok, failure = self._guarded_stage_motion(
                {"robot_z_ctrl": config.contact_z_ctrl}, .5, "APPROACH"
            )
        final = self.contact_debug_trace[-1]
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
        left_total = right_total = 0.0
        left_seen = right_seen = samples = settle = 0
        steps = max(1, int(config.close_duration_seconds / self.model.opt.timestep))
        confirm_steps = max(1, int(config.bilateral_confirm_seconds / self.model.opt.timestep))
        start = float(self.data.ctrl[self._actuator("left_finger_ctrl")])
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
                hold = self._monitored_motion({}, config.stable_hold_seconds, "STABLE_HOLD")
                success = (
                    hold.bilateral_rate >= .95
                    and min(hold.left_force_n, hold.right_force_n)
                    >= config.minimum_normal_force_n
                )
                return {
                    "success": success,
                    "failure_code": None if success else "BILATERAL_CONTACT_UNSTABLE",
                    "left_contact_rate": hold.left_rate,
                    "right_contact_rate": hold.right_rate,
                    "left_normal_force_n": hold.left_force_n,
                    "right_normal_force_n": hold.right_force_n,
                    "max_slip_m": hold.max_slip_m,
                }
        return {
            "success": False,
            "failure_code": "BILATERAL_CONTACT_NOT_ESTABLISHED",
            "left_contact_rate": left_seen / max(samples, 1),
            "right_contact_rate": right_seen / max(samples, 1),
            "left_normal_force_n": left_total / max(samples, 1),
            "right_normal_force_n": right_total / max(samples, 1),
            "max_slip_m": 0.0,
        }

    def skill_test_lift(self) -> dict[str, object]:
        """Trial lift and full lift; impossible to call without bilateral hold."""
        config = self.grasp_config
        if not self._skill_phase_trace or self._skill_phase_trace[-1] != "STABLE_HOLD":
            return {"success": False, "failure_code": "BILATERAL_CONTACT_REQUIRED"}
        start_height = self._skill_start_height or self._cube_height()
        self._skill_phase_trace.append("TRIAL_LIFT")
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
            return {
                "success": False,
                "failure_code": "TRIAL_LIFT_UNSTABLE",
                "trial_lift_success": False,
                "full_lift_success": False,
                "lift_height_m": trial_height,
                "bilateral_contact_fraction": trial.bilateral_rate,
                "max_slip_m": trial.max_slip_m,
            }
        self._skill_phase_trace.extend(["STABILITY_CHECK", "FULL_LIFT"])
        lift = self._monitored_motion(
            {"robot_z_ctrl": config.full_lift_z_ctrl}, config.full_lift_seconds, "FULL_LIFT"
        )
        height = self._cube_height() - start_height
        contact = min(trial.bilateral_rate, lift.bilateral_rate)
        slip = max(trial.max_slip_m, lift.max_slip_m)
        success = lift.bilateral_rate >= .85 and slip <= config.slip_limit_m and height >= .06
        return {
            "success": success,
            "failure_code": None if success else "FULL_LIFT_UNSTABLE",
            "trial_lift_success": True,
            "full_lift_success": success,
            "lift_height_m": height,
            "bilateral_contact_fraction": contact,
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
        self._set_controls({"wrist_yaw_ctrl": selected.wrist_yaw_radians}, .7)
        phase_trace.append("APPROACH")
        tangent, closure = config.approach_offset_local_xy_m
        cosine, sine = math.cos(selected.wrist_yaw_radians), math.sin(selected.wrist_yaw_radians)
        offset_x = cosine * tangent - sine * closure
        offset_y = sine * tangent + cosine * closure
        self._set_controls({
            "robot_x_ctrl": x + offset_x,
            "robot_y_ctrl": y + offset_y,
            "robot_z_ctrl": -.22,
        }, .8)
        # Keep pad bottoms 2 cm above the table to avoid parasitic table friction.
        self._set_controls({"robot_z_ctrl": config.contact_z_ctrl}, .5)
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
        core = self._id(self.mujoco.mjtObj.mjOBJ_GEOM, "cube_core")
        table = self._id(self.mujoco.mjtObj.mjOBJ_GEOM, "table")
        stable_steps = 0
        required = max(4, int(.08 / self.model.opt.timestep))
        steps = max(1, int(seconds / self.model.opt.timestep))
        for step in range(steps):
            progress = (step + 1) / steps
            smooth = progress * progress * (3 - 2 * progress)
            self.data.ctrl[control] = start + (lowest_z_ctrl - start) * smooth
            self.step_physics()
            supported = any(
                {int(self.data.contact[index].geom1), int(self.data.contact[index].geom2)}
                == {core, table}
                for index in range(self.data.ncon)
            )
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

    # Public task-level Skills. They deliberately expose observations and
    # contact outcomes, never simulator pose or the private logical cube state.
    def task_place_release(self) -> dict[str, object]:
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
        if self.physical_u:
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
        """Move gantry XY with active derivative damping from robot joint encoders.

        The gantry slide actuators (kp=500, damping=2.0) are underdamped for
        large step targets. Adding velocity damping from the robot's own
        encoder velocity eliminates overshoot and settles within ~2 mm without
        changing model physics or touching object ground truth.
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
        settled = 0
        steps = max(1, int(round(max_seconds / step_seconds)))
        converged = False
        iterations = 0
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
                "trajectory_velocity_limit":None,
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
        if self.physical_u:
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
        from .failure_aware_v6 import FailureAwareRulePlanner, FailureAwareSkillAgent
        from .vlm import HeuristicSceneVLM

        refresh = self.refresh_visual_world_state(
            "overhead", valid_after_skill="before_regrasp"
        )
        excluded: set[str] = set(exclude_face_pairs or ())
        attempts: list[dict[str, object]] = []
        success = False
        if not excluded:
            # Prefer the v6 failure-aware grasp agent (contact guards, trial
            # lift, and tangent/closure offset recovery), then re-align faces
            # with the scan cameras.
            v6 = FailureAwareSkillAgent(
                self, HeuristicSceneVLM(), FailureAwareRulePlanner()
            ).run(0, 15, reset_scene=False)
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
        return {
            "success": success,
            "bilateral_contact_fraction": telemetry.bilateral_contact_fraction,
            "max_relative_slip_m": telemetry.max_relative_slip_m,
            "failure_code": None if success else (self.contact_failure_class or "REGRASP_FAILED"),
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
        diagnostics = self._monitored_rotation("wrist_yaw_ctrl", target)
        if before_state != self._appearance_state:
            raise RuntimeError("scan alignment changed internal arrangement")
        success = diagnostics.bilateral_rate >= .8 and diagnostics.max_slip_m <= .03
        if success and self._predicted_cube_rotation is None:
            # Initial calibration seed before any multi-view observation is
            # taken; once released/held views are captured, centre colours from
            # two orthogonal faces replace or validate this seed.
            self._predicted_cube_rotation = np.diag([-1.0, -1.0, 1.0])
        return {
            "success": success,
            "target_yaw_radians": target,
            "bilateral_contact_fraction": diagnostics.bilateral_rate,
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
        if getattr(self, "physical_u", False):
            raise RuntimeError("Use contact-driven U fixture; symbolic appearance updates are forbidden")
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
