"""CubeRelay v7 task-level embodied agent.

The agent chooses only validated high-level Skills. Physics, contact checks,
visual localization, sticker fusion and legality remain deterministic modules.
Simulator cube state is never an observation or planner input.
"""

from __future__ import annotations

import base64
import io
import json
import time
import urllib.request
from dataclasses import asdict
from enum import Enum
from typing import Any, Literal, Protocol

import numpy as np
from PIL import Image
from pydantic import BaseModel, ConfigDict, Field

from .failure_aware_v6 import FailureAwareRulePlanner, FailureAwareSkillAgent
from .perception_v2 import DeterministicCubeLocalizer, StickerStateFusion
from .v2_types import FaceObservation
from .vlm import HeuristicSceneVLM


class TaskPhase(str, Enum):
    STARTING = "STARTING"
    SEARCHING = "SEARCHING"
    GRASPING = "GRASPING"
    PLACING = "PLACING"
    OBSERVING = "OBSERVING"
    REGRASPING = "REGRASPING"
    REORIENTING = "REORIENTING"
    VALIDATING = "VALIDATING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"


class TaskSkill(str, Enum):
    OBSERVE_CUBE = "observe_cube"
    GRASP_CUBE = "grasp_cube_v6"
    ALIGN_SCAN_AXES = "align_scan_axes"
    PLACE_RELEASE = "place_release"
    OBSERVE_RELEASED = "observe_released"
    OBSERVE_HELD = "observe_held"
    REGRASP = "regrasp"
    REORIENT_PITCH = "reorient_pitch_90"
    REORIENT_YAW = "reorient_yaw_90"
    VALIDATE_STATE = "validate_state"
    COMPLETE = "complete"
    ABORT = "abort"


class TaskSkillCandidate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    skill: TaskSkill
    reason: str
    safety_checked: bool = True


class TaskPlannerDecision(BaseModel):
    model_config = ConfigDict(extra="forbid")
    skill: TaskSkill
    reason: str = Field(min_length=1, max_length=1000)


class TaskObservation(BaseModel):
    model_config = ConfigDict(extra="forbid")
    phase: TaskPhase
    step: int
    allowed_skills: tuple[TaskSkillCandidate, ...]
    cube_visible: bool | None = None
    pose_world_m: tuple[float, float, float] | None = None
    yaw_radians: float | None = None
    observed_faces: int = 0
    unknown_stickers: int = 54
    last_skill: TaskSkill | None = None
    last_success: bool | None = None
    last_failure_code: str | None = None
    action_history: tuple[str, ...] = ()


class TaskCallTrace(BaseModel):
    provider: str
    model: str
    latency_ms: float
    input_tokens: int | None = None
    output_tokens: int | None = None
    raw_response: str
    parsed_decision: TaskPlannerDecision | None
    error: str | None = None


class TaskPlanner(Protocol):
    name: str
    def decide(self, observation: TaskObservation, rgb: np.ndarray) -> TaskPlannerDecision: ...


class RuleTaskPlanner:
    """Offline deterministic control; never used as a real-VLM substitute."""

    name = "rule_task_planner"

    def decide(self, observation: TaskObservation, rgb: np.ndarray) -> TaskPlannerDecision:
        candidate = observation.allowed_skills[0]
        return TaskPlannerDecision(skill=candidate.skill, reason=candidate.reason)


class FixedTaskPlanner(RuleTaskPlanner):
    name = "fixed_task_planner"


class GeminiTaskPlanner:
    """OpenAI-compatible real-VLM task planner with a strict Skill allow-list."""

    name = "gemini_task_planner"

    def __init__(self, endpoint: str, model: str, api_key: str, timeout_seconds: float = 45) -> None:
        self.endpoint = endpoint.rstrip("/")
        self.model = model
        self.api_key = api_key
        self.timeout_seconds = timeout_seconds
        self.traces: list[TaskCallTrace] = []

    def decide(self, observation: TaskObservation, rgb: np.ndarray) -> TaskPlannerDecision:
        allowed = {item.skill for item in observation.allowed_skills if item.safety_checked}
        buffer = io.BytesIO()
        Image.fromarray(rgb).save(buffer, format="JPEG", quality=86)
        image = base64.b64encode(buffer.getvalue()).decode("ascii")
        prompt = (
            "You are CubeRelay's task-level embodied planner. From task start, choose exactly "
            "one allowed high-level Skill. You may plan active perception and recovery, but never "
            "output joint commands, poses, simulator state changes, sticker guesses, or safety "
            "overrides. Return JSON {skill, reason}. Context: "
            + json.dumps(observation.model_dump(mode="json"), separators=(",", ":"))
        )
        payload = {
            "model": self.model,
            "temperature": 0,
            "response_format": {"type": "json_object"},
            "messages": [{"role": "user", "content": [
                {"type": "text", "text": prompt},
                {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{image}"}},
            ]}],
        }
        request = urllib.request.Request(
            self.endpoint + "/chat/completions",
            data=json.dumps(payload).encode(),
            headers={"Content-Type": "application/json", "Authorization": f"Bearer {self.api_key}"},
        )
        started = time.perf_counter()
        raw = ""
        parsed = None
        error = None
        usage: dict[str, Any] = {}
        try:
            with urllib.request.urlopen(request, timeout=self.timeout_seconds) as response:
                result = json.loads(response.read())
            raw = str(result["choices"][0]["message"]["content"])
            data = json.loads(raw)
            aliases = {
                "observe": "observe_cube", "grasp": "grasp_cube_v6",
                "place": "place_release", "release": "place_release",
                "scan": "observe_released", "reorient": "reorient_pitch_90",
            }
            data["skill"] = aliases.get(data.get("skill"), data.get("skill"))
            parsed = TaskPlannerDecision.model_validate(data)
            if parsed.skill not in allowed:
                raise ValueError(f"VLM selected disallowed Skill: {parsed.skill.value}")
            usage = result.get("usage") or result.get("usageMetadata") or {}
        except Exception as exc:
            error = f"{type(exc).__name__}: {exc}"
            parsed = None
        trace = TaskCallTrace(
            provider="openai_compatible_real", model=self.model,
            latency_ms=(time.perf_counter() - started) * 1000,
            input_tokens=usage.get("prompt_tokens", usage.get("promptTokenCount")),
            output_tokens=usage.get("completion_tokens", usage.get("candidatesTokenCount")),
            raw_response=raw, parsed_decision=parsed, error=error,
        )
        self.traces.append(trace)
        if parsed is None:
            raise RuntimeError(error or "VLM decision was not parsed")
        return parsed


class TaskEvent(BaseModel):
    step: int
    phase: TaskPhase
    skill: TaskSkill
    success: bool
    detail: dict[str, Any] = Field(default_factory=dict)


class EmbodiedTaskResult(BaseModel):
    planner: str
    seed: int
    success: bool
    legal: bool
    reconstructed_facelets: str | None
    observed_faces: int
    unknown_stickers: int
    action_count: int
    regrasp_attempts: int
    regrasp_successes: int
    elapsed_seconds: float
    vlm_calls: int
    vlm_latency_ms: float
    input_tokens: int
    output_tokens: int
    failure_code: str | None
    events: tuple[TaskEvent, ...]
    pose_track: tuple[dict[str, Any], ...]
    sticker_evidence: tuple[dict[str, Any], ...]
    vlm_traces: tuple[TaskCallTrace, ...]


class EmbodiedTaskAgent:
    """Task-level v7 orchestration over v6 grasp and shared physical Skills."""

    def __init__(self, backend: Any, planner: TaskPlanner) -> None:
        self.backend = backend
        self.planner = planner
        self.localizer = DeterministicCubeLocalizer()
        self.scene_vlm = HeuristicSceneVLM()
        self.fusion = StickerStateFusion()
        self.events: list[TaskEvent] = []
        self.pose_track: list[dict[str, Any]] = []
        self.last_rgb = np.zeros((4, 4, 3), dtype=np.uint8)
        self.last_skill: TaskSkill | None = None
        self.last_success: bool | None = None
        self.last_failure: str | None = None
        self.regrasp_attempts = 0
        self.regrasp_successes = 0
        self.orientation_attempts = 0
        self.scan_aligned = False
        self.held_after_reorient = False

    def _allowed(self, phase: TaskPhase) -> tuple[TaskSkillCandidate, ...]:
        if phase in {TaskPhase.STARTING, TaskPhase.SEARCHING}:
            return (TaskSkillCandidate(skill=TaskSkill.OBSERVE_CUBE, reason="obtain current RGB-D observation"),)
        if phase == TaskPhase.GRASPING:
            return (
                TaskSkillCandidate(skill=TaskSkill.GRASP_CUBE, reason="run retained v6 contact-safe grasp subtask"),
                TaskSkillCandidate(skill=TaskSkill.OBSERVE_CUBE, reason="refresh pose before grasp"),
            )
        if phase == TaskPhase.PLACING:
            if not self.scan_aligned:
                return (TaskSkillCandidate(
                    skill=TaskSkill.ALIGN_SCAN_AXES,
                    reason="physically align cube faces to calibrated scan cameras",
                ),)
            return (TaskSkillCandidate(skill=TaskSkill.PLACE_RELEASE, reason="physical place and contact release"),)
        if phase == TaskPhase.OBSERVING:
            if self.held_after_reorient:
                return (TaskSkillCandidate(skill=TaskSkill.OBSERVE_HELD, reason="inspect reoriented held face before placement"),)
            return (TaskSkillCandidate(skill=TaskSkill.OBSERVE_RELEASED, reason="collect sticker pixels from released cube"),)
        if phase == TaskPhase.REGRASPING:
            return (
                TaskSkillCandidate(skill=TaskSkill.REGRASP, reason="camera-localized physical regrasp"),
                TaskSkillCandidate(skill=TaskSkill.OBSERVE_RELEASED, reason="obtain another released observation"),
            )
        if phase == TaskPhase.REORIENTING:
            # Four side cameras plus an oblique top camera cover five faces in
            # the first placement. One physical pitch then exposes the bottom;
            # no second grasp of a side-placed cube is required.
            skill = TaskSkill.REORIENT_PITCH if self.orientation_attempts < 2 else TaskSkill.REORIENT_YAW
            return (TaskSkillCandidate(skill=skill, reason="expose an unobserved physical face"),)
        if phase == TaskPhase.VALIDATING:
            return (TaskSkillCandidate(skill=TaskSkill.VALIDATE_STATE, reason="run independent 54-cell legality check"),)
        return (TaskSkillCandidate(skill=TaskSkill.ABORT, reason="no safe continuation"),)

    def _observation(self, phase: TaskPhase, step: int) -> TaskObservation:
        pose = self.pose_track[-1] if self.pose_track else None
        return TaskObservation(
            phase=phase, step=step, allowed_skills=self._allowed(phase),
            cube_visible=None if pose is None else True,
            pose_world_m=None if pose is None else tuple(pose["center_world_m"]),
            yaw_radians=None if pose is None else pose["yaw_radians"],
            observed_faces=self.fusion.observed_face_count,
            unknown_stickers=self.fusion.unknown_count,
            last_skill=self.last_skill, last_success=self.last_success,
            last_failure_code=self.last_failure,
            action_history=tuple(event.skill.value for event in self.events),
        )

    def _record(self, step: int, phase: TaskPhase, skill: TaskSkill,
                success: bool, detail: dict[str, Any]) -> None:
        self.events.append(TaskEvent(step=step, phase=phase, skill=skill,
                                     success=success, detail=detail))
        self.last_skill, self.last_success = skill, success
        self.last_failure = None if success else str(detail.get("failure_code", "SKILL_FAILED"))

    def run(self, seed: int, *, reset_scene: bool = True, scramble_steps: int = 15,
            max_steps: int = 24) -> EmbodiedTaskResult:
        started = time.perf_counter()
        if reset_scene:
            self.backend.reset_random(seed, scramble_steps)
        phase = TaskPhase.STARTING
        failure: str | None = None
        legal = False
        reconstructed: str | None = None
        frame_offset = 0
        for step in range(1, max_steps + 1):
            try:
                decision = self.planner.decide(self._observation(phase, step), self.last_rgb)
            except Exception as exc:
                failure = f"TASK_PLANNER_FAILED:{exc}"
                break
            skill = decision.skill
            detail: dict[str, Any] = {"planner_reason": decision.reason}
            success = False
            if skill == TaskSkill.OBSERVE_CUBE:
                frame = self.backend.capture_rgbd("overhead")
                self.last_rgb = frame.rgb
                semantics = self.scene_vlm.understand(frame.rgb)
                detection = self.localizer.locate(frame) if semantics.cube_visible else None
                success = detection is not None
                if detection:
                    pose = {"step": step, "center_world_m": list(detection.center_world_m),
                            "yaw_radians": detection.yaw_radians,
                            "source": detection.source}
                    self.pose_track.append(pose)
                    detail.update(pose)
                else:
                    detail["failure_code"] = "CUBE_NOT_LOCALIZED"
                phase = TaskPhase.GRASPING if success else TaskPhase.SEARCHING
            elif skill == TaskSkill.GRASP_CUBE:
                result = FailureAwareSkillAgent(
                    self.backend, self.scene_vlm, FailureAwareRulePlanner()
                ).run(seed, scramble_steps, reset_scene=False)
                success = result.final_success
                detail.update({"attempts": result.attempts,
                               "failure_history": list(result.failure_history)})
                if not success:
                    detail["failure_code"] = result.failure_history[-1] if result.failure_history else "GRASP_FAILED"
                phase = TaskPhase.PLACING if success else TaskPhase.SEARCHING
            elif skill == TaskSkill.PLACE_RELEASE:
                detail.update(self.backend.task_place_release())
                success = bool(detail["success"])
                phase = TaskPhase.OBSERVING if success else TaskPhase.FAILED
            elif skill == TaskSkill.ALIGN_SCAN_AXES:
                detail.update(self.backend.task_align_scan_axes())
                success = bool(detail["success"])
                self.scan_aligned = success
                phase = TaskPhase.PLACING if success else TaskPhase.REGRASPING
            elif skill == TaskSkill.OBSERVE_RELEASED:
                observations: list[FaceObservation] = self.backend.task_observe_released(frame_offset)
                frame_offset += 5
                for item in observations:
                    self.fusion.add(item)
                self.last_rgb = self.backend.capture_rgbd("overhead").rgb
                success = bool(observations)
                detail.update({"observations": len(observations),
                               "faces": self.fusion.observed_face_count,
                               "unknown": self.fusion.unknown_count})
                if not success:
                    detail["failure_code"] = "NO_FACE_OBSERVATION"
                if self.fusion.unknown_count == 0:
                    phase = TaskPhase.VALIDATING
                elif self.orientation_attempts < 3:
                    phase = TaskPhase.REGRASPING
                else:
                    failure = "INCOMPLETE_54_STICKER_SCAN"
                    self._record(step, TaskPhase.OBSERVING, skill, success, detail)
                    break
            elif skill == TaskSkill.OBSERVE_HELD:
                observations = self.backend.task_observe_held(frame_offset)
                frame_offset += 4
                for item in observations:
                    self.fusion.add(item)
                self.last_rgb = self.backend.capture_rgbd("overhead").rgb
                success = bool(observations)
                detail.update({"observations": len(observations),
                               "faces": self.fusion.observed_face_count,
                               "unknown": self.fusion.unknown_count})
                if not success:
                    detail["failure_code"] = "NO_HELD_FACE_OBSERVATION"
                self.held_after_reorient = False
                phase = TaskPhase.VALIDATING if self.fusion.unknown_count == 0 else TaskPhase.PLACING
            elif skill == TaskSkill.REGRASP:
                self.regrasp_attempts += 1
                if self.orientation_attempts == 0:
                    detail.update(self.backend.task_regrasp())
                    success = bool(detail["success"])
                else:
                    grasp_result = FailureAwareSkillAgent(
                        self.backend, self.scene_vlm, FailureAwareRulePlanner()
                    ).run(seed, scramble_steps, reset_scene=False)
                    success = grasp_result.final_success
                    detail.update({
                        "success": success,
                        "attempts": grasp_result.attempts,
                        "failure_history": list(grasp_result.failure_history),
                        "failure_code": None if success else (
                            grasp_result.failure_history[-1]
                            if grasp_result.failure_history else "REGRASP_FAILED"
                        ),
                    })
                self.regrasp_successes += int(success)
                if success:
                    # Refresh held orientation anchor from the four side cameras
                    # before pitching/yawing the wrist.
                    for item in self.backend.task_observe_held(frame_offset):
                        self.fusion.add(item)
                    frame_offset += 4
                phase = TaskPhase.REORIENTING if success else TaskPhase.OBSERVING
            elif skill in {TaskSkill.REORIENT_PITCH, TaskSkill.REORIENT_YAW}:
                axis = "pitch" if skill == TaskSkill.REORIENT_PITCH else "yaw"
                # Negative pitch presents the previously bottom face to the
                # unobstructed -Y scan camera; positive pitch puts it behind
                # the palm in this gripper geometry.
                radians = -np.pi / 2 if axis == "pitch" else np.pi / 2
                detail.update(self.backend.task_reorient(axis, radians))
                success = bool(detail["success"])
                self.orientation_attempts += 1
                self.scan_aligned = True
                self.held_after_reorient = success
                phase = TaskPhase.OBSERVING if success else TaskPhase.REGRASPING
            elif skill == TaskSkill.VALIDATE_STATE:
                try:
                    reconstructed = self.fusion.validated_facelets()
                    legal = success = True
                    phase = TaskPhase.COMPLETED
                except ValueError as exc:
                    detail.update({"failure_code": "STATE_INVALID", "error": str(exc)})
                    failure = "STATE_INVALID"
                    phase = TaskPhase.FAILED
            elif skill == TaskSkill.COMPLETE:
                success = legal
                phase = TaskPhase.COMPLETED if legal else TaskPhase.FAILED
            else:
                detail["failure_code"] = "PLANNER_ABORT"
                failure = "PLANNER_ABORT"
                phase = TaskPhase.FAILED
            self._record(step, phase, skill, success, detail)
            if phase in {TaskPhase.COMPLETED, TaskPhase.FAILED}:
                if not success and failure is None:
                    failure = self.last_failure
                break
        else:
            failure = "TASK_STEP_LIMIT"

        traces = tuple(getattr(self.planner, "traces", ()))
        return EmbodiedTaskResult(
            planner=self.planner.name, seed=seed, success=bool(legal and reconstructed),
            legal=legal, reconstructed_facelets=reconstructed,
            observed_faces=self.fusion.observed_face_count,
            unknown_stickers=self.fusion.unknown_count,
            action_count=len(self.events), regrasp_attempts=self.regrasp_attempts,
            regrasp_successes=self.regrasp_successes,
            elapsed_seconds=time.perf_counter() - started, vlm_calls=len(traces),
            vlm_latency_ms=sum(item.latency_ms for item in traces),
            input_tokens=sum(item.input_tokens or 0 for item in traces),
            output_tokens=sum(item.output_tokens or 0 for item in traces),
            failure_code=failure, events=tuple(self.events),
            pose_track=tuple(self.pose_track),
            sticker_evidence=tuple(asdict(item) for item in self.fusion.fused_evidence()),
            vlm_traces=traces,
        )
