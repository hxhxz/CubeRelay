"""Comprehensive M3-D test suite for Mission orchestration, SkillRegistry, DecisionEvents, API/WS, and frontend build."""

from __future__ import annotations

import os
import re
import time
from pathlib import Path
from typing import Iterator

import pytest
from fastapi.testclient import TestClient

from cube_relay.api import main as api_main
from cube_relay.cube.moves import LEGAL_MOVES
from cube_relay.mission import (
    DecisionEventLog,
    DecisionEventType,
    DeterministicMissionPlanner,
    MissionState,
    MissionStatus,
    MissionType,
    PlannerMode,
    SimulationSession,
    SkillRegistry,
    TraceEventLog,
    TraceEventType,
)

ROOT = Path(__file__).resolve().parents[1]


def _can_init_mujoco_gl() -> bool:
    """Fast check for environments with sandboxed macOS CGL disabled."""
    return os.environ.get("CUBERELAY_SKIP_GL_TESTS", "0") != "1"


@pytest.fixture(scope="module")
def live_session() -> Iterator[SimulationSession]:
    session = SimulationSession(seed=0, width=320, height=240, use_dedicated_thread=True)
    try:
        yield session
    finally:
        session.close()


def test_planner_differentiation_across_missions() -> None:
    registry = SkillRegistry()
    planner = DeterministicMissionPlanner()

    def _make_mission(mtype: MissionType) -> MissionState:
        return MissionState(
            mission_id=f"m-{mtype.value}",
            session_id="test-sess",
            mission_type=mtype,
            user_goal=mtype.value,
            success_criteria="done",
            status=MissionStatus.CREATED,
            created_at="00:00:00",
        )

    plan_inspect = planner.create_plan(_make_mission(MissionType.INSPECT_CUBE), registry, plan_id="p1")
    plan_u = planner.create_plan(_make_mission(MissionType.VERIFY_PHYSICAL_U_TURN), registry, plan_id="p2")
    plan_solve = planner.create_plan(_make_mission(MissionType.SOLVE_CUBE), registry, plan_id="p3")

    inspect_skills = [s.skill_id for s in plan_inspect.steps]
    u_skills = [s.skill_id for s in plan_u.steps]
    solve_skills = [s.skill_id for s in plan_solve.steps]

    assert inspect_skills == ["observe_workspace", "active_six_face_scan", "validate_cube_state"]
    assert "execute_physical_u_turn" not in inspect_skills

    assert u_skills == [
        "observe_workspace",
        "active_six_face_scan",
        "validate_cube_state",
        "compute_symbolic_plan",
        "execute_physical_u_turn",
        "verify_post_turn_state",
    ]
    assert solve_skills == [
        "observe_workspace",
        "active_six_face_scan",
        "validate_cube_state",
        "compute_symbolic_plan",
        "check_physical_capability",
    ]
    assert "execute_physical_u_turn" not in solve_skills


def test_skill_registry_symbolic_vs_physical_boundaries() -> None:
    registry = SkillRegistry()
    ready_scene = {
        "physical_u_scene_enabled": True,
        "cube_localized_and_scanned": True,
        "turn_station_available": True,
        "u_turns_completed": 0,
    }

    for move in LEGAL_MOVES:
        cap = registry.can_execute_physical_move(move, ready_scene)
        assert cap.symbolic_supported is True
        if move == "U":
            assert cap.supported is True
            assert cap.physical_model_supported is True
            assert cap.skill_id == "execute_physical_u_turn"
            assert cap.missing_preconditions == []
        else:
            assert cap.supported is False
            assert cap.physical_model_supported is False
            assert cap.unsupported_reason

    # Preconditions must gate physical "U"
    for missing_flag, bad_state in [
        ("physical_u_scene_enabled", {**ready_scene, "physical_u_scene_enabled": False}),
        ("cube_localized_and_scanned", {**ready_scene, "cube_localized_and_scanned": False}),
        ("turn_station_available", {**ready_scene, "turn_station_available": False}),
        ("single_u_turn_not_yet_consumed", {**ready_scene, "u_turns_completed": 1}),
    ]:
        cap = registry.can_execute_physical_move("U", bad_state)
        assert cap.supported is False
        assert cap.symbolic_supported is True
        assert missing_flag in cap.missing_preconditions

    audit = registry.audit_move_sequence(["U", "R", "U"], ready_scene)
    assert audit["all_supported"] is False
    assert audit["supported_count"] == 1
    assert audit["blocked_count"] == 2
    assert audit["first_blocked_move"] == "R"


def test_decision_event_log_monotonic_sim_time() -> None:
    log = DecisionEventLog()
    ev1 = log.append(
        session_id="s1",
        mission_id="m1",
        plan_id="p1",
        event_type=DecisionEventType.MISSION_CREATED,
        source="MissionController",
        sim_time=0.5,
        summary="created",
        decision_rationale_summary="goal accepted",
        status="CREATED",
    )
    # Even if an out-of-order lower sim_time is supplied, log keeps sim_time monotonic.
    ev2 = log.append(
        session_id="s1",
        mission_id="m1",
        plan_id="p1",
        event_type=DecisionEventType.PLAN_CREATED,
        source="DeterministicMissionPlanner",
        sim_time=0.2,
        summary="planned",
        decision_rationale_summary="plan ready",
        status="PLANNING",
    )
    assert ev1.sequence == 1
    assert ev2.sequence == 2
    assert ev2.sim_time >= ev1.sim_time  # type: ignore[operator]


def test_live_stream_throttle_requires_wall_and_simulation_progress() -> None:
    session = SimulationSession.__new__(SimulationSession)
    session.stream_interval_sec = 0.4
    session.stream_sim_interval_sec = 0.25
    session._last_stream_wall = 10.0
    session._last_stream_sim = 2.0

    # A slow render may consume the wall-clock interval, but the next 2 ms
    # physics step must not immediately render another three images.
    assert not session._stream_update_due(now_wall=10.8, now_sim=2.002)
    # Fast physics alone is still bounded by the wall-clock cadence.
    assert not session._stream_update_due(now_wall=10.2, now_sim=2.30)
    assert session._stream_update_due(now_wall=10.4, now_sim=2.25)


def test_hierarchical_trace_parentage_failure_and_replay_roundtrip() -> None:
    trace = TraceEventLog()
    mission = trace.append(
        mission_id="m1", session_id="s1", event_type=TraceEventType.MISSION,
        name="INSPECT_CUBE", source="test", status="RUNNING", sim_time=0.0,
    )
    composite = trace.append(
        mission_id="m1", session_id="s1", event_type=TraceEventType.COMPOSITE_SKILL,
        name="active_six_face_scan", source="test", status="RUNNING", sim_time=.4,
        parent_event_id=mission.event_id, skill_id="active_six_face_scan",
    )
    child = trace.append(
        mission_id="m1", session_id="s1", event_type=TraceEventType.PERCEPTION,
        name="observe_released", source="camera_perception", status="FAILED", sim_time=2.0,
        end_sim_time=2.2, parent_event_id=composite.event_id,
        skill_id="active_six_face_scan", failure_reason="NO_VALID_OBSERVATIONS",
        evidence={"unknown_before": 54, "unknown_after": 54},
    )
    assert composite.parent_event_id == mission.event_id
    assert child.parent_event_id == composite.event_id
    assert child.failure_reason == "NO_VALID_OBSERVATIONS"

    replay_payload = [event.model_dump(mode="json") for event in trace.events]
    restored = [type(child).model_validate(event) for event in replay_payload]
    assert [event.model_dump(mode="json") for event in restored] == replay_payload


def test_e2e_inspect_cube_never_runs_physical_turn(live_session: SimulationSession) -> None:
    snap = live_session.run_mission(MissionType.INSPECT_CUBE, seed=0)

    assert snap["mission"]["status"] == MissionStatus.COMPLETED.value
    assert snap["frame_source"] == "REAL_MUJOCO_RENDERER"
    assert str(snap["main_frame_url"]).startswith("data:image/jpeg;base64,")
    assert str(snap["wrist_rgb_url"]).startswith("data:image/jpeg;base64,")
    assert str(snap["wrist_depth_url"]).startswith("data:image/jpeg;base64,")
    assert snap["depth_range_m"] is not None
    assert snap["depth_range_m"][0] < snap["depth_range_m"][1]

    skill_ids = [ex["skill_id"] for ex in snap["skill_executions"]]
    assert skill_ids == ["observe_workspace", "active_six_face_scan", "validate_cube_state"]
    assert "execute_physical_u_turn" not in skill_ids

    obs = snap["last_observation_ref"]
    assert obs is not None
    assert obs["observed_count"] == 54
    assert obs["unknown_count"] == 0
    assert snap["cube_validation_status"] == "VALID_SOLVABLE"

    # Explicit no-fake-LLM banner check
    agent = snap["agent_state"]
    assert agent["llm_connected"] is False
    assert agent["planner_mode"] == PlannerMode.DETERMINISTIC_PLANNER.value
    assert agent["status_label"] == "当前由确定性任务规划器执行，LLM Agent 尚未接入"


def test_e2e_verify_physical_u_turn_real_physics_and_21_cell_verification(
    live_session: SimulationSession,
) -> None:
    snap = live_session.run_mission(MissionType.VERIFY_PHYSICAL_U_TURN, seed=0)

    assert snap["mission"]["status"] == MissionStatus.COMPLETED.value
    skill_ids = [ex["skill_id"] for ex in snap["skill_executions"]]
    assert "execute_physical_u_turn" in skill_ids
    assert "verify_post_turn_state" in skill_ids

    pv = snap["physical_verification"]
    assert pv is not None
    assert pv["actual_angle_deg"] > 85.0
    assert pv["min_base_contact_n"] > 0.5
    assert pv["min_turn_contact_n"] > 0.5
    assert pv["affected_21_verified"] is True
    assert pv["no_recolor"] is True
    assert pv["logical_state_unchanged"] is True
    assert pv["same_model_and_data"] is True
    assert pv["active_equalities"] == []

    # Released post-turn cameras never fabricate hidden D-face facelets
    obs = snap["last_observation_ref"]
    assert obs is not None
    assert obs["unknown_count"] == 9


def test_e2e_solve_cube_computes_solution_and_blocks_capability(
    live_session: SimulationSession,
) -> None:
    snap = live_session.run_mission(MissionType.SOLVE_CUBE, seed=0)

    assert snap["mission"]["status"] == MissionStatus.BLOCKED_CAPABILITY.value
    sol = snap["mission"]["symbolic_solution"]
    assert isinstance(sol, list) and len(sol) > 0
    assert snap["mission"]["blocked_move"] is not None
    assert len(snap["mission"]["blocked_moves"]) > 0
    assert snap["mission"]["blocked_reason"]

    skill_ids = [ex["skill_id"] for ex in snap["skill_executions"]]
    assert "compute_symbolic_plan" in skill_ids
    assert "check_physical_capability" in skill_ids
    assert "execute_physical_u_turn" not in skill_ids

    events = snap["decision_events"]
    seqs = [ev["sequence"] for ev in events]
    assert seqs == list(range(1, len(events) + 1))
    sim_times = [ev["sim_time"] for ev in events if ev["sim_time"] is not None]
    assert sim_times == sorted(sim_times)

    blocked_events = [ev for ev in events if ev["event_type"] == DecisionEventType.CAPABILITY_BLOCKED.value]
    assert len(blocked_events) >= 1

    # Zero fabricated LLM thought text across entire event stream and agent state
    serialized = repr(snap)
    for forbidden in ("Agent 正在思考", "Chain-of-thought", "模拟思考"):
        assert forbidden not in serialized


def test_fastapi_m3d_rest_and_websocket_consistency(live_session: SimulationSession) -> None:
    prev_session = api_main._m3d_session
    api_main.configure_m3d_session(live_session, default_seed=0)
    client = TestClient(api_main.app)
    try:
        # Legacy homepage remains intact
        res_legacy = client.get("/")
        assert res_legacy.status_code == 200

        # M3-D console & offline built assets are served
        res_console = client.get("/console")
        assert res_console.status_code == 200
        assert "/console-assets/bundle.js" in res_console.text
        assert "/console-assets/cuberelay_v4.css" in res_console.text

        assert client.get("/console-assets/bundle.js").status_code == 200
        assert client.get("/console-assets/cuberelay_v4.css").status_code == 200

        res_caps = client.get("/api/m3d/capabilities")
        assert res_caps.status_code == 200
        caps = res_caps.json()
        assert caps["physical_supported_moves"] == ["U"]
        assert "U" in caps["symbolic_supported_moves"] and "R" in caps["symbolic_supported_moves"]

        res_sel = client.post("/api/m3d/command", json={"type": "SELECT_MISSION", "mission_type": "INSPECT_CUBE"})
        assert res_sel.status_code == 200
        assert res_sel.json()["snapshot"]["selected_mission_type"] == "INSPECT_CUBE"

        # Test WebSocket state & decision_events parity
        with client.websocket_connect("/ws/session") as ws:
            msg = ws.receive_json()
            assert msg["type"] == "STATE_UPDATE"
            payload = msg["payload"]
            assert payload["frame_source"] == "REAL_MUJOCO_RENDERER"
            assert payload["agent_state"]["planner_mode"] == "DETERMINISTIC_PLANNER"

            ws.send_json({"type": "SELECT_MISSION", "mission_type": "SOLVE_CUBE"})
            msg2 = ws.receive_json()
            assert msg2["payload"]["selected_mission_type"] == "SOLVE_CUBE"

        # Start async INSPECT_CUBE via REST command and wait for completion
        start_resp = client.post(
            "/api/m3d/command",
            json={"type": "START_MISSION", "mission_type": "INSPECT_CUBE", "seed": 0},
        )
        assert start_resp.status_code == 200
        assert start_resp.json()["ok"] is True

        deadline = time.time() + 45.0
        final_state = client.get("/api/m3d/state").json()
        while (final_state.get("running") or final_state["mission"]["status"] not in {"COMPLETED", "FAILED", "BLOCKED_CAPABILITY"}) and time.time() < deadline:
            time.sleep(0.25)
            final_state = client.get("/api/m3d/state").json()

        assert final_state["mission"]["mission_type"] == "INSPECT_CUBE"
        assert final_state["mission"]["status"] == "COMPLETED"
        events = client.get("/api/m3d/events").json()
        assert len(events) == len(final_state["decision_events"])
        assert final_state["agent_state"]["last_skill_call"] in {ex["skill_id"] for ex in final_state["skill_executions"]}
    finally:
        api_main._m3d_session = prev_session


def test_frontend_source_sample_isolation_and_css_coverage() -> None:
    tsx = (ROOT / "web" / "console" / "cuberelay_v4.tsx").read_text(encoding="utf-8")
    css = (ROOT / "web" / "console" / "cuberelay_v4.css").read_text(encoding="utf-8")
    bundle = ROOT / "web" / "console" / "bundle.js"

    assert bundle.exists() and bundle.stat().st_size > 100_000

    # UI dual tabs, 3 Mission options, dynamic START_MISSION dispatch
    assert "Agent / 决策" in tsx
    assert "Skill / 执行" in tsx
    assert "INSPECT_CUBE" in tsx
    assert "VERIFY_PHYSICAL_U_TURN" in tsx
    assert "SOLVE_CUBE" in tsx
    assert "type: 'START_MISSION'" in tsx
    assert "type: 'START_TASK', task: 'single_u_turn'" not in tsx

    # Strict SAMPLE vs LIVE isolation
    assert "drawSyntheticSampleFrame" in tsx or "renderSynthetic" in tsx or "SYNTHETIC_SAMPLE" in tsx
    assert "if (next.frame_source === 'SYNTHETIC_SAMPLE')" in tsx
    assert "if (body.snapshot && body.snapshot.frame_source !== 'SYNTHETIC_SAMPLE')" in tsx

    # Verify CSS defines tokens present in TSX
    matches = re.findall(r"className\s*=\s*(?:\{`([^`]+)`\}|\"([^\"]+)\"|'([^']+)')", tsx)
    tokens: set[str] = set()
    for a, b, c in matches:
        s = a or b or c
        for q in re.findall(r"['\"]([^'\"]+)['\"]", s):
            tokens.update(q.split())
        tokens.update(re.sub(r"\$\{[^}]+\}", " ", s).split())
    enum_skip = {
        "AGENT",
        "BLOCKED",
        "COMPARISON",
        "DEPTH",
        "DETERMINISTIC_PLANNER",
        "LIVE",
        "OBSERVED",
        "PREDICTED",
        "REPLAY",
        "RGB",
        "SAMPLE",
        "SKILL",
    }
    css_unescaped = css.replace("\\", "")
    missing = [t for t in sorted(tokens) if t not in enum_skip and f".{t}" not in css_unescaped]
    assert missing == [], f"CSS tokens missing in web/console/cuberelay_v4.css: {missing}"
