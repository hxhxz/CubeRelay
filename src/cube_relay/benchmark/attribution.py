"""Strict 4-class + technical/safety Failure Attribution for CubeRelay M4-D."""

from __future__ import annotations

from typing import Any

from .schema import (
    BenchmarkCase,
    FailureAttributionCategory,
    FailureAttributionResult,
    OracleEvaluationResult,
    SafetyValidationResult,
)


def attribute_replay_decision(
    *,
    case: BenchmarkCase,
    oracle_result: OracleEvaluationResult,
    safety_validation: SafetyValidationResult,
    model_call_status: str,
    model_error_code: str | None = None,
) -> FailureAttributionResult:
    """Assign primary and secondary failure categories for a Decision Replay step."""
    if oracle_result.verdict in {"PASS", "INCOMPARABLE", "NOT_RUN", "REQUIRES_REVIEW"}:
        return FailureAttributionResult(
            primary_category=FailureAttributionCategory.NONE,
            secondary_categories=[],
            evidence=list(oracle_result.notes),
            explanation="Decision passed or requires no failure attribution.",
        )

    evidence = list(oracle_result.notes)
    secondary: list[FailureAttributionCategory] = []

    if model_call_status in {"TIMEOUT", "API_ERROR", "UNCONFIGURED", "BUDGET_EXCEEDED"}:
        return FailureAttributionResult(
            primary_category=FailureAttributionCategory.MODEL_API_FAILURE,
            secondary_categories=[],
            evidence=[f"model_call_status={model_call_status}", *( [f"error_code={model_error_code}"] if model_error_code else [] )],
            explanation=f"Online/model provider call failed ({model_call_status}).",
        )

    if model_call_status in {"INVALID_JSON", "SCHEMA_ERROR"} or not oracle_result.schema_valid:
        return FailureAttributionResult(
            primary_category=FailureAttributionCategory.SCHEMA_VALIDATION_FAILURE,
            secondary_categories=[FailureAttributionCategory.AGENT_DECISION_FAILURE],
            evidence=[f"model_call_status={model_call_status}", *( [f"error_code={model_error_code}"] if model_error_code else [] )],
            explanation="Model response violated strict JSON / Pydantic action schema.",
        )

    if model_error_code in {"PERCEPTION_FAILED", "OBSERVATION_REFERENCE_MISMATCH"}:
        return FailureAttributionResult(
            primary_category=FailureAttributionCategory.PERCEPTION_FAILURE,
            secondary_categories=[],
            evidence=[f"perception_error={model_error_code}", *evidence],
            explanation="Perception provider failed to produce valid SemanticSceneObservation.",
        )

    # Check if Safety Gate rejected an illegal Agent action
    if not safety_validation.passed:
        secondary.append(FailureAttributionCategory.SAFETY_GATE_REJECTION)
        evidence.append(f"safety_gate={safety_validation.safety_gate_status}")

    # Distinguish CAPABILITY_LIMITATION only if no legal/appropriate action existed in acceptable_decisions
    acceptable_kinds = {
        kind
        for rule in case.acceptable_decisions
        for kind in rule.decision_kinds
    }
    if acceptable_kinds.issubset({"BLOCK_CAPABILITY", "SAFE_STOP"}) and not safety_validation.passed:
        # Agent tried an illegal physical move when only CAPABILITY_BLOCKED / SAFE_STOP was acceptable
        return FailureAttributionResult(
            primary_category=FailureAttributionCategory.AGENT_DECISION_FAILURE,
            secondary_categories=[FailureAttributionCategory.CAPABILITY_LIMITATION, *secondary],
            evidence=evidence,
            explanation="Only safe stop / capability block was valid, yet Agent selected an unsafe/illegal action.",
        )

    return FailureAttributionResult(
        primary_category=FailureAttributionCategory.AGENT_DECISION_FAILURE,
        secondary_categories=secondary,
        evidence=evidence,
        explanation="Legal and appropriate actions existed in SkillRegistry/protocol, but Agent selected an inappropriate or forbidden decision.",
    )


def attribute_closed_loop_episode(
    *,
    snapshot: dict[str, Any],
    expected_capability_block: bool,
    agent_violated_safety_gate: bool,
    safety_gate_failure_code: str | None,
    model_api_error: str | None = None,
    schema_error: str | None = None,
) -> FailureAttributionResult:
    """Strictly separate Agent vs Skill vs Perception vs Capability failures in closed-loop MuJoCo."""
    mission = snapshot.get("mission") or {}
    status = str(mission.get("status") or "UNKNOWN")
    failure_reason = str(mission.get("failure_reason") or "")
    skill_execs = snapshot.get("skill_executions") or []
    decision_events = snapshot.get("decision_events") or []

    if status == "COMPLETED":
        return FailureAttributionResult(
            primary_category=FailureAttributionCategory.NONE,
            explanation="Mission completed and verified in real MuJoCo.",
        )

    if status == "BLOCKED_CAPABILITY":
        return FailureAttributionResult(
            primary_category=FailureAttributionCategory.CAPABILITY_LIMITATION,
            evidence=[
                f"blocked_move={mission.get('blocked_move')}",
                f"blocked_reason={mission.get('blocked_reason')}",
            ],
            explanation=(
                "Expected capability boundary triggered on unsupported physical move."
                if expected_capability_block
                else "Mission blocked by missing physical capability."
            ),
        )

    if model_api_error:
        return FailureAttributionResult(
            primary_category=FailureAttributionCategory.MODEL_API_FAILURE,
            evidence=[f"model_api_error={model_api_error}"],
            explanation="Closed-loop run stopped due to online model API failure/timeout.",
        )

    if schema_error:
        return FailureAttributionResult(
            primary_category=FailureAttributionCategory.SCHEMA_VALIDATION_FAILURE,
            secondary_categories=[FailureAttributionCategory.AGENT_DECISION_FAILURE],
            evidence=[f"schema_error={schema_error}"],
            explanation="Model output failed strict JSON/schema validation.",
        )

    # Check if Safety Gate rejected an Agent decision (skip VLM_REQUESTED_STOP)
    rejected_events = [
        ev for ev in decision_events
        if ev.get("event_type") == "SKILL_REJECTED"
        and ev.get("failure_reason") not in {"VLM_REQUESTED_STOP", "CAPABILITY_UNSUPPORTED"}
    ]
    if agent_violated_safety_gate or rejected_events:
        ev_reasons = [str(ev.get("failure_reason") or ev.get("validation_result")) for ev in rejected_events]
        if safety_gate_failure_code:
            ev_reasons.append(safety_gate_failure_code)
        return FailureAttributionResult(
            primary_category=FailureAttributionCategory.AGENT_DECISION_FAILURE,
            secondary_categories=[FailureAttributionCategory.SAFETY_GATE_REJECTION],
            evidence=ev_reasons,
            explanation="Agent proposed an illegal/disallowed/premature action rejected by Safety Gate.",
        )

    # Inspect Skill failures vs Perception failures vs Safe Stop
    failed_skills = [ex for ex in skill_execs if ex.get("status") == "FAILED"]
    if failed_skills:
        last_fail = failed_skills[-1]
        skill_id = str(last_fail.get("skill_id") or "")
        fcode = str(last_fail.get("failure_code") or failure_reason)
        if fcode in {"CUBE_NOT_LOCALIZED", "INSUFFICIENT_MASK_PIXELS", "DEPTH_UNAVAILABLE", "NO_VALID_OBSERVATIONS"} or (
            skill_id == "observe_workspace"
        ):
            return FailureAttributionResult(
                primary_category=FailureAttributionCategory.PERCEPTION_FAILURE,
                evidence=[f"skill={skill_id}", f"failure_code={fcode}", str(last_fail.get("failure_reason") or "")],
                explanation="Perception / RGB-D sensor stream failed to localize or observe cube.",
            )
        return FailureAttributionResult(
            primary_category=FailureAttributionCategory.SKILL_EXECUTION_FAILURE,
            evidence=[
                f"skill={skill_id}",
                f"failure_code={fcode}",
                str(last_fail.get("failure_reason") or ""),
                f"causal_refs={last_fail.get('causal_refs')}",
            ],
            explanation=(
                "Agent selected a legal skill, but physical MuJoCo execution/contact verification failed"
                + (" (Agent subsequently issued SAFE_STOP)." if failure_reason == "VLM_REQUESTED_STOP" else ".")
            ),
        )

    if failure_reason in {"MAX_DECISION_ROUNDS_EXCEEDED", "MAX_VLM_CALLS_EXCEEDED", "MAX_OBSERVE_CALLS_EXCEEDED", "MAX_REORIENT_CALLS_EXCEEDED"}:
        return FailureAttributionResult(
            primary_category=FailureAttributionCategory.AGENT_DECISION_FAILURE,
            evidence=[f"failure_reason={failure_reason}", f"skills_executed={[e.get('skill_id') for e in skill_execs]}"],
            explanation="Agent exhausted decision/call budget without completing or safely stopping.",
        )

    if failure_reason == "VLM_REQUESTED_STOP":
        # Agent stopped cleanly; check if a prior perception/skill issue caused it
        return FailureAttributionResult(
            primary_category=FailureAttributionCategory.PERCEPTION_FAILURE
            if any("INSUFFICIENT_MASK_PIXELS" in str(ev) or "CUBE_NOT_LOCALIZED" in str(ev) for ev in decision_events)
            else FailureAttributionCategory.AGENT_DECISION_FAILURE,
            evidence=[f"failure_reason={failure_reason}"],
            explanation="Agent issued SAFE_STOP during closed-loop execution.",
        )

    return FailureAttributionResult(
        primary_category=FailureAttributionCategory.TEST_HARNESS_FAILURE,
        evidence=[f"status={status}", f"failure_reason={failure_reason}"],
        explanation="Unclassified mission failure.",
    )
