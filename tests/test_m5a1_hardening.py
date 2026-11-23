"""M5-A.1 hardening tests: preempted mid-slice unwind recovery, lattice guards, and 26-cubie API/session config."""

from __future__ import annotations

import importlib.util
import inspect
import math
import os

import numpy as np
import pytest
from fastapi.testclient import TestClient

from cube_relay.api import main as api_main
from cube_relay.cube import CubeEngine
from cube_relay.cube.moves import LEGAL_MOVES
from cube_relay.execution.action_chunk import CancellationToken, InterruptMode
from cube_relay.mission import MissionState, MissionStatus, MissionType, SkillRegistry
from cube_relay.mission.planner import LLMAgentDecisionPolicy
from cube_relay.mission.session import SimulationSession

_SKIP_MUJOCO_GL = (
    os.environ.get("CUBERELAY_SKIP_GL_TESTS", "0") == "1"
    or importlib.util.find_spec("mujoco") is None
)


def _preempt_u_at_angle(backend: object, target_abs_deg: float) -> tuple[dict, str, object, np.ndarray]:
    """Run U and preempt via CancellationToken once top rotor crosses target_abs_deg."""
    from cube_relay.embodied.physical_u import physical_color_layout

    meta = backend.reset_random(seed=0, scramble_steps=4)  # type: ignore[attr-defined]
    init_state = str(meta["truth_for_evaluation_only"])
    geom_init = physical_color_layout(init_state)
    init_rgba = backend.model.geom_rgba.copy()  # type: ignore[attr-defined]

    token = CancellationToken()
    rj = backend._joint("turn_rotor_joint")  # type: ignore[attr-defined]
    rj_qadr = int(backend.model.jnt_qposadr[rj])  # type: ignore[attr-defined]
    turner = backend.cube_26_turner  # type: ignore[attr-defined]
    assert turner is not None
    old_post = turner.post_step_fn

    def _post_step(_step_idx: int = 0) -> None:
        if old_post is not None:
            old_post()
        deg = abs(math.degrees(float(backend.data.qpos[rj_qadr])))  # type: ignore[attr-defined]
        if deg >= target_abs_deg and not token.is_cancelled():
            token.cancel(
                "HUMAN_HANDOFF_MID_SLICE",
                mode=InterruptMode.IMMEDIATE_HOLD,
                sim_time_s=float(backend.data.time),  # type: ignore[attr-defined]
            )

    turner.post_step_fn = _post_step
    try:
        res = backend.execute_physical_face_turn("U", token=token)  # type: ignore[attr-defined]
    finally:
        turner.post_step_fn = old_post
    return res, init_state, geom_init, init_rgba


def test_skill_registry_station_lattice_guard_and_recovery_validation() -> None:
    reg = SkillRegistry(physical_full_cube=True)
    rec_desc = reg.get("recover_preempted_turn_slice")
    assert rec_desc is not None and rec_desc.implemented is True
    assert set(rec_desc.supported_physical_actions) == {"UNWIND_TO_ZERO", "ALIGN_NEAREST_DETENT"}

    assert reg.validate_parameters("recover_preempted_turn_slice", {"mode": "UNWIND_TO_ZERO"}) == (True, None)
    assert reg.validate_parameters("recover_preempted_turn_slice", {"mode": "ALIGN_NEAREST_DETENT"}) == (True, None)
    ok_bad_mode, msg_bad_mode = reg.validate_parameters("recover_preempted_turn_slice", {"mode": "SNAP"})
    assert not ok_bad_mode and "PARAMETER_OUT_OF_BOUNDS" in msg_bad_mode
    ok_bad_key, msg_bad_key = reg.validate_parameters("recover_preempted_turn_slice", {"force": 1})
    assert not ok_bad_key and "PARAMETER_OUT_OF_BOUNDS" in msg_bad_key

    misaligned_state = {
        "full_26_cubie_scene_enabled": True,
        "cube_localized_and_scanned": True,
        "turn_station_available": True,
        "is_lattice_aligned": False,
    }
    for sid in ("execute_physical_face_turn", "regrasp_cube", "reorient_cube"):
        ok_pre, missing = reg.check_preconditions(sid, misaligned_state)
        assert not ok_pre
        assert "station_lattice_aligned" in missing

    cap = reg.can_execute_physical_move("R'", scene_state=misaligned_state)
    assert not cap.supported
    assert "station_lattice_aligned" in cap.missing_preconditions

    assert reg.check_preconditions(
        "recover_preempted_turn_slice",
        {"full_26_cubie_scene_enabled": True, "turn_station_available": True},
    ) == (True, [])

    # Verify LLM allowed skill filter excludes recovery during pure inspect / legacy U-turn missions
    policy = object.__new__(LLMAgentDecisionPolicy)
    policy.context_mode = "vision_plus_structured_state"
    inspect_mission = MissionState(
        mission_id="m-ins",
        session_id="s-1",
        mission_type=MissionType.INSPECT_CUBE,
        user_goal="inspect",
        success_criteria="all 54",
        status=MissionStatus.CREATED,
        created_at="2026-11-19T00:00:00Z",
    )
    verify_u_mission = MissionState(
        mission_id="m-u",
        session_id="s-1",
        mission_type=MissionType.VERIFY_PHYSICAL_U_TURN,
        user_goal="u turn",
        success_criteria="U",
        status=MissionStatus.CREATED,
        created_at="2026-11-19T00:00:00Z",
    )
    assert "recover_preempted_turn_slice" not in policy._allowed_skill_ids(inspect_mission, reg)
    assert "recover_preempted_turn_slice" not in policy._allowed_skill_ids(verify_u_mission, reg)


def test_m3d_api_full_26_cubie_config_and_legacy_default(monkeypatch: pytest.MonkeyPatch) -> None:
    sig = inspect.signature(SimulationSession.__init__)
    assert sig.parameters["full_26_cubie"].default is False

    class _MockLiveSession:
        def __init__(self, *, full_26_cubie: bool = False) -> None:
            self.full_26_cubie = full_26_cubie
            self.selected_mission_type = MissionType.VERIFY_PHYSICAL_U_TURN
            self.reset_calls: list[dict] = []
            self.start_calls: list[dict] = []

        def get_snapshot(self) -> dict[str, object]:
            return {
                "full_26_cubie": self.full_26_cubie,
                "physical_full_cube": self.full_26_cubie,
                "selected_mission_type": self.selected_mission_type.value,
            }

        def get_capabilities(self) -> dict[str, object]:
            return {"physical_full_cube": self.full_26_cubie}

        def reconfigure_full_26_cubie(self, full_26_cubie: bool) -> dict[str, object]:
            self.full_26_cubie = bool(full_26_cubie)
            return self.get_snapshot()

        def reset_scene(
            self,
            seed: int | None = None,
            mission_type: str | None = None,
            *,
            full_26_cubie: bool | None = None,
        ) -> dict[str, object]:
            if full_26_cubie is not None:
                self.full_26_cubie = bool(full_26_cubie)
            self.reset_calls.append({"seed": seed, "mission_type": mission_type, "full_26_cubie": full_26_cubie})
            return self.get_snapshot()

        def start_mission_async(
            self,
            mission_type: str,
            *,
            seed: int | None = None,
            full_26_cubie: bool | None = None,
        ) -> dict[str, object]:
            if full_26_cubie is not None:
                self.full_26_cubie = bool(full_26_cubie)
            self.start_calls.append({"mission_type": mission_type, "seed": seed, "full_26_cubie": full_26_cubie})
            return {"accepted": True, "full_26_cubie": self.full_26_cubie}

    prev_session = api_main._m3d_session
    prev_default_full = api_main._m3d_default_full_26_cubie
    mock = _MockLiveSession(full_26_cubie=True)
    api_main.configure_m3d_session(mock, default_seed=0, full_26_cubie=True)
    client = TestClient(api_main.app)
    try:
        assert prev_default_full is True
        cfg_resp = client.post("/api/m3d/configure", json={"seed": 3, "full_26_cubie": False})
        assert cfg_resp.status_code == 200
        assert cfg_resp.json()["snapshot"]["full_26_cubie"] is False

        cmd_resp = client.post("/api/m3d/command", json={"type": "SET_FULL_26_CUBIE", "full_26_cubie": True})
        assert cmd_resp.status_code == 200
        assert cmd_resp.json()["snapshot"]["full_26_cubie"] is True

        start_resp = client.post(
            "/api/m3d/command",
            json={"type": "START_MISSION", "mission_type": "SOLVE_CUBE", "seed": 2, "full_26_cubie": True},
        )
        assert start_resp.status_code == 200
        assert mock.start_calls[-1]["full_26_cubie"] is True
    finally:
        api_main._m3d_session = prev_session
        api_main._m3d_default_full_26_cubie = prev_default_full


@pytest.mark.skipif(_SKIP_MUJOCO_GL, reason="MuJoCo GL tests skipped or mujoco not installed")
def test_preempted_mid_slice_unwind_to_zero_and_subsequent_r_prime() -> None:
    """Mandatory Task 1 check: preempt U at -35..-50 deg -> block R' -> pure contact unwind < 2 deg -> R' succeeds."""
    from cube_relay.embodied.mujoco_v2 import MuJoCoEmbodiedBackend
    from cube_relay.embodied.physical_cube_26 import extract_54_geom_facelets_state

    backend = MuJoCoEmbodiedBackend(full_26_cubie=True)
    try:
        m_id, d_id = id(backend.model), id(backend.data)
        u_res, init_state, geom_init, init_rgba = _preempt_u_at_angle(backend, target_abs_deg=38.0)

        assert u_res["success"] is False
        assert u_res["preempted"] is True
        assert u_res["chunk_status"] == "PREEMPTED_SAFE_HOLD"
        assert u_res["is_lattice_aligned"] is False
        assert 35.0 <= abs(float(u_res["residual_slice_angle_deg"])) <= 50.0
        assert float(u_res["actual_angle_rad"]) < 0.0

        # Guard check 1: attempting another axis/move R' before unwind must fail safely with SLICE_MISALIGNED_JAM.
        blocked_turn = backend.execute_physical_face_turn("R'")
        assert blocked_turn["success"] is False
        assert blocked_turn["failure_code"] == "SLICE_MISALIGNED_JAM"
        assert blocked_turn["is_lattice_aligned"] is False

        # Guard check 2: FlipAndFeed arm pick/flip must reject lifting while misaligned.
        assert backend.flip_controller is not None and backend.orientation_tracker is not None
        assert backend.flip_controller.is_lattice_aligned is False
        blocked_ff = backend.flip_controller.orient_face_up_and_dock(
            "R",
            backend.orientation_tracker,
            current_location=backend._cube_26_location,
            current_center_xy=(0.35, -0.32),
        )
        assert blocked_ff.success is False
        assert "SLICE_MISALIGNED_JAM" in (blocked_ff.failure_reason or "")

        # Pure contact unwind back to 0 deg without modifying qpos directly.
        rec = backend.recover_preempted_turn_slice(mode="UNWIND_TO_ZERO")
        assert rec["success"] is True
        assert rec["contact_driven"] is True
        assert int(rec["top_pad_contact_steps"]) > 0
        assert rec["is_lattice_aligned"] is True
        assert float(rec["max_slice_misalignment_deg"]) < 2.0
        assert abs(float(rec["residual_slice_angle_deg"])) < 2.0
        assert float(rec["target_angle_rad"]) > 0.0
        assert abs(math.degrees(float(rec["actual_angle_rad"]) - float(rec["target_angle_rad"]))) < 2.0

        restored_54 = extract_54_geom_facelets_state(backend.model, backend.data, backend.mujoco, geom_init)
        assert restored_54 == init_state, f"54-cell mismatch after unwind: {restored_54} vs {init_state}"

        # Immediately execute flip-and-feed + R' after safe recovery.
        r_res = backend.execute_physical_face_turn("R'")
        assert r_res["success"] is True, r_res
        assert r_res["contact_driven"] is True
        assert r_res["is_lattice_aligned"] is True
        assert float(r_res["max_slice_misalignment_deg"]) < 2.0
        expected_after_rp = CubeEngine().apply_move(init_state, "R'")
        obs_after_rp = extract_54_geom_facelets_state(backend.model, backend.data, backend.mujoco, geom_init)
        assert obs_after_rp == expected_after_rp
        assert (id(backend.model), id(backend.data)) == (m_id, d_id)
        assert np.array_equal(init_rgba, backend.model.geom_rgba)
    finally:
        backend.renderer.close()


@pytest.mark.skipif(_SKIP_MUJOCO_GL, reason="MuJoCo GL tests skipped or mujoco not installed")
def test_recover_preempted_turn_slice_align_nearest_detent() -> None:
    from cube_relay.embodied.mujoco_v2 import MuJoCoEmbodiedBackend
    from cube_relay.embodied.physical_cube_26 import extract_54_geom_facelets_state

    backend = MuJoCoEmbodiedBackend(full_26_cubie=True)
    try:
        u_res, init_state, geom_init, _ = _preempt_u_at_angle(backend, target_abs_deg=55.0)
        assert u_res["preempted"] is True
        assert u_res["is_lattice_aligned"] is False

        rec = backend.recover_preempted_turn_slice(mode="ALIGN_NEAREST_DETENT")
        assert rec["success"] is True, rec
        assert rec["contact_driven"] is True
        assert rec["is_lattice_aligned"] is True
        assert float(rec["target_angle_rad"]) < 0.0
        assert abs(math.degrees(float(rec["actual_angle_rad"]) - float(rec["target_angle_rad"]))) < 2.0
        assert float(rec["max_slice_misalignment_deg"]) < 2.0
        expected_after_u = CubeEngine().apply_move(init_state, "U")
        obs_after_u = extract_54_geom_facelets_state(backend.model, backend.data, backend.mujoco, geom_init)
        assert obs_after_u == expected_after_u
    finally:
        backend.renderer.close()


@pytest.mark.skipif(_SKIP_MUJOCO_GL, reason="MuJoCo GL tests skipped or mujoco not installed")
def test_session_full_26_cubie_and_legacy_compatibility() -> None:
    session = SimulationSession(seed=0, width=240, height=180, use_dedicated_thread=False)
    try:
        assert session.full_26_cubie is False
        snap_legacy = session.run_mission(MissionType.SOLVE_CUBE, seed=0)
        assert snap_legacy["full_26_cubie"] is False
        assert snap_legacy["capabilities"]["physical_supported_moves"] == ["U"]
        assert snap_legacy["mission"]["status"] == MissionStatus.BLOCKED_CAPABILITY.value
        assert snap_legacy["mission"]["blocked_move"] is not None

        snap_26 = session.reconfigure_full_26_cubie(True)
        assert snap_26["full_26_cubie"] is True
        assert snap_26["physical_full_cube"] is True
        caps = session.get_capabilities()
        assert set(caps["physical_supported_moves"]) == set(LEGAL_MOVES)
        skills = {item["skill_id"]: item for item in caps["skills"]}
        assert skills["recover_preempted_turn_slice"]["implemented"] is True
    finally:
        session.close()
