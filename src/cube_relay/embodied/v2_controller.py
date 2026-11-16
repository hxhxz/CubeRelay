"""Embodied Simulation v2 state machine and closed-loop orchestration."""

from __future__ import annotations

import json
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Callable, Protocol

from cube_relay.cube import CubeEngine, CubeSolver

from .execution import ActionFeedback
from .perception_v2 import DeterministicCubeLocalizer, StickerStateFusion
from .v2_types import EmbodiedState, FaceObservation, RGBDFrame, StickerEvidence, V2Metrics
from .vlm import SceneVLM


class EmbodiedBackend(Protocol):
    implementation_level: str

    def reset_random(self, seed: int, scramble_steps: int) -> dict[str, object]: ...
    def capture_rgbd(self) -> RGBDFrame: ...
    def approach_grasp_lift(
        self, target_xyz: tuple[float, float, float], target_yaw: float | None = None
    ) -> bool: ...
    def active_scan(self) -> list[FaceObservation]: ...
    def execute_physical_turn(self, move: str) -> ActionFeedback: ...
    def hand_over(self) -> bool: ...
    def wait_for_human_move(self, move: str | None) -> str | None: ...
    def take_back(self) -> bool: ...
    def record_frame(self) -> None: ...


@dataclass(frozen=True, slots=True)
class V2Event:
    index: int
    state: str
    kind: str
    payload: dict[str, object]


@dataclass(frozen=True, slots=True)
class V2Result:
    solved: bool
    final_state: str | None
    terminal_state: EmbodiedState
    metrics: V2Metrics
    events: tuple[V2Event, ...]
    sticker_evidence: tuple[StickerEvidence, ...]


class EmbodiedV2Controller:
    """Runs perception -> grasp -> scan -> validate -> solve -> collaboration.

    The controller never asks the backend for the simulator's logical cube state.
    Its only state estimate is the output of ``active_scan``.
    """

    def __init__(
        self,
        backend: EmbodiedBackend,
        vlm: SceneVLM,
        *,
        localizer: DeterministicCubeLocalizer | None = None,
        solver: CubeSolver | None = None,
        engine: CubeEngine | None = None,
        max_recoveries: int = 3,
    ) -> None:
        self.backend = backend
        self.vlm = vlm
        self.localizer = localizer or DeterministicCubeLocalizer()
        self.solver = solver or CubeSolver()
        self.engine = engine or CubeEngine()
        self.max_recoveries = max_recoveries
        self.state = EmbodiedState.SEARCHING
        self.events: list[V2Event] = []
        self.metrics = V2Metrics(extra={"implementation_level": backend.implementation_level})

    def _transition(self, state: EmbodiedState, kind: str, **payload: object) -> None:
        self.state = state
        self.metrics.state_transitions += 1
        self.events.append(V2Event(len(self.events) + 1, state.value, kind, dict(payload)))
        self.backend.record_frame()

    def run(
        self,
        *,
        seed: int = 0,
        scramble_steps: int = 15,
        max_robot_turns: int | None = None,
        human_move_provider: Callable[[str], str | None] | None = None,
    ) -> V2Result:
        started = time.perf_counter()
        self.backend.reset_random(seed, scramble_steps)
        estimated: str | None = None
        recoveries = 0
        try:
            detection = None
            while detection is None and recoveries <= self.max_recoveries:
                self._transition(EmbodiedState.SEARCHING, "camera_search", attempt=recoveries + 1)
                self.metrics.search_attempts += 1
                frame = self.backend.capture_rgbd()
                semantics = self.vlm.understand(frame.rgb)
                detection = self.localizer.locate(frame) if semantics.cube_visible else None
                if detection is None:
                    recoveries += 1
                    self.metrics.recoveries += 1
                    self._transition(EmbodiedState.RECOVERING_SEARCH, "cube_not_localized")
            if detection is None:
                raise RuntimeError("cube could not be localized from RGB-D observations")

            self._transition(
                EmbodiedState.GRASPING, "pose_estimated",
                center_world_m=list(detection.center_world_m), confidence=detection.confidence,
                yaw_radians=detection.yaw_radians, yaw_confidence=detection.yaw_confidence,
                source=detection.source,
            )
            self.metrics.grasp_attempts += 1
            if not self.backend.approach_grasp_lift(
                detection.center_world_m, detection.yaw_radians
            ):
                self.metrics.recoveries += 1
                self._transition(EmbodiedState.RECOVERING_GRASP, "grasp_verification_failed")
                raise RuntimeError("physical grasp/lift verification failed")

            self._transition(EmbodiedState.ACTIVE_SCANNING, "grasp_lift_verified")
            observations = self.backend.active_scan()
            self.metrics.observations += len(observations)
            fusion = StickerStateFusion()
            for observation in observations:
                fusion.add(observation)
            action_trace = list(getattr(self.backend, "observation_action_trace", []))
            self.metrics.extra["observation_action_trace"] = action_trace
            self.metrics.regrasp_count += action_trace.count("REGRASP")
            self.metrics.extra["unknown_stickers_after_scan"] = fusion.unknown_count
            self._transition(
                EmbodiedState.STATE_VALIDATING, "six_face_scan_complete",
                face_observations=len(observations), observed_faces=fusion.observed_face_count,
            )
            try:
                estimated = fusion.validated_facelets()
            except ValueError:
                self.metrics.validation_failures += 1
                self._transition(EmbodiedState.RECOVERING_OBSERVATION, "state_validation_failed")
                observations = self.backend.active_scan()
                self.metrics.observations += len(observations)
                for observation in observations:
                    fusion.add(observation)
                self.metrics.extra["unknown_stickers_after_recovery"] = fusion.unknown_count
                estimated = fusion.validated_facelets()

            self._transition(EmbodiedState.SOLVING, "visual_state_valid", facelets=estimated)
            plan = self.solver.solve(estimated)
            limit = len(plan) if max_robot_turns is None else min(len(plan), max_robot_turns)
            for move in plan[:limit]:
                self._transition(EmbodiedState.ROBOT_MANIPULATING, "physical_turn_requested", move=move)
                self.metrics.physical_turn_attempts += 1
                feedback = self.backend.execute_physical_turn(move)
                if not feedback.success:
                    self.metrics.recoveries += 1
                    self.metrics.replans += 1
                    self._transition(
                        EmbodiedState.RECOVERING_MANIPULATION, "turn_failed",
                        move=move, detail=feedback.detail,
                    )
                    continue
                self.metrics.verified_turns += 1
                estimated = self.engine.apply_move(estimated, move)
                self._transition(EmbodiedState.REOBSERVING, "turn_joint_verified", move=move)

                if human_move_provider is not None:
                    self._transition(EmbodiedState.HANDING_OVER, "handover_requested")
                    if not self.backend.hand_over():
                        raise RuntimeError("human gripper did not confirm receipt")
                    self.metrics.handovers += 1
                    self._transition(EmbodiedState.HUMAN_MANIPULATING, "human_has_control")
                    human_move = self.backend.wait_for_human_move(human_move_provider(estimated))
                    if human_move:
                        estimated = self.engine.apply_move(estimated, human_move)
                    self._transition(EmbodiedState.TAKING_BACK, "human_released", move=human_move)
                    if not self.backend.take_back():
                        raise RuntimeError("robot failed to take cube back")
                    self.metrics.replans += 1
                    plan = self.solver.solve(estimated)

            solved = self.engine.is_solved(estimated)
            terminal = EmbodiedState.COMPLETED if solved else EmbodiedState.REOBSERVING
            self._transition(terminal, "episode_finished", solved=solved)
        except Exception as exc:
            self._transition(EmbodiedState.ERROR, "episode_error", error=str(exc))
            solved = False
        self.metrics.elapsed_seconds = time.perf_counter() - started
        evidence = fusion.fused_evidence() if "fusion" in locals() else ()
        return V2Result(solved, estimated, self.state, self.metrics, tuple(self.events), evidence)


def write_v2_artifacts(result: V2Result, output_dir: str | Path) -> None:
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    (output / "trajectory.jsonl").write_text(
        "".join(json.dumps(asdict(event), sort_keys=True) + "\n" for event in result.events),
        encoding="utf-8",
    )
    summary = {
        "solved": result.solved,
        "final_state": result.final_state,
        "terminal_state": result.terminal_state.value,
        "metrics": asdict(result.metrics),
    }
    (output / "metrics.json").write_text(json.dumps(summary, indent=2, sort_keys=True), encoding="utf-8")
    (output / "sticker_evidence.jsonl").write_text(
        "".join(json.dumps(asdict(item), sort_keys=True) + "\n" for item in result.sticker_evidence),
        encoding="utf-8",
    )
