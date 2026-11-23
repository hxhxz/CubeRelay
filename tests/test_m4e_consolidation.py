"""M4-E Perception & Agent Architecture Consolidation verification tests."""

from __future__ import annotations

import hashlib
import io
import json
import os
from pathlib import Path
import zipfile

import numpy as np
import pytest

from cube_relay.api.main import _dispatch_m3d_command
from cube_relay.benchmark.schema import BenchmarkRunResult
from cube_relay.embodied.failure_aware_v6 import FailureAwareSkillAgent, run_bounded_grasp_retry
from cube_relay.embodied.skill_agent import SkillBasedGraspAgent, VLMAgentPlanner
from cube_relay.embodied.task_agent_v7 import EmbodiedTaskAgent, GeminiTaskPlanner
from cube_relay.embodied.vlm import (
    ChromaCubePresenceDetector,
    HeuristicSceneVLM,
    OpenAICompatibleSceneVLM,
)
from cube_relay.experiment.exporter import ArtifactExporter
from cube_relay.mission.dual_model import (
    AgentPlanningProvider,
    DualModelDecisionClient,
    FakeStructuredModelClient,
    OpenAICompatibleStructuredClient,
    VLMPerceptionProvider,
)
from cube_relay.mission.events import DecisionEvent, DecisionEventType
from cube_relay.mission.models import (
    AgentObservation,
    MissionState,
    MissionStatus,
    MissionType,
    ObservationReference,
    PlanState,
    PlannerMode,
    SemanticSceneObservation,
    SkillExecutionState,
    PlanStepStatus,
)
from cube_relay.mission.planner import (
    GeminiMissionPlanner,
    LLMAgentDecisionPolicy,
    VLMInspectionLimits,
)
from cube_relay.mission.skill_registry import SkillRegistry
from cube_relay.perception import (
    EvidenceSourceType,
    EvidenceValidator,
    FrameEvidenceRef,
    PerceptionEvidenceBundle,
    SourceCoercionError,
    build_perception_evidence_bundle,
)

ROOT = Path(__file__).resolve().parents[1]


def _make_obs(
    *,
    obs_id: str = "obs-001",
    frame_id: str = "frm-001",
    camera_id: str = "overhead",
    sim_time: float = 1.5,
    rgb: str | None = "data:image/jpeg;base64,ZmFrZQ==",
    observed_count: int = 18,
    unknown_indices: list[int] | None = None,
    cube_detected: bool = True,
    pose_valid: bool = True,
    rgbd_valid: bool = True,
    held: bool = False,
    state_valid: bool = False,
    cv_54_verified: bool = False,
    camera_metadata: dict | None = None,
) -> AgentObservation:
    unk = list(range(54 - observed_count)) if unknown_indices is None else unknown_indices
    facelets = ("U" * 54) if observed_count == 54 else ("U" * observed_count + "?" * (54 - observed_count))
    return AgentObservation(
        observation_id=obs_id,
        mission_id="msn-test",
        session_id="SESS-M4E",
        sim_time=sim_time,
        frame_id=frame_id,
        camera_id=camera_id,
        rgb_image_data_url=rgb,
        image_sha256=hashlib.sha256(rgb.encode()).hexdigest() if rgb else None,
        camera_metadata=camera_metadata or {"frame_source": "REAL_MUJOCO_RENDERER", "pose_estimate_id": "pose-1" if pose_valid else None},
        observed_facelets=facelets,
        observed_count=observed_count,
        unknown_facelet_indices=unk,
        observation_conflicts=[],
        scene_summary={
            "cube_localized": cube_detected,
            "cube_detected": cube_detected,
            "pose_valid": pose_valid,
            "rgbd_valid": rgbd_valid,
            "pose_estimate_id": "pose-1" if pose_valid else None,
            "cube_center_world_m": [0.25, 0.0, 0.03] if pose_valid else None,
            "cube_held_in_gripper": held,
            "cube_released_on_table": not held,
            "cube_state_validated": state_valid,
            "state_valid": state_valid,
            "validation_status": "SOLVABLE" if cv_54_verified else "UNVERIFIED",
        },
    )


def _make_sem(
    *,
    obs_id: str = "obs-001",
    frame_id: str = "frm-001",
    camera_id: str = "overhead",
    cube_visible: bool = True,
    relation: str = "on_table_away_from_gripper",
    support: str = "resting_on_table",
    occluded: list[str] | None = None,
    gaps: list[str] | None = None,
    suggested: list[str] | None = None,
    confidence: float = 0.88,
    summary: str = "Cube visible on table.",
) -> SemanticSceneObservation:
    return SemanticSceneObservation(
        observation_id=obs_id,
        frame_id=frame_id,
        camera_id=camera_id,
        cube_visible=cube_visible,
        cube_relation_to_gripper=relation,
        support_relation=support,
        visible_regions=["U", "F"],
        occluded_regions=occluded or [],
        information_gaps=gaps or [],
        suggested_observations=suggested or [],
        visual_conflicts=[],
        confidence=confidence,
        summary=summary,
    )


def _agent_action_dict(obs_id: str, skill: str = "observe_visible_faces") -> dict:
    return {
        "selected_action": skill,
        "skill_id": skill,
        "parameters": {},
        "reason_summary": f"Choosing {skill} from evidence.",
        "evidence_observation_ids": [obs_id],
        "expected_outcome": "Advance inspection safely",
        "completion_condition": "54 stickers observed",
        "confidence": 0.9,
        "need_replan": False,
    }


def test_p3_dual_model_decoupled_from_single_model_baseline() -> None:
    assert not issubclass(LLMAgentDecisionPolicy, GeminiMissionPlanner)
    assert LLMAgentDecisionPolicy.architecture_role == "ACTIVE_MAINLINE"
    assert GeminiMissionPlanner.architecture_role == "BENCHMARK_BASELINE"

    policy = LLMAgentDecisionPolicy(
        client=DualModelDecisionClient(
            perception=VLMPerceptionProvider(FakeStructuredModelClient("perception", lambda _p, _img: {})),
            agent=AgentPlanningProvider(FakeStructuredModelClient("agent", lambda _p, _img: _agent_action_dict("obs-001"))),
            use_vlm_perception=False,
        ),
        use_vlm_perception=False,
    )
    assert "live MuJoCo camera image" not in policy._prompt_header_instruction()


def test_cv_only_allows_none_semantics_and_no_rgb_bytes() -> None:
    perception_calls = {"count": 0}

    def p_handler(_prompt: str, _img: str | None) -> dict:
        perception_calls["count"] += 1
        return _make_sem().model_dump()

    def a_handler(prompt: str, img: str | None) -> dict:
        assert img is None
        outer = json.loads(prompt.split("\n", 1)[1])
        assert outer["semantic_scene_observation"] is None
        assert outer["evidence_bundle"]["provenance"]["semantic_source"] == "NONE"
        assert outer["evidence_bundle"]["provenance"]["semantic_provided_to_agent"] is False
        return _agent_action_dict("obs-001")

    dual = DualModelDecisionClient(
        perception=VLMPerceptionProvider(FakeStructuredModelClient("perception", p_handler)),
        agent=AgentPlanningProvider(FakeStructuredModelClient("agent", a_handler)),
        use_vlm_perception=False,
    )
    policy = LLMAgentDecisionPolicy(client=dual, use_vlm_perception=False)
    mission = MissionState(
        mission_id="msn-test",
        session_id="SESS-M4E",
        mission_type=MissionType.INSPECT_CUBE,
        user_goal="inspect",
        success_criteria="54/54",
        status=MissionStatus.OBSERVING,
        created_at="00:00:00",
    )
    registry = SkillRegistry()
    plan = policy.create_plan(mission, registry, plan_id="plan-cv")
    obs = _make_obs(rgb=None, observed_count=9)
    obs_ref = ObservationReference(
        observation_id="obs-001",
        frame_id="frm-001",
        sim_time=1.5,
        camera_name="overhead",
        observed_count=9,
        unknown_count=45,
        cube_center_world_m=(0.25, 0.0, 0.03),
    )

    sel = policy.select_next_action(
        mission,
        plan,
        registry,
        {"cube_localized": True, "cube_held_in_gripper": False},
        obs_ref,
        agent_observation=obs,
    )
    assert perception_calls["count"] == 0
    assert sel.decision_kind == "EXECUTE_STEP"
    assert sel.skill_id == "observe_visible_faces"
    assert sel.evidence_bundle_id is not None
    assert sel.request_id is not None
    assert sel.semantic_provided_to_agent is False
    assert sel.perception_provenance["semantic_source"] == "NONE"
    assert sel.perception_provenance["is_real_vlm"] is False


def test_evidence_bundle_multicamera_and_source_coercion_guard() -> None:
    obs = _make_obs(
        camera_metadata={
            "frame_source": "REAL_MUJOCO_RENDERER",
            "pose_estimate_id": "pose-multi",
            "multiview_frames": [
                {"camera_id": "wrist", "frame_id": "frm-w-1", "captured_sim_time": 1.5, "image_present": True},
                {"camera_id": "cam_L", "frame_id": "frm-l-1", "captured_sim_time": 1.5, "image_present": True},
            ],
        }
    )
    bundle = build_perception_evidence_bundle(
        obs,
        semantic_observation=_make_sem(obs_id="obs-001", frame_id="frm-w-1", camera_id="wrist"),
        semantic_source=EvidenceSourceType.REAL_VLM,
        is_real_vlm=True,
    )
    assert bundle.observation_id == "obs-001"
    assert len(bundle.frames) == 3
    assert {f.camera_id for f in bundle.frames} == {"overhead", "wrist", "cam_L"}
    assert "pose-1" in bundle.observation_refs

    res = EvidenceValidator().validate(bundle)
    assert res.passed is True
    assert res.semantic_passed_to_agent is not None

    # Forbid coercing heuristic detector output to REAL_VLM
    with pytest.raises(SourceCoercionError):
        build_perception_evidence_bundle(
            obs,
            semantic_observation=_make_sem(),
            semantic_source=EvidenceSourceType.REAL_VLM,
            semantic_client_type="heuristic_local",
            is_real_vlm=True,
        )
    with pytest.raises(SourceCoercionError):
        EvidenceValidator.assert_valid_source_transition(
            EvidenceSourceType.HEURISTIC_VISION, EvidenceSourceType.REAL_VLM
        )


def test_validator_cases_1_to_7() -> None:
    validator = EvidenceValidator(default_max_semantic_age_sec=5.0)

    # Case 1: CV unlocalized while VLM claims cube visible -> cannot generate grasp pose
    b1 = build_perception_evidence_bundle(
        _make_obs(cube_detected=False, pose_valid=False, rgbd_valid=False, observed_count=0),
        semantic_observation=_make_sem(cube_visible=True, summary="Cube looks visible on table"),
        semantic_source=EvidenceSourceType.INJECTED_SEMANTICS,
    )
    r1 = validator.validate(b1)
    assert "CASE_1_CV_UNLOCALIZED_VLM_CLAIMS_VISIBLE" in r1.bundle.detected_conflicts
    assert r1.allow_grasp_generation is False
    assert r1.bundle.validity.grasp_precondition_satisfied is False
    assert r1.bundle.validity.can_use_semantic_for_grasp_pose is False

    # Case 2: CV 54/54 verified while single-frame VLM sees occlusion -> keep historical verified fusion
    b2 = build_perception_evidence_bundle(
        _make_obs(observed_count=54, unknown_indices=[], state_valid=True, cv_54_verified=True),
        semantic_observation=_make_sem(occluded=["back_D"], gaps=["bottom face hidden in overhead view"]),
        semantic_source=EvidenceSourceType.INJECTED_SEMANTICS,
    )
    r2 = validator.validate(b2)
    assert "CASE_2_CV_FULL_54_VLM_REPORTS_OCCLUSION" in r2.bundle.detected_conflicts
    assert r2.preserve_verified_cv_fusion is True
    assert r2.bundle.geometric_observation.cv_54_verified is True
    assert r2.bundle.geometric_observation.observed_count == 54

    # Case 3: Robot proprioception says released while VLM claims still held -> keep robot state
    b3 = build_perception_evidence_bundle(
        _make_obs(held=False),
        semantic_observation=_make_sem(relation="still_held_in_gripper", summary="Cube still inside gripper fingers"),
        semantic_source=EvidenceSourceType.INJECTED_SEMANTICS,
    )
    r3 = validator.validate(b3)
    assert "CASE_3_PROPRIOCEPTION_RELEASED_VLM_CLAIMS_HELD" in r3.bundle.detected_conflicts
    assert r3.authoritative_holding_cube is False
    assert r3.bundle.validity.robot_holding_cube is False

    # Case 4: VLM claims graspable while RGB-D has no valid pose -> forbid grasp generation
    b4 = build_perception_evidence_bundle(
        _make_obs(cube_detected=True, pose_valid=False, rgbd_valid=False),
        semantic_observation=_make_sem(cube_visible=True, summary="Cube clear on table and ready to grasp"),
        semantic_source=EvidenceSourceType.INJECTED_SEMANTICS,
    )
    r4 = validator.validate(b4)
    assert "CASE_4_NO_VALID_RGBD_POSE_VLM_CLAIMS_GRASPABLE" in r4.bundle.detected_conflicts
    assert r4.allow_grasp_generation is False
    assert r4.bundle.validity.grasp_precondition_satisfied is False

    # Case 5: CV uncertain (unknowns > 0) + VLM occlusion explanation -> keep both cleanly
    b5 = build_perception_evidence_bundle(
        _make_obs(observed_count=45, unknown_indices=list(range(9)), state_valid=False),
        semantic_observation=_make_sem(
            occluded=["D_face"],
            gaps=["bottom 9 stickers hidden on table"],
            suggested=["place_and_release or reorient_cube(pitch=-90)"],
            summary="Bottom face is resting on table and occluded from overhead view",
        ),
        semantic_source=EvidenceSourceType.INJECTED_SEMANTICS,
    )
    r5 = validator.validate(b5)
    assert r5.passed is True
    assert r5.bundle.validity.uncertainty_explained_by_semantics is True
    assert r5.semantic_passed_to_agent is not None

    # Case 6: Stale frame / mismatched IDs or expired age -> rejected, NEVER passed to agent
    b6 = build_perception_evidence_bundle(
        _make_obs(obs_id="obs-cur", frame_id="frm-cur", sim_time=12.0),
        semantic_observation=_make_sem(obs_id="obs-old", frame_id="frm-old"),
        semantic_source=EvidenceSourceType.INJECTED_SEMANTICS,
        semantic_captured_sim_time=2.0,
    )
    r6 = validator.validate(b6)
    assert r6.bundle.validity.is_stale is True
    assert r6.bundle.validity.semantic_rejected is True
    assert r6.semantic_passed_to_agent is None
    assert "CASE_6_STALE_SEMANTIC_FRAME_MISMATCH" in r6.bundle.detected_conflicts
    assert "CASE_6_STALE_SEMANTIC_EXPIRED" in r6.bundle.detected_conflicts

    # Case 7: VLM timeout -> safety controls unblocked; explicit CV-only fallback vs fail-closed
    b7 = build_perception_evidence_bundle(
        _make_obs(),
        semantic_observation=None,
        semantic_source=EvidenceSourceType.NONE,
        vlm_requested=True,
        vlm_timed_out=True,
        vlm_error_code="MODEL_TIMEOUT",
        vlm_error="Timed out waiting for perception endpoint",
    )
    r7_fail_closed = validator.validate(b7, allow_cv_only_on_vlm_failure=False)
    assert r7_fail_closed.safety_controls_unblocked is True
    assert r7_fail_closed.bundle.validity.fail_closed_required is True
    assert r7_fail_closed.bundle.validity.validation_status == "BLOCKED"
    assert "CASE_7_VLM_PROVIDER_TIMEOUT_OR_ERROR" in r7_fail_closed.bundle.detected_conflicts

    r7_cv_fallback = validator.validate(b7, allow_cv_only_on_vlm_failure=True)
    assert r7_cv_fallback.safety_controls_unblocked is True
    assert r7_cv_fallback.bundle.validity.fail_closed_required is False
    assert r7_cv_fallback.fallback_mode == "CV_ONLY_FALLBACK"
    assert r7_cv_fallback.bundle.provenance.fallback_source == "CV_ONLY_FALLBACK"
    assert r7_cv_fallback.bundle.provenance.semantic_source == EvidenceSourceType.NONE


def test_dual_model_rejects_stale_vlm_and_supports_controlled_timeout_fallback() -> None:
    agent_calls = {"count": 0}

    def stale_vlm(_prompt: str, _img: str | None) -> dict:
        return _make_sem(obs_id="obs-old", frame_id="frm-old").model_dump()

    def timeout_vlm(_prompt: str, _img: str | None) -> dict:
        raise TimeoutError("perception timeout")

    def agent_fn(prompt: str, _img: str | None) -> dict:
        agent_calls["count"] += 1
        outer = json.loads(prompt.split("\n", 1)[1])
        assert outer["semantic_scene_observation"] is None
        return _agent_action_dict("obs-001")

    dual_stale = DualModelDecisionClient(
        perception=VLMPerceptionProvider(FakeStructuredModelClient("perception", stale_vlm)),
        agent=AgentPlanningProvider(FakeStructuredModelClient("agent", agent_fn)),
        use_vlm_perception=True,
        allow_cv_only_on_vlm_failure=False,
    )
    policy_stale = LLMAgentDecisionPolicy(client=dual_stale)
    mission = MissionState(
        mission_id="msn-test",
        session_id="SESS-M4E",
        mission_type=MissionType.INSPECT_CUBE,
        user_goal="inspect",
        success_criteria="54/54",
        status=MissionStatus.OBSERVING,
        created_at="00:00:00",
    )
    reg = SkillRegistry()
    plan = policy_stale.create_plan(mission, reg, plan_id="plan-stale")
    obs = _make_obs()
    obs_ref = ObservationReference(
        observation_id="obs-001", frame_id="frm-001", sim_time=1.5, camera_name="overhead",
        cube_center_world_m=(0.25, 0.0, 0.03),
    )

    sel_stale = policy_stale.select_next_action(
        mission, plan, reg, {"cube_localized": True}, obs_ref, agent_observation=obs,
    )
    assert sel_stale.decision_kind == "FAIL_MISSION"
    assert sel_stale.failure_code == "OBSERVATION_REFERENCE_MISMATCH"
    assert agent_calls["count"] == 0
    assert dual_stale.last_evidence_bundle is not None
    assert dual_stale.last_evidence_bundle.validity.semantic_rejected is True

    # Controlled fallback on VLM error/timeout when explicitly allowed
    dual_fb = DualModelDecisionClient(
        perception=VLMPerceptionProvider(FakeStructuredModelClient("perception", timeout_vlm)),
        agent=AgentPlanningProvider(FakeStructuredModelClient("agent", agent_fn)),
        use_vlm_perception=True,
        allow_cv_only_on_vlm_failure=True,
    )
    policy_fb = LLMAgentDecisionPolicy(
        client=dual_fb,
        limits=VLMInspectionLimits(allow_cv_only_on_vlm_failure=True),
    )
    sel_fb = policy_fb.select_next_action(
        mission, plan, reg, {"cube_localized": True}, obs_ref, agent_observation=obs,
    )
    assert sel_fb.decision_kind == "EXECUTE_STEP"
    assert agent_calls["count"] == 1
    assert sel_fb.perception_provenance["fallback_source"] == "CV_ONLY_FALLBACK"
    assert sel_fb.semantic_provided_to_agent is False


def test_legacy_tags_and_live_no_nested_legacy_agent() -> None:
    detector = ChromaCubePresenceDetector()
    sem = detector.understand(np.zeros((32, 32, 3), dtype=np.uint8))
    assert detector.source_type == "HEURISTIC_VISION"
    assert detector.is_real_vlm is False
    assert sem.provider == "heuristic_local"

    for cls in (
        HeuristicSceneVLM,
        OpenAICompatibleSceneVLM,
        VLMAgentPlanner,
        SkillBasedGraspAgent,
        FailureAwareSkillAgent,
        GeminiTaskPlanner,
        EmbodiedTaskAgent,
    ):
        assert getattr(cls, "architecture_role", None) == "LEGACY_EXPERIMENT"

    session_src = (ROOT / "src" / "cube_relay" / "mission" / "session.py").read_text(encoding="utf-8")
    mujoco_src = (ROOT / "src" / "cube_relay" / "embodied" / "mujoco_v2.py").read_text(encoding="utf-8")
    assert "FailureAwareSkillAgent" not in session_src
    assert "HeuristicSceneVLM" not in session_src
    assert "run_bounded_grasp_retry" in session_src
    assert "FailureAwareSkillAgent" not in mujoco_src
    assert "HeuristicSceneVLM" not in mujoco_src
    assert "run_bounded_grasp_retry" in mujoco_src


def test_api_set_planner_mode_forwards_cv_only_and_guide_mode_when_present(monkeypatch) -> None:
    monkeypatch.setenv("CUBERELAY_VLM_ENABLE_PASSWORD", "m4e-secret")

    class _StubSession:
        def __init__(self) -> None:
            self.calls: list[tuple[tuple, dict]] = []

        def set_planner_mode(self, *args, **kwargs):
            self.calls.append((args, kwargs))
            return {"agent_state": {"planner_mode": args[0], **kwargs}}

    stub = _StubSession()
    _dispatch_m3d_command(stub, {"type": "SET_PLANNER_MODE", "planner_mode": "DETERMINISTIC_PLANNER"})
    assert stub.calls[-1][1] == {"model": None, "context_mode": "vision_plus_structured_state"}

    _dispatch_m3d_command(
        stub,
        {
            "type": "SET_PLANNER_MODE",
            "planner_mode": "LLM_AGENT",
            "enable_password": "m4e-secret",
            "use_vlm_perception": False,
            "guide_mode": "GUIDE_MINIMAL",
            "model": "agent-x",
        },
    )
    assert stub.calls[-1][1] == {
        "model": "agent-x",
        "context_mode": "vision_plus_structured_state",
        "use_vlm_perception": False,
        "guide_mode": "GUIDE_MINIMAL",
    }


def test_structured_client_default_token_budget_and_truncation_diagnostic(monkeypatch) -> None:
    monkeypatch.delenv("CUBERELAY_AGENT_TOKEN_BUDGET", raising=False)
    monkeypatch.delenv("CUBERELAY_AGENT_TIMEOUT_SECONDS", raising=False)
    client = OpenAICompatibleStructuredClient("AGENT")
    assert client.token_budget >= 8192
    assert client.timeout_seconds >= 60.0

    # Verify explicit env override is still honored and finish_reason=length reports diagnostic context
    monkeypatch.setenv("CUBERELAY_AGENT_TOKEN_BUDGET", "1200")
    monkeypatch.setenv("CUBERELAY_AGENT_ENDPOINT", "https://example.invalid/v1")
    monkeypatch.setenv("CUBERELAY_AGENT_MODEL", "gemini-test")
    monkeypatch.setenv("CUBERELAY_AGENT_API_KEY", "k-test")
    truncated_client = OpenAICompatibleStructuredClient("AGENT")

    class _Resp:
        def __enter__(self):
            return self
        def __exit__(self, *args):
            return False
        def read(self):
            return json.dumps({
                "usage": {"prompt_tokens": 100, "completion_tokens": 40},
                "choices": [{"finish_reason": "length", "message": {"content": '{"selected_action": "obs'}}],
            }).encode("utf-8")

    monkeypatch.setattr(
        "cube_relay.mission.dual_model._urlopen_without_environment_proxy",
        lambda *_a, **_k: _Resp(),
    )
    parsed, trace = truncated_client.generate("test", SemanticSceneObservation, None)
    assert parsed is None
    assert trace.error_code == "INVALID_JSON"
    assert "finish_reason=length" in (trace.error or "")


def test_backward_compatibility_and_zip_export_evidence_bundles() -> None:
    # 1. Existing M4-D summary.json deserializes without breakage
    m4d_summary = ROOT / "results" / "m4d_benchmark" / "summary.json"
    if m4d_summary.exists():
        loaded = BenchmarkRunResult.model_validate_json(m4d_summary.read_text(encoding="utf-8"))
        assert len(loaded.decision_records) > 0

    # 2. Export ZIP includes evidence_bundles.jsonl + trace links with valid SHA-256 checksums
    exporter = ArtifactExporter()
    snapshot = {
        "session_id": "LIVE-SEED0-M4ETEST",
        "seed": 0,
        "frame_source": "REAL_MUJOCO_RENDERER",
        "selected_mission_type": "INSPECT_CUBE",
        "mission": {"mission_id": "msn-1", "mission_type": "INSPECT_CUBE"},
        "agent_state": {"planner_mode": "LLM_AGENT", "use_vlm_perception": False},
        "observations": [{"observation_id": "obs-001", "frame_id": "frm-001", "sim_time": 1.0}],
        "decision_events": [
            DecisionEvent(
                event_id="de-0001",
                sequence=1,
                session_id="LIVE-SEED0-M4ETEST",
                mission_id="msn-1",
                event_type=DecisionEventType.ACTION_SELECTED,
                source="llm_agent_cv_only",
                sim_time=1.0,
                wall_time="00:00:01",
                summary="select",
                decision_rationale_summary="cv only",
                status="SELECTED",
                decision_id="dec-111",
                evidence_bundle_id="ev-222",
                request_id="req-333",
                semantic_provided_to_agent=False,
            ).model_dump(mode="json")
        ],
        "trace_events": [],
        "skill_executions": [
            SkillExecutionState(
                execution_id="exec-001",
                mission_id="msn-1",
                plan_id="plan-1",
                step_id="s-1",
                skill_id="place_and_release",
                skill_title="Place and release",
                status=PlanStepStatus.VERIFIED,
                started_sim_time=1.0,
                started_wall_time="00:00:01",
                decision_id="dec-111",
                evidence_bundle_id="ev-222",
                subroutine_provenance="HEURISTIC_VISION",
            ).model_dump(mode="json")
        ],
        "evidence_bundles": [
            build_perception_evidence_bundle(
                _make_obs(),
                bundle_id="ev-222",
                semantic_observation=None,
                semantic_source=EvidenceSourceType.NONE,
            ).model_dump(mode="json")
        ],
    }
    zip_bytes, manifest = exporter.export_zip_bytes(
        session_snapshot=snapshot, scope="events_only", include_rgbd=False
    )
    with zipfile.ZipFile(io.BytesIO(zip_bytes), "r") as zf:
        names = set(zf.namelist())
        assert "evidence_bundles.jsonl" in names
        for entry in manifest["files"]:
            data = zf.read(entry["path"])
            assert hashlib.sha256(data).hexdigest() == entry["sha256"]


def test_live_session_cv_only_toggle_and_real_grasp_retry() -> None:
    if os.environ.get("CUBERELAY_SKIP_GL_TESTS") == "1":
        pytest.skip("GL tests disabled")
    from cube_relay.mission.session import SimulationSession

    sess = SimulationSession(seed=0, width=320, height=240)
    try:
        snap = sess.set_planner_mode(
            PlannerMode.LLM_AGENT,
            model="agent-local-check",
            use_vlm_perception=False,
            guide_mode="GUIDE_MINIMAL",
        )
        agent_state = snap["agent_state"]
        assert agent_state["planner_mode"] == "LLM_AGENT"
        assert agent_state["use_vlm_perception"] is False
        assert agent_state["guide_mode"] == "GUIDE_MINIMAL"
        assert agent_state["perception_model_name"] == "DISABLED(CV_ONLY)"
        assert agent_state["agent_model_name"] == "agent-local-check"

        retry_res = run_bounded_grasp_retry(sess._backend, seed=0, scramble_steps=15, reset_scene=False)
        assert retry_res.attempts >= 1
    finally:
        sess.close()
