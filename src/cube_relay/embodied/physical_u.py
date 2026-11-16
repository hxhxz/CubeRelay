"""One-scene, contact-driven U prototype. No runtime recoloring or pose writes.

Compile-time extension of the unchanged v8 scene. A passive layer hinge and
releasable servo brake approximate a cube detent; an EXTERNAL rotary jaw must
supply turning torque through contacts. Lower body remains a free body.
"""
from pathlib import Path
import xml.etree.ElementTree as ET
import math
import numpy as np
from dataclasses import replace

STATION = np.array([.35, -.32, .66])


def physical_color_layout(kociemba_state: str) -> str:
    """Initialization only: legacy XML U/D rows point opposite to Kociemba.

    This involution is NOT a move. It maps notation to static sticker slots;
    never call it to generate a post-action appearance.
    """
    faces = [kociemba_state[i:i+9] for i in range(0, 54, 9)]
    for index in (0, 3):
        face = faces[index]
        faces[index] = face[6:9]+face[3:6]+face[:3]
    return "".join(faces)


def physical_observations(observations):
    """Convert actual legacy camera grid coordinates to Kociemba coordinates."""
    result = []
    order = (6, 7, 8, 3, 4, 5, 0, 1, 2)
    for obs in observations:
        if obs.face in "UD":
            obs = replace(obs, stickers=tuple(obs.stickers[i] for i in order),
                          sticker_confidences=tuple(obs.sticker_confidences[i] for i in order)
                          if obs.sticker_confidences is not None else None,
                          source_view=obs.source_view+":physical_kociemba_rows")
        result.append(obs)
    return result


def build_u_scene(path: str | Path) -> str:
    root = ET.parse(path).getroot()
    cube = root.find(".//body[@name='cube']")
    core = cube.find("geom[@name='cube_core']")
    core.set("pos", "0 0 -.02")
    core.set("size", ".06 .06 .04")
    core.set("mass", ".0566667")
    layer = ET.SubElement(cube, "body", name="u_layer")
    ET.SubElement(layer, "joint", name="u_layer_joint", type="hinge", axis="0 0 1",
                  damping=".002", armature=".00001", frictionloss=".0002")
    ET.SubElement(layer, "geom", name="u_layer_core", type="box", pos="0 0 .0401",
                  size=".06 .06 .0199", material="cube_black", mass=".0283333")
    for geom in list(cube.findall("geom")):
        name = geom.get("name", "")
        if name.startswith("sticker_"):
            _, face, cell = name.split("_")
            if face == "U" or (face in "FRBL" and int(cell) < 3):
                cube.remove(geom)
                layer.append(geom)
    actuators = root.find("actuator")
    ET.SubElement(actuators, "position", name="u_brake", joint="u_layer_joint", kp="50")
    world = root.find("worldbody")
    station = ET.SubElement(world, "body", name="turn_station", pos=".35 -.32 .66")
    base_carriage = ET.SubElement(station, "body", name="base_carriage")
    ET.SubElement(base_carriage, "inertial", pos="0 0 0", mass=".1", diaginertia=".001 .001 .001")
    ET.SubElement(base_carriage, "joint", name="base_clear_joint", type="slide", axis="1 0 0",
                  range="0 .3", damping="5")
    ET.SubElement(actuators, "position", name="base_clear_ctrl", joint="base_clear_joint", kp="2000")
    # Base clamp contacts only the lower two rows. It starts wide open.
    for sign, side in [(1, "pos"), (-1, "neg")]:
        body = ET.SubElement(base_carriage, "body", name=f"base_{side}", pos=f"0 {sign*.13} -.025")
        ET.SubElement(body, "joint", name=f"base_{side}_joint", type="slide", axis=f"0 {-sign} 0",
                      range="0 .075", damping="5", armature=".01")
        ET.SubElement(body, "geom", name=f"base_{side}_pad", type="box", size=".055 .01 .025",
                      mass=".1", friction="5 .05 .002", rgba=".3 .3 .35 1")
        ET.SubElement(actuators, "position", name=f"base_{side}_ctrl", joint=f"base_{side}_joint", kp="700")
    carriage = ET.SubElement(station, "body", name="turn_carriage", pos="0 0 .50")
    ET.SubElement(carriage, "joint", name="turn_z_joint", type="slide", axis="0 0 -1",
                  range="0 .5", damping="5")
    ET.SubElement(carriage, "inertial", pos="0 0 0", mass=".1", diaginertia=".001 .001 .001")
    rotor = ET.SubElement(carriage, "body", name="turn_rotor")
    ET.SubElement(rotor, "joint", name="turn_rotor_joint", type="hinge", axis="0 0 1",
                  damping=".1", armature=".001")
    ET.SubElement(rotor, "geom", name="rotor_hub", type="cylinder", pos="0 0 .15", size=".03 .02",
                  mass=".1", rgba=".6 .3 .1 1")
    for sign, side in [(1, "pos"), (-1, "neg")]:
        jaw = ET.SubElement(rotor, "body", name=f"turn_{side}", pos=f"{sign*.11} 0 .045")
        ET.SubElement(jaw, "joint", name=f"turn_{side}_joint", type="slide", axis=f"{-sign} 0 0",
                      range="0 .055", damping="3")
        ET.SubElement(jaw, "geom", name=f"turn_{side}_pad", type="box", size=".01 .055 .012",
                      mass=".05", friction="5 .02 .002", rgba=".6 .3 .1 1")
        ET.SubElement(actuators, "position", name=f"turn_{side}_ctrl", joint=f"turn_{side}_joint", kp="600")
    ET.SubElement(actuators, "position", name="turn_z_ctrl", joint="turn_z_joint", kp="2000")
    ET.SubElement(actuators, "position", name="turn_rotor_ctrl", joint="turn_rotor_joint", kp="20")
    ET.SubElement(world, "camera", name="turn_overview", pos=".35 -1.1 1.15",
                  xyaxes="1 0 0 0 .55 .83", fovy="40")
    return ET.tostring(root, encoding="unicode")


class ContactUTurn:
    def __init__(self, backend):
        if not backend.physical_u:
            raise ValueError("physical_u scene required")
        self.b = backend
        self.trace = []
        self.failure = None

    def angle(self, name):
        return float(self.b.data.qpos[self.b.model.jnt_qposadr[self.b._joint(name)]])

    def video_frame(self):
        from PIL import Image, ImageDraw
        b = self.b
        if b.video_timing != "legacy":
            return
        b.renderer.update_scene(b.data, camera="turn_overview")
        image = Image.fromarray(b.renderer.render().copy())
        phase = self.trace[-1]["phase"] if self.trace else ""
        ImageDraw.Draw(image).text((5,5), f"t={b.data.time:.3f}s {phase}", fill="white")
        b.frames.append(np.asarray(image))

    def sample(self, phase, *, record=True):
        b = self.b
        contacts = []
        for i in range(b.data.ncon):
            c = b.data.contact[i]
            names = [b.mujoco.mj_id2name(b.model, b.mujoco.mjtObj.mjOBJ_GEOM, int(g)) for g in (c.geom1, c.geom2)]
            force = np.zeros(6)
            b.mujoco.mj_contactForce(b.model, b.data, i, force)
            contacts.append({"geoms": names, "point": c.pos.tolist(), "distance": float(c.dist),
                             "normal_force": float(force[0])})
        cube = b._id(b.mujoco.mjtObj.mjOBJ_BODY, "cube")
        row = {"time": float(b.data.time), "phase": phase,
               "layer_angle": self.angle("u_layer_joint"), "rotor_angle": self.angle("turn_rotor_joint"),
               "cube_position": b.data.xpos[cube].tolist(), "cube_rotation": b.data.xmat[cube].tolist(),
               "cube_velocity": b.data.cvel[cube].tolist(),
               "contacts": contacts,
               "layer_velocity": float(b.data.qvel[b.model.jnt_dofadr[b._joint("u_layer_joint")]]),
               "rotor_velocity": float(b.data.qvel[b.model.jnt_dofadr[b._joint("turn_rotor_joint")]]),
               "rotor_torque": float(b.data.actuator_force[b._actuator("turn_rotor_ctrl")]),
               "layer_brake_torque": float(b.data.actuator_force[b._actuator("u_brake")])}
        if record:
            self.trace.append(row)
        return row

    @staticmethod
    def collision_safe(row):
        for c in row["contacts"]:
            if c["distance"] < -.005 or not math.isfinite(c["normal_force"]) or abs(c["normal_force"]) > 1000:
                return False
            names = set(c["geoms"])
            for side in ("pos", "neg"):
                if f"base_{side}_pad" in names and names != {f"base_{side}_pad", "cube_core"}:
                    return False
                if f"turn_{side}_pad" in names and names != {f"turn_{side}_pad", "u_layer_core"}:
                    return False
            if "rotor_hub" in names or ("palm" in names and names & {"cube_core", "u_layer_core"}):
                return False
        return True

    def move(self, phase, targets, seconds=1.0, guard=None):
        with self.b.motion_timing.segment(phase, {"targets":targets,"seconds":seconds}):
            return self._move(phase, targets, seconds, guard)

    def _move(self, phase, targets, seconds=1.0, guard=None):
        b = self.b
        b.video_camera = "turn_overview"
        ids = {b._actuator(name): value for name, value in targets.items()}
        start = {idx: float(b.data.ctrl[idx]) for idx in ids}
        steps = int(seconds/b.model.opt.timestep)
        for step in range(steps):
            t = (step+1)/steps
            s = t*t*(3-2*t)
            for idx, target in ids.items():
                b.data.ctrl[idx] = start[idx]+s*(target-start[idx])
            b.step_physics()
            row = self.sample(phase, record=(step % 10 == 0 or step == steps-1))
            if not self.collision_safe(row) or (guard and not guard(row)):
                self.failure = phase+"_SAFETY_STOP"
                self.trace.append(row)
                # Hold current measured actuator joint positions, not body poses.
                for idx in range(b.model.nu):
                    joint = b.model.actuator_trnid[idx, 0]
                    b.data.ctrl[idx] = b.data.qpos[b.model.jnt_qposadr[joint]]
                raise RuntimeError(self.failure)
            if step % 25 == 0:
                self.video_frame()
        return True

    def lower_to_support(self):
        with self.b.motion_timing.segment("DOCK_LOWER", {}):
            return self._lower_to_support()

    def _lower_to_support(self):
        """Monitored placement, stopping on stable table support, not pose truth."""
        b = self.b
        actuator = b._actuator("robot_z_ctrl")
        start = float(b.data.ctrl[actuator])
        count = 0
        steps = int(2./b.model.opt.timestep)
        for step in range(steps):
            t = (step+1)/steps
            b.data.ctrl[actuator] = start+(-.48-start)*t*t*(3-2*t)
            b.step_physics()
            row = self.sample("DOCK_LOWER", record=(step%10 == 0))
            supported = any(set(c["geoms"]) == {"cube_core", "table"} and c["normal_force"] > .05
                            for c in row["contacts"])
            # On table touchdown load transfers off the finger pads. Loss of
            # pad force is safe only while actual table support is present.
            if not self.collision_safe(row) or (not supported and not all(b._finger_contact_forces()[:2])):
                self.failure = "DOCK_LOWER_SAFETY_STOP"
                self.trace.append(row)
                raise RuntimeError(self.failure)
            count = count+1 if supported and np.linalg.norm(row["cube_velocity"][3:]) < .08 else 0
            if step%25 == 0:
                self.video_frame()
            if count >= 40:
                return True
        return False

    @staticmethod
    def paired(row, prefix, core):
        return all(any(set(c["geoms"]) == {f"{prefix}_{side}_pad", core} and c["normal_force"] > .05
                       for c in row["contacts"]) for side in ("pos", "neg"))

    def dock_and_turn(self):
        try:
            return self._dock_and_turn()
        except RuntimeError:
            if self.failure is None:
                raise
            return {"success": False, "failure": self.failure}

    def _dock_and_turn(self):
        b = self.b
        # Existing scan ends with a held cube. Use the existing safety-checked
        # whole-cube rotation, then camera-derived center for transport delta.
        upright = b.task_reorient("pitch", -self.angle("wrist_pitch_joint"))
        if not upright.get("success"):
            return {"success": False, "failure": "UPRIGHT_FAILED", "detail": upright}
        b.task_observe_held(2000)
        world = b.refresh_visual_world_state("overhead", valid_after_skill="reorient_transport")
        if not world.get("success"):
            return {"success": False, "failure": "VISUAL_POSE_MISSING", "detail": world}
        center = np.array(world["center_world_m"])
        # Opposing side-depth estimates cancel the oblique overhead centroid
        # bias; never use the simulated body position to aim the transporter.
        from .perception_v2 import DeterministicCubeLocalizer
        localizer = DeterministicCubeLocalizer()
        side_detections = [localizer.locate(b.capture_rgbd(camera)) for camera in
                           ("inspection_high_y", "inspection_high_neg_y")]
        if all(d is not None for d in side_detections):
            center = np.mean([d.center_world_m for d in side_detections], axis=0)
        self.trace.append({"phase": "VISUAL_TRANSPORT_TARGET", "time": float(b.data.time),
                           "estimated_center": center.tolist(), "target_center": STATION.tolist()})
        ctrl = {f"robot_{axis}_ctrl": self.angle(f"robot_{axis}_joint")+STATION[i]-center[i]
                for i, axis in enumerate("xy")}
        if not self.move("TRANSPORT", ctrl, 3., lambda row: all(b._finger_contact_forces()[:2])):
            return {"success": False, "failure": self.failure}
        if not self.lower_to_support():
            return {"success": False, "failure": "DOCK_SUPPORT_MISSING"}
        self.move("BASE_CLOSE", {"base_pos_ctrl": .065, "base_neg_ctrl": .065}, 2.)
        if not self.paired(self.trace[-1], "base", "cube_core"):
            return {"success": False, "failure": "BASE_CONTACT_MISSING"}
        base_guard = lambda row: self.paired(row, "base", "cube_core")
        self.move("BASE_HOLD", {}, .2, base_guard)
        self.move("ROBOT_RELEASE", {"left_finger_ctrl": 0., "right_finger_ctrl": 0.}, 1., base_guard)
        self.move("ROBOT_RETREAT_Z", {"robot_z_ctrl": -.02}, 1., base_guard)
        self.move("ROBOT_RETREAT_XY", {"robot_x_ctrl": -.45, "robot_y_ctrl": .45}, 2., base_guard)
        self.move("HEAD_LOWER", {"turn_z_ctrl": .5}, 2., base_guard)
        self.move("HEAD_CLOSE", {"turn_pos_ctrl": .045, "turn_neg_ctrl": .045}, 2., base_guard)
        if not self.paired(self.trace[-1], "turn", "u_layer_core"):
            return {"success": False, "failure": "LAYER_CONTACT_MISSING"}
        start = self.sample("TURN_START")
        self.move("CONTACT_CONFIRM", {}, .2, lambda row:
                  base_guard(row) and self.paired(row, "turn", "u_layer_core"))
        # Release the ideal detent, never drive the layer joint. Only the
        # external rotor actuator is commanded during the turn.
        brake = b._actuator("u_brake")
        b.model.actuator_gainprm[brake, 0] = 0
        b.model.actuator_biasprm[brake, 1] = 0
        start_pos = np.array(start["cube_position"])
        start_rotation = np.array(start["cube_rotation"]).reshape(3,3)
        def stable(row):
            rotation = np.array(row["cube_rotation"]).reshape(3,3)
            angular_slip = float(np.arccos(np.clip((np.trace(start_rotation.T@rotation)-1)/2, -1, 1)))
            rotor_slip = abs((row["layer_angle"]-start["layer_angle"])-(row["rotor_angle"]-start["rotor_angle"]))
            row["base_angular_slip"] = angular_slip
            row["rotor_layer_slip"] = rotor_slip
            return (self.paired(row, "base", "cube_core") and self.paired(row, "turn", "u_layer_core")
                    and np.linalg.norm(np.array(row["cube_position"])-start_pos) < .01
                    and angular_slip < .03 and rotor_slip < .03
                    and all(c["distance"] > -.005 and c["normal_force"] < 1000 for c in row["contacts"]))
        ok = self.move("CONTACT_TURN", {"turn_rotor_ctrl": -math.pi/2}, 4., stable)
        if ok:
            ok = self.move("TURN_HOLD", {}, .5, stable)
        final = self.sample("TURN_END")
        error = abs((final["layer_angle"]-start["layer_angle"])+math.pi/2)
        ok = (ok and error < .03 and abs(final["rotor_angle"]+math.pi/2) < .03
              and abs(final["layer_velocity"]) < .02 and abs(final["rotor_velocity"]) < .02)
        if ok:
            # Re-engage detent at the MEASURED position, not a symbolic target.
            b.data.ctrl[brake] = final["layer_angle"]
            b.model.actuator_gainprm[brake, 0] = 50
            b.model.actuator_biasprm[brake, 1] = -50
            self.move("HEAD_OPEN", {"turn_pos_ctrl": 0., "turn_neg_ctrl": 0.}, 1.)
            self.move("HEAD_RETRACT", {"turn_z_ctrl": 0.}, 2.)
            if not any(set(c["geoms"]) == {"cube_core", "table"} for c in self.trace[-1]["contacts"]):
                return {"success": False, "failure": "POST_TURN_SUPPORT_MISSING"}
            self.move("BASE_OPEN", {"base_pos_ctrl": 0., "base_neg_ctrl": 0.}, 1.)
            self.move("BASE_CLEAR_FOR_VISION", {"base_clear_ctrl": .3}, 2.)
        return {"success": bool(ok), "failure": (self.failure or "LAYER_OR_ROTOR_NOT_SETTLED") if not ok else None,
                "target_delta": -math.pi/2, "actual_delta": final["layer_angle"]-start["layer_angle"],
                "layer_error": error, "base_displacement": float(np.linalg.norm(np.array(final["cube_position"])-start_pos))}
