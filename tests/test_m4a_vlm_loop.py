"""Comprehensive M4-A test suite for Gemini VLM-in-the-Loop, Safety Gate, Trace, and Visual Ablation."""

from __future__ import annotations

import os
import socket
import urllib.error
from pathlib import Path
from typing import Any

import numpy as np
from PIL import Image
import pytest
from pydantic import ValidationError
from fastapi import HTTPException

from cube_relay.mission import (
    AgentObservation,
    DecisionEventType,
    DeterministicMissionPlanner,
    FakeGeminiVLMClient,
    GeminiMissionPlanner,
    MissionState,
    MissionStatus,
    MissionType,
    PlannerMode,
    SimulationSession,
    SkillRegistry,
    TraceEventType,
    VLMDecisionOutput,
    VLMInspectionLimits,
    _EnvLoadedGeminiClient,
)


def _dummy_jpeg_data_url(color: tuple[int, int, int] = (30, 120, 220)) -> str:
    import base64
    import io

    arr = np.full((32, 48, 3), color, dtype=np.uint8)
    buf = io.BytesIO()
    Image.fromarray(arr).save(buf, format="JPEG", quality=85)
    return "data:image/jpeg;base64," + base64.b64encode(buf.getvalue()).decode("ascii")


def _make_mission(mtype: MissionType = MissionType.INSPECT_CUBE) -> MissionState:
    return MissionState(
        mission_id="msn-test-m4a",
        session_id="TEST-SESSION",
        mission_type=mtype,
        user_goal="test goal",
        success_criteria="done",
        status=MissionStatus.OBSERVING,
        created_at="00:00:00",
    )


def _make_obs(
    *,
    obs_id: str = "obs-001",
    frame_id: str = "frm-001",
    sim_time: float = 1.0,
    rgb_url: str | None = None,
    unknown_count: int = 54,
    context_mode: str = "vision_plus_structured_state",
) -> AgentObservation:
    return AgentObservation(
        observation_id=obs_id,
        mission_id="msn-test-m4a",
        session_id="TEST-SESSION",
        sim_time=sim_time,
        frame_id=frame_id,
        camera_id="overhead",
        rgb_image_data_url=rgb_url if rgb_url is not None else _dummy_jpeg_data_url(),
        image_sha256="dummyhash",
        camera_metadata={"frame_source": "REAL_MUJOCO_RENDERER", "width": 320, "height": 240},
        observed_facelets="?" * unknown_count + "W" * (54 - unknown_count),
        observed_count=54 - unknown_count,
        unknown_facelet_indices=list(range(unknown_count)),
        observation_conflicts=[],
        context_mode=context_mode,
    )


# 1. Gemini Client interface & API key redaction
def test_gemini_client_env_loading_and_key_redaction(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    env_file = tmp_path / ".env"
    env_file.write_text(
        'CUBERELAY_VLM_ENDPOINT="https://example.googleapis.com/v1beta/openai/"\n'
        'CUBERELAY_VLM_MODEL="gemini-test-model"\n'
        'CUBERELAY_VLM_API_KEY="SECRET-TEST-KEY-123456"\n',
        encoding="utf-8",
    )
    monkeypatch.delenv("CUBERELAY_VLM_ENDPOINT", raising=False)
    monkeypatch.delenv("CUBERELAY_VLM_MODEL", raising=False)
    monkeypatch.delenv("CUBERELAY_VLM_API_KEY", raising=False)

    client = _EnvLoadedGeminiClient(env_path=env_file, load_env_file=True)
    assert client.is_configured() is True
    assert client.model == "gemini-test-model"
    assert "SECRET-TEST-KEY" not in repr(client)
    assert "<REDACTED>" in repr(client)

    # Unconfigured client refuses cleanly without throwing
    monkeypatch.delenv("CUBERELAY_VLM_API_KEY", raising=False)
    unconf = _EnvLoadedGeminiClient(endpoint="", model="", api_key="", load_env_file=False)
    assert unconf.is_configured() is False
    res = unconf.generate_decision("hello", _dummy_jpeg_data_url())
    assert res.error_code == "CLIENT_UNCONFIGURED"
    assert res.parsed_output is None


# 2. Structured Decision Schema validation
def test_structured_decision_schema_validation() -> None:
    valid = VLMDecisionOutput.model_validate({
        "action": "observe_visible_faces",
        "parameters": {"view_mode": "released"},
        "reason_summary": "Cube is sitting on table.",
        "expected_information_gain": "Reveal up to 45 visible stickers",
        "confidence": 0.91,
    })
    assert valid.action == "observe_visible_faces"

    # Extra unknown field rejected
    with pytest.raises(ValidationError):
        VLMDecisionOutput.model_validate({
            "action": "observe_visible_faces",
            "reason_summary": "ok",
            "joint_torques": [1, 2, 3],
        })

    # Confidence out of [0, 1] rejected
    with pytest.raises(ValidationError):
        VLMDecisionOutput.model_validate({
            "action": "observe_visible_faces",
            "reason_summary": "ok",
            "confidence": 1.5,
        })

    # Empty rationale rejected
    with pytest.raises(ValidationError):
        VLMDecisionOutput.model_validate({
            "action": "observe_visible_faces",
            "reason_summary": "",
        })


def test_real_vlm_activation_requires_server_password(monkeypatch: pytest.MonkeyPatch) -> None:
    from cube_relay.api.main import _dispatch_m3d_command

    class _SessionStub:
        def __init__(self) -> None:
            self.calls: list[tuple[str, str | None, str]] = []

        def get_snapshot(self) -> dict[str, Any]:
            return {"agent_state": {"planner_mode": "DETERMINISTIC_PLANNER"}}

        def set_planner_mode(
            self,
            planner_mode: str,
            *,
            model: str | None = None,
            context_mode: str = "vision_plus_structured_state",
        ) -> dict[str, Any]:
            self.calls.append((planner_mode, model, context_mode))
            return {"agent_state": {"planner_mode": planner_mode}}

    session = _SessionStub()
    command = {"type": "SET_PLANNER_MODE", "planner_mode": "LLM_AGENT"}

    monkeypatch.delenv("CUBERELAY_VLM_ENABLE_PASSWORD", raising=False)
    with pytest.raises(HTTPException) as not_configured:
        _dispatch_m3d_command(session, command)
    assert not_configured.value.status_code == 503
    assert session.calls == []

    monkeypatch.setenv("CUBERELAY_VLM_ENABLE_PASSWORD", "strong-test-password")
    with pytest.raises(HTTPException) as invalid:
        _dispatch_m3d_command(session, {**command, "enable_password": "wrong"})
    assert invalid.value.status_code == 403
    assert session.calls == []

    accepted = _dispatch_m3d_command(
        session,
        {**command, "enable_password": "strong-test-password", "model": "local-vlm"},
    )
    assert accepted["ok"] is True
    assert session.calls == [("LLM_AGENT", "local-vlm", "vision_plus_structured_state")]

    # Returning to deterministic mode never needs or retains the password.
    _dispatch_m3d_command(session, {"type": "SET_PLANNER_MODE", "planner_mode": "DETERMINISTIC_PLANNER"})
    assert session.calls[-1][0] == "DETERMINISTIC_PLANNER"


# 3 & 4. Input image source & observation_id / frame_id / sim_time alignment + stale check
def test_observation_alignment_missing_frame_and_stale_rejection() -> None:
    registry = SkillRegistry()
    fake = FakeGeminiVLMClient(responses=[{"action": "observe_workspace", "parameters": {}, "reason_summary": "go"}])
    planner = GeminiMissionPlanner(client=fake)
    mission = _make_mission()
    plan = planner.create_plan(mission, registry, plan_id="p1")

    # Missing AgentObservation -> CAMERA_FRAME_MISSING
    act_missing = planner.select_next_action(mission, plan, registry, {"simulation_initialized": True}, None, agent_observation=None)
    assert act_missing.decision_kind == "FAIL_MISSION"
    assert act_missing.failure_code == "CAMERA_FRAME_MISSING"

    # Missing RGB image in vision mode -> CAMERA_FRAME_MISSING
    obs_no_img = AgentObservation(
        observation_id="obs-noimg",
        mission_id="msn-test-m4a",
        session_id="TEST-SESSION",
        sim_time=1.0,
        frame_id="frm-noimg",
        camera_id="overhead",
        rgb_image_data_url=None,
    )
    act_no_rgb = planner.select_next_action(mission, plan, registry, {"simulation_initialized": True}, None, agent_observation=obs_no_img)
    assert act_no_rgb.decision_kind == "FAIL_MISSION"
    assert act_no_rgb.failure_code == "CAMERA_FRAME_MISSING"

    # Stale observation (obs.sim_time < scene_state.latest_sim_time) -> STALE_OBSERVATION
    obs_stale = _make_obs(sim_time=1.0)
    act_stale = planner.select_next_action(
        mission, plan, registry, {"simulation_initialized": True, "latest_sim_time": 2.5}, None, agent_observation=obs_stale
    )
    assert act_stale.decision_kind == "FAIL_MISSION"
    assert act_stale.failure_code == "STALE_OBSERVATION"


# 5. Skill parameter validation & precondition gates
def test_skill_registry_parameter_and_precondition_validation() -> None:
    reg = SkillRegistry()

    assert reg.validate_parameters("reorient_cube", {"axis": "pitch", "degrees": -90})[0] is True
    assert reg.validate_parameters("reorient_cube", {"axis": "yaw", "degrees": 90})[0] is True
    assert reg.validate_parameters("reorient_cube", {"axis": "roll", "degrees": 90})[0] is False
    assert reg.validate_parameters("reorient_cube", {"axis": "pitch", "degrees": 180})[0] is False
    assert reg.validate_parameters("reorient_cube", {"axis": "pitch", "degrees": 45, "extra": 1})[0] is False
    assert reg.validate_parameters("observe_workspace", {"camera_name": "invalid_cam"})[0] is False
    assert reg.validate_parameters("observe_visible_faces", {"view_mode": "xray"})[0] is False
    assert reg.validate_parameters("execute_physical_u_turn", {"move": "U"})[0] is True
    assert reg.validate_parameters("execute_physical_u_turn", {"move": "U'"})[0] is False

    # Preconditions
    ok_reg, miss_reg = reg.check_preconditions("regrasp_cube", {"cube_localized": True, "cube_released_on_table": False})
    assert not ok_reg and "cube_released_on_table" in miss_reg

    ok_rot, miss_rot = reg.check_preconditions("reorient_cube", {"cube_held_in_gripper": False})
    assert not ok_rot and "cube_held_in_gripper" in miss_rot

    ok_fin, miss_fin = reg.check_preconditions("finish_inspection", {"scan_attempted": True, "all_54_facelets_observed": False})
    assert not ok_fin and "all_54_facelets_observed" in miss_fin


# 6. Unsupported physical move rejection -> CAPABILITY_BLOCKED
def test_unsupported_physical_move_rejected_and_blocked() -> None:
    reg = SkillRegistry()
    mission = _make_mission(MissionType.SOLVE_CUBE)
    obs = _make_obs()

    for bad_payload in (
        {"action": "U'", "parameters": {}, "reason_summary": "try U'"},
        {"action": "R", "parameters": {}, "reason_summary": "try R"},
        {"action": "execute_physical_non_u_turn", "parameters": {"move": "F2"}, "reason_summary": "try F2"},
        {"action": "execute_physical_u_turn", "parameters": {"move": "U'"}, "reason_summary": "try U' via u turn"},
    ):
        fake = FakeGeminiVLMClient(responses=[bad_payload])
        planner = GeminiMissionPlanner(client=fake)
        plan = planner.create_plan(mission, reg, plan_id="p-blk")
        act = planner.select_next_action(mission, plan, reg, {"simulation_initialized": True}, None, agent_observation=obs)
        assert act.decision_kind == "BLOCK_CAPABILITY"
        assert "CAPABILITY_BLOCKED" in act.validation_result
        assert act.blocked_reason


# 7 & 8. Model timeout, invalid JSON, API unavailable, disallowed action & explicit fallback audit
def test_vlm_failure_modes_and_explicit_fallback_audit() -> None:
    reg = SkillRegistry()
    mission = _make_mission(MissionType.INSPECT_CUBE)
    obs = _make_obs()

    # Timeout without fallback -> FAIL_MISSION
    timeout_client = FakeGeminiVLMClient(responses=[socket.timeout("timed out")])
    planner_to = GeminiMissionPlanner(client=timeout_client, limits=VLMInspectionLimits(allow_deterministic_fallback=False))
    plan = planner_to.create_plan(mission, reg, plan_id="p-to")
    act_to = planner_to.select_next_action(mission, plan, reg, {"simulation_initialized": True}, None, agent_observation=obs)
    assert act_to.decision_kind == "FAIL_MISSION"
    assert act_to.failure_code == "MODEL_TIMEOUT"
    assert act_to.fallback_used is False

    # API unavailable without fallback -> FAIL_MISSION
    url_err_client = FakeGeminiVLMClient(responses=[urllib.error.URLError("connection refused")])
    planner_api = GeminiMissionPlanner(client=url_err_client, limits=VLMInspectionLimits(allow_deterministic_fallback=False))
    act_api = planner_api.select_next_action(mission, plan, reg, {"simulation_initialized": True}, None, agent_observation=obs)
    assert act_api.decision_kind == "FAIL_MISSION"
    assert act_api.failure_code == "API_UNAVAILABLE"

    # Invalid JSON -> INVALID_JSON
    bad_json_client = FakeGeminiVLMClient(responses=["not a json {"])
    planner_json = GeminiMissionPlanner(client=bad_json_client)
    act_json = planner_json.select_next_action(mission, plan, reg, {"simulation_initialized": True}, None, agent_observation=obs)
    assert act_json.decision_kind == "FAIL_MISSION"
    assert act_json.failure_code == "INVALID_JSON"

    # Disallowed action (including Mode A black-box active_six_face_scan or arbitrary tool)
    for bad_action in ("active_six_face_scan", "apply_joint_torques"):
        disallowed_client = FakeGeminiVLMClient(responses=[{
            "action": bad_action, "parameters": {}, "reason_summary": "bypass"
        }])
        planner_dis = GeminiMissionPlanner(client=disallowed_client)
        act_dis = planner_dis.select_next_action(mission, plan, reg, {"simulation_initialized": True}, None, agent_observation=obs)
        assert act_dis.decision_kind == "FAIL_MISSION"
        assert act_dis.failure_code == "DISALLOWED_ACTION"

    # Explicit fallback when enabled marks fallback_used=True (never counted as autonomous VLM)
    fb_client = FakeGeminiVLMClient(responses=[socket.timeout("timed out")])
    planner_fb = GeminiMissionPlanner(client=fb_client, limits=VLMInspectionLimits(allow_deterministic_fallback=True))
    act_fb = planner_fb.select_next_action(mission, plan, reg, {"simulation_initialized": True}, None, agent_observation=obs)
    assert act_fb.decision_kind == "EXECUTE_STEP"
    assert act_fb.skill_id == "observe_workspace"
    assert act_fb.fallback_used is True
    assert "FALLBACK_USED:MODEL_TIMEOUT" in act_fb.validation_result


# 13. Visual dependency ablation (minimal prompt omits state/truth, no_image, replaced_image)
def test_visual_dependency_ablation_and_information_leakage_prevention() -> None:
    reg = SkillRegistry()
    mission = _make_mission(MissionType.INSPECT_CUBE)
    img_released = _dummy_jpeg_data_url((200, 40, 40))
    img_held = _dummy_jpeg_data_url((40, 200, 40))
    obs_released = _make_obs(obs_id="obs-rel", frame_id="frm-rel", rgb_url=img_released)

    def _visual_handler(prompt: str, rgb_url: str | None, include_image: bool) -> dict[str, Any]:
        # Verify minimal prompt contains NO ground truth or held/released leakage flags
        assert "cube_released_on_table" not in prompt
        assert "cube_held_in_gripper" not in prompt
        assert "unknown_facelet_indices" not in prompt
        assert "_appearance_state" not in prompt
        if not include_image or rgb_url is None:
            return {"action": "observe_visible_faces", "parameters": {"view_mode": "auto"}, "reason_summary": "no image provided"}
        if rgb_url == img_released:
            return {"action": "regrasp_cube", "parameters": {}, "reason_summary": "cube on table"}
        return {"action": "reorient_cube", "parameters": {"axis": "pitch", "degrees": -90}, "reason_summary": "cube held"}

    permissive_state = {"simulation_initialized": True, "cube_localized": True, "cube_released_on_table": True, "cube_held_in_gripper": True}

    # Exp A: Real image (released) -> regrasp_cube
    client_a = FakeGeminiVLMClient(handler=_visual_handler)
    p_a = GeminiMissionPlanner(client=client_a, context_mode="vision_only_minimal")
    act_a = p_a.select_next_action(mission, p_a.create_plan(mission, reg, plan_id="pa"), reg, permissive_state, None, agent_observation=obs_released)
    assert act_a.skill_id == "regrasp_cube"
    assert client_a.calls[0]["image_included"] is True

    # Exp B: No image -> differs from Exp A and sends no image
    client_b = FakeGeminiVLMClient(handler=_visual_handler)
    p_b = GeminiMissionPlanner(client=client_b, context_mode="no_image")
    act_b = p_b.select_next_action(mission, p_b.create_plan(mission, reg, plan_id="pb"), reg, permissive_state, None, agent_observation=obs_released)
    assert act_b.skill_id == "observe_visible_faces"
    assert client_b.calls[0]["image_included"] is False

    # Exp C: Replaced image (held img injected) -> action flips to reorient_cube, and real scene_state gate blocks it!
    client_c = FakeGeminiVLMClient(handler=_visual_handler)
    p_c = GeminiMissionPlanner(client=client_c, context_mode="replaced_image", replacement_image_data_url=img_held)
    real_released_state = {"simulation_initialized": True, "cube_localized": True, "cube_released_on_table": True, "cube_held_in_gripper": False}
    act_c_blocked = p_c.select_next_action(mission, p_c.create_plan(mission, reg, plan_id="pc"), reg, real_released_state, None, agent_observation=obs_released)
    assert act_c_blocked.decision_kind == "FAIL_MISSION"
    assert act_c_blocked.failure_code == "PRECONDITION_MISSING"
    assert "cube_held_in_gripper" in act_c_blocked.validation_result


def test_all_mission_prompts_preserve_safe_inspection_phase_and_gate_yaw() -> None:
    reg = SkillRegistry()
    obs = _make_obs(unknown_count=9)
    scene = {
        "simulation_initialized": True,
        "cube_localized": True,
        "cube_held_in_gripper": True,
        "cube_released_on_table": False,
        "scan_attempted": True,
    }

    for mission_type in MissionType:
        mission = _make_mission(mission_type)
        fake = FakeGeminiVLMClient(responses=[{
            "action": "reorient_cube",
            "parameters": {"axis": "yaw", "degrees": 90},
            "reason_summary": "try yaw",
        }])
        planner = GeminiMissionPlanner(client=fake)
        prompt = planner._build_prompt(mission, reg, scene, obs, planner._allowed_skill_ids(mission, reg))
        assert "Required safe inspection phase" in prompt
        assert "Do not use yaw for the hidden-face scan" in prompt
        assert '"axis":"Literal[\'pitch\']"' in prompt

        action = planner.select_next_action(
            mission,
            planner.create_plan(mission, reg, plan_id=f"plan-{mission_type.value}"),
            reg,
            scene,
            None,
            agent_observation=obs,
        )
        assert action.decision_kind == "FAIL_MISSION"
        assert action.failure_code == "PARAMETER_OUT_OF_BOUNDS"
        assert action.validation_result == "REJECTED:INSPECTION_REORIENT_UNSUPPORTED"


# 7, 9, 10, 11. Real MuJoCo multi-step VLM-in-the-Loop, limits, planner switching, trace linkage, and new post-action observations
def test_vlm_in_the_loop_real_mujoco_multi_step_and_limits() -> None:
    if os.environ.get("CUBERELAY_SKIP_GL_TESTS", "0") == "1":
        pytest.skip("GL tests disabled")

    # 1) Planner switching & source distinction (Fake client never claims llm_connected=True)
    fake_protocol_client = FakeGeminiVLMClient(
        handler=lambda prompt, rgb, has_img: _scripted_mode_b_policy(prompt),
        simulated_latency_ms=15.0,
    )
    sess = SimulationSession(seed=0, width=320, height=240, planner=GeminiMissionPlanner(client=fake_protocol_client))
    try:
        # Run full Mode B VLM-controlled INSPECT_CUBE on real MuJoCo
        snap = sess.run_mission(MissionType.INSPECT_CUBE, seed=0)
        assert snap["mission"]["status"] == MissionStatus.COMPLETED.value
        assert snap["frame_source"] == "REAL_MUJOCO_RENDERER"
        assert snap["agent_state"]["planner_mode"] == PlannerMode.LLM_AGENT.value
        # Fake client must NOT falsely claim llm_connected=True
        assert snap["agent_state"]["llm_connected"] is False
        assert snap["agent_state"]["fallback_triggered"] is False

        skills = [ex["skill_id"] for ex in snap["skill_executions"]]
        assert "active_six_face_scan" not in skills
        assert skills == [
            "observe_workspace",
            "place_and_release",
            "observe_visible_faces",
            "regrasp_cube",
            "observe_visible_faces",
            "reorient_cube",
            "observe_visible_faces",
            "finish_inspection",
            "validate_cube_state",
        ]
        assert snap["last_observation_ref"]["observed_count"] == 54
        assert snap["last_observation_ref"]["unknown_count"] == 0
        assert snap["cube_validation_status"] == "VALID_SOLVABLE"

        # Verify >= 2 decisions received genuinely NEW post-action real camera images
        action_events = [
            ev for ev in snap["decision_events"] if ev["event_type"] == DecisionEventType.ACTION_SELECTED.value
        ]
        assert len(action_events) >= 2
        assert all(ev["source"] == "gemini_vlm" for ev in action_events)
        assert all(ev["skill_execution_id"] is not None for ev in action_events)

        # Check frame_ids & image_sha256 changed across physical actions
        frame_ids = [ev["input_frame_ids"][0] for ev in action_events]
        assert len(set(frame_ids)) == len(frame_ids)
        img_hashes = [tr.image_sha256 for tr in fake_protocol_client.traces]
        assert len(set(img_hashes)) >= 4

        # Verify hierarchical trace linkage for Mode B
        trace_events = snap["trace_events"]
        composites = [ev for ev in trace_events if ev["event_type"] == TraceEventType.COMPOSITE_SKILL.value]
        assert len(composites) == 1
        assert composites[0]["name"] == "vlm_controlled_inspection"
        children = [ev for ev in trace_events if ev["parent_event_id"] == composites[0]["event_id"]]
        assert len(children) >= 7

        # 2) Switch back to DeterministicMissionPlanner and check source=deterministic_policy
        snap_det_mode = sess.set_planner_mode("DETERMINISTIC_PLANNER")
        assert snap_det_mode["agent_state"]["planner_mode"] == "DETERMINISTIC_PLANNER"
        snap_det = sess.run_mission(MissionType.INSPECT_CUBE, seed=0)
        det_actions = [
            ev for ev in snap_det["decision_events"] if ev["event_type"] == DecisionEventType.ACTION_SELECTED.value
        ]
        assert all(ev["source"] == "deterministic_policy" for ev in det_actions)

        # 3) Enforce max_decision_rounds limit deterministically
        limit_client = FakeGeminiVLMClient(
            responses=[
                {"action": "observe_workspace", "parameters": {}, "reason_summary": "r1"},
                {"action": "place_and_release", "parameters": {}, "reason_summary": "r2"},
                {"action": "observe_visible_faces", "parameters": {}, "reason_summary": "r3"},
            ]
        )
        limited_planner = GeminiMissionPlanner(
            client=limit_client,
            limits=VLMInspectionLimits(max_decision_rounds=2, max_vlm_calls=10),
        )
        sess.planner = limited_planner
        snap_limited = sess.run_mission(MissionType.INSPECT_CUBE, seed=0)
        assert snap_limited["mission"]["status"] == MissionStatus.FAILED.value
        assert snap_limited["mission"]["failure_reason"] == "MAX_DECISION_ROUNDS_EXCEEDED"
    finally:
        sess.close()


def _scripted_mode_b_policy(prompt: str) -> dict[str, Any]:
    import json

    ctx = json.loads(prompt.split("\n", 1)[1])
    st = ctx["observable_state"]
    if not st["cube_localized"]:
        return {"action": "observe_workspace", "parameters": {"camera_name": "overhead"}, "reason_summary": "locate cube"}
    if not st["scan_attempted"]:
        return {"action": "place_and_release", "parameters": {}, "reason_summary": "place and release at scan station"}
    if not st["all_54_facelets_observed"]:
        if st["observed_count"] == 0:
            return {"action": "observe_visible_faces", "parameters": {"view_mode": "released"}, "reason_summary": "scan released faces"}
        if st["cube_released_on_table"]:
            return {"action": "regrasp_cube", "parameters": {}, "reason_summary": "regrasp to flip"}
        if st["cube_held_in_gripper"]:
            # If we just regrasped and haven't observed held yet or just rotated
            latest = ctx["observation_metadata"]["latest_skill_result"]
            if latest and latest["skill_id"] == "regrasp_cube":
                return {"action": "observe_visible_faces", "parameters": {"view_mode": "held"}, "reason_summary": "observe held faces"}
            if latest and latest["skill_id"] == "observe_visible_faces":
                return {"action": "reorient_cube", "parameters": {"axis": "pitch", "degrees": -90}, "reason_summary": "pitch -90"}
            return {"action": "observe_visible_faces", "parameters": {"view_mode": "held"}, "reason_summary": "observe reoriented face"}
    if not st["finish_inspection_done"]:
        return {"action": "finish_inspection", "parameters": {}, "reason_summary": "finish scan"}
    if not st["cube_state_validated"]:
        return {"action": "validate_cube_state", "parameters": {}, "reason_summary": "validate 54 facelets"}
    return {"action": "FINISH", "parameters": {}, "reason_summary": "mission complete"}
