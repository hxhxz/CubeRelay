"""Failure-Aware Skill Planning v6.

The deterministic geometry planner owns the bounded grasp-option set. High-level
planners may select one option, request another observation, or abort. They never
emit joint controls or weaken Skill safety checks.
"""

from __future__ import annotations

import base64
import hashlib
import io
import json
import math
import time
import urllib.request
from collections.abc import Callable
from typing import Any, Literal, Protocol

import numpy as np
from pydantic import BaseModel, ConfigDict, Field

from .skill_agent import (
    ApproachGraspInput,
    EstablishGraspInput,
    FailureCode,
    ObserveCubeInput,
    PlanGraspInput,
    RetreatInput,
    SkillLog,
    SkillRuntime,
    TestLiftInput,
    VerifyPoseInput,
)
from .v2_types import CubeDetection, GraspCandidate, SceneSemantics
from .vlm import SceneVLM


def _angle_distance(first: float, second: float, period: float = 2 * math.pi) -> float:
    return abs((first - second + period / 2) % period - period / 2)


class ContactSnapshot(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    left_contact_rate: float = 0.0
    right_contact_rate: float = 0.0
    left_normal_force_n: float = 0.0
    right_normal_force_n: float = 0.0
    max_slip_m: float = 0.0


class GraspAttemptRecord(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    attempt: int
    candidate_index: int
    face_pair: str
    tangent_offset_m: float
    closure_offset_m: float
    cube_world_position_m: tuple[float, float, float]
    cube_world_yaw_rad: float
    gripper_target_world_position_m: tuple[float, float, float]
    gripper_target_world_yaw_rad: float
    gripper_pose_in_object_m: tuple[float, float, float]
    gripper_yaw_in_object_rad: float
    contact: ContactSnapshot
    failure_code: str | None
    success: bool
    repeated_geometry: bool
    image_sha256: str


class GraspAttemptMemory:
    """Episode-local memory with object-frame geometric repeat detection."""

    def __init__(
        self,
        *,
        local_position_tolerance_m: float = .004,
        local_yaw_tolerance_rad: float = math.radians(3),
        world_position_tolerance_m: float = .015,
        world_yaw_tolerance_rad: float = math.radians(5),
    ) -> None:
        self.records: list[GraspAttemptRecord] = []
        self.local_position_tolerance_m = local_position_tolerance_m
        self.local_yaw_tolerance_rad = local_yaw_tolerance_rad
        self.world_position_tolerance_m = world_position_tolerance_m
        self.world_yaw_tolerance_rad = world_yaw_tolerance_rad

    def geometrically_similar(
        self,
        *,
        cube_world_position_m: tuple[float, float, float],
        cube_world_yaw_rad: float,
        face_pair: str,
        gripper_pose_in_object_m: tuple[float, float, float],
        gripper_yaw_in_object_rad: float,
    ) -> bool:
        for record in self.records:
            if record.face_pair != face_pair:
                continue
            local_distance = float(np.linalg.norm(
                np.asarray(record.gripper_pose_in_object_m)
                - np.asarray(gripper_pose_in_object_m)
            ))
            world_distance = float(np.linalg.norm(
                np.asarray(record.cube_world_position_m)
                - np.asarray(cube_world_position_m)
            ))
            if (
                local_distance <= self.local_position_tolerance_m
                and _angle_distance(
                    record.gripper_yaw_in_object_rad, gripper_yaw_in_object_rad, math.pi
                ) <= self.local_yaw_tolerance_rad
                and world_distance <= self.world_position_tolerance_m
                and _angle_distance(
                    record.cube_world_yaw_rad, cube_world_yaw_rad, math.pi / 2
                ) <= self.world_yaw_tolerance_rad
            ):
                return True
        return False

    def add(self, record: GraspAttemptRecord) -> None:
        self.records.append(record)

    def snapshot(self) -> tuple[GraspAttemptRecord, ...]:
        return tuple(self.records)


class GeometryGraspOption(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    option_id: str
    candidate_index: int = Field(ge=0, le=1)
    face_pair: str
    wrist_yaw_rad: float
    tangent_offset_m: float = Field(ge=-.02, le=.02)
    closure_offset_m: float = Field(ge=-.015, le=.015)
    gripper_target_world_position_m: tuple[float, float, float]
    gripper_pose_in_object_m: tuple[float, float, float]
    gripper_yaw_in_object_rad: float
    ik_feasible: bool
    collision_free: bool
    safety_checked: bool
    geometry_score: float
    repeated_geometry: bool
    rejection_reason: str | None = None


class DeterministicFailureAwareGeometryPlanner:
    """Generate a finite, checked option set; no learned low-level geometry."""

    offsets = (
        (.01, -.015), (.01, .015), (-.01, -.015), (-.01, .015),
        (0.0, 0.0), (.02, 0.0), (-.02, 0.0),
    )

    def generate(
        self,
        detection: CubeDetection,
        candidates: tuple[GraspCandidate, ...],
        memory: GraspAttemptMemory,
    ) -> tuple[GeometryGraspOption, ...]:
        options: list[GeometryGraspOption] = []
        x, y, z = detection.center_world_m
        for candidate_index, candidate in enumerate(candidates):
            relative_yaw = (
                candidate.wrist_yaw_radians - detection.yaw_radians + math.pi
            ) % (2 * math.pi) - math.pi
            cosine, sine = math.cos(candidate.wrist_yaw_radians), math.sin(
                candidate.wrist_yaw_radians
            )
            for tangent, closure in self.offsets:
                offset_x = cosine * tangent - sine * closure
                offset_y = sine * tangent + cosine * closure
                world_target = (x + offset_x, y + offset_y, z)
                local_pose = (tangent, closure, 0.0)
                repeated = memory.geometrically_similar(
                    cube_world_position_m=detection.center_world_m,
                    cube_world_yaw_rad=detection.yaw_radians,
                    face_pair=candidate.face_pair,
                    gripper_pose_in_object_m=local_pose,
                    gripper_yaw_in_object_rad=relative_yaw,
                )
                safety_checked = candidate.ik_feasible and candidate.collision_free
                score = (
                    candidate.contact_geometry_score
                    - .08 * candidate.motion_cost
                    - (2.0 if repeated else 0.0)
                    - .4 * abs(closure) / .015
                    - .1 * abs(tangent) / .02
                )
                option_id = (
                    f"c{candidate_index}_t{round(tangent * 1000):+d}"
                    f"_c{round(closure * 1000):+d}"
                )
                options.append(GeometryGraspOption(
                    option_id=option_id,
                    candidate_index=candidate_index,
                    face_pair=candidate.face_pair,
                    wrist_yaw_rad=candidate.wrist_yaw_radians,
                    tangent_offset_m=tangent,
                    closure_offset_m=closure,
                    gripper_target_world_position_m=world_target,
                    gripper_pose_in_object_m=local_pose,
                    gripper_yaw_in_object_rad=relative_yaw,
                    ik_feasible=candidate.ik_feasible,
                    collision_free=candidate.collision_free,
                    safety_checked=safety_checked,
                    geometry_score=score,
                    repeated_geometry=repeated,
                    rejection_reason=candidate.rejection_reason,
                ))
        return tuple(sorted(
            options,
            key=lambda option: (
                not option.safety_checked,
                option.repeated_geometry,
                -option.geometry_score,
                option.option_id,
            ),
        ))


class FailureAwareObservation(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    attempt: int
    semantics: SceneSemantics
    detection: CubeDetection
    options: tuple[GeometryGraspOption, ...]
    memory: tuple[GraspAttemptRecord, ...]
    failure_history: tuple[str, ...]
    image_shape: tuple[int, int, int]
    image_sha256: str


class FailureAwareDecision(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    action: Literal["select", "reobserve", "abort"]
    option_id: str | None = None
    reason: str


class FailureAwarePlanner(Protocol):
    name: str
    max_attempts: int
    decision_cost: dict[str, float]
    def decide(
        self, observation: FailureAwareObservation, rgb: np.ndarray
    ) -> FailureAwareDecision: ...


class FixedBudgetPlanner:
    """Fixed-1 or Fixed-3: identical option every attempt, no adaptation."""

    def __init__(self, attempts: Literal[1, 3]) -> None:
        self.max_attempts = attempts
        self.name = f"fixed_{attempts}"
        self.decision_cost = {
            "planner_calls": 0.0, "vlm_calls": 0.0, "decision_ms": 0.0,
            "input_tokens": 0.0, "output_tokens": 0.0, "cost_usd": 0.0,
        }

    def decide(
        self, observation: FailureAwareObservation, rgb: np.ndarray
    ) -> FailureAwareDecision:
        del rgb
        self.decision_cost["planner_calls"] += 1
        baseline = next(
            option for option in observation.options
            if option.candidate_index == 1
            and option.tangent_offset_m == .01
            and option.closure_offset_m == -.015
        )
        return FailureAwareDecision(
            action="select", option_id=baseline.option_id,
            reason="fixed option; retries intentionally ignore memory",
        )


class FailureAwareRulePlanner:
    name = "rule_based_3"
    max_attempts = 3

    def __init__(self) -> None:
        self.decision_cost = {
            "planner_calls": 0.0, "vlm_calls": 0.0, "decision_ms": 0.0,
            "input_tokens": 0.0, "output_tokens": 0.0, "cost_usd": 0.0,
        }

    def decide(
        self, observation: FailureAwareObservation, rgb: np.ndarray
    ) -> FailureAwareDecision:
        del rgb
        started = time.perf_counter()
        self.decision_cost["planner_calls"] += 1
        if observation.attempt == 1:
            baseline = next(
                option for option in observation.options
                if option.candidate_index == 1
                and option.tangent_offset_m == .01
                and option.closure_offset_m == -.015
            )
            self.decision_cost["decision_ms"] += (time.perf_counter() - started) * 1000
            return FailureAwareDecision(
                action="select", option_id=baseline.option_id,
                reason="shared first-attempt baseline before failure-aware adaptation",
            )
        feasible = [
            option for option in observation.options
            if option.safety_checked and not option.repeated_geometry
        ]
        if not feasible:
            decision = FailureAwareDecision(
                action="reobserve" if observation.attempt < self.max_attempts else "abort",
                reason="no non-repeated safe geometry remains",
            )
        else:
            last = observation.memory[-1] if observation.memory else None
            if last and last.contact.left_contact_rate > last.contact.right_contact_rate:
                preferred = [o for o in feasible if o.closure_offset_m < 0]
            elif last and last.contact.right_contact_rate > last.contact.left_contact_rate:
                preferred = [o for o in feasible if o.closure_offset_m > 0]
            else:
                preferred = []
            selected = max(preferred or feasible, key=lambda option: option.geometry_score)
            decision = FailureAwareDecision(
                action="select", option_id=selected.option_id,
                reason="highest-scoring safe non-repeated geometry with contact-side correction",
            )
        self.decision_cost["decision_ms"] += (time.perf_counter() - started) * 1000
        return decision


class RealVLMCallTrace(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    call_index: int
    provider: str
    model: str
    endpoint_host: str
    prompt_sha256: str
    image_sha256: str
    latency_ms: float
    input_tokens: int | None = None
    output_tokens: int | None = None
    cost_usd: float | None = None
    response_text: str
    parsed_decision: FailureAwareDecision | None = None
    error: str | None = None


class OpenAICompatibleFailureAwareVLM:
    """Real cloud/vLLM vision planner with auditable calls and strict output."""

    def __init__(
        self,
        *,
        endpoint: str,
        model: str,
        api_key: str,
        timeout_seconds: float = 45.0,
        input_cost_per_million: float | None = None,
        output_cost_per_million: float | None = None,
    ) -> None:
        if not endpoint or not model:
            raise ValueError("real VLM endpoint and model are required")
        self.endpoint = endpoint.rstrip("/")
        self.model = model
        self.api_key = api_key
        self.timeout_seconds = timeout_seconds
        self.input_cost_per_million = input_cost_per_million
        self.output_cost_per_million = output_cost_per_million
        self.traces: list[RealVLMCallTrace] = []

    def decide(
        self, observation: FailureAwareObservation, rgb: np.ndarray
    ) -> tuple[FailureAwareDecision, RealVLMCallTrace]:
        from PIL import Image
        from urllib.parse import urlparse

        buffer = io.BytesIO()
        Image.fromarray(rgb).save(buffer, format="JPEG", quality=88)
        encoded = base64.b64encode(buffer.getvalue()).decode("ascii")
        compact = observation.model_dump(mode="json")
        prompt = (
            "You are a high-level grasp recovery planner. Choose only one supplied "
            "option_id, request reobserve, or abort. Never output joint commands, "
            "simulator state changes, or safety overrides. Prefer safe non-repeated "
            "object-frame geometry and use contact/failure history. Return JSON with "
            "action, option_id, reason. Context: " + json.dumps(compact, separators=(",", ":"))
        )
        payload = {
            "model": self.model,
            "temperature": 0,
            "response_format": {"type": "json_object"},
            "messages": [{"role": "user", "content": [
                {"type": "text", "text": prompt},
                {"type": "image_url", "image_url": {
                    "url": f"data:image/jpeg;base64,{encoded}"}},
            ]}],
        }
        request = urllib.request.Request(
            self.endpoint + "/chat/completions",
            data=json.dumps(payload).encode(),
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self.api_key}",
            },
        )
        started = time.perf_counter()
        response_text = ""
        parsed: FailureAwareDecision | None = None
        error: str | None = None
        usage: dict[str, Any] = {}
        try:
            with urllib.request.urlopen(request, timeout=self.timeout_seconds) as response:
                result = json.loads(response.read())
            response_text = str(result["choices"][0]["message"]["content"])
            decision_data = json.loads(response_text)
            # OpenAI-compatible providers use a few common high-level aliases.
            # Canonicalization is deterministic and does not create candidates,
            # joint commands, or safety overrides; the raw response is retained.
            action_aliases = {
                "select_option": "select",
                "execute": "select",
                "execute_option": "select",
                "execute_grasp": "select",
                "request_reobserve": "reobserve",
                "request_observation": "reobserve",
            }
            decision_data["action"] = action_aliases.get(
                decision_data.get("action"), decision_data.get("action")
            )
            parsed = FailureAwareDecision.model_validate(decision_data)
            usage = (
                result.get("usage") or result.get("usageMetadata")
                or result.get("usage_metadata") or {}
            )
        except Exception as exc:
            error = f"{type(exc).__name__}: {exc}"
        input_tokens = usage.get("prompt_tokens", usage.get("promptTokenCount"))
        output_tokens = usage.get(
            "completion_tokens", usage.get("candidatesTokenCount")
        )
        cost = None
        if (
            input_tokens is not None and output_tokens is not None
            and self.input_cost_per_million is not None
            and self.output_cost_per_million is not None
        ):
            cost = (
                input_tokens * self.input_cost_per_million
                + output_tokens * self.output_cost_per_million
            ) / 1_000_000
        trace = RealVLMCallTrace(
            call_index=len(self.traces) + 1,
            provider="openai_compatible_real",
            model=self.model,
            endpoint_host=urlparse(self.endpoint).netloc,
            prompt_sha256=hashlib.sha256(prompt.encode()).hexdigest(),
            image_sha256=observation.image_sha256,
            latency_ms=(time.perf_counter() - started) * 1000,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            cost_usd=cost,
            response_text=response_text,
            parsed_decision=parsed,
            error=error,
        )
        self.traces.append(trace)
        if parsed is None:
            raise RuntimeError(f"real VLM decision failed: {error}")
        return parsed, trace


class RealVLMFailureAwarePlanner:
    name = "real_vlm_3"
    max_attempts = 3

    def __init__(self, provider: OpenAICompatibleFailureAwareVLM) -> None:
        self.provider = provider
        self.decision_cost = {
            "planner_calls": 0.0, "vlm_calls": 0.0, "decision_ms": 0.0,
            "input_tokens": 0.0, "output_tokens": 0.0, "cost_usd": 0.0,
        }

    def decide(
        self, observation: FailureAwareObservation, rgb: np.ndarray
    ) -> FailureAwareDecision:
        self.decision_cost["planner_calls"] += 1
        if observation.attempt == 1:
            baseline = next(
                option for option in observation.options
                if option.candidate_index == 1
                and option.tangent_offset_m == .01
                and option.closure_offset_m == -.015
            )
            return FailureAwareDecision(
                action="select", option_id=baseline.option_id,
                reason="shared first-attempt baseline; VLM reserved for recovery",
            )
        self.decision_cost["vlm_calls"] += 1
        trace_count = len(self.provider.traces)
        try:
            decision, trace = self.provider.decide(observation, rgb)
        except Exception:
            if len(self.provider.traces) > trace_count:
                failed_trace = self.provider.traces[-1]
                self.decision_cost["decision_ms"] += failed_trace.latency_ms
                self.decision_cost["input_tokens"] += failed_trace.input_tokens or 0
                self.decision_cost["output_tokens"] += failed_trace.output_tokens or 0
                self.decision_cost["cost_usd"] += failed_trace.cost_usd or 0
            raise
        self.decision_cost["decision_ms"] += trace.latency_ms
        self.decision_cost["input_tokens"] += trace.input_tokens or 0
        self.decision_cost["output_tokens"] += trace.output_tokens or 0
        self.decision_cost["cost_usd"] += trace.cost_usd or 0
        if decision.action == "select":
            option = next(
                (item for item in observation.options if item.option_id == decision.option_id),
                None,
            )
            if option is None or not option.safety_checked:
                raise ValueError("real VLM selected an unknown or unsafe option")
        return decision


class FailureAwareEpisodeResult(BaseModel):
    planner: str
    seed: int
    first_attempt_success: bool
    final_success: bool
    recovery_success: bool
    attempts: int
    abnormal_push: bool
    repeated_attempt_count: int
    failure_history: tuple[str, ...]
    decision_cost: dict[str, float]
    attempt_memory: tuple[GraspAttemptRecord, ...]
    skill_logs: tuple[SkillLog, ...]
    contact_trace: tuple[dict[str, Any], ...]
    vlm_call_traces: tuple[RealVLMCallTrace, ...] = ()


class FailureAwareSkillAgent:
    def __init__(
        self,
        backend: Any,
        scene_vlm: SceneVLM,
        planner: FailureAwarePlanner,
        *,
        geometry_planner: DeterministicFailureAwareGeometryPlanner | None = None,
    ) -> None:
        self.backend = backend
        self.runtime = SkillRuntime(backend, scene_vlm)
        self.planner = planner
        self.geometry_planner = geometry_planner or DeterministicFailureAwareGeometryPlanner()
        self.memory = GraspAttemptMemory()

    def run(
        self, seed: int, scramble_steps: int = 15, *, reset_scene: bool = True
    ) -> FailureAwareEpisodeResult:
        if reset_scene:
            self.backend.reset_random(seed, scramble_steps)
        failures: list[str] = []
        traces: list[dict[str, Any]] = []
        abnormal_push = success = first_success = False
        attempts = 0
        reobserve_budget = 1
        for attempt in range(1, self.planner.max_attempts + 1):
            attempts = attempt
            observed = self.runtime.observe_cube(ObserveCubeInput())
            if not observed.success or observed.detection is None:
                failures.append((observed.failure_code or FailureCode.INTERNAL_ERROR).value)
                break
            planned = self.runtime.plan_grasp(PlanGraspInput(detection=observed.detection))
            if not planned.success:
                failures.append((planned.failure_code or FailureCode.INTERNAL_ERROR).value)
                break
            options = self.geometry_planner.generate(
                observed.detection, planned.candidates, self.memory
            )
            context = FailureAwareObservation(
                attempt=attempt,
                semantics=observed.semantics,  # type: ignore[arg-type]
                detection=observed.detection,
                options=options,
                memory=self.memory.snapshot(),
                failure_history=tuple(failures),
                image_shape=observed.image_shape,  # type: ignore[arg-type]
                image_sha256=observed.image_sha256 or "",
            )
            try:
                decision = self.planner.decide(
                    context, self.runtime.state.last_frame.rgb
                )
            except Exception:
                failures.append("VLM_OR_PLANNER_DECISION_FAILED")
                break
            if decision.action == "reobserve":
                if reobserve_budget <= 0:
                    failures.append("REOBSERVE_BUDGET_EXHAUSTED")
                    break
                reobserve_budget -= 1
                observed = self.runtime.observe_cube(ObserveCubeInput())
                if not observed.success or observed.detection is None:
                    failures.append((observed.failure_code or FailureCode.INTERNAL_ERROR).value)
                    break
                planned = self.runtime.plan_grasp(PlanGraspInput(detection=observed.detection))
                options = self.geometry_planner.generate(
                    observed.detection, planned.candidates, self.memory
                )
                context = context.model_copy(update={
                    "semantics": observed.semantics,
                    "detection": observed.detection,
                    "options": options,
                    "image_shape": observed.image_shape,
                    "image_sha256": observed.image_sha256 or "",
                })
                try:
                    decision = self.planner.decide(
                        context, self.runtime.state.last_frame.rgb
                    )
                except Exception:
                    failures.append("VLM_OR_PLANNER_DECISION_FAILED")
                    break
            if failures and failures[-1] == "VLM_OR_PLANNER_DECISION_FAILED":
                break
            if decision.action == "abort":
                failures.append("PLANNER_ABORTED")
                break
            option = next(
                (item for item in options if item.option_id == decision.option_id), None
            )
            if option is None or not option.safety_checked:
                failures.append("PLANNER_SELECTED_INVALID_OPTION")
                break
            approached = self.runtime.approach_grasp(ApproachGraspInput(
                detection=observed.detection,
                candidate_index=option.candidate_index,
                tangent_offset_m=option.tangent_offset_m,
                closure_offset_m=option.closure_offset_m,
            ))
            abnormal_push |= (
                approached.cube_displacement_m
                > self.backend.grasp_config.approach_displacement_limit_m
            )
            contact = ContactSnapshot(
                left_contact_rate=float(approached.left_contact_count > 0),
                right_contact_rate=float(approached.right_contact_count > 0),
            )
            failure_code: str | None = None
            if not approached.success:
                failure_code = (approached.failure_code or FailureCode.INTERNAL_ERROR).value
            else:
                verified = self.runtime.verify_pose(VerifyPoseInput(
                    expected_detection=observed.detection
                ))
                if not verified.success:
                    failure_code = (verified.failure_code or FailureCode.INTERNAL_ERROR).value
                else:
                    established = self.runtime.establish_grasp(EstablishGraspInput())
                    contact = ContactSnapshot(
                        left_contact_rate=established.left_contact_rate,
                        right_contact_rate=established.right_contact_rate,
                        left_normal_force_n=established.left_normal_force_n,
                        right_normal_force_n=established.right_normal_force_n,
                        max_slip_m=established.max_slip_m,
                    )
                    if not established.success:
                        failure_code = (
                            established.failure_code or FailureCode.INTERNAL_ERROR
                        ).value
                    else:
                        lifted = self.runtime.test_lift(TestLiftInput())
                        contact = contact.model_copy(update={
                            "max_slip_m": lifted.max_slip_m
                        })
                        success = lifted.success
                        if not success:
                            failure_code = (
                                lifted.failure_code or FailureCode.INTERNAL_ERROR
                            ).value
            record = GraspAttemptRecord(
                attempt=attempt,
                candidate_index=option.candidate_index,
                face_pair=option.face_pair,
                tangent_offset_m=option.tangent_offset_m,
                closure_offset_m=option.closure_offset_m,
                cube_world_position_m=observed.detection.center_world_m,
                cube_world_yaw_rad=observed.detection.yaw_radians,
                gripper_target_world_position_m=option.gripper_target_world_position_m,
                gripper_target_world_yaw_rad=option.wrist_yaw_rad,
                gripper_pose_in_object_m=option.gripper_pose_in_object_m,
                gripper_yaw_in_object_rad=option.gripper_yaw_in_object_rad,
                contact=contact,
                failure_code=failure_code,
                success=success,
                repeated_geometry=option.repeated_geometry,
                image_sha256=observed.image_sha256 or "",
            )
            self.memory.add(record)
            traces.extend(self.backend.contact_debug_trace)
            if success:
                first_success = attempt == 1
                break
            failures.append(failure_code or FailureCode.INTERNAL_ERROR.value)
            self.runtime.retreat(RetreatInput(reason=failures[-1]))
        provider = getattr(self.planner, "provider", None)
        vlm_traces = tuple(getattr(provider, "traces", ()))
        return FailureAwareEpisodeResult(
            planner=self.planner.name,
            seed=seed,
            first_attempt_success=first_success,
            final_success=success,
            recovery_success=success and attempts > 1,
            attempts=attempts,
            abnormal_push=abnormal_push,
            repeated_attempt_count=sum(r.repeated_geometry for r in self.memory.records),
            failure_history=tuple(failures),
            decision_cost=dict(self.planner.decision_cost),
            attempt_memory=self.memory.snapshot(),
            skill_logs=tuple(self.runtime.logs),
            contact_trace=tuple(traces),
            vlm_call_traces=vlm_traces,
        )
