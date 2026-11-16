"""Continuous active inspection over contact-safe physical Skills.

Ground truth is deliberately absent. Evaluation code may score emitted visual
evidence afterwards, but this controller can only see camera-derived state.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
import time
from typing import Any, Callable, Literal

import numpy as np

from .failure_aware_v6 import FailureAwareRulePlanner, FailureAwareSkillAgent
from .perception_v2 import StickerStateFusion
from .vlm import HeuristicSceneVLM


@dataclass(frozen=True, slots=True)
class InspectionEvent:
    step: int
    skill: str
    success: bool
    correct_observed: int
    incorrect_observed: int
    unknown: int
    conflicts: int
    detail: dict[str, Any]
    event_type: str = "action"
    start_sim_time: float = 0.0
    end_sim_time: float = 0.0
    duration: float = 0.0


@dataclass(frozen=True, slots=True)
class InspectionResult:
    success: bool
    legal: bool
    reconstructed_facelets: str | None
    first_failure_stage: str | None
    action_count: int
    regrasp_skill_success: bool
    regrasp_first_candidate_successes: int
    regrasp_final_successes: int
    events: tuple[InspectionEvent, ...]
    evidence: tuple[dict[str, Any], ...]


class NextBestViewPlanner:
    """Choose only a validated pitch/yaw Skill from current visual coverage."""

    def choose(self, fusion: StickerStateFusion, history: tuple[str, ...]) -> str:
        unknown_by_face = {
            face: sum(item.face == face and item.color is None
                      for item in fusion.fused_evidence())
            for face in "URFDLB"
        }
        pitch_score = unknown_by_face["U"] + unknown_by_face["D"]
        yaw_score = sum(unknown_by_face[face] for face in "FRBL") / 2
        if pitch_score == yaw_score and history:
            return "yaw" if history[-1] == "pitch" else "pitch"
        return "pitch" if pitch_score >= yaw_score else "yaw"


class ContinuousActiveInspector:
    def __init__(
        self,
        backend: Any,
        mode: Literal["sequential", "nbv"] = "nbv",
        *,
        event_sink: Callable[[dict[str, Any]], None] | None = None,
    ) -> None:
        self.backend = backend
        self.mode = mode
        self.fusion = StickerStateFusion()
        self.events: list[InspectionEvent] = []
        self.nbv = NextBestViewPlanner()
        self.event_sink = event_sink
        self._observation_sequence = 0

    def _sim_time(self) -> float:
        return float(getattr(getattr(self.backend, "data", None), "time", 0.0))

    def _publish(self, payload: dict[str, Any]) -> None:
        if self.event_sink is not None:
            self.event_sink(payload)

    def _decision(self, name: str, evidence: dict[str, Any]) -> None:
        now = self._sim_time()
        self._publish({
            "event_type": "decision",
            "name": name,
            "source": "deterministic_policy",
            "status": "COMPLETED",
            "start_sim_time": now,
            "end_sim_time": now,
            "duration": 0.0,
            "evidence": evidence,
        })

    @staticmethod
    def _action_evidence(skill: str, detail: dict[str, Any]) -> dict[str, Any]:
        target: dict[str, Any] = {}
        measured: dict[str, Any] = {}
        if skill.startswith("reorient_"):
            axis = "pitch" if "pitch" in skill else "yaw"
            target = {
                "axis": axis,
                "radians": detail.get("reorient_target_radians"),
                "degrees": (
                    float(np.degrees(detail["reorient_target_radians"]))
                    if detail.get("reorient_target_radians") is not None else None
                ),
            }
            measured = {
                "radians": detail.get("reorient_actual_radians"),
                "degrees": (
                    float(np.degrees(detail["reorient_actual_radians"]))
                    if detail.get("reorient_actual_radians") is not None else None
                ),
                "error_radians": detail.get("reorient_error_radians"),
            }
        elif "grasp" in skill:
            raw_attempts = detail.get("attempts", [])
            attempts = list(raw_attempts) if isinstance(raw_attempts, (list, tuple)) else []
            attempt_count = int(raw_attempts) if isinstance(raw_attempts, (int, np.integer)) else len(attempts)
            measured = {
                "attempt_count": attempt_count,
                "final_attempt": attempts[-1] if attempts else None,
                "grasp_confirmed": bool(detail.get("success", detail.get("final_success", False))),
            }
        elif "place" in skill or "release" in skill:
            measured = {
                "released": detail.get("released"),
                "height_before_m": detail.get("height_before_m"),
                "height_after_m": detail.get("height_after_m"),
                "contact": detail.get("diagnostics"),
            }
        return {
            "action_name": skill,
            "target_parameters": target,
            "measured_parameters": measured,
            "raw_result": detail,
        }

    def _record(
        self,
        skill: str,
        success: bool,
        detail: dict[str, Any],
        *,
        start_sim_time: float | None = None,
        started_wall: float | None = None,
    ) -> None:
        end_sim_time = self._sim_time()
        start_sim_time = end_sim_time if start_sim_time is None else start_sim_time
        event = InspectionEvent(
            len(self.events) + 1, skill, success, 0, 0,
            self.fusion.unknown_count, self.fusion.conflict_count, detail,
            "action", start_sim_time, end_sim_time,
            max(0.0, end_sim_time - start_sim_time),
        )
        self.events.append(event)
        evidence = self._action_evidence(skill, detail)
        evidence.update({
            "success": success,
            "failure_reason": detail.get("failure_code") if isinstance(detail, dict) else None,
            "wall_duration": None if started_wall is None else time.perf_counter() - started_wall,
        })
        self._publish({
            "event_type": "action",
            "name": skill,
            "source": "physical_skill",
            "status": "COMPLETED" if success else "FAILED",
            "start_sim_time": start_sim_time,
            "end_sim_time": end_sim_time,
            "duration": event.duration,
            "evidence": evidence,
            "failure_reason": evidence["failure_reason"],
        })

    def _observe(
        self,
        skill: str,
        observations: list[Any],
        *,
        start_sim_time: float | None = None,
        started_wall: float | None = None,
    ) -> None:
        before_items = self.fusion.fused_evidence()
        before = {(item.face, item.index): item.color for item in before_items}
        unknown_before = self.fusion.unknown_count
        known = {key for key, color in before.items() if color is not None}
        camera_contributions: dict[str, list[int]] = {}
        face_order = "URFDLB"
        for observation in observations:
            source_parts = str(observation.source_view).split(":")
            camera = source_parts[1] if len(source_parts) > 1 else source_parts[0]
            contribution = camera_contributions.setdefault(camera, [])
            for index, color in enumerate(observation.stickers):
                key = (observation.face, index)
                if color is not None and key not in known:
                    canonical_index = face_order.index(observation.face) * 9 + index
                    contribution.append(canonical_index)
                    known.add(key)
        for observation in observations:
            self.fusion.add(observation)
        after_items = self.fusion.fused_evidence()
        newly_observed_indices = sorted(
            face_order.index(item.face) * 9 + item.index
            for item in after_items
            if before[(item.face, item.index)] is None and item.color is not None
        )
        newly_observed = len(newly_observed_indices)
        visual_evidence = [
            {"face": observation.face, "index": index, "color": color,
             "confidence": (
                 observation.sticker_confidences[index]
                 if observation.sticker_confidences is not None else observation.confidence
             ), "source_view": observation.source_view}
            for observation in observations
            for index, color in enumerate(observation.stickers)
        ]
        end_sim_time = self._sim_time()
        start_sim_time = end_sim_time if start_sim_time is None else start_sim_time
        self._observation_sequence += 1
        observation_id = f"scan-obs-{self._observation_sequence:03d}"
        camera_ids = list(camera_contributions)
        frame_refs = [f"frame:{observation_id}:{camera}" for camera in camera_ids]
        detail = {"observation_count": len(observations), "newly_observed": newly_observed,
             "newly_observed_facelet_indices": newly_observed_indices,
             "camera_ids": camera_ids,
             "camera_contributions": camera_contributions,
             "coverage_before": 54 - unknown_before,
             "coverage_after": 54 - self.fusion.unknown_count,
             "unknown_before": unknown_before,
             "unknown_after": self.fusion.unknown_count,
             "frame_refs": frame_refs,
             "observation_id": observation_id,
             "conflicting_indices": list(self.fusion.conflicting_indices),
             "observation_diagnostics": list(getattr(
                 self.backend, "last_observation_diagnostics", []
             )),
             "visual_evidence": visual_evidence}
        event = InspectionEvent(
            len(self.events) + 1, skill, bool(observations), 0, 0,
            self.fusion.unknown_count, self.fusion.conflict_count,
            detail, "perception", start_sim_time, end_sim_time,
            max(0.0, end_sim_time - start_sim_time),
        )
        self.events.append(event)
        self._publish({
            "event_type": "perception",
            "name": skill,
            "source": "camera_perception",
            "status": "COMPLETED" if observations else "FAILED",
            "start_sim_time": start_sim_time,
            "end_sim_time": end_sim_time,
            "duration": event.duration,
            "evidence": {
                **detail,
                "conflicts": self.fusion.conflict_count,
                "visual_summary": (
                    f"{len(camera_ids)} cameras added {newly_observed} unique canonical "
                    f"facelets; unknown {unknown_before} -> {self.fusion.unknown_count}"
                ),
                "wall_duration": None if started_wall is None else time.perf_counter() - started_wall,
            },
            "failure_reason": None if observations else "NO_VALID_OBSERVATIONS",
        })

    def run(self, seed: int, *, reset_scene: bool = True, max_cycles: int = 6) -> InspectionResult:
        if reset_scene:
            self.backend.reset_random(seed, 15)
        first_failure: str | None = None
        regrasp_first = regrasp_final = 0
        started_sim, started_wall = self._sim_time(), time.perf_counter()
        grasp = FailureAwareSkillAgent(
            self.backend, HeuristicSceneVLM(), FailureAwareRulePlanner()
        ).run(seed, 15, reset_scene=False)
        self._record(
            "initial_grasp", grasp.final_success,
            {"attempts": grasp.attempts, "final_success": grasp.final_success},
            start_sim_time=started_sim, started_wall=started_wall,
        )
        if not grasp.final_success:
            first_failure = "initial_grasp"
        if first_failure is None:
            started_sim, started_wall = self._sim_time(), time.perf_counter()
            aligned = self.backend.task_align_scan_axes()
            self._record(
                "align_scan_axes", bool(aligned["success"]), aligned,
                start_sim_time=started_sim, started_wall=started_wall,
            )
            if not aligned["success"]:
                first_failure = "align_scan_axes"

        orientation_history: list[str] = []
        u_occlusion_recovery_used = False
        u_external_supplement_used = False
        frame_offset = 0
        if first_failure is None:
            started_sim, started_wall = self._sim_time(), time.perf_counter()
            placed = self.backend.task_place_release()
            self._record(
                "place_release_refresh", bool(placed["success"]), placed,
                start_sim_time=started_sim, started_wall=started_wall,
            )
            if not placed["success"]:
                first_failure = str(placed.get("failure_code") or "place_release")
        if first_failure is None:
            started_sim, started_wall = self._sim_time(), time.perf_counter()
            observations = self.backend.task_observe_released(frame_offset)
            frame_offset += 5
            self._observe(
                "observe_released", observations,
                start_sim_time=started_sim, started_wall=started_wall,
            )
        if first_failure is None and not (
            self.fusion.unknown_count == 0 and self.fusion.conflict_count == 0
        ):
            self._decision("regrasp_required", {
                "remaining_unknown_facelets": self.fusion.unknown_count,
                "visible_faces": sorted({item.face for item in self.fusion.fused_evidence() if item.color is not None}),
                "selected_action": "refresh_plan_regrasp",
                "reason": "released multi-camera observation is incomplete; grasp is required to change object pose",
            })
            started_sim, started_wall = self._sim_time(), time.perf_counter()
            regrasp = self.backend.task_regrasp()
            attempts = regrasp.get("attempts", [])
            regrasp_first += int(bool(attempts and attempts[0].get("success")))
            regrasp_final += int(bool(regrasp["success"]))
            self._record(
                "refresh_plan_regrasp", bool(regrasp["success"]), regrasp,
                start_sim_time=started_sim, started_wall=started_wall,
            )
            if not regrasp["success"]:
                first_failure = str(regrasp.get("failure_code") or "regrasp")
            else:
                # Re-validate orientation from the held side cameras before any
                # wrist pitch/yaw rotation so that any Z-rotation introduced by
                # regrasp + align_scan_axes is resolved from centre colours.
                started_sim, started_wall = self._sim_time(), time.perf_counter()
                held_initial = self.backend.task_observe_held(frame_offset)
                frame_offset += 5
                self._observe(
                    "observe_held_after_regrasp", held_initial,
                    start_sim_time=started_sim, started_wall=started_wall,
                )

        # Once a stable regrasp exists, continuous held inspection avoids the
        # known side-place instability. Every rotation still performs a fresh
        # multi-camera 6-D refresh before the next action.
        for cycle in range(max_cycles):
            if first_failure is not None or (
                self.fusion.unknown_count == 0 and self.fusion.conflict_count == 0
            ):
                break
            if self.mode == "sequential":
                sequence = ("pitch", "yaw", "pitch", "yaw", "pitch", "yaw")
                axis = sequence[cycle]
            else:
                axis = self.nbv.choose(self.fusion, tuple(orientation_history))
            orientation_history.append(axis)
            radians = -np.pi / 2 if axis == "pitch" else np.pi / 2
            self._decision("object_reorientation_selected", {
                "remaining_unknown_facelets": self.fusion.unknown_count,
                "visible_faces": sorted({item.face for item in self.fusion.fused_evidence() if item.color is not None}),
                "mode": self.mode,
                "cycle": cycle,
                "selected_action": f"reorient_{axis}",
                "target_axis": axis,
                "target_radians": radians,
                "reason": "current held views add no missing canonical facelets; expose a hidden face",
            })
            started_sim, started_wall = self._sim_time(), time.perf_counter()
            reoriented = self.backend.task_reorient(axis, radians)
            self._record(
                f"reorient_{axis}_refresh", bool(reoriented["success"]), reoriented,
                start_sim_time=started_sim, started_wall=started_wall,
            )
            # A second -90 degree pitch from an already -90 degree grasp is
            # outside the physical wrist range.  The equivalent cube rotation
            # is +180 degrees, so execute it as two monitored +90 degree
            # segments from -90 to 0 to +90.  This stays inside the joint
            # limits and preserves the same final rigid-body orientation
            # (-180 == +180) without release, teleportation, or a retry loop.
            if (
                not reoriented["success"]
                and reoriented.get("failure_code") == "REORIENT_JOINT_LIMIT"
                and axis == "pitch"
                and radians < 0
            ):
                for segment in (1, 2):
                    reoriented = self.backend.task_reorient(
                        "pitch", np.pi / 2, recenter=(segment == 2)
                    )
                    self._record(
                        f"reorient_pitch_alternate_segment_{segment}",
                        bool(reoriented["success"]), reoriented,
                    )
                    if not reoriented["success"]:
                        break
            if not reoriented["success"]:
                first_failure = str(reoriented.get("failure_code") or "reorient")
                break
            started_sim, started_wall = self._sim_time(), time.perf_counter()
            held = self.backend.task_observe_held(frame_offset)
            frame_offset += 5
            self._observe(
                "observe_held", held,
                start_sim_time=started_sim, started_wall=started_wall,
            )

            u_known = sum(
                item.color is not None for item in self.fusion.fused_evidence()
                if item.face == "U"
            )
            if 0 < u_known < 9 and not u_external_supplement_used:
                u_external_supplement_used = True
                supplemental = self.backend.task_observe_held(
                    frame_offset, use_fixed_external=True
                )
                frame_offset += 3
                self._observe(
                    "observe_held_u_external_supplement",
                    [item for item in supplemental if item.face == "U"],
                )
                if self.fusion.unknown_count == 0 and self.fusion.conflict_count == 0:
                    break
                upright_for_u = self.backend.task_reorient(
                    "pitch", np.pi / 4, recenter=False
                )
                self._record(
                    "u_partial_return_upright",
                    bool(upright_for_u["success"]), upright_for_u,
                )
                if not upright_for_u["success"]:
                    first_failure = str(
                        upright_for_u.get("failure_code")
                        or "U_PARTIAL_RETURN_UPRIGHT_FAILED"
                    )
                    break
                placed_for_u = self.backend.task_place_release()
                self._record(
                    "u_partial_place_release",
                    bool(placed_for_u["success"]), placed_for_u,
                )
                if not placed_for_u["success"]:
                    first_failure = str(
                        placed_for_u.get("failure_code")
                        or "U_PARTIAL_PLACE_RELEASE_FAILED"
                    )
                    break
                released_u = self.backend.task_observe_released(frame_offset)
                frame_offset += 5
                self._observe(
                    "observe_released_u_final",
                    [item for item in released_u if item.face == "U"],
                )
                if self.fusion.unknown_count == 0 and self.fusion.conflict_count == 0:
                    break
                first_failure = "U_RELEASED_OBSERVATION_INCOMPLETE"
                break

            # If U is geometrically front-facing but the held image is mostly
            # gripper/non-sticker pixels, do one physical alternate-face
            # regrasp.  Never repeat this recovery and never synthesize an
            # observation from pose or simulator state.
            u_unknown = all(
                item.color is None for item in self.fusion.fused_evidence()
                if item.face == "U"
            )
            u_views = [
                item.get("u_face_visibility", {})
                for item in getattr(self.backend, "last_observation_diagnostics", [])
            ]
            u_occluded = any(
                item.get("available")
                and float(item.get("normal_to_camera_angle_degrees", 180)) < 25
                and bool(item.get("fully_in_frame"))
                and float(item.get("estimated_noncolored_or_occluded_fraction", 0)) > .70
                for item in u_views
            )
            if u_unknown and u_occluded and not u_occlusion_recovery_used:
                u_occlusion_recovery_used = True
                previous_pair = getattr(
                    getattr(self.backend, "last_selected_grasp_candidate", None),
                    "face_pair", None,
                )
                current_pitch = float(reoriented.get("reorient_actual_radians", 0.0))
                unwind_delta = -np.pi / 2 if current_pitch > 0 else np.pi / 2
                unwind = self.backend.task_reorient(
                    "pitch", unwind_delta, recenter=False
                )
                self._record("u_occlusion_unwind", bool(unwind["success"]), unwind)
                if not unwind["success"]:
                    first_failure = str(
                        unwind.get("failure_code") or "U_OCCLUSION_UNWIND_FAILED"
                    )
                    break
                placed = self.backend.task_place_release()
                self._record("u_occlusion_place_release", bool(placed["success"]), placed)
                if not placed["success"]:
                    first_failure = str(
                        placed.get("failure_code") or "U_OCCLUSION_PLACE_FAILED"
                    )
                    break
                released_views = self.backend.task_observe_released(frame_offset)
                frame_offset += 5
                self._observe("observe_released_u_recovery", released_views)
                if self.fusion.unknown_count == 0 and self.fusion.conflict_count == 0:
                    break
                excluded = {previous_pair} if previous_pair else set()
                regrasp = self.backend.task_regrasp(exclude_face_pairs=excluded)
                self._record("u_occlusion_alternate_regrasp", bool(regrasp["success"]), regrasp)
                if not regrasp["success"]:
                    first_failure = str(
                        regrasp.get("failure_code") or "U_OCCLUSION_REGRASP_FAILED"
                    )
                    break
                expose_u = self.backend.task_reorient(
                    "pitch", -np.pi / 4, recenter=False
                )
                self._record("u_occlusion_expose_u", bool(expose_u["success"]), expose_u)
                if not expose_u["success"]:
                    first_failure = str(
                        expose_u.get("failure_code") or "U_OCCLUSION_EXPOSE_FAILED"
                    )
                    break
                recovered = self.backend.task_observe_held(
                    frame_offset, use_fixed_external=True
                )
                frame_offset += 3
                self._observe(
                    "observe_held_u_recovery",
                    [observation for observation in recovered if observation.face == "U"],
                )
                if self.fusion.unknown_count == 0 and self.fusion.conflict_count == 0:
                    break

        reconstructed = self.fusion.facelets()
        legal = False
        if reconstructed is not None:
            try:
                self.fusion.validated_facelets()
                legal = True
            except ValueError:
                pass
        if first_failure is None and not (
            legal and reconstructed and self.fusion.conflict_count == 0
        ):
            first_failure = "SCAN_INCOMPLETE_AFTER_MAX_CYCLES"
        self._decision("scan_termination_check", {
            "remaining_unknown_facelets": self.fusion.unknown_count,
            "conflicts": self.fusion.conflict_count,
            "legal": legal,
            "termination_allowed": bool(legal and reconstructed and self.fusion.conflict_count == 0),
            "reason": (
                "all 54 canonical facelets observed with no conflicts and legal state"
                if legal and reconstructed and self.fusion.conflict_count == 0
                else first_failure or "scan incomplete"
            ),
        })
        now = self._sim_time()
        self._publish({
            "event_type": "verification",
            "name": "six_face_scan_verification",
            "source": "deterministic_validator",
            "status": "COMPLETED" if legal and reconstructed and self.fusion.conflict_count == 0 else "FAILED",
            "start_sim_time": now,
            "end_sim_time": now,
            "duration": 0.0,
            "evidence": {
                "coverage": 54 - self.fusion.unknown_count,
                "unknown": self.fusion.unknown_count,
                "conflicts": self.fusion.conflict_count,
                "legal": legal,
            },
            "failure_reason": first_failure,
        })
        evidence = tuple(asdict(item) for item in self.fusion.fused_evidence())
        return InspectionResult(
            bool(legal and reconstructed and self.fusion.conflict_count == 0), legal,
            reconstructed, first_failure, len(self.events), bool(regrasp_final),
            regrasp_first, regrasp_final, tuple(self.events), evidence,
        )
