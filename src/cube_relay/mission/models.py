"""Data models for Mission, Plan, ObservationReference, SkillExecution, and Agent state."""

from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class MissionType(str, Enum):
    INSPECT_CUBE = "INSPECT_CUBE"
    VERIFY_PHYSICAL_U_TURN = "VERIFY_PHYSICAL_U_TURN"
    SOLVE_CUBE = "SOLVE_CUBE"


class MissionStatus(str, Enum):
    CREATED = "CREATED"
    OBSERVING = "OBSERVING"
    PLANNING = "PLANNING"
    EXECUTING = "EXECUTING"
    VERIFYING = "VERIFYING"
    BLOCKED_CAPABILITY = "BLOCKED_CAPABILITY"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


class PlannerMode(str, Enum):
    DETERMINISTIC_PLANNER = "DETERMINISTIC_PLANNER"
    LLM_AGENT = "LLM_AGENT"
    UNCONNECTED = "UNCONNECTED"


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
    status_label: str = "当前由确定性任务规划器执行，LLM Agent 尚未接入"
    latest_observation: ObservationReference | None = None
    selected_action: str | None = None
    selection_rationale: str | None = None
    last_skill_call: str | None = None
    last_execution_feedback: str | None = None
    blocked_or_replan_reason: str | None = None
