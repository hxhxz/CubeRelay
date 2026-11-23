"""M5-Agent-Demo acceptance suite: Agent-sovereign human-robot relay with real 26-cubie MuJoCo & Gemini 3.8 Flash."""

from __future__ import annotations

import importlib.util
import json
import math
import os
from pathlib import Path
import threading
import time
from typing import Any

from fastapi.testclient import TestClient
import numpy as np
import pytest

from cube_relay.api import main as api_main
from cube_relay.cube.moves import CubeEngine
from cube_relay.cube.solver import CubeSolver
from cube_relay.cube.state import LEGAL_MOVES, SOLVED_FACELETS
from cube_relay.mission import (
    DualModelDecisionClient,
    FakeStructuredModelClient,
    LLMAgentDecisionPolicy,
    MissionStatus,
    MissionType,
    PlannerMode,
    RelayPhase,
    SkillRegistry,
    VLMInspectionLimits,
)
from cube_relay.mission.dual_model import AgentPlanningProvider, VLMPerceptionProvider
from cube_relay.mission.models import AgentActionDecision, AgentObservation
from cube_relay.mission.relay_cognition import (
    BeliefConservationAnalyzer,
    ExecutionContractSpec,
    FlipCostProfile,
    HRIDialogueInterpreter,
    HumanUtteranceSemantics,
    StaleResponseGuard,
    compute_candidate_solve_paths,
)
from cube_relay.mission.session import SimulationSession
from cube_relay.mission.vlm_client import load_local_env

ROOT = Path(__file__).resolve().parents[1]
ARTIFACTS_DIR = ROOT / "results" / "m5_agent_relay_demo"

_SKIP_MUJOCO_GL = (
    os.environ.get("CUBERELAY_SKIP_GL_TESTS", "0") == "1"
    or importlib.util.find_spec("mujoco") is None
)


def _export_mp4(frames: list[np.ndarray], out_path: Path, *, fps: int = 12) -> Path:
    import imageio.v2 as imageio

    out_path.parent.mkdir(parents=True, exist_ok=True)
    if not frames:
        raise AssertionError(f"No video frames recorded for {out_path.name}")
    # Ensure frame dimensions are divisible by 2 for libx264 yuv420p compatibility.
    with imageio.get_writer(str(out_path), fps=fps, codec="libx264", macro_block_size=1) as writer:
        for fr in frames:
            writer.append_data(np.asarray(fr, dtype=np.uint8))
    return out_path


# ---------------------------------------------------------------------------
# 1. Deterministic Unit Tests (Cognition, Flip Cost, Anti-Undo, Zero Leakage)
# ---------------------------------------------------------------------------


def test_belief_conservation_analyzer_18_moves_and_real_ambiguity() -> None:
    eng = CubeEngine()
    analyzer = BeliefConservationAnalyzer()
    base, _ = eng.scramble(seed=3, n=5)

    # All 18 single moves analyzed under bottom-occluded 45-sticker observation
    for mv in LEGAL_MOVES:
        after = eng.apply_move(base, mv)
        partial = after[:27] + ("?" * 9) + after[36:]
        res = analyzer.analyze(partial, previous_belief_54=base, last_suggested_moves=["U"])
        if mv == "L2":
            # On seed=3 scramble+L2, two unused bottom edges share visible side colors -> genuine ambiguity
            assert res.candidate_count >= 1
        else:
            assert res.deduced_54_unique is True, f"Expected unique deduction for {mv}, got {res}"
            assert res.ambiguous_facelet_count == 0
            assert res.deduced_facelets == after
            assert res.inferred_human_moves == [mv]
            assert res.human_deviation_detected is (mv != "U")

    # Multi-move D2 + R also locks cleanly and infers 2-move human transition visually
    base2 = eng.apply_moves(SOLVED_FACELETS, ["L", "F'", "R'", "D2", "U'", "U"])
    after2 = eng.apply_moves(base2, ["D2", "R"])
    partial2 = after2[:27] + ("?" * 9) + after2[36:]
    res2 = analyzer.analyze(partial2, previous_belief_54=base2, last_suggested_moves=["D2", "R"])
    assert res2.deduced_54_unique is True
    assert res2.deduced_facelets == after2
    assert res2.inferred_human_moves == ["D2", "R"]
    assert res2.human_deviation_detected is False


def test_flip_cost_profile_and_non_undo_alternative_paths() -> None:
    profile = FlipCostProfile.from_file(ROOT / "results" / "m5a1_calibration" / "flip_cost_profile.json")
    assert profile.marginal_time_s_by_flips[0] < profile.marginal_time_s_by_flips[1] < profile.marginal_time_s_by_flips[2]
    assert profile.mean_regrasps_by_flips[0] == 0.0
    assert profile.mean_regrasps_by_flips[2] >= 1.0

    eng = CubeEngine()
    # Suppose before handover we needed [D2, F, R]; human deviated with "R"
    pre_handover = eng.apply_moves(SOLVED_FACELETS, ["R'", "F'", "D2"])
    after_human_r = eng.apply_move(pre_handover, "R")
    summary = compute_candidate_solve_paths(
        after_human_r,
        top_face="U",
        bottom_face="D",
        flip_profile=profile,
        inferred_human_moves=["R"],
        state_history=[pre_handover, after_human_r],
    )
    assert summary["is_solved"] is False
    assert summary["undo_conflict_risk"] is True
    assert summary["undo_target_move"] == "R'"
    alt = summary["alternative_non_undo_solution"]
    assert isinstance(alt, list) and len(alt) >= 1
    assert alt[0][0] != "R"
    # Executing the alternative solution really solves the cube!
    assert eng.apply_moves(after_human_r, alt) == SOLVED_FACELETS


def test_stale_response_guard_and_contract_spec() -> None:
    contract = ExecutionContractSpec(max_target_drift_m=0.015, interrupt_on_human_chat_command=True)
    assert contract.mid_turn_recovery_mode == "UNWIND_TO_ZERO"

    guard = StaleResponseGuard()
    e0 = guard.issue_epoch()
    e1 = guard.invalidate("HUMAN_CHAT_INTERRUPT")
    assert e1 == e0 + 1
    assert guard.accept(e0) is False
    assert guard.stale_responses_discarded == 1
    assert guard.accept(e1) is True


def test_skill_registry_and_agent_relay_skills_safety_gate() -> None:
    reg = SkillRegistry(physical_full_cube=True)
    for sid in (
        "observe_tabletop_rapid",
        "scan_occluded_bottom_face",
        "request_vlm_scene_semantics",
        "commit_physical_moves",
        "handover_to_human",
        "ask_human_clarification",
        "verify_solved_cube_independent",
    ):
        desc = reg.get(sid)
        assert desc is not None and desc.implemented is True

    assert reg.validate_parameters("commit_physical_moves", {"moves": ["U", "R'"]}) == (True, None)
    ok_too_many, _ = reg.validate_parameters("commit_physical_moves", {"moves": ["U", "R", "F", "L"]})
    assert not ok_too_many
    ok_bad_move, _ = reg.validate_parameters("commit_physical_moves", {"moves": ["X"]})
    assert not ok_bad_move
    assert reg.validate_parameters(
        "handover_to_human",
        {"message_zh": "请执行 D2", "suggested_moves": ["D2"], "delegation_reason_zh": "省去2次翻面"},
    ) == (True, None)

    # Misaligned lattice blocks commit_physical_moves and handover_to_human until recovered
    misaligned = {
        "full_26_cubie_scene_enabled": True,
        "cube_localized_and_scanned": True,
        "turn_station_available": True,
        "is_lattice_aligned": False,
    }
    ok_commit, missing_c = reg.check_preconditions("commit_physical_moves", misaligned)
    assert not ok_commit and "station_lattice_aligned" in missing_c
    ok_handover, missing_h = reg.check_preconditions("handover_to_human", misaligned)
    assert not ok_handover and "station_lattice_aligned" in missing_h


def test_relay_ux_fixes_chat_takeover_camera_closeup_and_turn_indicator() -> None:
    """Verify M5-Demo UX upgrades: semantic HRI takeover auto-resume, closer closeup preset, turn indicator, and UI layout."""
    from threading import RLock
    from cube_relay.mission.session import CAMERA_PRESET_SPECS, SimulationSession
    from cube_relay.mission.models import MissionState

    # 1. Hardcoded substring marker methods must be completely removed from SimulationSession
    assert not hasattr(SimulationSession, "_chat_implies_robot_takeover")
    assert not hasattr(SimulationSession, "_is_pause_interrupt_text")

    # 2. Live human_send_chat routed via HRIDialogueInterpreter auto-resumes on YIELD_TURN_TO_ROBOT
    def _fake_hri_router(prompt: str, _img: str | None) -> dict[str, Any]:
        body = json.loads(prompt.split("\n", 1)[1])
        utt = body["utterance"]
        if "不玩了" in utt:
            return {
                "speech_act": "YIELD_TURN_TO_ROBOT",
                "requires_immediate_motion_interrupt": False,
                "should_wake_robot_from_human_turn": True,
                "persistent_constraints_to_add": ["剩余步骤全部由机器人复原"],
                "constraints_to_clear": [],
                "deviation_intent": "NONE",
                "rationale_zh": "人类明确交回控制权由机器人继续复原。",
                "confidence": 0.98,
            }
        return {
            "speech_act": "UPDATE_PREFERENCE_ONLY",
            "requires_immediate_motion_interrupt": False,
            "should_wake_robot_from_human_turn": False,
            "persistent_constraints_to_add": ["底面 D 由机器人执行，顶面或侧面留给人类"],
            "constraints_to_clear": [],
            "deviation_intent": "NONE",
            "rationale_zh": "仅更新分工偏好，保留当前人类回合。",
            "confidence": 0.96,
        }

    s = SimulationSession.__new__(SimulationSession)
    s._lock = RLock()
    s._hri_lock = RLock()
    s._running = False
    s.use_dedicated_thread = True
    s.seed = 0
    s.selected_mission_type = MissionType.RELAY_SOLVE_CUBE
    s._relay_phase = RelayPhase.WAITING_FOR_HUMAN_TURN
    s._relay_clarification_pending = False
    s._relay_clarification_question_zh = None
    s._relay_clarification_options = []
    s._relay_clarification_topic = None
    s._relay_active_constraints = []
    s._relay_latest_human_reply = None
    s._relay_latest_hri_semantics = None
    s._relay_human_dialog = []
    s._relay_human_turns_count = 0
    s._relay_round_number = 1
    s._relay_last_verified_54 = "UUUUUUUUURRRRRRRRRFFFFFFFFFDDDDDDDDDLLLLLLLLLBBBBBBBBB"
    s._subscribers = set()
    s._recorded_events = []
    s.scene_state = {"needs_rescan": False}
    s._hri_interpreter = HRIDialogueInterpreter(FakeStructuredModelClient("hri", _fake_hri_router))
    s.mission = MissionState(
        mission_id="msn-test",
        session_id="S-TEST",
        mission_type=MissionType.RELAY_SOLVE_CUBE,
        user_goal="test",
        success_criteria="test",
        status=MissionStatus.WAITING_FOR_HUMAN_TURN,
        created_at="00:00:00",
    )
    resumed_calls: list[str | None] = []
    s._append_relay_dialog = lambda *a, **kw: None  # type: ignore[method-assign]
    s._record_decision = lambda *a, **kw: None  # type: ignore[method-assign]
    s._emit_snapshot = lambda *a, **kw: {"ok": True}  # type: ignore[method-assign]
    s.get_snapshot = lambda: {"mission": {"status": s.mission.status.value}, "resumed": len(resumed_calls)}  # type: ignore[method-assign]
    s.human_finish_turn_async = lambda *, note=None: (resumed_calls.append(note), {"accepted": True, "snapshot": {"resumed": len(resumed_calls)}})[1]  # type: ignore[method-assign]

    snap_keep = s.human_send_chat("底面D我不方便拧，底面由你翻面拧掉，给我留顶面或侧面")
    assert resumed_calls == []
    assert snap_keep["resumed"] == 0

    snap_takeover = s.human_send_chat("我不玩了，你复原吧")
    assert len(resumed_calls) == 1
    assert snap_takeover["resumed"] == 1

    # Face assignment leaves the cadence untouched. Explicit delegation and
    # turn-length requests propagate from the structured router into the session.
    s._stale_guard = StaleResponseGuard()
    for utterance, override, expected in [
        ("底面 D 我不方便拧，底面动作由你拧", None, 3),
        ("我不玩了，剩下的全由你复原", "UNLIMITED", None),
        ("底面动作由你拧", None, None),
        ("接下来我们一人只拧一步", "STEP_1", 1),
        ("每轮拧两步", "STEP_2", 2),
        ("恢复每轮三步", "DEFAULT_3", 3),
    ]:
        def quota_reply(prompt, _img):
            payload = json.loads(prompt.split("\n", 1)[1])
            assert payload["utterance"] == utterance
            return dict(speech_act="UPDATE_PREFERENCE_ONLY", requires_immediate_motion_interrupt=False,
                        should_wake_robot_from_human_turn=False, turn_quota_override=override)
        s._hri_interpreter = HRIDialogueInterpreter(FakeStructuredModelClient("hri", quota_reply))
        s.human_send_chat(utterance)
        assert s.max_robot_moves_per_turn == expected

    # 3. Close-up camera preset & zoom lower bound
    assert CAMERA_PRESET_SPECS["overview"]["dist"] == 1.15
    assert CAMERA_PRESET_SPECS["cube_closeup"]["dist"] <= 0.30
    s.active_camera = "overview"
    s._user_camera_locked = False
    s._maybe_apply_relay_closeup_camera()
    assert s.active_camera == "cube_closeup"
    assert s.camera_distance_m == CAMERA_PRESET_SPECS["cube_closeup"]["dist"]

    # 4. Turn indicator metadata across phases
    ti_human = s._build_turn_indicator(RelayPhase.WAITING_FOR_HUMAN_TURN)
    assert ti_human["owner"] == "HUMAN" and ti_human["stage_index"] == 3
    assert len(ti_human["stage_labels"]) == 6
    ti_robot = s._build_turn_indicator(RelayPhase.ROBOT_ACTING)
    assert ti_robot["owner"] == "ROBOT" and ti_robot["stage_index"] == 1
    ti_done = s._build_turn_indicator(RelayPhase.RELAY_COMPLETED_VERIFIED)
    assert ti_done["owner"] == "DONE" and ti_done["is_terminal"] is True

    # 5. Frontend layout & controls verification
    tsx = (ROOT / "web" / "console" / "cuberelay_v4.tsx").read_text(encoding="utf-8")
    assert "useState<MissionType>('RELAY_SOLVE_CUBE')" in tsx
    assert "+放大" in tsx and "-缩小" in tsx
    assert "机器人相机 · Cube State · 遥测监控" in tsx
    assert "setTechDrawerOpen" in tsx and "setAgentDrawerOpen" in tsx and "setSkillDrawerOpen" in tsx
    assert "我不玩了，剩下的全部交给你复原！" in tsx


def test_relay_interrupt_pause_never_aborts_and_resumes_on_continue() -> None:
    """Reproduce uploaded bug: '停' causing SAFE_STOP must pause in WAITING_FOR_HUMAN_TURN (not FAILED),
    prune stale '停', and auto-resume when human replies '我拿走了魔方，执行U、F、R，然后放回原位，你继续'."""
    from threading import RLock
    from cube_relay.mission.dual_model import (
        AgentPlanningProvider,
        DualModelDecisionClient,
        FakeStructuredModelClient,
    )
    from cube_relay.mission.models import AgentObservation, MissionState, ObservationReference, PlanState
    from cube_relay.mission.planner import LLMAgentDecisionPolicy
    from cube_relay.mission.session import SimulationSession
    from cube_relay.mission.skill_registry import SkillRegistry

    fake_agent_client = FakeStructuredModelClient(
        "agent",
        lambda _p, _img: {
            "selected_action": "SAFE_STOP",
            "parameters": {},
            "reason_summary": "Human asked to pause ('停').",
            "evidence_observation_ids": ["obs-1"],
            "expected_outcome": "Pause safely for human",
            "completion_condition": "waiting_for_human",
            "confidence": 1.0,
        },
    )
    dual_client = DualModelDecisionClient(
        agent=AgentPlanningProvider(fake_agent_client),
        use_vlm_perception=False,
    )
    policy = LLMAgentDecisionPolicy(client=dual_client, guide_mode="GUIDE_MINIMAL", use_vlm_perception=False)
    registry = SkillRegistry(physical_full_cube=True)
    mission = MissionState(
        mission_id="msn-int",
        session_id="S-INT",
        mission_type=MissionType.RELAY_SOLVE_CUBE,
        user_goal="relay",
        success_criteria="solved",
        status=MissionStatus.EXECUTING,
        created_at="00:00:00",
    )
    plan = PlanState(
        plan_id="plan-int",
        mission_id="msn-int",
        mission_type=MissionType.RELAY_SOLVE_CUBE,
        planner_name="test",
        planner_mode=policy.mode,
        created_at="00:00:00",
        updated_at="00:00:00",
    )
    scene_aligned = {
        "simulation_initialized": True,
        "full_26_cubie_scene_enabled": True,
        "turn_station_available": True,
        "is_lattice_aligned": True,
        "cube_localized_and_scanned": True,
        "unknown_count": 0,
    }
    obs_ref = ObservationReference(
        observation_id="obs-1",
        frame_id="frm-1",
        sim_time=10.0,
        camera_name="overhead",
        observed_count=54,
        unknown_count=0,
        conflict_count=0,
        validation_status="VALID_SOLVABLE",
        summary="ready",
    )
    agent_obs = AgentObservation(
        observation_id="obs-1",
        mission_id="msn-int",
        session_id="S-INT",
        sim_time=10.0,
        frame_id="frm-1",
        camera_id="overhead",
        scene_summary={"aligned": True},
    )

    # 1a. SAFE_STOP while aligned in RELAY_SOLVE_CUBE redirects to handover_to_human (NOT FAIL_MISSION)
    sel1 = policy.select_next_action(mission, plan, registry, scene_aligned, obs_ref, agent_observation=agent_obs)
    assert sel1.decision_kind == "EXECUTE_STEP"
    assert sel1.skill_id == "handover_to_human"

    # A confirmed pause arriving during inference must park even if the next
    # model call would fail or choose another move. Recovery precedes handover.
    calls_before = len(fake_agent_client.traces)
    for aligned, skill in ((False, "recover_preempted_turn_slice"), (True, "handover_to_human")):
        paused = {**scene_aligned, "is_lattice_aligned": aligned,
                  "relay_cognitive_context": {"hri_context": {"paused_by_interrupt": True}}}
        sel = policy.select_next_action(mission, plan, registry, paused, obs_ref)
        assert sel.decision_kind == "EXECUTE_STEP" and sel.skill_id == skill
    assert len(fake_agent_client.traces) == calls_before

    # 1b. SAFE_STOP while misaligned redirects to recover_preempted_turn_slice(UNWIND_TO_ZERO) first
    scene_jammed = {**scene_aligned, "is_lattice_aligned": False}
    sel2 = policy.select_next_action(mission, plan, registry, scene_jammed, obs_ref, agent_observation=agent_obs)
    assert sel2.decision_kind == "EXECUTE_STEP"
    assert sel2.skill_id == "recover_preempted_turn_slice"
    assert sel2.parameters.get("mode") == "UNWIND_TO_ZERO"

    # 2. Session reflex pause ("停") -> paused_by_interrupt=True; then continuation message resumes & sets needs_rescan
    from cube_relay.mission.relay_cognition import StaleResponseGuard
    s = SimulationSession.__new__(SimulationSession)
    s._lock = RLock()
    s._hri_lock = RLock()
    s._stale_guard = StaleResponseGuard()
    s.recorded_video_frames = []
    s._init_relay_episode_state(clear_video=False)
    s._running = True
    s.use_dedicated_thread = True
    s.seed = 0
    s.selected_mission_type = MissionType.RELAY_SOLVE_CUBE
    s._relay_phase = RelayPhase.AGENT_REASONING
    s._subscribers = set()
    s._recorded_events = []
    s.scene_state = {"needs_rescan": False}
    s._hri_interpreter = HRIDialogueInterpreter(
        FakeStructuredModelClient(
            "hri",
            lambda _p, _img: {
                "speech_act": "YIELD_TURN_TO_ROBOT",
                "requires_immediate_motion_interrupt": False,
                "should_wake_robot_from_human_turn": True,
                "persistent_constraints_to_add": ["魔方已放回原位，请视觉重扫后继续求解"],
                "constraints_to_clear": [],
                "deviation_intent": "NONE",
                "rationale_zh": "人类完成桌面操作并交回机器人继续求解。",
                "confidence": 0.99,
            },
        )
    )
    s.mission = MissionState(
        mission_id="msn-int2",
        session_id="S-INT2",
        mission_type=MissionType.RELAY_SOLVE_CUBE,
        user_goal="relay",
        success_criteria="solved",
        status=MissionStatus.EXECUTING,
        created_at="00:00:00",
    )
    resumed: list[int] = []
    s._sim_time = lambda: 12.0  # type: ignore[method-assign]
    s._append_relay_dialog = lambda *a, **kw: None  # type: ignore[method-assign]
    s._record_decision = lambda *a, **kw: None  # type: ignore[method-assign]
    s._emit_snapshot = lambda *a, **kw: {"resumed": len(resumed)}  # type: ignore[method-assign]
    s.get_snapshot = lambda: {"mission": {"status": s.mission.status.value}, "resumed": len(resumed)}  # type: ignore[method-assign]
    s.human_finish_turn_async = lambda *, note=None: (s._prepare_human_finish_turn(note=note), resumed.append(1), {"accepted": True, "snapshot": {"resumed": len(resumed)}})[2]  # type: ignore[method-assign]

    # Step 2a: Human types exact single-word "停" while running -> <2ms reflex e-stop without polluting persistent constraints
    s.human_send_chat("停")
    assert s._relay_paused_by_interrupt is True
    assert "停" not in s._relay_active_constraints
    assert s._relay_latest_hri_semantics is not None
    assert s._relay_latest_hri_semantics["provenance"] == "REFLEX_ESTOP"

    # Step 2b: Robot hands over to human -> WAITING_FOR_HUMAN_TURN
    s._running = False
    s.mission.status = MissionStatus.WAITING_FOR_HUMAN_TURN
    s._relay_phase = RelayPhase.WAITING_FOR_HUMAN_TURN

    # Step 2c: Human sends exact continuation message from user bug report
    snap = s.human_send_chat("我拿走了魔方，执行U、F、R，然后放回原位，你继续")
    assert len(resumed) == 1
    assert snap["resumed"] == 1
    assert "停" not in s._relay_active_constraints
    assert any("继续求解" in c for c in s._relay_active_constraints)
    assert s.scene_state["needs_rescan"] is True
    assert s._relay_paused_by_interrupt is False


def test_relay_zero_action_pose_leakage_and_rest_ws_protocol(monkeypatch: pytest.MonkeyPatch) -> None:
    class _MockRelaySession:
        def __init__(self) -> None:
            self.full_26_cubie = True
            self.selected_mission_type = MissionType.RELAY_SOLVE_CUBE
            self.use_dedicated_thread = True
            self.relay_scramble_steps: int | str = 5
            self.phase = RelayPhase.WAITING_FOR_HUMAN_TURN
            self.clicks: list[str] = []
            self.dx = 0.0
            self.dy = 0.0
            self.dyaw = 0.0
            self.dialog: list[dict[str, Any]] = []
            self.interrupts = 0
            self._subs: set[Any] = set()

        def subscribe(self, cb: Any) -> None:
            self._subs.add(cb)

        def unsubscribe(self, cb: Any) -> None:
            self._subs.discard(cb)

        def get_snapshot(self) -> dict[str, Any]:
            return {
                "session_id": "MOCK-RELAY",
                "seed": 1,
                "full_26_cubie": self.full_26_cubie,
                "selected_mission_type": self.selected_mission_type.value,
                "task_status": "WAITING_FOR_HUMAN_TURN",
                "running": False,
                "relay_phase": self.phase.value,
                "relay_state": {
                    "enabled": True,
                    "phase": self.phase.value,
                    "scramble_steps": self.relay_scramble_steps,
                    "banner": {"tone": "amber", "title_zh": "人类回合", "subtitle_zh": "..."},
                    "delegation": {
                        "suggested_moves": ["D2"],
                        "completed_prefix_count": 1 if self.clicks == ["D2"] else 0,
                        "deviated_this_turn": bool(self.clicks and self.clicks[0] != "D2"),
                        "delegation_reason_zh": "D2 为 2-Flip",
                    },
                    "human_pad": {
                        "active": True,
                        "waiting_for_human": True,
                        "clicks_this_turn": list(self.clicks),
                        "can_undo": len(self.clicks) > 0,
                        "highlighted_next_move": "D2" if not self.clicks else None,
                    },
                    "perturbation": {"dx_m": self.dx, "dy_m": self.dy, "dyaw_deg": self.dyaw},
                    "hri": {"dialog_history": list(self.dialog), "clarification_pending": False},
                    "progress": {"initial_optimal_steps": 5, "remaining_optimal_steps": 4, "completion_pct": 20.0},
                    "belief": {"deduced_54_unique": True, "ambiguous_facelet_count": 0},
                    "contract": {"is_lattice_aligned": True},
                    "cognitive_stats": {"fast_loop_contract_interceptions": self.interrupts},
                },
            }

        def select_mission(self, mtype: str, **kwargs: Any) -> dict[str, Any]:
            self.selected_mission_type = MissionType(mtype)
            if "scramble_steps" in kwargs:
                self.relay_scramble_steps = kwargs["scramble_steps"]
            return self.get_snapshot()

        def set_scramble_steps(self, steps: int | str) -> dict[str, Any]:
            self.relay_scramble_steps = steps
            return self.get_snapshot()

        def set_planner_mode(self, *args: Any, **kwargs: Any) -> dict[str, Any]:
            return self.get_snapshot()

        def start_mission_async(self, mtype: str, **kwargs: Any) -> dict[str, Any]:
            return {"accepted": True, "mission_type": mtype}

        def human_apply_move(self, mv: str) -> dict[str, Any]:
            if mv not in LEGAL_MOVES:
                raise ValueError(f"illegal move {mv}")
            self.clicks.append(mv)
            return self.get_snapshot()

        def human_undo_move(self) -> dict[str, Any]:
            if not self.clicks:
                raise ValueError("empty undo stack")
            self.clicks.pop()
            return self.get_snapshot()

        def human_perturb_pose(self, dx_m: float = 0.0, dy_m: float = 0.0, dyaw_deg: float = 0.0) -> dict[str, Any]:
            self.dx, self.dy, self.dyaw = dx_m, dy_m, dyaw_deg
            return self.get_snapshot()

        def human_send_chat(self, text: str, **kwargs: Any) -> dict[str, Any]:
            if not text.strip():
                raise ValueError("empty")
            self.dialog.append({"role": "human", "text": text})
            return self.get_snapshot()

        def urgent_interrupt(self, reason: str = "") -> dict[str, Any]:
            self.interrupts += 1
            return self.get_snapshot()

        def human_finish_turn_async(self, *, note: str | None = None) -> dict[str, Any]:
            self.clicks.clear()
            self.phase = RelayPhase.AGENT_REASONING
            return {"accepted": True, "snapshot": self.get_snapshot()}

    mock = _MockRelaySession()
    monkeypatch.setattr(api_main, "get_m3d_session", lambda: mock)
    client = TestClient(api_main.app)

    r_sel = client.post("/api/m3d/command", json={"type": "SELECT_MISSION", "mission_type": "RELAY_SOLVE_CUBE", "scramble_steps": 6})
    assert r_sel.status_code == 200
    assert r_sel.json()["snapshot"]["relay_state"]["scramble_steps"] == 6

    r_mv = client.post("/api/m3d/command", json={"type": "HUMAN_APPLY_MOVE", "move": "D2"})
    assert r_mv.status_code == 200
    assert r_mv.json()["snapshot"]["relay_state"]["human_pad"]["clicks_this_turn"] == ["D2"]

    r_bad = client.post("/api/m3d/command", json={"type": "HUMAN_APPLY_MOVE", "move": "INVALID_Z"})
    assert r_bad.status_code == 422

    r_undo = client.post("/api/m3d/command", json={"type": "HUMAN_UNDO_MOVE"})
    assert r_undo.status_code == 200 and r_undo.json()["snapshot"]["relay_state"]["human_pad"]["clicks_this_turn"] == []

    r_pert = client.post("/api/m3d/command", json={"type": "HUMAN_PERTURB_POSE", "dx_m": 0.06, "dy_m": -0.04, "dyaw_deg": 20.0})
    assert r_pert.status_code == 200
    assert r_pert.json()["snapshot"]["relay_state"]["perturbation"]["dyaw_deg"] == 20.0

    r_chat = client.post("/api/m3d/command", json={"type": "HUMAN_SEND_CHAT", "text": "底面我不想拧"})
    assert r_chat.status_code == 200
    assert len(r_chat.json()["snapshot"]["relay_state"]["hri"]["dialog_history"]) == 1

    r_int = client.post("/api/m3d/command", json={"type": "URGENT_INTERRUPT", "reason": "test"})
    assert r_int.status_code == 200 and r_int.json()["snapshot"]["relay_state"]["cognitive_stats"]["fast_loop_contract_interceptions"] == 1

    with client.websocket_connect("/ws/session") as ws:
        init_msg = ws.receive_json()
        assert init_msg["type"] == "STATE_UPDATE"
        assert "relay_state" in init_msg["payload"]
        ws.send_json({"type": "HUMAN_FINISH_TURN"})
        upd = ws.receive_json()
        assert upd["payload"]["relay_phase"] == "AGENT_REASONING"


# ---------------------------------------------------------------------------
# 2. Offline MuJoCo 26-Cubie EGL Integration Test (Zero Network Cost)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("pause_during_planning", [False, True])
def test_mujoco_26cubie_agent_relay_protocol_and_zero_leakage(pause_during_planning: bool) -> None:
    if _SKIP_MUJOCO_GL:
        pytest.skip("MuJoCo GL tests skipped or mujoco not installed")

    def _scripted_agent(prompt: str, _img: str | None) -> dict[str, Any]:
        body = json.loads(prompt.split("\n", 1)[1])
        ctx = json.loads(body["planner_context"].split("\n", 1)[1])
        obs_id = ctx["observation_metadata"]["observation_id"]
        obs_state = ctx["observable_state"]
        rc = ctx["relay_cognitive_context"]
        belief = rc["belief_state"]
        paths = rc["candidate_paths_and_embodied_costs"]

        if not obs_state.get("cube_localized"):
            return AgentActionDecision(
                selected_action="observe_workspace",
                skill_id="observe_workspace",
                parameters={"camera_name": "overhead"},
                reason_summary="Localize cube first.",
                evidence_observation_ids=[obs_id],
                expected_outcome="cube localized",
                completion_condition="cube_localized=true",
                confidence=0.95,
            ).model_dump(mode="json")
        if not belief.get("previous_belief_54_known"):
            return AgentActionDecision(
                selected_action="scan_occluded_bottom_face",
                skill_id="scan_occluded_bottom_face",
                parameters={},
                reason_summary="Initial 54-sticker full scan.",
                evidence_observation_ids=[obs_id],
                expected_outcome="54/54 observed",
                completion_condition="current_54_known=true",
                confidence=0.95,
            ).model_dump(mode="json")
        if rc.get("needs_rescan"):
            return AgentActionDecision(
                selected_action="observe_tabletop_rapid",
                skill_id="observe_tabletop_rapid",
                parameters={},
                reason_summary="Human turn finished; run 1s rapid tabletop scan with conservation deduction.",
                evidence_observation_ids=[obs_id],
                expected_outcome="deduce 54/54 without 25s flip",
                completion_condition="deduced_54_unique=true",
                confidence=0.95,
            ).model_dump(mode="json")
        if paths.get("is_solved"):
            if not belief.get("post_solve_independent_verified"):
                return AgentActionDecision(
                    selected_action="verify_solved_cube_independent",
                    skill_id="verify_solved_cube_independent",
                    parameters={},
                    reason_summary="Verify 54/54 solved state via independent 6-face cameras.",
                    evidence_observation_ids=[obs_id],
                    expected_outcome="independent 54/54 verified",
                    completion_condition="post_solve_independent_verified=true",
                    confidence=0.99,
                ).model_dump(mode="json")
            return AgentActionDecision(
                selected_action="FINISH",
                skill_id=None,
                parameters={},
                reason_summary="Verified 100% physically solved.",
                evidence_observation_ids=[obs_id],
                expected_outcome="mission complete",
                completion_condition="COMPLETED",
                confidence=0.99,
            ).model_dump(mode="json")
        sol = list(paths.get("primary_kociemba_solution") or [])
        if len(sol) == 2 and sol[0] == "U" and sol[1] == "D2":
            return AgentActionDecision(
                selected_action="commit_physical_moves",
                skill_id="commit_physical_moves",
                parameters={"moves": ["U"]},
                reason_summary="Execute 0-Flip U first before 2-Flip D2.",
                evidence_observation_ids=[obs_id],
                expected_outcome="U completed",
                completion_condition="U applied",
                confidence=0.95,
            ).model_dump(mode="json")
        if pause_during_planning:
            assert not sess._relay_paused_by_interrupt, "Parking requested a second model decision"
            sess.human_send_chat("停")
        return AgentActionDecision(
            selected_action="handover_to_human",
            skill_id="handover_to_human",
            parameters={
                "suggested_moves": sol[:3],
                "message_zh": "请执行推荐动作后交回。",
                "delegation_reason_zh": "下一步含 2-Flip，委派人类高效完成。",
            },
            reason_summary="Handover before 2-Flip.",
            evidence_observation_ids=[obs_id],
            expected_outcome="human executes remaining move",
            completion_condition="waiting_for_human",
            confidence=0.95,
        ).model_dump(mode="json")

    fake_agent = FakeStructuredModelClient("AGENT", handler=_scripted_agent)
    dual = DualModelDecisionClient(
        perception=VLMPerceptionProvider(),
        agent=AgentPlanningProvider(fake_agent),
        use_vlm_perception=False,
    )
    policy = LLMAgentDecisionPolicy(
        client=dual,
        guide_mode="GUIDE_MINIMAL",
        limits=VLMInspectionLimits(max_vlm_calls=32, max_decision_rounds=32, max_sim_time_sec=400.0),
    )

    sess = SimulationSession(
        seed=1,
        width=320,
        height=240,
        full_26_cubie=True,
        planner=policy,
    )
    try:
        # 2-step scramble -> sol = ["U", "D2"] -> Agent executes U, delegates D2
        snap1 = sess.run_mission(
            MissionType.RELAY_SOLVE_CUBE,
            seed=1,
            scramble_moves=["D2", "U'"],
        )
        assert snap1["mission"]["status"] == MissionStatus.WAITING_FOR_HUMAN_TURN.value
        if pause_during_planning:
            assert snap1["relay_state"]["cognitive_stats"]["stale_responses_discarded"] == 1
            assert snap1["relay_state"]["delegation"]["suggested_moves"] == []
        else:
            assert snap1["relay_state"]["delegation"]["suggested_moves"] == ["D2"]

        # Verify STRICT zero action/pose leakage BEFORE human acts and AFTER human acts:
        sess.human_apply_move("D2")
        sess.human_perturb_pose(dx_m=0.06, dy_m=-0.04, dyaw_deg=20.0)
        for leaked_key in ("moves_this_turn", "dx_m", "dy_m", "dyaw_deg", "applied_dx_m"):
            assert leaked_key not in sess.scene_state
        obs_dict = sess.build_agent_observation().model_dump()
        assert "D2" not in json.dumps(obs_dict.get("scene_summary"))

        if pause_during_planning:
            sess._hri_interpreter = HRIDialogueInterpreter(FakeStructuredModelClient(
                "hri", lambda *_: dict(speech_act="YIELD_TURN_TO_ROBOT",
                                       requires_immediate_motion_interrupt=False,
                                       should_wake_robot_from_human_turn=True)
            ))
            snap2 = sess.human_send_chat("我拿走了魔方，执行D2，然后放回原位，你继续")
        else:
            snap2 = sess.human_finish_turn()
        assert snap2["mission"]["status"] == MissionStatus.COMPLETED.value
        assert snap2["relay_phase"] == RelayPhase.RELAY_COMPLETED_VERIFIED.value
        assert snap2["relay_state"]["cognitive_stats"]["rapid_glance_deduction_successes"] >= 1
        assert snap2["relay_state"]["progress"]["is_solved"] is True
        assert snap2["relay_state"]["progress"]["post_solve_independent_verified"] is True
        assert snap2["physical_verification"]["exact_54_solved"] is True
        assert snap2["physical_verification"]["no_recolor"] is True
        assert snap2["physical_verification"]["logical_state_unchanged"] is True
    finally:
        sess.close()


# ---------------------------------------------------------------------------
# 3. LIVE Online Gemini-3.8-Flash + MuJoCo 26-Cubie E2E Acceptance Trials
# ---------------------------------------------------------------------------


def _build_live_agent_session(*, seed: int = 1, width: int = 480, height: int = 320) -> SimulationSession:
    load_local_env(ROOT / ".env")
    policy = LLMAgentDecisionPolicy(
        guide_mode="GUIDE_MINIMAL",
        use_vlm_perception=False,
        limits=VLMInspectionLimits(
            max_vlm_calls=64,
            max_decision_rounds=64,
            max_sim_time_sec=600.0,
            allow_deterministic_fallback=False,
            allow_cv_only_on_vlm_failure=False,
        ),
    )
    if not policy.agent_provider.client.is_configured():
        pytest.skip("Live CUBERELAY_AGENT_* not configured")
    return SimulationSession(
        seed=seed,
        width=width,
        height=height,
        full_26_cubie=True,
        planner=policy,
        stream_interval_sec=0.12,
        stream_sim_interval_sec=0.12,
        record_video_frames=True,
    )


def _save_evidence(name: str, sess: SimulationSession, extra: dict[str, Any]) -> None:
    ARTIFACTS_DIR.mkdir(parents=True, exist_ok=True)
    mp4 = _export_mp4(list(sess.recorded_video_frames), ARTIFACTS_DIR / f"{name}.mp4", fps=12)
    snap = sess.get_snapshot()
    payload = {
        "trial": name,
        "mp4_path": str(mp4),
        "video_frames": len(sess.recorded_video_frames),
        "session_id": snap.get("session_id"),
        "mission": snap.get("mission"),
        "relay_phase": snap.get("relay_phase"),
        "relay_state": snap.get("relay_state"),
        "timing_metrics": snap.get("timing_metrics"),
        "agent_state": snap.get("agent_state"),
        "physical_verification": snap.get("physical_verification"),
        "decision_events": snap.get("decision_events"),
        "extra": extra,
    }
    (ARTIFACTS_DIR / f"{name}.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def run_live_trial_1_cooperative_rapid_glance() -> dict[str, Any]:
    """Trial 1: Live Gemini 3.8 Flash + 5-step scramble + dx=+6cm,dy=-4cm,dyaw=+20deg + 1s rapid glance -> 100% SOLVED."""
    sess = _build_live_agent_session(seed=11)
    try:
        # 5-step cross-axis scramble -> optimal sol = ['U', 'D2', 'R', 'F', "L'"]
        snap = sess.run_mission(
            MissionType.RELAY_SOLVE_CUBE,
            seed=11,
            scramble_moves=["L", "F'", "R'", "D2", "U'"],
        )
        assert snap["mission"]["status"] == MissionStatus.WAITING_FOR_HUMAN_TURN.value, snap
        suggested = list(snap["relay_state"]["delegation"]["suggested_moves"])
        assert len(suggested) >= 1, f"Expected recommended human moves, got {snap['relay_state']['delegation']}"

        # Zero leakage verification before human moves
        assert "moves_this_turn" not in sess.scene_state

        # Human executes recommended high-cost 2-Flip move(s) on 26-cubie pad + applies (+6cm, -4cm, +20 deg) perturbation
        moves_clicked: list[str] = []
        for mv in suggested[:2]:
            sess.human_apply_move(mv)
            moves_clicked.append(mv)
        sess.human_perturb_pose(dx_m=0.06, dy_m=-0.04, dyaw_deg=20.0)

        snap = sess.human_finish_turn()
        # Handle any extra round dynamically if Agent splits remaining work cleanly
        guard_rounds = 0
        while snap["mission"]["status"] == MissionStatus.WAITING_FOR_HUMAN_TURN.value and guard_rounds < 3:
            guard_rounds += 1
            if snap["relay_state"]["hri"]["clarification_pending"]:
                snap = sess.human_send_chat("请继续按推荐路径求解并独立核验", auto_resume=True)
            else:
                rem_sug = list(snap["relay_state"]["delegation"]["suggested_moves"])
                if not rem_sug:
                    rem_sug = ["R"]
                for mv in rem_sug:
                    sess.human_apply_move(mv)
                    moves_clicked.append(mv)
                snap = sess.human_finish_turn()

        assert snap["mission"]["status"] == MissionStatus.COMPLETED.value, snap["mission"]
        assert snap["relay_phase"] == RelayPhase.RELAY_COMPLETED_VERIFIED.value
        assert snap["relay_state"]["cognitive_stats"]["rapid_glance_deduction_successes"] >= 1
        assert snap["relay_state"]["progress"]["is_solved"] is True
        assert snap["relay_state"]["progress"]["post_solve_independent_verified"] is True
        assert snap["agent_state"]["llm_connected"] is True
        assert "gemini-3.8-flash" in str(snap["agent_state"]["agent_model_name"])
        assert snap["agent_state"]["fallback_triggered"] is False
        assert snap["physical_verification"]["exact_54_solved"] is True
        assert snap["physical_verification"]["no_recolor"] is True

        _save_evidence(
            "trial_1_cooperative_rapid_glance",
            sess,
            {"human_clicked_moves": moves_clicked, "perturbation_applied": {"dx_m": 0.06, "dy_m": -0.04, "dyaw_deg": 20.0}},
        )
        return snap
    finally:
        sess.close()


def run_live_trial_2_deviation_and_preference_flip() -> dict[str, Any]:
    """Trial 2: Live Gemini 3.8 Flash + wrong-face 'R' deviation -> clarification/non-undo + NL bottom refusal -> 100% SOLVED."""
    sess = _build_live_agent_session(seed=22)
    try:
        # 4-step cross-axis scramble -> optimal sol = ['U', 'D2', 'F', 'R']
        snap = sess.run_mission(
            MissionType.RELAY_SOLVE_CUBE,
            seed=22,
            scramble_moves=["R'", "F'", "D2", "U'"],
        )
        assert snap["mission"]["status"] == MissionStatus.WAITING_FOR_HUMAN_TURN.value, snap

        # Human ignores recommendation and clicks wrong face 'R' + perturbs tabletop pose, then finishes turn silently
        sess.human_apply_move("R")
        sess.human_perturb_pose(dx_m=-0.04, dy_m=0.05, dyaw_deg=-15.0)
        snap = sess.human_finish_turn()

        # Verify Agent either asks clarification instead of blind R' ping-pong OR cleanly takes new constraint
        assert snap["mission"]["status"] == MissionStatus.WAITING_FOR_HUMAN_TURN.value, snap
        # Inject natural language intent + bottom-face preference override
        snap = sess.human_send_chat(
            "我是故意拧 R 的别撤回，另外底面动作我不方便拧，剩下所有面都由你独自复原，不用再交给我。",
            auto_resume=True,
        )
        # If not auto-resumed (e.g. if Agent had already handed over rather than clarifying), finish turn cleanly
        if snap["mission"]["status"] == MissionStatus.WAITING_FOR_HUMAN_TURN.value:
            snap = sess.human_finish_turn()

        guard_rounds = 0
        while snap["mission"]["status"] == MissionStatus.WAITING_FOR_HUMAN_TURN.value and guard_rounds < 3:
            guard_rounds += 1
            snap = sess.human_send_chat(
                "底面动作我不方便拧，剩余所有步骤都请你独立完成，不用再传给我。",
                auto_resume=True,
            )
            if snap["mission"]["status"] == MissionStatus.WAITING_FOR_HUMAN_TURN.value:
                snap = sess.human_finish_turn()

        assert snap["mission"]["status"] == MissionStatus.COMPLETED.value, snap["mission"]
        assert snap["relay_phase"] == RelayPhase.RELAY_COMPLETED_VERIFIED.value
        assert snap["relay_state"]["progress"]["is_solved"] is True
        assert snap["relay_state"]["progress"]["post_solve_independent_verified"] is True
        assert snap["relay_state"]["max_robot_moves_per_turn"] is None
        # Ensure robot obeyed constraint & executed bottom/remaining moves physically without R/R' loop
        exec_moves = list(sess.scene_state.get("executed_physical_moves") or [])
        assert len(exec_moves) >= 2
        assert snap["agent_state"]["fallback_triggered"] is False
        assert snap["physical_verification"]["exact_54_solved"] is True
        assert snap["physical_verification"]["no_recolor"] is True

        _save_evidence(
            "trial_2_deviation_and_preference_flip",
            sess,
            {"executed_physical_moves": exec_moves},
        )
        return snap
    finally:
        sess.close()


def run_live_trial_3_urgent_preemption_handover() -> dict[str, Any]:
    """Trial 3: Live Gemini 3.8 Flash + mid-turn NL interrupt -> <50ms PREEMPTED_SAFE_HOLD -> UNWIND_TO_ZERO -> safe handover."""
    sess = _build_live_agent_session(seed=33)
    try:
        # Scramble whose optimal 1st move is 'U' (after initial 6-face scan, Agent commits ['U'] with ExecutionContract!)
        preempt_dispatched = threading.Event()
        turner = sess._backend.cube_26_turner
        assert turner is not None
        rj_qadr = int(sess._backend.model.jnt_qposadr[sess._backend._joint("turn_rotor_joint")])
        orig_post = turner.post_step_fn

        def _mid_slice_chat_trigger(_step_idx: int = 0) -> None:
            if orig_post is not None:
                orig_post()
            # Trigger urgent chat mid-slice once rotor has crossed 32 deg (~halfway through 90 deg turn)
            deg = abs(math.degrees(float(sess._backend.data.qpos[rj_qadr])))
            if deg >= 32.0 and not preempt_dispatched.is_set() and sess._active_cancellation_token is not None:
                preempt_dispatched.set()
                sess.human_send_chat("停一下！先别解了，把魔方安全放回桌面交给我")

        turner.post_step_fn = _mid_slice_chat_trigger
        try:
            # Test StaleResponseGuard cleanly alongside live physical preemption
            guard_epoch_before = sess._stale_guard.issue_epoch()
            snap = sess.run_mission(
                MissionType.RELAY_SOLVE_CUBE,
                seed=33,
                scramble_moves=["U'"],
            )
            assert preempt_dispatched.is_set(), "Mid-slice human interrupt trigger never fired!"
            assert sess._stale_guard.accept(guard_epoch_before) is False

            assert snap["mission"]["status"] == MissionStatus.WAITING_FOR_HUMAN_TURN.value, snap
            assert snap["relay_phase"] == RelayPhase.WAITING_FOR_HUMAN_TURN.value
            contract_info = snap["relay_state"]["contract"]
            preempt = contract_info["latest_preemption"]
            assert preempt is not None and preempt["preempted"] is True
            assert preempt["chunk_status"] == "PREEMPTED_SAFE_HOLD"
            assert preempt["recovery_mode"] == "UNWIND_TO_ZERO"
            assert snap["relay_state"]["robot_moves_this_turn"] == 0
            assert preempt["interrupt_to_hold_sim_ms"] is not None and float(preempt["interrupt_to_hold_sim_ms"]) < 50.0
            assert contract_info["is_lattice_aligned"] is True
            assert abs(float(contract_info["residual_slice_angle_deg"])) < 2.0
            assert snap["relay_state"]["cognitive_stats"]["fast_loop_contract_interceptions"] >= 1
            assert snap["agent_state"]["fallback_triggered"] is False

            _save_evidence(
                "trial_3_urgent_preemption_handover",
                sess,
                {"preemption_metrics": preempt, "stale_guard": contract_info["stale_guard"]},
            )
            return snap
        finally:
            turner.post_step_fn = orig_post
    finally:
        sess.close()


@pytest.mark.skipif(
    _SKIP_MUJOCO_GL or os.environ.get("CUBERELAY_RUN_LIVE_AGENT_DEMO", "0") != "1",
    reason="Set CUBERELAY_RUN_LIVE_AGENT_DEMO=1 inside MuJoCo EGL container to run live Gemini-3.8-Flash E2E trials",
)
def test_live_gemini_agent_relay_e2e_all_3_trials() -> None:
    s1 = run_live_trial_1_cooperative_rapid_glance()
    assert s1["mission"]["status"] == MissionStatus.COMPLETED.value

    s2 = run_live_trial_2_deviation_and_preference_flip()
    assert s2["mission"]["status"] == MissionStatus.COMPLETED.value

    s3 = run_live_trial_3_urgent_preemption_handover()
    assert s3["mission"]["status"] == MissionStatus.WAITING_FOR_HUMAN_TURN.value


# ---------------------------------------------------------------------------
# 4. M5-Demo.1: Real LLM Semantic HRI Router Adversarial Tests & On-Demand VLM
# ---------------------------------------------------------------------------


def test_hri_dialogue_interpreter_offline_contracts_and_on_demand_vlm(monkeypatch: pytest.MonkeyPatch) -> None:
    """Offline contract verification for HRIDialogueInterpreter, session integration, and on-demand VLM switch."""
    from threading import RLock
    from cube_relay.execution.action_chunk import CancellationToken
    from cube_relay.mission.events import DecisionEventLog, DecisionEventType
    from cube_relay.mission.models import AgentObservabilityState, MissionState, ObservationReference, PlanState

    # 1. Confirm hardcoded substring wordlists are completely removed from session.py
    session_src = (ROOT / "src" / "cube_relay" / "mission" / "session.py").read_text(encoding="utf-8")
    for forbidden in ("_chat_implies_robot_takeover", "_is_pause_interrupt_text", "takeover_markers", "keep_human_markers", "pause_markers"):
        assert forbidden not in session_src, f"Hardcoded wordlist symbol {forbidden!r} must be removed from session.py"

    # 2. <2ms reflex e-stop channel for pure single-word hardware stop tokens
    reflex_interp = HRIDialogueInterpreter(
        FakeStructuredModelClient("hri", lambda _p, _img: (_ for _ in ()).throw(AssertionError("Reflex e-stop should not invoke LLM")))
    )
    for tok in ("停", "急停", "stop", "halt", "STOP"):
        sem = reflex_interp.interpret(tok, relay_phase="ROBOT_ACTING", robot_running=True)
        assert sem.speech_act == "EMERGENCY_STOP"
        assert sem.requires_immediate_motion_interrupt is True
        assert sem.should_wake_robot_from_human_turn is False
        assert sem.provenance == "REFLEX_ESTOP"
        assert sem.latency_ms < 5.0

    # 3. Pure offline degraded mode (no API key configured) explicitly marks PROVENANCE=OFFLINE_FALLBACK
    for key in (
        "CUBERELAY_PERCEPTION_API_KEY",
        "CUBERELAY_HRI_ENDPOINT",
        "CUBERELAY_HRI_MODEL",
        "CUBERELAY_HRI_API_KEY",
        "CUBERELAY_AGENT_ENDPOINT",
        "CUBERELAY_AGENT_MODEL",
        "CUBERELAY_AGENT_API_KEY",
    ):
        monkeypatch.delenv(key, raising=False)
    offline_interp = HRIDialogueInterpreter()
    fb = offline_interp.interpret("干得不错，待会儿底面 D 留给我拧就行", relay_phase="ROBOT_ACTING", robot_running=True)
    assert fb.provenance == "OFFLINE_FALLBACK"
    assert fb.requires_immediate_motion_interrupt is False

    # 4. Adversarial routing contracts wired through SimulationSession.human_send_chat
    def _contract_router(prompt: str, _img: str | None) -> dict[str, Any]:
        body = json.loads(prompt.split("\n", 1)[1])
        utt = body["utterance"]
        if utt == "先别继续解，让我自己先转两步看看":
            return {
                "speech_act": "RETAIN_HUMAN_TURN",
                "requires_immediate_motion_interrupt": False,
                "should_wake_robot_from_human_turn": False,
                "persistent_constraints_to_add": [],
                "constraints_to_clear": [],
                "deviation_intent": "NONE",
                "rationale_zh": "否定语义要求暂缓机器人求解，保留人类桌面操作回合。",
                "confidence": 0.98,
            }
        if utt == "这几个块太绕了我搞不定，剩下的看你的啦":
            return {
                "speech_act": "YIELD_TURN_TO_ROBOT",
                "requires_immediate_motion_interrupt": False,
                "should_wake_robot_from_human_turn": True,
                "persistent_constraints_to_add": ["剩余步骤交由机器人接管复原"],
                "constraints_to_clear": [],
                "deviation_intent": "NONE",
                "rationale_zh": "口语表达交权，唤醒 Agent 视觉重扫接管。",
                "confidence": 0.97,
            }
        if utt == "干得漂亮，待会儿底面 D 动作留给我拧就行":
            return {
                "speech_act": "UPDATE_PREFERENCE_ONLY",
                "requires_immediate_motion_interrupt": False,
                "should_wake_robot_from_human_turn": False,
                "persistent_constraints_to_add": ["后续底面 D 动作留给人类执行"],
                "constraints_to_clear": [],
                "deviation_intent": "NONE",
                "rationale_zh": "运行中称赞并约定后续回合底面分工，不中断当前机械臂动作。",
                "confidence": 0.96,
            }
        if utt == "停一下，后面底面 D 全归你拧":
            return {
                "speech_act": "PAUSE_AND_HANDOVER",
                "requires_immediate_motion_interrupt": True,
                "should_wake_robot_from_human_turn": False,
                "persistent_constraints_to_add": ["后续底面 D 动作全部由机器人执行"],
                "constraints_to_clear": ["后续底面 D 动作留给人类执行"],
                "deviation_intent": "NONE",
                "rationale_zh": "复合指令：立即安全刹停当前动作，并独立提炼持久约束供后续规划遵守。",
                "confidence": 0.99,
            }
        raise AssertionError(f"Unexpected utterance in fake contract router: {utt!r}")

    s = SimulationSession.__new__(SimulationSession)
    s._lock = RLock()
    s._hri_lock = RLock()
    s._stale_guard = StaleResponseGuard()
    s.recorded_video_frames = []
    s._init_relay_episode_state(clear_video=False)
    s._running = False
    s.use_dedicated_thread = True
    s.seed = 0
    s.relay_scramble_steps = 5
    s._flip_cost_profile = FlipCostProfile.from_file()
    s.session_id = "S-HRI-CONTRACT"
    s.selected_mission_type = MissionType.RELAY_SOLVE_CUBE
    s.planner = LLMAgentDecisionPolicy(
        client=DualModelDecisionClient(
            agent=AgentPlanningProvider(FakeStructuredModelClient("agent", lambda _p, _img: {})),
            use_vlm_perception=True,
        ),
        guide_mode="GUIDE_FULL",
        use_vlm_perception=True,
    )
    s.agent_state = AgentObservabilityState(
        planner_mode=s.planner.mode,
        planner_name=s.planner.name,
        llm_connected=False,
        status_label="test",
    )
    s.event_log = DecisionEventLog()
    s._timeline_events = []
    s._active_decision_id = None
    s._current_run = None
    s._backend = None
    s._subscribers = set()
    s.plan = None
    s.scene_state = {"needs_rescan": False, "is_lattice_aligned": True, "residual_slice_angle_deg": 0.0}
    s._hri_interpreter = HRIDialogueInterpreter(FakeStructuredModelClient("hri", _contract_router, latency_ms=12.5))
    s.mission = MissionState(
        mission_id="msn-hri",
        session_id="S-HRI-CONTRACT",
        mission_type=MissionType.RELAY_SOLVE_CUBE,
        user_goal="relay",
        success_criteria="solved",
        status=MissionStatus.WAITING_FOR_HUMAN_TURN,
        created_at="00:00:00",
    )
    s._relay_phase = RelayPhase.WAITING_FOR_HUMAN_TURN
    resumed_count: list[int] = []
    s._sim_time = lambda: 5.0  # type: ignore[method-assign]
    s._emit_snapshot = lambda *a, **kw: {"resumed": len(resumed_count)}  # type: ignore[method-assign]
    s.get_snapshot = lambda: {"resumed": len(resumed_count), "relay_state": s._build_relay_state_snapshot()}  # type: ignore[method-assign]
    s.human_finish_turn_async = lambda *, note=None: (s._prepare_human_finish_turn(note=note), resumed_count.append(1), {"accepted": True, "snapshot": s.get_snapshot()})[2]  # type: ignore[method-assign]

    # Case A: Negation must NOT wake robot from human turn
    snap_neg = s.human_send_chat("先别继续解，让我自己先转两步看看")
    assert resumed_count == []
    assert snap_neg["relay_state"]["hri"]["latest_semantics"]["speech_act"] == "RETAIN_HUMAN_TURN"
    assert snap_neg["relay_state"]["hri"]["latest_semantics"]["should_wake_robot_from_human_turn"] is False
    assert snap_neg["relay_state"]["hri"]["dialog_history"][-1]["semantics"]["speech_act"] == "RETAIN_HUMAN_TURN"

    # Case B: Colloquial out-of-vocab handover MUST wake robot
    s.human_send_chat("这几个块太绕了我搞不定，剩下的看你的啦")
    assert len(resumed_count) == 1
    assert s._relay_latest_hri_semantics is not None
    assert s._relay_latest_hri_semantics["should_wake_robot_from_human_turn"] is True

    # Case C: Mid-motion preference remark must NOT cancel motion or invalidate stale_guard
    s._running = True
    s.mission.status = MissionStatus.EXECUTING
    s._relay_phase = RelayPhase.ROBOT_ACTING
    tok = CancellationToken()
    s._active_cancellation_token = tok
    s._active_execution_contract = ExecutionContractSpec(interrupt_on_human_chat_command=True)
    epoch_before = s._stale_guard.issue_epoch()

    s.human_send_chat("干得漂亮，待会儿底面 D 动作留给我拧就行")
    assert tok.is_cancelled() is False
    assert s._stale_guard.current_epoch == epoch_before
    assert "后续底面 D 动作留给人类执行" in s._relay_active_constraints
    assert s._relay_paused_by_interrupt is False

    # Case D: Compound interrupt + persistent constraint MUST cancel motion immediately AND preserve constraint after resume
    s.human_send_chat("停一下，后面底面 D 全归你拧")
    assert tok.is_cancelled() is True
    assert s._stale_guard.current_epoch == epoch_before + 1
    assert s._relay_paused_by_interrupt is True
    assert "后续底面 D 动作全部由机器人执行" in s._relay_active_constraints
    assert "后续底面 D 动作留给人类执行" not in s._relay_active_constraints

    # Park in WAITING_FOR_HUMAN_TURN and resume -> persistent constraint MUST survive _prepare_human_finish_turn!
    s._running = False
    s.mission.status = MissionStatus.WAITING_FOR_HUMAN_TURN
    s._relay_phase = RelayPhase.WAITING_FOR_HUMAN_TURN
    s._prepare_human_finish_turn()
    assert "后续底面 D 动作全部由机器人执行" in s._relay_active_constraints

    # Verify DecisionEvent audit stream recorded structured HRI semantics + latency
    hri_events = [ev for ev in s.event_log.events if ev.event_type == DecisionEventType.HUMAN_CHAT_RECEIVED]
    assert len(hri_events) == 4
    assert hri_events[-1].parameters["speech_act"] == "PAUSE_AND_HANDOVER"
    assert hri_events[-1].parameters["requires_immediate_motion_interrupt"] is True
    assert hri_events[-1].parameters["persistent_constraints_to_add"] == ["后续底面 D 动作全部由机器人执行"]
    assert hri_events[-1].model_latency_ms == 12.5

    # 5. Verify _ensure_relay_agent_planner forces use_vlm_perception=False by default (on-demand VLM only)
    assert s.planner.use_vlm_perception is True
    s._ensure_relay_agent_planner()
    assert s.planner.use_vlm_perception is False
    assert s.agent_state.use_vlm_perception is False
    assert s.agent_state.perception_model_name == "DISABLED(CV_ONLY)"

    # Verify on-demand VLM: dormant by default in RELAY_SOLVE_CUBE, activates ONLY when vlm_awakening_requested=True
    vlm_calls = 0

    def _fake_vlm(_p: str, _img: str | None) -> dict[str, Any]:
        nonlocal vlm_calls
        vlm_calls += 1
        return {
            "observation_id": "obs-vlm-1",
            "frame_id": "frm-vlm-1",
            "camera_id": "overhead",
            "cube_visible": True,
            "cube_relation_to_gripper": "on_table",
            "support_relation": "tabletop",
            "visible_regions": ["U", "F", "R"],
            "occluded_regions": ["D"],
            "information_gaps": [],
            "suggested_observations": [],
            "visual_conflicts": [],
            "confidence": 0.95,
            "summary": "cube clearly visible on tabletop",
        }

    def _fake_agent_sel(_p: str, _img: str | None) -> dict[str, Any]:
        return {
            "selected_action": "observe_workspace",
            "skill_id": "observe_workspace",
            "parameters": {"camera_name": "overhead"},
            "reason_summary": "localize cube",
            "evidence_observation_ids": ["obs-vlm-1"],
            "expected_outcome": "cube localized",
            "completion_condition": "cube_localized=true",
            "confidence": 0.95,
        }

    dual_on_demand = DualModelDecisionClient(
        perception=VLMPerceptionProvider(FakeStructuredModelClient("perception", _fake_vlm)),
        agent=AgentPlanningProvider(FakeStructuredModelClient("agent", _fake_agent_sel)),
        use_vlm_perception=False,
    )
    policy_on_demand = LLMAgentDecisionPolicy(client=dual_on_demand, guide_mode="GUIDE_MINIMAL", use_vlm_perception=False)
    reg = SkillRegistry(physical_full_cube=True)
    plan_od = PlanState(
        plan_id="plan-od",
        mission_id="msn-hri",
        mission_type=MissionType.RELAY_SOLVE_CUBE,
        planner_name="test",
        planner_mode=policy_on_demand.mode,
        created_at="00:00:00",
        updated_at="00:00:00",
    )
    obs_od = AgentObservation(
        observation_id="obs-vlm-1",
        mission_id="msn-hri",
        session_id="S-HRI-CONTRACT",
        sim_time=1.0,
        frame_id="frm-vlm-1",
        camera_id="overhead",
        rgb_image_data_url="data:image/jpeg;base64,/9j/4AAQSkZJRg==",
        scene_summary={},
    )
    obs_ref_od = ObservationReference(
        observation_id="obs-vlm-1",
        frame_id="frm-vlm-1",
        sim_time=1.0,
        camera_name="overhead",
        observed_count=0,
        unknown_count=54,
        conflict_count=0,
        validation_status="UNVERIFIED",
        summary="init",
    )
    # Normal round (vlm_awakening_requested=False) -> 0 VLM calls
    policy_on_demand.select_next_action(
        s.mission, plan_od, reg, {"simulation_initialized": True, "vlm_awakening_requested": False}, obs_ref_od, agent_observation=obs_od
    )
    assert vlm_calls == 0
    # Anomaly round (vlm_awakening_requested=True) -> 1 VLM call, then reverts to dormant
    policy_on_demand.select_next_action(
        s.mission, plan_od, reg, {"simulation_initialized": True, "vlm_awakening_requested": True}, obs_ref_od, agent_observation=obs_od
    )
    assert vlm_calls == 1
    assert policy_on_demand.use_vlm_perception is False


def test_hri_dialogue_interpreter_live_llm_adversarial_routing() -> None:
    """Real online LLM adversarial verification for the four Demo.1 scenarios plus a clarification reply."""
    load_local_env(ROOT / ".env")
    interp = HRIDialogueInterpreter()
    if not interp.client.is_configured():
        pytest.skip("Live CUBERELAY_HRI_* / CUBERELAY_AGENT_* not configured")

    # 1. Negation in human turn must NOT falsely trigger robot takeover
    r_neg = interp.interpret(
        "先别继续解，让我自己先转两步看看",
        relay_phase="WAITING_FOR_HUMAN_TURN",
        robot_running=False,
        clarification_pending=False,
        recent_dialog=[{"role": "agent", "text": "魔方已放到桌面，轮到你操作。"}],
    )
    if r_neg.provenance == "OFFLINE_FALLBACK" and r_neg.error_code in {"API_UNAVAILABLE", "MODEL_TIMEOUT"}:
        pytest.skip(f"Live LLM endpoint unreachable in current environment: {r_neg.error_code}")
    assert r_neg.provenance == "LIVE_LLM_ROUTER"
    assert r_neg.should_wake_robot_from_human_turn is False, r_neg

    # 2. Colloquial out-of-vocab handover MUST wake robot from human turn
    r_wake = interp.interpret(
        "这几个块太绕了我搞不定，剩下的看你的啦",
        relay_phase="WAITING_FOR_HUMAN_TURN",
        robot_running=False,
        clarification_pending=False,
        recent_dialog=[{"role": "agent", "text": "魔方已放到桌面，轮到你操作。"}],
    )
    assert r_wake.provenance == "LIVE_LLM_ROUTER"
    assert r_wake.should_wake_robot_from_human_turn is True, r_wake
    assert r_wake.speech_act == "YIELD_TURN_TO_ROBOT", r_wake

    # 3. Mid-motion preference remark must NOT interrupt robot arm motion, and must extract D-face preference
    r_pref = interp.interpret(
        "干得漂亮，待会儿底面 D 动作留给我拧就行",
        relay_phase="ROBOT_ACTING",
        robot_running=True,
        clarification_pending=False,
        current_action="commit_physical_moves",
    )
    assert r_pref.provenance == "LIVE_LLM_ROUTER"
    assert r_pref.turn_quota_override is None
    assert r_pref.requires_immediate_motion_interrupt is False, r_pref
    assert len(r_pref.persistent_constraints_to_add) >= 1, r_pref
    assert any(("D" in c or "底面" in c) for c in r_pref.persistent_constraints_to_add), r_pref

    # 4. Compound interrupt + persistent constraint MUST interrupt AND extract persistent D-face constraint cleanly
    r_comp = interp.interpret(
        "停一下，后面底面 D 全归你拧",
        relay_phase="ROBOT_ACTING",
        robot_running=True,
        clarification_pending=False,
        current_action="commit_physical_moves",
        active_constraints=list(r_pref.persistent_constraints_to_add),
    )
    assert r_comp.provenance == "LIVE_LLM_ROUTER"
    assert r_comp.requires_immediate_motion_interrupt is True, r_comp
    assert len(r_comp.persistent_constraints_to_add) >= 1, r_comp
    assert any(("D" in c or "底面" in c) for c in r_comp.persistent_constraints_to_add), r_comp
    assert all(c.strip() not in {"停一下", "停", "暂停"} for c in r_comp.persistent_constraints_to_add), r_comp


    r_clarify = interp.interpret(
        "刚才那步是我故意拧的，别撤回，按现在的状态继续",
        relay_phase="WAITING_FOR_HUMAN_TURN",
        clarification_pending=True,
    )
    assert r_clarify.provenance == "LIVE_LLM_ROUTER"
    assert r_clarify.deviation_intent == "INTENTIONAL_KEEP"
    assert r_clarify.should_wake_robot_from_human_turn
    for utterance, expected in [("我不玩了，剩下的全由你复原", "UNLIMITED"),
                                ("接下来我们一人只拧一步", "STEP_1")]:
        result = interp.interpret(utterance, relay_phase="WAITING_FOR_HUMAN_TURN")
        assert result.provenance == "LIVE_LLM_ROUTER"
        assert result.turn_quota_override == expected
    for result in (r_neg, r_wake, r_pref, r_comp, r_clarify):
        print(result.provenance, result.model_name, result.speech_act, result.latency_ms)


@pytest.mark.parametrize("value,expected", [(1, 1), (2, 2), (3, 3), ("unlimited", None)])
def test_turn_quota_rest_and_snapshot(monkeypatch, value, expected):
    sess = SimulationSession.__new__(SimulationSession)
    sess._hri_lock = threading.Lock()
    sess._stale_guard = StaleResponseGuard()
    sess.scene_state = {"relay_cognitive_context": {}}
    sess.robot_moves_this_turn = 2
    sess._emit_snapshot = lambda **_: {"relay_state": sess._turn_quota_state()}
    monkeypatch.setattr(api_main, "get_m3d_session", lambda: sess)
    client = TestClient(api_main.app)
    response = client.post("/api/m3d/command", json={"type": "SET_TURN_QUOTA", "quota": value})
    assert response.status_code == 200
    quota = response.json()["snapshot"]["relay_state"]
    assert quota["max_robot_moves_per_turn"] == expected and quota["robot_moves_this_turn"] == 2
    assert quota["remaining_turn_quota"] == (None if expected is None else max(0, expected - 2))
    assert client.post("/api/m3d/command", json={"type": "SET_TURN_QUOTA", "quota": 0}).status_code == 422


@pytest.mark.parametrize("scramble", [["R'", "F2", "U'"], ["L'", "R'", "F2", "U'"]])
def test_turn_quota_across_physical_batches(scramble):
    if _SKIP_MUJOCO_GL:
        pytest.skip("Requires MuJoCo")
    rejected = False

    def choose(prompt, _img):
        nonlocal rejected
        body = json.loads(prompt.split("\n", 1)[1])
        ctx = json.loads(body["planner_context"].split("\n", 1)[1])
        relay = ctx["relay_cognitive_context"]
        paths = relay["candidate_paths_and_embodied_costs"]
        params = {}
        if not ctx["observable_state"].get("cube_localized"):
            skill = "observe_workspace"
            params = {"camera_name": "overhead"}
        elif not relay["belief_state"]["previous_belief_54_known"]:
            skill = "scan_occluded_bottom_face"
        elif paths["is_solved"]:
            assert relay["belief_state"]["post_solve_independent_verified"]
            skill = "FINISH"
        else:
            skill = "commit_physical_moves"
            sol = paths["primary_kociemba_solution"]
            if relay["robot_moves_this_turn"] == 2 and not rejected:
                # Try two legal moves even if only one is needed to solve.
                params["moves"] = [sol[0], "U"]
                rejected = True
            else:
                params["moves"] = sol[:min(2, relay["remaining_turn_quota"])]
        return AgentActionDecision(selected_action=skill, parameters=params,
                                   reason_summary="exercise quota", expected_outcome=skill,
                                   completion_condition=skill, confidence=1,
                                   evidence_observation_ids=[ctx["observation_metadata"]["observation_id"]]).model_dump()

    client = DualModelDecisionClient(agent=AgentPlanningProvider(FakeStructuredModelClient("agent", choose)),
                                     use_vlm_perception=False)
    sess = SimulationSession(full_26_cubie=True, planner=LLMAgentDecisionPolicy(client=client))
    try:
        snap = sess.run_mission(MissionType.RELAY_SOLVE_CUBE, seed=1, scramble_moves=scramble)
        assert rejected
        assert any(event.get("failure_reason") == "EXCEEDS_REMAINING_TURN_QUOTA" for event in snap["decision_events"])
        assert snap["relay_state"]["robot_moves_this_turn"] == 3
        assert snap["relay_state"]["remaining_turn_quota"] == 0
        if len(scramble) == 3:
            assert snap["mission"]["status"] == "COMPLETED"
            assert snap["physical_verification"]["exact_54_solved"]
        else:
            assert snap["mission"]["status"] == "WAITING_FOR_HUMAN_TURN"
            ok, reason = sess.registry.validate_parameters("commit_physical_moves", {"moves": ["U"]}, sess.scene_state)
            assert not ok and reason.startswith("TURN_QUOTA_EXHAUSTED_MUST_HANDOVER")
            sess._prepare_human_finish_turn()
            assert sess.robot_moves_this_turn == 0 and sess.remaining_turn_quota == 3
    finally:
        sess.close()
