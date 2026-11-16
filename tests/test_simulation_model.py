from pathlib import Path
from xml.etree import ElementTree


def test_mujoco_model_declares_scene_camera_arm_and_six_turn_actuators() -> None:
    path = Path(__file__).resolve().parents[1] / "simulation" / "cube_relay.xml"
    root = ElementTree.parse(path).getroot()
    names = {element.get("name") for element in root.iter() if element.get("name")}
    assert {"table", "cube", "robot_base", "overhead"} <= names
    assert {f"face_{face}" for face in "URFDLB"} <= names
    assert {f"turn_{face}" for face in "URFDLB"} <= names


def test_v2_model_has_free_cube_rgb_stickers_gripper_and_handoff_constraints() -> None:
    path = Path(__file__).resolve().parents[1] / "simulation" / "cube_relay_v2.xml"
    root = ElementTree.parse(path).getroot()
    names = {element.get("name") for element in root.iter() if element.get("name")}
    assert {"cube_free", "left_finger_pad", "right_finger_pad", "inspection_x", "inspection_y"} <= names
    assert "robot_grasp_weld" not in names
    assert "human_grasp_weld" in names
    assert {f"sticker_{face}_{index}" for face in "URFDLB" for index in range(9)} <= names

    sticker_geoms = [
        element for element in root.iter("geom")
        if (element.get("name") or "").startswith("sticker_")
    ]
    assert len(sticker_geoms) == 54
    assert all(element.get("density") == "0" for element in sticker_geoms)


def test_v7_scan_station_has_four_sides_top_and_reoriented_views() -> None:
    path = Path(__file__).resolve().parents[1] / "simulation" / "cube_relay_v2.xml"
    root = ElementTree.parse(path).getroot()
    cameras = {element.get("name") for element in root.findall(".//camera")}
    assert {"scan_x", "scan_y", "scan_neg_x", "scan_neg_y", "scan_top"} <= cameras
    assert {"inspection_high_x", "inspection_high_y",
            "inspection_high_neg_x", "inspection_high_neg_y"} <= cameras

    core = next(element for element in root.iter("geom") if element.get("name") == "cube_core")
    assert float(core.get("mass")) == .085
    for pad_name in ("left_finger_pad", "right_finger_pad"):
        pad = next(element for element in root.iter("geom") if element.get("name") == pad_name)
        assert float(pad.get("friction").split()[0]) == 10.0

    bodies = {element.get("name"): element for element in root.iter("body")}
    assert float(bodies["left_finger"].get("pos").split()[1]) == .14
    assert float(bodies["right_finger"].get("pos").split()[1]) == -.14
