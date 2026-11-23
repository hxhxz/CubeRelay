"""Deterministic Evidence Validator for Perception -> Agent boundary (CubeRelay M4-E).

Handles provenance integrity, frame/timestamp staleness, geometric vs. semantic
conflicts (Cases 1-7), and safety precondition invariance without introducing
opaque fusion models or choosing high-level Skill sequences.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from cube_relay.mission.models import SemanticSceneObservation

from .evidence import (
    EvidenceConflict,
    EvidenceSourceType,
    PerceptionEvidenceBundle,
    SourceCoercionError,
)


class EvidenceValidationResult(BaseModel):
    """Structured output returned by `EvidenceValidator.validate`."""

    model_config = ConfigDict(extra="forbid")

    bundle: PerceptionEvidenceBundle
    passed: bool
    semantic_passed_to_agent: SemanticSceneObservation | None = None
    allow_grasp_generation: bool = False
    preserve_verified_cv_fusion: bool = False
    authoritative_holding_cube: bool = False
    safety_controls_unblocked: bool = True
    fallback_mode: str | None = None


def _contains_any(text: str, patterns: tuple[str, ...]) -> bool:
    return any(pattern in text for pattern in patterns)


def _semantic_claims_held(sem: SemanticSceneObservation) -> bool:
    rel = sem.cube_relation_to_gripper.lower()
    summary = sem.summary.lower()
    combined = f"{rel} {summary}"
    negated = (
        "not held",
        "not_held",
        "not in gripper",
        "not_in_gripper",
        "released",
        "no longer held",
        "away from gripper",
        "separate from gripper",
        "不在夹爪",
        "已释放",
        "已放下",
        "未夹持",
        "未抓持",
    )
    if _contains_any(rel, negated):
        return False
    positive = (
        "held",
        "in_gripper",
        "in gripper",
        "inside gripper",
        "grasped",
        "gripped",
        "clamped",
        "between_fingers",
        "between fingers",
        "holding",
        "夹持",
        "抓取中",
        "抓持",
        "握持",
    )
    if _contains_any(rel, positive):
        return True
    if not _contains_any(combined, negated) and _contains_any(
        combined, ("still held", "still in gripper", "仍在夹持", "仍在爪中")
    ):
        return True
    return False


def _semantic_claims_graspable(sem: SemanticSceneObservation) -> bool:
    text = " ".join(
        [
            sem.cube_relation_to_gripper,
            sem.support_relation,
            sem.summary,
            *sem.suggested_observations,
        ]
    ).lower()
    negated = (
        "cannot grasp",
        "can't grasp",
        "not graspable",
        "unable to grasp",
        "unreachable",
        "cannot be grasped",
        "不可抓取",
        "无法抓取",
        "不能抓取",
    )
    if _contains_any(text, negated):
        return False
    positive = (
        "graspable",
        "ready to grasp",
        "ready_to_grasp",
        "ready for grasp",
        "can grasp",
        "can be grasped",
        "can pick",
        "pickable",
        "regrasp now",
        "approach and grasp",
        "可抓取",
        "可以抓取",
        "可直接抓取",
    )
    return _contains_any(text, positive)


def _semantic_explains_occlusion(sem: SemanticSceneObservation) -> bool:
    if sem.occluded_regions or sem.information_gaps or sem.suggested_observations:
        return True
    text = f"{sem.summary} {sem.cube_relation_to_gripper} {sem.support_relation}".lower()
    return _contains_any(
        text,
        ("occlud", "blocked", "hidden", "partial", "blur", "back face", "unobserved", "遮挡", "背面", "盲区"),
    )


class EvidenceValidator:
    """Lightweight deterministic validator enforcing Principles P1-P4 and Cases 1-7."""

    def __init__(self, *, default_max_semantic_age_sec: float = 5.0) -> None:
        self.default_max_semantic_age_sec = float(default_max_semantic_age_sec)

    @staticmethod
    def assert_valid_source_transition(
        from_source: EvidenceSourceType,
        to_source: EvidenceSourceType,
    ) -> None:
        """Prevent converting heuristic/non-VLM sources into REAL_VLM."""
        if from_source == EvidenceSourceType.HEURISTIC_VISION and to_source == EvidenceSourceType.REAL_VLM:
            raise SourceCoercionError(
                "Converting HEURISTIC_VISION evidence to REAL_VLM is forbidden."
            )
        if from_source != to_source and to_source == EvidenceSourceType.REAL_VLM:
            raise SourceCoercionError(
                f"Cannot relabel {from_source.value} as REAL_VLM."
            )

    def validate(
        self,
        bundle: PerceptionEvidenceBundle,
        *,
        max_semantic_age_sec: float | None = None,
        allow_cv_only_on_vlm_failure: bool = False,
    ) -> EvidenceValidationResult:
        """Run deterministic validation on `bundle` and return a validated copy."""
        max_age = self.default_max_semantic_age_sec if max_semantic_age_sec is None else float(max_semantic_age_sec)
        geom = bundle.geometric_observation
        sem = bundle.semantic_observation
        envelope = bundle.raw_semantic_envelope

        conflicts: list[EvidenceConflict] = []
        provenance = bundle.provenance.model_copy(deep=True)
        validity = bundle.validity.model_copy(deep=True)

        checked_rules = [
            "provenance_integrity",
            "case_6_frame_and_age_freshness",
            "case_7_vlm_timeout_and_safety_isolation",
            "case_1_cv_unlocalized_guard",
            "case_2_cv_54_fusion_preservation",
            "case_3_proprioception_override_guard",
            "case_4_rgbd_pose_grasp_precondition",
            "case_5_uncertainty_with_occlusion_note",
        ]
        validity.checked_rules = checked_rules
        validity.safety_controls_unblocked = True
        validity.can_use_semantic_for_grasp_pose = False
        validity.cv_cube_detected = geom.cube_detected
        validity.cv_pose_valid = geom.pose_valid
        validity.cv_54_verified = geom.cv_54_verified
        validity.preserve_verified_cv_fusion = geom.cv_54_verified
        validity.robot_holding_cube = geom.cube_held_in_gripper

        # Quantitatively required grasp preconditions always belong to deterministic CV + RGB-D.
        allow_grasp = bool(geom.cube_detected and geom.pose_valid and geom.rgbd_valid)
        validity.grasp_precondition_satisfied = allow_grasp

        semantic_passed: SemanticSceneObservation | None = sem
        fallback_mode: str | None = provenance.fallback_source
        fail_closed = False

        # 0. Provenance integrity: never allow heuristic pixel detectors disguised as REAL_VLM.
        client_tag = (provenance.semantic_client_type or "").lower()
        provider_tag = (provenance.model_provider or "").lower()
        origin_tag = (envelope.declared_origin if envelope else "") or ""
        heuristic_leak = (
            provenance.semantic_source == EvidenceSourceType.HEURISTIC_VISION
            or any(
                tok in tag
                for tag in (client_tag, provider_tag, origin_tag.lower())
                for tok in ("heuristic_local", "heuristicscenevlm", "chroma_cube_presence_detector")
            )
        )
        if heuristic_leak and (
            provenance.semantic_source == EvidenceSourceType.REAL_VLM or provenance.is_real_vlm
        ):
            conflicts.append(
                EvidenceConflict(
                    conflict_code="SOURCE_COERCION_FORBIDDEN",
                    severity="BLOCK",
                    message="Heuristic pixel detector output cannot be marked as REAL_VLM.",
                    rejects_semantic_observation=True,
                )
            )
            provenance.semantic_source = EvidenceSourceType.HEURISTIC_VISION
            provenance.is_real_vlm = False
            validity.semantic_rejected = True
            validity.semantic_rejection_reason = "SOURCE_COERCION_FORBIDDEN"
            validity.semantic_usable = False
            semantic_passed = None
            fail_closed = True

        # 1. Case 6: Stale frame / observation mismatch / timestamp expiration.
        if semantic_passed is not None:
            valid_frame_pairs = {(f.camera_id, f.frame_id) for f in bundle.frames}
            valid_frame_pairs.add((bundle.primary_camera_id, bundle.primary_frame_id))
            obs_match = semantic_passed.observation_id == bundle.observation_id
            frame_cam_match = (semantic_passed.camera_id, semantic_passed.frame_id) in valid_frame_pairs

            age_sec: float | None = None
            if envelope is not None and envelope.captured_sim_time is not None:
                age_sec = max(0.0, float(bundle.captured_sim_time) - float(envelope.captured_sim_time))
                validity.semantic_age_sec = age_sec

            stale_reasons: list[str] = []
            if not obs_match:
                stale_reasons.append(
                    f"semantic observation_id={semantic_passed.observation_id} != current {bundle.observation_id}"
                )
            if not frame_cam_match:
                stale_reasons.append(
                    f"semantic frame/camera=({semantic_passed.camera_id},{semantic_passed.frame_id}) not in current frames"
                )
            if stale_reasons:
                validity.frame_alignment_ok = False
                validity.is_stale = True
                validity.stale_reasons.extend(stale_reasons)
                conflicts.append(
                    EvidenceConflict(
                        conflict_code="CASE_6_STALE_SEMANTIC_FRAME_MISMATCH",
                        severity="ERROR",
                        message="Semantic output references an older or mismatched frame/observation; rejected.",
                        rejects_semantic_observation=True,
                    )
                )

            if age_sec is not None and age_sec > max_age:
                validity.is_stale = True
                validity.stale_reasons.append(
                    f"semantic_age_sec={age_sec:.3f} exceeds max_semantic_age_sec={max_age:.3f}"
                )
                conflicts.append(
                    EvidenceConflict(
                        conflict_code="CASE_6_STALE_SEMANTIC_EXPIRED",
                        severity="ERROR",
                        message="Semantic output exceeded freshness window; rejected.",
                        rejects_semantic_observation=True,
                    )
                )

            if validity.is_stale:
                validity.semantic_rejected = True
                validity.semantic_rejection_reason = (
                    validity.stale_reasons[0] if validity.stale_reasons else "STALE_FRAME"
                )
                validity.semantic_usable = False
                semantic_passed = None
                if provenance.vlm_requested and allow_cv_only_on_vlm_failure:
                    fallback_mode = "CV_ONLY_STALE_FALLBACK"
                    provenance.fallback_source = fallback_mode
                    provenance.notes.append("Stale VLM frame rejected; continuing in CV_ONLY fallback.")
                elif provenance.vlm_requested:
                    provenance.notes.append("Stale VLM frame rejected before reaching Task Agent.")

        # 2. Case 7: VLM provider timeout or failure when VLM was requested.
        if provenance.vlm_requested and (
            provenance.vlm_timed_out or provenance.vlm_error_code is not None or (sem is None and semantic_passed is None)
        ):
            msg = (
                f"VLM perception unavailable ({provenance.vlm_error_code or 'timeout/missing'}); "
                "emergency safety controls remain unblocked."
            )
            if allow_cv_only_on_vlm_failure:
                fallback_mode = fallback_mode or "CV_ONLY_FALLBACK"
                provenance.fallback_source = fallback_mode
                provenance.semantic_source = EvidenceSourceType.NONE
                provenance.notes.append("Explicitly fell back to CV_ONLY after VLM timeout/failure.")
                conflicts.append(
                    EvidenceConflict(
                        conflict_code="CASE_7_VLM_PROVIDER_TIMEOUT_OR_ERROR",
                        severity="WARNING",
                        message=msg,
                    )
                )
                validity.semantic_usable = False
            else:
                fail_closed = True
                conflicts.append(
                    EvidenceConflict(
                        conflict_code="CASE_7_VLM_PROVIDER_TIMEOUT_OR_ERROR",
                        severity="ERROR",
                        message=f"{msg} Failing closed because allow_cv_only_on_vlm_failure=False.",
                    )
                )
                validity.semantic_usable = False

        # 3. Cases 1-5 on aligned, non-rejected semantic evidence.
        if semantic_passed is not None:
            # Case 1: CV unlocalized while VLM claims cube is visible.
            if not geom.cube_detected and semantic_passed.cube_visible:
                allow_grasp = False
                validity.grasp_precondition_satisfied = False
                conflicts.append(
                    EvidenceConflict(
                        conflict_code="CASE_1_CV_UNLOCALIZED_VLM_CLAIMS_VISIBLE",
                        severity="WARNING",
                        message="CV has not localized cube; VLM visibility claim cannot synthesize grasp pose.",
                        affects_grasp_precondition=True,
                    )
                )

            # Case 2: CV already 54/54 verified while single-frame VLM reports hidden/occluded faces.
            if geom.cv_54_verified and (
                not semantic_passed.cube_visible
                or bool(semantic_passed.occluded_regions)
                or bool(semantic_passed.information_gaps)
            ):
                validity.preserve_verified_cv_fusion = True
                conflicts.append(
                    EvidenceConflict(
                        conflict_code="CASE_2_CV_FULL_54_VLM_REPORTS_OCCLUSION",
                        severity="WARNING",
                        message="Single-frame VLM reports occlusion/gaps, but verified 54/54 CV fusion is preserved.",
                    )
                )

            # Case 3: Robot proprioception says released/not held while VLM claims held.
            if not geom.cube_held_in_gripper and _semantic_claims_held(semantic_passed):
                validity.robot_holding_cube = False
                conflicts.append(
                    EvidenceConflict(
                        conflict_code="CASE_3_PROPRIOCEPTION_RELEASED_VLM_CLAIMS_HELD",
                        severity="WARNING",
                        message="Robot proprioception shows cube released; VLM holding claim does not override.",
                    )
                )

            # Case 4: VLM claims cube can be grasped while RGB-D has no valid pose.
            if (not geom.pose_valid or not geom.rgbd_valid) and _semantic_claims_graspable(semantic_passed):
                allow_grasp = False
                validity.grasp_precondition_satisfied = False
                conflicts.append(
                    EvidenceConflict(
                        conflict_code="CASE_4_NO_VALID_RGBD_POSE_VLM_CLAIMS_GRASPABLE",
                        severity="WARNING",
                        message="No valid RGB-D 6D pose; VLM graspable claim cannot authorize grasp generation.",
                        affects_grasp_precondition=True,
                    )
                )

            # Case 5: CV has uncertainty (unknowns/conflicts/unverified) and VLM gives occlusion explanation.
            has_cv_uncertainty = (
                geom.unknown_count > 0
                or geom.conflict_count > 0
                or geom.observed_count < 54
                or not geom.state_valid
            )
            if has_cv_uncertainty and _semantic_explains_occlusion(semantic_passed):
                validity.uncertainty_explained_by_semantics = True
                validity.advisory_notes.append(
                    "CASE_5_UNCERTAINTY_WITH_OCCLUSION_EXPLANATION: Keep both CV uncertainty and VLM occlusion explanation for Task Agent observation decision."
                )

        provenance.semantic_provided_to_agent = semantic_passed is not None
        validity.semantic_usable = semantic_passed is not None
        validity.fail_closed_required = fail_closed

        if fail_closed:
            validity.validation_status = "BLOCKED"
        elif validity.is_stale:
            validity.validation_status = "STALE"
        elif any(c.severity in {"WARNING", "ERROR", "BLOCK"} for c in conflicts):
            if (
                len(conflicts) == 1
                and conflicts[0].conflict_code == "CASE_7_VLM_PROVIDER_TIMEOUT_OR_ERROR"
                and fallback_mode is not None
            ):
                validity.validation_status = "DEGRADED"
            else:
                validity.validation_status = "CONFLICT"
        else:
            validity.validation_status = "VALID"

        conflict_codes = [c.conflict_code for c in conflicts]
        updated_bundle = bundle.model_copy(
            update={
                "semantic_observation": semantic_passed,
                "provenance": provenance,
                "validity": validity,
                "conflicts": conflicts,
                "detected_conflicts": conflict_codes,
            }
        )

        # `passed=True` means the evidence bundle is safe to hand to Task Agent (with
        # `semantic_passed_to_agent` scrubbed if stale/rejected, and CV preconditions intact).
        passed = not fail_closed and not validity.semantic_rejected
        return EvidenceValidationResult(
            bundle=updated_bundle,
            passed=passed,
            semantic_passed_to_agent=semantic_passed,
            allow_grasp_generation=allow_grasp,
            preserve_verified_cv_fusion=validity.preserve_verified_cv_fusion,
            authoritative_holding_cube=geom.cube_held_in_gripper,
            safety_controls_unblocked=True,
            fallback_mode=fallback_mode,
        )
