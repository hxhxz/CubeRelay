"""Auditable decision event protocol and ordered event log."""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class DecisionEventType(str, Enum):
    MISSION_CREATED = "MISSION_CREATED"
    OBSERVATION_RECEIVED = "OBSERVATION_RECEIVED"
    PLAN_CREATED = "PLAN_CREATED"
    PLAN_UPDATED = "PLAN_UPDATED"
    ACTION_SELECTED = "ACTION_SELECTED"
    SKILL_STARTED = "SKILL_STARTED"
    SKILL_COMPLETED = "SKILL_COMPLETED"
    SKILL_FAILED = "SKILL_FAILED"
    VERIFICATION_COMPLETED = "VERIFICATION_COMPLETED"
    REPLAN_REQUESTED = "REPLAN_REQUESTED"
    CAPABILITY_BLOCKED = "CAPABILITY_BLOCKED"
    MISSION_COMPLETED = "MISSION_COMPLETED"
    MISSION_FAILED = "MISSION_FAILED"
    OBSERVATION_CAPTURED = "OBSERVATION_CAPTURED"
    VLM_INFERENCE_STARTED = "VLM_INFERENCE_STARTED"
    VLM_INFERENCE_COMPLETED = "VLM_INFERENCE_COMPLETED"
    PERCEPTION_UPDATED = "PERCEPTION_UPDATED"
    AGENT_DECISION_STARTED = "AGENT_DECISION_STARTED"
    AGENT_DECISION_COMPLETED = "AGENT_DECISION_COMPLETED"
    SKILL_VALIDATED = "SKILL_VALIDATED"
    SKILL_REJECTED = "SKILL_REJECTED"
    REOBSERVATION_COMPLETED = "REOBSERVATION_COMPLETED"
    REPLAN_TRIGGERED = "REPLAN_TRIGGERED"
    HANDOVER_COMPLETED = "HANDOVER_COMPLETED"
    HUMAN_TURN_FINISHED = "HUMAN_TURN_FINISHED"
    CLARIFICATION_REQUESTED = "CLARIFICATION_REQUESTED"
    HUMAN_CHAT_RECEIVED = "HUMAN_CHAT_RECEIVED"
    PREEMPTION_TRIGGERED = "PREEMPTION_TRIGGERED"
    STALE_RESPONSE_DISCARDED = "STALE_RESPONSE_DISCARDED"
    RAPID_GLANCE_DEDUCED = "RAPID_GLANCE_DEDUCED"


class TraceEventType(str, Enum):
    MISSION = "mission"
    COMPOSITE_SKILL = "composite_skill"
    ACTION = "action"
    PERCEPTION = "perception"
    DECISION = "decision"
    VERIFICATION = "verification"


class TraceEvent(BaseModel):
    """One node in the persisted, replayable hierarchical execution trace."""

    model_config = ConfigDict(extra="forbid")

    event_id: str
    parent_event_id: str | None = None
    sequence: int
    mission_id: str
    session_id: str
    skill_id: str | None = None
    event_type: TraceEventType
    name: str
    source: str
    status: str
    sim_time: float
    end_sim_time: float | None = None
    wall_time: str
    duration: float | None = None
    evidence: dict[str, Any] = Field(default_factory=dict)
    failure_reason: str | None = None


class TraceEventLog:
    """Append-only hierarchy that can be streamed live and replayed verbatim."""

    def __init__(self) -> None:
        self._events: list[TraceEvent] = []

    def clear(self) -> None:
        self._events.clear()

    def append(
        self,
        *,
        mission_id: str,
        session_id: str,
        event_type: TraceEventType,
        name: str,
        source: str,
        status: str,
        sim_time: float,
        parent_event_id: str | None = None,
        skill_id: str | None = None,
        evidence: dict[str, Any] | None = None,
        failure_reason: str | None = None,
        wall_time: str | None = None,
        end_sim_time: float | None = None,
    ) -> TraceEvent:
        sequence = len(self._events) + 1
        duration = None if end_sim_time is None else max(0.0, end_sim_time - sim_time)
        event = TraceEvent(
            event_id=f"te-{sequence:04d}",
            parent_event_id=parent_event_id,
            sequence=sequence,
            mission_id=mission_id,
            session_id=session_id,
            skill_id=skill_id,
            event_type=event_type,
            name=name,
            source=source,
            status=status,
            sim_time=sim_time,
            end_sim_time=end_sim_time,
            wall_time=wall_time or now_wall_time(),
            duration=duration,
            evidence=evidence or {},
            failure_reason=failure_reason,
        )
        self._events.append(event)
        return event

    def finish(
        self,
        event_id: str,
        *,
        status: str,
        end_sim_time: float,
        evidence: dict[str, Any] | None = None,
        failure_reason: str | None = None,
    ) -> TraceEvent:
        event = next(item for item in self._events if item.event_id == event_id)
        event.status = status
        event.end_sim_time = end_sim_time
        event.duration = max(0.0, end_sim_time - event.sim_time)
        if evidence:
            event.evidence.update(evidence)
        event.failure_reason = failure_reason
        return event

    @property
    def events(self) -> list[TraceEvent]:
        return list(self._events)


class DecisionEvent(BaseModel):
    """Structured engineering audit event for planner/agent decisions and skill outcomes."""

    model_config = ConfigDict(extra="forbid")

    event_id: str
    sequence: int
    session_id: str
    mission_id: str
    plan_id: str | None = None
    event_type: DecisionEventType
    source: str
    sim_time: float | None = None
    wall_time: str
    summary: str
    decision_rationale_summary: str
    selected_action: str | None = None
    skill_id: str | None = None
    input_reference: str | None = None
    output_reference: str | None = None
    status: str
    failure_reason: str | None = None
    # M4-A VLM decision audit extensions
    planner_mode: str | None = None
    model_provider: str | None = None
    model_name: str | None = None
    observation_id: str | None = None
    input_frame_ids: list[str] = Field(default_factory=list)
    action_candidates: list[str] = Field(default_factory=list)
    parameters: dict[str, Any] = Field(default_factory=dict)
    expected_information_gain: str | None = None
    confidence: float | None = None
    validation_result: str | None = None
    skill_execution_id: str | None = None
    feedback_observation_id: str | None = None
    model_latency_ms: float | None = None
    token_usage: dict[str, Any] | None = None
    # M4-E perception-to-execution correlation fields
    decision_id: str | None = None
    evidence_bundle_id: str | None = None
    request_id: str | None = None
    prompt_sha256: str | None = None
    perception_provenance: dict[str, Any] = Field(default_factory=dict)
    evidence_conflicts: list[str] = Field(default_factory=list)
    evidence_validity: dict[str, Any] = Field(default_factory=dict)
    semantic_provided_to_agent: bool | None = None


def now_wall_time() -> str:
    return datetime.now(timezone.utc).astimezone().strftime("%H:%M:%S")


class DecisionEventLog:
    """Append-only ordered log preserving execution sequence and monotonic sim_time."""

    def __init__(self) -> None:
        self._events: list[DecisionEvent] = []
        self._last_sim_time: float | None = None

    def clear(self) -> None:
        self._events.clear()
        self._last_sim_time = None

    def append(
        self,
        *,
        session_id: str,
        mission_id: str,
        plan_id: str | None,
        event_type: DecisionEventType,
        source: str,
        sim_time: float | None,
        summary: str,
        decision_rationale_summary: str,
        status: str,
        selected_action: str | None = None,
        skill_id: str | None = None,
        input_reference: str | None = None,
        output_reference: str | None = None,
        failure_reason: str | None = None,
        wall_time: str | None = None,
        planner_mode: str | None = None,
        model_provider: str | None = None,
        model_name: str | None = None,
        observation_id: str | None = None,
        input_frame_ids: list[str] | None = None,
        action_candidates: list[str] | None = None,
        parameters: dict[str, Any] | None = None,
        expected_information_gain: str | None = None,
        confidence: float | None = None,
        validation_result: str | None = None,
        skill_execution_id: str | None = None,
        feedback_observation_id: str | None = None,
        model_latency_ms: float | None = None,
        token_usage: dict[str, Any] | None = None,
        decision_id: str | None = None,
        evidence_bundle_id: str | None = None,
        request_id: str | None = None,
        prompt_sha256: str | None = None,
        perception_provenance: dict[str, Any] | None = None,
        evidence_conflicts: list[str] | None = None,
        evidence_validity: dict[str, Any] | None = None,
        semantic_provided_to_agent: bool | None = None,
    ) -> DecisionEvent:
        seq = len(self._events) + 1
        effective_sim_time = sim_time
        if effective_sim_time is not None and self._last_sim_time is not None:
            if effective_sim_time < self._last_sim_time:
                effective_sim_time = self._last_sim_time
        if effective_sim_time is not None:
            self._last_sim_time = effective_sim_time

        event = DecisionEvent(
            event_id=f"de-{seq:04d}",
            sequence=seq,
            session_id=session_id,
            mission_id=mission_id,
            plan_id=plan_id,
            event_type=event_type,
            source=source,
            sim_time=effective_sim_time,
            wall_time=wall_time or now_wall_time(),
            summary=summary,
            decision_rationale_summary=decision_rationale_summary,
            selected_action=selected_action,
            skill_id=skill_id,
            input_reference=input_reference,
            output_reference=output_reference,
            status=status,
            failure_reason=failure_reason,
            planner_mode=planner_mode,
            model_provider=model_provider,
            model_name=model_name,
            observation_id=observation_id,
            input_frame_ids=list(input_frame_ids) if input_frame_ids else [],
            action_candidates=list(action_candidates) if action_candidates else [],
            parameters=dict(parameters) if parameters else {},
            expected_information_gain=expected_information_gain,
            confidence=confidence,
            validation_result=validation_result,
            skill_execution_id=skill_execution_id,
            feedback_observation_id=feedback_observation_id,
            model_latency_ms=model_latency_ms,
            token_usage=dict(token_usage) if token_usage else None,
            decision_id=decision_id,
            evidence_bundle_id=evidence_bundle_id,
            request_id=request_id,
            prompt_sha256=prompt_sha256,
            perception_provenance=dict(perception_provenance) if perception_provenance else {},
            evidence_conflicts=list(evidence_conflicts) if evidence_conflicts else [],
            evidence_validity=dict(evidence_validity) if evidence_validity else {},
            semantic_provided_to_agent=semantic_provided_to_agent,
        )
        self._events.append(event)
        return event

    @property
    def events(self) -> list[DecisionEvent]:
        return list(self._events)
