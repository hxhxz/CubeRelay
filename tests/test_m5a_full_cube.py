from __future__ import annotations

import json
import math
from pathlib import Path

import numpy as np
import pytest

mujoco = pytest.importorskip("mujoco")

from cube_relay.cube.moves import CubeEngine, LEGAL_MOVES  # noqa: E402
from cube_relay.cube.state import SOLVED_FACELETS  # noqa: E402
from cube_relay.embodied.mujoco_v2 import _COLORS, MuJoCoEmbodiedBackend  # noqa: E402
from cube_relay.embodied.physical_cube_26 import (  # noqa: E402
    Physical26CubeTurnExecutor,
    build_26_cubie_scene,
    extract_54_geom_facelets_state,
    move_to_top_fixture_angle_rad,
)
from cube_relay.embodied.physical_u import physical_color_layout  # noqa: E402
from cube_relay.mission.models import MissionType  # noqa: E402
from cube_relay.mission.session import SimulationSession  # noqa: E402
from cube_relay.mission.skill_registry import SkillRegistry  # noqa: E402


def test_skill_registry_full_cube_metadata_and_validation() -> None:
    reg_default = SkillRegistry()
    cap_u_only = reg_default.can_execute_physical_move("R'", {"physical_u_scene_enabled": True})
    assert cap_u_only.supported is False

    reg_full = SkillRegistry(physical_full_cube=True)
    snap = reg_full.snapshot()
    assert snap.physical_supported_moves == list(LEGAL_MOVES)
    desc = reg_full.get("execute_physical_face_turn")
    assert desc is not None and desc.implemented is True
    assert desc.execution_metadata["supports_all_18_moves"] is True
    assert desc.execution_metadata["estimated_flips_values"] == [0, 1, 2]

    ok, err = reg_full.validate_parameters("execute_physical_face_turn", {"move": "R'"})
    assert ok is True and err is None
    ok_bad, err_bad = reg_full.validate_parameters("execute_physical_face_turn", {"move": "X"})
    assert ok_bad is False and err_bad is not None
    ok_extra, _ = reg_full.validate_parameters("execute_physical_face_turn", {"move": "U", "bogus": 1})
    assert ok_extra is False

    scene_ready = {
        "full_26_cubie_scene_enabled": True,
        "cube_localized_and_scanned": True,
        "turn_station_available": True,
        "cube_top_face": "U",
        "cube_bottom_face": "D",
    }
    cap_u = reg_full.can_execute_physical_move("U", scene_ready)
    cap_r = reg_full.can_execute_physical_move("R'", scene_ready)
    cap_d2 = reg_full.can_execute_physical_move("D2", scene_ready)
    assert cap_u.supported and cap_u.estimated_flips == 0
    assert cap_r.supported and cap_r.estimated_flips == 1
    assert cap_d2.supported and cap_d2.estimated_flips == 2

    blocked_state = dict(scene_ready)
    blocked_state["turn_station_available"] = False
    cap_blocked = reg_full.can_execute_physical_move("R'", blocked_state)
    assert cap_blocked.supported is False
    assert "turn_station_available" in cap_blocked.missing_preconditions


def test_all_18_moves_real_flip_and_contact_fixture_54_cell_equivalence() -> None:
    """Verify every one of the 18 standard moves via real flip-and-feed + contact-driven fixture."""
    eng = CubeEngine()
    base_state = eng.apply_move(eng.apply_move(SOLVED_FACELETS, "L"), "F")
    geom_init = physical_color_layout(base_state)

    backend = MuJoCoEmbodiedBackend(full_26_cubie=True, width=240, height=180)
    try:
        for face in ("U", "R", "F", "D", "L", "B"):
            # Fresh episode per face axis so each face genuinely flips from table (0, 1, or 2 flips),
            # then verifies base (-90°), prime (+90°), and double (-180°) via contact fixture!
            backend._sticker_colors_locked = False
            backend.mujoco.mj_resetData(backend.model, backend.data)
            assert backend.cube_26_turner is not None and backend.orientation_tracker is not None
            backend.cube_26_turner.reset_welds()
            backend.orientation_tracker.reset()
            backend._cube_26_location = "table"
            backend._appearance_state = base_state
            backend._set_sticker_colors(base_state)
            backend._sticker_colors_locked = True
            qadr = int(backend.model.jnt_qposadr[backend._joint("cube_free")])
            backend.data.qpos[qadr : qadr + 3] = [0.18, 0.05, 0.665]
            backend.data.qpos[qadr + 3 : qadr + 7] = [1.0, 0.0, 0.0, 0.0]
            backend.mujoco.mj_forward(backend.model, backend.data)
            for _ in range(120):
                backend.step_physics()
            backend.visual_world_state = None
            backend._index_cube_to_world = None
            backend._predicted_cube_rotation = None
            init_rgba = backend.model.geom_rgba.copy()
            exp = base_state

            for idx, mv in enumerate((face, f"{face}'", f"{face}2")):
                res = backend.execute_physical_face_turn(mv)
                assert res["success"] is True, (mv, res)
                assert res["contact_driven"] is True, (mv, res)
                assert res["top_pad_contact_steps"] > 0, (mv, res)
                assert float(res["angle_error_deg"]) < 8.0, (mv, res)
                if idx == 0:
                    expected_flips = 0 if face == "U" else (2 if face == "D" else 1)
                    assert res["flips_executed"] == expected_flips, (mv, res)
                else:
                    assert res["flips_executed"] == 0, (mv, res)

                exp = eng.apply_move(exp, mv)
                obs = extract_54_geom_facelets_state(backend.model, backend.data, backend.mujoco, geom_init)
                assert obs == exp, f"54-cell mismatch after physical {mv}"
                assert np.array_equal(init_rgba, backend.model.geom_rgba), f"Runtime recolor detected during {mv}"
    finally:
        backend.renderer.close()


def test_negative_contact_control_and_slice_misaligned_jam() -> None:
    xml = build_26_cubie_scene("simulation/cube_relay_v2.xml")

    # (a) Negative control: disabling turn pad collisions leaves top layer at ~0 deg and fails
    m_neg = mujoco.MjModel.from_xml_string(xml)
    d_neg = mujoco.MjData(m_neg)
    qadr = int(m_neg.jnt_qposadr[mujoco.mj_name2id(m_neg, mujoco.mjtObj.mjOBJ_JOINT, "cube_free")])
    d_neg.qpos[qadr : qadr + 3] = [0.35, -0.32, 0.660]
    d_neg.qpos[qadr + 3 : qadr + 7] = [1.0, 0.0, 0.0, 0.0]
    mujoco.mj_forward(m_neg, d_neg)

    ex_neg = Physical26CubeTurnExecutor(m_neg, d_neg, mujoco)
    res_neg = ex_neg.execute_top_face_turn(move_to_top_fixture_angle_rad("U"), contact_enabled=False)
    assert res_neg.success is False
    assert res_neg.failure_code == "CONTACT_DRIVE_FAILED"
    assert abs(math.degrees(res_neg.actual_angle_rad)) < 1.0
    assert res_neg.top_pad_contact_steps == 0

    # (b) Mechanical slice jam: incomplete ~15 deg turn + perpendicular axis switch triggers SLICE_MISALIGNED_JAM
    m_jam = mujoco.MjModel.from_xml_string(xml)
    d_jam = mujoco.MjData(m_jam)
    d_jam.qpos[qadr : qadr + 3] = [0.35, -0.32, 0.660]
    d_jam.qpos[qadr + 3 : qadr + 7] = [1.0, 0.0, 0.0, 0.0]
    mujoco.mj_forward(m_jam, d_jam)

    ex_jam = Physical26CubeTurnExecutor(m_jam, d_jam, mujoco)
    res_partial = ex_jam.execute_top_face_turn(
        move_to_top_fixture_angle_rad("U"),
        interrupt_after_rad=-math.radians(15.0),
    )
    assert res_partial.success is False
    assert res_partial.max_slice_misalignment_deg > 8.0

    # Rotate whole cube 90 deg around X (perpendicular F face now up) without auto-snapping off-lattice cubies
    d_jam.qpos[qadr : qadr + 3] = [0.35, -0.32, 0.660]
    d_jam.qpos[qadr + 3 : qadr + 7] = [math.cos(math.pi * 0.25), math.sin(math.pi * 0.25), 0.0, 0.0]
    mujoco.mj_forward(m_jam, d_jam)

    res_jam = ex_jam.execute_top_face_turn(move_to_top_fixture_angle_rad("F"))
    assert res_jam.success is False
    assert res_jam.failure_code == "SLICE_MISALIGNED_JAM"
    assert res_jam.max_slice_misalignment_deg > 8.0


def test_cross_axis_u_rp_d2_and_two_flip_d2_with_independent_camera_verification() -> None:
    artifact_dir = Path("results/m5a_cross_axis_u_rp_d2")
    artifact_dir.mkdir(parents=True, exist_ok=True)
    video_path = artifact_dir / "cross_axis_u_rp_d2.mp4"

    eng = CubeEngine()

    # Sequence 1: U -> R' -> D2 in one continuous MjModel/MjData session + independent camera 54/54 check
    b1 = MuJoCoEmbodiedBackend(
        full_26_cubie=True,
        width=320,
        height=240,
        video_path=video_path,
        video_timing="sim_time",
    )
    try:
        meta = b1.reset_random(seed=0, scramble_steps=4)
        init_state = str(meta["truth_for_evaluation_only"])
        geom_init = physical_color_layout(init_state)
        init_rgba = b1.model.geom_rgba.copy()
        m_id, d_id = id(b1.model), id(b1.data)

        # Forbid runtime color overwrites or symbolic appearance mutations
        with pytest.raises(RuntimeError):
            b1._set_sticker_colors(init_state)
        with pytest.raises(RuntimeError):
            b1.execute_physical_turn("U")

        exp = init_state
        move_reports: list[dict] = []
        for mv in ("U", "R'", "D2"):
            res = b1.execute_physical_face_turn(mv)
            exp = eng.apply_move(exp, mv)
            geom_obs = extract_54_geom_facelets_state(b1.model, b1.data, b1.mujoco, geom_init)
            assert res["success"] is True, (mv, res)
            assert res["contact_driven"] is True, (mv, res)
            assert float(res["angle_error_deg"]) < 2.0, (mv, res)
            assert float(res["max_slice_misalignment_deg"]) < 2.0, (mv, res)
            assert geom_obs == exp, (mv, geom_obs, exp)
            assert (id(b1.model), id(b1.data)) == (m_id, d_id)
            assert np.array_equal(init_rgba, b1.model.geom_rgba)
            move_reports.append(res)

        cam_verify = b1.inspect_26_cubie_via_independent_cameras()
        assert cam_verify["success"] is True, cam_verify
        assert cam_verify["observed_count"] == 54, cam_verify
        assert cam_verify["conflict_count"] == 0, cam_verify
        assert cam_verify["facelets"] == exp
        assert np.array_equal(init_rgba, b1.model.geom_rgba)

        written_video = b1.write_video(video_path, fps=12)
        assert written_video is not None and written_video.exists()
    finally:
        b1.renderer.close()

    # Sequence 2: explicit U -> D2 (verifying 2-flip bottom tabletop lay -> release -> visual regrasp -> flip -> 180 deg turn)
    b2 = MuJoCoEmbodiedBackend(full_26_cubie=True, width=240, height=180)
    try:
        meta2 = b2.reset_random(seed=3, scramble_steps=3)
        init2 = str(meta2["truth_for_evaluation_only"])
        geom_init2 = physical_color_layout(init2)
        exp2 = init2
        r_u = b2.execute_physical_face_turn("U")
        exp2 = eng.apply_move(exp2, "U")
        assert r_u["success"] and r_u["flips_executed"] == 0

        r_d2 = b2.execute_physical_face_turn("D2")
        exp2 = eng.apply_move(exp2, "D2")
        assert r_d2["success"] is True, r_d2
        assert r_d2["flips_executed"] == 2, r_d2
        assert r_d2["regrasps_executed"] == 1, r_d2
        assert float(r_d2["angle_error_deg"]) < 2.0, r_d2
        assert extract_54_geom_facelets_state(b2.model, b2.data, b2.mujoco, geom_init2) == exp2

        cam2 = b2.inspect_26_cubie_via_independent_cameras()
        assert cam2["success"] is True and cam2["observed_count"] == 54
        assert cam2["facelets"] == exp2
    finally:
        b2.renderer.close()

    report_payload = {
        "u_rp_d2_moves": move_reports,
        "u_rp_d2_camera_verification": {k: v for k, v in cam_verify.items() if k != "facelets"},
        "u_rp_d2_video_path": str(video_path),
        "u_d2_two_flip_turn": r_d2,
        "u_d2_camera_verification": {k: v for k, v in cam2.items() if k != "facelets"},
    }
    (artifact_dir / "verification_report.json").write_text(
        json.dumps(report_payload, indent=2, ensure_ascii=False), encoding="utf-8"
    )


def test_simulation_session_full_cube_solve_mission() -> None:
    sess = SimulationSession(seed=0, full_26_cubie=True, scramble_steps=2, width=240, height=180)
    try:
        snap = sess.run_mission(MissionType.SOLVE_CUBE)
        assert snap["mission"]["status"] == "COMPLETED", snap["mission"]
        pv = snap.get("physical_verification") or {}
        assert pv.get("exact_54_match") is True, pv
        assert pv.get("observed_count") == 54, pv
        assert pv.get("no_recolor") is True, pv
        assert pv.get("logical_state_unchanged") is True, pv
        assert len(sess.scene_state.get("executed_physical_moves") or []) >= 1
    finally:
        sess.close()
