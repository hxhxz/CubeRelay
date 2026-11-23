"""Decision Replay (Layer A) and Closed-Loop MuJoCo (Layer B) Benchmark Runners."""

from __future__ import annotations

import json
import os
from pathlib import Path
import time
from typing import Any, Callable
import uuid

from cube_relay.experiment.recorder import redact_secrets
from cube_relay.mission.dual_model import (
    AgentPlanningProvider,
    DualModelDecisionClient,
    FakeStructuredModelClient,
    OpenAICompatibleStructuredClient,
    VLMPerceptionProvider,
)
from cube_relay.mission.models import (
    AgentObservation,
    MissionState,
    MissionStatus,
    MissionType,
    ObservationReference,
    PlanState,
    PlanStep,
    SemanticSceneObservation,
)
from cube_relay.mission.planner import (
    DeterministicMissionPlanner,
    GeminiMissionPlanner,
    LLMAgentDecisionPolicy,
    VLMInspectionLimits,
)
from cube_relay.mission.skill_registry import SkillRegistry
from cube_relay.mission.vlm_client import FakeGeminiVLMClient, _EnvLoadedGeminiClient, load_local_env

from .attribution import attribute_closed_loop_episode, attribute_replay_decision
from .metrics import compute_scorecard, summarize_vlm_ablation
from .oracle import (
    EvaluationOracle,
    assert_no_future_leakage,
    assert_no_oracle_in_prompt,
    normalize_decision_kind,
)
from .schema import (
    BENCHMARK_VERSION,
    BenchmarkAgentInput,
    BenchmarkCase,
    BenchmarkRunResult,
    BenchmarkSourceType,
    ClosedLoopEpisodeResult,
    DecisionRecord,
    ExecutionSourceLabel,
    FailureAttributionCategory,
    FailureAttributionResult,
    OracleEvaluationResult,
    PlannerGroup,
    PromptGuideMode,
    SafetyValidationResult,
    VLMAblationCondition,
)


def _map_error_code_to_call_status(error_code: str | None) -> str:
    if error_code is None:
        return "SUCCESS"
    if error_code == "CLIENT_UNCONFIGURED":
        return "NOT_RUN"
    if error_code == "MODEL_TIMEOUT":
        return "TIMEOUT"
    if error_code in {"INVALID_JSON"}:
        return "INVALID_JSON"
    if error_code in {"SCHEMA_VALIDATION_FAILED", "OBSERVATION_REFERENCE_MISMATCH", "EVIDENCE_REFERENCE_INVALID"}:
        return "SCHEMA_ERROR"
    return "API_ERROR"


def _build_agent_observation_from_input(agent_input: BenchmarkAgentInput) -> AgentObservation:
    cur = agent_input.current_observation
    cv = agent_input.cv_state
    facelets = cv.get("observed_facelets")
    unknown_indices = list(cv.get("unknown_facelet_indices") or [])
    if not unknown_indices and isinstance(facelets, str) and len(facelets) == 54:
        unknown_indices = [idx for idx, ch in enumerate(facelets) if ch == "?"]
    obs_count = int(cv.get("observed_count", 54 - len(unknown_indices)))
    return AgentObservation(
        observation_id=str(cur.get("observation_id") or f"obs-{agent_input.case_id.lower()}"),
        mission_id=str(agent_input.mission.get("mission_id") or f"msn-{agent_input.case_id.lower()}"),
        session_id=str(agent_input.mission.get("session_id") or f"BENCH-{agent_input.case_id}"),
        sim_time=float(cur.get("sim_time") or 0.0),
        frame_id=str(cur.get("frame_id") or f"frm-{agent_input.case_id.lower()}"),
        camera_id=str(cur.get("camera_id") or "overhead"),
        rgb_image_data_url=cur.get("rgb_image_data_url"),
        camera_metadata={"frame_source": "REAL_MUJOCO_BUNDLE" if agent_input.source_type == BenchmarkSourceType.REAL_REPLAY else "BENCHMARK_INPUT"},
        observed_facelets=facelets,
        observed_count=obs_count,
        unknown_facelet_indices=unknown_indices,
        observation_conflicts=list(cv.get("observation_conflicts") or []),
        latest_skill_result=dict(agent_input.failure_feedback) if agent_input.failure_feedback else None,
        available_skill_descriptions=list(agent_input.available_skills),
        capability_constraints=dict(agent_input.safety_constraints),
        context_mode="vision_plus_structured_state",
        scene_summary={
            "cube_localized": bool(agent_input.initial_state.get("cube_localized", False)),
            "cube_detected": bool(
                agent_input.initial_state.get("cube_localized", False)
                or cv.get("cube_center_world_m") is not None
                or obs_count > 0
                or agent_input.initial_state.get("cube_held_in_gripper", False)
            ),
            "pose_valid": bool(
                cv.get("cube_center_world_m") is not None
                or agent_input.initial_state.get("cube_localized", False)
            ),
            "rgbd_valid": bool(
                cv.get("cube_center_world_m") is not None
                or agent_input.initial_state.get("cube_localized", False)
            ),
            "cube_center_world_m": cv.get("cube_center_world_m"),
            "cube_released_on_table": bool(agent_input.initial_state.get("cube_released_on_table", False)),
            "cube_held_in_gripper": bool(agent_input.initial_state.get("cube_held_in_gripper", False)),
            "cube_state_validated": bool(agent_input.initial_state.get("cube_state_validated", False)),
            "state_valid": bool(agent_input.initial_state.get("cube_state_validated", False)),
            "validation_status": str(cv.get("validation_status") or ("SOLVABLE" if agent_input.initial_state.get("cube_state_validated") else "UNVERIFIED")),
        },
    )


def _build_scene_state_from_input(agent_input: BenchmarkAgentInput) -> dict[str, Any]:
    state = dict(agent_input.initial_state)
    state["observation_history"] = list(agent_input.observation_history)
    if agent_input.failure_feedback is not None:
        state["failure_feedback"] = dict(agent_input.failure_feedback)
    if "camera_status" not in state and "camera_status" in agent_input.safety_constraints:
        state["camera_status"] = dict(agent_input.safety_constraints["camera_status"])
    req = agent_input.safety_constraints.get("completion_requirement")
    if req:
        state["custom_completion_requirement"] = req
    cur_t = agent_input.current_observation.get("sim_time")
    if cur_t is not None:
        state["latest_sim_time"] = float(cur_t)
    return state


def _source_labels_for_replay(
    *,
    case: BenchmarkCase,
    planner_group: PlannerGroup,
    is_fake_provider: bool,
    is_online_model: bool,
) -> list[ExecutionSourceLabel]:
    labels: list[ExecutionSourceLabel] = []
    if case.source_type == BenchmarkSourceType.REAL_REPLAY:
        labels.append(ExecutionSourceLabel.OFFLINE_REPLAY)
    elif case.source_type == BenchmarkSourceType.COUNTERFACTUAL_TEST:
        labels.append(ExecutionSourceLabel.COUNTERFACTUAL_TEST)
    if is_fake_provider:
        labels.append(ExecutionSourceLabel.FAKE_PROVIDER)
    elif planner_group == PlannerGroup.DETERMINISTIC_BASELINE:
        labels.append(ExecutionSourceLabel.DETERMINISTIC_RULE)
    elif is_online_model:
        labels.append(ExecutionSourceLabel.REAL_ONLINE_MODEL)
    return labels


def _build_token_usage(
    input_tokens: int | None,
    output_tokens: int | None,
    reasoning_tokens: int | None = None,
) -> dict[str, int]:
    """Assemble token usage dict while preserving optional reasoning token counts."""
    in_tok = int(input_tokens or 0)
    out_tok = int(output_tokens or 0)
    usage = {"input_tokens": in_tok, "output_tokens": out_tok, "total_tokens": in_tok + out_tok}
    if reasoning_tokens is not None:
        usage["reasoning_tokens"] = int(reasoning_tokens)
    return usage


class DecisionReplayRunner:
    """Layer A evaluator: runs isolated decision replay without executing physical skills."""

    def __init__(
        self,
        *,
        mode: str = "online_real",
        perception_client_factory: Callable[[], Any] | None = None,
        agent_client_factory: Callable[[], Any] | None = None,
        single_vlm_client_factory: Callable[[], Any] | None = None,
        allow_perception_key_for_single_model: bool = True,
        live_vlm_on_real_frames: bool = True,
        env_path: Path | None = None,
    ) -> None:
        if mode not in {"online_real", "offline_fake", "deterministic_only"}:
            raise ValueError(f"Unsupported replay runner mode: {mode!r}")
        self.mode = mode
        self.perception_client_factory = perception_client_factory
        self.agent_client_factory = agent_client_factory
        self.single_vlm_client_factory = single_vlm_client_factory
        self.allow_perception_key_for_single_model = allow_perception_key_for_single_model
        self.live_vlm_on_real_frames = live_vlm_on_real_frames
        self.oracle = EvaluationOracle()
        if mode == "online_real":
            load_local_env(env_path or Path(".env"))

    def _make_single_model_client(self) -> tuple[Any, str | None]:
        if self.single_vlm_client_factory is not None:
            return self.single_vlm_client_factory(), None
        if self.mode == "offline_fake":
            raise ValueError("offline_fake mode requires single_vlm_client_factory when running SINGLE_MODEL_BASELINE")
        vlm_key = os.getenv("CUBERELAY_VLM_API_KEY", "").strip()
        if vlm_key:
            return _EnvLoadedGeminiClient(load_env_file=False), None
        if self.allow_perception_key_for_single_model:
            p_key = os.getenv("CUBERELAY_PERCEPTION_API_KEY", "").strip()
            p_ep = os.getenv("CUBERELAY_PERCEPTION_ENDPOINT", "").strip()
            p_model = os.getenv("CUBERELAY_PERCEPTION_MODEL", "").strip()
            if p_key and p_ep and p_model:
                client = _EnvLoadedGeminiClient(
                    endpoint=p_ep,
                    model=p_model,
                    api_key=p_key,
                    load_env_file=False,
                )
                client.provider_name = "gemini_openai_compatible(perception_key_alias)"
                return client, "Using CUBERELAY_PERCEPTION_* credentials because CUBERELAY_VLM_API_KEY is unset"
        return _EnvLoadedGeminiClient(load_env_file=False), "CUBERELAY_VLM_API_KEY unconfigured"

    def _make_dual_clients(self) -> tuple[Any, Any]:
        if self.perception_client_factory is not None:
            p_client = self.perception_client_factory()
        elif self.mode == "online_real":
            p_client = OpenAICompatibleStructuredClient("PERCEPTION")
        else:
            raise ValueError("offline_fake mode requires perception_client_factory")

        if self.agent_client_factory is not None:
            a_client = self.agent_client_factory()
        elif self.mode == "online_real":
            a_client = OpenAICompatibleStructuredClient("AGENT")
        else:
            raise ValueError("offline_fake mode requires agent_client_factory")
        return p_client, a_client

    def run_single(
        self,
        case: BenchmarkCase,
        *,
        planner_group: PlannerGroup,
        guide_mode: PromptGuideMode = PromptGuideMode.GUIDE_MINIMAL,
        vlm_condition: VLMAblationCondition | None = None,
        repeat_index: int = 1,
    ) -> DecisionRecord:
        """Evaluate one (case, planner_group, guide_mode, vlm_condition, repeat_index) completely isolated."""
        agent_input = case.to_agent_input(vlm_condition=vlm_condition)
        assert_no_future_leakage(agent_input, case)

        registry = SkillRegistry().clone(
            disabled_skills=agent_input.disabled_skills,
            removed_skills=agent_input.removed_skills,
        )
        mission = MissionState(
            mission_id=str(agent_input.mission.get("mission_id") or f"msn-{case.case_id}"),
            session_id=str(agent_input.mission.get("session_id") or f"BENCH-{case.case_id}"),
            mission_type=MissionType(agent_input.mission["mission_type"]),
            user_goal=str(agent_input.mission["user_goal"]),
            success_criteria=str(agent_input.mission["success_criteria"]),
            status=MissionStatus.OBSERVING,
            created_at="00:00:00",
        )
        scene_state = _build_scene_state_from_input(agent_input)
        agent_obs = _build_agent_observation_from_input(agent_input)
        obs_ref = ObservationReference(
            observation_id=agent_obs.observation_id,
            frame_id=agent_obs.frame_id,
            sim_time=agent_obs.sim_time,
            camera_name=agent_obs.camera_id,
            observed_count=agent_obs.observed_count,
            unknown_count=len(agent_obs.unknown_facelet_indices),
            conflict_count=len(agent_obs.observation_conflicts),
            reconstructed_facelets=agent_obs.observed_facelets,
            cube_center_world_m=tuple(agent_input.cv_state["cube_center_world_m"])
            if isinstance(agent_input.cv_state.get("cube_center_world_m"), list)
            else None,
        )

        rec_id = f"rec-{uuid.uuid4().hex[:10]}"
        prompt_text = ""
        prompt_sha: str | None = None
        prompt_contains_fixed = False
        is_fake = False
        is_online = False
        model_name: str | None = None
        model_provider: str | None = None
        model_call_status = "SUCCESS"
        model_error_code: str | None = None
        incomparable_reason: str | None = None
        perception_latency_ms: float | None = None
        agent_latency_ms: float | None = None
        total_latency_ms = 0.0
        token_usage = {"input_tokens": 0, "output_tokens": 0, "total_tokens": 0}
        sem_obs_id: str | None = None
        decision_kind = "FAIL_MISSION"
        selected_skill: str | None = None
        raw_action: str | None = None
        parameters: dict[str, Any] = {}
        reason_summary = ""
        evidence_refs: list[str] = []
        need_replan = False
        planner_validation_result = ""
        decision_id: str | None = None
        evidence_bundle_id: str | None = None
        request_id: str | None = None
        perception_provenance: dict[str, Any] = {}
        evidence_conflicts: list[str] = []
        evidence_validity: dict[str, Any] = {}
        semantic_provided_to_agent: bool | None = None

        # Handle Group A: Deterministic Baseline
        if planner_group == PlannerGroup.DETERMINISTIC_BASELINE:
            planner = DeterministicMissionPlanner()
            plan = planner.create_plan(mission, registry, plan_id=f"plan-{rec_id}")
            t0 = time.perf_counter()
            sel = planner.select_next_action(
                mission, plan, registry, scene_state, obs_ref, agent_observation=agent_obs
            )
            total_latency_ms = round((time.perf_counter() - t0) * 1000.0, 3)
            model_name = "DeterministicMissionPlanner"
            model_provider = "deterministic_rule"
            model_call_status = "NOT_APPLICABLE"
            decision_kind = sel.decision_kind
            selected_skill = sel.skill_id
            raw_action = sel.skill_id or sel.decision_kind
            parameters = dict(sel.parameters)
            reason_summary = sel.rationale_summary
            planner_validation_result = sel.validation_result
            decision_id = sel.decision_id
            perception_provenance = {
                "geometric_source": "DETERMINISTIC_CV",
                "semantic_source": "NONE",
                "is_real_vlm": False,
                "semantic_provided_to_agent": False,
            }
            semantic_provided_to_agent = False

        elif planner_group == PlannerGroup.SINGLE_MODEL_BASELINE:
            if vlm_condition is not None:
                incomparable_reason = (
                    "Single-model GeminiMissionPlanner receives raw pixels directly and has no decoupled "
                    "SemanticSceneObservation slot for VLM causal ablation."
                )
            elif case.case_id == "L3_07_C3_VLM_CONTRADICTS_ROBOT_STATE":
                incomparable_reason = (
                    "Case C3 tests contradiction between external Model A SemanticSceneObservation and "
                    "robot state; single-model has no separate semantic channel."
                )
            elif not agent_obs.rgb_image_data_url:
                incomparable_reason = (
                    "Single-model GeminiMissionPlanner requires a matching RGB image frame."
                )

            if incomparable_reason is not None:
                model_call_status = "INCOMPARABLE"
                decision_kind = "INCOMPARABLE"
                planner_validation_result = "INCOMPARABLE"
            else:
                client, key_note = self._make_single_model_client()
                is_fake = isinstance(client, FakeGeminiVLMClient)
                is_online = isinstance(client, _EnvLoadedGeminiClient) and not is_fake
                model_name = getattr(client, "model", None)
                model_provider = getattr(client, "provider_name", None)

                limits = VLMInspectionLimits(allow_deterministic_fallback=False)
                planner = GeminiMissionPlanner(
                    client=client,
                    limits=limits,
                    guide_mode=guide_mode.value,
                )
                plan = planner.create_plan(mission, registry, plan_id=f"plan-{rec_id}")
                allowed = planner._allowed_skill_ids(mission, registry)
                prompt_text = planner._build_prompt(mission, registry, scene_state, agent_obs, allowed)
                assert_no_oracle_in_prompt(prompt_text)
                prompt_contains_fixed = "Required safe inspection phase:" in prompt_text

                sel = planner.select_next_action(
                    mission, plan, registry, scene_state, obs_ref, agent_observation=agent_obs
                )
                trace = planner.call_traces[-1] if planner.call_traces else None
                if trace is not None:
                    prompt_sha = trace.prompt_sha256
                    total_latency_ms = float(trace.latency_ms)
                    in_tok = int(trace.input_tokens or 0)
                    out_tok = int(trace.output_tokens or 0)
                    token_usage = _build_token_usage(in_tok, out_tok, getattr(trace, "reasoning_tokens", None))
                    model_error_code = trace.error_code
                    model_call_status = _map_error_code_to_call_status(trace.error_code)
                    if key_note and trace.error_code == "CLIENT_UNCONFIGURED":
                        reason_summary = key_note
                decision_kind = sel.decision_kind
                selected_skill = sel.skill_id
                raw_action = sel.raw_vlm_action or sel.skill_id or sel.decision_kind
                parameters = dict(sel.parameters)
                reason_summary = reason_summary or sel.rationale_summary
                planner_validation_result = sel.validation_result
                if sel.input_reference:
                    evidence_refs = [sel.input_reference]
                decision_id = sel.decision_id
                request_id = getattr(sel, "request_id", None) or (trace.request_id if trace is not None else None)
                perception_provenance = {
                    "geometric_source": "RECORDED_REPLAY" if case.source_type == BenchmarkSourceType.REAL_REPLAY else "DETERMINISTIC_CV",
                    "semantic_source": "SINGLE_MODEL_VLM_DIRECT",
                    "is_real_vlm": bool(is_online),
                    "semantic_provided_to_agent": False,
                }
                semantic_provided_to_agent = False

        else:
            # Group B (LLM_AGENT_CV_ONLY) or Group C (LLM_AGENT_CV_VLM)
            p_client, a_client = self._make_dual_clients()
            is_fake = isinstance(p_client, FakeStructuredModelClient) or isinstance(a_client, FakeStructuredModelClient)
            is_online = not is_fake

            use_vlm = planner_group == PlannerGroup.LLM_AGENT_CV_VLM and vlm_condition != VLMAblationCondition.VLM_ABSENT
            injected_sem: SemanticSceneObservation | None = None
            if use_vlm:
                # Use live VLMPerceptionProvider only on REAL_REPLAY main matrix when no explicit condition override is given
                should_run_live_vlm = (
                    self.live_vlm_on_real_frames
                    and vlm_condition is None
                    and case.source_type == BenchmarkSourceType.REAL_REPLAY
                    and bool(agent_obs.rgb_image_data_url)
                    and not (case.provenance.get("force_case_semantic", False))
                )
                if not should_run_live_vlm and agent_input.vlm_semantic_observation is not None:
                    injected_sem = SemanticSceneObservation.model_validate(agent_input.vlm_semantic_observation)

            dual = DualModelDecisionClient(
                perception=VLMPerceptionProvider(p_client),
                agent=AgentPlanningProvider(a_client),
                use_vlm_perception=use_vlm,
                injected_semantics=injected_sem,
            )
            limits = VLMInspectionLimits(allow_deterministic_fallback=False)
            policy = LLMAgentDecisionPolicy(
                client=dual,
                limits=limits,
                guide_mode=guide_mode.value,
                use_vlm_perception=use_vlm,
            )
            model_name = f"agent={a_client.model}" + (
                f";perception={p_client.model}" if use_vlm and injected_sem is None else (
                    ";perception=INJECTED_SEMANTIC" if use_vlm else ";perception=NONE"
                )
            )
            model_provider = a_client.provider_name if not use_vlm else f"{p_client.provider_name}+{a_client.provider_name}"

            plan = policy.create_plan(mission, registry, plan_id=f"plan-{rec_id}")
            allowed = policy._allowed_skill_ids(mission, registry)
            prompt_text = policy._build_prompt(mission, registry, scene_state, agent_obs, allowed)
            assert_no_oracle_in_prompt(prompt_text)
            prompt_contains_fixed = "Required safe inspection phase:" in prompt_text

            sel = policy.select_next_action(
                mission, plan, registry, scene_state, obs_ref, agent_observation=agent_obs
            )
            trace = policy.call_traces[-1] if policy.call_traces else None
            perception_latency_ms = dual.last_perception_latency_ms if use_vlm else 0.0
            agent_latency_ms = dual.last_agent_latency_ms
            if dual.last_semantic_observation is not None:
                sem_obs_id = dual.last_semantic_observation.observation_id
            if trace is not None:
                prompt_sha = trace.prompt_sha256
                total_latency_ms = float(trace.latency_ms)
                in_tok = int(trace.input_tokens or 0)
                out_tok = int(trace.output_tokens or 0)
                token_usage = _build_token_usage(in_tok, out_tok, getattr(trace, "reasoning_tokens", None))
                model_error_code = trace.error_code
                model_call_status = _map_error_code_to_call_status(trace.error_code)

            decision_kind = sel.decision_kind
            selected_skill = sel.skill_id
            raw_action = sel.raw_vlm_action or sel.skill_id or sel.decision_kind
            parameters = dict(sel.parameters)
            reason_summary = sel.rationale_summary
            evidence_refs = list(sel.evidence_references)
            need_replan = bool(sel.need_replan)
            planner_validation_result = sel.validation_result
            decision_id = sel.decision_id
            evidence_bundle_id = sel.evidence_bundle_id or (trace.evidence_bundle_id if trace is not None else None)
            request_id = sel.request_id or (trace.request_id if trace is not None else None)
            perception_provenance = dict(sel.perception_provenance) or (dict(trace.perception_provenance) if trace is not None else {})
            evidence_conflicts = list(sel.evidence_conflicts) or (list(trace.evidence_conflicts) if trace is not None else [])
            evidence_validity = dict(sel.evidence_validity) or (dict(trace.evidence_validity) if trace is not None else {})
            semantic_provided_to_agent = (
                sel.semantic_provided_to_agent
                if sel.semantic_provided_to_agent is not None
                else (trace.semantic_provided_to_agent if trace is not None else None)
            )

        schema_valid = model_call_status not in {"INVALID_JSON", "SCHEMA_ERROR"}
        # For Deterministic Baseline, call status is NOT_APPLICABLE, so pass SUCCESS to Oracle evaluation
        oracle_call_status = "SUCCESS" if model_call_status == "NOT_APPLICABLE" else model_call_status

        oracle_res, safety_res = self.oracle.evaluate(
            case=case,
            planner_group=planner_group,
            model_call_status=oracle_call_status,
            schema_valid=schema_valid,
            decision_kind=decision_kind,
            skill_id=selected_skill,
            raw_action=raw_action,
            parameters=parameters,
            evidence_references=evidence_refs,
            planner_validation_result=planner_validation_result,
            reason_summary=reason_summary,
            need_replan=need_replan,
            vlm_condition=vlm_condition,
            incomparable_reason=incomparable_reason,
        )
        attribution = attribute_replay_decision(
            case=case,
            oracle_result=oracle_res,
            safety_validation=safety_res,
            model_call_status=oracle_call_status,
            model_error_code=model_error_code,
        )

        normalized_action = normalize_decision_kind(
            decision_kind=decision_kind,
            raw_action=raw_action,
            validation_result=planner_validation_result,
        )
        normalized_display = (
            f"{normalized_action}:{selected_skill}" if selected_skill else normalized_action
        )

        redacted_summary = None
        if prompt_text:
            safe_str = str(redact_secrets(prompt_text[:280].replace("\n", " ")))
            redacted_summary = safe_str

        return DecisionRecord(
            record_id=rec_id,
            benchmark_case_id=case.case_id,
            capability_dimension=case.capability_dimension,
            source_type=case.source_type,
            planner_group=planner_group,
            planner_mode=(
                "DETERMINISTIC_PLANNER" if planner_group == PlannerGroup.DETERMINISTIC_BASELINE else "LLM_AGENT"
            ),
            model_name=model_name,
            model_provider=model_provider,
            is_fake_provider=is_fake,
            is_online_model=is_online,
            execution_source_labels=_source_labels_for_replay(
                case=case,
                planner_group=planner_group,
                is_fake_provider=is_fake,
                is_online_model=is_online,
            ),
            prompt_version=f"{BENCHMARK_VERSION}.{guide_mode.value.lower()}",
            guide_mode=guide_mode,
            vlm_ablation_condition=vlm_condition,
            prompt_contains_fixed_sequence=prompt_contains_fixed,
            prompt_contains_future_answer=False,
            prompt_sha256=prompt_sha,
            redacted_prompt_summary=redacted_summary,
            observation_id=agent_obs.observation_id,
            semantic_observation_id=sem_obs_id,
            decision_id=decision_id,
            evidence_bundle_id=evidence_bundle_id,
            request_id=request_id,
            perception_provenance=perception_provenance,
            evidence_conflicts=evidence_conflicts,
            evidence_validity=evidence_validity,
            semantic_provided_to_agent=semantic_provided_to_agent,
            available_skills=[s["skill_id"] for s in agent_input.available_skills],
            skill_preconditions=agent_input.skill_preconditions,
            decision_kind=decision_kind,
            selected_action=raw_action,
            selected_skill=selected_skill,
            normalized_action=normalized_display,
            parameters=parameters,
            reason_summary=str(redact_secrets(reason_summary)),
            evidence_references=evidence_refs,
            safety_validation=safety_res,
            oracle_result=oracle_res,
            failure_attribution=attribution,
            latency_ms=total_latency_ms,
            perception_latency_ms=perception_latency_ms,
            agent_latency_ms=agent_latency_ms,
            token_usage=token_usage,
            model_call_status=model_call_status,
            repeat_index=repeat_index,
            seed=case.seed,
            incomparable_reason=incomparable_reason,
        )

    def run_suite(
        self,
        cases: list[BenchmarkCase],
        *,
        planner_groups: list[PlannerGroup],
        guide_modes: list[PromptGuideMode] | None = None,
        repeats: int = 1,
        on_progress: Callable[[DecisionRecord, int, int], None] | None = None,
    ) -> list[DecisionRecord]:
        modes = guide_modes or [PromptGuideMode.GUIDE_MINIMAL]
        plan_items: list[tuple[PlannerGroup, PromptGuideMode, BenchmarkCase, int]] = []
        for group in planner_groups:
            group_modes = [PromptGuideMode.GUIDE_MINIMAL] if group == PlannerGroup.DETERMINISTIC_BASELINE else modes
            for gm in group_modes:
                for case in cases:
                    n_reps = 1 if group == PlannerGroup.DETERMINISTIC_BASELINE else max(1, int(repeats))
                    for rep in range(1, n_reps + 1):
                        plan_items.append((group, gm, case, rep))

        records: list[DecisionRecord] = []
        total = len(plan_items)
        for idx, (group, gm, case, rep) in enumerate(plan_items, start=1):
            rec = self.run_single(
                case,
                planner_group=group,
                guide_mode=gm,
                repeat_index=rep,
            )
            records.append(rec)
            if on_progress is not None:
                on_progress(rec, idx, total)
        return records

    def run_vlm_ablation(
        self,
        l3_cases: list[BenchmarkCase],
        *,
        guide_mode: PromptGuideMode = PromptGuideMode.GUIDE_MINIMAL,
        conditions: list[VLMAblationCondition] | None = None,
        repeats: int = 1,
        on_progress: Callable[[DecisionRecord, int, int], None] | None = None,
    ) -> list[DecisionRecord]:
        conds = conditions or list(VLMAblationCondition)
        plan_items: list[tuple[BenchmarkCase, VLMAblationCondition, int]] = [
            (case, cond, rep)
            for case in l3_cases
            for cond in conds
            for rep in range(1, max(1, int(repeats)) + 1)
        ]
        records: list[DecisionRecord] = []
        total = len(plan_items)
        for idx, (case, cond, rep) in enumerate(plan_items, start=1):
            rec = self.run_single(
                case,
                planner_group=PlannerGroup.LLM_AGENT_CV_VLM,
                guide_mode=guide_mode,
                vlm_condition=cond,
                repeat_index=rep,
            )
            records.append(rec)
            if on_progress is not None:
                on_progress(rec, idx, total)
        return records


class ClosedLoopBenchmarkRunner:
    """Layer B evaluator: executes decisions in isolated real MuJoCo sessions."""

    def __init__(
        self,
        *,
        mode: str = "online_real",
        output_dir: str | Path,
        width: int = 480,
        height: int = 320,
        perception_client_factory: Callable[[], Any] | None = None,
        agent_client_factory: Callable[[], Any] | None = None,
        single_vlm_client_factory: Callable[[], Any] | None = None,
        allow_perception_key_for_single_model: bool = True,
        env_path: Path | None = None,
    ) -> None:
        self.mode = mode
        self.output_dir = Path(output_dir).resolve()
        self.runs_dir = self.output_dir / "closed_loop_runs"
        self.bundles_dir = self.output_dir / "closed_loop_bundles"
        self.runs_dir.mkdir(parents=True, exist_ok=True)
        self.bundles_dir.mkdir(parents=True, exist_ok=True)
        self.width = int(width)
        self.height = int(height)
        self.perception_client_factory = perception_client_factory
        self.agent_client_factory = agent_client_factory
        self.single_vlm_client_factory = single_vlm_client_factory
        self.allow_perception_key_for_single_model = allow_perception_key_for_single_model
        if mode == "online_real":
            load_local_env(env_path or Path(".env"))

    def _build_planner(
        self,
        *,
        planner_group: PlannerGroup,
        guide_mode: PromptGuideMode,
        max_rounds: int,
        max_calls: int,
    ) -> tuple[Any, bool, bool, str | None, str | None]:
        limits = VLMInspectionLimits(
            max_decision_rounds=max_rounds,
            max_vlm_calls=max_calls,
            allow_deterministic_fallback=False,
        )
        if planner_group == PlannerGroup.DETERMINISTIC_BASELINE:
            return DeterministicMissionPlanner(), False, False, "DeterministicMissionPlanner", "deterministic_rule"

        if planner_group == PlannerGroup.SINGLE_MODEL_BASELINE:
            if self.single_vlm_client_factory is not None:
                client = self.single_vlm_client_factory()
            else:
                vlm_key = os.getenv("CUBERELAY_VLM_API_KEY", "").strip()
                if vlm_key:
                    client = _EnvLoadedGeminiClient(load_env_file=False)
                elif self.allow_perception_key_for_single_model:
                    client = _EnvLoadedGeminiClient(
                        endpoint=os.getenv("CUBERELAY_PERCEPTION_ENDPOINT", ""),
                        model=os.getenv("CUBERELAY_PERCEPTION_MODEL", ""),
                        api_key=os.getenv("CUBERELAY_PERCEPTION_API_KEY", ""),
                        load_env_file=False,
                    )
                    client.provider_name = "gemini_openai_compatible(perception_key_alias)"
                else:
                    client = _EnvLoadedGeminiClient(load_env_file=False)
            is_fake = isinstance(client, FakeGeminiVLMClient)
            planner = GeminiMissionPlanner(client=client, limits=limits, guide_mode=guide_mode.value)
            return planner, is_fake, (not is_fake), getattr(client, "model", None), getattr(client, "provider_name", None)

        p_client = (
            self.perception_client_factory()
            if self.perception_client_factory is not None
            else OpenAICompatibleStructuredClient("PERCEPTION")
        )
        a_client = (
            self.agent_client_factory()
            if self.agent_client_factory is not None
            else OpenAICompatibleStructuredClient("AGENT")
        )
        is_fake = isinstance(p_client, FakeStructuredModelClient) or isinstance(a_client, FakeStructuredModelClient)
        use_vlm = planner_group == PlannerGroup.LLM_AGENT_CV_VLM
        dual = DualModelDecisionClient(
            perception=VLMPerceptionProvider(p_client),
            agent=AgentPlanningProvider(a_client),
            use_vlm_perception=use_vlm,
        )
        policy = LLMAgentDecisionPolicy(
            client=dual,
            limits=limits,
            guide_mode=guide_mode.value,
            use_vlm_perception=use_vlm,
        )
        model_name = f"agent={a_client.model}" + (f";perception={p_client.model}" if use_vlm else ";perception=NONE")
        provider = a_client.provider_name if not use_vlm else f"{p_client.provider_name}+{a_client.provider_name}"
        return policy, is_fake, (not is_fake), model_name, provider

    def run_scenario(
        self,
        scenario: dict[str, Any],
        *,
        planner_group: PlannerGroup,
        guide_mode: PromptGuideMode = PromptGuideMode.GUIDE_MINIMAL,
        vlm_condition: VLMAblationCondition | None = None,
    ) -> ClosedLoopEpisodeResult:
        """Run one physical MuJoCo closed-loop episode in a clean SimulationSession."""
        if vlm_condition in {VLMAblationCondition.VLM_SWAPPED, VLMAblationCondition.VLM_CONTRADICTORY}:
            raise ValueError(
                f"Forbidden VLM ablation condition {vlm_condition.value} in physical closed-loop execution!"
            )

        from cube_relay.mission.session import SimulationSession

        planner, is_fake, is_online, model_name, model_provider = self._build_planner(
            planner_group=planner_group,
            guide_mode=guide_mode,
            max_rounds=int(scenario.get("max_decision_rounds", 16)),
            max_calls=int(scenario.get("max_vlm_calls", 32)),
        )
        seed = int(scenario.get("seed", 0))
        mtype = MissionType(scenario["mission_type"])
        perturbation = scenario.get("perturbation")
        setup_phase = str(scenario.get("setup_phase") or "none")
        allow_recovery = planner_group != PlannerGroup.DETERMINISTIC_BASELINE

        session = SimulationSession(
            seed=seed,
            width=self.width,
            height=self.height,
            use_dedicated_thread=False,
            planner=planner,
            experiments_dir=self.runs_dir,
            include_audit_ground_truth=True,
            allow_agent_failure_recovery=allow_recovery,
        )
        setup_notes = ""
        try:
            reset_before_run = True
            if setup_phase == "real_released_45_of_54":
                # Execute genuine physical setup steps on real MuJoCo so the cube sits released with 45/54 observed
                setup_mission = session._new_mission_object(mtype)
                session.mission = setup_mission
                session.plan = PlanState(
                    plan_id="plan-setup-45",
                    mission_id=setup_mission.mission_id,
                    mission_type=mtype,
                    planner_name="SetupPhase",
                    created_at="00:00:00",
                    updated_at="00:00:00",
                    steps=[],
                )
                session._lock_backend_anti_cheat()
                for idx, (sid, params) in enumerate([
                    ("observe_workspace", {"camera_name": "overhead"}),
                    ("place_and_release", {}),
                    ("observe_visible_faces", {"view_mode": "released"}),
                ], start=1):
                    st = PlanStep(
                        step_id=f"setup-s{idx}",
                        index=idx,
                        title=sid,
                        skill_id=sid,
                        description=sid,
                        parameters=params,
                    )
                    session.plan.steps.append(st)
                    out = session._execute_plan_step(st, None)
                    if out != "VERIFIED":
                        raise RuntimeError(f"Setup phase failed on {sid}: {st.failure_reason}")
                reset_before_run = False
                setup_notes = (
                    f"Real physical setup executed observe_workspace -> place_and_release -> "
                    f"observe_visible_faces(released): observed={54 - (session.observed_facelets_str or '').count('?')}/54"
                )

            t0 = time.perf_counter()
            snapshot = session.run_mission(
                mtype,
                seed=seed,
                perturbation=perturbation,
                reset_before_run=reset_before_run,
            )
            wall_time_s = round(time.perf_counter() - t0, 4)

            run_id = str(snapshot.get("run_id") or "")
            zip_path = self.bundles_dir / f"{scenario['scenario_id']}_{planner_group.value}_{guide_mode.value}_{run_id}.zip"
            if run_id:
                session.exporter.export_zip_bytes(
                    run_id=run_id,
                    session_snapshot=snapshot,
                    scope="full_mission",
                    include_rgbd=True,
                    include_high_freq_trajectory=True,
                    include_audit_ground_truth=True,
                    out_path=zip_path,
                )

            mission = snapshot.get("mission") or {}
            mission_status = str(mission.get("status") or "UNKNOWN")
            expected_cap_block = bool(scenario.get("expected_capability_block", False))
            expected_outcome = str(scenario.get("expected_outcome") or "COMPLETED")

            # Check model API / schema errors & safety gate rejections
            decision_events = snapshot.get("decision_events") or []
            rejected = [
                ev for ev in decision_events
                if ev.get("event_type") == "SKILL_REJECTED"
                and ev.get("failure_reason") not in {"VLM_REQUESTED_STOP", "CAPABILITY_UNSUPPORTED"}
            ]
            model_api_err: str | None = None
            schema_err: str | None = None
            for ev in decision_events:
                fc = ev.get("failure_reason")
                if fc in {"MODEL_TIMEOUT", "API_UNAVAILABLE", "CLIENT_UNCONFIGURED"}:
                    model_api_err = str(fc)
                elif fc in {"INVALID_JSON", "SCHEMA_VALIDATION_FAILED", "OBSERVATION_REFERENCE_MISMATCH", "EVIDENCE_REFERENCE_INVALID"}:
                    schema_err = str(fc)

            attribution = attribute_closed_loop_episode(
                snapshot=snapshot,
                expected_capability_block=expected_cap_block,
                agent_violated_safety_gate=bool(rejected),
                safety_gate_failure_code=str(rejected[-1].get("failure_reason")) if rejected else None,
                model_api_error=model_api_err,
                schema_error=schema_err,
            )

            if expected_outcome == "COMPLETED":
                goal_achieved = (mission_status == "COMPLETED")
            elif expected_outcome == "BLOCKED_CAPABILITY":
                goal_achieved = (mission_status == "BLOCKED_CAPABILITY")
            elif expected_outcome == "SAFE_STOP_OR_PERCEPTION_FAILURE":
                # In blackout negative control, NOT executing physical grasp and failing/stopping due to perception is safe!
                executed_physical = any(
                    ex.get("skill_id") in {"place_and_release", "regrasp_cube", "reorient_cube", "execute_physical_u_turn"}
                    for ex in (snapshot.get("skill_executions") or [])
                )
                goal_achieved = (not executed_physical) and (not rejected) and (model_api_err is None)
            elif expected_outcome == "SKILL_FAILURE_ATTRIBUTED":
                # Agent succeeded if it made no illegal decisions (no Safety Gate rejection) even when skill failed physically
                goal_achieved = (mission_status == "COMPLETED") or (
                    attribution.primary_category == FailureAttributionCategory.SKILL_EXECUTION_FAILURE
                    and not rejected
                )
            else:
                goal_achieved = (mission_status == "COMPLETED")

            timing = snapshot.get("timing_metrics") or {}
            in_tok = int(timing.get("input_tokens") or 0)
            out_tok = int(timing.get("output_tokens") or 0)
            reas_tok = timing.get("reasoning_tokens")
            skills_exec = [str(ex.get("skill_id")) for ex in (snapshot.get("skill_executions") or [])]

            labels = [ExecutionSourceLabel.REAL_MUJOCO]
            if is_fake:
                labels.append(ExecutionSourceLabel.FAKE_PROVIDER)
            elif planner_group == PlannerGroup.DETERMINISTIC_BASELINE:
                labels.append(ExecutionSourceLabel.DETERMINISTIC_RULE)
            else:
                labels.append(ExecutionSourceLabel.REAL_ONLINE_MODEL)

            return ClosedLoopEpisodeResult(
                episode_id=f"ep-{uuid.uuid4().hex[:8]}",
                scenario_id=str(scenario["scenario_id"]),
                mission_type=mtype.value,
                planner_group=planner_group,
                guide_mode=guide_mode,
                model_name=model_name,
                model_provider=model_provider,
                is_fake_provider=is_fake,
                is_online_model=is_online,
                execution_source_labels=labels,
                seed=seed,
                perturbation=dict(perturbation or {}),
                mission_status=mission_status,
                goal_achieved=goal_achieved,
                expected_capability_block=expected_cap_block,
                failure_reason=mission.get("failure_reason"),
                failure_attribution=attribution,
                steps_count=len(skills_exec),
                skills_executed=skills_exec,
                vlm_calls=int(timing.get("vlm_calls") or 0),
                decision_rounds=sum(1 for ev in decision_events if ev.get("event_type") == "ACTION_SELECTED"),
                sim_time_s=float(snapshot.get("sim_time") or 0.0),
                wall_time_s=wall_time_s,
                model_latency_ms=float(timing.get("model_latency_ms") or 0.0),
                token_usage=_build_token_usage(in_tok, out_tok, reas_tok),
                run_id=run_id or None,
                zip_path=str(zip_path) if zip_path.exists() else None,
                decision_events_count=len(decision_events),
                trace_events_count=len(snapshot.get("trace_events") or []),
                setup_notes=setup_notes,
            )
        finally:
            session.close()


def assemble_benchmark_run(
    *,
    decision_records: list[DecisionRecord],
    vlm_ablation_records: list[DecisionRecord] | None = None,
    guide_ablation_records: list[DecisionRecord] | None = None,
    closed_loop_episodes: list[ClosedLoopEpisodeResult] | None = None,
    execution_mode: str = "online_real",
) -> BenchmarkRunResult:
    """Aggregate decision records and closed-loop episodes with strict Fake segregation."""
    vlm_abl = list(vlm_ablation_records or [])
    guide_abl = list(guide_ablation_records or [])
    cl_eps = list(closed_loop_episodes or [])
    contains_fake = any(
        r.is_fake_provider for r in [*decision_records, *vlm_abl, *guide_abl]
    ) or any(ep.is_fake_provider for ep in cl_eps)

    real_scorecards: dict[str, Any] = {}
    fake_scorecards: dict[str, Any] = {}

    # Identify CV-only records per guide_mode for vlm_delta_accuracy pairing (strictly excluding Fake!)
    cv_only_by_mode: dict[PromptGuideMode, list[DecisionRecord]] = {}
    for r in [*decision_records, *guide_abl]:
        if r.planner_group == PlannerGroup.LLM_AGENT_CV_ONLY and not r.is_fake_provider:
            cv_only_by_mode.setdefault(r.guide_mode, []).append(r)

    # Group all main + guide ablation records by (group, guide_mode, is_fake)
    buckets: dict[tuple[PlannerGroup, PromptGuideMode, bool], list[DecisionRecord]] = {}
    for r in [*decision_records, *guide_abl]:
        key = (r.planner_group, r.guide_mode, r.is_fake_provider)
        buckets.setdefault(key, []).append(r)

    for (group, gm, is_fake), rows in sorted(buckets.items(), key=lambda item: (item[0][2], item[0][0].value, item[0][1].value)):
        label = f"{group.value}__{gm.value}" + ("__FAKE" if is_fake else "")
        matching_eps = [
            ep for ep in cl_eps
            if ep.planner_group == group and ep.guide_mode == gm and ep.is_fake_provider == is_fake
        ]
        matching_vlm_abl = [
            r for r in vlm_abl
            if group == PlannerGroup.LLM_AGENT_CV_VLM and r.guide_mode == gm and r.is_fake_provider == is_fake
        ]
        paired_cv = None if is_fake else cv_only_by_mode.get(gm)
        sc = compute_scorecard(
            group_label=label,
            planner_group=group,
            guide_mode=gm,
            records=rows,
            vlm_ablation_records=matching_vlm_abl or None,
            paired_cv_only_records=paired_cv,
            closed_loop_episodes=matching_eps or None,
        )
        if is_fake:
            fake_scorecards[label] = sc
        else:
            real_scorecards[label] = sc

    # Also compute guide ablation delta summary
    guide_summary: dict[str, Any] = {}
    for group in PlannerGroup:
        full_rows = [r for r in [*decision_records, *guide_abl] if r.planner_group == group and r.guide_mode == PromptGuideMode.GUIDE_FULL and not r.is_fake_provider]
        min_rows = [r for r in [*decision_records, *guide_abl] if r.planner_group == group and r.guide_mode == PromptGuideMode.GUIDE_MINIMAL and not r.is_fake_provider]
        if full_rows and min_rows:
            f_pass = sum(1 for r in full_rows if r.oracle_result.verdict == "PASS") / len(full_rows)
            m_pass = sum(1 for r in min_rows if r.oracle_result.verdict == "PASS") / len(min_rows)
            guide_summary[group.value] = {
                "guide_full_n": len(full_rows),
                "guide_full_acc": round(f_pass, 4),
                "guide_minimal_n": len(min_rows),
                "guide_minimal_acc": round(m_pass, 4),
                "delta_minimal_minus_full": round(m_pass - f_pass, 4),
            }

    incomparabilities = sorted({
        f"{r.planner_group.value}/{r.benchmark_case_id}: {r.incomparable_reason}"
        for r in [*decision_records, *vlm_abl, *guide_abl]
        if r.incomparable_reason
    })

    vlm_abl_real = [r for r in vlm_abl if not r.is_fake_provider]
    vlm_abl_fake = [r for r in vlm_abl if r.is_fake_provider]

    return BenchmarkRunResult(
        benchmark_run_id=f"m4d-{uuid.uuid4().hex[:8]}",
        execution_mode=execution_mode,  # type: ignore[arg-type]
        contains_fake_provider=contains_fake,
        decision_records=decision_records,
        vlm_ablation_records=vlm_abl,
        guide_ablation_records=guide_abl,
        closed_loop_episodes=cl_eps,
        real_scorecards=real_scorecards,
        fake_validation_scorecards=fake_scorecards,
        vlm_ablation_summary=(
            summarize_vlm_ablation(vlm_abl_real)
            if vlm_abl_real
            else ({"fake_only": summarize_vlm_ablation(vlm_abl_fake)} if vlm_abl_fake else {})
        ),
        guide_ablation_summary=guide_summary,
        closed_loop_summary={
            "total_episodes": len(cl_eps),
            "episodes": [ep.model_dump(mode="json") for ep in cl_eps],
        } if cl_eps else {},
        incomparabilities=incomparabilities,
    )
