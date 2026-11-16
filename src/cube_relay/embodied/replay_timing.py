"""Simulation-clock recording and non-mutating motion timing instrumentation."""
from contextlib import contextmanager
from functools import wraps
import hashlib
import inspect
import time
import numpy as np


class MotionTiming:
    def __init__(self, backend):
        self.b = backend
        self.reset()

    def reset(self):
        self.events = []
        self.stack = []
        self.path = self.stationary = 0.
        self.xy_path = 0.
        self.previous = None
        self.digest = hashlib.sha256()
        self.steps = 0

    def tick(self):
        b = self.b
        gid = b._id(b.mujoco.mjtObj.mjOBJ_BODY, "gripper")
        pos = b.data.xpos[gid].copy()
        if self.previous is not None:
            distance = float(np.linalg.norm(pos-self.previous))
            self.path += distance
            self.xy_path += float(np.linalg.norm(pos[:2]-self.previous[:2]))
            if distance / b.model.opt.timestep < .001:
                self.stationary += b.model.opt.timestep
        self.previous = pos
        self.digest.update(b.data.qpos.tobytes())
        self.digest.update(b.data.qvel.tobytes())
        self.steps += 1

    def joints(self):
        b = self.b
        names = ["robot_x_joint", "robot_y_joint", "robot_z_joint", "wrist_yaw_joint", "wrist_pitch_joint"]
        if b.physical_u:
            names += ["turn_rotor_joint", "u_layer_joint"]
        return {name: float(b.data.qpos[b.model.jnt_qposadr[b._joint(name)]]) for name in names}

    def joint_velocities(self):
        b = self.b
        return {name: float(b.data.qvel[b.model.jnt_dofadr[b._joint(name)]]) for name in self.joints()}

    @contextmanager
    def segment(self, name, params):
        started = time.perf_counter()
        event = {"id": len(self.events), "parent": self.stack[-1] if self.stack else None,
                 "name": name, "params": params, "start_sim": float(self.b.data.time),
                 "start_joints": self.joints(), "start_joint_velocities":self.joint_velocities()}
        self.events.append(event)
        self.stack.append(event["id"])
        start_path, start_stationary = self.path, self.stationary
        start_xy = self.xy_path
        try:
            yield event
        finally:
            self.stack.pop()
            duration = float(self.b.data.time)-event["start_sim"]
            event.update(end_sim=float(self.b.data.time), duration_sim=duration,
                         wall_seconds=time.perf_counter()-started,
                         tcp_path_m=self.path-start_path,
                         tcp_mean_speed_m_s=(self.path-start_path)/duration if duration else 0.,
                         tcp_stationary_seconds=self.stationary-start_stationary,
                         tcp_xy_path_m=self.xy_path-start_xy,
                         commanded_hold_seconds=duration if params.get("targets", None) == {} else 0.,
                         end_joints=self.joints(), end_joint_velocities=self.joint_velocities())

    def install(self):
        for name in ("_set_controls", "_move_gantry_xy_damped", "_monitored_motion",
                     "_monitored_rotation", "_guarded_stage_motion", "_lower_until_table_supported",
                     "skill_establish_grasp", "capture_released_views", "task_place_release",
                     "task_reorient", "task_regrasp", "task_align_scan_axes"):
            original = getattr(self.b, name)
            signature = inspect.signature(original)
            @wraps(original)
            def wrapped(*args, _original=original, _name=name, _signature=signature, **kwargs):
                params = dict(_signature.bind(*args, **kwargs).arguments)
                with self.segment(_name, params):
                    return _original(*args, **kwargs)
            setattr(self.b, name, wrapped)


class TimedFrames(list):
    def __init__(self, backend):
        super().__init__()
        self.b = backend
        self.timestamps = []
        self.next_capture = 0.

    def clear(self):
        super().clear()
        self.timestamps.clear()
        self.next_capture = float(self.b.data.time)

    def append(self, frame):
        # Legacy call-site snapshots are not inserted in the uniform movie.
        # Debug RGB-D files remain independently available to perception.
        if self.b.video_timing == "legacy":
            self.store(frame)

    def store(self, frame):
        super().append(frame)
        self.timestamps.append(float(self.b.data.time))

    def capture_due(self):
        b = self.b
        if b.video_path is None or b.video_timing == "legacy" or b.data.time + 1e-9 < self.next_capture:
            return
        b.renderer.disable_depth_rendering()
        b.renderer.update_scene(b.data, camera=b.video_camera)
        self.store(b.renderer.render().copy())
        self.next_capture += 1./b.video_fps


def resample_indices(timestamps, fps):
    """Use only recorded physical frames; never synthesize interpolated poses."""
    ts = np.asarray(timestamps, dtype=float)
    if not len(ts):
        return []
    if fps <= 0 or np.any(np.diff(ts) < 0):
        raise ValueError("positive fps and monotonic timestamps required")
    count = int(np.ceil((ts[-1]-ts[0])*fps-1e-9))+1
    targets = ts[0]+np.arange(count)/fps
    # nearest actual sample (at most one physics timestep from schedule)
    right = np.searchsorted(ts, targets).clip(0,len(ts)-1)
    left = np.maximum(0,right-1)
    return np.where(abs(ts[left]-targets) <= abs(ts[right]-targets),left,right).tolist()
