"""Unified Perception Evidence Protocol schemas and adapters (CubeRelay M4-E).

This module bridges existing deterministic CV structures (`AgentObservation`,
`ObservationReference`, `scene_state`) and VLM semantic output (`SemanticSceneObservation`)
into a traceable `PerceptionEvidenceBundle` without modifying core CV algorithms.
"""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any, Literal, Mapping
import uuid

from pydantic import BaseModel, ConfigDict, Field

from cube_relay.mission.models import (
    AgentObservation,
    ObservationReference,
    SemanticSceneObservation,
)


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class SourceCoercionError(ValueError):
    """Raised when an empirical/heuristic or synthetic output is coerced into REAL_VLM."""


class EvidenceSourceType(str, Enum):
    """Explicit non-fungible source labels for geometric and semantic evidence."""

    DETERMINISTIC_CV = "DETERMINISTIC_CV"
    REAL_VLM = "REAL_VLM"
    INJECTED_SEMANTICS = "INJECTED_SEMANTICS"
    HEURISTIC_VISION = "HEURISTIC_VISION"
    RECORDED_REPLAY = "RECORDED_REPLAY"
    NONE = "NONE"


_HEURISTIC_MARKERS = frozenset({
    "heuristic_local",
    "heuristicscenevlm",
    "heuristic_scene_vlm",
    "heuristic_vision",
    "chroma_cube_presence_detector",
    "heuristic_chroma",
})


class FrameEvidenceRef(BaseModel):
    """Traceable reference to one captured camera frame inside an evidence bundle."""

    model_config = ConfigDict(extra="forbid")

    camera_id: str
    frame_id: str
    captured_sim_time: float | None = None
    image_sha256: str | None = None
    image_present: bool = False
    camera_metadata: dict[str, Any] = Field(default_factory=dict)


class GeometricObservationPayload(BaseModel):
    """Quantitative CV & proprioceptive state preserved without VLM mutation (Principle P1)."""

    model_config = ConfigDict(extra="forbid")

    observation_id: str
    frame_id: str
    camera_id: str
    sim_time: float
    pose_estimate_id: str | None = None
    cube_detected: bool = False
    pose_valid: bool = False
    rgbd_valid: bool = False
    cube_center_world_m: tuple[float, float, float] | None = None
    cube_held_in_gripper: bool = False
    gripper_open: bool | None = None
    cube_resting_on_table: bool | None = None
    observed_facelets: str | None = None
    observed_count: int = 0
    unknown_count: int = 54
    conflict_count: int = 0
    unknown_facelet_indices: list[int] = Field(default_factory=list)
    observation_conflicts: list[str] = Field(default_factory=list)
    cv_54_verified: bool = False
    state_valid: bool = False
    validation_status: str = "UNVERIFIED"
    latest_skill_result: dict[str, Any] | None = None
    scene_summary: dict[str, Any] = Field(default_factory=dict)


class SemanticObservationEnvelope(BaseModel):
    """Semantic observation tagged with source, frame/timestamp identity, and raw client origin."""

    model_config = ConfigDict(extra="forbid")

    semantic: SemanticSceneObservation
    source_type: EvidenceSourceType
    is_real_vlm: bool = False
    declared_origin: str | None = None
    client_type: str | None = None
    model_provider: str | None = None
    model_name: str | None = None
    captured_sim_time: float | None = None
    captured_wall_time_utc: str | None = None
    request_id: str | None = None
    latency_ms: float | None = None


class EvidenceConflict(BaseModel):
    """Deterministic conflict or hazard detected during evidence validation."""

    model_config = ConfigDict(extra="forbid")

    conflict_code: str
    severity: Literal["INFO", "WARNING", "ERROR", "BLOCK"]
    message: str
    affects_grasp_precondition: bool = False
    rejects_semantic_observation: bool = False


class EvidenceProvenance(BaseModel):
    """Non-forgeable source tracking from perception providers into agent context."""

    model_config = ConfigDict(extra="forbid")

    geometric_source: EvidenceSourceType = EvidenceSourceType.DETERMINISTIC_CV
    semantic_source: EvidenceSourceType = EvidenceSourceType.NONE
    fallback_source: str | None = None
    semantic_client_type: str | None = None
    model_provider: str | None = None
    model_name: str | None = None
    is_real_vlm: bool = False
    semantic_provided_to_agent: bool = False
    vlm_requested: bool = False
    vlm_timed_out: bool = False
    vlm_error_code: str | None = None
    vlm_error: str | None = None
    notes: list[str] = Field(default_factory=list)


class EvidenceValidity(BaseModel):
    """Freshness, frame alignment, and deterministic safety precondition flags."""

    model_config = ConfigDict(extra="forbid")

    validation_status: Literal["VALID", "DEGRADED", "CONFLICT", "STALE", "BLOCKED"] = "VALID"
    is_stale: bool = False
    stale_reasons: list[str] = Field(default_factory=list)
    frame_alignment_ok: bool = True
    semantic_present: bool = False
    semantic_usable: bool = False
    semantic_rejected: bool = False
    semantic_rejection_reason: str | None = None
    semantic_age_sec: float | None = None
    cv_cube_detected: bool = False
    cv_pose_valid: bool = False
    cv_54_verified: bool = False
    preserve_verified_cv_fusion: bool = False
    robot_holding_cube: bool = False
    grasp_precondition_satisfied: bool = False
    can_use_semantic_for_grasp_pose: bool = False
    uncertainty_explained_by_semantics: bool = False
    safety_controls_unblocked: bool = True
    fail_closed_required: bool = False
    checked_rules: list[str] = Field(default_factory=list)
    advisory_notes: list[str] = Field(default_factory=list)


class PerceptionEvidenceBundle(BaseModel):
    """Single traceable evidence container handed from Perception -> Validator -> Agent."""

    model_config = ConfigDict(extra="forbid")

    bundle_id: str = Field(default_factory=lambda: f"ev-{uuid.uuid4().hex[:12]}")
    observation_id: str
    mission_id: str | None = None
    session_id: str | None = None
    primary_camera_id: str
    primary_frame_id: str
    captured_sim_time: float
    wall_time_utc: str = Field(default_factory=_utc_now_iso)
    frames: list[FrameEvidenceRef] = Field(default_factory=list)
    geometric_observation: GeometricObservationPayload
    semantic_observation: SemanticSceneObservation | None = None
    raw_semantic_envelope: SemanticObservationEnvelope | None = None
    observation_refs: list[str] = Field(default_factory=list)
    provenance: EvidenceProvenance = Field(default_factory=EvidenceProvenance)
    validity: EvidenceValidity = Field(default_factory=EvidenceValidity)
    conflicts: list[EvidenceConflict] = Field(default_factory=list)
    detected_conflicts: list[str] = Field(default_factory=list)

    def to_agent_prompt_payload(self) -> dict[str, Any]:
        """Return a concise, non-privileged summary for AgentPlanningProvider (no image bytes)."""
        return {
            "bundle_id": self.bundle_id,
            "observation_id": self.observation_id,
            "primary_camera_id": self.primary_camera_id,
            "primary_frame_id": self.primary_frame_id,
            "captured_sim_time": self.captured_sim_time,
            "frame_count": len(self.frames),
            "observation_refs": list(self.observation_refs),
            "geometric_summary": {
                "cube_detected": self.geometric_observation.cube_detected,
                "pose_valid": self.geometric_observation.pose_valid,
                "rgbd_valid": self.geometric_observation.rgbd_valid,
                "cube_held_in_gripper": self.geometric_observation.cube_held_in_gripper,
                "observed_count": self.geometric_observation.observed_count,
                "unknown_count": self.geometric_observation.unknown_count,
                "conflict_count": self.geometric_observation.conflict_count,
                "cv_54_verified": self.geometric_observation.cv_54_verified,
                "validation_status": self.geometric_observation.validation_status,
            },
            "provenance": self.provenance.model_dump(mode="json"),
            "validity": self.validity.model_dump(mode="json"),
            "detected_conflicts": list(self.detected_conflicts),
        }


def _coerce_source_type(value: EvidenceSourceType | str) -> EvidenceSourceType:
    if isinstance(value, EvidenceSourceType):
        return value
    return EvidenceSourceType(str(value))


def _contains_heuristic_marker(text: str | None) -> bool:
    if not text:
        return False
    lower = text.strip().lower()
    return any(marker in lower for marker in _HEURISTIC_MARKERS)


def enforce_non_coerced_semantic_source(
    requested_source: EvidenceSourceType,
    *,
    declared_origin: str | None = None,
    client_type: str | None = None,
    model_provider: str | None = None,
    is_real_vlm: bool | None = None,
) -> tuple[EvidenceSourceType, bool]:
    """Ensure heuristic or synthetic detectors can never be upgraded to REAL_VLM."""
    has_heuristic_origin = any(
        _contains_heuristic_marker(token)
        for token in (declared_origin, client_type, model_provider)
    )
    if has_heuristic_origin and (requested_source == EvidenceSourceType.REAL_VLM or is_real_vlm):
        raise SourceCoercionError(
            "Heuristic pixel detectors (HEURISTIC_VISION / HeuristicSceneVLM) must never be converted to REAL_VLM."
        )
    if has_heuristic_origin:
        return EvidenceSourceType.HEURISTIC_VISION, False

    if client_type and "fake" in client_type.lower():
        if requested_source == EvidenceSourceType.REAL_VLM and is_real_vlm is True:
            raise SourceCoercionError(
                "Fake structured model client cannot claim is_real_vlm=True."
            )
        if requested_source == EvidenceSourceType.REAL_VLM:
            # Preserve non-real status when a fake client executes through VLMPerceptionProvider.
            return EvidenceSourceType.REAL_VLM, False

    resolved_is_real = (
        bool(is_real_vlm)
        if is_real_vlm is not None
        else requested_source == EvidenceSourceType.REAL_VLM
    )
    if requested_source != EvidenceSourceType.REAL_VLM and resolved_is_real:
        raise SourceCoercionError(
            f"Only REAL_VLM source may set is_real_vlm=True, got {requested_source.value}."
        )
    return requested_source, resolved_is_real


def resolve_semantic_envelope(
    semantic_input: SemanticSceneObservation | SemanticObservationEnvelope | None,
    *,
    semantic_source: EvidenceSourceType | str = EvidenceSourceType.NONE,
    declared_origin: str | None = None,
    client_type: str | None = None,
    model_provider: str | None = None,
    model_name: str | None = None,
    captured_sim_time: float | None = None,
    captured_wall_time_utc: str | None = None,
    request_id: str | None = None,
    latency_ms: float | None = None,
    is_real_vlm: bool | None = None,
) -> SemanticObservationEnvelope | None:
    """Wrap raw `SemanticSceneObservation` into a source-verified envelope."""
    if semantic_input is None:
        return None
    if isinstance(semantic_input, SemanticObservationEnvelope):
        checked_source, checked_real = enforce_non_coerced_semantic_source(
            semantic_input.source_type,
            declared_origin=semantic_input.declared_origin,
            client_type=semantic_input.client_type,
            model_provider=semantic_input.model_provider,
            is_real_vlm=semantic_input.is_real_vlm,
        )
        return semantic_input.model_copy(
            update={"source_type": checked_source, "is_real_vlm": checked_real}
        )

    requested = _coerce_source_type(semantic_source)
    if requested == EvidenceSourceType.NONE:
        requested = EvidenceSourceType.INJECTED_SEMANTICS
    checked_source, checked_real = enforce_non_coerced_semantic_source(
        requested,
        declared_origin=declared_origin,
        client_type=client_type,
        model_provider=model_provider,
        is_real_vlm=is_real_vlm,
    )
    return SemanticObservationEnvelope(
        semantic=semantic_input,
        source_type=checked_source,
        is_real_vlm=checked_real,
        declared_origin=declared_origin,
        client_type=client_type,
        model_provider=model_provider,
        model_name=model_name,
        captured_sim_time=captured_sim_time,
        captured_wall_time_utc=captured_wall_time_utc or _utc_now_iso(),
        request_id=request_id,
        latency_ms=latency_ms,
    )


def extract_frame_refs(
    observation: AgentObservation | Mapping[str, Any],
    *,
    extra_frames: list[FrameEvidenceRef] | None = None,
) -> list[FrameEvidenceRef]:
    """Collect multi-camera and multi-frame references from an observation without altering schema."""
    obs_dict = observation.model_dump() if isinstance(observation, AgentObservation) else dict(observation)
    camera_meta = dict(obs_dict.get("camera_metadata") or {})
    primary_cam = str(obs_dict.get("camera_id") or "overhead")
    primary_frame = str(obs_dict.get("frame_id") or "frame-unknown")
    sim_time = float(obs_dict.get("sim_time") or 0.0)
    image_present = bool(obs_dict.get("rgb_image_data_url"))
    primary_sha = obs_dict.get("image_sha256")

    refs: list[FrameEvidenceRef] = [
        FrameEvidenceRef(
            camera_id=primary_cam,
            frame_id=primary_frame,
            captured_sim_time=sim_time,
            image_sha256=primary_sha,
            image_present=image_present,
            camera_metadata={
                k: v for k, v in camera_meta.items() if k not in {"multiview_frames", "frames"}
            },
        )
    ]
    seen_keys = {(primary_cam, primary_frame)}

    raw_multi = camera_meta.get("multiview_frames") or camera_meta.get("frames") or []
    if isinstance(raw_multi, list):
        for item in raw_multi:
            if not isinstance(item, Mapping):
                continue
            cam = str(item.get("camera_id") or item.get("camera_name") or primary_cam)
            fid = str(item.get("frame_id") or primary_frame)
            if (cam, fid) in seen_keys:
                continue
            seen_keys.add((cam, fid))
            refs.append(
                FrameEvidenceRef(
                    camera_id=cam,
                    frame_id=fid,
                    captured_sim_time=item.get("captured_sim_time", sim_time),
                    image_sha256=item.get("image_sha256"),
                    image_present=bool(item.get("image_present", False)),
                    camera_metadata=dict(item.get("camera_metadata") or {}),
                )
            )

    for extra in extra_frames or ():
        key = (extra.camera_id, extra.frame_id)
        if key not in seen_keys:
            seen_keys.add(key)
            refs.append(extra)
    return refs


def build_geometric_observation(
    observation: AgentObservation | Mapping[str, Any],
    *,
    observation_ref: ObservationReference | Mapping[str, Any] | None = None,
    scene_state: Mapping[str, Any] | None = None,
) -> GeometricObservationPayload:
    """Adapt existing CV / `AgentObservation` / `scene_state` payloads into formal evidence."""
    obs = observation.model_dump() if isinstance(observation, AgentObservation) else dict(observation)
    ref = (
        observation_ref.model_dump()
        if isinstance(observation_ref, ObservationReference)
        else dict(observation_ref or {})
    )
    scene = dict(scene_state or {})
    summary = dict(obs.get("scene_summary") or {})

    observed_count = int(obs.get("observed_count", summary.get("observed_count", ref.get("observed_count", 0))) or 0)
    unknown_indices = [int(i) for i in (obs.get("unknown_facelet_indices") or [])]
    unknown_count = int(
        ref.get("unknown_count")
        if ref.get("unknown_count") is not None
        else summary.get("unknown_count", len(unknown_indices) if unknown_indices else max(0, 54 - observed_count))
    )
    obs_conflicts = [str(c) for c in (obs.get("observation_conflicts") or [])]
    conflict_count = int(
        ref.get("conflict_count")
        if ref.get("conflict_count") is not None
        else summary.get("conflict_count", len(obs_conflicts))
    )

    state_valid = bool(
        summary.get("state_valid")
        if summary.get("state_valid") is not None
        else scene.get("state_valid", False)
    )
    validation_status = str(
        ref.get("validation_status")
        or summary.get("validation_status")
        or scene.get("validation_status")
        or ("SOLVABLE" if state_valid and observed_count >= 54 and conflict_count == 0 else "UNVERIFIED")
    )
    cv_54_verified = bool(
        (observed_count >= 54 and unknown_count == 0 and conflict_count == 0)
        and (state_valid or validation_status in {"VERIFIED", "SOLVABLE", "VALID"})
    )

    pose_estimate_id = (
        summary.get("pose_estimate_id")
        or scene.get("pose_estimate_id")
        or (obs.get("camera_metadata") or {}).get("pose_estimate_id")
    )
    cube_center = ref.get("cube_center_world_m") or summary.get("cube_center_world_m") or scene.get("cube_center_world_m")
    if isinstance(cube_center, list) and len(cube_center) == 3:
        cube_center_tuple: tuple[float, float, float] | None = (
            float(cube_center[0]),
            float(cube_center[1]),
            float(cube_center[2]),
        )
    elif isinstance(cube_center, tuple) and len(cube_center) == 3:
        cube_center_tuple = (float(cube_center[0]), float(cube_center[1]), float(cube_center[2]))
    else:
        cube_center_tuple = None

    raw_detected = summary.get("cube_detected", scene.get("cube_detected"))
    raw_pose_valid = summary.get("pose_valid", scene.get("pose_valid"))
    raw_rgbd_valid = summary.get("rgbd_valid", scene.get("rgbd_valid"))
    if raw_detected is None:
        raw_detected = bool(pose_estimate_id or cube_center_tuple is not None or observed_count > 0 or scene.get("cube_held_in_gripper"))
    if raw_pose_valid is None:
        raw_pose_valid = bool(pose_estimate_id is not None or cube_center_tuple is not None)
    if raw_rgbd_valid is None:
        raw_rgbd_valid = bool(raw_pose_valid)

    cube_held = bool(
        summary.get("cube_held_in_gripper")
        if summary.get("cube_held_in_gripper") is not None
        else scene.get("cube_held_in_gripper", False)
    )
    gripper_open = summary.get("gripper_open", scene.get("gripper_open"))
    cube_on_table = summary.get("cube_resting_on_table", scene.get("cube_resting_on_table"))

    return GeometricObservationPayload(
        observation_id=str(obs["observation_id"]),
        frame_id=str(obs["frame_id"]),
        camera_id=str(obs["camera_id"]),
        sim_time=float(obs["sim_time"]),
        pose_estimate_id=str(pose_estimate_id) if pose_estimate_id else None,
        cube_detected=bool(raw_detected),
        pose_valid=bool(raw_pose_valid),
        rgbd_valid=bool(raw_rgbd_valid),
        cube_center_world_m=cube_center_tuple,
        cube_held_in_gripper=cube_held,
        gripper_open=bool(gripper_open) if gripper_open is not None else None,
        cube_resting_on_table=bool(cube_on_table) if cube_on_table is not None else None,
        observed_facelets=obs.get("observed_facelets") or ref.get("reconstructed_facelets"),
        observed_count=observed_count,
        unknown_count=unknown_count,
        conflict_count=conflict_count,
        unknown_facelet_indices=unknown_indices,
        observation_conflicts=obs_conflicts,
        cv_54_verified=cv_54_verified,
        state_valid=state_valid,
        validation_status=validation_status,
        latest_skill_result=dict(obs.get("latest_skill_result")) if obs.get("latest_skill_result") else None,
        scene_summary=summary,
    )


def build_perception_evidence_bundle(
    observation: AgentObservation | Mapping[str, Any],
    *,
    observation_ref: ObservationReference | Mapping[str, Any] | None = None,
    scene_state: Mapping[str, Any] | None = None,
    semantic_observation: SemanticSceneObservation | SemanticObservationEnvelope | None = None,
    semantic_source: EvidenceSourceType | str = EvidenceSourceType.NONE,
    geometric_source: EvidenceSourceType | str = EvidenceSourceType.DETERMINISTIC_CV,
    frame_refs: list[FrameEvidenceRef] | None = None,
    is_real_vlm: bool | None = None,
    declared_origin: str | None = None,
    semantic_client_type: str | None = None,
    model_provider: str | None = None,
    model_name: str | None = None,
    semantic_captured_sim_time: float | None = None,
    semantic_wall_time_utc: str | None = None,
    semantic_request_id: str | None = None,
    semantic_latency_ms: float | None = None,
    vlm_requested: bool = False,
    vlm_timed_out: bool = False,
    vlm_error_code: str | None = None,
    vlm_error: str | None = None,
    bundle_id: str | None = None,
) -> PerceptionEvidenceBundle:
    """Build a traceable `PerceptionEvidenceBundle` preserving IDs, frames, timestamps, and provenance."""
    obs_dict = observation.model_dump() if isinstance(observation, AgentObservation) else dict(observation)
    geom = build_geometric_observation(
        obs_dict,
        observation_ref=observation_ref,
        scene_state=scene_state,
    )
    frames = extract_frame_refs(obs_dict, extra_frames=frame_refs)
    geo_src = _coerce_source_type(geometric_source)

    envelope = resolve_semantic_envelope(
        semantic_observation,
        semantic_source=semantic_source,
        declared_origin=declared_origin,
        client_type=semantic_client_type,
        model_provider=model_provider,
        model_name=model_name,
        captured_sim_time=semantic_captured_sim_time,
        captured_wall_time_utc=semantic_wall_time_utc,
        request_id=semantic_request_id,
        latency_ms=semantic_latency_ms,
        is_real_vlm=is_real_vlm,
    )

    obs_refs: list[str] = [geom.observation_id]
    if geom.pose_estimate_id and geom.pose_estimate_id not in obs_refs:
        obs_refs.append(geom.pose_estimate_id)
    for frame in frames:
        if frame.frame_id and frame.frame_id not in obs_refs:
            obs_refs.append(frame.frame_id)
    if envelope is not None:
        if envelope.semantic.observation_id not in obs_refs:
            obs_refs.append(envelope.semantic.observation_id)
        if envelope.semantic.frame_id not in obs_refs:
            obs_refs.append(envelope.semantic.frame_id)

    effective_sem_source = envelope.source_type if envelope is not None else EvidenceSourceType.NONE
    effective_is_real = envelope.is_real_vlm if envelope is not None else False
    effective_provider = (envelope.model_provider if envelope else None) or model_provider
    effective_model = (envelope.model_name if envelope else None) or model_name
    effective_client_type = (envelope.client_type if envelope else None) or semantic_client_type

    provenance = EvidenceProvenance(
        geometric_source=geo_src,
        semantic_source=effective_sem_source,
        semantic_client_type=effective_client_type,
        model_provider=effective_provider,
        model_name=effective_model,
        is_real_vlm=effective_is_real,
        semantic_provided_to_agent=False,
        vlm_requested=vlm_requested or envelope is not None,
        vlm_timed_out=vlm_timed_out,
        vlm_error_code=vlm_error_code,
        vlm_error=vlm_error,
    )

    validity = EvidenceValidity(
        semantic_present=envelope is not None,
        semantic_usable=envelope is not None,
        cv_cube_detected=geom.cube_detected,
        cv_pose_valid=geom.pose_valid,
        cv_54_verified=geom.cv_54_verified,
        preserve_verified_cv_fusion=geom.cv_54_verified,
        robot_holding_cube=geom.cube_held_in_gripper,
        grasp_precondition_satisfied=bool(geom.cube_detected and geom.pose_valid and geom.rgbd_valid),
        can_use_semantic_for_grasp_pose=False,
    )

    return PerceptionEvidenceBundle(
        bundle_id=bundle_id or f"ev-{uuid.uuid4().hex[:12]}",
        observation_id=geom.observation_id,
        mission_id=obs_dict.get("mission_id"),
        session_id=obs_dict.get("session_id"),
        primary_camera_id=geom.camera_id,
        primary_frame_id=geom.frame_id,
        captured_sim_time=geom.sim_time,
        frames=frames,
        geometric_observation=geom,
        semantic_observation=envelope.semantic if envelope else None,
        raw_semantic_envelope=envelope,
        observation_refs=obs_refs,
        provenance=provenance,
        validity=validity,
    )
