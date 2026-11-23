"""Data models for Mission, Plan, ObservationReference, SkillExecution, and Agent state."""

from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class MissionType(str, Enum):
    INSPECT_CUBE = "INSPECT_CUBE"
    VERIFY_PHYSICAL_U_TURN = "VERIFY_PHYSICAL_U_TURN"
    SOLVE_CUBE = "SOLVE_CUBE"
    RELAY_SOLVE_CUBE = "RELAY_SOLVE_CUBE"


class MissionStatus(str, Enum):
    CREATED = "CREATED"
    OBSERVING = "OBSERVING"
    PLANNING = "PLANNING"
    EXECUTING = "EXECUTING"
    VERIFYING = "VERIFYING"
    WAITING_FOR_HUMAN_TURN = "WAITING_FOR_HUMAN_TURN"
    BLOCKED_CAPABILITY = "BLOCKED_CAPABILITY"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


class RelayPhase(str, Enum):
    IDLE = "IDLE"
    AGENT_REASONING = "AGENT_REASONING"
    ROBOT_ACTING = "ROBOT_ACTING"
    ROBOT_PERCEIVING = "ROBOT_PERCEIVING"
    WAITING_FOR_HUMAN_TURN = "WAITING_FOR_HUMAN_TURN"
    AWAITING_HUMAN_CLARIFICATION = "AWAITING_HUMAN_CLARIFICATION"
    PREEMPTED_RECOVERING = "PREEMPTED_RECOVERING"
    VERIFYING_SOLVED = "VERIFYING_SOLVED"
    RELAY_COMPLETED_VERIFIED = "RELAY_COMPLETED_VERIFIED"
    FAILED = "FAILED"


class PlannerMode(str, Enum):
    DETERMINISTIC_PLANNER = "DETERMINISTIC_PLANNER"
    DETERMINISTIC = "DETERMINISTIC_PLANNER"
    LLM_AGENT = "LLM_AGENT"
    UNCONNECTED = "UNCONNECTED"


class VLMDecisionOutput(BaseModel):
    """Strict schema returned by Gemini VLM per decision step."""

    model_config = ConfigDict(extra="forbid")

    action: str = Field(min_length=1, max_length=128)
    parameters: dict[str, Any] = Field(default_factory=dict)
    reason_summary: str = Field(min_length=1, max_length=2000)
    expected_information_gain: str = Field(default="", max_length=1000)
    confidence: float = Field(default=0.8, ge=0.0, le=1.0)


class AgentObservation(BaseModel):
    """Unified VLM observation payload grounded in real MuJoCo frames."""

    model_config = ConfigDict(extra="forbid")

    observation_id: str
    mission_id: str
    session_id: str
    sim_time: float
    frame_id: str
    camera_id: str
    rgb_image_data_url: str | None = None
    image_sha256: str | None = None
    camera_metadata: dict[str, Any] = Field(default_factory=dict)
    observed_facelets: str | None = None
    observed_count: int = 0
    unknown_facelet_indices: list[int] = Field(default_factory=list)
    observation_conflicts: list[str] = Field(default_factory=list)
    latest_skill_result: dict[str, Any] | None = None
    available_skill_descriptions: list[dict[str, Any]] = Field(default_factory=list)
    capability_constraints: dict[str, Any] = Field(default_factory=dict)
    context_mode: str = "vision_plus_structured_state"
    scene_summary: dict[str, Any] = Field(default_factory=dict)


class SemanticSceneObservation(BaseModel):
    """Image-grounded semantic output from the perception model; never an action decision."""

    model_config = ConfigDict(extra="forbid")

    observation_id: str
    frame_id: str
    camera_id: str
    cube_visible: bool
    cube_relation_to_gripper: str = Field(max_length=256)
    support_relation: str = Field(max_length=256)
    visible_regions: list[str] = Field(default_factory=list)
    occluded_regions: list[str] = Field(default_factory=list)
    information_gaps: list[str] = Field(default_factory=list)
    suggested_observations: list[str] = Field(default_factory=list)
    visual_conflicts: list[str] = Field(default_factory=list)
    confidence: float = Field(ge=0.0, le=1.0)
    summary: str = Field(min_length=1, max_length=2000)


class AgentActionDecision(BaseModel):
    """Strict planning-model output based on semantics, CV, history, and capabilities."""

    model_config = ConfigDict(extra="forbid")

    selected_action: str = Field(min_length=1, max_length=128)
    skill_id: str | None = Field(default=None, max_length=128)
    parameters: dict[str, Any] = Field(default_factory=dict)
    reason_summary: str = Field(min_length=1, max_length=2000)
    evidence_observation_ids: list[str] = Field(min_length=1)
    expected_outcome: str = Field(min_length=1, max_length=1000)
    completion_condition: str = Field(min_length=1, max_length=1000)
    confidence: float = Field(ge=0.0, le=1.0)
    need_replan: bool = False


class PlanStepStatus(str, Enum):
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    VERIFIED = "VERIFIED"
    FAILED = "FAILED"
    BLOCKED = "BLOCKED"
    UNAVAILABLE = "UNAVAILABLE"


class ObservationReference(BaseModel):
    """Structured observation summary with real frame/sim_time references for VLM/Agent."""

    model_config = ConfigDict(extra="forbid")

    observation_id: str
    frame_id: str
    sim_time: float
    camera_name: str
    observed_count: int = 0
    unknown_count: int = 54
    conflict_count: int = 0
    validation_status: str = "UNVERIFIED"
    reconstructed_facelets: str | None = None
    cube_center_world_m: tuple[float, float, float] | None = None
    summary: str = ""


class PlanStep(BaseModel):
    """A single dynamically planned step backed by a registered Skill."""

    model_config = ConfigDict(extra="forbid")

    step_id: str
    index: int
    title: str
    skill_id: str
    description: str
    status: PlanStepStatus = PlanStepStatus.PENDING
    implemented: bool = True
    parameters: dict[str, Any] = Field(default_factory=dict)
    started_sim_time: float | None = None
    ended_sim_time: float | None = None
    started_wall_time: str | None = None
    ended_wall_time: str | None = None
    elapsed_sec: float | None = None
    result_summary: str | None = None
    failure_reason: str | None = None
    input_reference: str | None = None
    output_reference: str | None = None


class PlanState(BaseModel):
    """Current task plan bound to a Mission."""

    model_config = ConfigDict(extra="forbid")

    plan_id: str
    mission_id: str
    mission_type: MissionType
    planner_name: str
    planner_mode: PlannerMode = PlannerMode.DETERMINISTIC_PLANNER
    created_at: str
    updated_at: str
    current_step_id: str | None = None
    steps: list[PlanStep] = Field(default_factory=list)
    rationale_summary: str = ""
    replan_count: int = 0
    replan_reason: str | None = None


class SkillExecutionState(BaseModel):
    """Execution record of a single Skill invocation."""

    model_config = ConfigDict(extra="forbid")

    execution_id: str
    mission_id: str
    plan_id: str
    step_id: str
    skill_id: str
    skill_title: str
    status: PlanStepStatus
    started_sim_time: float
    ended_sim_time: float | None = None
    started_wall_time: str
    ended_wall_time: str | None = None
    elapsed_sec: float | None = None
    parameters: dict[str, Any] = Field(default_factory=dict)
    result_summary: str = ""
    output_data: dict[str, Any] = Field(default_factory=dict)
    verification_passed: bool | None = None
    failure_code: str | None = None
    failure_reason: str | None = None
    input_observation_id: str | None = None
    feedback_observation_id: str | None = None
    decision_id: str | None = None
    evidence_bundle_id: str | None = None
    subroutine_provenance: str | None = None
    causal_refs: dict[str, Any] = Field(default_factory=dict)


class MissionState(BaseModel):
    """Top-level user goal & lifecycle state decoupled from individual Skills."""

    model_config = ConfigDict(extra="forbid")

    mission_id: str
    session_id: str
    mission_type: MissionType
    user_goal: str
    success_criteria: str
    status: MissionStatus = MissionStatus.CREATED
    current_plan_id: str | None = None
    created_at: str
    completed_at: str | None = None
    result_summary: str | None = None
    blocked_reason: str | None = None
    blocked_move: str | None = None
    blocked_moves: list[str] = Field(default_factory=list)
    symbolic_solution: list[str] = Field(default_factory=list)
    failure_reason: str | None = None


class AgentObservabilityState(BaseModel):
    """Explicit observability banner for LLM vs Deterministic Planner status."""

    model_config = ConfigDict(extra="forbid")

    planner_mode: PlannerMode = PlannerMode.DETERMINISTIC_PLANNER
    planner_name: str = "DeterministicMissionPlanner"
    llm_connected: bool = False
    llm_model: str | None = None
    model_provider: str | None = None
    status_label: str = "当前由确定性任务规划器执行，LLM Agent 尚未接入"
    latest_observation: ObservationReference | None = None
    current_observation_id: str | None = None
    current_frame_id: str | None = None
    current_camera_id: str | None = None
    current_observation_image_url: str | None = None
    selected_action: str | None = None
    selected_parameters: dict[str, Any] = Field(default_factory=dict)
    selection_rationale: str | None = None
    expected_information_gain: str | None = None
    confidence: float | None = None
    safety_gate_status: str | None = None
    safety_gate_detail: str | None = None
    last_skill_call: str | None = None
    last_execution_feedback: str | None = None
    next_decision_hint: str | None = None
    blocked_or_replan_reason: str | None = None
    model_latency_ms: float | None = None
    total_vlm_calls: int = 0
    total_input_tokens: int = 0
    total_output_tokens: int = 0
    total_reasoning_tokens: int = 0
    fallback_triggered: bool = False
    fallback_reason: str | None = None
    perception_model_provider: str | None = None
    perception_model_name: str | None = None
    perception_connected: bool = False
    perception_latency_ms: float | None = None
    agent_model_provider: str | None = None
    agent_model_name: str | None = None
    agent_connected: bool = False
    agent_latency_ms: float | None = None
    latest_semantic_observation: SemanticSceneObservation | None = None
    # M4-E consolidated perception/evidence observability (optional, backward-compatible)
    use_vlm_perception: bool | None = None
    guide_mode: str | None = None
    current_evidence_bundle_id: str | None = None
    last_decision_id: str | None = None
    perception_provenance: dict[str, Any] = Field(default_factory=dict)
    evidence_conflicts: list[str] = Field(default_factory=list)
    evidence_validity: dict[str, Any] = Field(default_factory=dict)
    semantic_provided_to_agent: bool = False
