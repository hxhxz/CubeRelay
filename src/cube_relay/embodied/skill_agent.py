"""Safety-gated grasp Skills and constrained high-level planners.

Planners may choose only a Skill, a precomputed candidate and bounded offsets.
All joint control, contact checks and simulator access stay in the deterministic
MuJoCo backend.
"""

from __future__ import annotations

import hashlib
import math
import time
from enum import Enum
from typing import Any, Literal, Protocol

import numpy as np
from pydantic import BaseModel, ConfigDict, Field

from .perception_v2 import DeterministicCubeLocalizer
from .v2_types import CubeDetection, GraspCandidate, RGBDFrame, SceneSemantics
from .vlm import SceneVLM


class FailureCode(str, Enum):
    PRECONDITION_FAILED = "PRECONDITION_FAILED"
    TIMEOUT = "TIMEOUT"
    CUBE_NOT_VISIBLE = "CUBE_NOT_VISIBLE"
    LOCALIZATION_FAILED = "LOCALIZATION_FAILED"
    NO_FEASIBLE_GRASP = "NO_FEASIBLE_GRASP"
    APPROACH_UNEXPECTED_COLLISION = "APPROACH_UNEXPECTED_COLLISION"
    APPROACH_OBJECT_DISPLACED = "APPROACH_OBJECT_DISPLACED"
    POSE_VERIFICATION_FAILED = "POSE_VERIFICATION_FAILED"
    BILATERAL_CONTACT_NOT_ESTABLISHED = "BILATERAL_CONTACT_NOT_ESTABLISHED"
    BILATERAL_CONTACT_UNSTABLE = "BILATERAL_CONTACT_UNSTABLE"
    BILATERAL_CONTACT_REQUIRED = "BILATERAL_CONTACT_REQUIRED"
    TRIAL_LIFT_UNSTABLE = "TRIAL_LIFT_UNSTABLE"
    FULL_LIFT_UNSTABLE = "FULL_LIFT_UNSTABLE"
    RELEASE_FAILED = "RELEASE_FAILED"
    INTERNAL_ERROR = "INTERNAL_ERROR"


class SkillInput(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class SkillOutput(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    success: bool
    failure_code: FailureCode | None = None
    message: str = ""


class ObserveCubeInput(SkillInput):
    camera_name: Literal["overhead"] = "overhead"


class ObserveCubeOutput(SkillOutput):
    semantics: SceneSemantics | None = None
    detection: CubeDetection | None = None
    image_shape: tuple[int, int, int] | None = None
    image_sha256: str | None = None


class PlanGraspInput(SkillInput):
    detection: CubeDetection


class PlanGraspOutput(SkillOutput):
    candidates: tuple[GraspCandidate, ...] = ()


class ApproachGraspInput(SkillInput):
    detection: CubeDetection
    candidate_index: int = Field(ge=0, le=1)
    tangent_offset_m: float = Field(ge=-.02, le=.02)
    closure_offset_m: float = Field(ge=-.015, le=.015)


class ApproachGraspOutput(SkillOutput):
    candidate_index: int
    cube_displacement_m: float = 0.0
    unexpected_contact_count: int = 0
    left_contact_count: int = 0
    right_contact_count: int = 0


class VerifyPoseInput(SkillInput):
    expected_detection: CubeDetection


class VerifyPoseOutput(SkillOutput):
    observed_detection: CubeDetection | None = None
    position_error_m: float | None = None
    yaw_error_rad: float | None = None


class EstablishGraspInput(SkillInput):
    minimum_force_n: float = Field(default=.35, ge=.35, le=2.0)


class EstablishGraspOutput(SkillOutput):
    left_contact_rate: float = 0.0
    right_contact_rate: float = 0.0
    left_normal_force_n: float = 0.0
    right_normal_force_n: float = 0.0
    max_slip_m: float = 0.0


class TestLiftInput(SkillInput):
    maximum_slip_m: float = Field(default=.03, ge=.005, le=.03)


class TestLiftOutput(SkillOutput):
    trial_lift_success: bool = False
    full_lift_success: bool = False
    lift_height_m: float = 0.0
    bilateral_contact_fraction: float = 0.0
    max_slip_m: float = 0.0


class RetreatInput(SkillInput):
    reason: str = "recovery"


class RetreatOutput(SkillOutput):
    released: bool = False


class SkillLog(BaseModel):
    model_config = ConfigDict(extra="forbid")
    sequence: int
    skill: str
    started_at_sim_seconds: float
    duration_ms: float
    timeout_seconds: float
    preconditions: dict[str, bool]
    input: dict[str, Any]
    output: dict[str, Any]


class AgentState(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)
    observed: bool = False
    planned: bool = False
    approached: bool = False
    pose_verified: bool = False
    bilateral_grasp: bool = False
    lifted: bool = False
    last_frame: RGBDFrame | None = None
    semantics: SceneSemantics | None = None
    detection: CubeDetection | None = None
    candidates: tuple[GraspCandidate, ...] = ()
    failures: list[str] = Field(default_factory=list)


class SkillRuntime:
    """Executes Skills and emits uniform, observable logs."""

    timeouts = {
        "observe_cube": 3.0,
        "plan_grasp": 1.0,
        "approach_grasp": 4.0,
        "verify_pose": 3.0,
        "establish_grasp": 4.0,
        "test_lift": 5.0,
        "retreat": 3.0,
    }

    def __init__(self, backend: Any, scene_vlm: SceneVLM) -> None:
        self.backend = backend
        self.scene_vlm = scene_vlm
        self.localizer = DeterministicCubeLocalizer()
        self.state = AgentState()
        self.logs: list[SkillLog] = []

    def _record(
        self, skill: str, started: float, sim_started: float, preconditions: dict[str, bool],
        input_model: SkillInput, output_model: SkillOutput,
    ) -> SkillOutput:
        duration = (time.perf_counter() - started) * 1000
        timeout = self.timeouts[skill]
        if duration > timeout * 1000 and output_model.success:
            output_model = output_model.model_copy(update={
                "success": False, "failure_code": FailureCode.TIMEOUT,
                "message": f"{skill} exceeded {timeout:.1f}s timeout",
            })
        self.logs.append(SkillLog(
            sequence=len(self.logs) + 1,
            skill=skill,
            started_at_sim_seconds=sim_started,
            duration_ms=duration,
            timeout_seconds=timeout,
            preconditions=preconditions,
            input=input_model.model_dump(mode="json"),
            output=output_model.model_dump(mode="json"),
        ))
        if not output_model.success and output_model.failure_code:
            self.state.failures.append(output_model.failure_code.value)
        return output_model

    def observe_cube(self, value: ObserveCubeInput) -> ObserveCubeOutput:
        started, sim = time.perf_counter(), float(self.backend.data.time)
        pre = {"camera_available": True}
        frame = self.backend.capture_rgbd(value.camera_name)
        semantics = self.scene_vlm.understand(frame.rgb)
        detection = self.localizer.locate(frame) if semantics.cube_visible else None
        success = detection is not None
        output = ObserveCubeOutput(
            success=success,
            failure_code=None if success else (
                FailureCode.LOCALIZATION_FAILED if semantics.cube_visible
                else FailureCode.CUBE_NOT_VISIBLE
            ),
            semantics=semantics,
            detection=detection,
            image_shape=tuple(frame.rgb.shape),
            image_sha256=hashlib.sha256(frame.rgb.tobytes()).hexdigest(),
        )
        if success:
            self.state.observed = True
            self.state.planned = self.state.approached = self.state.pose_verified = False
            self.state.bilateral_grasp = self.state.lifted = False
            self.state.last_frame, self.state.semantics = frame, semantics
            self.state.detection = detection
        return self._record("observe_cube", started, sim, pre, value, output)  # type: ignore[return-value]

    def plan_grasp(self, value: PlanGraspInput) -> PlanGraspOutput:
        started, sim = time.perf_counter(), float(self.backend.data.time)
        pre = {"cube_observed": self.state.observed}
        if not all(pre.values()):
            output = PlanGraspOutput(success=False, failure_code=FailureCode.PRECONDITION_FAILED)
        else:
            candidates = self.backend.generate_grasp_candidates(
                value.detection.center_world_m, value.detection.yaw_radians
            )
            success = any(item.ik_feasible and item.collision_free for item in candidates)
            output = PlanGraspOutput(
                success=success,
                failure_code=None if success else FailureCode.NO_FEASIBLE_GRASP,
                candidates=candidates,
            )
            if success:
                self.state.planned = True
                self.state.candidates = candidates
        return self._record("plan_grasp", started, sim, pre, value, output)  # type: ignore[return-value]

    def approach_grasp(self, value: ApproachGraspInput) -> ApproachGraspOutput:
        started, sim = time.perf_counter(), float(self.backend.data.time)
        pre = {"grasp_planned": self.state.planned,
               "candidate_exists": value.candidate_index < len(self.state.candidates)}
        if not all(pre.values()):
            output = ApproachGraspOutput(
                success=False, failure_code=FailureCode.PRECONDITION_FAILED,
                candidate_index=value.candidate_index,
            )
        else:
            raw = self.backend.skill_approach_grasp(
                value.detection.center_world_m,
                self.state.candidates[value.candidate_index],
                tangent_offset_m=value.tangent_offset_m,
                closure_offset_m=value.closure_offset_m,
            )
            code = FailureCode(raw["failure_code"]) if raw.get("failure_code") else None
            output = ApproachGraspOutput(
                success=bool(raw["success"]), failure_code=code,
                candidate_index=value.candidate_index,
                cube_displacement_m=float(raw.get("cube_displacement_m", 0)),
                unexpected_contact_count=int(raw.get("unexpected_contact_count", 0)),
                left_contact_count=int(raw.get("left_contact_count", 0)),
                right_contact_count=int(raw.get("right_contact_count", 0)),
            )
            self.state.approached = output.success
        return self._record("approach_grasp", started, sim, pre, value, output)  # type: ignore[return-value]

    def verify_pose(self, value: VerifyPoseInput) -> VerifyPoseOutput:
        started, sim = time.perf_counter(), float(self.backend.data.time)
        pre = {"approach_complete": self.state.approached}
        detection = None
        position_error = yaw_error = None
        if all(pre.values()):
            frame = self.backend.capture_rgbd("overhead")
            detection = self.localizer.locate(frame)
            if detection is not None:
                position_error = float(np.linalg.norm(
                    np.asarray(detection.center_world_m)
                    - np.asarray(value.expected_detection.center_world_m)
                ))
                yaw_error = abs((
                    detection.yaw_radians - value.expected_detection.yaw_radians
                    + math.pi / 4
                ) % (math.pi / 2) - math.pi / 4)
        success = (
            all(pre.values()) and detection is not None
            and position_error is not None
            and position_error <= self.backend.grasp_config.pose_verification_position_tolerance_m
        )
        output = VerifyPoseOutput(
            success=success,
            failure_code=None if success else (
                FailureCode.POSE_VERIFICATION_FAILED if all(pre.values())
                else FailureCode.PRECONDITION_FAILED
            ),
            observed_detection=detection,
            position_error_m=position_error,
            yaw_error_rad=yaw_error,
        )
        self.state.pose_verified = output.success
        if output.success and detection is not None:
            self.state.detection = detection
        return self._record("verify_pose", started, sim, pre, value, output)  # type: ignore[return-value]

    def establish_grasp(self, value: EstablishGraspInput) -> EstablishGraspOutput:
        started, sim = time.perf_counter(), float(self.backend.data.time)
        pre = {"pose_verified": self.state.pose_verified}
        if not all(pre.values()):
            output = EstablishGraspOutput(
                success=False, failure_code=FailureCode.PRECONDITION_FAILED
            )
        else:
            raw = self.backend.skill_establish_grasp()
            code = FailureCode(raw["failure_code"]) if raw.get("failure_code") else None
            force_ok = min(
                float(raw.get("left_normal_force_n", 0)),
                float(raw.get("right_normal_force_n", 0)),
            ) >= value.minimum_force_n
            output = EstablishGraspOutput(
                success=bool(raw["success"]) and force_ok,
                failure_code=(code if not raw["success"] else (
                    None if force_ok else FailureCode.BILATERAL_CONTACT_UNSTABLE
                )),
                left_contact_rate=float(raw.get("left_contact_rate", 0)),
                right_contact_rate=float(raw.get("right_contact_rate", 0)),
                left_normal_force_n=float(raw.get("left_normal_force_n", 0)),
                right_normal_force_n=float(raw.get("right_normal_force_n", 0)),
                max_slip_m=float(raw.get("max_slip_m", 0)),
            )
            self.state.bilateral_grasp = output.success
        return self._record("establish_grasp", started, sim, pre, value, output)  # type: ignore[return-value]

    def test_lift(self, value: TestLiftInput) -> TestLiftOutput:
        started, sim = time.perf_counter(), float(self.backend.data.time)
        pre = {"stable_bilateral_contact": self.state.bilateral_grasp}
        if not all(pre.values()):
            output = TestLiftOutput(
                success=False, failure_code=FailureCode.BILATERAL_CONTACT_REQUIRED
            )
        else:
            raw = self.backend.skill_test_lift()
            code = FailureCode(raw["failure_code"]) if raw.get("failure_code") else None
            slip_ok = float(raw.get("max_slip_m", 0)) <= value.maximum_slip_m
            output = TestLiftOutput(
                success=bool(raw["success"]) and slip_ok,
                failure_code=(code if not raw["success"] else (
                    None if slip_ok else FailureCode.TRIAL_LIFT_UNSTABLE
                )),
                trial_lift_success=bool(raw.get("trial_lift_success", False)),
                full_lift_success=bool(raw.get("full_lift_success", False)),
                lift_height_m=float(raw.get("lift_height_m", 0)),
                bilateral_contact_fraction=float(raw.get("bilateral_contact_fraction", 0)),
                max_slip_m=float(raw.get("max_slip_m", 0)),
            )
            self.state.lifted = output.success
        return self._record("test_lift", started, sim, pre, value, output)  # type: ignore[return-value]

    def retreat(self, value: RetreatInput) -> RetreatOutput:
        started, sim = time.perf_counter(), float(self.backend.data.time)
        pre = {"backend_ready": True}
        raw = self.backend.skill_retreat()
        code = FailureCode(raw["failure_code"]) if raw.get("failure_code") else None
        output = RetreatOutput(
            success=bool(raw["success"]), failure_code=code,
            released=bool(raw["success"]),
        )
        self.state = AgentState(failures=self.state.failures)
        return self._record("retreat", started, sim, pre, value, output)  # type: ignore[return-value]


class PlannerDecision(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    skill: Literal["approach_grasp"] = "approach_grasp"
    candidate_index: int = Field(ge=0, le=1)
    tangent_offset_m: float = Field(ge=-.02, le=.02)
    closure_offset_m: float = Field(ge=-.015, le=.015)
    recovery: Literal["retry", "abort"] = "abort"
    recovery_skill: Literal["retreat"] = "retreat"
    reason: str


class PlannerObservation(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    attempt: int
    semantics: SceneSemantics
    detection: CubeDetection
    candidates: tuple[GraspCandidate, ...]
    failure_history: tuple[str, ...]
    last_left_contact_rate: float = 0.0
    last_right_contact_rate: float = 0.0
    image_shape: tuple[int, int, int]
    image_sha256: str


class SkillPlanner(Protocol):
    name: str
    max_attempts: int
    decision_cost: dict[str, float]
    def decide(self, observation: PlannerObservation, rgb: np.ndarray) -> PlannerDecision: ...


class FixedPipelinePlanner:
    name = "fixed_pipeline"
    max_attempts = 1

    def __init__(self) -> None:
        self.decision_cost = {"planner_calls": 0, "vlm_calls": 0, "decision_ms": 0}

    def decide(self, observation: PlannerObservation, rgb: np.ndarray) -> PlannerDecision:
        del rgb
        self.decision_cost["planner_calls"] += 1
        return PlannerDecision(
            candidate_index=1, tangent_offset_m=.01, closure_offset_m=-.015,
            recovery="abort", reason="fixed production baseline",
        )


class RuleBasedSkillPlanner:
    name = "rule_based_skill_planner"
    max_attempts = 3

    def __init__(self) -> None:
        self.decision_cost = {"planner_calls": 0, "vlm_calls": 0, "decision_ms": 0}

    def decide(self, observation: PlannerObservation, rgb: np.ndarray) -> PlannerDecision:
        del rgb
        started = time.perf_counter()
        self.decision_cost["planner_calls"] += 1
        attempt = observation.attempt
        # Candidate switch is the first recovery. The third attempt applies a
        # bounded 10 mm correction away from the side that contacted alone.
        candidate = 1 if attempt < 3 else 0
        closure = -.015 if attempt == 1 else .015 if attempt == 2 else 0.0
        if attempt >= 3:
            if observation.last_left_contact_rate > observation.last_right_contact_rate:
                closure = -.01
            elif observation.last_right_contact_rate > observation.last_left_contact_rate:
                closure = .01
        self.decision_cost["decision_ms"] += (time.perf_counter() - started) * 1000
        return PlannerDecision(
            candidate_index=candidate,
            tangent_offset_m=.01,
            closure_offset_m=closure,
            recovery="retry" if attempt < self.max_attempts else "abort",
            reason="alternate opposing-face candidate, then bounded contact-balance correction",
        )


class VLMDecisionProvider(Protocol):
    def decide(self, observation: PlannerObservation, rgb: np.ndarray) -> dict[str, Any]: ...


class ConstrainedHeuristicVLMProvider:
    """Offline Mock of the VLM decision boundary used for reproducible tests."""

    def decide(self, observation: PlannerObservation, rgb: np.ndarray) -> dict[str, Any]:
        del rgb
        rule = RuleBasedSkillPlanner().decide(observation, np.empty((0, 0, 3)))
        return rule.model_dump()


class VLMAgentPlanner:
    name = "vlm_agent_planner"
    max_attempts = 3

    def __init__(self, provider: VLMDecisionProvider) -> None:
        self.provider = provider
        self.decision_cost = {"planner_calls": 0, "vlm_calls": 0, "decision_ms": 0}

    def decide(self, observation: PlannerObservation, rgb: np.ndarray) -> PlannerDecision:
        started = time.perf_counter()
        self.decision_cost["planner_calls"] += 1
        self.decision_cost["vlm_calls"] += 1
        # Pydantic rejects unknown fields and out-of-range parameters. The VLM
        # can never return joint targets or disable a safety check.
        decision = PlannerDecision.model_validate(self.provider.decide(observation, rgb))
        self.decision_cost["decision_ms"] += (time.perf_counter() - started) * 1000
        return decision


class GraspEpisodeResult(BaseModel):
    planner: str
    seed: int
    first_attempt_success: bool
    final_success: bool
    attempts: int
    abnormal_push: bool
    failure_history: tuple[str, ...]
    decision_cost: dict[str, float]
    skill_logs: tuple[SkillLog, ...]
    contact_trace: tuple[dict[str, Any], ...]


class SkillBasedGraspAgent:
    def __init__(self, backend: Any, scene_vlm: SceneVLM, planner: SkillPlanner) -> None:
        self.backend = backend
        self.runtime = SkillRuntime(backend, scene_vlm)
        self.planner = planner

    def run(self, seed: int, scramble_steps: int = 15) -> GraspEpisodeResult:
        self.backend.reset_random(seed, scramble_steps)
        failure_history: list[str] = []
        abnormal_push = False
        last_left = last_right = 0.0
        all_contact_trace: list[dict[str, Any]] = []
        attempts = 0
        success = False
        first_success = False
        for attempt in range(1, self.planner.max_attempts + 1):
            attempts = attempt
            observed = self.runtime.observe_cube(ObserveCubeInput())
            if not observed.success or observed.detection is None:
                failure_history.append((observed.failure_code or FailureCode.INTERNAL_ERROR).value)
                break
            planned = self.runtime.plan_grasp(PlanGraspInput(detection=observed.detection))
            if not planned.success:
                failure_history.append((planned.failure_code or FailureCode.INTERNAL_ERROR).value)
                break
            observation = PlannerObservation(
                attempt=attempt,
                semantics=observed.semantics,  # type: ignore[arg-type]
                detection=observed.detection,
                candidates=planned.candidates,
                failure_history=tuple(failure_history),
                last_left_contact_rate=last_left,
                last_right_contact_rate=last_right,
                image_shape=observed.image_shape,  # type: ignore[arg-type]
                image_sha256=observed.image_sha256 or "",
            )
            decision = self.planner.decide(observation, self.runtime.state.last_frame.rgb)
            approached = self.runtime.approach_grasp(ApproachGraspInput(
                detection=observed.detection,
                candidate_index=decision.candidate_index,
                tangent_offset_m=decision.tangent_offset_m,
                closure_offset_m=decision.closure_offset_m,
            ))
            if approached.cube_displacement_m > self.backend.grasp_config.approach_displacement_limit_m:
                abnormal_push = True
            if not approached.success:
                last_left = float(approached.left_contact_count > 0)
                last_right = float(approached.right_contact_count > 0)
                failure_history.append((approached.failure_code or FailureCode.INTERNAL_ERROR).value)
            else:
                verified = self.runtime.verify_pose(VerifyPoseInput(
                    expected_detection=observed.detection
                ))
                if not verified.success:
                    failure_history.append((verified.failure_code or FailureCode.INTERNAL_ERROR).value)
                else:
                    established = self.runtime.establish_grasp(EstablishGraspInput())
                    last_left, last_right = (
                        established.left_contact_rate, established.right_contact_rate
                    )
                    if not established.success:
                        failure_history.append(
                            (established.failure_code or FailureCode.INTERNAL_ERROR).value
                        )
                    else:
                        lifted = self.runtime.test_lift(TestLiftInput())
                        success = lifted.success
                        if not success:
                            failure_history.append(
                                (lifted.failure_code or FailureCode.INTERNAL_ERROR).value
                            )
            all_contact_trace.extend(self.backend.contact_debug_trace)
            if success:
                first_success = attempt == 1
                break
            self.runtime.retreat(RetreatInput(
                reason=failure_history[-1] if failure_history else "unknown"
            ))
            if decision.recovery == "abort":
                break
        return GraspEpisodeResult(
            planner=self.planner.name,
            seed=seed,
            first_attempt_success=first_success,
            final_success=success,
            attempts=attempts,
            abnormal_push=abnormal_push,
            failure_history=tuple(failure_history),
            decision_cost=dict(self.planner.decision_cost),
            skill_logs=tuple(self.runtime.logs),
            contact_trace=tuple(all_contact_trace),
        )
