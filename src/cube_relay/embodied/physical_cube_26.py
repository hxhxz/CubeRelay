from __future__ import annotations

import math
import time
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Literal

import numpy as np

from cube_relay.cube.moves import LEGAL_MOVES
from cube_relay.execution.action_chunk import (
    ActionChunk,
    ActionChunkExecutor,
    CancellationToken,
    ChunkStatus,
)
from .canonical_facelets import (
    FACE_FRAMES,
    axis_rotation,
    canonical_local_centers,
    cube_rotations_24,
)

STATION_POS = np.array([0.35, -0.32, 0.66], dtype=float)
CUBIE_STEP = 0.040
CUBIE_HALF_SIZE = 0.0198
AXIS_NAMES: tuple[str, ...] = ("U", "D", "F", "B", "R", "L")

CUBIE_COORDS: tuple[tuple[int, int, int], ...] = tuple(
    (ix, iy, iz)
    for ix in (-1, 0, 1)
    for iy in (-1, 0, 1)
    for iz in (-1, 0, 1)
    if (ix, iy, iz) != (0, 0, 0)
)


def _quat_conj(q: np.ndarray) -> np.ndarray:
    return np.array([q[0], -q[1], -q[2], -q[3]], dtype=float)


def _quat_mul(u: np.ndarray, v: np.ndarray) -> np.ndarray:
    w1, x1, y1, z1 = float(u[0]), float(u[1]), float(u[2]), float(u[3])
    w2, x2, y2, z2 = float(v[0]), float(v[1]), float(v[2]), float(v[3])
    out = np.array(
        [
            w1 * w2 - x1 * x2 - y1 * y2 - z1 * z2,
            w1 * x2 + x1 * w2 + y1 * z2 - z1 * y2,
            w1 * y2 - x1 * z2 + y1 * w2 + z1 * x2,
            w1 * z2 + x1 * y2 - y1 * x2 + z1 * w2,
        ],
        dtype=float,
    )
    norm = float(np.linalg.norm(out))
    return out / max(norm, 1e-12)


def _rotation_geodesic_rad(r_a: np.ndarray, r_b: np.ndarray) -> float:
    rel = r_a.T @ r_b
    cos_theta = float(np.clip((np.trace(rel) - 1.0) * 0.5, -1.0, 1.0))
    return float(math.acos(cos_theta))


def _rotation_axis_angle(rel: np.ndarray) -> tuple[np.ndarray, float]:
    cos_t = float(np.clip((np.trace(rel) - 1.0) * 0.5, -1.0, 1.0))
    angle = float(math.acos(cos_t))
    if angle < 1e-6:
        return np.array([0.0, 0.0, 1.0], dtype=float), 0.0
    skew = np.array(
        [
            rel[2, 1] - rel[1, 2],
            rel[0, 2] - rel[2, 0],
            rel[1, 0] - rel[0, 1],
        ],
        dtype=float,
    )
    norm = float(np.linalg.norm(skew))
    if norm < 1e-8:
        # 180 deg fallback via diagonal of R
        vals = np.maximum(0.0, (np.diag(rel) + 1.0) * 0.5)
        ax = np.sqrt(vals)
        ax_norm = float(np.linalg.norm(ax))
        return (ax / max(ax_norm, 1e-9)), angle
    return skew / norm, angle


def move_to_top_fixture_angle_rad(move: str) -> float:
    """Return top-fixture rotor angle in radians when the target face points +Z_world.

    CubeEngine defines clockwise moves (`U`, `R`, `F`, `D`, `L`, `B`) around the
    outward face normal (-90 deg right-hand rule), prime moves (`'`) as +90 deg,
    and half turns (`2`) as -180 deg.
    """
    m = move.strip()
    if m not in LEGAL_MOVES:
        raise ValueError(f"Illegal Rubik's cube move: {move!r}")
    suffix = m[1:]
    if suffix == "":
        return -math.pi * 0.5
    if suffix == "'":
        return math.pi * 0.5
    if suffix == "2":
        return -math.pi
    raise ValueError(f"Unsupported move suffix in {move!r}")


def _sticker_size_for_face(face: str) -> str:
    if face in ("U", "D"):
        return ".017 .017 .001"
    if face in ("F", "B"):
        return ".017 .001 .017"
    return ".001 .017 .017"


def _cubie_stickers_map() -> dict[tuple[int, int, int], list[tuple[str, int, np.ndarray]]]:
    mapping: dict[tuple[int, int, int], list[tuple[str, int, np.ndarray]]] = {
        coord: [] for coord in CUBIE_COORDS
    }
    for face in "URFDLB":
        centers = canonical_local_centers(face)
        for idx, pt in enumerate(centers):
            coord = (
                int(np.clip(round(float(pt[0]) / 0.039), -1, 1)),
                int(np.clip(round(float(pt[1]) / 0.039), -1, 1)),
                int(np.clip(round(float(pt[2]) / 0.039), -1, 1)),
            )
            mapping[coord].append((face, idx, np.asarray(pt, dtype=float)))
    return mapping


def build_26_cubie_scene(
    xml_path: str | Path = "simulation/cube_relay_v2.xml",
    *,
    top_turn_contact_enabled: bool = True,
) -> str:
    """Upgrade cube_relay_v2.xml to 26 persistent rigid cubies + ±90°/180° single top fixture."""
    root = ET.parse(Path(xml_path)).getroot()
    worldbody = root.find("worldbody")
    equality = root.find("equality")
    actuator = root.find("actuator")
    if worldbody is None or equality is None or actuator is None:
        raise ValueError("Invalid MuJoCo base scene XML: missing worldbody/equality/actuator")

    cube_body = worldbody.find("./body[@name='cube']")
    if cube_body is None:
        raise ValueError("Base XML missing <body name='cube'>")

    cube_pos = cube_body.attrib.get("pos", ".18 .05 .665")
    cube_body.clear()
    cube_body.attrib["name"] = "cube"
    cube_body.attrib["pos"] = cube_pos

    ET.SubElement(cube_body, "freejoint", {"name": "cube_free"})
    ET.SubElement(
        cube_body,
        "inertial",
        {"pos": "0 0 0", "mass": ".012", "diaginertia": ".00005 .00005 .00005"},
    )
    ET.SubElement(
        cube_body,
        "geom",
        {
            "name": "cube_hub",
            "type": "sphere",
            "size": ".012",
            "contype": "0",
            "conaffinity": "0",
            "material": "cube_black",
        },
    )

    for axis_name in AXIS_NAMES:
        nx, ny, nz = FACE_FRAMES[axis_name].normal
        carrier = ET.SubElement(
            cube_body,
            "body",
            {"name": f"carrier_{axis_name}", "pos": "0 0 0"},
        )
        ET.SubElement(
            carrier,
            "inertial",
            {"pos": "0 0 0", "mass": ".0005", "diaginertia": ".00002 .00002 .00002"},
        )
        ET.SubElement(
            carrier,
            "joint",
            {
                "name": f"carrier_{axis_name}_joint",
                "type": "hinge",
                "axis": f"{nx} {ny} {nz}",
                "damping": ".002",
                "armature": ".0005",
                "frictionloss": ".0002",
            },
        )

    sticker_map = _cubie_stickers_map()
    for k, coord in enumerate(CUBIE_COORDS):
        ix, iy, iz = coord
        cx, cy, cz = ix * CUBIE_STEP, iy * CUBIE_STEP, iz * CUBIE_STEP
        cubie = ET.SubElement(cube_body, "body", {"name": f"cubie_{k:02d}", "pos": "0 0 0"})
        ET.SubElement(
            cubie,
            "inertial",
            {
                "pos": f"{cx:.4f} {cy:.4f} {cz:.4f}",
                "mass": ".003",
                "diaginertia": ".00002 .00002 .00002",
            },
        )
        ET.SubElement(
            cubie,
            "joint",
            {
                "name": f"cubie_joint_{k:02d}",
                "type": "ball",
                "damping": ".0008",
                "armature": ".00005",
            },
        )
        ET.SubElement(
            cubie,
            "geom",
            {
                "name": f"cubie_geom_{k:02d}",
                "type": "box",
                "pos": f"{cx:.4f} {cy:.4f} {cz:.4f}",
                "size": f"{CUBIE_HALF_SIZE:.4f} {CUBIE_HALF_SIZE:.4f} {CUBIE_HALF_SIZE:.4f}",
                "material": "cube_black",
                "contype": "2",
                "conaffinity": "1",
            },
        )
        for face, idx, s_pos in sticker_map[coord]:
            ET.SubElement(
                cubie,
                "geom",
                {
                    "name": f"sticker_{face}_{idx}",
                    "type": "box",
                    "pos": f"{s_pos[0]:.4f} {s_pos[1]:.4f} {s_pos[2]:.4f}",
                    "size": _sticker_size_for_face(face),
                    "contype": "0",
                    "conaffinity": "0",
                    "density": "0",
                },
            )

        ET.SubElement(
            equality,
            "weld",
            {
                "name": f"w_core_{k:02d}",
                "body1": "cube",
                "body2": f"cubie_{k:02d}",
                "relpose": "0 0 0 1 0 0 0",
                "active": "true",
                "solref": ".0015 1",
                "solimp": ".98 .998 .0005",
            },
        )
        for axis_name in AXIS_NAMES:
            ET.SubElement(
                equality,
                "weld",
                {
                    "name": f"w_car_{k:02d}_{axis_name}",
                    "body1": f"carrier_{axis_name}",
                    "body2": f"cubie_{k:02d}",
                    "relpose": "0 0 0 1 0 0 0",
                    "active": "false",
                    "solref": ".0015 1",
                    "solimp": ".98 .998 .0005",
                },
            )

    # Single top turn station: holds lower 2 layers at [0.610, 0.660] and drives top layer at 0.705
    turn_station = ET.SubElement(worldbody, "body", {"name": "turn_station", "pos": ".35 -.32 .66"})
    base_carriage = ET.SubElement(turn_station, "body", {"name": "base_carriage"})
    ET.SubElement(
        base_carriage,
        "inertial",
        {"pos": "0 0 0", "mass": ".1", "diaginertia": ".001 .001 .001"},
    )
    ET.SubElement(
        base_carriage,
        "joint",
        {
            "name": "base_clear_joint",
            "type": "slide",
            "axis": "1 0 0",
            "range": "0 .3",
            "damping": "5",
        },
    )
    for pad_name, sign_y, j_axis in (("base_pos", "0.13", "0 -1 0"), ("base_neg", "-0.13", "0 1 0")):
        b = ET.SubElement(base_carriage, "body", {"name": pad_name, "pos": f"0 {sign_y} -.025"})
        ET.SubElement(
            b,
            "joint",
            {
                "name": f"{pad_name}_joint",
                "type": "slide",
                "axis": j_axis,
                "range": "0 .075",
                "damping": "5",
                "armature": ".01",
            },
        )
        ET.SubElement(
            b,
            "geom",
            {
                "name": f"{pad_name}_pad",
                "type": "box",
                "size": ".055 .01 .025",
                "mass": ".1",
                "friction": "5 .05 .002",
                "rgba": ".3 .3 .35 1",
            },
        )

    turn_carriage = ET.SubElement(turn_station, "body", {"name": "turn_carriage", "pos": "0 0 .50"})
    ET.SubElement(
        turn_carriage,
        "joint",
        {"name": "turn_z_joint", "type": "slide", "axis": "0 0 -1", "range": "0 .5", "damping": "5"},
    )
    ET.SubElement(
        turn_carriage,
        "inertial",
        {"pos": "0 0 0", "mass": ".1", "diaginertia": ".001 .001 .001"},
    )
    turn_rotor = ET.SubElement(turn_carriage, "body", {"name": "turn_rotor"})
    ET.SubElement(
        turn_rotor,
        "joint",
        {"name": "turn_rotor_joint", "type": "hinge", "axis": "0 0 1", "damping": ".15", "armature": ".002"},
    )
    ET.SubElement(
        turn_rotor,
        "geom",
        {
            "name": "rotor_hub",
            "type": "cylinder",
            "pos": "0 0 .15",
            "size": ".03 .02",
            "mass": ".1",
            "rgba": ".6 .3 .1 1",
        },
    )
    ct = "1" if top_turn_contact_enabled else "0"
    ca = "1" if top_turn_contact_enabled else "0"
    for pad_name, sign_x, j_axis in (("turn_pos", "0.11", "-1 0 0"), ("turn_neg", "-0.11", "1 0 0")):
        b = ET.SubElement(turn_rotor, "body", {"name": pad_name, "pos": f"{sign_x} 0 .045"})
        ET.SubElement(
            b,
            "joint",
            {
                "name": f"{pad_name}_joint",
                "type": "slide",
                "axis": j_axis,
                "range": "0 .055",
                "damping": "3",
            },
        )
        ET.SubElement(
            b,
            "geom",
            {
                "name": f"{pad_name}_pad",
                "type": "box",
                "size": ".01 .055 .012",
                "mass": ".05",
                "friction": "5 .02 .002",
                "rgba": ".6 .3 .1 1",
                "contype": ct,
                "conaffinity": ca,
            },
        )

    ET.SubElement(
        worldbody,
        "camera",
        {"name": "turn_overview", "pos": ".35 -1.1 1.15", "xyaxes": "1 0 0 0 .55 .83", "fovy": "40"},
    )

    station_actuators = [
        ("base_clear_ctrl", "base_clear_joint", "2000"),
        ("base_pos_ctrl", "base_pos_joint", "700"),
        ("base_neg_ctrl", "base_neg_joint", "700"),
        ("turn_pos_ctrl", "turn_pos_joint", "600"),
        ("turn_neg_ctrl", "turn_neg_joint", "600"),
        ("turn_z_ctrl", "turn_z_joint", "2000"),
        ("turn_rotor_ctrl", "turn_rotor_joint", "35"),
    ]
    for name, jnt, kp in station_actuators:
        ET.SubElement(actuator, "position", {"name": name, "joint": jnt, "kp": kp})

    return ET.tostring(root, encoding="unicode")


@dataclass
class PhysicalTurnResult:
    success: bool
    target_angle_rad: float
    actual_angle_rad: float
    top_axis_name: str
    top_cubie_indices: list[int]
    contact_driven: bool
    top_pad_contact_steps: int
    base_pad_contact_steps: int
    max_slice_misalignment_deg: float
    failure_code: str | None = None
    failure_reason: str | None = None
    preempted: bool = False
    chunk_status: str = ChunkStatus.COMPLETED.value
    telemetry: dict[str, Any] = field(default_factory=dict)


class Physical26CubeTurnExecutor:
    """Contact-driven single-top-fixture turn executor on 26 persistent rigid cubies.

    Physics integrity guarantees:
    - Top 9 cubies are identified strictly from 3D world positions (`geom_xpos`) when docked.
    - Weld switching anchors `relpose` from live measured `xquat` (zero snap / zero teleport).
    - Switching axes after an incomplete turn (> 8 deg off-lattice) fails as `SLICE_MISALIGNED_JAM`.
    - Top layer motion is driven 100% by friction/normal contact from `turn_{pos,neg}_pad`.
    - Never modifies sticker RGBA colors or calls `CubeEngine.apply_move`.
    """

    MISALIGNMENT_TOL_DEG = 8.0
    LATTICE_RECOVERY_TOL_DEG = 2.0

    def __init__(
        self,
        model: Any,
        data: Any,
        mujoco_mod: Any,
        *,
        record_ctrl_fn: Callable[[dict[str, float]], None] | None = None,
        post_step_fn: Callable[[], None] | None = None,
    ) -> None:
        self.model = model
        self.data = data
        self.mujoco = mujoco_mod
        self.record_ctrl_fn = record_ctrl_fn
        self.post_step_fn = post_step_fn

        self._rots_24 = [np.asarray(r, dtype=float) for r in cube_rotations_24()]
        self.cube_body = self._body("cube")
        self.cubie_bodies = [self._body(f"cubie_{k:02d}") for k in range(26)]
        self.cubie_geoms = [self._geom(f"cubie_geom_{k:02d}") for k in range(26)]
        self.carrier_bodies = {a: self._body(f"carrier_{a}") for a in AXIS_NAMES}
        self.carrier_qpos_adr = {
            a: int(self.model.jnt_qposadr[self._joint(f"carrier_{a}_joint")])
            for a in AXIS_NAMES
        }
        self.turn_rotor_qpos_adr = int(self.model.jnt_qposadr[self._joint("turn_rotor_joint")])
        self.w_core = [self._eq(f"w_core_{k:02d}") for k in range(26)]
        self.w_car = {
            (k, a): self._eq(f"w_car_{k:02d}_{a}")
            for k in range(26)
            for a in AXIS_NAMES
        }
        self._initial_eq_data = np.array(self.model.eq_data, copy=True)
        self.base_pos_pad = self._geom("base_pos_pad")
        self.base_neg_pad = self._geom("base_neg_pad")
        self.turn_pos_pad = self._geom("turn_pos_pad")
        self.turn_neg_pad = self._geom("turn_neg_pad")
        self._act_names = (
            "base_clear_ctrl",
            "base_pos_ctrl",
            "base_neg_ctrl",
            "turn_pos_ctrl",
            "turn_neg_ctrl",
            "turn_z_ctrl",
            "turn_rotor_ctrl",
        )
        self._acts = {n: self._act(n) for n in self._act_names}
        self.is_lattice_aligned: bool = True
        self.residual_slice_angle_rad: float = 0.0
        self.residual_slice_angle_deg: float = 0.0
        self.preempted_slice_axis: str | None = None
        self.preempted_top_cubie_indices: list[int] = []
        self._preturn_lattice_rots: dict[int, np.ndarray] = {}
        self._fixture_holding_preempted: bool = False

    def _body(self, name: str) -> int:
        gid = int(self.mujoco.mj_name2id(self.model, self.mujoco.mjtObj.mjOBJ_BODY, name))
        if gid < 0:
            raise KeyError(f"Missing MuJoCo body {name!r}")
        return gid

    def _geom(self, name: str) -> int:
        gid = int(self.mujoco.mj_name2id(self.model, self.mujoco.mjtObj.mjOBJ_GEOM, name))
        if gid < 0:
            raise KeyError(f"Missing MuJoCo geom {name!r}")
        return gid

    def _joint(self, name: str) -> int:
        jid = int(self.mujoco.mj_name2id(self.model, self.mujoco.mjtObj.mjOBJ_JOINT, name))
        if jid < 0:
            raise KeyError(f"Missing MuJoCo joint {name!r}")
        return jid

    def _eq(self, name: str) -> int:
        eid = int(self.mujoco.mj_name2id(self.model, self.mujoco.mjtObj.mjOBJ_EQUALITY, name))
        if eid < 0:
            raise KeyError(f"Missing MuJoCo equality {name!r}")
        return eid

    def _act(self, name: str) -> int:
        aid = int(self.mujoco.mj_name2id(self.model, self.mujoco.mjtObj.mjOBJ_ACTUATOR, name))
        if aid < 0:
            raise KeyError(f"Missing MuJoCo actuator {name!r}")
        return aid

    def _set_station_ctrl(self, values: dict[str, float]) -> None:
        for name, val in values.items():
            self.data.ctrl[self._acts[name]] = float(val)
        if self.record_ctrl_fn is not None:
            self.record_ctrl_fn(values)

    def _step_station(self, seconds: float, values: dict[str, float] | None = None) -> tuple[int, int]:
        if values:
            self._set_station_ctrl(values)
        steps = max(1, int(round(seconds / float(self.model.opt.timestep))))
        top_hits = 0
        base_hits = 0
        cubie_set = set(self.cubie_geoms)
        for _ in range(steps):
            self.mujoco.mj_step(self.model, self.data)
            t_pos, t_neg, b_pos, b_neg = self._pad_contact_flags(cubie_set)
            if t_pos and t_neg:
                top_hits += 1
            if b_pos and b_neg:
                base_hits += 1
            if self.post_step_fn is not None:
                self.post_step_fn()
        return top_hits, base_hits

    def _pad_contact_flags(self, cubie_set: set[int]) -> tuple[bool, bool, bool, bool]:
        t_pos = t_neg = b_pos = b_neg = False
        for c in self.data.contact[: self.data.ncon]:
            g1, g2 = int(c.geom1), int(c.geom2)
            if g1 not in cubie_set and g2 not in cubie_set:
                continue
            other = g2 if g1 in cubie_set else g1
            if other == self.turn_pos_pad:
                t_pos = True
            elif other == self.turn_neg_pad:
                t_neg = True
            elif other == self.base_pos_pad:
                b_pos = True
            elif other == self.base_neg_pad:
                b_neg = True
        return t_pos, t_neg, b_pos, b_neg

    def validate_lattice_alignment(
        self,
        *,
        tol_deg: float = MISALIGNMENT_TOL_DEG,
        active_world_axis: np.ndarray | None = None,
    ) -> tuple[bool, float, str | None]:
        """Verify all 26 cubies lie on 90° lattice orientations; catch >8° off-lattice slice jams."""
        r_cube = self.data.xmat[self.cube_body].reshape(3, 3)
        max_deg = 0.0
        for k in range(26):
            r_cubie = self.data.xmat[self.cubie_bodies[k]].reshape(3, 3)
            r_rel = r_cube.T @ r_cubie
            best_r24 = min(self._rots_24, key=lambda r24: _rotation_geodesic_rad(r_rel, r24))
            rel_err = best_r24.T @ r_rel
            err_axis_local, err_rad = _rotation_axis_angle(rel_err)
            err_deg = math.degrees(err_rad)
            max_deg = max(max_deg, err_deg)
            if err_deg > tol_deg:
                if active_world_axis is None:
                    return False, max_deg, f"Cubie {k} off 90 deg lattice by {err_deg:.2f} deg"
                err_axis_world = r_cube @ err_axis_local
                if abs(float(np.dot(err_axis_world, active_world_axis))) < 0.7:
                    return (
                        False,
                        max_deg,
                        f"Cross-axis interference: cubie {k} skewed {err_deg:.2f} deg off perpendicular slice",
                    )
        return True, max_deg, None

    def select_top_layer_from_world_coords(self) -> tuple[list[int], str, float]:
        """Identify the 9 top-layer cubies purely from live 3D world geom positions."""
        positions = np.array([self.data.geom_xpos[g].copy() for g in self.cubie_geoms], dtype=float)
        centroid = np.mean(positions, axis=0)
        z_offsets = positions[:, 2] - float(centroid[2])
        top_ids = [int(k) for k in range(26) if float(z_offsets[k]) > 0.020]
        if len(top_ids) != 9:
            raise RuntimeError(
                f"Expected 9 top-layer cubies by 3D height (>+20mm), found {len(top_ids)}: "
                f"z_offsets={[round(float(z), 4) for z in sorted(z_offsets)]}"
            )
        top_z_spread = float(np.ptp(positions[top_ids, 2]))
        if top_z_spread > 0.008:
            raise RuntimeError(
                f"Top 9 cubies are not coplanar (z spread={top_z_spread * 1000:.1f}mm > 8mm)"
            )
        r_cube = self.data.xmat[self.cube_body].reshape(3, 3)
        z_world = np.array([0.0, 0.0, 1.0], dtype=float)
        best_axis = max(
            AXIS_NAMES,
            key=lambda a: float(np.dot(r_cube @ np.asarray(FACE_FRAMES[a].normal, dtype=float), z_world)),
        )
        best_dot = float(
            np.dot(r_cube @ np.asarray(FACE_FRAMES[best_axis].normal, dtype=float), z_world)
        )
        return top_ids, best_axis, best_dot

    def reset_welds(self) -> None:
        """Restore initial core welds after episode reset (never call mid-episode)."""
        self.model.eq_data[:] = self._initial_eq_data
        for eid in self.w_core:
            self.data.eq_active[eid] = 1
        for eid in self.w_car.values():
            self.data.eq_active[eid] = 0
        self.is_lattice_aligned = True
        self.residual_slice_angle_rad = 0.0
        self.residual_slice_angle_deg = 0.0
        self.preempted_slice_axis = None
        self.preempted_top_cubie_indices = []
        self._preturn_lattice_rots = {}
        self._fixture_holding_preempted = False
        self.mujoco.mj_forward(self.model, self.data)

    @staticmethod
    def _orthogonal_basis(normal: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
        n = np.asarray(normal, dtype=float)
        n = n / max(float(np.linalg.norm(n)), 1e-12)
        ref = np.array([1.0, 0.0, 0.0], dtype=float) if abs(float(n[0])) < 0.9 else np.array([0.0, 1.0, 0.0], dtype=float)
        u = np.cross(ref, n)
        u = u / max(float(np.linalg.norm(u)), 1e-12)
        v = np.cross(n, u)
        v = v / max(float(np.linalg.norm(v)), 1e-12)
        return u, v

    def _snapshot_top_lattice_rots(self, top_ids: list[int]) -> dict[int, np.ndarray]:
        r_cube = self.data.xmat[self.cube_body].reshape(3, 3)
        snap: dict[int, np.ndarray] = {}
        for k in top_ids:
            r_rel = r_cube.T @ self.data.xmat[self.cubie_bodies[k]].reshape(3, 3)
            best_r24 = min(self._rots_24, key=lambda r24: _rotation_geodesic_rad(r_rel, r24))
            snap[int(k)] = best_r24.copy()
        return snap

    def _measure_signed_top_slice_angle_rad(self, top_ids: list[int], axis_name: str) -> float:
        r_cube = self.data.xmat[self.cube_body].reshape(3, 3)
        n_local = np.asarray(FACE_FRAMES[axis_name].normal, dtype=float)
        u, v = self._orthogonal_basis(n_local)
        sin_acc = 0.0
        cos_acc = 0.0
        count = 0
        for k in top_ids:
            r_ref = self._preturn_lattice_rots.get(int(k))
            r_rel = r_cube.T @ self.data.xmat[self.cubie_bodies[k]].reshape(3, 3)
            if r_ref is None:
                r_ref = min(self._rots_24, key=lambda r24: _rotation_geodesic_rad(r_rel, r24))
            d_r = r_rel @ r_ref.T
            cos_acc += 0.5 * (float(u @ (d_r @ u)) + float(v @ (d_r @ v)))
            sin_acc += 0.5 * (float(v @ (d_r @ u)) - float(u @ (d_r @ v)))
            count += 1
        if count == 0:
            return float(self.residual_slice_angle_rad)
        return float(math.atan2(sin_acc / count, cos_acc / count))

    def refresh_lattice_status(self, *, tol_deg: float = LATTICE_RECOVERY_TOL_DEG) -> tuple[bool, float]:
        """Re-measure live 26-cubie lattice alignment and synchronize state flags."""
        ok, max_deg, _ = self.validate_lattice_alignment(tol_deg=tol_deg)
        self.is_lattice_aligned = bool(ok)
        if ok:
            self.residual_slice_angle_rad = 0.0
            self.residual_slice_angle_deg = 0.0
            self.preempted_slice_axis = None
            self.preempted_top_cubie_indices = []
            self._preturn_lattice_rots = {}
            self._fixture_holding_preempted = False
        return bool(ok), float(max_deg)

    def _live_relpose_quat(self, body1_id: int, body2_id: int) -> np.ndarray:
        q1 = np.asarray(self.data.xquat[body1_id], dtype=float)
        q2 = np.asarray(self.data.xquat[body2_id], dtype=float)
        return _quat_mul(_quat_conj(q1), q2)

    def _switch_top_to_carrier(self, top_ids: list[int], axis_name: str) -> None:
        c_body = self.carrier_bodies[axis_name]
        for k in top_ids:
            q_rel = self._live_relpose_quat(c_body, self.cubie_bodies[k])
            eq_car = self.w_car[(k, axis_name)]
            self.model.eq_data[eq_car, 3:6] = 0.0
            self.model.eq_data[eq_car, 6:10] = q_rel
            self.data.eq_active[self.w_core[k]] = 0
            self.data.eq_active[eq_car] = 1
        self.mujoco.mj_forward(self.model, self.data)

    def _lock_top_to_core(self, top_ids: list[int], axis_name: str) -> None:
        for k in top_ids:
            q_rel = self._live_relpose_quat(self.cube_body, self.cubie_bodies[k])
            eq_core = self.w_core[k]
            self.model.eq_data[eq_core, 3:6] = 0.0
            self.model.eq_data[eq_core, 6:10] = q_rel
            self.data.eq_active[self.w_car[(k, axis_name)]] = 0
            self.data.eq_active[eq_core] = 1
        self.mujoco.mj_forward(self.model, self.data)

    def _release_top_fixture(self) -> None:
        self._step_station(0.22, {"turn_pos_ctrl": 0.0, "turn_neg_ctrl": 0.0})
        self._step_station(0.42, {"turn_z_ctrl": 0.0})
        self._step_station(0.28, {"turn_rotor_ctrl": 0.0})

    def release_base_clamp(self) -> None:
        self._step_station(0.20, {"base_pos_ctrl": 0.0, "base_neg_ctrl": 0.0})

    def execute_top_face_turn(
        self,
        target_angle_rad: float,
        *,
        contact_enabled: bool = True,
        token: CancellationToken | None = None,
        executor: ActionChunkExecutor | None = None,
        interrupt_after_rad: float | None = None,
        clamp_base: bool = True,
        release_base_after: bool = False,
        chunk_id: str | None = None,
    ) -> PhysicalTurnResult:
        """Clamp docked cube at station, release top 9 cubies to passive carrier, and drive ±90°/180° via friction pads."""
        if not self.is_lattice_aligned:
            _, live_mis_deg, _ = self.validate_lattice_alignment(tol_deg=self.MISALIGNMENT_TOL_DEG)
            return PhysicalTurnResult(
                success=False,
                target_angle_rad=target_angle_rad,
                actual_angle_rad=0.0,
                top_axis_name=self.preempted_slice_axis or "?",
                top_cubie_indices=list(self.preempted_top_cubie_indices),
                contact_driven=False,
                top_pad_contact_steps=0,
                base_pad_contact_steps=0,
                max_slice_misalignment_deg=max(live_mis_deg, abs(self.residual_slice_angle_deg)),
                failure_code="SLICE_MISALIGNED_JAM",
                failure_reason=(
                    f"Station slice misaligned ({self.residual_slice_angle_deg:+.2f} deg); "
                    "call recover_preempted_turn_slice before turning or switching axes"
                ),
                telemetry={
                    "is_lattice_aligned": False,
                    "residual_slice_angle_deg": round(self.residual_slice_angle_deg, 3),
                },
            )

        saved_turn_ct = (int(self.model.geom_contype[self.turn_pos_pad]), int(self.model.geom_contype[self.turn_neg_pad]))
        saved_turn_ca = (int(self.model.geom_conaffinity[self.turn_pos_pad]), int(self.model.geom_conaffinity[self.turn_neg_pad]))
        if not contact_enabled:
            self.model.geom_contype[self.turn_pos_pad] = 0
            self.model.geom_conaffinity[self.turn_pos_pad] = 0
            self.model.geom_contype[self.turn_neg_pad] = 0
            self.model.geom_conaffinity[self.turn_neg_pad] = 0

        top_ids: list[int] = []
        axis_name = "U"
        switched_to_carrier = False
        try:
            init_ctrl: dict[str, float] = {
                "base_clear_ctrl": 0.0,
                "turn_rotor_ctrl": 0.0,
                "turn_pos_ctrl": 0.0,
                "turn_neg_ctrl": 0.0,
                "turn_z_ctrl": 0.0,
            }
            self._step_station(0.08, init_ctrl)
            chunk_exec = executor or ActionChunkExecutor(
                self.model,
                self.data,
                record_command_fn=self.record_ctrl_fn,
                post_step_fn=(lambda _idx=0: (self.post_step_fn(), None)[1]) if self.post_step_fn else None,
            )
            dt_s = float(self.model.opt.timestep)
            if clamp_base:
                base_chunk = ActionChunk.linear_ramp(
                    chunk_id="base_clamp",
                    start={"base_pos_ctrl": 0.0, "base_neg_ctrl": 0.0},
                    goal={"base_pos_ctrl": 0.068, "base_neg_ctrl": 0.068},
                    steps=max(20, int(round(0.22 / dt_s))),
                    settle_steps=30,
                    dt=dt_s,
                )
                base_res = chunk_exec.execute(base_chunk, token=token)
                if base_res.status in (ChunkStatus.PREEMPTED_SAFE_HOLD, ChunkStatus.SAFETY_ABORTED):
                    if release_base_after:
                        self.release_base_clamp()
                    return PhysicalTurnResult(
                        success=False,
                        target_angle_rad=target_angle_rad,
                        actual_angle_rad=0.0,
                        top_axis_name=axis_name,
                        top_cubie_indices=[],
                        contact_driven=False,
                        top_pad_contact_steps=0,
                        base_pad_contact_steps=0,
                        max_slice_misalignment_deg=0.0,
                        failure_code="PREEMPTED",
                        failure_reason=base_res.cancel_reason or "Preempted before slice turn",
                        preempted=True,
                        chunk_status=base_res.status.value,
                        telemetry={
                            "interrupt_to_hold_sim_ms": base_res.interrupt_to_hold_sim_ms,
                            "interrupt_to_hold_wall_ms": (
                                round(max(0.0, (time.monotonic() - token.requested_at_wall_s) * 1000.0), 3)
                                if token is not None and token.requested_at_wall_s is not None
                                else None
                            ),
                        },
                    )
            tz_chunk = ActionChunk.linear_ramp(
                chunk_id="turn_z_lower",
                start={"turn_z_ctrl": float(self.data.ctrl[self._acts["turn_z_ctrl"]])},
                goal={"turn_z_ctrl": 0.50},
                steps=max(20, int(round(0.38 / dt_s))),
                settle_steps=40,
                dt=dt_s,
            )
            tz_res = chunk_exec.execute(tz_chunk, token=token)
            if tz_res.status in (ChunkStatus.PREEMPTED_SAFE_HOLD, ChunkStatus.SAFETY_ABORTED):
                self._release_top_fixture()
                if release_base_after:
                    self.release_base_clamp()
                return PhysicalTurnResult(
                    success=False,
                    target_angle_rad=target_angle_rad,
                    actual_angle_rad=0.0,
                    top_axis_name=axis_name,
                    top_cubie_indices=[],
                    contact_driven=False,
                    top_pad_contact_steps=0,
                    base_pad_contact_steps=0,
                    max_slice_misalignment_deg=0.0,
                    failure_code="PREEMPTED",
                    failure_reason=tz_res.cancel_reason or "Preempted during fixture lower",
                    preempted=True,
                    chunk_status=tz_res.status.value,
                    telemetry={
                        "interrupt_to_hold_sim_ms": tz_res.interrupt_to_hold_sim_ms,
                        "interrupt_to_hold_wall_ms": (
                            round(max(0.0, (time.monotonic() - token.requested_at_wall_s) * 1000.0), 3)
                            if token is not None and token.requested_at_wall_s is not None
                            else None
                        ),
                    },
                )

            try:
                top_ids, axis_name, axis_dot = self.select_top_layer_from_world_coords()
            except RuntimeError as exc:
                _, measured_mis, _ = self.validate_lattice_alignment(tol_deg=self.MISALIGNMENT_TOL_DEG)
                self.is_lattice_aligned = False
                self._release_top_fixture()
                if release_base_after:
                    self.release_base_clamp()
                return PhysicalTurnResult(
                    success=False,
                    target_angle_rad=target_angle_rad,
                    actual_angle_rad=0.0,
                    top_axis_name="?",
                    top_cubie_indices=[],
                    contact_driven=False,
                    top_pad_contact_steps=0,
                    base_pad_contact_steps=0,
                    max_slice_misalignment_deg=measured_mis,
                    failure_code="SLICE_MISALIGNED_JAM",
                    failure_reason=str(exc),
                )

            if axis_dot < 0.98:
                self._release_top_fixture()
                if release_base_after:
                    self.release_base_clamp()
                return PhysicalTurnResult(
                    success=False,
                    target_angle_rad=target_angle_rad,
                    actual_angle_rad=0.0,
                    top_axis_name=axis_name,
                    top_cubie_indices=top_ids,
                    contact_driven=False,
                    top_pad_contact_steps=0,
                    base_pad_contact_steps=0,
                    max_slice_misalignment_deg=999.0,
                    failure_code="FIXTURE_MISALIGNED",
                    failure_reason=f"Top face normal dot +Z={axis_dot:.3f} < 0.98",
                )

            r_cube = self.data.xmat[self.cube_body].reshape(3, 3)
            active_world_axis = r_cube @ np.asarray(FACE_FRAMES[axis_name].normal, dtype=float)
            ok_lattice, max_mis_deg, jam_reason = self.validate_lattice_alignment(
                tol_deg=self.MISALIGNMENT_TOL_DEG,
                active_world_axis=active_world_axis,
            )
            if not ok_lattice:
                self.is_lattice_aligned = False
                self._release_top_fixture()
                if release_base_after:
                    self.release_base_clamp()
                return PhysicalTurnResult(
                    success=False,
                    target_angle_rad=target_angle_rad,
                    actual_angle_rad=0.0,
                    top_axis_name=axis_name,
                    top_cubie_indices=top_ids,
                    contact_driven=False,
                    top_pad_contact_steps=0,
                    base_pad_contact_steps=0,
                    max_slice_misalignment_deg=max_mis_deg,
                    failure_code="SLICE_MISALIGNED_JAM",
                    failure_reason=jam_reason,
                )

            # Smoothly clamp top layer with turn_pos/neg pads
            t_clamp = 0
            b_clamp = 0
            cubie_set = set(self.cubie_geoms)

            def _track_clamp(_step_idx: int = 0) -> None:
                nonlocal t_clamp, b_clamp
                tp, tn, bp, bn = self._pad_contact_flags(cubie_set)
                if tp and tn:
                    t_clamp += 1
                if bp and bn:
                    b_clamp += 1
                if self.post_step_fn is not None:
                    self.post_step_fn()
                return None

            clamp_chunk = ActionChunk.linear_ramp(
                chunk_id="turn_clamp",
                start={"turn_pos_ctrl": 0.0, "turn_neg_ctrl": 0.0},
                goal={"turn_pos_ctrl": 0.052, "turn_neg_ctrl": 0.052},
                steps=max(20, int(round(0.20 / dt_s))),
                settle_steps=30,
                dt=dt_s,
            )
            clamp_res = chunk_exec.execute(clamp_chunk, token=token, post_step_fn=_track_clamp)
            if clamp_res.status in (ChunkStatus.PREEMPTED_SAFE_HOLD, ChunkStatus.SAFETY_ABORTED):
                self._release_top_fixture()
                if release_base_after:
                    self.release_base_clamp()
                return PhysicalTurnResult(
                    success=False,
                    target_angle_rad=target_angle_rad,
                    actual_angle_rad=0.0,
                    top_axis_name=axis_name,
                    top_cubie_indices=top_ids,
                    contact_driven=False,
                    top_pad_contact_steps=t_clamp,
                    base_pad_contact_steps=b_clamp,
                    max_slice_misalignment_deg=0.0,
                    failure_code="PREEMPTED",
                    failure_reason=clamp_res.cancel_reason or "Preempted during top clamp",
                    preempted=True,
                    chunk_status=clamp_res.status.value,
                    telemetry={
                        "interrupt_to_hold_sim_ms": clamp_res.interrupt_to_hold_sim_ms,
                        "interrupt_to_hold_wall_ms": (
                            round(max(0.0, (time.monotonic() - token.requested_at_wall_s) * 1000.0), 3)
                            if token is not None and token.requested_at_wall_s is not None
                            else None
                        ),
                    },
                )

            self._preturn_lattice_rots = self._snapshot_top_lattice_rots(top_ids)
            theta0 = float(self.data.qpos[self.carrier_qpos_adr[axis_name]])
            self._switch_top_to_carrier(top_ids, axis_name)
            switched_to_carrier = True

            sweep_target = float(interrupt_after_rad) if interrupt_after_rad is not None else float(target_angle_rad)
            duration_s = 1.25 if abs(sweep_target) <= 1.75 else 2.25
            if interrupt_after_rad is not None:
                duration_s = max(0.35, 1.25 * (abs(sweep_target) / (math.pi * 0.5)))

            n_wp = max(20, int(round(duration_s / dt_s)))
            chunk = ActionChunk.linear_ramp(
                chunk_id=chunk_id or f"turn_rotor_{axis_name}",
                start={"turn_rotor_ctrl": 0.0},
                goal={"turn_rotor_ctrl": sweep_target},
                steps=n_wp,
                settle_steps=25,
                dt=dt_s,
                source_type="CLASSICAL_SKILL",
            )

            spin_top_hits = 0
            spin_base_hits = 0

            def _track_contacts(_step_idx: int = 0) -> None:
                nonlocal spin_top_hits, spin_base_hits
                tp, tn, bp, bn = self._pad_contact_flags(cubie_set)
                if tp and tn:
                    spin_top_hits += 1
                if bp and bn:
                    spin_base_hits += 1
                if self.post_step_fn is not None:
                    self.post_step_fn()
                return None

            exec_res = chunk_exec.execute(chunk, token=token, post_step_fn=_track_contacts)

            if exec_res.status in (ChunkStatus.PREEMPTED_SAFE_HOLD, ChunkStatus.SAFETY_ABORTED):
                self._lock_top_to_core(top_ids, axis_name)
                switched_to_carrier = False
                rotor_hold = float(self.data.qpos[self.turn_rotor_qpos_adr])
                self._set_station_ctrl({"turn_rotor_ctrl": rotor_hold})
                actual_rad = float(self.data.qpos[self.carrier_qpos_adr[axis_name]] - theta0)
                signed_rad = self._measure_signed_top_slice_angle_rad(top_ids, axis_name)
                ok_lat, mis_deg, _ = self.validate_lattice_alignment(tol_deg=self.LATTICE_RECOVERY_TOL_DEG)
                misaligned = bool(
                    not ok_lat
                    or mis_deg >= self.LATTICE_RECOVERY_TOL_DEG
                    or abs(math.degrees(signed_rad)) >= self.LATTICE_RECOVERY_TOL_DEG
                )
                if misaligned:
                    self.is_lattice_aligned = False
                    self.residual_slice_angle_rad = float(signed_rad)
                    self.residual_slice_angle_deg = float(math.degrees(signed_rad))
                    self.preempted_slice_axis = axis_name
                    self.preempted_top_cubie_indices = list(top_ids)
                    self._fixture_holding_preempted = True
                    # Hold fixture safely until recover_preempted_turn_slice restores alignment.
                else:
                    self.is_lattice_aligned = True
                    self.residual_slice_angle_rad = 0.0
                    self.residual_slice_angle_deg = 0.0
                    self.preempted_slice_axis = None
                    self.preempted_top_cubie_indices = []
                    self._preturn_lattice_rots = {}
                    self._fixture_holding_preempted = False
                    self._release_top_fixture()
                    if release_base_after:
                        self.release_base_clamp()
                return PhysicalTurnResult(
                    success=False,
                    target_angle_rad=target_angle_rad,
                    actual_angle_rad=actual_rad,
                    top_axis_name=axis_name,
                    top_cubie_indices=top_ids,
                    contact_driven=spin_top_hits > 0,
                    top_pad_contact_steps=spin_top_hits + t_clamp,
                    base_pad_contact_steps=spin_base_hits + b_clamp,
                    max_slice_misalignment_deg=max(mis_deg, abs(math.degrees(signed_rad))),
                    failure_code="PREEMPTED",
                    failure_reason=exec_res.cancel_reason or "Preempted by CancellationToken",
                    preempted=True,
                    chunk_status=exec_res.status.value,
                    telemetry={
                        "is_lattice_aligned": self.is_lattice_aligned,
                        "residual_slice_angle_deg": round(self.residual_slice_angle_deg, 3),
                        "residual_slice_angle_rad": float(self.residual_slice_angle_rad),
                        "fixture_holding": self._fixture_holding_preempted,
                        "axis": axis_name,
                        "interrupt_to_hold_sim_ms": exec_res.interrupt_to_hold_sim_ms,
                        "interrupt_to_hold_wall_ms": (
                            round(max(0.0, (time.monotonic() - token.requested_at_wall_s) * 1000.0), 3)
                            if token is not None and token.requested_at_wall_s is not None
                            else None
                        ),
                    },
                )

            # Settle briefly at target rotor angle before live-relocking to cube_core
            t_set, b_set = self._step_station(0.28)
            actual_rad = float(self.data.qpos[self.carrier_qpos_adr[axis_name]] - theta0)

            self._lock_top_to_core(top_ids, axis_name)
            switched_to_carrier = False
            self._release_top_fixture()
            if release_base_after:
                self.release_base_clamp()

            ok_final, final_mis_deg, _ = self.validate_lattice_alignment(tol_deg=self.MISALIGNMENT_TOL_DEG)
            err_rad = abs(actual_rad - target_angle_rad)
            contact_ok = spin_top_hits > 0
            angle_ok = err_rad <= math.radians(self.MISALIGNMENT_TOL_DEG) and interrupt_after_rad is None

            if (not ok_final) or final_mis_deg >= self.LATTICE_RECOVERY_TOL_DEG or (
                interrupt_after_rad is not None and abs(math.degrees(actual_rad)) >= self.LATTICE_RECOVERY_TOL_DEG
            ):
                signed_rad = self._measure_signed_top_slice_angle_rad(top_ids, axis_name)
                self.is_lattice_aligned = False
                self.residual_slice_angle_rad = float(signed_rad)
                self.residual_slice_angle_deg = float(math.degrees(signed_rad))
                self.preempted_slice_axis = axis_name
                self.preempted_top_cubie_indices = list(top_ids)
            else:
                self.is_lattice_aligned = True
                self.residual_slice_angle_rad = 0.0
                self.residual_slice_angle_deg = 0.0
                self.preempted_slice_axis = None
                self.preempted_top_cubie_indices = []
                self._preturn_lattice_rots = {}
            self._fixture_holding_preempted = False

            failure_code = None
            failure_reason = None
            if not contact_ok:
                failure_code = "CONTACT_DRIVE_FAILED"
                failure_reason = (
                    f"Top fixture pads had no bilateral contact (top_hits={spin_top_hits}); "
                    f"actual_deg={math.degrees(actual_rad):.2f}"
                )
            elif not angle_ok:
                failure_code = "SLICE_TURN_INCOMPLETE"
                failure_reason = (
                    f"Top layer reached {math.degrees(actual_rad):.2f} deg vs target "
                    f"{math.degrees(target_angle_rad):.2f} deg (err={math.degrees(err_rad):.2f} deg)"
                )

            return PhysicalTurnResult(
                success=bool(contact_ok and angle_ok),
                target_angle_rad=target_angle_rad,
                actual_angle_rad=actual_rad,
                top_axis_name=axis_name,
                top_cubie_indices=top_ids,
                contact_driven=contact_ok,
                top_pad_contact_steps=spin_top_hits + t_clamp + t_set,
                base_pad_contact_steps=spin_base_hits + b_clamp + b_set,
                max_slice_misalignment_deg=final_mis_deg,
                failure_code=failure_code,
                failure_reason=failure_reason,
                chunk_status=exec_res.status.value,
                telemetry={
                    "target_deg": round(math.degrees(target_angle_rad), 3),
                    "actual_deg": round(math.degrees(actual_rad), 3),
                    "error_deg": round(math.degrees(err_rad), 3),
                    "top_cubies": list(top_ids),
                    "axis": axis_name,
                    "is_lattice_aligned": self.is_lattice_aligned,
                    "residual_slice_angle_deg": round(self.residual_slice_angle_deg, 3),
                },
            )
        finally:
            if switched_to_carrier and top_ids:
                self._lock_top_to_core(top_ids, axis_name)
            self.model.geom_contype[self.turn_pos_pad] = saved_turn_ct[0]
            self.model.geom_contype[self.turn_neg_pad] = saved_turn_ct[1]
            self.model.geom_conaffinity[self.turn_pos_pad] = saved_turn_ca[0]
            self.model.geom_conaffinity[self.turn_neg_pad] = saved_turn_ca[1]

    def recover_preempted_turn_slice(
        self,
        mode: Literal["UNWIND_TO_ZERO", "ALIGN_NEAREST_DETENT"] = "UNWIND_TO_ZERO",
        *,
        release_base_after: bool = True,
        executor: ActionChunkExecutor | None = None,
        chunk_id: str | None = None,
    ) -> PhysicalTurnResult:
        """Recover a preempted off-lattice top slice 100% via contact pad torque.

        Never writes cube qpos or snaps cubie poses. Measures residual slice angle,
        aligns/engages the top & base fixture pads if not already holding, drives
        contact friction torque back to 0 deg (`UNWIND_TO_ZERO`) or nearest 90 deg
        lattice detent (`ALIGN_NEAREST_DETENT`), re-locks to `cube_core`, verifies
        `validate_lattice_alignment(tol_deg=8.0)` with residual < 2.0 deg, and
        only then releases the fixture clamps.
        """
        if mode not in ("UNWIND_TO_ZERO", "ALIGN_NEAREST_DETENT"):
            raise ValueError(f"Unsupported recovery mode: {mode!r}")

        ok_now, mis_now, _ = self.validate_lattice_alignment(tol_deg=self.LATTICE_RECOVERY_TOL_DEG)
        if self.is_lattice_aligned and ok_now and mis_now < self.LATTICE_RECOVERY_TOL_DEG:
            if self._fixture_holding_preempted:
                self._release_top_fixture()
                if release_base_after:
                    self.release_base_clamp()
            self._fixture_holding_preempted = False
            self.residual_slice_angle_rad = 0.0
            self.residual_slice_angle_deg = 0.0
            return PhysicalTurnResult(
                success=True,
                target_angle_rad=0.0,
                actual_angle_rad=0.0,
                top_axis_name=self.preempted_slice_axis or "U",
                top_cubie_indices=[],
                contact_driven=False,
                top_pad_contact_steps=0,
                base_pad_contact_steps=0,
                max_slice_misalignment_deg=mis_now,
                telemetry={"mode": mode, "already_aligned": True, "is_lattice_aligned": True},
            )

        try:
            top_ids, axis_name, axis_dot = self.select_top_layer_from_world_coords()
        except RuntimeError as exc:
            _, measured_mis, _ = self.validate_lattice_alignment(tol_deg=self.MISALIGNMENT_TOL_DEG)
            return PhysicalTurnResult(
                success=False,
                target_angle_rad=0.0,
                actual_angle_rad=0.0,
                top_axis_name=self.preempted_slice_axis or "?",
                top_cubie_indices=[],
                contact_driven=False,
                top_pad_contact_steps=0,
                base_pad_contact_steps=0,
                max_slice_misalignment_deg=measured_mis,
                failure_code="SLICE_MISALIGNED_JAM",
                failure_reason=str(exc),
                telemetry={"mode": mode, "is_lattice_aligned": False},
            )

        if axis_dot < 0.98:
            return PhysicalTurnResult(
                success=False,
                target_angle_rad=0.0,
                actual_angle_rad=0.0,
                top_axis_name=axis_name,
                top_cubie_indices=top_ids,
                contact_driven=False,
                top_pad_contact_steps=0,
                base_pad_contact_steps=0,
                max_slice_misalignment_deg=999.0,
                failure_code="FIXTURE_MISALIGNED",
                failure_reason=f"Top face normal dot +Z={axis_dot:.3f} < 0.98",
                telemetry={"mode": mode, "is_lattice_aligned": False},
            )

        alpha_rad = self._measure_signed_top_slice_angle_rad(top_ids, axis_name)
        if mode == "UNWIND_TO_ZERO":
            target_alpha_rad = 0.0
        else:
            target_alpha_rad = float(round(alpha_rad / (math.pi * 0.5)) * (math.pi * 0.5))
        delta_target_rad = float(target_alpha_rad - alpha_rad)

        chunk_exec = executor or ActionChunkExecutor(
            self.model,
            self.data,
            record_command_fn=self.record_ctrl_fn,
            post_step_fn=(lambda _idx=0: (self.post_step_fn(), None)[1]) if self.post_step_fn else None,
        )
        dt_s = float(self.model.opt.timestep)
        cubie_set = set(self.cubie_geoms)

        rotor_now = float(self.data.qpos[self.turn_rotor_qpos_adr])
        rotor_diff = float((rotor_now - alpha_rad + math.pi) % (2.0 * math.pi) - math.pi)
        tp0, tn0, bp0, bn0 = self._pad_contact_flags(cubie_set)
        already_holding = bool(
            float(self.data.ctrl[self._acts["turn_z_ctrl"]]) >= 0.45
            and float(self.data.ctrl[self._acts["turn_pos_ctrl"]]) >= 0.04
            and float(self.data.ctrl[self._acts["turn_neg_ctrl"]]) >= 0.04
            and float(self.data.ctrl[self._acts["base_pos_ctrl"]]) >= 0.055
            and float(self.data.ctrl[self._acts["base_neg_ctrl"]]) >= 0.055
            and tp0
            and tn0
            and bp0
            and bn0
            and abs(rotor_diff) < math.radians(8.0)
        )

        t_clamp = 0
        b_clamp = 0
        if not already_holding:
            self._step_station(0.18, {"turn_pos_ctrl": 0.0, "turn_neg_ctrl": 0.0})
            self._step_station(0.38, {"turn_z_ctrl": 0.0, "base_clear_ctrl": 0.0})
            base_chunk = ActionChunk.linear_ramp(
                chunk_id="recover_base_clamp",
                start={
                    "base_pos_ctrl": float(self.data.ctrl[self._acts["base_pos_ctrl"]]),
                    "base_neg_ctrl": float(self.data.ctrl[self._acts["base_neg_ctrl"]]),
                },
                goal={"base_pos_ctrl": 0.068, "base_neg_ctrl": 0.068},
                steps=max(20, int(round(0.22 / dt_s))),
                settle_steps=30,
                dt=dt_s,
            )
            chunk_exec.execute(base_chunk)

            # Align open rotor jaws above the cube to match the skewed top slice angle
            align_rotor_chunk = ActionChunk.linear_ramp(
                chunk_id="recover_align_rotor",
                start={"turn_rotor_ctrl": float(self.data.ctrl[self._acts["turn_rotor_ctrl"]])},
                goal={"turn_rotor_ctrl": alpha_rad},
                steps=max(20, int(round(0.35 / dt_s))),
                settle_steps=20,
                dt=dt_s,
            )
            chunk_exec.execute(align_rotor_chunk)

            tz_chunk = ActionChunk.linear_ramp(
                chunk_id="recover_turn_z_lower",
                start={"turn_z_ctrl": float(self.data.ctrl[self._acts["turn_z_ctrl"]])},
                goal={"turn_z_ctrl": 0.50},
                steps=max(20, int(round(0.38 / dt_s))),
                settle_steps=40,
                dt=dt_s,
            )
            chunk_exec.execute(tz_chunk)

            def _track_recover_clamp(_step_idx: int = 0) -> None:
                nonlocal t_clamp, b_clamp
                tp, tn, bp, bn = self._pad_contact_flags(cubie_set)
                if tp and tn:
                    t_clamp += 1
                if bp and bn:
                    b_clamp += 1
                if self.post_step_fn is not None:
                    self.post_step_fn()
                return None

            clamp_chunk = ActionChunk.linear_ramp(
                chunk_id="recover_turn_clamp",
                start={"turn_pos_ctrl": 0.0, "turn_neg_ctrl": 0.0},
                goal={"turn_pos_ctrl": 0.052, "turn_neg_ctrl": 0.052},
                steps=max(20, int(round(0.20 / dt_s))),
                settle_steps=30,
                dt=dt_s,
            )
            chunk_exec.execute(clamp_chunk, post_step_fn=_track_recover_clamp)

        rotor_start = float(self.data.qpos[self.turn_rotor_qpos_adr])
        rotor_goal = float(rotor_start + delta_target_rad)
        theta0 = float(self.data.qpos[self.carrier_qpos_adr[axis_name]])
        switched_to_carrier = False
        spin_top_hits = 0
        spin_base_hits = 0

        try:
            self._switch_top_to_carrier(top_ids, axis_name)
            switched_to_carrier = True

            duration_s = max(0.45, 1.25 * (abs(delta_target_rad) / (math.pi * 0.5)))
            n_wp = max(20, int(round(duration_s / dt_s)))
            recover_chunk = ActionChunk.linear_ramp(
                chunk_id=chunk_id or f"recover_slice_{mode.lower()}_{axis_name}",
                start={"turn_rotor_ctrl": float(self.data.ctrl[self._acts["turn_rotor_ctrl"]])},
                goal={"turn_rotor_ctrl": rotor_goal},
                steps=n_wp,
                settle_steps=30,
                dt=dt_s,
            )

            def _track_recover_contacts(_step_idx: int = 0) -> None:
                nonlocal spin_top_hits, spin_base_hits
                tp, tn, bp, bn = self._pad_contact_flags(cubie_set)
                if tp and tn:
                    spin_top_hits += 1
                if bp and bn:
                    spin_base_hits += 1
                if self.post_step_fn is not None:
                    self.post_step_fn()
                return None

            exec_res = chunk_exec.execute(recover_chunk, post_step_fn=_track_recover_contacts)
            t_set, b_set = self._step_station(0.28)
            actual_delta_rad = float(self.data.qpos[self.carrier_qpos_adr[axis_name]] - theta0)

            self._lock_top_to_core(top_ids, axis_name)
            switched_to_carrier = False
        finally:
            if switched_to_carrier and top_ids:
                self._lock_top_to_core(top_ids, axis_name)

        # Re-validate lattice alignment strictly BEFORE releasing clamps
        r_cube = self.data.xmat[self.cube_body].reshape(3, 3)
        active_world_axis = r_cube @ np.asarray(FACE_FRAMES[axis_name].normal, dtype=float)
        ok_lat_8, final_mis_deg, jam_reason = self.validate_lattice_alignment(
            tol_deg=self.MISALIGNMENT_TOL_DEG,
            active_world_axis=active_world_axis,
        )
        residual_after_rad = self._measure_signed_top_slice_angle_rad(top_ids, axis_name) - target_alpha_rad
        contact_ok = spin_top_hits > 0 or abs(delta_target_rad) < math.radians(1.0)
        aligned_ok = bool(ok_lat_8 and final_mis_deg < self.LATTICE_RECOVERY_TOL_DEG)

        if aligned_ok and contact_ok:
            self.is_lattice_aligned = True
            self.residual_slice_angle_rad = float(residual_after_rad)
            self.residual_slice_angle_deg = float(math.degrees(residual_after_rad))
            self.preempted_slice_axis = None
            self.preempted_top_cubie_indices = []
            self._preturn_lattice_rots = {}
            self._fixture_holding_preempted = False
            self._release_top_fixture()
            if release_base_after:
                self.release_base_clamp()
            failure_code = None
            failure_reason = None
        else:
            self.is_lattice_aligned = False
            self.residual_slice_angle_rad = float(residual_after_rad)
            self.residual_slice_angle_deg = float(math.degrees(residual_after_rad))
            self._fixture_holding_preempted = True
            failure_code = "CONTACT_DRIVE_FAILED" if not contact_ok else "SLICE_RECOVERY_FAILED"
            failure_reason = jam_reason or (
                f"Recovery residual={final_mis_deg:.2f} deg (tol < {self.LATTICE_RECOVERY_TOL_DEG:.1f} deg), "
                f"spin_top_hits={spin_top_hits}"
            )

        return PhysicalTurnResult(
            success=bool(aligned_ok and contact_ok),
            target_angle_rad=delta_target_rad,
            actual_angle_rad=actual_delta_rad,
            top_axis_name=axis_name,
            top_cubie_indices=top_ids,
            contact_driven=bool(spin_top_hits > 0),
            top_pad_contact_steps=spin_top_hits + t_clamp + t_set,
            base_pad_contact_steps=spin_base_hits + b_clamp + b_set,
            max_slice_misalignment_deg=final_mis_deg,
            failure_code=failure_code,
            failure_reason=failure_reason,
            chunk_status=exec_res.status.value,
            telemetry={
                "mode": mode,
                "initial_residual_deg": round(math.degrees(alpha_rad), 3),
                "target_alpha_deg": round(math.degrees(target_alpha_rad), 3),
                "delta_target_deg": round(math.degrees(delta_target_rad), 3),
                "actual_delta_deg": round(math.degrees(actual_delta_rad), 3),
                "final_misalignment_deg": round(final_mis_deg, 3),
                "is_lattice_aligned": self.is_lattice_aligned,
                "already_holding_at_preempt": already_holding,
            },
        )

    def select_face_layer_from_local_coords(self, axis_name: str) -> list[int]:
        """Identify the 9 cubies belonging to logical face `axis_name` from 3D world coords."""
        if axis_name not in AXIS_NAMES:
            raise ValueError(f"Unsupported face axis: {axis_name!r}")
        c_pos = np.asarray(self.data.xpos[self.cube_body], dtype=float)
        r_cube = np.asarray(self.data.xmat[self.cube_body], dtype=float).reshape(3, 3)
        n_local = np.asarray(FACE_FRAMES[axis_name].normal, dtype=float)
        layer_ids: list[int] = []
        for k in range(26):
            p_local = r_cube.T @ (np.asarray(self.data.geom_xpos[self.cubie_geoms[k]], dtype=float) - c_pos)
            if float(np.dot(p_local, n_local)) > 0.020:
                layer_ids.append(k)
        if len(layer_ids) != 9:
            raise RuntimeError(f"Expected 9 cubies on face {axis_name}, found {len(layer_ids)}: {layer_ids}")
        return layer_ids

    def execute_human_layer_turn(
        self,
        move: str,
        *,
        duration_s: float = 0.25,
        frame_callback: Callable[[int, int], None] | None = None,
    ) -> PhysicalTurnResult:
        """Physically rotate any of the 18 cube faces on the 26-cubie entity for a human turn.

        Briefly lifts and supports the cube above the tabletop in a virtual human hold,
        switches the target face's 9 cubies onto `carrier_{axis}`, drives smooth hinge
        motion via physics stepping without altering sticker RGBA, re-anchors `w_core`
        welds from live `xquat`, and settles back onto the table under gravity.
        """
        mv = str(move).strip()
        if mv not in LEGAL_MOVES:
            raise ValueError(f"Illegal Rubik's cube move: {move!r}")
        if not self.is_lattice_aligned:
            _, live_mis_deg, _ = self.validate_lattice_alignment(tol_deg=self.MISALIGNMENT_TOL_DEG)
            return PhysicalTurnResult(
                success=False,
                target_angle_rad=move_to_top_fixture_angle_rad(mv),
                actual_angle_rad=0.0,
                top_axis_name=mv[0],
                top_cubie_indices=[],
                contact_driven=False,
                top_pad_contact_steps=0,
                base_pad_contact_steps=0,
                max_slice_misalignment_deg=max(live_mis_deg, abs(self.residual_slice_angle_deg)),
                failure_code="SLICE_MISALIGNED_JAM",
                failure_reason="Cube lattice is misaligned before human move",
            )

        axis_name = mv[0]
        target_angle_rad = move_to_top_fixture_angle_rad(mv)
        layer_ids = self.select_face_layer_from_local_coords(axis_name)
        dt_s = float(self.model.opt.timestep)
        cube_jnt = self._joint("cube_free")
        cube_dof = int(self.model.jnt_dofadr[cube_jnt])
        car_jnt = self._joint(f"carrier_{axis_name}_joint")
        car_dof = int(self.model.jnt_dofadr[car_jnt])
        car_qadr = self.carrier_qpos_adr[axis_name]

        c_pos0 = np.asarray(self.data.xpos[self.cube_body], dtype=float).copy()
        r_hold = np.asarray(self.data.xmat[self.cube_body], dtype=float).reshape(3, 3).copy()
        x0, y0, z0 = float(c_pos0[0]), float(c_pos0[1]), float(c_pos0[2])
        z_hold = max(z0, 0.660) + 0.036
        total_mass = 0.012 + 26.0 * 0.003

        def _hold_core(target_z: float) -> None:
            pos = np.asarray(self.data.xpos[self.cube_body], dtype=float)
            r_cur = np.asarray(self.data.xmat[self.cube_body], dtype=float).reshape(3, 3)
            v_lin = np.asarray(self.data.qvel[cube_dof : cube_dof + 3], dtype=float)
            omega_w = r_cur @ np.asarray(self.data.qvel[cube_dof + 3 : cube_dof + 6], dtype=float)
            pos_err = np.array([x0 - float(pos[0]), y0 - float(pos[1]), target_z - float(pos[2])], dtype=float)
            f_world = np.array([0.0, 0.0, total_mass * 9.81], dtype=float) + 180.0 * pos_err - 8.5 * v_lin
            r_err = r_hold @ r_cur.T
            rot_vec = 0.5 * np.array(
                [
                    r_err[2, 1] - r_err[1, 2],
                    r_err[0, 2] - r_err[2, 0],
                    r_err[1, 0] - r_err[0, 1],
                ],
                dtype=float,
            )
            tau_world = 4.5 * rot_vec - 0.16 * omega_w
            self.data.xfrc_applied[self.cube_body, :3] = f_world
            self.data.xfrc_applied[self.cube_body, 3:6] = tau_world

        switched_to_carrier = False
        try:
            # 1. Smoothly lift cube clear of table surface for collision-free face rotation
            lift_steps = max(16, int(round(0.04 / dt_s)))
            for s in range(1, lift_steps + 1):
                u = float(s) / float(lift_steps)
                tz = z0 + (z_hold - z0) * (3.0 * u * u - 2.0 * u * u * u)
                _hold_core(tz)
                self.mujoco.mj_step(self.model, self.data)
                if self.post_step_fn is not None:
                    self.post_step_fn()

            # 2. Switch the 9 face cubies to carrier_{axis} and rotate smoothly over duration_s
            self._preturn_lattice_rots = self._snapshot_top_lattice_rots(layer_ids)
            theta0 = float(self.data.qpos[car_qadr])
            self._switch_top_to_carrier(layer_ids, axis_name)
            switched_to_carrier = True

            eff_dur = float(duration_s) if abs(target_angle_rad) <= 1.75 else max(float(duration_s), 0.30)
            turn_steps = max(40, int(round(eff_dur / dt_s)))
            settle_steps = max(18, int(round(0.04 / dt_s)))
            total_anim = turn_steps + settle_steps
            checkpoint_steps = {
                max(1, int(round(turn_steps * 0.25))),
                max(1, int(round(turn_steps * 0.50))),
                max(1, int(round(turn_steps * 0.75))),
                turn_steps,
            }

            for s in range(1, total_anim + 1):
                if s <= turn_steps:
                    u = float(s) / float(turn_steps)
                    theta_ref = target_angle_rad * (3.0 * u * u - 2.0 * u * u * u)
                else:
                    theta_ref = target_angle_rad
                theta_rel = float(self.data.qpos[car_qadr] - theta0)
                omega_car = float(self.data.qvel[car_dof])
                self.data.qfrc_applied[car_dof] = 3.2 * (theta_ref - theta_rel) - 0.08 * omega_car
                _hold_core(z_hold)
                self.mujoco.mj_step(self.model, self.data)
                if self.post_step_fn is not None:
                    self.post_step_fn()
                if frame_callback is not None and s in checkpoint_steps:
                    frame_callback(s, total_anim)

            actual_rad = float(self.data.qpos[car_qadr] - theta0)
            self.data.qfrc_applied[car_dof] = 0.0
            self._lock_top_to_core(layer_ids, axis_name)
            switched_to_carrier = False

            # 3. Lower gently back to tabletop and settle under gravity with zero external forces
            lower_steps = max(16, int(round(0.04 / dt_s)))
            for s in range(1, lower_steps + 1):
                u = float(s) / float(lower_steps)
                tz = z_hold + (z0 + 0.002 - z_hold) * (3.0 * u * u - 2.0 * u * u * u)
                _hold_core(tz)
                self.mujoco.mj_step(self.model, self.data)
                if self.post_step_fn is not None:
                    self.post_step_fn()

            self.data.xfrc_applied[self.cube_body] = 0.0
            self.data.qfrc_applied[:] = 0.0
            for _ in range(max(20, int(round(0.06 / dt_s)))):
                self.mujoco.mj_step(self.model, self.data)
                if self.post_step_fn is not None:
                    self.post_step_fn()
        finally:
            self.data.xfrc_applied[self.cube_body] = 0.0
            self.data.qfrc_applied[:] = 0.0
            if switched_to_carrier and layer_ids:
                self._lock_top_to_core(layer_ids, axis_name)

        ok_lat, final_mis_deg = self.refresh_lattice_status(tol_deg=self.LATTICE_RECOVERY_TOL_DEG)
        err_rad = abs(actual_rad - target_angle_rad)
        angle_ok = err_rad <= math.radians(self.MISALIGNMENT_TOL_DEG)
        success = bool(ok_lat and angle_ok)
        return PhysicalTurnResult(
            success=success,
            target_angle_rad=target_angle_rad,
            actual_angle_rad=actual_rad,
            top_axis_name=axis_name,
            top_cubie_indices=layer_ids,
            contact_driven=False,
            top_pad_contact_steps=0,
            base_pad_contact_steps=0,
            max_slice_misalignment_deg=final_mis_deg,
            failure_code=None if success else "HUMAN_TURN_MISALIGNED",
            failure_reason=None if success else f"misalignment={final_mis_deg:.2f} deg, angle_err={math.degrees(err_rad):.2f} deg",
            telemetry={
                "move": mv,
                "axis": axis_name,
                "target_deg": round(math.degrees(target_angle_rad), 3),
                "actual_deg": round(math.degrees(actual_rad), 3),
                "error_deg": round(math.degrees(err_rad), 3),
                "max_slice_misalignment_deg": round(final_mis_deg, 3),
                "is_lattice_aligned": self.is_lattice_aligned,
            },
        )


def extract_54_geom_facelets_state(
    model: Any,
    data: Any,
    mujoco_mod: Any,
    initial_geom_colors_54: str,
) -> str:
    """Test/verification helper mapping current 54 sticker geom 3D world coords into logical cube state.

    Must only be used in offline physics verification tests (never runtime robot policy).
    Reads sticker world positions relative to `cube` body frame, resolves canonical grid slots,
    and un-maps `physical_color_layout` back to CubeEngine string order.
    """
    from .physical_u import physical_color_layout

    cube_id = int(mujoco_mod.mj_name2id(model, mujoco_mod.mjtObj.mjOBJ_BODY, "cube"))
    c_pos = np.asarray(data.xpos[cube_id], dtype=float)
    r_cube = np.asarray(data.xmat[cube_id], dtype=float).reshape(3, 3)

    slot_points: list[np.ndarray] = []
    for face in "URFDLB":
        slot_points.extend(canonical_local_centers(face))

    out = ["?"] * 54
    slot_idx = 0
    for face in "URFDLB":
        for idx in range(9):
            gid = int(mujoco_mod.mj_name2id(model, mujoco_mod.mjtObj.mjOBJ_GEOM, f"sticker_{face}_{idx}"))
            p_world = np.asarray(data.geom_xpos[gid], dtype=float)
            p_cube = r_cube.T @ (p_world - c_pos)
            best_j = min(range(54), key=lambda j: float(np.linalg.norm(slot_points[j] - p_cube)))
            out[best_j] = initial_geom_colors_54[slot_idx]
            slot_idx += 1

    geom_state = "".join(out)
    return physical_color_layout(geom_state)
