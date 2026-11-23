"""Serializable benchmark schemas for CubeRelay M4-D Task Agent Capability Benchmark."""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

BENCHMARK_VERSION = "m4d.v1"


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class BenchmarkSourceType(str, Enum):
    REAL_REPLAY = "REAL_REPLAY"
    COUNTERFACTUAL_TEST = "COUNTERFACTUAL_TEST"
    REAL_MUJOCO_CLOSED_LOOP = "REAL_MUJOCO_CLOSED_LOOP"


class CapabilityDimension(str, Enum):
    L1_SKILL_SELECTION = "L1_SKILL_SELECTION"
    L2_STATE_AWARE_PLANNING = "L2_STATE_AWARE_PLANNING"
    L3_PERCEPTION_GROUNDED_REASONING = "L3_PERCEPTION_GROUNDED_REASONING"
    L4_FAILURE_RECOVERY = "L4_FAILURE_RECOVERY"
    L5_GENERALIZATION = "L5_GENERALIZATION"


class PlannerGroup(str, Enum):
    DETERMINISTIC_BASELINE = "DETERMINISTIC_BASELINE"
    LLM_AGENT_CV_ONLY = "LLM_AGENT_CV_ONLY"
    LLM_AGENT_CV_VLM = "LLM_AGENT_CV_VLM"
    SINGLE_MODEL_BASELINE = "SINGLE_MODEL_BASELINE"


class PromptGuideMode(str, Enum):
    GUIDE_FULL = "GUIDE_FULL"
    GUIDE_MINIMAL = "GUIDE_MINIMAL"


class VLMAblationCondition(str, Enum):
    VLM_TRUE = "VLM_TRUE"
    VLM_ABSENT = "VLM_ABSENT"
    VLM_SWAPPED = "VLM_SWAPPED"
    VLM_CONTRADICTORY = "VLM_CONTRADICTORY"
    VLM_LOW_CONFIDENCE = "VLM_LOW_CONFIDENCE"


class FailureAttributionCategory(str, Enum):
    NONE = "NONE"
    AGENT_DECISION_FAILURE = "AGENT_DECISION_FAILURE"
    SKILL_EXECUTION_FAILURE = "SKILL_EXECUTION_FAILURE"
    PERCEPTION_FAILURE = "PERCEPTION_FAILURE"
    CAPABILITY_LIMITATION = "CAPABILITY_LIMITATION"
    SAFETY_GATE_REJECTION = "SAFETY_GATE_REJECTION"
    MODEL_API_FAILURE = "MODEL_API_FAILURE"
    SCHEMA_VALIDATION_FAILURE = "SCHEMA_VALIDATION_FAILURE"
    TEST_HARNESS_FAILURE = "TEST_HARNESS_FAILURE"


class ExecutionSourceLabel(str, Enum):
    REAL_ONLINE_MODEL = "REAL_ONLINE_MODEL"
    OFFLINE_REPLAY = "OFFLINE_REPLAY"
    COUNTERFACTUAL_TEST = "COUNTERFACTUAL_TEST"
    FAKE_PROVIDER = "FAKE_PROVIDER"
    REAL_MUJOCO = "REAL_MUJOCO"
    DETERMINISTIC_RULE = "DETERMINISTIC_RULE"


class DecisionRuleSpec(BaseModel):
    """Rule matching one or more acceptable, forbidden, or unnecessary decisions."""

    model_config = ConfigDict(extra="forbid")

    decision_kinds: list[str] = Field(default_factory=list)
    skill_ids: list[str] | None = None
    raw_actions: list[str] | None = None
    parameter_rules: dict[str, list[Any]] = Field(default_factory=dict)
    require_need_replan: bool | None = None
    note: str = ""


class BenchmarkAgentInput(BaseModel):
    """Sanitized input view passed to Task Agent / Planner.

    Structurally forbids oracle fields (acceptable_decisions, expected_behavior,
    evaluation_rubric, oracle_source) and simulator ground-truth fields.
    """

    model_config = ConfigDict(extra="forbid")

    case_id: str
    benchmark_version: str = BENCHMARK_VERSION
    capability_dimension: CapabilityDimension
    difficulty: Literal["easy", "medium", "hard"]
    source_type: BenchmarkSourceType
    mission: dict[str, Any]
    initial_state: dict[str, Any]
    observation_history: list[dict[str, Any]] = Field(default_factory=list)
    cv_state: dict[str, Any] = Field(default_factory=dict)
    vlm_semantic_observation: dict[str, Any] | None = None
    available_skills: list[dict[str, Any]] = Field(default_factory=list)
    skill_preconditions: dict[str, dict[str, Any]] = Field(default_factory=dict)
    safety_constraints: dict[str, Any] = Field(default_factory=dict)
    failure_feedback: dict[str, Any] | None = None
    allowed_actions: list[str] = Field(default_factory=list)
    current_observation: dict[str, Any] = Field(default_factory=dict)
    disabled_skills: list[str] = Field(default_factory=list)
    removed_skills: list[str] = Field(default_factory=list)
    seed: int = 0
    max_decisions: int = 1
    model_budget: dict[str, Any] = Field(default_factory=dict)


class BenchmarkCase(BaseModel):
    """Serializable benchmark test case separating model input from evaluation oracle."""

    model_config = ConfigDict(extra="forbid")

    case_id: str
    benchmark_version: str = BENCHMARK_VERSION
    capability_dimension: CapabilityDimension
    difficulty: Literal["easy", "medium", "hard"]
    source_type: BenchmarkSourceType
    mission: dict[str, Any]
    initial_state: dict[str, Any]
    observation_history: list[dict[str, Any]] = Field(default_factory=list)
    cv_state: dict[str, Any] = Field(default_factory=dict)
    vlm_semantic_observation: dict[str, Any] | None = None
    vlm_ablation_semantics: dict[str, dict[str, Any] | None] = Field(default_factory=dict)
    available_skills: list[dict[str, Any]] = Field(default_factory=list)
    skill_preconditions: dict[str, dict[str, Any]] = Field(default_factory=dict)
    safety_constraints: dict[str, Any] = Field(default_factory=dict)
    failure_feedback: dict[str, Any] | None = None
    allowed_actions: list[str] = Field(default_factory=list)
    acceptable_decisions: list[DecisionRuleSpec] = Field(default_factory=list)
    forbidden_decisions: list[DecisionRuleSpec] = Field(default_factory=list)
    unnecessary_decisions: list[DecisionRuleSpec] = Field(default_factory=list)
    evaluation_rubric: dict[str, Any] = Field(default_factory=dict)
    expected_behavior: str
    oracle_source: str
    requires_human_review: bool = False
    seed: int = 0
    max_decisions: int = 1
    model_budget: dict[str, Any] = Field(default_factory=lambda: {
        "max_calls": 4,
        "max_input_tokens": 8000,
        "max_output_tokens": 1200,
        "timeout_seconds": 45.0,
    })
    disabled_skills: list[str] = Field(default_factory=list)
    removed_skills: list[str] = Field(default_factory=list)
    current_observation: dict[str, Any] = Field(default_factory=dict)
    provenance: dict[str, Any] = Field(default_factory=dict)

    def to_agent_input(
        self,
        *,
        vlm_condition: VLMAblationCondition | None = None,
    ) -> BenchmarkAgentInput:
        """Return strictly sanitized input for the Agent without any oracle or audit truth."""
        if vlm_condition is None:
            sem = self.vlm_semantic_observation
        elif vlm_condition == VLMAblationCondition.VLM_ABSENT:
            sem = None
        elif vlm_condition.value in self.vlm_ablation_semantics:
            sem = self.vlm_ablation_semantics[vlm_condition.value]
        elif vlm_condition == VLMAblationCondition.VLM_TRUE:
            sem = self.vlm_semantic_observation
        else:
            raise KeyError(
                f"Case {self.case_id} missing VLM ablation variant {vlm_condition.value}"
            )

        cutoff = self.provenance.get("cutoff_sim_time")
        safe_history = []
        for entry in self.observation_history:
            sim_t = entry.get("sim_time")
            if cutoff is not None and sim_t is not None and float(sim_t) > float(cutoff) + 1e-9:
                raise AssertionError(
                    f"Temporal leakage detected in {self.case_id}: obs sim_time={sim_t} > cutoff={cutoff}"
                )
            sanitized_entry = {
                k: v for k, v in entry.items()
                if not str(k).startswith("audit_") and "ground_truth" not in str(k).lower()
            }
            safe_history.append(sanitized_entry)

        safe_init = {
            k: v for k, v in self.initial_state.items()
            if not str(k).startswith("audit_") and "ground_truth" not in str(k).lower()
        }
        return BenchmarkAgentInput(
            case_id=self.case_id,
            benchmark_version=self.benchmark_version,
            capability_dimension=self.capability_dimension,
            difficulty=self.difficulty,
            source_type=self.source_type,
            mission=dict(self.mission),
            initial_state=safe_init,
            observation_history=safe_history,
            cv_state=dict(self.cv_state),
            vlm_semantic_observation=dict(sem) if sem is not None else None,
            available_skills=[dict(s) for s in self.available_skills],
            skill_preconditions={k: dict(v) for k, v in self.skill_preconditions.items()},
            safety_constraints=dict(self.safety_constraints),
            failure_feedback=dict(self.failure_feedback) if self.failure_feedback else None,
            allowed_actions=list(self.allowed_actions),
            current_observation=dict(self.current_observation),
            disabled_skills=list(self.disabled_skills),
            removed_skills=list(self.removed_skills),
            seed=self.seed,
            max_decisions=self.max_decisions,
            model_budget=dict(self.model_budget),
        )


class SafetyValidationResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    passed: bool
    safety_gate_status: str
    skill_in_registry: bool = True
    preconditions_met: bool = True
    missing_preconditions: list[str] = Field(default_factory=list)
    parameter_valid: bool = True
    parameter_error: str | None = None
    capability_blocked: bool = False
    reason: str = ""


class OracleEvaluationResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    verdict: Literal["PASS", "FAIL", "REQUIRES_REVIEW", "INCOMPARABLE", "NOT_RUN"]
    schema_valid: bool
    legal_action: bool
    valid_parameters: bool
    evidence_grounded: bool
    evidence_grounding_applicable: bool = True
    temporal_causal_valid: bool
    decision_appropriate: bool
    matched_acceptable_rule: str | None = None
    forbidden_violation: str | None = None
    unnecessary_action: bool = False
    failure_detected: bool | None = None
    safe_stop_correct: bool | None = None
    notes: list[str] = Field(default_factory=list)


class FailureAttributionResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    primary_category: FailureAttributionCategory
    secondary_categories: list[FailureAttributionCategory] = Field(default_factory=list)
    evidence: list[str] = Field(default_factory=list)
    explanation: str = ""


class DecisionRecord(BaseModel):
    """Full auditable record of one Task Agent decision step (Section XV)."""

    model_config = ConfigDict(extra="forbid")

    record_id: str
    benchmark_case_id: str
    capability_dimension: CapabilityDimension
    source_type: BenchmarkSourceType
    planner_group: PlannerGroup
    planner_mode: str
    model_name: str | None = None
    model_provider: str | None = None
    is_fake_provider: bool = False
    is_online_model: bool = False
    execution_source_labels: list[ExecutionSourceLabel] = Field(default_factory=list)
    prompt_version: str
    guide_mode: PromptGuideMode
    vlm_ablation_condition: VLMAblationCondition | None = None
    prompt_contains_fixed_sequence: bool = False
    prompt_contains_future_answer: bool = False
    prompt_sha256: str | None = None
    redacted_prompt_summary: str | None = None
    observation_id: str | None = None
    semantic_observation_id: str | None = None
    # M4-E perception-to-execution audit correlation
    decision_id: str | None = None
    evidence_bundle_id: str | None = None
    request_id: str | None = None
    perception_provenance: dict[str, Any] = Field(default_factory=dict)
    evidence_conflicts: list[str] = Field(default_factory=list)
    evidence_validity: dict[str, Any] = Field(default_factory=dict)
    semantic_provided_to_agent: bool | None = None
    available_skills: list[str] = Field(default_factory=list)
    skill_preconditions: dict[str, dict[str, Any]] = Field(default_factory=dict)
    decision_kind: str
    selected_action: str | None = None
    selected_skill: str | None = None
    normalized_action: str | None = None
    parameters: dict[str, Any] = Field(default_factory=dict)
    reason_summary: str = ""
    evidence_references: list[str] = Field(default_factory=list)
    safety_validation: SafetyValidationResult
    oracle_result: OracleEvaluationResult
    failure_attribution: FailureAttributionResult
    latency_ms: float = 0.0
    perception_latency_ms: float | None = None
    agent_latency_ms: float | None = None
    token_usage: dict[str, int] = Field(default_factory=lambda: {
        "input_tokens": 0,
        "output_tokens": 0,
        "total_tokens": 0,
    })
    model_call_status: str = "SUCCESS"
    repeat_index: int = 1
    seed: int = 0
    incomparable_reason: str | None = None
    timestamp_utc: str = Field(default_factory=utc_now_iso)


class ClosedLoopEpisodeResult(BaseModel):
    """Result of one real MuJoCo closed-loop benchmark episode (Layer B)."""

    model_config = ConfigDict(extra="forbid")

    episode_id: str
    scenario_id: str
    mission_type: str
    planner_group: PlannerGroup
    guide_mode: PromptGuideMode
    model_name: str | None = None
    model_provider: str | None = None
    is_fake_provider: bool = False
    is_online_model: bool = False
    execution_source_labels: list[ExecutionSourceLabel] = Field(default_factory=list)
    seed: int
    perturbation: dict[str, Any] = Field(default_factory=dict)
    mission_status: str
    goal_achieved: bool
    expected_capability_block: bool = False
    failure_reason: str | None = None
    failure_attribution: FailureAttributionResult
    steps_count: int = 0
    skills_executed: list[str] = Field(default_factory=list)
    vlm_calls: int = 0
    decision_rounds: int = 0
    sim_time_s: float = 0.0
    wall_time_s: float = 0.0
    model_latency_ms: float = 0.0
    token_usage: dict[str, int] = Field(default_factory=lambda: {
        "input_tokens": 0,
        "output_tokens": 0,
        "total_tokens": 0,
    })
    run_id: str | None = None
    zip_path: str | None = None
    decision_events_count: int = 0
    trace_events_count: int = 0
    setup_notes: str = ""
    timestamp_utc: str = Field(default_factory=utc_now_iso)


class MetricValue(BaseModel):
    """Explicit metric with numerator, denominator, mathematical definition, and optional 95% CI."""

    model_config = ConfigDict(extra="forbid")

    value: float | None
    numerator: int | float
    denominator: int | float
    formula: str
    ci_95_low: float | None = None
    ci_95_high: float | None = None
    notes: str | None = None


class DimensionScoreSummary(BaseModel):
    model_config = ConfigDict(extra="forbid")

    dimension: CapabilityDimension
    total_samples: int
    passed_count: int
    failed_count: int
    requires_review_count: int = 0
    incomparable_count: int = 0
    not_run_count: int = 0
    pass_rate: MetricValue
    attribution_counts: dict[str, int] = Field(default_factory=dict)


class AgentScorecard(BaseModel):
    """Per-dimension, non-collapsed capability scorecard for one PlannerGroup / configuration."""

    model_config = ConfigDict(extra="forbid")

    group_label: str
    planner_group: PlannerGroup
    guide_mode: PromptGuideMode
    execution_source_label: ExecutionSourceLabel
    is_fake_provider: bool
    included_in_real_agent_ranking: bool
    sample_count: int
    decision_metrics: dict[str, MetricValue]
    perception_metrics: dict[str, MetricValue] = Field(default_factory=dict)
    recovery_metrics: dict[str, MetricValue] = Field(default_factory=dict)
    closed_loop_metrics: dict[str, MetricValue] = Field(default_factory=dict)
    per_dimension: dict[str, DimensionScoreSummary] = Field(default_factory=dict)
    failure_attribution_counts: dict[str, int] = Field(default_factory=dict)
    latency_summary_ms: dict[str, float | None] = Field(default_factory=dict)
    token_summary: dict[str, int] = Field(default_factory=dict)
    notes: list[str] = Field(default_factory=list)


class BenchmarkRunResult(BaseModel):
    """Complete serializable output of a M4-D Benchmark evaluation run."""

    model_config = ConfigDict(extra="forbid")

    benchmark_run_id: str
    benchmark_version: str = BENCHMARK_VERSION
    generated_utc: str = Field(default_factory=utc_now_iso)
    execution_mode: Literal["offline_fake", "online_real", "deterministic_only", "mixed"]
    contains_fake_provider: bool = False
    decision_records: list[DecisionRecord] = Field(default_factory=list)
    vlm_ablation_records: list[DecisionRecord] = Field(default_factory=list)
    guide_ablation_records: list[DecisionRecord] = Field(default_factory=list)
    closed_loop_episodes: list[ClosedLoopEpisodeResult] = Field(default_factory=list)
    real_scorecards: dict[str, AgentScorecard] = Field(default_factory=dict)
    fake_validation_scorecards: dict[str, AgentScorecard] = Field(default_factory=dict)
    vlm_ablation_summary: dict[str, Any] = Field(default_factory=dict)
    guide_ablation_summary: dict[str, Any] = Field(default_factory=dict)
    closed_loop_summary: dict[str, Any] = Field(default_factory=dict)
    incomparabilities: list[str] = Field(default_factory=list)
