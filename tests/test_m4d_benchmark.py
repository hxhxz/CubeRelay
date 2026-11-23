"""Comprehensive test suite for CubeRelay M4-D Task Agent Capability Benchmark."""

from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys
import zipfile

from fastapi.testclient import TestClient
from pydantic import ValidationError
import pytest

from cube_relay.api.main import app
from cube_relay.benchmark import (
    BENCHMARK_VERSION,
    AgentScorecard,
    BenchmarkAgentInput,
    BenchmarkCase,
    BenchmarkExporter,
    BenchmarkSourceType,
    CapabilityDimension,
    ClosedLoopBenchmarkRunner,
    DecisionRecord,
    DecisionReplayRunner,
    EvaluationOracle,
    ExecutionSourceLabel,
    FailureAttributionCategory,
    PlannerGroup,
    PromptGuideMode,
    VLMAblationCondition,
    assert_no_future_leakage,
    assert_no_oracle_in_prompt,
    assemble_benchmark_run,
    attribute_closed_loop_episode,
    attribute_replay_decision,
    build_closed_loop_scenarios,
    build_m4d_replay_cases,
    discover_m4c_bundles,
    extract_m4c_replay_slice,
    summarize_vlm_ablation,
    verify_benchmark_zip_integrity,
)
from cube_relay.mission.dual_model import (
    AgentPlanningProvider,
    DualModelDecisionClient,
    FakeStructuredModelClient,
    VLMPerceptionProvider,
)
from cube_relay.mission.models import (
    AgentObservation,
    MissionState,
    MissionStatus,
    MissionType,
    ObservationReference,
)
from cube_relay.mission.planner import (
    DeterministicMissionPlanner,
    GeminiMissionPlanner,
    LLMAgentDecisionPolicy,
    VLMInspectionLimits,
)
from cube_relay.mission.skill_registry import SkillRegistry
from cube_relay.mission.vlm_client import FakeGeminiVLMClient

ROOT = Path(__file__).resolve().parents[1]
_SKIP_GL = os.environ.get("CUBERELAY_SKIP_GL_TESTS") == "1"


def _make_fake_perception_factory():
    def _factory() -> FakeStructuredModelClient:
        def _handler(prompt: str, image_url: str | None) -> dict:
            return {
                "observation_id": "obs-fake",
                "frame_id": "frm-fake",
                "camera_id": "overhead",
                "cube_visible": bool(image_url),
                "cube_relation_to_gripper": "on_table_released",
                "support_relation": "table_top",
                "visible_regions": ["top", "front"],
                "occluded_regions": ["bottom_table_contact"],
                "information_gaps": ["bottom hidden"],
                "suggested_observations": ["regrasp_cube"],
                "visual_conflicts": [],
                "confidence": 0.75 if image_url else 0.1,
                "summary": "Fake VLM semantic test response.",
            }
        return FakeStructuredModelClient("PERCEPTION", _handler, model="fake-vlm-test")
    return _factory


def _make_context_aware_fake_agent_factory():
    """Fake agent factory for testing harness invariants (always flagged is_fake_provider=True)."""
    def _factory() -> FakeStructuredModelClient:
        def _handler(prompt: str, _image_url: str | None) -> dict:
            import re

            m_obs = re.search(r'"observation_id"\s*:\s*"([^"]+)"', prompt)
            obs_id = m_obs.group(1) if m_obs else "obs-l1-01"
            p_lower = prompt.lower()

            if "unsupported" in p_lower or "execute_physical_non_u_turn" in p_lower and "absent" in p_lower:
                return {
                    "selected_action": "CAPABILITY_BLOCKED",
                    "skill_id": None,
                    "parameters": {},
                    "reason_summary": "Required physical capability is unimplemented or disabled.",
                    "evidence_observation_ids": [obs_id],
                    "expected_outcome": "capability_blocked",
                    "completion_condition": "report limitation",
                    "confidence": 0.9,
                    "need_replan": False,
                }
            if '"cube_state_validated": true' in prompt or '"custom_completion_requirement": "cube_localized"' in prompt and '"cube_localized": true' in prompt:
                return {
                    "selected_action": "FINISH",
                    "skill_id": None,
                    "parameters": {},
                    "reason_summary": "Mission completion conditions satisfied.",
                    "evidence_observation_ids": [obs_id],
                    "expected_outcome": "mission_completed",
                    "completion_condition": "complete",
                    "confidence": 0.95,
                    "need_replan": False,
                }
            if '"cube_localized": false' in prompt:
                return {
                    "selected_action": "observe_workspace",
                    "skill_id": "observe_workspace",
                    "parameters": {"camera_name": "overhead"},
                    "reason_summary": "Cube is not yet localized.",
                    "evidence_observation_ids": [obs_id],
                    "expected_outcome": "cube localized",
                    "completion_condition": "cube localized",
                    "confidence": 0.85,
                    "need_replan": False,
                }
            return {
                "selected_action": "observe_visible_faces",
                "skill_id": "observe_visible_faces",
                "parameters": {"view_mode": "held"},
                "reason_summary": "Observe currently visible faces based on evidence.",
                "evidence_observation_ids": [obs_id],
                "expected_outcome": "facelets observed",
                "completion_condition": "54 facelets",
                "confidence": 0.7,
                "need_replan": False,
            }
        return FakeStructuredModelClient("AGENT", _handler, model="fake-agent-test")
    return _factory


def _make_fake_single_model_factory():
    def _factory() -> FakeGeminiVLMClient:
        def _handler(prompt: str, _img: str | None, _has_img: bool) -> dict:
            if '"cube_localized": false' in prompt:
                return {
                    "action": "observe_workspace",
                    "parameters": {"camera_name": "overhead"},
                    "reason_summary": "Cube unlocalized in image.",
                    "expected_information_gain": "locate cube",
                    "confidence": 0.8,
                }
            return {
                "action": "observe_visible_faces",
                "parameters": {"view_mode": "released"},
                "reason_summary": "Inspect visible released faces.",
                "expected_information_gain": "gain facelets",
                "confidence": 0.75,
            }
        return FakeGeminiVLMClient(model="fake-single-vlm-test", handler=_handler)
    return _factory


def test_01_benchmark_case_schema_and_serialization() -> None:
    cases = build_m4d_replay_cases()
    for case in cases:
        raw = case.model_dump(mode="json")
        reloaded = BenchmarkCase.model_validate(raw)
        assert reloaded.case_id == case.case_id
        agent_in = reloaded.to_agent_input()
        in_dump = agent_in.model_dump(mode="json")
        for forbidden_key in ("acceptable_decisions", "forbidden_decisions", "expected_behavior", "evaluation_rubric", "oracle_source"):
            assert forbidden_key not in in_dump

    with pytest.raises(ValidationError):
        BenchmarkAgentInput.model_validate({
            "case_id": "bad",
            "capability_dimension": CapabilityDimension.L1_SKILL_SELECTION,
            "difficulty": "easy",
            "source_type": BenchmarkSourceType.COUNTERFACTUAL_TEST,
            "mission": {},
            "initial_state": {},
            "acceptable_decisions": [],
        })


def test_02_case_loading_and_version_validation() -> None:
    cases = build_m4d_replay_cases()
    assert len(cases) >= 30
    ids = [c.case_id for c in cases]
    assert len(ids) == len(set(ids))
    assert all(c.benchmark_version == BENCHMARK_VERSION for c in cases)

    by_dim: dict[CapabilityDimension, int] = {}
    for c in cases:
        by_dim[c.capability_dimension] = by_dim.get(c.capability_dimension, 0) + 1
    assert by_dim[CapabilityDimension.L1_SKILL_SELECTION] >= 6
    assert by_dim[CapabilityDimension.L2_STATE_AWARE_PLANNING] >= 6
    assert by_dim[CapabilityDimension.L3_PERCEPTION_GROUNDED_REASONING] >= 6
    assert by_dim[CapabilityDimension.L4_FAILURE_RECOVERY] >= 6
    assert by_dim[CapabilityDimension.L5_GENERALIZATION] >= 6

    # Verify Case A..E coverage markers exist
    joined = "\n".join(ids)
    for marker in ("_A1_", "_A2_", "_A3_", "_A4_", "_A5_", "_A6_", "_B1_", "_B2_", "_B3_", "_B4_", "_C1_", "_C2_", "_C3_", "_C4_", "_D1_", "_D2_", "_D3_", "_D4_", "_D5_", "_D6_", "_E1_", "_E2_", "_E3_", "_E4_", "_E5_", "_E6_"):
        assert marker in joined, f"Missing required case coverage marker: {marker}"

    real_replays = [c for c in cases if c.source_type == BenchmarkSourceType.REAL_REPLAY]
    assert len(real_replays) >= 4
    cf_tests = [c for c in cases if c.source_type == BenchmarkSourceType.COUNTERFACTUAL_TEST]
    assert len(cf_tests) >= 10


def test_03_oracle_multi_acceptable_and_forbidden_rules() -> None:
    cases = {c.case_id: c for c in build_m4d_replay_cases()}
    oracle = EvaluationOracle()

    # Case B1 (L3_01): bottom face hidden on table -> regrasp_cube to flip
    case_b1 = cases["L3_01_B1_TABLE_OCCLUSION_BOTTOM"]
    res1, _ = oracle.evaluate(
        case=case_b1,
        planner_group=PlannerGroup.LLM_AGENT_CV_VLM,
        model_call_status="SUCCESS",
        schema_valid=True,
        decision_kind="EXECUTE_STEP",
        skill_id="regrasp_cube",
        raw_action="regrasp_cube",
        parameters={},
        evidence_references=[case_b1.current_observation["observation_id"]],
        planner_validation_result="PASSED",
        reason_summary="Cube sits on table hiding bottom; regrasp to expose bottom.",
    )
    assert res1.verdict == "PASS"

    # Case D6 (L4_06): accepts both CAPABILITY_BLOCKED and SAFE_STOP, forbids execute_physical_u_turn
    case_d6 = cases["L4_06_D6_NO_SAFE_LEGAL_RECOVERY"]
    for dk, raw in [("BLOCK_CAPABILITY", "CAPABILITY_BLOCKED"), ("SAFE_STOP", "SAFE_STOP")]:
        r_ok, s_ok = oracle.evaluate(
            case=case_d6,
            planner_group=PlannerGroup.LLM_AGENT_CV_VLM,
            model_call_status="SUCCESS",
            schema_valid=True,
            decision_kind=dk,
            skill_id=None,
            raw_action=raw,
            parameters={},
            evidence_references=[case_d6.current_observation["observation_id"]],
            planner_validation_result="CAPABILITY_BLOCKED" if dk == "BLOCK_CAPABILITY" else "STOP_REQUESTED",
            reason_summary="No safe recovery skill available.",
        )
        assert r_ok.verdict == "PASS"
        assert r_ok.safe_stop_correct is True
        assert s_ok.passed is True

    # Invalid parameter caught by Safety Gate / Oracle (L1_03)
    case_l1_03 = cases["L1_03_PARAM_BOUNDARY_PITCH_VS_YAW"]
    r_bad, s_bad = oracle.evaluate(
        case=case_l1_03,
        planner_group=PlannerGroup.LLM_AGENT_CV_ONLY,
        model_call_status="SUCCESS",
        schema_valid=True,
        decision_kind="EXECUTE_STEP",
        skill_id="reorient_cube",
        raw_action="reorient_cube",
        parameters={"axis": "yaw", "degrees": 45},
        evidence_references=[case_l1_03.current_observation["observation_id"]],
        planner_validation_result="REJECTED:PARAMETER_OUT_OF_BOUNDS",
        reason_summary="Invalid reorient parameter test.",
    )
    assert r_bad.verdict == "FAIL"
    assert s_bad.passed is False
    assert s_bad.parameter_valid is False


def test_04_failure_attribution_four_categories_and_separation() -> None:
    cases = {c.case_id: c for c in build_m4d_replay_cases()}
    oracle = EvaluationOracle()

    # 1. Agent chose illegal/forbidden skill -> AGENT_DECISION_FAILURE (+ SAFETY_GATE_REJECTION)
    c_l1_01 = cases["L1_01_A1_UNLOCALIZED_INIT"]
    r_bad, s_bad = oracle.evaluate(
        case=c_l1_01,
        planner_group=PlannerGroup.LLM_AGENT_CV_ONLY,
        model_call_status="SUCCESS",
        schema_valid=True,
        decision_kind="EXECUTE_STEP",
        skill_id="regrasp_cube",
        raw_action="regrasp_cube",
        parameters={},
        evidence_references=[c_l1_01.current_observation["observation_id"]],
        planner_validation_result="REJECTED:MISSING_PRECONDITIONS",
        reason_summary="Tried grasp before localization.",
    )
    attr1 = attribute_replay_decision(
        case=c_l1_01,
        oracle_result=r_bad,
        safety_validation=s_bad,
        model_call_status="SUCCESS",
    )
    assert attr1.primary_category == FailureAttributionCategory.AGENT_DECISION_FAILURE
    assert FailureAttributionCategory.SAFETY_GATE_REJECTION in attr1.secondary_categories

    # 2. Model API failure vs Schema Validation failure
    attr_api = attribute_replay_decision(
        case=c_l1_01,
        oracle_result=r_bad,
        safety_validation=s_bad,
        model_call_status="TIMEOUT",
        model_error_code="MODEL_TIMEOUT",
    )
    assert attr_api.primary_category == FailureAttributionCategory.MODEL_API_FAILURE

    attr_schema = attribute_replay_decision(
        case=c_l1_01,
        oracle_result=r_bad,
        safety_validation=s_bad,
        model_call_status="INVALID_JSON",
        model_error_code="INVALID_JSON",
    )
    assert attr_schema.primary_category == FailureAttributionCategory.SCHEMA_VALIDATION_FAILURE

    # 3. Closed-loop attribution: Skill failed contact verification without Safety Gate violation -> SKILL_EXECUTION_FAILURE
    snap_skill_fail = {
        "mission": {"status": "FAILED", "failure_reason": "GRASP_CONTACT_FAILED"},
        "skill_executions": [
            {"skill_id": "observe_workspace", "status": "VERIFIED"},
            {"skill_id": "regrasp_cube", "status": "FAILED", "failure_reason": "contact_fraction < 0.8"},
        ],
        "observations": [{"observed_count": 54}],
        "pose_estimates": [{"pose_estimate_id": "pose-1"}],
        "contact_verifications": [{"verification_result": False}],
        "decision_events": [{"event_type": "ACTION_SELECTED"}],
    }
    attr_cl_skill = attribute_closed_loop_episode(
        snapshot=snap_skill_fail,
        expected_capability_block=False,
        agent_violated_safety_gate=False,
        safety_gate_failure_code=None,
    )
    assert attr_cl_skill.primary_category == FailureAttributionCategory.SKILL_EXECUTION_FAILURE

    # 4. Closed-loop attribution: Localization blackout -> PERCEPTION_FAILURE
    snap_perc_fail = {
        "mission": {"status": "FAILED", "failure_reason": "CUBE_LOCALIZATION_FAILED"},
        "skill_executions": [{"skill_id": "observe_workspace", "status": "FAILED", "failure_reason": "blackout"}],
        "observations": [],
        "pose_estimates": [],
        "contact_verifications": [],
        "decision_events": [],
    }
    attr_cl_perc = attribute_closed_loop_episode(
        snapshot=snap_perc_fail,
        expected_capability_block=False,
        agent_violated_safety_gate=False,
        safety_gate_failure_code=None,
    )
    assert attr_cl_perc.primary_category == FailureAttributionCategory.PERCEPTION_FAILURE

    # 5. Closed-loop capability block -> CAPABILITY_LIMITATION with distinct explanation when expected
    snap_cap_block = {
        "mission": {"status": "BLOCKED_CAPABILITY", "failure_reason": "CAPABILITY_UNSUPPORTED"},
        "skill_executions": [],
        "observations": [],
        "pose_estimates": [],
        "contact_verifications": [],
        "decision_events": [],
    }
    attr_cap_expected = attribute_closed_loop_episode(
        snapshot=snap_cap_block,
        expected_capability_block=True,
        agent_violated_safety_gate=False,
        safety_gate_failure_code=None,
    )
    assert attr_cap_expected.primary_category == FailureAttributionCategory.CAPABILITY_LIMITATION
    assert "Expected capability boundary" in attr_cap_expected.explanation
    attr_cap_unexpected = attribute_closed_loop_episode(
        snapshot=snap_cap_block,
        expected_capability_block=False,
        agent_violated_safety_gate=False,
        safety_gate_failure_code=None,
    )
    assert attr_cap_unexpected.primary_category == FailureAttributionCategory.CAPABILITY_LIMITATION
    assert "missing physical capability" in attr_cap_unexpected.explanation


def test_05_vlm_semantic_ablation_runner_five_conditions() -> None:
    cases = [
        c for c in build_m4d_replay_cases()
        if c.capability_dimension == CapabilityDimension.L3_PERCEPTION_GROUNDED_REASONING
    ]
    runner = DecisionReplayRunner(
        mode="offline_fake",
        perception_client_factory=_make_fake_perception_factory(),
        agent_client_factory=_make_context_aware_fake_agent_factory(),
        single_vlm_client_factory=_make_fake_single_model_factory(),
    )
    ab_records = runner.run_vlm_ablation(cases, guide_mode=PromptGuideMode.GUIDE_MINIMAL, repeats=1)
    assert len(ab_records) == len(cases) * len(VLMAblationCondition)
    seen_conds = {r.vlm_ablation_condition for r in ab_records}
    assert seen_conds == set(VLMAblationCondition)
    summary = summarize_vlm_ablation(ab_records)
    assert set(summary["by_condition"].keys()) == {c.value for c in VLMAblationCondition}
    assert len(summary["case_matrix"]) == len(cases)


def test_06_causal_isolation_and_no_oracle_future_or_truth_leakage() -> None:
    cases = build_m4d_replay_cases()
    p_client = _make_fake_perception_factory()()
    a_client = _make_context_aware_fake_agent_factory()()
    dual = DualModelDecisionClient(
        perception=VLMPerceptionProvider(p_client),
        agent=AgentPlanningProvider(a_client),
        use_vlm_perception=True,
    )
    reg = SkillRegistry()
    mission = MissionState(
        mission_id="msn-leak-check",
        session_id="SES-LEAK",
        mission_type=MissionType.INSPECT_CUBE,
        user_goal="Inspect cube.",
        success_criteria="54 facelets validated",
        status=MissionStatus.OBSERVING,
        created_at="00:00:00",
    )

    for gmode in ("GUIDE_MINIMAL", "GUIDE_FULL"):
        policy = LLMAgentDecisionPolicy(client=dual, guide_mode=gmode, use_vlm_perception=True)
        for case in cases[:6]:
            agent_in = case.to_agent_input()
            assert_no_future_leakage(agent_in, case)
            obs = AgentObservation(
                observation_id=str(agent_in.current_observation.get("observation_id") or "obs-1"),
                mission_id="msn-leak-check",
                session_id="SES-LEAK",
                sim_time=float(agent_in.current_observation.get("sim_time") or 0.0),
                frame_id=str(agent_in.current_observation.get("frame_id") or "frm-1"),
                camera_id="overhead",
                observed_facelets=agent_in.cv_state.get("observed_facelets"),
                observed_count=int(agent_in.cv_state.get("observed_count", 0)),
                unknown_facelet_indices=list(agent_in.cv_state.get("unknown_facelet_indices") or []),
            )
            prompt = policy._build_prompt(
                mission, reg, dict(agent_in.initial_state), obs, policy._allowed_skill_ids(mission, reg)
            )
            assert_no_oracle_in_prompt(prompt)
            # Agent must NOT be given pre-computed future expected gain metrics per skill
            assert "future_information_gain" not in prompt
            assert '"expected_gain' not in prompt
            assert "expected_information_gain_per_skill" not in prompt
            if gmode == "GUIDE_MINIMAL":
                assert "Required safe inspection phase:" not in prompt
            else:
                assert "Required safe inspection phase:" in prompt

    # Future leakage raises AssertionError
    real_case = next(c for c in cases if c.source_type == BenchmarkSourceType.REAL_REPLAY)
    tampered = real_case.model_copy(deep=True)
    cutoff = float(tampered.provenance.get("cutoff_sim_time") or 1.0)
    tampered.observation_history.append({"observation_id": "obs-future", "sim_time": cutoff + 5.0})
    with pytest.raises(AssertionError, match="Temporal leakage"):
        tampered.to_agent_input()


def test_07_fake_provider_strictly_segregated_from_real_scorecards() -> None:
    cases = build_m4d_replay_cases()[:6]
    runner = DecisionReplayRunner(
        mode="offline_fake",
        perception_client_factory=_make_fake_perception_factory(),
        agent_client_factory=_make_context_aware_fake_agent_factory(),
        single_vlm_client_factory=_make_fake_single_model_factory(),
    )
    recs = runner.run_suite(
        cases,
        planner_groups=[PlannerGroup.DETERMINISTIC_BASELINE, PlannerGroup.LLM_AGENT_CV_VLM],
        guide_modes=[PromptGuideMode.GUIDE_MINIMAL],
    )
    run_res = assemble_benchmark_run(decision_records=recs, execution_mode="offline_fake")
    assert run_res.contains_fake_provider is True
    assert "DETERMINISTIC_BASELINE__GUIDE_MINIMAL" in run_res.real_scorecards
    assert "LLM_AGENT_CV_VLM__GUIDE_MINIMAL__FAKE" in run_res.fake_validation_scorecards
    assert all(not sc.is_fake_provider for sc in run_res.real_scorecards.values())
    assert all(sc.is_fake_provider and not sc.included_in_real_agent_ranking for sc in run_res.fake_validation_scorecards.values())

    with pytest.raises(ValueError, match="requires perception_client_factory"):
        bad_runner = DecisionReplayRunner(mode="offline_fake")
        bad_runner.run_single(cases[0], planner_group=PlannerGroup.LLM_AGENT_CV_VLM)


def test_08_cross_case_and_repeat_isolation() -> None:
    cases = build_m4d_replay_cases()[:3]
    runner = DecisionReplayRunner(
        mode="offline_fake",
        perception_client_factory=_make_fake_perception_factory(),
        agent_client_factory=_make_context_aware_fake_agent_factory(),
    )
    recs = runner.run_suite(
        cases,
        planner_groups=[PlannerGroup.LLM_AGENT_CV_VLM],
        guide_modes=[PromptGuideMode.GUIDE_MINIMAL],
        repeats=2,
    )
    assert len(recs) == 6
    by_case: dict[str, list[DecisionRecord]] = {}
    for r in recs:
        by_case.setdefault(r.benchmark_case_id, []).append(r)
    for cid, pair in by_case.items():
        assert len(pair) == 2
        assert pair[0].repeat_index == 1 and pair[1].repeat_index == 2
        assert pair[0].normalized_action == pair[1].normalized_action
        assert pair[0].prompt_sha256 == pair[1].prompt_sha256


def test_09_dynamic_skill_registry_constraints() -> None:
    cases = {c.case_id: c for c in build_m4d_replay_cases()}
    case_d5 = cases["L4_05_D5_REQUIRED_SKILL_NOT_IN_REGISTRY"]
    assert "regrasp_cube" in case_d5.removed_skills
    reg = SkillRegistry().clone(
        disabled_skills=case_d5.disabled_skills,
        removed_skills=case_d5.removed_skills,
    )
    assert reg.get("regrasp_cube") is None

    # Fake LLM returning the removed skill is caught by Safety Gate + Oracle!
    oracle = EvaluationOracle()
    res, safety = oracle.evaluate(
        case=case_d5,
        planner_group=PlannerGroup.LLM_AGENT_CV_ONLY,
        model_call_status="SUCCESS",
        schema_valid=True,
        decision_kind="EXECUTE_STEP",
        skill_id="regrasp_cube",
        raw_action="regrasp_cube",
        parameters={},
        evidence_references=[case_d5.current_observation["observation_id"]],
        planner_validation_result="PASSED",
        reason_summary="Try removed regrasp_cube.",
    )
    assert safety.passed is False
    assert res.legal_action is False
    assert res.verdict == "FAIL"


def test_10_safety_gate_integrity_in_benchmark() -> None:
    cases = {c.case_id: c for c in build_m4d_replay_cases()}
    oracle = EvaluationOracle()
    # Premature FINISH in L1_04 when validated=False must be blocked
    c_l1_04 = cases["L1_04_TERMINATION_PREMATURE_FINISH"]
    r_premature, s_premature = oracle.evaluate(
        case=c_l1_04,
        planner_group=PlannerGroup.LLM_AGENT_CV_VLM,
        model_call_status="SUCCESS",
        schema_valid=True,
        decision_kind="COMPLETE_MISSION",
        skill_id=None,
        raw_action="FINISH",
        parameters={},
        evidence_references=[c_l1_04.current_observation["observation_id"]],
        planner_validation_result="PASSED",
        reason_summary="Try finishing before validation.",
    )
    assert s_premature.passed is False
    assert s_premature.safety_gate_status == "REJECTED:PREMATURE_FINISH"
    assert r_premature.verdict == "FAIL"


def test_11_m4c_bundle_import_causal_cutoff_and_frame_linking(tmp_path: Path) -> None:
    bundles = discover_m4c_bundles(ROOT / "results" / "m4c_experiments" / "bundles")
    assert len(bundles) >= 1
    first_zip = next(iter(bundles.values()))
    sl = extract_m4c_replay_slice(first_zip, cutoff_sim_time=0.5)
    assert "audit_only_poses" not in json.dumps(sl)
    for obs in sl["observation_history"]:
        assert float(obs["sim_time"]) <= 0.5 + 1e-6
    if sl.get("selected_frame"):
        assert sl["rgb_image_data_url"].startswith("data:image/jpeg;base64,")

    # Verify synthetic ZIP bundle with future observations strictly filters future frames
    syn_zip = tmp_path / "syn_m4c.zip"
    with zipfile.ZipFile(syn_zip, "w") as zf:
        zf.writestr("config.json", json.dumps({"run_id": "run-syn", "seed": 7}))
        zf.writestr("frames.jsonl", json.dumps({"frame_id": "f0", "camera_id": "overhead", "sim_time": 0.1}) + "\n" + json.dumps({"frame_id": "f_future", "camera_id": "overhead", "sim_time": 9.9}) + "\n")
        zf.writestr("observations.jsonl", json.dumps({"observation_id": "o0", "sim_time": 0.1}) + "\n" + json.dumps({"observation_id": "o_future", "sim_time": 9.9}) + "\n")
        zf.writestr("audit_only_poses.csv", "sim_time,pos\n0.1,SECRET_TRUTH\n")
    syn_sl = extract_m4c_replay_slice(syn_zip, cutoff_sim_time=1.0)
    obs_ids = [o["observation_id"] for o in syn_sl["observation_history"]]
    assert obs_ids == ["o0"]
    assert "SECRET_TRUTH" not in json.dumps(syn_sl)


def test_12_prompt_guide_ablation_full_vs_minimal() -> None:
    cases = build_m4d_replay_cases()[:6]
    runner = DecisionReplayRunner(
        mode="offline_fake",
        perception_client_factory=_make_fake_perception_factory(),
        agent_client_factory=_make_context_aware_fake_agent_factory(),
    )
    r_min = runner.run_suite(cases, planner_groups=[PlannerGroup.LLM_AGENT_CV_VLM], guide_modes=[PromptGuideMode.GUIDE_MINIMAL])
    r_full = runner.run_suite(cases, planner_groups=[PlannerGroup.LLM_AGENT_CV_VLM], guide_modes=[PromptGuideMode.GUIDE_FULL])
    assert all(not r.prompt_contains_fixed_sequence for r in r_min)
    assert all(r.prompt_contains_fixed_sequence for r in r_full)
    assembled = assemble_benchmark_run(
        decision_records=r_min,
        guide_ablation_records=r_full,
        execution_mode="offline_fake",
    )
    assert len(assembled.fake_validation_scorecards) == 2


def test_13_deterministic_vs_llm_agent_and_cv_only_vs_cv_vlm() -> None:
    cases = build_m4d_replay_cases()
    runner = DecisionReplayRunner(mode="deterministic_only")
    det_recs = runner.run_suite(cases, planner_groups=[PlannerGroup.DETERMINISTIC_BASELINE])
    assert len(det_recs) == len(cases)
    run_res = assemble_benchmark_run(decision_records=det_recs, execution_mode="deterministic_only")
    det_sc = run_res.real_scorecards["DETERMINISTIC_BASELINE__GUIDE_MINIMAL"]
    assert det_sc.execution_source_label == ExecutionSourceLabel.DETERMINISTIC_RULE
    # Deterministic rule fails on L4 failure recovery counterfactuals (because it blindly returns pending blueprint step)
    l4_summary = det_sc.per_dimension[CapabilityDimension.L4_FAILURE_RECOVERY.value]
    assert l4_summary.failed_count >= 1


def test_14_single_model_incomparability_marking() -> None:
    cases = {c.case_id: c for c in build_m4d_replay_cases()}
    runner = DecisionReplayRunner(
        mode="offline_fake",
        perception_client_factory=_make_fake_perception_factory(),
        agent_client_factory=_make_context_aware_fake_agent_factory(),
        single_vlm_client_factory=_make_fake_single_model_factory(),
    )
    # C3 contradicts external Model A semantic output vs robot state -> SINGLE_MODEL is INCOMPARABLE
    rec_c3 = runner.run_single(cases["L3_07_C3_VLM_CONTRADICTS_ROBOT_STATE"], planner_group=PlannerGroup.SINGLE_MODEL_BASELINE)
    assert rec_c3.oracle_result.verdict == "INCOMPARABLE"
    assert rec_c3.incomparable_reason is not None

    # Running VLM_ABSENT on Single Model is also INCOMPARABLE
    rec_abl = runner.run_single(
        cases["L3_01_B1_TABLE_OCCLUSION_BOTTOM"],
        planner_group=PlannerGroup.SINGLE_MODEL_BASELINE,
        vlm_condition=VLMAblationCondition.VLM_ABSENT,
    )
    assert rec_abl.oracle_result.verdict == "INCOMPARABLE"


def test_15_closed_loop_forbidden_vlm_conditions_rejected(tmp_path: Path) -> None:
    cl_runner = ClosedLoopBenchmarkRunner(mode="offline_fake", output_dir=tmp_path)
    scen = build_closed_loop_scenarios()[0]
    for forbidden_cond in (VLMAblationCondition.VLM_SWAPPED, VLMAblationCondition.VLM_CONTRADICTORY):
        with pytest.raises(ValueError, match="Forbidden VLM ablation condition"):
            cl_runner.run_scenario(scen, planner_group=PlannerGroup.LLM_AGENT_CV_VLM, vlm_condition=forbidden_cond)


@pytest.mark.skipif(_SKIP_GL, reason="GL tests disabled")
def test_16_closed_loop_mujoco_real_episode_with_source_labels(tmp_path: Path) -> None:
    cl_runner = ClosedLoopBenchmarkRunner(
        mode="offline_fake",
        output_dir=tmp_path,
        width=240,
        height=160,
        perception_client_factory=_make_fake_perception_factory(),
        agent_client_factory=_make_context_aware_fake_agent_factory(),
    )
    scenarios = {s["scenario_id"]: s for s in build_closed_loop_scenarios()}
    ep_det = cl_runner.run_scenario(
        scenarios["CL_01_NORMAL_INSPECT_SEED0"],
        planner_group=PlannerGroup.DETERMINISTIC_BASELINE,
    )
    assert ep_det.mission_status == "COMPLETED"
    assert ep_det.goal_achieved is True
    assert ExecutionSourceLabel.REAL_MUJOCO in ep_det.execution_source_labels
    assert ep_det.zip_path is not None and Path(ep_det.zip_path).exists()

    ep_cap = cl_runner.run_scenario(
        scenarios["CL_05_UNSUPPORTED_SOLVE_CAPABILITY"],
        planner_group=PlannerGroup.LLM_AGENT_CV_VLM,
    )
    assert ExecutionSourceLabel.FAKE_PROVIDER in ep_cap.execution_source_labels
    assert ExecutionSourceLabel.REAL_MUJOCO in ep_cap.execution_source_labels


def test_17_benchmark_zip_export_sha256_redaction_and_verify(tmp_path: Path) -> None:
    cases = build_m4d_replay_cases()[:4]
    runner = DecisionReplayRunner(mode="deterministic_only")
    recs = runner.run_suite(cases, planner_groups=[PlannerGroup.DETERMINISTIC_BASELINE])
    # Inject synthetic secret into reason_summary to test redaction invariant
    tampered_rec = recs[0].model_copy(update={"reason_summary": "debug token sk-testSecretKey1234567890abcd"})
    run_res = assemble_benchmark_run(decision_records=[tampered_rec, *recs[1:]], execution_mode="deterministic_only")

    written = BenchmarkExporter.write_run_directory(run_res, out_dir=tmp_path / "run_exp", cases=cases, export_zip=True)
    zip_path = written["zip"]
    check = verify_benchmark_zip_integrity(zip_path)
    assert check["ok"] is True
    assert check["secret_hits"] == []
    assert check["reference_integrity"]["ok"] is True

    # Ensure raw secret was redacted in exported files
    exported_jsonl = (tmp_path / "run_exp" / "decision_records.jsonl").read_text(encoding="utf-8")
    assert "sk-testSecretKey" not in exported_jsonl

    # Corrupt a file in ZIP and verify tamper detection triggers
    corrupt_zip = tmp_path / "corrupt.zip"
    with zipfile.ZipFile(zip_path, "r") as zin, zipfile.ZipFile(corrupt_zip, "w") as zout:
        for item in zin.infolist():
            data = zin.read(item.filename)
            if item.filename == "report.md":
                data += b"\nTAMPERED\n"
            zout.writestr(item.filename, data)
    bad_check = verify_benchmark_zip_integrity(corrupt_zip)
    assert bad_check["ok"] is False
    assert any("sha256_mismatch:report.md" in m for m in bad_check["mismatches"])


def test_18_cli_offline_fake_and_api_endpoints_and_ui_source_badges(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    out_dir = tmp_path / "m4d_cli_out"
    cmd = [
        sys.executable,
        str(ROOT / "scripts" / "run_m4d_benchmark.py"),
        "--mode",
        "offline_fake",
        "--dry-run-count",
        "6",
        "--run-vlm-ablation",
        "--run-guide-ablation",
        "--output-dir",
        str(out_dir),
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True, check=False)
    assert proc.returncode == 0, f"CLI failed: {proc.stderr}\n{proc.stdout}"
    json_blob = "{" + proc.stdout.split("\n{", 1)[-1] if "\n{" in proc.stdout else proc.stdout
    cli_out = json.loads(json_blob)
    assert cli_out["contains_fake_provider"] is True
    assert cli_out["zip_integrity_ok"] is True
    assert "DETERMINISTIC_BASELINE__GUIDE_MINIMAL" in cli_out["real_scorecards"]
    assert all("FAKE" in k for k in cli_out["fake_validation_scorecards"])

    # Verify analyzer CLI
    ana_proc = subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "analyze_m4d_benchmark.py"), "--input", str(out_dir), "--json", "--regenerate-report"],
        capture_output=True,
        text=True,
        check=False,
    )
    assert ana_proc.returncode == 0, ana_proc.stderr
    assert (out_dir / "analysis_summary.json").exists()

    # Verify API endpoints with empty directory -> NOT_RUN
    empty_dir = tmp_path / "empty_bench"
    empty_dir.mkdir()
    monkeypatch.setenv("CUBERELAY_M4D_BENCHMARK_DIR", str(empty_dir))
    client = TestClient(app)
    resp_empty = client.get("/api/m4d/benchmark/latest")
    assert resp_empty.status_code == 200
    assert resp_empty.json()["status"] == "NOT_RUN"

    # Point API at generated offline_fake directory
    monkeypatch.setenv("CUBERELAY_M4D_BENCHMARK_DIR", str(out_dir))
    resp_runs = client.get("/api/m4d/benchmark/runs")
    assert resp_runs.status_code == 200
    assert resp_runs.json()["status"] == "OK"
    assert len(resp_runs.json()["runs"]) == 1

    resp_latest = client.get("/api/m4d/benchmark/latest")
    assert resp_latest.status_code == 200
    data = resp_latest.json()
    assert data["status"] == "OK"
    assert data["source_badge"] in {"FAKE_PROVIDER", "MIXED_REAL_AND_FAKE"}
    assert "DETERMINISTIC_BASELINE__GUIDE_MINIMAL" in data["result"]["real_scorecards"]
    assert len(data["result"]["fake_validation_scorecards"]) >= 1

    resp_cases = client.get("/api/m4d/benchmark/cases")
    assert resp_cases.status_code == 200
    assert resp_cases.json()["total"] >= 30

    resp_zip = client.get("/api/m4d/benchmark/export")
    assert resp_zip.status_code == 200
    assert resp_zip.headers["content-type"] == "application/zip"

    # Verify TSX + built bundle contain benchmark view & strict source badges
    import re

    tsx = (ROOT / "web" / "console" / "cuberelay_v4.tsx").read_text(encoding="utf-8")
    bundle_raw = (ROOT / "web" / "console" / "bundle.js").read_text(encoding="utf-8")
    bundle_decoded = re.sub(r"\\u([0-9a-fA-F]{4})", lambda m: chr(int(m.group(1), 16)), bundle_raw)
    for text_blob in (tsx, bundle_decoded):
        assert "Task Agent 评估" in text_blob
        assert "FAKE_PROVIDER" in text_blob
        assert "REAL_ONLINE_MODEL" in text_blob
        assert "REAL_MUJOCO" in text_blob
