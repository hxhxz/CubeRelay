"""Isolated mechanism tests initialize an object in the station.

These are not robot-transport or visual end-to-end tests; those use the runner.
"""
from pathlib import Path
import xml.etree.ElementTree as ET
import numpy as np
import pytest
from cube_relay.embodied.physical_u import build_u_scene

SCENE = Path(__file__).resolve().parents[1]/"simulation/cube_relay_v2.xml"


def test_physical_notation_adapter_matches_engine_geometry():
    from cube_relay.cube.moves import STICKERS
    from cube_relay.embodied.canonical_facelets import canonical_local_centers
    from cube_relay.embodied.physical_u import physical_color_layout
    # Kociemba (R,U,F) -> XML (+X,+Z,-Y) is a proper rotation.
    transform = np.array([[1,0,0],[0,0,-1],[0,1,0]])
    for i, face in enumerate("URFDLB"):
        centers = canonical_local_centers(face, 1., 1.)
        order = [6,7,8,3,4,5,0,1,2] if face in "UD" else list(range(9))
        for j, k in enumerate(order):
            assert np.array_equal(centers[k], transform @ np.array(STICKERS[i*9+j][0]))
    labels = "".join(chr(33+i) for i in range(54))
    assert physical_color_layout(physical_color_layout(labels)) == labels


def test_layer_owns_exact_21_affected_stickers():
    root = ET.fromstring(build_u_scene(SCENE))
    layer = root.find(".//body[@name='u_layer']")
    names = {g.get("name") for g in layer.findall("geom") if g.get("name", "").startswith("sticker")}
    expected = {f"sticker_U_{i}" for i in range(9)} | {f"sticker_{f}_{i}" for f in "FRBL" for i in range(3)}
    assert names == expected
    # Only the releasable detent acts on the layer joint. External rotor has
    # its own actuator and no equality coupling to the layer.
    assert [a.get("name") for a in root.find("actuator") if a.get("joint") == "u_layer_joint"] == ["u_brake"]
    assert not any("u_layer" in str(e.attrib) for e in root.find("equality"))


@pytest.mark.parametrize("contact_enabled", [True, False])
def test_external_rotor_requires_actual_layer_contact(contact_enabled):
    mj = pytest.importorskip("mujoco")
    root = ET.fromstring(build_u_scene(SCENE))
    root.find(".//body[@name='cube']").set("pos", ".35 -.32 .66")
    if not contact_enabled:
        for side in ("pos", "neg"):
            geom = root.find(f".//geom[@name='turn_{side}_pad']")
            geom.set("contype", "0")
            geom.set("conaffinity", "0")
    model = mj.MjModel.from_xml_string(ET.tostring(root, encoding="unicode"))
    data = mj.MjData(model)
    def act(name):
        return mj.mj_name2id(model, mj.mjtObj.mjOBJ_ACTUATOR, name)
    def step(targets, seconds):
        start = data.ctrl.copy()
        steps = int(seconds/model.opt.timestep)
        for i in range(steps):
            t = (i+1)/steps
            for name, value in targets.items():
                idx = act(name)
                data.ctrl[idx] = start[idx]+(value-start[idx])*t*t*(3-2*t)
            mj.mj_step(model, data)
    rgba = model.geom_rgba.copy()
    step({"base_pos_ctrl": .065, "base_neg_ctrl": .065}, 2)
    step({"turn_z_ctrl": .5}, 2)
    step({"turn_pos_ctrl": .045, "turn_neg_ctrl": .045}, 2)
    model.actuator_gainprm[act("u_brake"), 0] = 0
    model.actuator_biasprm[act("u_brake"), 1] = 0
    step({"turn_rotor_ctrl": -np.pi/2}, 4)
    step({}, .5)
    joint = mj.mj_name2id(model, mj.mjtObj.mjOBJ_JOINT, "u_layer_joint")
    angle = data.qpos[model.jnt_qposadr[joint]]
    if contact_enabled:
        assert angle == pytest.approx(-np.pi/2, abs=.03)
        # Independent geometry check: actual transformed geom centres must
        # occupy the symbolic U destinations, not just a successful actuator.
        from cube_relay.embodied.canonical_facelets import canonical_local_centers
        from cube_relay.cube.moves import QUARTER_TURNS
        local_centers = []
        order_ud = [6,7,8,3,4,5,0,1,2]
        for face in "URFDLB":
            centers = canonical_local_centers(face)
            local_centers.extend(centers[order_ud] if face in "UD" else centers)
        cube = mj.mj_name2id(model, mj.mjtObj.mjOBJ_BODY, "cube")
        rotation = data.xmat[cube].reshape(3,3)
        for face_index, face in enumerate("URFDLB"):
            for physical_index in range(9):
                source = face_index*9+(order_ud[physical_index] if face in "UD" else physical_index)
                geom = mj.mj_name2id(model, mj.mjtObj.mjOBJ_GEOM, f"sticker_{face}_{physical_index}")
                measured = rotation.T@(data.geom_xpos[geom]-data.xpos[cube])
                distances = np.linalg.norm(np.asarray(local_centers)-measured,axis=1)
                assert np.argmin(distances) == QUARTER_TURNS["U"][source]
                assert min(distances) < .002
    else:
        assert abs(angle) < .01  # Same successful rotor motion cannot turn layer.
    rotor = mj.mj_name2id(model, mj.mjtObj.mjOBJ_JOINT, "turn_rotor_joint")
    assert data.qpos[model.jnt_qposadr[rotor]] == pytest.approx(-np.pi/2, abs=.03)
    assert np.array_equal(model.geom_rgba, rgba)


def test_collision_guard_does_not_allow_robot_fixture_overlap():
    from cube_relay.embodied.physical_u import ContactUTurn
    row = {"contacts": [{"geoms": ["left_finger_pad", "base_pos_pad"],
                         "distance": -.0001, "normal_force": 1.}]}
    assert not ContactUTurn.collision_safe(row)
    row["contacts"][0]["geoms"] = ["cube_core", "base_pos_pad"]
    assert ContactUTurn.collision_safe(row)


def test_seed0_same_scene_scan_transport_contact_turn_and_visual(monkeypatch):
    pytest.importorskip("mujoco")
    from cube_relay.embodied.mujoco_v2 import MuJoCoEmbodiedBackend
    from cube_relay.embodied.active_inspection_v7 import ContinuousActiveInspector
    from cube_relay.embodied.physical_u import ContactUTurn
    from cube_relay.embodied.visual_turn_loop import compare_observations
    from cube_relay.cube import CubeEngine
    b = MuJoCoEmbodiedBackend(physical_u=True, width=320, height=240)
    try:
        b.reset_random(0, 15)
        identity = (id(b.model), id(b.data))
        colors = b.model.geom_rgba.copy()
        state_sentinel = b._appearance_state
        def forbidden(*a, **kw):
            raise AssertionError("No reset/recolor/symbolic execution after initialization")
        monkeypatch.setattr(b, "reset_random", forbidden)
        monkeypatch.setattr(b, "_set_sticker_colors", forbidden)
        monkeypatch.setattr(b.engine, "apply_move", forbidden)
        assert b._turner is None
        scan = ContinuousActiveInspector(b, "sequential").run(0, reset_scene=False)
        assert scan.success
        expected = CubeEngine().apply_move(scan.reconstructed_facelets, "U")
        controller = ContactUTurn(b)
        result = controller.dock_and_turn()
        assert result["success"], result
        comparison = compare_observations(expected, b.task_observe_released(3000))
        affected = list(range(9))+["URFDLB".index(f)*9+i for f in "RFLB" for i in range(3)]
        assert not comparison["conflicts"] and not comparison["differences"]
        assert all(comparison["observed_state"][i] == expected[i] for i in affected)
        assert np.array_equal(colors, b.model.geom_rgba)
        assert state_sentinel == b._appearance_state
        assert identity == (id(b.model), id(b.data))
        assert not any(b.data.eq_active)  # Including the legacy unused human weld.
        turning = [r for r in controller.trace if r["phase"] == "CONTACT_TURN"]
        assert all(abs(r["layer_brake_torque"]) < 1e-10 for r in turning)
        assert all(controller.paired(r,"base","cube_core") and
                   controller.paired(r,"turn","u_layer_core") for r in turning)
    finally:
        b.renderer.close()
