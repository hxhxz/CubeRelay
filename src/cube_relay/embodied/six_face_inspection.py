"""CubeRelay v8: complete six-face active perception over physical Skills.

Pipeline (no simulator pose, no logical cube state, no ground truth):

1. ``initial_grasp`` (v6 failure-aware agent) -> ``align_scan_axes`` ->
   ``place_release`` puts the cube on the table with its faces aligned to the
   calibrated scan axes.
2. ``observe_released``: an offset eye-in-gantry camera views the top face
   without gripper occlusion and four orthogonal cameras view the sides.
3. ``regrasp`` -> ``observe_held`` -> repeated ``reorient`` + ``observe_held``
   chosen by an expected-information-gain rule until every canonical sticker
   is observed. Held views expose the former support face.
4. ``validate_state``: 54 fused stickers pass the independent legality check.

Orientation is never taken from a hard-coded anchor. On a real cube the six
centre stickers never move, so the centre colour of each detected face is its
identity. Two non-parallel identified faces determine the cube-to-world
rotation uniquely among the 24 cube rotations. Whole-cube actions propagate
that rotation as a prior, and every new observation re-estimates it. The
in-face 3x3 assignment is then the dihedral (D4) element whose projected
canonical sticker centres best match the observed grid, after removing
translation and scale so that a few centimetres of localisation error cannot
flip the decision.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any

import numpy as np

from .canonical_facelets import (
    FACE_FRAMES,
    _observed_grid_centers,
    axis_rotation,
    canonical_local_centers,
    cube_rotations_24,
    project_points,
    projected_face_corners,
    remap_observation_values,
)
from .facelet_mapping import PerspectiveFaceletMapper, canonical_index
from .perception_v2 import DeterministicCubeLocalizer, StickerStateFusion
from .v2_types import FaceObservation, RGBDFrame

FACES = "URFDLB"
_ROTATIONS = cube_rotations_24()


def face_normal_world(face: str, rotation: np.ndarray) -> np.ndarray:
    return np.asarray(rotation, dtype=float) @ np.asarray(FACE_FRAMES[face].normal, dtype=float)


def camera_outward_direction(frame: RGBDFrame) -> np.ndarray:
    """World direction from the observed face toward the camera (= -optical axis)."""
    return -np.asarray(frame.calibration.camera_to_world[:3, 2], dtype=float)


# ---------------------------------------------------------------------------
# Orientation from centre colours
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class OrientationEstimate:
    rotation: tuple[tuple[float, float, float], ...] | None
    unique: bool
    consistent_constraints: int
    total_constraints: int
    constrained_axes: int
    source: str
    outliers: tuple[str, ...] = ()
    prior_agrees: bool | None = None

    @property
    def matrix(self) -> np.ndarray | None:
        return None if self.rotation is None else np.asarray(self.rotation, dtype=float)


def _distinct_axes(normals: list[np.ndarray]) -> int:
    axes: list[np.ndarray] = []
    for normal in normals:
        if all(abs(float(np.dot(normal, axis))) < .5 for axis in axes):
            axes.append(normal)
    return len(axes)


def estimate_orientation_from_centers(
    constraints: list[tuple[str, np.ndarray, str]],
    prior: np.ndarray | None = None,
    *,
    min_cosine: float = .70,
) -> OrientationEstimate:
    """Choose the cube rotation consistent with centre-colour face identities.

    ``constraints`` holds (face label from the centre colour, outward world
    direction of the observed face, view name).
    """
    if not constraints:
        if prior is None:
            return OrientationEstimate(None, False, 0, 0, 0, "no_constraints")
        return OrientationEstimate(
            tuple(map(tuple, np.asarray(prior).tolist())), False, 0, 0, 0,
            "action_prediction_only",
        )
    ranked: list[tuple[int, float, float, int]] = []
    for index, rotation in enumerate(_ROTATIONS):
        cosines = [float(np.dot(face_normal_world(face, rotation), direction))
                   for face, direction, _ in constraints]
        consistent = sum(value >= min_cosine for value in cosines)
        prior_distance = (
            float(np.linalg.norm(rotation - prior)) if prior is not None else 0.0
        )
        ranked.append((consistent, float(np.sum(cosines)), -prior_distance, index))
    ranked.sort(reverse=True)
    best = ranked[0]
    rotation = _ROTATIONS[best[3]]
    consistent_normals = []
    outliers = []
    for face, direction, view in constraints:
        if float(np.dot(face_normal_world(face, rotation), direction)) >= min_cosine:
            consistent_normals.append(np.asarray(direction, dtype=float))
        else:
            outliers.append(f"{view}:{face}")
    axes = _distinct_axes(consistent_normals)
    # Unique when two non-parallel faces are identified and no other rotation
    # explains the same number of constraints.
    tied = [item for item in ranked[1:] if item[0] == best[0]]
    unique = axes >= 2 and not tied
    prior_agrees = None
    source = "center_colors"
    if prior is not None:
        prior_agrees = bool(np.linalg.norm(rotation - prior) < 1e-6)
        if not unique:
            # Try pure Z-rotation (quarter turns around world +Z) of prior:
            # happens when regrasp + align_scan_axes rotates an upright cube.
            z_axis = np.array([0.0, 0.0, 1.0])
            z_candidates = [axis_rotation(z_axis, k * np.pi / 2) @ prior for k in range(4)]
            matching_z = [
                cand for cand in z_candidates
                if all(
                    float(np.dot(face_normal_world(face, cand), direction)) >= min_cosine
                    for face, direction, _ in constraints
                )
            ]
            if len(matching_z) == 1:
                rotation = np.round(matching_z[0])
                source = "action_prediction_validated_by_centers"
                unique = True
                outliers = []
                prior_agrees = bool(np.linalg.norm(rotation - prior) < 1e-6)
    return OrientationEstimate(
        tuple(map(tuple, np.asarray(rotation).tolist())), unique, best[0],
        len(constraints), axes, source, tuple(outliers), prior_agrees,
    )


# ---------------------------------------------------------------------------
# Translation/scale-invariant D4 facelet assignment
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class D4Decision:
    observed_to_canonical: tuple[int, ...]
    quarter_turns: int
    mirrored: bool
    error: float
    margin: float
    reliable: bool
    reason: str | None


def _normalize(points: np.ndarray) -> np.ndarray:
    centred = points - points.mean(axis=0)
    scale = float(np.sqrt(np.mean(np.sum(centred * centred, axis=1))))
    return centred / max(scale, 1e-9)


def solve_d4_assignment(
    face: str, corners_xy: np.ndarray, center_world_m: np.ndarray,
    rotation: np.ndarray, calibration: Any, *,
    max_error: float = .35, min_margin: float = .45,
) -> D4Decision:
    projected = _normalize(project_points(
        canonical_local_centers(face), np.asarray(center_world_m, dtype=float),
        np.asarray(rotation, dtype=float), calibration,
    ))
    observed = _normalize(_observed_grid_centers(np.asarray(corners_xy, dtype=float)))
    candidates = []
    for mirrored in (False, True):
        for quarter_turns in range(4):
            assignment = tuple(canonical_index(r, c, quarter_turns, mirrored)
                               for r in range(3) for c in range(3))
            residual = observed - projected[np.asarray(assignment)]
            error = float(np.sqrt(np.mean(np.sum(residual * residual, axis=1))))
            candidates.append((error, quarter_turns, mirrored, assignment))
    candidates.sort(key=lambda item: item[0])
    best, second = candidates[0], candidates[1]
    margin = second[0] - best[0]
    reason = None
    if best[0] > max_error:
        reason = "d4_projection_error"
    elif margin < min_margin:
        reason = "d4_ambiguous"
    return D4Decision(best[3], best[1], best[2], best[0], margin, reason is None, reason)


# ---------------------------------------------------------------------------
# Per-view detection and mapping
# ---------------------------------------------------------------------------


@dataclass(slots=True)
class ViewDetection:
    view: str
    frame: RGBDFrame
    label: str | None
    corners_xy: np.ndarray | None
    raw_colors: tuple[str | None, ...] | None
    raw_confidences: tuple[float, ...] | None
    center_world_m: np.ndarray | None
    outward: np.ndarray


@dataclass(frozen=True, slots=True)
class ViewResult:
    view: str
    label: str | None
    predicted_face: str | None
    emitted: bool
    reason: str | None
    corner_source: str | None
    d4_error: float | None
    d4_margin: float | None
    quarter_turns: int | None
    mirrored: bool | None
    known_stickers: int
    observation: FaceObservation | None = field(default=None, compare=False)

    def summary(self) -> dict[str, Any]:
        data = {key: getattr(self, key) for key in (
            "view", "label", "predicted_face", "emitted", "reason", "corner_source",
            "d4_error", "d4_margin", "quarter_turns", "mirrored", "known_stickers",
        )}
        if self.observation is not None:
            data["stickers"] = list(self.observation.stickers)
        return data


class SixFacePerception:
    """Camera-only face identity, cube orientation and canonical facelets."""

    def __init__(self) -> None:
        self.mapper = PerspectiveFaceletMapper()
        self.localizer = DeterministicCubeLocalizer()

    def detect(self, frame: RGBDFrame, view: str) -> ViewDetection:
        mapped = self.mapper.map_face(frame.rgb, frame_index=0, source_view=view)
        detection = self.localizer.locate(frame) if frame.depth_m is not None else None
        center = np.asarray(detection.center_world_m) if detection is not None else None
        if mapped is None:
            return ViewDetection(view, frame, None, None, None, None, center,
                                 camera_outward_direction(frame))
        corners = np.asarray(mapped.corners_xy, dtype=float)
        if (
            not self._corners_in_frame(corners, frame.rgb.shape, margin=4.0)
            or not self._quad_aspect_ok(corners)
        ):
            return ViewDetection(view, frame, None, None, None, None, center,
                                 camera_outward_direction(frame))
        observation = mapped.observation
        label = observation.stickers[4]
        return ViewDetection(
            view, frame, label, corners,
            observation.stickers, observation.sticker_confidences, center,
            camera_outward_direction(frame),
        )

    @staticmethod
    def orientation_constraints(
        detections: list[ViewDetection],
    ) -> list[tuple[str, np.ndarray, str]]:
        return [(item.label, item.outward, item.view) for item in detections
                if item.label is not None]

    @staticmethod
    def _corners_in_frame(
        corners: np.ndarray,
        image_shape: tuple[int, ...],
        margin: float = 4.0,
    ) -> bool:
        if corners.shape != (4, 2) or len(image_shape) < 2:
            return False
        height, width = int(image_shape[0]), int(image_shape[1])
        xs = corners[:, 0]
        ys = corners[:, 1]
        return bool(
            np.all(xs >= margin)
            and np.all(xs <= width - 1 - margin)
            and np.all(ys >= margin)
            and np.all(ys <= height - 1 - margin)
        )

    @staticmethod
    def _quad_aspect_ok(corners: np.ndarray, min_ratio: float = .78) -> bool:
        edges = [
            float(np.linalg.norm(corners[(i + 1) % 4] - corners[i]))
            for i in range(4)
        ]
        longest = max(edges)
        shortest = min(edges)
        return longest > 18.0 and (shortest / longest) >= min_ratio

    def map_detection(
        self, detection: ViewDetection, rotation: np.ndarray,
        fallback_center: np.ndarray | None, frame_index: int,
    ) -> ViewResult:
        frame = detection.frame
        center = detection.center_world_m if detection.center_world_m is not None \
            else fallback_center
        if center is None:
            return ViewResult(detection.view, detection.label, None, False,
                              "cube_center_unavailable", None, None, None, None, None, 0)
        # Visible face predicted by the estimated orientation for this camera.
        outward = detection.outward
        scores = {face: float(np.dot(face_normal_world(face, rotation), outward))
                  for face in FACES}
        predicted = max(scores, key=scores.get)
        if scores[predicted] < .70:
            return ViewResult(detection.view, detection.label, predicted, False,
                              "no_face_frontal_to_camera", None, None, None, None, None, 0)
        corners = detection.corners_xy
        colors = detection.raw_colors
        confidences = detection.raw_confidences
        corner_source = "vision_corners"
        need_reproject = (
            detection.label != predicted
            or corners is None
            or not self._corners_in_frame(corners, frame.rgb.shape, margin=2.0)
            or not self._quad_aspect_ok(corners)
        )
        if need_reproject:
            # Dominant-component detection may pick an adjacent oblique face,
            # clip one sticker row/column, or fail under occlusion. Re-sample
            # the image inside the quad that the estimated pose projects for
            # the predicted face, and accept it only if the sampled centre
            # colour confirms the identity.
            try:
                pose_corners = projected_face_corners(predicted, center, rotation,
                                                      frame.calibration)
            except ValueError:
                pose_corners = None
            remapped = None
            if (
                pose_corners is not None
                and self._corners_in_frame(pose_corners, frame.rgb.shape, margin=2.0)
            ):
                remapped = self.mapper.map_face(
                    frame.rgb, frame_index=frame_index, source_view=detection.view,
                    corners_xy=pose_corners, face_hint=predicted,
                )
            if (
                remapped is not None
                and remapped.observation.stickers[4] == predicted
                and all(s is not None for s in remapped.observation.stickers)
            ):
                corners = np.asarray(remapped.corners_xy, dtype=float)
                colors = remapped.observation.stickers
                confidences = remapped.observation.sticker_confidences
                corner_source = "pose_projected_corners_center_validated"
            elif (
                detection.label != predicted
                or corners is None
                or not self._corners_in_frame(corners, frame.rgb.shape, margin=2.0)
            ):
                return ViewResult(
                    detection.view, detection.label, predicted, False,
                    f"face_identity_mismatch:{detection.label}!={predicted}",
                    None, None, None, None, None, 0,
                )
        try:
            decision = solve_d4_assignment(predicted, corners, center, rotation,
                                           frame.calibration)
        except ValueError as exc:
            return ViewResult(detection.view, detection.label, predicted, False,
                              f"projection_unavailable:{exc}", corner_source,
                              None, None, None, None, 0)
        if not decision.reliable:
            return ViewResult(detection.view, detection.label, predicted, False,
                              decision.reason, corner_source, decision.error,
                              decision.margin, decision.quarter_turns, decision.mirrored, 0)
        canonical_colors = remap_observation_values(colors, decision.observed_to_canonical)
        canonical_confidences = remap_observation_values(
            confidences, decision.observed_to_canonical
        )
        if canonical_colors[4] != predicted:
            return ViewResult(detection.view, detection.label, predicted, False,
                              "center_color_changed_after_mapping", corner_source,
                              decision.error, decision.margin, decision.quarter_turns,
                              decision.mirrored, 0)
        observation = FaceObservation(
            predicted, tuple(canonical_colors),
            float(np.mean([value for value in canonical_confidences])),
            frame_index, tuple(float(value) for value in canonical_confidences),
            f"{detection.view}:canonical_v8",
        )
        known = sum(value is not None for value in canonical_colors)
        return ViewResult(
            detection.view, detection.label, predicted, True, None, corner_source,
            decision.error, decision.margin, decision.quarter_turns, decision.mirrored,
            known, observation,
        )


# ---------------------------------------------------------------------------
# Expected-information-gain view selection over held reorientations
# ---------------------------------------------------------------------------


def held_visible_faces(rotation: np.ndarray, finger_axis: np.ndarray,
                       palm_direction: np.ndarray) -> tuple[str, ...]:
    """Faces a horizontal camera ring can see while the cube is grasped."""
    visible = []
    for face in FACES:
        normal = face_normal_world(face, rotation)
        if abs(float(normal[2])) > .5:
            continue
        if abs(float(np.dot(normal, finger_axis))) > .5:
            continue
        if float(np.dot(normal, palm_direction)) > .5:
            continue
        visible.append(face)
    return tuple(visible)


@dataclass(frozen=True, slots=True)
class ReorientOption:
    axis: str
    radians: float
    visible_faces: tuple[str, ...]
    gain: int


class InformationGainViewPlanner:
    """Pick the feasible wrist reorientation exposing the most missing stickers."""

    OPTIONS = (("pitch", np.pi / 2), ("pitch", -np.pi / 2),
               ("yaw", np.pi / 2), ("yaw", -np.pi / 2))

    def __init__(self, pitch_limits: tuple[float, float] = (-1.7, 1.7)) -> None:
        self.pitch_limits = pitch_limits

    def options(self, rotation: np.ndarray, gripper: dict[str, Any], pitch_angle: float,
                yaw_angle: float, needed: dict[str, int]) -> list[ReorientOption]:
        finger = np.asarray(gripper["finger_closure_axis"], dtype=float)
        palm = np.asarray(gripper["palm_direction"], dtype=float)
        options = []
        for axis, radians in self.OPTIONS:
            if axis == "pitch":
                target = pitch_angle + radians
                if not self.pitch_limits[0] <= target <= self.pitch_limits[1]:
                    continue
                world_axis = np.array([np.cos(yaw_angle), np.sin(yaw_angle), 0.0])
            else:
                world_axis = np.array([0.0, 0.0, 1.0])
            turn = axis_rotation(world_axis, radians)
            visible = held_visible_faces(turn @ rotation, turn @ finger, turn @ palm)
            options.append(ReorientOption(axis, float(radians), visible,
                                          sum(needed.get(face, 0) for face in visible)))
        options.sort(key=lambda item: (item.gain, item.axis == "pitch"), reverse=True)
        return options


# ---------------------------------------------------------------------------
# Controller
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class SixFaceEvent:
    step: int
    skill: str
    success: bool
    unknown: int
    conflicts: int
    detail: dict[str, Any]


@dataclass(frozen=True, slots=True)
class SixFaceInspectionResult:
    success: bool
    complete: bool
    legal: bool
    reconstructed_facelets: str | None
    first_failure_stage: str | None
    action_count: int
    physical_skill_counts: dict[str, int]
    orientation_log: tuple[dict[str, Any], ...]
    events: tuple[SixFaceEvent, ...]
    evidence: tuple[dict[str, Any], ...]


class SixFaceActiveInspector:
    """Autonomous grasp/release/regrasp/reorient/observe loop for 54 stickers."""

    def __init__(self, backend: Any, *, max_held_reorients: int = 4,
                 max_rounds: int = 2) -> None:
        self.backend = backend
        self.max_held_reorients = max_held_reorients
        self.max_rounds = max_rounds
        self.perception = SixFacePerception()
        self.planner = InformationGainViewPlanner()
        self.fusion = StickerStateFusion()
        self.events: list[SixFaceEvent] = []
        self.orientation_log: list[dict[str, Any]] = []
        self.rotation: np.ndarray | None = None
        self.last_center: np.ndarray | None = None
        self.frame_index = 0
        self.skill_counts: dict[str, int] = {}

    # -- bookkeeping -----------------------------------------------------
    def _record(self, skill: str, success: bool, detail: dict[str, Any]) -> None:
        self.skill_counts[skill] = self.skill_counts.get(skill, 0) + 1
        self.events.append(SixFaceEvent(
            len(self.events) + 1, skill, bool(success), self.fusion.unknown_count,
            self.fusion.conflict_count, detail,
        ))

    def _needed_by_face(self) -> dict[str, int]:
        needed = {face: 0 for face in FACES}
        conflicting = set(self.fusion.conflicting_indices)
        for item in self.fusion.fused_evidence():
            if item.color is None or f"{item.face}{item.index}" in conflicting:
                needed[item.face] += 1
        return needed

    def _done(self) -> bool:
        if self.fusion.unknown_count or self.fusion.conflict_count:
            return False
        try:
            self.fusion.validated_facelets()
        except ValueError:
            return False
        return True

    @staticmethod
    def _physical_ok(result: dict[str, Any]) -> bool:
        if result.get("success"):
            return True
        # The legacy world-state refresh after a physically successful action
        # may fail; v8 perception performs its own camera-only estimate.
        return bool(result.get("physical_success")) and \
            result.get("failure_code") == "WORLD_STATE_REFRESH_FAILED"

    # -- perception step -------------------------------------------------
    def _observe(self, skill: str, capture: dict[str, Any], views_prefix: str) -> bool:
        frames: list[RGBDFrame] = list(capture.get("frames", []))
        detections = [self.perception.detect(frame, f"{views_prefix}:{frame.camera_name}")
                      for frame in frames]
        prior = self.rotation
        estimate = estimate_orientation_from_centers(
            self.perception.orientation_constraints(detections), prior,
        )
        self.orientation_log.append({
            "skill": skill, **{key: value for key, value in asdict(estimate).items()},
        })
        if estimate.unique and estimate.matrix is not None:
            self.rotation = estimate.matrix
        centers = [item.center_world_m for item in detections
                   if item.center_world_m is not None]
        if centers:
            self.last_center = np.median(np.asarray(centers), axis=0)
        results: list[ViewResult] = []
        if self.rotation is not None:
            for detection in detections:
                self.frame_index += 1
                result = self.perception.map_detection(
                    detection, self.rotation, self.last_center, self.frame_index,
                )
                results.append(result)
                if result.observation is not None:
                    self.fusion.add(result.observation)
        visual_evidence = [
            {"face": result.observation.face, "index": index, "color": color,
             "source_view": result.observation.source_view}
            for result in results if result.observation is not None
            for index, color in enumerate(result.observation.stickers)
        ]
        self._record(skill, bool(capture.get("success")) and any(r.emitted for r in results), {
            "orientation_unique": estimate.unique,
            "orientation_source": estimate.source,
            "orientation_outliers": list(estimate.outliers),
            "views": [result.summary() for result in results] or [
                {"view": item.view, "label": item.label} for item in detections
            ],
            "conflicting_indices": list(self.fusion.conflicting_indices),
            "capture_failure_code": capture.get("failure_code"),
            "visual_evidence": visual_evidence,
        })
        return bool(results)

    # -- physical helpers ------------------------------------------------
    def _joint_angle(self, name: str) -> float:
        backend = self.backend
        return float(backend.data.qpos[backend.model.jnt_qposadr[backend._joint(name)]])

    def _released_round(self) -> str | None:
        placed = self.backend.task_place_release()
        self._record("place_release", self._physical_ok(placed), {
            key: placed.get(key) for key in (
                "success", "failure_code", "height_before_m", "height_after_m", "released",
            )
        })
        if not self._physical_ok(placed):
            return str(placed.get("failure_code") or "PLACE_RELEASE_FAILED")
        capture = self.backend.capture_released_views()
        self._observe("observe_released", capture, "released")
        if not capture.get("success"):
            return str(capture.get("failure_code") or "RELEASED_OBSERVATION_FAILED")
        return None

    def _regrasp_released_cube(self) -> tuple[bool, dict[str, Any]]:
        """Regrasp the released cube using the v6 failure-aware skill agent."""
        from .failure_aware_v6 import FailureAwareRulePlanner, FailureAwareSkillAgent
        from .vlm import HeuristicSceneVLM

        regrasp = FailureAwareSkillAgent(
            self.backend, HeuristicSceneVLM(), FailureAwareRulePlanner()
        ).run(0, 15, reset_scene=False)
        if regrasp.final_success:
            aligned = self.backend.task_align_scan_axes()
            return bool(aligned.get("success")), {
                "attempts": regrasp.attempts,
                "recovery_success": regrasp.recovery_success,
                "failure_history": list(regrasp.failure_history),
                "aligned": bool(aligned.get("success")),
                "failure_code": aligned.get("failure_code"),
            }
        # Fallback to backend.task_regrasp() if v6 did not succeed.
        fallback = self.backend.task_regrasp()
        return bool(fallback.get("success")), {
            "attempts": regrasp.attempts,
            "failure_history": list(regrasp.failure_history),
            "fallback": fallback,
            "failure_code": fallback.get("failure_code") or "REGRASP_FAILED",
        }

    def _held_round(self) -> str | None:
        ok, regrasp_detail = self._regrasp_released_cube()
        self._record("regrasp", ok, regrasp_detail)
        if not ok:
            return str(regrasp_detail.get("failure_code") or "REGRASP_FAILED")
        # Keep the released-round rotation as a prior; if align_scan_axes after
        # regrasp rotated the cube around Z, the held side views plus the top
        # face identity uniquely update self.rotation.
        self._observe("observe_held_after_regrasp", self.backend.capture_held_views(), "held")
        for _ in range(self.max_held_reorients):
            if self._done() or self.rotation is None:
                break
            gripper = self.backend.gripper_axes_world()
            options = self.planner.options(
                self.rotation, gripper, self._joint_angle("wrist_pitch_joint"),
                self._joint_angle("wrist_yaw_joint"), self._needed_by_face(),
            )
            best = options[0] if options else None
            if best is None or best.gain <= 0:
                self._record("plan_next_view", False, {
                    "reason": "no_held_view_exposes_missing_stickers",
                    "needed_by_face": self._needed_by_face(),
                    "options": [asdict(option) for option in options],
                })
                break
            self._record("plan_next_view", True, {
                "chosen": asdict(best), "options": [asdict(option) for option in options],
                "needed_by_face": self._needed_by_face(),
            })
            yaw = self._joint_angle("wrist_yaw_joint")
            world_axis = (np.array([0.0, 0.0, 1.0]) if best.axis == "yaw"
                          else np.array([np.cos(yaw), np.sin(yaw), 0.0]))
            reoriented = self.backend.task_reorient(best.axis, best.radians)
            error = abs(float(reoriented.get("reorient_error_radians", 1.0)))
            rotated = error <= .08 and float(reoriented.get("bilateral_contact_fraction", 0)) >= .8
            self._record(f"reorient_{best.axis}", rotated, {
                key: reoriented.get(key) for key in (
                    "success", "failure_code", "reorient_error_radians",
                    "bilateral_contact_fraction", "max_relative_slip_m", "recentered_from_rgbd",
                )
            })
            if not rotated:
                return str(reoriented.get("failure_code") or "REORIENT_FAILED")
            # Propagate the measured whole-cube rotation as the prior.
            actual = best.radians - float(reoriented.get("reorient_error_radians", 0.0)) * 0
            self.rotation = axis_rotation(world_axis, actual) @ self.rotation
            self.rotation = np.round(self.rotation)
            capture = self.backend.capture_held_views()
            self._observe(f"observe_held_after_{best.axis}", capture, "held")
            if not capture.get("success"):
                return str(capture.get("failure_code") or "HELD_GRASP_LOST")
        return None

    # -- main loop ---------------------------------------------------------
    def run(self, seed: int, *, reset_scene: bool = True) -> SixFaceInspectionResult:
        from .failure_aware_v6 import FailureAwareRulePlanner, FailureAwareSkillAgent
        from .vlm import HeuristicSceneVLM

        if reset_scene:
            self.backend.reset_random(seed, 15)
        failure: str | None = None
        grasp = FailureAwareSkillAgent(
            self.backend, HeuristicSceneVLM(), FailureAwareRulePlanner()
        ).run(seed, 15, reset_scene=False)
        self._record("initial_grasp", grasp.final_success, {"attempts": grasp.attempts})
        if not grasp.final_success:
            failure = "INITIAL_GRASP_FAILED"
        if failure is None:
            aligned = self.backend.task_align_scan_axes()
            self._record("align_scan_axes", bool(aligned["success"]), {
                key: aligned.get(key) for key in ("target_yaw_radians", "failure_code")
            })
            if not aligned["success"]:
                failure = "ALIGN_SCAN_AXES_FAILED"
        for _ in range(self.max_rounds):
            if failure is not None or self._done():
                break
            failure = self._released_round()
            if failure is not None or self._done():
                break
            failure = self._held_round()
        complete = self.fusion.unknown_count == 0
        reconstructed = self.fusion.facelets()
        legal = False
        if reconstructed is not None:
            try:
                self.fusion.validated_facelets()
                legal = True
            except ValueError:
                legal = False
        success = complete and legal and self.fusion.conflict_count == 0
        self._record("validate_state", success, {
            "complete": complete, "legal": legal,
            "conflicts": self.fusion.conflict_count,
        })
        if failure is None and not success:
            if not complete:
                failure = "SCAN_INCOMPLETE"
            elif not legal:
                failure = "RECONSTRUCTION_ILLEGAL"
            else:
                failure = "UNRESOLVED_CONFLICTS"
        return SixFaceInspectionResult(
            success, complete, legal, reconstructed, failure, len(self.events),
            dict(self.skill_counts), tuple(self.orientation_log), tuple(self.events),
            tuple(asdict(item) for item in self.fusion.fused_evidence()),
        )
