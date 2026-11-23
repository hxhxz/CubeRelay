"""Benchmark cases (32 Decision Replay cases across L1-L5 + Closed-loop MuJoCo scenarios)."""

from __future__ import annotations

import base64
from pathlib import Path
from typing import Any

from cube_relay.mission.models import MissionStatus, MissionType
from cube_relay.mission.skill_registry import SkillRegistry

from .m4c_importer import discover_m4c_bundles, extract_m4c_replay_slice
from .schema import (
    BENCHMARK_VERSION,
    BenchmarkCase,
    BenchmarkSourceType,
    CapabilityDimension,
    DecisionRuleSpec,
)

ROOT = Path(__file__).resolve().parents[3]
DEFAULT_M4C_BUNDLES_DIR = ROOT / "results" / "m4c_experiments" / "bundles"
DEFAULT_M4A_FRAMES_DIR = ROOT / "results" / "m4a_acceptance" / "frames"

DEFAULT_BUDGET: dict[str, Any] = {
    "max_calls": 4,
    "max_input_tokens": 8000,
    "max_output_tokens": 1200,
    "timeout_seconds": 45.0,
}


def _file_to_jpeg_data_url(path: Path) -> str | None:
    if not path.exists():
        return None
    raw = path.read_bytes()
    b64 = base64.b64encode(raw).decode("ascii")
    return f"data:image/jpeg;base64,{b64}"


def _build_registry_metadata(
    scene_state: dict[str, Any],
    *,
    disabled_skills: list[str] | None = None,
    removed_skills: list[str] | None = None,
) -> tuple[list[dict[str, Any]], dict[str, dict[str, Any]], list[str]]:
    reg = SkillRegistry().clone(
        disabled_skills=disabled_skills,
        removed_skills=removed_skills,
    )
    available: list[dict[str, Any]] = []
    preconditions: dict[str, dict[str, Any]] = {}
    allowed_actions: list[str] = ["FINISH", "SAFE_STOP", "CAPABILITY_BLOCKED", "REQUEST_REPLAN"]
    for desc in reg.list_skills():
        if desc.skill_id == "active_six_face_scan":
            continue
        pre_ok, missing = reg.check_preconditions(desc.skill_id, scene_state)
        preconditions[desc.skill_id] = {
            "implemented": desc.implemented,
            "required_preconditions": list(desc.required_preconditions),
            "preconditions_met": pre_ok and desc.implemented,
            "missing_preconditions": list(missing),
        }
        if desc.implemented:
            available.append({
                "skill_id": desc.skill_id,
                "title": desc.title,
                "description": desc.description,
                "is_physical_action": desc.is_physical_action,
                "supported_parameters": dict(desc.supported_parameters),
                "required_preconditions": list(desc.required_preconditions),
                "preconditions_met": pre_ok,
                "missing_preconditions": list(missing),
            })
            allowed_actions.append(desc.skill_id)
    return available, preconditions, allowed_actions


def _mission_dict(
    mission_type: MissionType,
    *,
    case_id: str,
    user_goal: str | None = None,
    success_criteria: str | None = None,
) -> dict[str, Any]:
    from cube_relay.mission.planner import MISSION_SPECS

    spec = MISSION_SPECS[mission_type]
    return {
        "mission_id": f"msn-{case_id.lower()}",
        "session_id": f"BENCH-{case_id}",
        "mission_type": mission_type.value,
        "user_goal": user_goal or spec["user_goal"],
        "success_criteria": success_criteria or spec["success_criteria"],
        "status": MissionStatus.OBSERVING.value,
        "created_at": "00:00:00",
    }


def _sem(
    *,
    obs_id: str,
    frame_id: str,
    camera_id: str = "overhead",
    cube_visible: bool = True,
    relation: str,
    support: str,
    visible: list[str],
    occluded: list[str],
    gaps: list[str],
    suggested: list[str],
    conflicts: list[str] | None = None,
    confidence: float = 0.92,
    summary: str,
) -> dict[str, Any]:
    return {
        "observation_id": obs_id,
        "frame_id": frame_id,
        "camera_id": camera_id,
        "cube_visible": cube_visible,
        "cube_relation_to_gripper": relation,
        "support_relation": support,
        "visible_regions": visible,
        "occluded_regions": occluded,
        "information_gaps": gaps,
        "suggested_observations": suggested,
        "visual_conflicts": list(conflicts or []),
        "confidence": float(confidence),
        "summary": summary,
    }


def _make_case(
    *,
    case_id: str,
    dimension: CapabilityDimension,
    difficulty: str,
    source_type: BenchmarkSourceType,
    mission_type: MissionType = MissionType.INSPECT_CUBE,
    user_goal: str | None = None,
    success_criteria: str | None = None,
    initial_state: dict[str, Any],
    cv_state: dict[str, Any],
    observation_history: list[dict[str, Any]],
    current_observation: dict[str, Any],
    vlm_semantic_observation: dict[str, Any] | None = None,
    vlm_ablation_semantics: dict[str, dict[str, Any] | None] | None = None,
    safety_constraints: dict[str, Any] | None = None,
    failure_feedback: dict[str, Any] | None = None,
    acceptable_decisions: list[DecisionRuleSpec],
    forbidden_decisions: list[DecisionRuleSpec],
    unnecessary_decisions: list[DecisionRuleSpec] | None = None,
    expected_behavior: str,
    oracle_source: str,
    evaluation_rubric: dict[str, Any] | None = None,
    requires_human_review: bool = False,
    disabled_skills: list[str] | None = None,
    removed_skills: list[str] | None = None,
    seed: int = 0,
    provenance: dict[str, Any] | None = None,
) -> BenchmarkCase:
    available_skills, skill_preconditions, allowed_actions = _build_registry_metadata(
        initial_state,
        disabled_skills=disabled_skills,
        removed_skills=removed_skills,
    )
    default_safety = {
        "physical_supported_moves": ["U"],
        "symbolic_supported_moves_count": 18,
        "reorient_inspection_pitch_only": True,
        "require_54_facelets_for_validation": True,
        **(safety_constraints or {}),
    }
    return BenchmarkCase(
        case_id=case_id,
        benchmark_version=BENCHMARK_VERSION,
        capability_dimension=dimension,
        difficulty=difficulty,  # type: ignore[arg-type]
        source_type=source_type,
        mission=_mission_dict(mission_type, case_id=case_id, user_goal=user_goal, success_criteria=success_criteria),
        initial_state=dict(initial_state),
        observation_history=list(observation_history),
        cv_state=dict(cv_state),
        vlm_semantic_observation=vlm_semantic_observation,
        vlm_ablation_semantics=vlm_ablation_semantics or {},
        available_skills=available_skills,
        skill_preconditions=skill_preconditions,
        safety_constraints=default_safety,
        failure_feedback=failure_feedback,
        allowed_actions=allowed_actions,
        acceptable_decisions=acceptable_decisions,
        forbidden_decisions=forbidden_decisions,
        unnecessary_decisions=unnecessary_decisions or [],
        evaluation_rubric=evaluation_rubric or {
            "require_legal_action": True,
            "require_valid_parameters": True,
            "require_evidence_grounding": True,
        },
        expected_behavior=expected_behavior,
        oracle_source=oracle_source,
        requires_human_review=requires_human_review,
        seed=seed,
        max_decisions=1,
        model_budget=dict(DEFAULT_BUDGET),
        disabled_skills=list(disabled_skills or []),
        removed_skills=list(removed_skills or []),
        current_observation=dict(current_observation),
        provenance=dict(provenance or {}),
    )


def build_m4d_replay_cases(
    *,
    m4c_bundles_dir: str | Path = DEFAULT_M4C_BUNDLES_DIR,
    m4a_frames_dir: str | Path = DEFAULT_M4A_FRAMES_DIR,
) -> list[BenchmarkCase]:
    """Construct the 32-case m4d.v1 Decision Replay Benchmark suite (L1=6, L2=6, L3=8, L4=6, L5=6)."""
    bundles = discover_m4c_bundles(m4c_bundles_dir)
    frames_dir = Path(m4a_frames_dir)

    def _try_slice(cond: str, cutoff: float) -> dict[str, Any] | None:
        zp = bundles.get(cond)
        if zp is None:
            return None
        return extract_m4c_replay_slice(zp, cutoff_sim_time=cutoff)

    sl_base_init = _try_slice("baseline", 0.800001)
    sl_base_released = _try_slice("baseline", 16.605)
    sl_base_final = _try_slice("baseline", 30.329)
    sl_x005_fail = _try_slice("translate_x_005", 41.615)
    sl_x010_fail = _try_slice("translate_x_010", 12.745)
    sl_blackout = _try_slice("vision_missing_negative_control", 0.800001)

    img_released_m4a = _file_to_jpeg_data_url(frames_dir / "ablation_s1_released_table_seed0.jpg")
    img_held_m4a = _file_to_jpeg_data_url(frames_dir / "ablation_s2_held_gripper_seed0.jpg")
    img_final_m4a = _file_to_jpeg_data_url(frames_dir / "vlm_inspect_final_overhead_seed0.jpg")

    img_base_init = sl_base_init["rgb_image_data_url"] if sl_base_init else img_released_m4a
    img_base_released = sl_base_released["rgb_image_data_url"] if sl_base_released else img_released_m4a
    img_base_final = sl_base_final["rgb_image_data_url"] if sl_base_final else img_final_m4a
    img_x005 = sl_x005_fail["rgb_image_data_url"] if sl_x005_fail else img_released_m4a
    img_x010 = sl_x010_fail["rgb_image_data_url"] if sl_x010_fail else img_released_m4a
    img_blackout = sl_blackout["rgb_image_data_url"] if sl_blackout else None

    full_facelets_sample = "DFUBURBBBUBLLRFRFFRLLRFFDUUBBFDDUDLDRDUULUFRLFDBRBLRDL"
    partial_45_facelets = "DFUBURBBBUBLLRFRFFRLLRFFDUU?????????RDUULUFRLFDBRBLRDL"
    all_unknown_facelets = "?" * 54

    cases: list[BenchmarkCase] = []

    # =========================================================================
    # L1: Skill Selection (6 cases)
    # =========================================================================
    cases.append(_make_case(
        case_id="L1_01_A1_UNLOCALIZED_INIT",
        dimension=CapabilityDimension.L1_SKILL_SELECTION,
        difficulty="easy",
        source_type=BenchmarkSourceType.REAL_REPLAY if sl_base_init else BenchmarkSourceType.COUNTERFACTUAL_TEST,
        initial_state={
            "simulation_initialized": True,
            "cube_localized": False,
            "scan_attempted": False,
            "cube_released_on_table": False,
            "cube_held_in_gripper": False,
            "all_54_facelets_observed": False,
        },
        cv_state={
            "cube_localized": False,
            "observed_facelets": all_unknown_facelets,
            "observed_count": 0,
            "unknown_count": 54,
            "unknown_facelet_indices": list(range(54)),
            "observation_conflicts": [],
        },
        observation_history=[],
        current_observation={
            "observation_id": "obs-l1-01",
            "frame_id": (sl_base_init["selected_frame"]["frame_id"] if sl_base_init and sl_base_init.get("selected_frame") else "frm-init-01"),
            "camera_id": "overhead",
            "sim_time": 0.8,
            "rgb_image_data_url": img_base_init,
        },
        vlm_semantic_observation=_sem(
            obs_id="obs-l1-01",
            frame_id=(sl_base_init["selected_frame"]["frame_id"] if sl_base_init and sl_base_init.get("selected_frame") else "frm-init-01"),
            relation="cube sitting on workspace table away from open gripper",
            support="supported by workspace table",
            visible=["top face", "partial front/right sides"],
            occluded=["bottom face", "rear faces"],
            gaps=["3D cube localization not yet performed", "54 stickers unknown"],
            suggested=["localize cube from overhead RGB-D before grasping"],
            summary="Cube rests on workspace table; 3D pose not yet localized.",
        ),
        acceptable_decisions=[
            DecisionRuleSpec(
                decision_kinds=["EXECUTE_STEP"],
                skill_ids=["observe_workspace"],
                parameter_rules={"camera_name": ["overhead", "world_top", "scan_top", "inspection_top", None]},
                note="Localize unlocalized cube first.",
            ),
        ],
        forbidden_decisions=[
            DecisionRuleSpec(decision_kinds=["EXECUTE_STEP"], skill_ids=["place_and_release", "observe_visible_faces", "regrasp_cube", "reorient_cube", "finish_inspection", "validate_cube_state"], note="Precondition cube_localized is False."),
            DecisionRuleSpec(decision_kinds=["COMPLETE_MISSION"], note="Cannot finish unlocalized."),
        ],
        expected_behavior="Select observe_workspace because cube_localized=False.",
        oracle_source="SkillRegistry preconditions + A1 state rule (M4-C baseline t=0.8s)",
        provenance={
            "case_alias": "A1",
            "source_bundle_run_id": sl_base_init["run_id"] if sl_base_init else None,
            "cutoff_sim_time": 0.8,
            "m4c_bundle_loaded": sl_base_init is not None,
        },
    ))

    cases.append(_make_case(
        case_id="L1_02_PRECOND_REORIENT_WHEN_RELEASED",
        dimension=CapabilityDimension.L1_SKILL_SELECTION,
        difficulty="easy",
        source_type=BenchmarkSourceType.COUNTERFACTUAL_TEST,
        initial_state={
            "simulation_initialized": True,
            "cube_localized": True,
            "scan_attempted": True,
            "cube_released_on_table": True,
            "cube_held_in_gripper": False,
            "all_54_facelets_observed": False,
        },
        cv_state={
            "cube_localized": True,
            "observed_facelets": partial_45_facelets,
            "observed_count": 45,
            "unknown_count": 9,
            "unknown_facelet_indices": list(range(27, 36)),
            "observation_conflicts": [],
        },
        observation_history=[
            {"observation_id": "obs-hist-01", "frame_id": "frm-hist-01", "sim_time": 0.8, "coverage": 0, "visual_summary": "Cube localized on workspace"},
            {"observation_id": "obs-hist-02", "frame_id": "frm-hist-02", "sim_time": 16.6, "coverage": 45, "unknown_after": 9, "visual_summary": "Released scan observed 45/54; D face (27..35) unknown"},
        ],
        current_observation={
            "observation_id": "obs-l1-02",
            "frame_id": "frm-l1-02",
            "camera_id": "overhead",
            "sim_time": 16.7,
            "rgb_image_data_url": img_released_m4a,
        },
        vlm_semantic_observation=_sem(
            obs_id="obs-l1-02",
            frame_id="frm-l1-02",
            relation="released on table; gripper retracted",
            support="supported by table",
            visible=["top face", "4 lateral faces"],
            occluded=["bottom D face against table"],
            gaps=["bottom 9 stickers unknown"],
            suggested=["regrasp cube from table before rotating"],
            summary="Cube rests released on table; bottom D face occluded by table.",
        ),
        acceptable_decisions=[
            DecisionRuleSpec(decision_kinds=["EXECUTE_STEP"], skill_ids=["regrasp_cube"], note="Regrasp released cube before flipping."),
        ],
        forbidden_decisions=[
            DecisionRuleSpec(decision_kinds=["EXECUTE_STEP"], skill_ids=["reorient_cube"], note="Illegal: cube_held_in_gripper=False."),
            DecisionRuleSpec(decision_kinds=["EXECUTE_STEP"], skill_ids=["finish_inspection", "validate_cube_state"], note="9 stickers remain unknown."),
            DecisionRuleSpec(decision_kinds=["COMPLETE_MISSION"], note="Cannot finish with 9 unknown stickers."),
        ],
        unnecessary_decisions=[
            DecisionRuleSpec(decision_kinds=["EXECUTE_STEP"], skill_ids=["observe_workspace", "place_and_release", "observe_visible_faces"], note="Redundant when already released and observed 45/54."),
        ],
        expected_behavior="Select regrasp_cube (and NOT reorient_cube since cube_held_in_gripper is False).",
        oracle_source="SkillRegistry precondition check: cube_released_on_table vs cube_held_in_gripper",
    ))

    cases.append(_make_case(
        case_id="L1_03_PARAM_BOUNDARY_PITCH_VS_YAW",
        dimension=CapabilityDimension.L1_SKILL_SELECTION,
        difficulty="medium",
        source_type=BenchmarkSourceType.COUNTERFACTUAL_TEST,
        initial_state={
            "simulation_initialized": True,
            "cube_localized": True,
            "scan_attempted": True,
            "cube_released_on_table": False,
            "cube_held_in_gripper": True,
            "all_54_facelets_observed": False,
        },
        cv_state={
            "cube_localized": True,
            "observed_facelets": partial_45_facelets,
            "observed_count": 45,
            "unknown_count": 9,
            "unknown_facelet_indices": list(range(27, 36)),
            "observation_conflicts": [],
        },
        observation_history=[
            {"observation_id": "obs-hist-10", "frame_id": "frm-hist-10", "sim_time": 16.6, "coverage": 45, "unknown_after": 9, "visual_summary": "Released scan got 45/54; D face unknown"},
            {"observation_id": "obs-hist-11", "frame_id": "frm-hist-11", "sim_time": 26.3, "coverage": 45, "unknown_after": 9, "visual_summary": "Regrasped & held observation refreshed anchor; D face still hidden below"},
        ],
        failure_feedback={
            "skill_id": "regrasp_cube",
            "success": True,
            "result_summary": "安全重抓并刷新持握姿态锚点成功，unknown 仍为 9 (D 面)。",
        },
        current_observation={
            "observation_id": "obs-l1-03",
            "frame_id": "frm-l1-03",
            "camera_id": "overhead",
            "sim_time": 26.4,
            "rgb_image_data_url": img_held_m4a,
        },
        vlm_semantic_observation=_sem(
            obs_id="obs-l1-03",
            frame_id="frm-l1-03",
            relation="held between gripper finger pads in mid-air",
            support="held by bilateral gripper pads",
            visible=["top face", "lateral sides"],
            occluded=["bottom D face facing downward"],
            gaps=["bottom D face needs pitch rotation to face upward/side cameras"],
            suggested=["pitch reorientation -90 degrees to expose bottom face"],
            summary="Cube held in gripper; bottom face remains occluded downward.",
        ),
        acceptable_decisions=[
            DecisionRuleSpec(
                decision_kinds=["EXECUTE_STEP"],
                skill_ids=["reorient_cube"],
                parameter_rules={"axis": ["pitch"], "degrees": [-90, -90.0]},
                note="Safe inspection reorientation requires axis='pitch', degrees=-90.",
            ),
        ],
        forbidden_decisions=[
            DecisionRuleSpec(decision_kinds=["EXECUTE_STEP"], skill_ids=["reorient_cube"], parameter_rules={"axis": ["yaw", "roll"]}, note="Yaw/roll forbidden for hidden-face inspection."),
            DecisionRuleSpec(decision_kinds=["EXECUTE_STEP"], skill_ids=["reorient_cube"], parameter_rules={"degrees": [90, 90.0, 180, 45]}, note="Invalid degrees for inspection reorient."),
            DecisionRuleSpec(decision_kinds=["EXECUTE_STEP"], skill_ids=["regrasp_cube", "place_and_release", "finish_inspection"], note="Invalid precondition or premature."),
            DecisionRuleSpec(decision_kinds=["COMPLETE_MISSION"], note="Incomplete 45/54."),
        ],
        unnecessary_decisions=[
            DecisionRuleSpec(decision_kinds=["EXECUTE_STEP"], skill_ids=["observe_workspace", "observe_visible_faces"], note="Held observation already refreshed after regrasp."),
        ],
        expected_behavior="Select reorient_cube with exact safe parameters axis='pitch', degrees=-90.",
        oracle_source="SkillRegistry.validate_parameters + M4-A inspection pitch-only safety rule",
    ))

    cases.append(_make_case(
        case_id="L1_04_TERMINATION_PREMATURE_FINISH",
        dimension=CapabilityDimension.L1_SKILL_SELECTION,
        difficulty="easy",
        source_type=BenchmarkSourceType.COUNTERFACTUAL_TEST,
        initial_state={
            "simulation_initialized": True,
            "cube_localized": True,
            "scan_attempted": True,
            "cube_released_on_table": False,
            "cube_held_in_gripper": True,
            "all_54_facelets_observed": False,
            "finish_inspection_done": False,
            "cube_state_validated": False,
        },
        cv_state={
            "cube_localized": True,
            "observed_facelets": partial_45_facelets,
            "observed_count": 45,
            "unknown_count": 9,
            "unknown_facelet_indices": list(range(27, 36)),
            "observation_conflicts": [],
        },
        observation_history=[
            {"observation_id": "obs-hist-20", "frame_id": "frm-hist-20", "sim_time": 16.6, "coverage": 45, "unknown_after": 9, "visual_summary": "Released scan observed 45/54"},
            {"observation_id": "obs-hist-21", "frame_id": "frm-hist-21", "sim_time": 26.3, "coverage": 45, "unknown_after": 9, "visual_summary": "Cube regrasped"},
        ],
        failure_feedback={
            "skill_id": "reorient_cube",
            "success": True,
            "result_summary": "持握整体翻转完成：pitch 目标 -90.0°，实测腕角 -90.0°。",
        },
        current_observation={
            "observation_id": "obs-l1-04",
            "frame_id": "frm-l1-04",
            "camera_id": "overhead",
            "sim_time": 30.2,
            "rgb_image_data_url": img_held_m4a,
        },
        vlm_semantic_observation=_sem(
            obs_id="obs-l1-04",
            frame_id="frm-l1-04",
            relation="held in gripper after pitch rotation",
            support="held by gripper",
            visible=["rotated former-bottom face now exposed to scan cameras"],
            occluded=["gripper contact band"],
            gaps=["post-reorient stickers not yet captured into 54-sticker fusion"],
            suggested=["call observe_visible_faces in held mode to fuse newly exposed face"],
            summary="Cube rotated by -90 pitch while held; need held camera observation to fuse missing 9 stickers.",
        ),
        acceptable_decisions=[
            DecisionRuleSpec(
                decision_kinds=["EXECUTE_STEP"],
                skill_ids=["observe_visible_faces"],
                parameter_rules={"view_mode": ["held", "auto", None]},
                note="Observe newly exposed face after pitch reorientation.",
            ),
        ],
        forbidden_decisions=[
            DecisionRuleSpec(decision_kinds=["COMPLETE_MISSION"], note="Premature finish: 9 stickers unknown."),
            DecisionRuleSpec(decision_kinds=["EXECUTE_STEP"], skill_ids=["finish_inspection", "validate_cube_state", "place_and_release", "regrasp_cube"], note="Premature or illegal while held."),
        ],
        expected_behavior="Do not terminate prematurely; call observe_visible_faces(view_mode='held'|'auto').",
        oracle_source="Termination rule: unknown_count must reach 0 before finish_inspection/FINISH",
    ))

    cases.append(_make_case(
        case_id="L1_05_A6_VALIDATED_INSPECT_TERMINATE",
        dimension=CapabilityDimension.L1_SKILL_SELECTION,
        difficulty="easy",
        source_type=BenchmarkSourceType.COUNTERFACTUAL_TEST,
        initial_state={
            "simulation_initialized": True,
            "cube_localized": True,
            "scan_attempted": True,
            "cube_released_on_table": False,
            "cube_held_in_gripper": True,
            "all_54_facelets_observed": True,
            "finish_inspection_done": True,
            "cube_localized_and_scanned": True,
            "cube_state_validated": True,
        },
        cv_state={
            "cube_localized": True,
            "observed_facelets": full_facelets_sample,
            "observed_count": 54,
            "unknown_count": 0,
            "unknown_facelet_indices": [],
            "observation_conflicts": [],
            "validation_status": "VALID_SOLVABLE",
        },
        observation_history=[
            {"observation_id": "obs-hist-30", "frame_id": "frm-hist-30", "sim_time": 30.3, "coverage": 54, "unknown_after": 0, "conflicts": 0, "visual_summary": "54/54 fused, VALID_SOLVABLE"},
        ],
        current_observation={
            "observation_id": "obs-l1-05",
            "frame_id": "frm-l1-05",
            "camera_id": "overhead",
            "sim_time": 30.4,
            "rgb_image_data_url": img_base_final,
        },
        vlm_semantic_observation=_sem(
            obs_id="obs-l1-05",
            frame_id="frm-l1-05",
            relation="held in gripper after complete 54-sticker inspection",
            support="held by gripper",
            visible=["top and side faces"],
            occluded=[],
            gaps=[],
            suggested=["inspection already complete and validated"],
            summary="54/54 stickers observed and validated solvable; goal achieved.",
        ),
        acceptable_decisions=[
            DecisionRuleSpec(decision_kinds=["COMPLETE_MISSION"], raw_actions=["FINISH"], note="Terminate completed INSPECT_CUBE mission."),
        ],
        forbidden_decisions=[
            DecisionRuleSpec(decision_kinds=["EXECUTE_STEP"], skill_ids=["execute_physical_u_turn", "place_and_release", "regrasp_cube", "reorient_cube"], note="Unnecessary or forbidden physical actions after completion."),
            DecisionRuleSpec(decision_kinds=["SAFE_STOP"], note="Mission succeeded, should FINISH rather than abort."),
        ],
        unnecessary_decisions=[
            DecisionRuleSpec(decision_kinds=["EXECUTE_STEP"], skill_ids=["observe_workspace", "observe_visible_faces", "finish_inspection", "validate_cube_state"], note="Already finished and validated."),
        ],
        expected_behavior="Select FINISH immediately because 54/54 stickers are observed and validated.",
        oracle_source="A6 state rule + INSPECT_CUBE success criteria",
        provenance={"case_alias": "A6"},
    ))

    cases.append(_make_case(
        case_id="L1_06_UNIMPLEMENTED_MOVE_RECOGNITION",
        dimension=CapabilityDimension.L1_SKILL_SELECTION,
        difficulty="medium",
        source_type=BenchmarkSourceType.COUNTERFACTUAL_TEST,
        mission_type=MissionType.SOLVE_CUBE,
        initial_state={
            "simulation_initialized": True,
            "cube_localized": True,
            "scan_attempted": True,
            "cube_released_on_table": True,
            "cube_held_in_gripper": False,
            "all_54_facelets_observed": True,
            "finish_inspection_done": True,
            "cube_localized_and_scanned": True,
            "cube_state_validated": True,
            "symbolic_plan_available": True,
            "symbolic_solution": ["R", "U2", "F'"],
            "capability_checked": False,
            "physical_u_scene_enabled": True,
            "turn_station_available": True,
        },
        cv_state={
            "cube_localized": True,
            "observed_facelets": full_facelets_sample,
            "observed_count": 54,
            "unknown_count": 0,
            "unknown_facelet_indices": [],
            "observation_conflicts": [],
            "validation_status": "VALID_SOLVABLE",
        },
        observation_history=[
            {"observation_id": "obs-hist-40", "frame_id": "frm-hist-40", "sim_time": 30.3, "coverage": 54, "unknown_after": 0, "visual_summary": "54/54 validated; Kociemba returned ['R', 'U2', \"F'\"]"},
        ],
        current_observation={
            "observation_id": "obs-l1-06",
            "frame_id": "frm-l1-06",
            "camera_id": "overhead",
            "sim_time": 30.5,
            "rgb_image_data_url": img_released_m4a,
        },
        vlm_semantic_observation=_sem(
            obs_id="obs-l1-06",
            frame_id="frm-l1-06",
            relation="cube released on table; symbolic solve requires R, U2, F'",
            support="supported by table",
            visible=["cube ready on table"],
            occluded=[],
            gaps=[],
            suggested=["audit physical capability against symbolic solution ['R', 'U2', \"F'\"]"],
            summary="Cube validated and symbolic plan computed (['R', 'U2', \"F'\"]); physical model only supports clockwise U.",
        ),
        acceptable_decisions=[
            DecisionRuleSpec(decision_kinds=["EXECUTE_STEP"], skill_ids=["check_physical_capability"], note="Formally audit move sequence via check_physical_capability."),
            DecisionRuleSpec(decision_kinds=["BLOCK_CAPABILITY"], note="Explicitly report capability limitation on R/U2/F'."),
        ],
        forbidden_decisions=[
            DecisionRuleSpec(decision_kinds=["EXECUTE_STEP"], skill_ids=["execute_physical_u_turn"], note="Cannot execute U turn when plan requires R, U2, F'."),
            DecisionRuleSpec(decision_kinds=["COMPLETE_MISSION"], note="Cannot FINISH without checking capability / reporting block."),
        ],
        expected_behavior="Recognize unsupported physical moves via check_physical_capability or CAPABILITY_BLOCKED.",
        oracle_source="SkillRegistry physical boundary: only single clockwise U modeled",
    ))

    # =========================================================================
    # L2: State-Aware Planning (6 cases: A2, A3, A4, A5 + skip tests)
    # =========================================================================
    cases.append(_make_case(
        case_id="L2_01_A2_ALREADY_LOCALIZED",
        dimension=CapabilityDimension.L2_STATE_AWARE_PLANNING,
        difficulty="easy",
        source_type=BenchmarkSourceType.REAL_REPLAY if sl_base_init else BenchmarkSourceType.COUNTERFACTUAL_TEST,
        initial_state={
            "simulation_initialized": True,
            "cube_localized": True,
            "scan_attempted": False,
            "cube_released_on_table": False,
            "cube_held_in_gripper": False,
            "all_54_facelets_observed": False,
        },
        cv_state={
            "cube_localized": True,
            "cube_center_world_m": (
                sl_base_init["latest_pose_estimate"]["estimated_center_world_m"]
                if sl_base_init and sl_base_init.get("latest_pose_estimate")
                else [0.1015, -0.1358, 0.6692]
            ),
            "observed_facelets": all_unknown_facelets,
            "observed_count": 0,
            "unknown_count": 54,
            "unknown_facelet_indices": list(range(54)),
            "observation_conflicts": [],
        },
        observation_history=sl_base_init["observation_history"][:1] if sl_base_init and sl_base_init.get("observation_history") else [
            {"observation_id": "obs-l2-01-hist", "frame_id": "frm-l2-01", "sim_time": 0.8, "coverage": 0, "visual_summary": "Cube localized at (0.101, -0.136, 0.669) m"},
        ],
        current_observation={
            "observation_id": "obs-l2-01",
            "frame_id": (sl_base_init["selected_frame"]["frame_id"] if sl_base_init and sl_base_init.get("selected_frame") else "frm-l2-01"),
            "camera_id": "overhead",
            "sim_time": 0.8,
            "rgb_image_data_url": img_base_init,
        },
        vlm_semantic_observation=_sem(
            obs_id="obs-l2-01",
            frame_id=(sl_base_init["selected_frame"]["frame_id"] if sl_base_init and sl_base_init.get("selected_frame") else "frm-l2-01"),
            relation="cube sitting at initial table pose, not yet aligned in scan station",
            support="supported by table",
            visible=["top face"],
            occluded=["bottom and unaligned side faces"],
            gaps=["54 stickers unknown"],
            suggested=["grasp, align scan axes, and place at scan station"],
            summary="Cube already localized on table; ready for place_and_release.",
        ),
        acceptable_decisions=[
            DecisionRuleSpec(decision_kinds=["EXECUTE_STEP"], skill_ids=["place_and_release"], note="Proceed directly to place_and_release."),
        ],
        forbidden_decisions=[
            DecisionRuleSpec(decision_kinds=["EXECUTE_STEP"], skill_ids=["reorient_cube", "regrasp_cube", "finish_inspection", "validate_cube_state"], note="Preconditions unmet."),
            DecisionRuleSpec(decision_kinds=["COMPLETE_MISSION"], note="54 stickers unknown."),
        ],
        unnecessary_decisions=[
            DecisionRuleSpec(decision_kinds=["EXECUTE_STEP"], skill_ids=["observe_workspace"], note="Redundant: cube_localized is already True."),
        ],
        expected_behavior="Skip observe_workspace because cube_localized=True; execute place_and_release.",
        oracle_source="A2 state adaptation check",
        provenance={"case_alias": "A2", "m4c_bundle_loaded": sl_base_init is not None},
    ))

    cases.append(_make_case(
        case_id="L2_02_A3_ALREADY_RELEASED_ON_TABLE",
        dimension=CapabilityDimension.L2_STATE_AWARE_PLANNING,
        difficulty="medium",
        source_type=BenchmarkSourceType.COUNTERFACTUAL_TEST,
        initial_state={
            "simulation_initialized": True,
            "cube_localized": True,
            "scan_attempted": False,
            "cube_released_on_table": True,
            "cube_held_in_gripper": False,
            "all_54_facelets_observed": False,
        },
        cv_state={
            "cube_localized": True,
            "observed_facelets": all_unknown_facelets,
            "observed_count": 0,
            "unknown_count": 54,
            "unknown_facelet_indices": list(range(54)),
            "observation_conflicts": [],
        },
        observation_history=[
            {"observation_id": "obs-l2-02-hist", "frame_id": "frm-l2-02-hist", "sim_time": 10.6, "coverage": 0, "visual_summary": "Cube placed and released onto scan station"},
        ],
        current_observation={
            "observation_id": "obs-l2-02",
            "frame_id": "frm-l2-02",
            "camera_id": "overhead",
            "sim_time": 10.7,
            "rgb_image_data_url": img_released_m4a,
        },
        vlm_semantic_observation=_sem(
            obs_id="obs-l2-02",
            frame_id="frm-l2-02",
            relation="already released on scan station table, gripper retracted",
            support="supported by scan table",
            visible=["top U face", "4 side faces"],
            occluded=["bottom D face"],
            gaps=["no stickers scanned yet (0/54)"],
            suggested=["observe visible faces in released mode directly"],
            summary="Cube is already aligned & released on table; skip place_and_release and scan visible faces.",
        ),
        acceptable_decisions=[
            DecisionRuleSpec(
                decision_kinds=["EXECUTE_STEP"],
                skill_ids=["observe_visible_faces"],
                parameter_rules={"view_mode": ["released", "auto", None]},
                note="Skip redundant place_and_release and observe released faces.",
            ),
        ],
        forbidden_decisions=[
            DecisionRuleSpec(decision_kinds=["EXECUTE_STEP"], skill_ids=["reorient_cube", "finish_inspection", "validate_cube_state"], note="Preconditions unmet."),
            DecisionRuleSpec(decision_kinds=["COMPLETE_MISSION"], note="0/54 observed."),
        ],
        unnecessary_decisions=[
            DecisionRuleSpec(decision_kinds=["EXECUTE_STEP"], skill_ids=["observe_workspace", "place_and_release"], note="Redundant: cube already localized and released on scan station."),
        ],
        expected_behavior="Skip observe_workspace and place_and_release; directly call observe_visible_faces.",
        oracle_source="A3 state adaptation check",
        provenance={"case_alias": "A3"},
    ))

    cases.append(_make_case(
        case_id="L2_03_A4_PARTIAL_45_OF_54_HELD",
        dimension=CapabilityDimension.L2_STATE_AWARE_PLANNING,
        difficulty="medium",
        source_type=BenchmarkSourceType.COUNTERFACTUAL_TEST,
        initial_state={
            "simulation_initialized": True,
            "cube_localized": True,
            "scan_attempted": True,
            "cube_released_on_table": False,
            "cube_held_in_gripper": True,
            "all_54_facelets_observed": False,
        },
        cv_state={
            "cube_localized": True,
            "observed_facelets": partial_45_facelets,
            "observed_count": 45,
            "unknown_count": 9,
            "unknown_facelet_indices": list(range(27, 36)),
            "observation_conflicts": [],
        },
        observation_history=[
            {"observation_id": "obs-l2-03-h1", "frame_id": "frm-l2-03-h1", "sim_time": 16.6, "coverage": 45, "unknown_after": 9, "visual_summary": "Released scan observed 45/54"},
            {"observation_id": "obs-l2-03-h2", "frame_id": "frm-l2-03-h2", "sim_time": 26.3, "coverage": 45, "unknown_after": 9, "visual_summary": "Regrasped & refreshed held anchor; bottom D face still unknown"},
        ],
        failure_feedback={"skill_id": "regrasp_cube", "success": True, "result_summary": "安全重抓成功，已刷新持握姿态锚点"},
        current_observation={
            "observation_id": "obs-l2-03",
            "frame_id": "frm-l2-03",
            "camera_id": "overhead",
            "sim_time": 26.4,
            "rgb_image_data_url": img_held_m4a,
        },
        vlm_semantic_observation=_sem(
            obs_id="obs-l2-03",
            frame_id="frm-l2-03",
            relation="cube held in gripper after regrasp",
            support="held by bilateral gripper pads",
            visible=["top and sides"],
            occluded=["bottom D face"],
            gaps=["9 bottom stickers require pitch rotation to inspect"],
            suggested=["reorient_cube pitch -90"],
            summary="45/54 observed; cube held in gripper; pitch -90 needed to expose bottom face.",
        ),
        acceptable_decisions=[
            DecisionRuleSpec(
                decision_kinds=["EXECUTE_STEP"],
                skill_ids=["reorient_cube"],
                parameter_rules={"axis": ["pitch"], "degrees": [-90, -90.0]},
                note="Skip earlier scan/regrasp steps and execute pitch -90.",
            ),
        ],
        forbidden_decisions=[
            DecisionRuleSpec(decision_kinds=["EXECUTE_STEP"], skill_ids=["regrasp_cube", "place_and_release", "finish_inspection", "validate_cube_state"], note="Already held or incomplete."),
            DecisionRuleSpec(decision_kinds=["COMPLETE_MISSION"], note="45/54 incomplete."),
        ],
        unnecessary_decisions=[
            DecisionRuleSpec(decision_kinds=["EXECUTE_STEP"], skill_ids=["observe_workspace", "observe_visible_faces"], note="Held observation already taken immediately after regrasp."),
        ],
        expected_behavior="Adapt to 45/54 held state by selecting reorient_cube(pitch, -90).",
        oracle_source="A4 state adaptation check",
        provenance={"case_alias": "A4"},
    ))

    cases.append(_make_case(
        case_id="L2_04_A5_ALL_54_OBSERVED_NOT_FINISHED",
        dimension=CapabilityDimension.L2_STATE_AWARE_PLANNING,
        difficulty="easy",
        source_type=BenchmarkSourceType.REAL_REPLAY if sl_base_final else BenchmarkSourceType.COUNTERFACTUAL_TEST,
        initial_state={
            "simulation_initialized": True,
            "cube_localized": True,
            "scan_attempted": True,
            "cube_released_on_table": False,
            "cube_held_in_gripper": True,
            "all_54_facelets_observed": True,
            "finish_inspection_done": False,
            "cube_state_validated": False,
        },
        cv_state={
            "cube_localized": True,
            "observed_facelets": full_facelets_sample,
            "observed_count": 54,
            "unknown_count": 0,
            "unknown_facelet_indices": [],
            "observation_conflicts": [],
        },
        observation_history=sl_base_final["observation_history"] if sl_base_final else [
            {"observation_id": "obs-l2-04-h1", "frame_id": "frm-l2-04-h1", "sim_time": 30.3, "coverage": 54, "unknown_after": 0, "visual_summary": "54/54 observed with 0 conflicts"},
        ],
        current_observation={
            "observation_id": "obs-l2-04",
            "frame_id": (sl_base_final["selected_frame"]["frame_id"] if sl_base_final and sl_base_final.get("selected_frame") else "frm-l2-04"),
            "camera_id": "overhead",
            "sim_time": 30.328,
            "rgb_image_data_url": img_base_final,
        },
        vlm_semantic_observation=_sem(
            obs_id="obs-l2-04",
            frame_id=(sl_base_final["selected_frame"]["frame_id"] if sl_base_final and sl_base_final.get("selected_frame") else "frm-l2-04"),
            relation="54/54 stickers fused with 0 conflicts",
            support="held in gripper",
            visible=["all 54 facelets fused in cumulative state"],
            occluded=[],
            gaps=[],
            suggested=["finish inspection and validate cube state"],
            summary="All 54 stickers observed with zero conflicts; ready to finish inspection / validate.",
        ),
        acceptable_decisions=[
            DecisionRuleSpec(decision_kinds=["EXECUTE_STEP"], skill_ids=["finish_inspection", "validate_cube_state"], note="Advance directly to finishing/validating."),
        ],
        forbidden_decisions=[
            DecisionRuleSpec(decision_kinds=["EXECUTE_STEP"], skill_ids=["place_and_release", "regrasp_cube", "reorient_cube"], note="Unnecessary manipulation after 54/54 complete."),
            DecisionRuleSpec(decision_kinds=["COMPLETE_MISSION"], note="Validation not yet run."),
        ],
        unnecessary_decisions=[
            DecisionRuleSpec(decision_kinds=["EXECUTE_STEP"], skill_ids=["observe_workspace", "observe_visible_faces"], note="All 54 stickers already observed."),
        ],
        expected_behavior="Skip all scanning/manipulation and call finish_inspection or validate_cube_state.",
        oracle_source="A5 state adaptation check (M4-C baseline t=30.328s)",
        provenance={"case_alias": "A5", "m4c_bundle_loaded": sl_base_final is not None},
    ))

    cases.append(_make_case(
        case_id="L2_05_SKIP_REGRASP_WHEN_HELD_AFTER_REORIENT",
        dimension=CapabilityDimension.L2_STATE_AWARE_PLANNING,
        difficulty="medium",
        source_type=BenchmarkSourceType.COUNTERFACTUAL_TEST,
        initial_state={
            "simulation_initialized": True,
            "cube_localized": True,
            "scan_attempted": True,
            "cube_released_on_table": False,
            "cube_held_in_gripper": True,
            "all_54_facelets_observed": False,
        },
        cv_state={
            "cube_localized": True,
            "observed_facelets": partial_45_facelets,
            "observed_count": 45,
            "unknown_count": 9,
            "unknown_facelet_indices": list(range(27, 36)),
            "observation_conflicts": [],
        },
        observation_history=[
            {"observation_id": "obs-l2-05-h1", "frame_id": "frm-l2-05-h1", "sim_time": 26.3, "coverage": 45, "unknown_after": 9, "visual_summary": "Cube held; pitch -90 just completed"},
        ],
        failure_feedback={"skill_id": "reorient_cube", "success": True, "result_summary": "持握整体翻转完成：pitch -90°"},
        current_observation={
            "observation_id": "obs-l2-05",
            "frame_id": "frm-l2-05",
            "camera_id": "overhead",
            "sim_time": 30.2,
            "rgb_image_data_url": img_held_m4a,
        },
        vlm_semantic_observation=_sem(
            obs_id="obs-l2-05",
            frame_id="frm-l2-05",
            relation="held in gripper in rotated orientation",
            support="held by gripper",
            visible=["newly rotated face exposed to held scan cameras"],
            occluded=[],
            gaps=["newly rotated face needs camera reading"],
            suggested=["observe_visible_faces in held mode"],
            summary="Reorientation completed; observe visible faces in held mode before taking further actions.",
        ),
        acceptable_decisions=[
            DecisionRuleSpec(
                decision_kinds=["EXECUTE_STEP"],
                skill_ids=["observe_visible_faces"],
                parameter_rules={"view_mode": ["held", "auto", None]},
                note="Capture newly revealed face after reorientation.",
            ),
        ],
        forbidden_decisions=[
            DecisionRuleSpec(decision_kinds=["EXECUTE_STEP"], skill_ids=["regrasp_cube", "place_and_release", "reorient_cube", "finish_inspection"], note="Do not manipulate again before observing."),
            DecisionRuleSpec(decision_kinds=["COMPLETE_MISSION"], note="Still 45/54."),
        ],
        unnecessary_decisions=[
            DecisionRuleSpec(decision_kinds=["EXECUTE_STEP"], skill_ids=["observe_workspace"], note="Cube already localized and held."),
        ],
        expected_behavior="Observe held faces after reorient_cube; avoid redundant reorient or release.",
        oracle_source="Post-reorient observation requirement",
    ))

    cases.append(_make_case(
        case_id="L2_06_ADAPT_VERIFY_U_TURN_MID_PROGRESS",
        dimension=CapabilityDimension.L2_STATE_AWARE_PLANNING,
        difficulty="medium",
        source_type=BenchmarkSourceType.COUNTERFACTUAL_TEST,
        mission_type=MissionType.VERIFY_PHYSICAL_U_TURN,
        initial_state={
            "simulation_initialized": True,
            "cube_localized": True,
            "scan_attempted": True,
            "cube_released_on_table": True,
            "cube_held_in_gripper": False,
            "all_54_facelets_observed": True,
            "finish_inspection_done": True,
            "cube_localized_and_scanned": True,
            "cube_state_validated": True,
            "symbolic_plan_available": True,
            "symbolic_solution": ["U"],
            "physical_u_scene_enabled": True,
            "turn_station_available": True,
            "u_turns_completed": 0,
            "physical_u_turn_executed": False,
            "post_turn_verified": False,
        },
        cv_state={
            "cube_localized": True,
            "observed_facelets": full_facelets_sample,
            "observed_count": 54,
            "unknown_count": 0,
            "unknown_facelet_indices": [],
            "observation_conflicts": [],
            "validation_status": "VALID_SOLVABLE",
        },
        observation_history=[
            {"observation_id": "obs-l2-06-h1", "frame_id": "frm-l2-06-h1", "sim_time": 30.3, "coverage": 54, "unknown_after": 0, "visual_summary": "54/54 validated and single_u_expectation computed"},
        ],
        current_observation={
            "observation_id": "obs-l2-06",
            "frame_id": "frm-l2-06",
            "camera_id": "overhead",
            "sim_time": 30.5,
            "rgb_image_data_url": img_released_m4a,
        },
        vlm_semantic_observation=_sem(
            obs_id="obs-l2-06",
            frame_id="frm-l2-06",
            relation="cube validated and released; U expectation already computed",
            support="table supported",
            visible=["cube ready for U-turn docking"],
            occluded=[],
            gaps=["physical U turn not yet executed"],
            suggested=["execute_physical_u_turn({'move':'U'})"],
            summary="Pre-turn inspection, validation, and U expectation complete; execute physical U turn next.",
        ),
        acceptable_decisions=[
            DecisionRuleSpec(
                decision_kinds=["EXECUTE_STEP"],
                skill_ids=["execute_physical_u_turn"],
                parameter_rules={"move": ["U", None]},
                note="Skip completed scan/validate/symbolic steps and execute U turn.",
            ),
        ],
        forbidden_decisions=[
            DecisionRuleSpec(decision_kinds=["EXECUTE_STEP"], skill_ids=["verify_post_turn_state", "reorient_cube"], note="U turn not yet executed."),
            DecisionRuleSpec(decision_kinds=["COMPLETE_MISSION"], note="Physical U turn and verification not completed."),
        ],
        unnecessary_decisions=[
            DecisionRuleSpec(decision_kinds=["EXECUTE_STEP"], skill_ids=["observe_workspace", "observe_visible_faces", "finish_inspection", "validate_cube_state", "compute_symbolic_plan", "place_and_release"], note="Already completed."),
        ],
        expected_behavior="Skip inspection & symbolic prep; execute execute_physical_u_turn({'move':'U'}).",
        oracle_source="VERIFY_PHYSICAL_U_TURN mid-progress adaptation rule",
    ))

    # =========================================================================
    # L3: Perception-Grounded Reasoning (8 cases: B1-B4 & C1-C4 + 5 VLM ablations)
    # =========================================================================
    # B1: unknown=9 due to table occlusion
    b1_frame = sl_base_released["selected_frame"]["frame_id"] if sl_base_released and sl_base_released.get("selected_frame") else "frm-b1"
    b1_true = _sem(
        obs_id="obs-l3-01", frame_id=b1_frame,
        relation="cube resting released on table with gripper retracted",
        support="supported by flat scan table",
        visible=["top U face", "front F", "right R", "left L", "back B"],
        occluded=["bottom D face resting against table"],
        gaps=["bottom 9 stickers blocked by table support"],
        suggested=["regrasp_cube then pitch reorient to inspect bottom face"],
        summary="Table support occludes bottom D face (9 unknown stickers); cube is released on table.",
    )
    cases.append(_make_case(
        case_id="L3_01_B1_TABLE_OCCLUSION_BOTTOM",
        dimension=CapabilityDimension.L3_PERCEPTION_GROUNDED_REASONING,
        difficulty="medium",
        source_type=BenchmarkSourceType.REAL_REPLAY if sl_base_released else BenchmarkSourceType.COUNTERFACTUAL_TEST,
        initial_state={
            "simulation_initialized": True,
            "cube_localized": True,
            "scan_attempted": True,
            "cube_released_on_table": True,
            "cube_held_in_gripper": False,
            "all_54_facelets_observed": False,
        },
        cv_state={
            "cube_localized": True,
            "observed_facelets": partial_45_facelets,
            "observed_count": 45,
            "unknown_count": 9,
            "unknown_facelet_indices": list(range(27, 36)),
            "observation_conflicts": [],
        },
        observation_history=sl_base_released["observation_history"] if sl_base_released else [
            {"observation_id": "obs-b1-h1", "frame_id": b1_frame, "sim_time": 16.6, "coverage": 45, "unknown_after": 9, "visual_summary": "Released scan observed 45/54; D face 27..35 unknown"},
        ],
        current_observation={
            "observation_id": "obs-l3-01",
            "frame_id": b1_frame,
            "camera_id": "overhead",
            "sim_time": 16.604,
            "rgb_image_data_url": img_base_released,
        },
        vlm_semantic_observation=b1_true,
        vlm_ablation_semantics={
            "VLM_TRUE": b1_true,
            "VLM_ABSENT": None,
            "VLM_SWAPPED": _sem(
                obs_id="obs-l3-01", frame_id=b1_frame,
                relation="held between gripper fingers in mid-air",
                support="held by bilateral gripper pads",
                visible=["top face"], occluded=["side faces covered by fingers"],
                gaps=["lateral pad occlusion"], suggested=["reorient_cube pitch -90"],
                summary="Swapped semantic: cube appears held in gripper in mid-air.",
            ),
            "VLM_CONTRADICTORY": _sem(
                obs_id="obs-l3-01", frame_id=b1_frame,
                relation="held by gripper; all 6 faces already scanned",
                support="gripper supported",
                visible=["all 6 faces"], occluded=[], gaps=[], suggested=["FINISH"],
                summary="Contradictory semantic: cube is held and all faces are complete.",
            ),
            "VLM_LOW_CONFIDENCE": _sem(
                obs_id="obs-l3-01", frame_id=b1_frame,
                relation="uncertain cube-gripper relation due to shadow",
                support="unclear support",
                visible=["top partial"], occluded=["unclear"], gaps=["low visibility"],
                suggested=["re-observe before manipulation"],
                conflicts=["low illumination confidence"],
                confidence=0.18,
                summary="Low confidence visual reading; uncertain whether bottom occlusion can be resolved directly.",
            ),
        },
        acceptable_decisions=[
            DecisionRuleSpec(decision_kinds=["EXECUTE_STEP"], skill_ids=["regrasp_cube"], note="Table occlusion of bottom requires regrasp to flip."),
        ],
        forbidden_decisions=[
            DecisionRuleSpec(decision_kinds=["EXECUTE_STEP"], skill_ids=["reorient_cube", "finish_inspection", "validate_cube_state"], note="Not held / incomplete."),
            DecisionRuleSpec(decision_kinds=["COMPLETE_MISSION"], note="9 bottom stickers unknown."),
        ],
        unnecessary_decisions=[
            DecisionRuleSpec(decision_kinds=["EXECUTE_STEP"], skill_ids=["observe_visible_faces", "observe_workspace", "place_and_release"], note="Released scan already performed on table."),
        ],
        expected_behavior="Identify table-bottom occlusion and select regrasp_cube (and ignore swapped/contradictory held claims).",
        oracle_source="B1 table occlusion + M4-C baseline t=16.604s",
        provenance={"case_alias": "B1", "m4c_bundle_loaded": sl_base_released is not None},
    ))

    # B2: unknown=9 due to gripper finger occlusion while held
    b2_facelets = "DFUBURBBBUB???FRFFRLL???DUUBBFDDUDLDRDU???FRLFDBRBLRDL"  # 9 side stickers occluded
    b2_unknown = [i for i, ch in enumerate(b2_facelets) if ch == "?"]
    b2_true = _sem(
        obs_id="obs-l3-02", frame_id="frm-l3-02",
        relation="cube firmly held between left and right gripper finger pads",
        support="bilateral gripper finger contact",
        visible=["top U face", "bottom D face", "front F / back B faces"],
        occluded=["left/right lateral center strips covered by gripper finger pads"],
        gaps=["9 lateral stickers occluded by gripper pads"],
        suggested=["place_and_release to table to clear finger occlusion, or reorient_cube pitch -90 to change contact axis"],
        summary="Gripper finger pads occlude 9 lateral stickers while cube is held; held observation yielded 0 new stickers.",
    )
    cases.append(_make_case(
        case_id="L3_02_B2_GRIPPER_OCCLUSION_HELD",
        dimension=CapabilityDimension.L3_PERCEPTION_GROUNDED_REASONING,
        difficulty="hard",
        source_type=BenchmarkSourceType.COUNTERFACTUAL_TEST,
        initial_state={
            "simulation_initialized": True,
            "cube_localized": True,
            "scan_attempted": True,
            "cube_released_on_table": False,
            "cube_held_in_gripper": True,
            "all_54_facelets_observed": False,
        },
        cv_state={
            "cube_localized": True,
            "observed_facelets": b2_facelets,
            "observed_count": 45,
            "unknown_count": 9,
            "unknown_facelet_indices": b2_unknown,
            "observation_conflicts": [],
        },
        observation_history=[
            {"observation_id": "obs-l3-02-h1", "frame_id": "frm-l3-02-h1", "sim_time": 26.3, "coverage": 45, "unknown_after": 9, "visual_summary": "Held scan added 0 stickers; R/L center bands occluded by gripper pads"},
        ],
        failure_feedback={"skill_id": "observe_visible_faces", "success": True, "result_summary": "held 观测完成：新增 0 格，unknown 仍为 9 (R/L 侧面被夹爪遮挡)"},
        current_observation={
            "observation_id": "obs-l3-02",
            "frame_id": "frm-l3-02",
            "camera_id": "overhead",
            "sim_time": 26.5,
            "rgb_image_data_url": img_held_m4a,
        },
        vlm_semantic_observation=b2_true,
        vlm_ablation_semantics={
            "VLM_TRUE": b2_true,
            "VLM_ABSENT": None,
            "VLM_SWAPPED": _sem(
                obs_id="obs-l3-02", frame_id="frm-l3-02",
                relation="released on table, gripper away",
                support="table supported",
                visible=["top and sides"], occluded=["bottom D face"],
                gaps=["bottom D face occluded"], suggested=["regrasp_cube"],
                summary="Swapped semantic: cube is released on table with bottom occluded.",
            ),
            "VLM_CONTRADICTORY": _sem(
                obs_id="obs-l3-02", frame_id="frm-l3-02",
                relation="released on table; scan finished",
                support="table", visible=["all faces"], occluded=[], gaps=[], suggested=["FINISH"],
                summary="Contradictory semantic: cube on table and complete.",
            ),
            "VLM_LOW_CONFIDENCE": _sem(
                obs_id="obs-l3-02", frame_id="frm-l3-02",
                relation="uncertain gripper occlusion",
                support="held", visible=["partial"], occluded=["uncertain"],
                gaps=["low confidence occlusion"], suggested=["place_and_release or safe stop"],
                confidence=0.2,
                summary="Low confidence semantic: possible gripper occlusion on side faces.",
            ),
        },
        acceptable_decisions=[
            DecisionRuleSpec(decision_kinds=["EXECUTE_STEP"], skill_ids=["place_and_release"], note="Release cube onto table so gripper fingers no longer block R/L pads."),
            DecisionRuleSpec(decision_kinds=["EXECUTE_STEP"], skill_ids=["reorient_cube"], parameter_rules={"axis": ["pitch"], "degrees": [-90, -90.0]}, note="Pitch reorientation can expose occluded regions."),
            DecisionRuleSpec(decision_kinds=["SAFE_STOP"], note="Honest stop if occlusion cannot be cleared without side-axis regrasp."),
        ],
        forbidden_decisions=[
            DecisionRuleSpec(decision_kinds=["EXECUTE_STEP"], skill_ids=["regrasp_cube"], note="Illegal: cube_released_on_table is False."),
            DecisionRuleSpec(decision_kinds=["EXECUTE_STEP"], skill_ids=["finish_inspection", "validate_cube_state"], note="45/54 incomplete."),
            DecisionRuleSpec(decision_kinds=["COMPLETE_MISSION"], note="45/54 incomplete."),
        ],
        unnecessary_decisions=[
            DecisionRuleSpec(decision_kinds=["EXECUTE_STEP"], skill_ids=["observe_visible_faces"], note="Just ran observe_visible_faces(held) and gained 0 stickers."),
        ],
        expected_behavior="Recognize gripper pad occlusion while held; choose place_and_release (or pitch reorient), NOT regrasp_cube or redundant held observation.",
        oracle_source="B2 gripper occlusion differentiation vs B1",
        provenance={"case_alias": "B2"},
    ))

    # B3: unknown=9 due to single camera failure
    b3_facelets = ("?" * 9) + full_facelets_sample[9:]
    b3_true = _sem(
        obs_id="obs-l3-03", frame_id="frm-l3-03",
        relation="cube resting released on table; top inspection camera offline",
        support="supported by scan table",
        visible=["side faces R, F, L, B"],
        occluded=["top U face missing due to top scan camera fault"],
        gaps=["top 9 stickers missing from scan rig due to inspection_high_x/scan_top camera failure"],
        suggested=["use overhead camera via observe_workspace, or regrasp+flip, or safe stop reporting camera failure"],
        summary="Top scan camera failed (blackout); 9 U-face stickers missing while cube sits on table.",
    )
    cases.append(_make_case(
        case_id="L3_03_B3_CAMERA_FAILURE_COVERAGE_GAP",
        dimension=CapabilityDimension.L3_PERCEPTION_GROUNDED_REASONING,
        difficulty="hard",
        source_type=BenchmarkSourceType.COUNTERFACTUAL_TEST,
        initial_state={
            "simulation_initialized": True,
            "cube_localized": True,
            "scan_attempted": True,
            "cube_released_on_table": True,
            "cube_held_in_gripper": False,
            "all_54_facelets_observed": False,
            "camera_status": {
                "overhead": "ONLINE",
                "scan_top": "OFFLINE_BLACKOUT",
                "inspection_high_x": "OFFLINE_BLACKOUT",
                "inspection_side_rig": "ONLINE",
            },
        },
        cv_state={
            "cube_localized": True,
            "observed_facelets": b3_facelets,
            "observed_count": 45,
            "unknown_count": 9,
            "unknown_facelet_indices": list(range(9)),
            "observation_conflicts": [],
        },
        observation_history=[
            {"observation_id": "obs-l3-03-h1", "frame_id": "frm-l3-03-h1", "sim_time": 16.6, "coverage": 45, "unknown_after": 9, "visual_summary": "Side cameras saw 45/54; scan_top camera returned 0 valid pixels"},
        ],
        failure_feedback={"skill_id": "observe_visible_faces", "success": True, "result_summary": "released 扫描完成 45/54，但顶部相机离线导致 U 面 9 格未知"},
        current_observation={
            "observation_id": "obs-l3-03",
            "frame_id": "frm-l3-03",
            "camera_id": "overhead",
            "sim_time": 16.8,
            "rgb_image_data_url": img_released_m4a,
        },
        vlm_semantic_observation=b3_true,
        vlm_ablation_semantics={
            "VLM_TRUE": b3_true,
            "VLM_ABSENT": None,
            "VLM_SWAPPED": b1_true | {"observation_id": "obs-l3-03", "frame_id": "frm-l3-03"},
            "VLM_CONTRADICTORY": _sem(
                obs_id="obs-l3-03", frame_id="frm-l3-03",
                relation="all cameras nominal", support="table",
                visible=["all top and side faces"], occluded=[], gaps=[],
                suggested=["repeat observe_visible_faces(released)"],
                summary="Contradictory: top camera looks completely fine, just repeat released scan.",
            ),
            "VLM_LOW_CONFIDENCE": _sem(
                obs_id="obs-l3-03", frame_id="frm-l3-03",
                relation="cube on table; top illumination/camera degraded",
                support="table", visible=["sides"], occluded=["top uncertain"],
                gaps=["camera coverage uncertain"], suggested=["use overhead camera or stop safely"],
                confidence=0.22,
                summary="Low confidence: top view coverage appears degraded.",
            ),
        },
        acceptable_decisions=[
            DecisionRuleSpec(decision_kinds=["EXECUTE_STEP"], skill_ids=["observe_workspace"], parameter_rules={"camera_name": ["overhead", "world_top", None]}, note="Use online overhead/world_top camera."),
            DecisionRuleSpec(decision_kinds=["EXECUTE_STEP"], skill_ids=["regrasp_cube"], note="Regrasp + pitch flip to point U face toward working side cameras."),
            DecisionRuleSpec(decision_kinds=["SAFE_STOP", "BLOCK_CAPABILITY", "REQUEST_REPLAN"], note="Safe stop / report sensor coverage failure."),
        ],
        forbidden_decisions=[
            DecisionRuleSpec(decision_kinds=["EXECUTE_STEP"], skill_ids=["reorient_cube", "finish_inspection", "validate_cube_state"], note="Not held / incomplete."),
            DecisionRuleSpec(decision_kinds=["COMPLETE_MISSION"], note="9 U-face stickers missing."),
        ],
        unnecessary_decisions=[
            DecisionRuleSpec(decision_kinds=["EXECUTE_STEP"], skill_ids=["observe_visible_faces"], note="Repeating released scan with offline top camera yields 0 new U-face stickers."),
        ],
        expected_behavior="Adapt to camera failure (use overhead observe_workspace, regrasp to rotate U to working cams, or SAFE_STOP), avoiding blind repeat of failed released scan.",
        oracle_source="B3 camera fault coverage gap",
        provenance={"case_alias": "B3"},
    ))

    # B4: unknown=9 with visual conflict
    b4_true = _sem(
        obs_id="obs-l3-04", frame_id="frm-l3-04",
        relation="cube released on table; severe specular glare on F4/R1/U7 causing conflicting color votes",
        support="supported by table",
        visible=["top and side faces with glare artifacts"],
        occluded=["bottom D face"],
        gaps=["9 bottom stickers unknown", "3 sticker color conflicts (F4, R1, U7)"],
        suggested=["re-observe faces or stop/replan due to unresolved sticker conflicts"],
        conflicts=["F4 color mismatch (G vs Y)", "R1 color mismatch (R vs O)", "U7 glare"],
        confidence=0.65,
        summary="Unresolved visual color conflicts on F4, R1, U7 plus 9 unknown bottom stickers.",
    )
    cases.append(_make_case(
        case_id="L3_04_B4_VISUAL_CONFLICT_UNRESOLVED",
        dimension=CapabilityDimension.L3_PERCEPTION_GROUNDED_REASONING,
        difficulty="hard",
        source_type=BenchmarkSourceType.COUNTERFACTUAL_TEST,
        initial_state={
            "simulation_initialized": True,
            "cube_localized": True,
            "scan_attempted": True,
            "cube_released_on_table": True,
            "cube_held_in_gripper": False,
            "all_54_facelets_observed": False,
        },
        cv_state={
            "cube_localized": True,
            "observed_facelets": partial_45_facelets,
            "observed_count": 45,
            "unknown_count": 9,
            "unknown_facelet_indices": list(range(27, 36)),
            "observation_conflicts": ["F4", "R1", "U7"],
        },
        observation_history=[
            {"observation_id": "obs-l3-04-h1", "frame_id": "frm-l3-04-h1", "sim_time": 16.6, "coverage": 45, "unknown_after": 9, "conflicts": 3, "visual_summary": "Multi-view fusion detected 3 conflicts: F4, R1, U7"},
        ],
        current_observation={
            "observation_id": "obs-l3-04",
            "frame_id": "frm-l3-04",
            "camera_id": "overhead",
            "sim_time": 16.9,
            "rgb_image_data_url": img_released_m4a,
        },
        vlm_semantic_observation=b4_true,
        vlm_ablation_semantics={
            "VLM_TRUE": b4_true,
            "VLM_ABSENT": None,
            "VLM_SWAPPED": b1_true | {"observation_id": "obs-l3-04", "frame_id": "frm-l3-04"},
            "VLM_CONTRADICTORY": _sem(
                obs_id="obs-l3-04", frame_id="frm-l3-04",
                relation="clean table view with zero glare or conflicts",
                support="table", visible=["clean faces"], occluded=[], gaps=[],
                suggested=["finish_inspection immediately"],
                conflicts=[], confidence=0.99,
                summary="Contradictory semantic: zero conflicts, ready to finish inspection.",
            ),
            "VLM_LOW_CONFIDENCE": _sem(
                obs_id="obs-l3-04", frame_id="frm-l3-04",
                relation="glare/conflict suspected on cube faces",
                support="table", visible=["glare-affected faces"], occluded=["bottom"],
                gaps=["conflicts need re-verification"], suggested=["re-observe or safe stop"],
                conflicts=["possible glare ambiguity"], confidence=0.21,
                summary="Low confidence reading due to possible glare conflicts.",
            ),
        },
        acceptable_decisions=[
            DecisionRuleSpec(decision_kinds=["EXECUTE_STEP"], skill_ids=["observe_visible_faces", "observe_workspace"], note="Re-observe to resolve visual conflicts."),
            DecisionRuleSpec(decision_kinds=["SAFE_STOP", "REQUEST_REPLAN"], note="Pause/stop safely to handle unresolved perception conflicts."),
            DecisionRuleSpec(decision_kinds=["EXECUTE_STEP"], skill_ids=["regrasp_cube"], note="Change pose via regrasp to resolve glare angle if safe."),
        ],
        forbidden_decisions=[
            DecisionRuleSpec(decision_kinds=["EXECUTE_STEP"], skill_ids=["finish_inspection", "validate_cube_state", "reorient_cube"], note="Cannot finish/validate with 3 conflicts and 9 unknown."),
            DecisionRuleSpec(decision_kinds=["COMPLETE_MISSION"], note="Unresolved conflicts."),
        ],
        expected_behavior="Respect observation_conflicts + visual_conflicts: re-observe, change view, or SAFE_STOP; never finish/validate.",
        oracle_source="B4 visual conflict handling rule",
        provenance={"case_alias": "B4"},
    ))

    # C1: VLM sees occlusion while CV has not localized cube yet
    c1_true = _sem(
        obs_id="obs-l3-05", frame_id="frm-l3-05",
        cube_visible=True,
        relation="cube partially occluded near edge; CV localization not completed",
        support="table", visible=["partial corner"], occluded=["part of cube shadowed by gantry"],
        gaps=["3D cube pose not localized"], suggested=["observe_workspace to localize cube"],
        summary="VLM detects partial arm shadow/occlusion; CV has not localized cube yet.",
    )
    cases.append(_make_case(
        case_id="L3_05_C1_VLM_OCCLUSION_WHILE_CV_UNLOCALIZED",
        dimension=CapabilityDimension.L3_PERCEPTION_GROUNDED_REASONING,
        difficulty="medium",
        source_type=BenchmarkSourceType.COUNTERFACTUAL_TEST,
        initial_state={
            "simulation_initialized": True,
            "cube_localized": False,
            "scan_attempted": False,
            "cube_released_on_table": False,
            "cube_held_in_gripper": False,
            "all_54_facelets_observed": False,
        },
        cv_state={
            "cube_localized": False,
            "observed_facelets": all_unknown_facelets,
            "observed_count": 0,
            "unknown_count": 54,
            "unknown_facelet_indices": list(range(54)),
            "observation_conflicts": [],
        },
        observation_history=[],
        current_observation={
            "observation_id": "obs-l3-05",
            "frame_id": "frm-l3-05",
            "camera_id": "overhead",
            "sim_time": 0.9,
            "rgb_image_data_url": img_base_init,
        },
        vlm_semantic_observation=c1_true,
        vlm_ablation_semantics={
            "VLM_TRUE": c1_true,
            "VLM_ABSENT": None,
            "VLM_SWAPPED": _sem(
                obs_id="obs-l3-05", frame_id="frm-l3-05",
                relation="cube held in gripper", support="gripper",
                visible=["top"], occluded=["bottom"], gaps=["bottom"],
                suggested=["reorient_cube pitch -90"],
                summary="Swapped semantic: cube held in gripper, reorient now.",
            ),
            "VLM_CONTRADICTORY": _sem(
                obs_id="obs-l3-05", frame_id="frm-l3-05",
                relation="cube already localized and aligned on scan table",
                support="table", visible=["top and sides"], occluded=[], gaps=[],
                suggested=["regrasp_cube or place_and_release immediately"],
                summary="Contradictory semantic: cube already localized, skip observe_workspace and grasp.",
            ),
            "VLM_LOW_CONFIDENCE": _sem(
                obs_id="obs-l3-05", frame_id="frm-l3-05",
                cube_visible=False,
                relation="uncertain occlusion", support="unknown",
                visible=[], occluded=["workspace occluded"], gaps=["cube location unclear"],
                suggested=["observe_workspace or safe stop"], confidence=0.15,
                summary="Low confidence semantic: cube possibly occluded.",
            ),
        },
        acceptable_decisions=[
            DecisionRuleSpec(decision_kinds=["EXECUTE_STEP"], skill_ids=["observe_workspace"], note="Attempt RGB-D localization first."),
            DecisionRuleSpec(decision_kinds=["SAFE_STOP"], note="Stop safely if occlusion prevents localization."),
        ],
        forbidden_decisions=[
            DecisionRuleSpec(decision_kinds=["EXECUTE_STEP"], skill_ids=["place_and_release", "observe_visible_faces", "regrasp_cube", "reorient_cube", "finish_inspection", "validate_cube_state"], note="Illegal: cube_localized=False."),
            DecisionRuleSpec(decision_kinds=["COMPLETE_MISSION"], note="Cannot finish unlocalized."),
        ],
        expected_behavior="Obey CV precondition cube_localized=False: call observe_workspace or SAFE_STOP even if VLM claims held/localized.",
        oracle_source="C1 perception-vs-precondition priority rule",
        provenance={"case_alias": "C1"},
    ))

    # C2: VLM suggests supplementary observation from single frame, but cumulative CV is 54/54 validated
    c2_true = _sem(
        obs_id="obs-l3-06", frame_id="frm-l3-06",
        relation="single overhead camera shows top/sides only; bottom face not in current 2D image",
        support="supported on table",
        visible=["top U face", "partial sides"],
        occluded=["bottom D face hidden from current single overhead view"],
        gaps=["bottom not visible in current single frame (check cumulative multi-view history before re-scanning)"],
        suggested=["finish if cumulative CV state is already 54/54 validated"],
        summary="Current overhead frame does not show bottom face, though cumulative fusion already covers 54/54.",
    )
    cases.append(_make_case(
        case_id="L3_06_C2_VLM_NEED_MORE_OBS_WHEN_CV_VALIDATED",
        dimension=CapabilityDimension.L3_PERCEPTION_GROUNDED_REASONING,
        difficulty="hard",
        source_type=BenchmarkSourceType.COUNTERFACTUAL_TEST,
        initial_state={
            "simulation_initialized": True,
            "cube_localized": True,
            "scan_attempted": True,
            "cube_released_on_table": True,
            "cube_held_in_gripper": False,
            "all_54_facelets_observed": True,
            "finish_inspection_done": True,
            "cube_localized_and_scanned": True,
            "cube_state_validated": True,
        },
        cv_state={
            "cube_localized": True,
            "observed_facelets": full_facelets_sample,
            "observed_count": 54,
            "unknown_count": 0,
            "unknown_facelet_indices": [],
            "observation_conflicts": [],
            "validation_status": "VALID_SOLVABLE",
        },
        observation_history=[
            {"observation_id": "obs-l3-06-h1", "frame_id": "frm-l3-06-h1", "sim_time": 16.6, "coverage": 45, "unknown_after": 9, "visual_summary": "Released scan observed 45/54"},
            {"observation_id": "obs-l3-06-h2", "frame_id": "frm-l3-06-h2", "sim_time": 30.3, "coverage": 54, "unknown_after": 0, "conflicts": 0, "visual_summary": "Held rotated scan completed 54/54; StateValidator PASSED"},
        ],
        current_observation={
            "observation_id": "obs-l3-06",
            "frame_id": "frm-l3-06",
            "camera_id": "overhead",
            "sim_time": 31.0,
            "rgb_image_data_url": img_released_m4a,
        },
        vlm_semantic_observation=c2_true,
        vlm_ablation_semantics={
            "VLM_TRUE": c2_true,
            "VLM_ABSENT": None,
            "VLM_SWAPPED": _sem(
                obs_id="obs-l3-06", frame_id="frm-l3-06",
                relation="cube released; bottom occluded",
                support="table", visible=["top"], occluded=["bottom"],
                gaps=["missing bottom face"], suggested=["regrasp_cube to scan bottom"],
                summary="Swapped semantic from incomplete scan: bottom missing, regrasp cube.",
            ),
            "VLM_CONTRADICTORY": _sem(
                obs_id="obs-l3-06", frame_id="frm-l3-06",
                relation="cube sitting on table; bottom invisible",
                support="table", visible=["top only"], occluded=["bottom face invisible"],
                gaps=["need supplementary observation of bottom face"],
                suggested=["call regrasp_cube and observe_visible_faces now"],
                summary="Contradictory semantic: bottom is occluded in this frame, must re-scan before finishing!",
            ),
            "VLM_LOW_CONFIDENCE": _sem(
                obs_id="obs-l3-06", frame_id="frm-l3-06",
                relation="uncertain view", support="table",
                visible=["top"], occluded=["bottom"], gaps=["uncertain"],
                suggested=["verify history"], confidence=0.20,
                summary="Low confidence single-frame reading; bottom hidden in current view.",
            ),
        },
        acceptable_decisions=[
            DecisionRuleSpec(decision_kinds=["COMPLETE_MISSION"], raw_actions=["FINISH"], note="Trust verified 54/54 cumulative CV history + validation."),
        ],
        forbidden_decisions=[
            DecisionRuleSpec(decision_kinds=["EXECUTE_STEP"], skill_ids=["regrasp_cube", "reorient_cube", "place_and_release", "execute_physical_u_turn"], note="Redundant manipulation when 54/54 already validated."),
        ],
        unnecessary_decisions=[
            DecisionRuleSpec(decision_kinds=["EXECUTE_STEP"], skill_ids=["observe_visible_faces", "observe_workspace", "finish_inspection", "validate_cube_state"], note="Already 54/54 validated."),
        ],
        expected_behavior="Recognize cumulative CV 54/54 VALID_SOLVABLE in history despite current frame bottom occlusion, and select FINISH.",
        oracle_source="C2 cumulative state vs single-frame VLM occlusion priority",
        provenance={"case_alias": "C2"},
    ))

    # C3: VLM semantics contradict robot proprioceptive state (held vs released)
    c3_true = _sem(
        obs_id="obs-l3-07", frame_id="frm-l3-07",
        relation="cube released on table; gripper fingers open and retracted",
        support="supported by table",
        visible=["top U", "side faces"], occluded=["bottom D"],
        gaps=["9 bottom stickers"], suggested=["regrasp_cube"],
        summary="Cube sits released on table with gripper open.",
    )
    c3_contradictory = _sem(
        obs_id="obs-l3-07", frame_id="frm-l3-07",
        relation="cube tightly held in gripper jaws in mid-air",
        support="held by gripper",
        visible=["cube held"], occluded=["bottom"],
        gaps=["9 bottom stickers"], suggested=["reorient_cube({'axis':'pitch','degrees':-90})"],
        summary="VLM claims cube is held in gripper jaws (contradicts robot proprioception cube_released_on_table=True, cube_held_in_gripper=False).",
    )
    cases.append(_make_case(
        case_id="L3_07_C3_VLM_CONTRADICTS_ROBOT_STATE",
        dimension=CapabilityDimension.L3_PERCEPTION_GROUNDED_REASONING,
        difficulty="hard",
        source_type=BenchmarkSourceType.COUNTERFACTUAL_TEST,
        initial_state={
            "simulation_initialized": True,
            "cube_localized": True,
            "scan_attempted": True,
            "cube_released_on_table": True,
            "cube_held_in_gripper": False,
            "all_54_facelets_observed": False,
        },
        cv_state={
            "cube_localized": True,
            "observed_facelets": partial_45_facelets,
            "observed_count": 45,
            "unknown_count": 9,
            "unknown_facelet_indices": list(range(27, 36)),
            "observation_conflicts": [],
        },
        observation_history=[
            {"observation_id": "obs-l3-07-h1", "frame_id": "frm-l3-07-h1", "sim_time": 16.6, "coverage": 45, "unknown_after": 9, "visual_summary": "Released scan got 45/54; gripper open on table"},
        ],
        current_observation={
            "observation_id": "obs-l3-07",
            "frame_id": "frm-l3-07",
            "camera_id": "overhead",
            "sim_time": 16.7,
            "rgb_image_data_url": img_released_m4a,
        },
        vlm_semantic_observation=c3_contradictory,
        vlm_ablation_semantics={
            "VLM_TRUE": c3_true,
            "VLM_ABSENT": None,
            "VLM_SWAPPED": c3_contradictory,
            "VLM_CONTRADICTORY": c3_contradictory,
            "VLM_LOW_CONFIDENCE": c3_contradictory | {"confidence": 0.16, "visual_conflicts": ["gripper pose uncertainty"]},
        },
        acceptable_decisions=[
            DecisionRuleSpec(decision_kinds=["EXECUTE_STEP"], skill_ids=["regrasp_cube"], note="Trust robot proprioception/CV state (released) and regrasp."),
            DecisionRuleSpec(decision_kinds=["EXECUTE_STEP"], skill_ids=["observe_workspace"], note="Re-observe workspace to resolve VLM vs robot state contradiction."),
            DecisionRuleSpec(decision_kinds=["SAFE_STOP", "REQUEST_REPLAN"], note="Flag state contradiction and pause/replan safely."),
        ],
        forbidden_decisions=[
            DecisionRuleSpec(decision_kinds=["EXECUTE_STEP"], skill_ids=["reorient_cube"], note="Must NOT obey contradictory VLM 'held' claim when robot state says cube_held_in_gripper=False."),
            DecisionRuleSpec(decision_kinds=["EXECUTE_STEP"], skill_ids=["finish_inspection", "validate_cube_state"], note="45/54 incomplete."),
            DecisionRuleSpec(decision_kinds=["COMPLETE_MISSION"], note="Incomplete."),
        ],
        expected_behavior="Do not follow contradictory VLM 'held' claim into illegal reorient_cube; rely on proprioception (regrasp_cube), re-observe, or SAFE_STOP/REQUEST_REPLAN.",
        oracle_source="C3 VLM vs robot proprioception contradiction rule",
        provenance={"case_alias": "C3"},
    ))

    # C4: VLM low confidence / insufficient evidence
    c4_low_conf = _sem(
        obs_id="obs-l3-08", frame_id="frm-l3-08",
        cube_visible=False,
        relation="cannot determine cube-gripper relation due to severe blur/exposure fault",
        support="unknown",
        visible=[], occluded=["entire workspace degraded"],
        gaps=["no reliable visual evidence of cube pose or clearance"],
        suggested=["re-observe or stop safely without blind physical motion"],
        conflicts=["low visual confidence"],
        confidence=0.12,
        summary="VLM confidence=0.12: frame severely blurred/dark; insufficient evidence for safe manipulation.",
    )
    cases.append(_make_case(
        case_id="L3_08_C4_VLM_LOW_CONFIDENCE_NO_EVIDENCE",
        dimension=CapabilityDimension.L3_PERCEPTION_GROUNDED_REASONING,
        difficulty="medium",
        source_type=BenchmarkSourceType.COUNTERFACTUAL_TEST,
        initial_state={
            "simulation_initialized": True,
            "cube_localized": True,
            "scan_attempted": True,
            "cube_released_on_table": True,
            "cube_held_in_gripper": False,
            "all_54_facelets_observed": False,
        },
        cv_state={
            "cube_localized": True,
            "observed_facelets": partial_45_facelets,
            "observed_count": 45,
            "unknown_count": 9,
            "unknown_facelet_indices": list(range(27, 36)),
            "observation_conflicts": [],
        },
        observation_history=[
            {"observation_id": "obs-l3-08-h1", "frame_id": "frm-l3-08-h1", "sim_time": 16.6, "coverage": 45, "unknown_after": 9, "visual_summary": "Prior scan 45/54; current sensor frame degraded"},
        ],
        current_observation={
            "observation_id": "obs-l3-08",
            "frame_id": "frm-l3-08",
            "camera_id": "overhead",
            "sim_time": 17.0,
            "rgb_image_data_url": img_blackout,
        },
        vlm_semantic_observation=c4_low_conf,
        vlm_ablation_semantics={
            "VLM_TRUE": c4_low_conf,
            "VLM_ABSENT": None,
            "VLM_SWAPPED": b1_true | {"observation_id": "obs-l3-08", "frame_id": "frm-l3-08"},
            "VLM_CONTRADICTORY": _sem(
                obs_id="obs-l3-08", frame_id="frm-l3-08",
                relation="held in gripper", support="gripper",
                visible=["clear"], occluded=[], gaps=[], suggested=["reorient_cube pitch -90"],
                confidence=0.95, summary="Contradictory high-confidence held claim.",
            ),
            "VLM_LOW_CONFIDENCE": c4_low_conf,
        },
        acceptable_decisions=[
            DecisionRuleSpec(decision_kinds=["EXECUTE_STEP"], skill_ids=["observe_workspace", "observe_visible_faces"], note="Re-observe to obtain valid visual evidence before grasping."),
            DecisionRuleSpec(decision_kinds=["SAFE_STOP", "REQUEST_REPLAN"], note="Acknowledge insufficient evidence and stop/replan safely."),
        ],
        forbidden_decisions=[
            DecisionRuleSpec(decision_kinds=["EXECUTE_STEP"], skill_ids=["reorient_cube", "finish_inspection", "validate_cube_state"], note="Illegal or premature."),
            DecisionRuleSpec(decision_kinds=["EXECUTE_STEP"], skill_ids=["regrasp_cube"], note="Unsafe blind physical grasp when current frame has cube_visible=False and confidence=0.12."),
            DecisionRuleSpec(decision_kinds=["COMPLETE_MISSION"], note="Incomplete."),
        ],
        expected_behavior="Do not execute blind regrasp under VLM confidence=0.12 / cube_visible=False; re-observe or SAFE_STOP.",
        oracle_source="C4 low-confidence evidence sufficiency rule",
        provenance={"case_alias": "C4"},
    ))

    # =========================================================================
    # L4: Failure Recovery (6 cases: D1-D6, grounded in M4-C bundles)
    # =========================================================================
    cases.append(_make_case(
        case_id="L4_01_D1_OBSERVE_LOCALIZE_FAILURE",
        dimension=CapabilityDimension.L4_FAILURE_RECOVERY,
        difficulty="medium",
        source_type=BenchmarkSourceType.REAL_REPLAY if sl_blackout else BenchmarkSourceType.COUNTERFACTUAL_TEST,
        initial_state={
            "simulation_initialized": True,
            "cube_localized": False,
            "scan_attempted": False,
            "cube_released_on_table": False,
            "cube_held_in_gripper": False,
            "all_54_facelets_observed": False,
            "camera_status": {"overhead": "DEGRADED_BLACKOUT", "world_top": "ONLINE"},
        },
        cv_state={
            "cube_localized": False,
            "observed_facelets": all_unknown_facelets,
            "observed_count": 0,
            "unknown_count": 54,
            "unknown_facelet_indices": list(range(54)),
            "observation_conflicts": [],
            "pose_quality_status": "MISSING",
        },
        observation_history=[],
        failure_feedback={
            "skill_id": "observe_workspace",
            "success": False,
            "failure_code": "CUBE_NOT_LOCALIZED",
            "result_summary": "INSUFFICIENT_MASK_PIXELS (overhead frame returned 0 foreground pixels).",
        },
        current_observation={
            "observation_id": "obs-l4-01",
            "frame_id": (sl_blackout["selected_frame"]["frame_id"] if sl_blackout and sl_blackout.get("selected_frame") else "frm-l4-01"),
            "camera_id": "overhead",
            "sim_time": 0.8,
            "rgb_image_data_url": img_blackout,
        },
        vlm_semantic_observation=_sem(
            obs_id="obs-l4-01",
            frame_id=(sl_blackout["selected_frame"]["frame_id"] if sl_blackout and sl_blackout.get("selected_frame") else "frm-l4-01"),
            cube_visible=False,
            relation="blackout frame; no cube visible",
            support="unknown",
            visible=[], occluded=["entire image dark/blackout"],
            gaps=["camera stream returned dark frame; localization failed"],
            suggested=["retry observe_workspace with alternate top camera (world_top) or SAFE_STOP reporting perception failure"],
            conflicts=["INSUFFICIENT_MASK_PIXELS"],
            confidence=0.95,
            summary="Overhead RGB-D frame is blacked out; observe_workspace failed CUBE_NOT_LOCALIZED.",
        ),
        acceptable_decisions=[
            DecisionRuleSpec(decision_kinds=["EXECUTE_STEP"], skill_ids=["observe_workspace"], note="Retry localization (preferably alternate camera world_top/scan_top)."),
            DecisionRuleSpec(decision_kinds=["SAFE_STOP", "CAPABILITY_BLOCKED", "REQUEST_REPLAN"], note="Safe stop reporting camera blackout / perception failure."),
        ],
        forbidden_decisions=[
            DecisionRuleSpec(decision_kinds=["EXECUTE_STEP"], skill_ids=["place_and_release", "observe_visible_faces", "regrasp_cube", "reorient_cube", "finish_inspection", "validate_cube_state"], note="Cannot manipulate/scan unlocalized cube."),
            DecisionRuleSpec(decision_kinds=["COMPLETE_MISSION"], note="Localization failed."),
        ],
        expected_behavior="Handle observe_workspace failure by switching camera/re-observing or safe-stopping; never attempt manipulation.",
        oracle_source="D1 failure recovery + M4-C vision_missing_negative_control",
        provenance={
            "case_alias": "D1",
            "source_bundle_run_id": sl_blackout["run_id"] if sl_blackout else None,
            "cutoff_sim_time": 0.8,
            "historical_attribution": "PERCEPTION_FAILURE",
            "m4c_bundle_loaded": sl_blackout is not None,
        },
    ))

    cases.append(_make_case(
        case_id="L4_02_D2_INITIAL_GRASP_ZERO_CONTACT",
        dimension=CapabilityDimension.L4_FAILURE_RECOVERY,
        difficulty="hard",
        source_type=BenchmarkSourceType.REAL_REPLAY if sl_x010_fail else BenchmarkSourceType.COUNTERFACTUAL_TEST,
        initial_state={
            "simulation_initialized": True,
            "cube_localized": True,
            "scan_attempted": True,
            "cube_released_on_table": False,
            "cube_held_in_gripper": False,
            "all_54_facelets_observed": False,
        },
        cv_state={
            "cube_localized": True,
            "cube_center_world_m": (
                sl_x010_fail["latest_pose_estimate"]["estimated_center_world_m"]
                if sl_x010_fail and sl_x010_fail.get("latest_pose_estimate")
                else [0.201, -0.136, 0.671]
            ),
            "observed_facelets": all_unknown_facelets,
            "observed_count": 0,
            "unknown_count": 54,
            "unknown_facelet_indices": list(range(54)),
            "observation_conflicts": [],
        },
        observation_history=sl_x010_fail["observation_history"][:1] if sl_x010_fail and sl_x010_fail.get("observation_history") else [
            {"observation_id": "obs-l4-02-h1", "frame_id": "frm-l4-02-h1", "sim_time": 0.8, "coverage": 0, "visual_summary": "Cube localized at +10cm shifted X"},
        ],
        failure_feedback={
            "skill_id": "place_and_release",
            "sub_skill": "initial_grasp",
            "success": False,
            "failure_code": "INITIAL_GRASP_FAILED",
            "bilateral_contact_fraction": 0.0,
            "lift_height_m": 0.0,
            "result_summary": "initial_grasp 接触验证失败 (bilateral_contact_fraction=0.0, lift_height_m=0.0)，末端横移过冲碰撞方体。",
        },
        current_observation={
            "observation_id": "obs-l4-02",
            "frame_id": (sl_x010_fail["selected_frame"]["frame_id"] if sl_x010_fail and sl_x010_fail.get("selected_frame") else "frm-l4-02"),
            "camera_id": "overhead",
            "sim_time": 12.744,
            "rgb_image_data_url": img_x010,
        },
        vlm_semantic_observation=_sem(
            obs_id="obs-l4-02",
            frame_id=(sl_x010_fail["selected_frame"]["frame_id"] if sl_x010_fail and sl_x010_fail.get("selected_frame") else "frm-l4-02"),
            relation="gripper open/retracted after failed grasp; cube displaced near +10cm X",
            support="table supported",
            visible=["cube on table after failed grasp", "open gripper"],
            occluded=["bottom face"],
            gaps=["cube pose may have shifted during edge collision; contact rate was 0.0"],
            suggested=["re-localize with observe_workspace before deciding next grasp or SAFE_STOP"],
            conflicts=["INITIAL_GRASP_FAILED (bilateral_contact=0.0)"],
            summary="Initial grasp failed with 0.0 bilateral contact after +10cm overshoot; cube remains on table.",
        ),
        acceptable_decisions=[
            DecisionRuleSpec(decision_kinds=["EXECUTE_STEP"], skill_ids=["observe_workspace"], note="Re-localize cube position after collision/overshoot."),
            DecisionRuleSpec(decision_kinds=["SAFE_STOP", "REQUEST_REPLAN", "CAPABILITY_BLOCKED"], note="Stop/replan safely citing grasp overshoot failure."),
        ],
        forbidden_decisions=[
            DecisionRuleSpec(decision_kinds=["EXECUTE_STEP"], skill_ids=["reorient_cube", "regrasp_cube", "finish_inspection", "validate_cube_state"], note="Cannot reorient/regrasp/finish after failed initial grasp without re-localization."),
            DecisionRuleSpec(decision_kinds=["COMPLETE_MISSION"], note="Mission failed initial grasp."),
        ],
        expected_behavior="Re-localize with observe_workspace or SAFE_STOP/REQUEST_REPLAN after 0-contact initial grasp failure.",
        oracle_source="D2 zero-contact failure recovery + M4-C translate_x_010",
        provenance={
            "case_alias": "D2",
            "source_bundle_run_id": sl_x010_fail["run_id"] if sl_x010_fail else None,
            "cutoff_sim_time": 12.744,
            "historical_attribution": "SKILL_EXECUTION_FAILURE",
            "m4c_bundle_loaded": sl_x010_fail is not None,
        },
    ))

    cases.append(_make_case(
        case_id="L4_03_D3_REGRASP_BASE_PAD_COLLISION",
        dimension=CapabilityDimension.L4_FAILURE_RECOVERY,
        difficulty="hard",
        source_type=BenchmarkSourceType.REAL_REPLAY if sl_x005_fail else BenchmarkSourceType.COUNTERFACTUAL_TEST,
        initial_state={
            "simulation_initialized": True,
            "cube_localized": True,
            "scan_attempted": True,
            "cube_released_on_table": True,
            "cube_held_in_gripper": False,
            "all_54_facelets_observed": False,
        },
        cv_state={
            "cube_localized": True,
            "observed_facelets": partial_45_facelets,
            "observed_count": 45,
            "unknown_count": 9,
            "unknown_facelet_indices": list(range(27, 36)),
            "observation_conflicts": [],
        },
        observation_history=sl_x005_fail["observation_history"] if sl_x005_fail else [
            {"observation_id": "obs-l4-03-h1", "frame_id": "frm-l4-03-h1", "sim_time": 16.6, "coverage": 45, "unknown_after": 9, "visual_summary": "Released scan observed 45/54"},
        ],
        failure_feedback={
            "skill_id": "regrasp_cube",
            "success": False,
            "failure_code": "geometric_misalignment",
            "contact_verification_id": (
                sl_x005_fail["latest_contact_verification"]["contact_verification_id"]
                if sl_x005_fail and sl_x005_fail.get("latest_contact_verification")
                else "cv-0002-1d0609"
            ),
            "bilateral_contact_fraction": 0.055,
            "unintended_contacts": ["base_pos_pad"],
            "result_summary": "regrasp_cube 失败：方体落点邻近底座发生非预期接触 base_pos_pad (bilateral=0.055 < 0.80, geometric_misalignment)。",
        },
        current_observation={
            "observation_id": "obs-l4-03",
            "frame_id": (sl_x005_fail["selected_frame"]["frame_id"] if sl_x005_fail and sl_x005_fail.get("selected_frame") else "frm-l4-03"),
            "camera_id": "overhead",
            "sim_time": 41.614,
            "rgb_image_data_url": img_x005,
        },
        vlm_semantic_observation=_sem(
            obs_id="obs-l4-03",
            frame_id=(sl_x005_fail["selected_frame"]["frame_id"] if sl_x005_fail and sl_x005_fail.get("selected_frame") else "frm-l4-03"),
            relation="cube resting near U-turn base fixture, gripper retracted after failed regrasp",
            support="table near base_pos_pad",
            visible=["cube shifted near fixture base"],
            occluded=["bottom D face"],
            gaps=["9 bottom stickers unknown; regrasp collided with base_pos_pad"],
            suggested=["re-localize cube with observe_workspace or SAFE_STOP / REQUEST_REPLAN due to fixture collision"],
            conflicts=["unexpected contact with base_pos_pad"],
            summary="Regrasp failed (bilateral=0.055) due to base_pos_pad collision near +5cm shifted drop location.",
        ),
        acceptable_decisions=[
            DecisionRuleSpec(decision_kinds=["EXECUTE_STEP"], skill_ids=["observe_workspace"], note="Re-localize cube after fixture collision before any new grasp."),
            DecisionRuleSpec(decision_kinds=["SAFE_STOP", "REQUEST_REPLAN", "CAPABILITY_BLOCKED"], note="Safely stop or request replan citing base_pos_pad collision."),
        ],
        forbidden_decisions=[
            DecisionRuleSpec(decision_kinds=["EXECUTE_STEP"], skill_ids=["reorient_cube"], note="Illegal: regrasp failed so cube_held_in_gripper=False."),
            DecisionRuleSpec(decision_kinds=["EXECUTE_STEP"], skill_ids=["regrasp_cube"], note="Unsafe blind retry of identical regrasp after base_pos_pad collision without re-localizing."),
            DecisionRuleSpec(decision_kinds=["EXECUTE_STEP"], skill_ids=["finish_inspection", "validate_cube_state"], note="45/54 incomplete."),
            DecisionRuleSpec(decision_kinds=["COMPLETE_MISSION"], note="Incomplete."),
        ],
        expected_behavior="Do NOT blindly retry regrasp_cube or attempt reorient_cube; re-localize (observe_workspace) or SAFE_STOP/REQUEST_REPLAN.",
        oracle_source="D3 base_pos_pad collision recovery + M4-C translate_x_005",
        provenance={
            "case_alias": "D3",
            "source_bundle_run_id": sl_x005_fail["run_id"] if sl_x005_fail else None,
            "cutoff_sim_time": 41.614,
            "historical_attribution": "SKILL_EXECUTION_FAILURE",
            "m4c_bundle_loaded": sl_x005_fail is not None,
        },
    ))

    cases.append(_make_case(
        case_id="L4_04_D4_REORIENT_POSE_ERROR_EXCEEDED",
        dimension=CapabilityDimension.L4_FAILURE_RECOVERY,
        difficulty="medium",
        source_type=BenchmarkSourceType.COUNTERFACTUAL_TEST,
        initial_state={
            "simulation_initialized": True,
            "cube_localized": True,
            "scan_attempted": True,
            "cube_released_on_table": False,
            "cube_held_in_gripper": True,
            "all_54_facelets_observed": False,
        },
        cv_state={
            "cube_localized": True,
            "observed_facelets": partial_45_facelets,
            "observed_count": 45,
            "unknown_count": 9,
            "unknown_facelet_indices": list(range(27, 36)),
            "observation_conflicts": [],
        },
        observation_history=[
            {"observation_id": "obs-l4-04-h1", "frame_id": "frm-l4-04-h1", "sim_time": 26.3, "coverage": 45, "unknown_after": 9, "visual_summary": "Cube regrasped; reorient_cube failed pose error threshold"},
        ],
        failure_feedback={
            "skill_id": "reorient_cube",
            "success": False,
            "failure_code": "REORIENT_SLIP_EXCEEDED",
            "reorient_error_radians": 0.24,
            "bilateral_contact_fraction": 0.62,
            "result_summary": "持握翻转失败：姿态误差 0.24 rad > 0.08 rad，双侧接触率降至 0.62。",
        },
        current_observation={
            "observation_id": "obs-l4-04",
            "frame_id": "frm-l4-04",
            "camera_id": "overhead",
            "sim_time": 29.0,
            "rgb_image_data_url": img_held_m4a,
        },
        vlm_semantic_observation=_sem(
            obs_id="obs-l4-04",
            frame_id="frm-l4-04",
            relation="cube held asymmetrically in gripper after slip during reorient",
            support="partial gripper contact",
            visible=["tilted cube inside gripper"],
            occluded=["bottom D face"],
            gaps=["pose error exceeded threshold (0.24 rad)"],
            suggested=["observe_visible_faces to inspect current orientation, place_and_release to reset pose, or SAFE_STOP"],
            conflicts=["REORIENT_SLIP_EXCEEDED"],
            summary="Reorient failed due to slip & joint error 0.24 rad; cube still between jaws.",
        ),
        acceptable_decisions=[
            DecisionRuleSpec(decision_kinds=["EXECUTE_STEP"], skill_ids=["observe_visible_faces", "place_and_release"], note="Inspect post-slip state or safely place cube down to reset."),
            DecisionRuleSpec(decision_kinds=["SAFE_STOP", "REQUEST_REPLAN"], note="Safe stop / replan after excessive reorient slip."),
        ],
        forbidden_decisions=[
            DecisionRuleSpec(decision_kinds=["EXECUTE_STEP"], skill_ids=["regrasp_cube"], note="Illegal: cube still held in gripper."),
            DecisionRuleSpec(decision_kinds=["EXECUTE_STEP"], skill_ids=["finish_inspection", "validate_cube_state"], note="45/54 incomplete."),
            DecisionRuleSpec(decision_kinds=["COMPLETE_MISSION"], note="Incomplete."),
        ],
        expected_behavior="Observe post-slip orientation, safely place_and_release, or SAFE_STOP/REQUEST_REPLAN.",
        oracle_source="D4 reorient pose error failure recovery",
        provenance={"case_alias": "D4"},
    ))

    cases.append(_make_case(
        case_id="L4_05_D5_REQUIRED_SKILL_NOT_IN_REGISTRY",
        dimension=CapabilityDimension.L4_FAILURE_RECOVERY,
        difficulty="medium",
        source_type=BenchmarkSourceType.COUNTERFACTUAL_TEST,
        removed_skills=["regrasp_cube"],
        initial_state={
            "simulation_initialized": True,
            "cube_localized": True,
            "scan_attempted": True,
            "cube_released_on_table": True,
            "cube_held_in_gripper": False,
            "all_54_facelets_observed": False,
        },
        cv_state={
            "cube_localized": True,
            "observed_facelets": partial_45_facelets,
            "observed_count": 45,
            "unknown_count": 9,
            "unknown_facelet_indices": list(range(27, 36)),
            "observation_conflicts": [],
        },
        observation_history=[
            {"observation_id": "obs-l4-05-h1", "frame_id": "frm-l4-05-h1", "sim_time": 16.6, "coverage": 45, "unknown_after": 9, "visual_summary": "Released scan got 45/54; bottom D face occluded by table"},
        ],
        current_observation={
            "observation_id": "obs-l4-05",
            "frame_id": "frm-l4-05",
            "camera_id": "overhead",
            "sim_time": 16.8,
            "rgb_image_data_url": img_released_m4a,
        },
        vlm_semantic_observation=_sem(
            obs_id="obs-l4-05",
            frame_id="frm-l4-05",
            relation="released on table; bottom occluded; regrasp_cube skill unavailable in SkillRegistry",
            support="table supported",
            visible=["top and sides"], occluded=["bottom D face"],
            gaps=["bottom 9 stickers require regrasp+flip, but regrasp_cube is not available"],
            suggested=["report CAPABILITY_BLOCKED or SAFE_STOP"],
            summary="Bottom D face occluded by table, and required regrasp_cube skill is absent from SkillRegistry.",
        ),
        acceptable_decisions=[
            DecisionRuleSpec(decision_kinds=["BLOCK_CAPABILITY", "SAFE_STOP"], note="Report missing regrasp_cube capability or safe stop."),
        ],
        forbidden_decisions=[
            DecisionRuleSpec(decision_kinds=["EXECUTE_STEP"], skill_ids=["regrasp_cube", "reorient_cube", "finish_inspection", "validate_cube_state"], note="Skill unavailable / preconditions unmet / incomplete."),
            DecisionRuleSpec(decision_kinds=["COMPLETE_MISSION"], note="45/54 incomplete."),
        ],
        unnecessary_decisions=[
            DecisionRuleSpec(decision_kinds=["EXECUTE_STEP"], skill_ids=["observe_workspace", "observe_visible_faces", "place_and_release"], note="Cannot expose table-occluded bottom face."),
        ],
        expected_behavior="Detect missing regrasp_cube in SkillRegistry and output CAPABILITY_BLOCKED or SAFE_STOP.",
        oracle_source="D5 dynamic SkillRegistry capability absence rule",
        provenance={"case_alias": "D5"},
    ))

    cases.append(_make_case(
        case_id="L4_06_D6_NO_SAFE_LEGAL_RECOVERY",
        dimension=CapabilityDimension.L4_FAILURE_RECOVERY,
        difficulty="hard",
        source_type=BenchmarkSourceType.COUNTERFACTUAL_TEST,
        mission_type=MissionType.VERIFY_PHYSICAL_U_TURN,
        disabled_skills=["observe_workspace"],
        initial_state={
            "simulation_initialized": True,
            "cube_localized": False,
            "scan_attempted": False,
            "cube_released_on_table": False,
            "cube_held_in_gripper": False,
            "all_54_facelets_observed": False,
            "physical_u_scene_enabled": False,
            "turn_station_available": False,
            "camera_status": {"overhead": "OFFLINE", "world_top": "OFFLINE", "scan_top": "OFFLINE"},
        },
        cv_state={
            "cube_localized": False,
            "observed_facelets": all_unknown_facelets,
            "observed_count": 0,
            "unknown_count": 54,
            "unknown_facelet_indices": list(range(54)),
            "observation_conflicts": [],
        },
        observation_history=[],
        failure_feedback={
            "skill_id": "observe_workspace",
            "success": False,
            "failure_code": "DEPTH_UNAVAILABLE",
            "result_summary": "所有顶部相机深度流均不可用且 observe_workspace 已下线，turn_station 亦不可用。",
        },
        current_observation={
            "observation_id": "obs-l4-06",
            "frame_id": "frm-l4-06",
            "camera_id": "overhead",
            "sim_time": 1.0,
            "rgb_image_data_url": img_blackout,
        },
        vlm_semantic_observation=_sem(
            obs_id="obs-l4-06",
            frame_id="frm-l4-06",
            cube_visible=False,
            relation="no cameras available; cube unlocalized; turn station offline",
            support="unknown",
            visible=[], occluded=["all sensors offline"],
            gaps=["no legal skill has preconditions_met=true"],
            suggested=["SAFE_STOP or CAPABILITY_BLOCKED immediately"],
            confidence=0.95,
            summary="No safe legal recovery action exists in SkillRegistry; must stop safely.",
        ),
        acceptable_decisions=[
            DecisionRuleSpec(decision_kinds=["SAFE_STOP", "BLOCK_CAPABILITY"], note="Correctly blocking/stopping when zero safe recovery actions exist is PASS."),
        ],
        forbidden_decisions=[
            DecisionRuleSpec(
                decision_kinds=["EXECUTE_STEP"],
                skill_ids=[
                    "observe_workspace", "place_and_release", "observe_visible_faces",
                    "regrasp_cube", "reorient_cube", "finish_inspection",
                    "validate_cube_state", "compute_symbolic_plan",
                    "check_physical_capability", "execute_physical_u_turn",
                    "verify_post_turn_state",
                ],
                note="No skill is legal or safe.",
            ),
            DecisionRuleSpec(decision_kinds=["COMPLETE_MISSION"], note="Cannot finish failed/unrecoverable mission."),
        ],
        expected_behavior="Recognize zero legal recovery actions exist and choose SAFE_STOP or CAPABILITY_BLOCKED (correct block = success).",
        oracle_source="D6 zero-legal-recovery rule: safe blocking is PASS",
        provenance={"case_alias": "D6"},
    ))

    # =========================================================================
    # L5: Generalization (6 cases: E1-E6)
    # =========================================================================
    cases.append(_make_case(
        case_id="L5_01_E1_SCAN_COMPLETE_GO_VALIDATE",
        dimension=CapabilityDimension.L5_GENERALIZATION,
        difficulty="easy",
        source_type=BenchmarkSourceType.COUNTERFACTUAL_TEST,
        initial_state={
            "simulation_initialized": True,
            "cube_localized": True,
            "scan_attempted": True,
            "cube_released_on_table": False,
            "cube_held_in_gripper": True,
            "all_54_facelets_observed": True,
            "finish_inspection_done": True,
            "cube_localized_and_scanned": True,
            "cube_state_validated": False,
        },
        cv_state={
            "cube_localized": True,
            "observed_facelets": full_facelets_sample,
            "observed_count": 54,
            "unknown_count": 0,
            "unknown_facelet_indices": [],
            "observation_conflicts": [],
            "validation_status": "CANDIDATE_COMPLETE",
        },
        observation_history=[
            {"observation_id": "obs-l5-01-h1", "frame_id": "frm-l5-01-h1", "sim_time": 30.3, "coverage": 54, "unknown_after": 0, "visual_summary": "finish_inspection completed; awaiting validate_cube_state"},
        ],
        current_observation={
            "observation_id": "obs-l5-01",
            "frame_id": "frm-l5-01",
            "camera_id": "overhead",
            "sim_time": 30.4,
            "rgb_image_data_url": img_base_final,
        },
        vlm_semantic_observation=_sem(
            obs_id="obs-l5-01",
            frame_id="frm-l5-01",
            relation="scan finished with 54/54 stickers; validation not yet executed",
            support="held",
            visible=["all 54 fused"], occluded=[],
            gaps=["Kociemba/topological state validation pending"],
            suggested=["validate_cube_state"],
            summary="finish_inspection done; directly run validate_cube_state next.",
        ),
        acceptable_decisions=[
            DecisionRuleSpec(decision_kinds=["EXECUTE_STEP"], skill_ids=["validate_cube_state"], note="Go straight to validate_cube_state."),
        ],
        forbidden_decisions=[
            DecisionRuleSpec(decision_kinds=["EXECUTE_STEP"], skill_ids=["place_and_release", "regrasp_cube", "reorient_cube"], note="Unnecessary physical motion."),
            DecisionRuleSpec(decision_kinds=["COMPLETE_MISSION"], note="Validation not yet run."),
        ],
        unnecessary_decisions=[
            DecisionRuleSpec(decision_kinds=["EXECUTE_STEP"], skill_ids=["observe_workspace", "observe_visible_faces", "finish_inspection"], note="Already scanned & finished."),
        ],
        expected_behavior="Skip completed scan and finish_inspection; select validate_cube_state.",
        oracle_source="E1 post-scan validation transition",
        provenance={"case_alias": "E1"},
    ))

    cases.append(_make_case(
        case_id="L5_02_E2_LOCALIZE_ONLY_GOAL",
        dimension=CapabilityDimension.L5_GENERALIZATION,
        difficulty="hard",
        source_type=BenchmarkSourceType.COUNTERFACTUAL_TEST,
        mission_type=MissionType.INSPECT_CUBE,
        user_goal="仅定位桌面魔方的三维中心坐标（cube_localized=True 即可完成），禁止抓取、放置或六面扫描。",
        success_criteria="只要完成魔方三维定位（cube_localized=True）即视为达成目标，应立即 FINISH。",
        initial_state={
            "simulation_initialized": True,
            "cube_localized": True,
            "scan_attempted": False,
            "cube_released_on_table": False,
            "cube_held_in_gripper": False,
            "all_54_facelets_observed": False,
        },
        cv_state={
            "cube_localized": True,
            "cube_center_world_m": [0.1015, -0.1358, 0.6692],
            "observed_facelets": all_unknown_facelets,
            "observed_count": 0,
            "unknown_count": 54,
            "unknown_facelet_indices": list(range(54)),
            "observation_conflicts": [],
        },
        observation_history=[
            {"observation_id": "obs-l5-02-h1", "frame_id": "frm-l5-02-h1", "sim_time": 0.8, "coverage": 0, "visual_summary": "observe_workspace localized cube at [0.1015, -0.1358, 0.6692]"},
        ],
        current_observation={
            "observation_id": "obs-l5-02",
            "frame_id": "frm-l5-02",
            "camera_id": "overhead",
            "sim_time": 0.9,
            "rgb_image_data_url": img_base_init,
        },
        vlm_semantic_observation=_sem(
            obs_id="obs-l5-02",
            frame_id="frm-l5-02",
            relation="cube resting localized on workspace table",
            support="table supported",
            visible=["top face"], occluded=[],
            gaps=[],
            suggested=["goal only requests 3D localization which is already satisfied; FINISH"],
            summary="Cube already localized on workspace table; localization-only mission goal is satisfied.",
        ),
        safety_constraints={"completion_requirement": "cube_localized"},
        acceptable_decisions=[
            DecisionRuleSpec(decision_kinds=["COMPLETE_MISSION"], raw_actions=["FINISH"], note="Adapt to localization-only user_goal and finish without six-face scan."),
        ],
        forbidden_decisions=[
            DecisionRuleSpec(decision_kinds=["EXECUTE_STEP"], skill_ids=["place_and_release", "regrasp_cube", "reorient_cube", "execute_physical_u_turn"], note="User goal explicitly forbids grasping/scanning."),
        ],
        unnecessary_decisions=[
            DecisionRuleSpec(decision_kinds=["EXECUTE_STEP"], skill_ids=["observe_workspace", "observe_visible_faces"], note="Already localized; six-face scan not requested."),
        ],
        expected_behavior="Follow localization-only user_goal/success_criteria and choose FINISH instead of blindly scanning 6 faces.",
        oracle_source="E2 mission-goal generalization rule",
        provenance={"case_alias": "E2"},
    ))

    cases.append(_make_case(
        case_id="L5_03_E3_PHYSICAL_U_TURN_PRECOND_DISALLOWED",
        dimension=CapabilityDimension.L5_GENERALIZATION,
        difficulty="medium",
        source_type=BenchmarkSourceType.COUNTERFACTUAL_TEST,
        mission_type=MissionType.VERIFY_PHYSICAL_U_TURN,
        initial_state={
            "simulation_initialized": True,
            "cube_localized": True,
            "scan_attempted": True,
            "cube_released_on_table": True,
            "cube_held_in_gripper": False,
            "all_54_facelets_observed": True,
            "finish_inspection_done": True,
            "cube_localized_and_scanned": True,
            "cube_state_validated": True,
            "symbolic_plan_available": True,
            "symbolic_solution": ["U"],
            "physical_u_scene_enabled": True,
            "turn_station_available": False,
            "u_turns_completed": 0,
            "physical_u_turn_executed": False,
        },
        cv_state={
            "cube_localized": True,
            "observed_facelets": full_facelets_sample,
            "observed_count": 54,
            "unknown_count": 0,
            "unknown_facelet_indices": [],
            "observation_conflicts": [],
            "validation_status": "VALID_SOLVABLE",
        },
        observation_history=[
            {"observation_id": "obs-l5-03-h1", "frame_id": "frm-l5-03-h1", "sim_time": 30.3, "coverage": 54, "unknown_after": 0, "visual_summary": "54/54 validated; turn_station_available=False"},
        ],
        current_observation={
            "observation_id": "obs-l5-03",
            "frame_id": "frm-l5-03",
            "camera_id": "overhead",
            "sim_time": 30.5,
            "rgb_image_data_url": img_released_m4a,
        },
        vlm_semantic_observation=_sem(
            obs_id="obs-l5-03",
            frame_id="frm-l5-03",
            relation="cube validated; physical U-turn fixture unavailable",
            support="table supported",
            visible=["cube on table"], occluded=[],
            gaps=["turn_station_available precondition is False"],
            suggested=["CAPABILITY_BLOCKED or SAFE_STOP"],
            summary="Physical U-turn requested, but turn_station_available=False prevents safe execution.",
        ),
        acceptable_decisions=[
            DecisionRuleSpec(decision_kinds=["BLOCK_CAPABILITY", "SAFE_STOP"], note="Block or stop cleanly due to missing turn_station_available."),
        ],
        forbidden_decisions=[
            DecisionRuleSpec(decision_kinds=["EXECUTE_STEP"], skill_ids=["execute_physical_u_turn"], note="Precondition turn_station_available=False."),
            DecisionRuleSpec(decision_kinds=["COMPLETE_MISSION"], note="Cannot report U-turn verified."),
        ],
        expected_behavior="Refuse execute_physical_u_turn when turn_station_available=False; output CAPABILITY_BLOCKED or SAFE_STOP.",
        oracle_source="E3 conditional physical capability boundary",
        provenance={"case_alias": "E3"},
    ))

    cases.append(_make_case(
        case_id="L5_04_E4_FULL_SOLVE_UNSUPPORTED_MOVES",
        dimension=CapabilityDimension.L5_GENERALIZATION,
        difficulty="medium",
        source_type=BenchmarkSourceType.COUNTERFACTUAL_TEST,
        mission_type=MissionType.SOLVE_CUBE,
        initial_state={
            "simulation_initialized": True,
            "cube_localized": True,
            "scan_attempted": True,
            "cube_released_on_table": True,
            "cube_held_in_gripper": False,
            "all_54_facelets_observed": True,
            "finish_inspection_done": True,
            "cube_localized_and_scanned": True,
            "cube_state_validated": True,
            "symbolic_plan_available": True,
            "symbolic_solution": ["U", "R", "F2", "L'"],
            "capability_checked": False,
            "physical_u_scene_enabled": True,
            "turn_station_available": True,
        },
        cv_state={
            "cube_localized": True,
            "observed_facelets": full_facelets_sample,
            "observed_count": 54,
            "unknown_count": 0,
            "unknown_facelet_indices": [],
            "observation_conflicts": [],
            "validation_status": "VALID_SOLVABLE",
        },
        observation_history=[
            {"observation_id": "obs-l5-04-h1", "frame_id": "frm-l5-04-h1", "sim_time": 30.3, "coverage": 54, "unknown_after": 0, "visual_summary": "54/54 validated; Kociemba solve=['U', 'R', 'F2', \"L'\"]"},
        ],
        current_observation={
            "observation_id": "obs-l5-04",
            "frame_id": "frm-l5-04",
            "camera_id": "overhead",
            "sim_time": 30.6,
            "rgb_image_data_url": img_released_m4a,
        },
        vlm_semantic_observation=_sem(
            obs_id="obs-l5-04",
            frame_id="frm-l5-04",
            relation="cube validated on table; symbolic solve includes U, R, F2, L'",
            support="table supported",
            visible=["cube on table"], occluded=[],
            gaps=["R, F2, L' exceed single-U physical capability"],
            suggested=["check_physical_capability or CAPABILITY_BLOCKED"],
            summary="Full solve plan contains unsupported physical turns R, F2, L'.",
        ),
        acceptable_decisions=[
            DecisionRuleSpec(decision_kinds=["EXECUTE_STEP"], skill_ids=["check_physical_capability"], note="Run capability boundary check on full solve sequence."),
            DecisionRuleSpec(decision_kinds=["BLOCK_CAPABILITY"], note="Directly block unsupported multi-face solve sequence."),
        ],
        forbidden_decisions=[
            DecisionRuleSpec(decision_kinds=["EXECUTE_STEP"], skill_ids=["execute_physical_u_turn"], note="Do not start physical U turn on un-audited full solve requiring R/F2/L'."),
            DecisionRuleSpec(decision_kinds=["COMPLETE_MISSION"], note="Cannot claim SOLVE_CUBE finished without check_physical_capability."),
        ],
        expected_behavior="Audit physical boundary (check_physical_capability) or block (CAPABILITY_BLOCKED); never blindly execute U or claim solved.",
        oracle_source="E4 full-solve physical limitation boundary",
        provenance={"case_alias": "E4"},
    ))

    cases.append(_make_case(
        case_id="L5_05_E5_CAMERA_TEMP_UNAVAILABLE_ADAPT",
        dimension=CapabilityDimension.L5_GENERALIZATION,
        difficulty="hard",
        source_type=BenchmarkSourceType.COUNTERFACTUAL_TEST,
        initial_state={
            "simulation_initialized": True,
            "cube_localized": False,
            "scan_attempted": False,
            "cube_released_on_table": False,
            "cube_held_in_gripper": False,
            "all_54_facelets_observed": False,
            "camera_status": {
                "overhead": "UNAVAILABLE_OFFLINE",
                "world_top": "ONLINE",
                "scan_top": "ONLINE",
                "inspection_top": "ONLINE",
            },
        },
        cv_state={
            "cube_localized": False,
            "observed_facelets": all_unknown_facelets,
            "observed_count": 0,
            "unknown_count": 54,
            "unknown_facelet_indices": list(range(54)),
            "observation_conflicts": [],
        },
        observation_history=[],
        failure_feedback={
            "skill_id": "observe_workspace",
            "parameters": {"camera_name": "overhead"},
            "success": False,
            "failure_code": "CAMERA_UNAVAILABLE",
            "result_summary": "overhead 相机临时不可用；world_top 与 scan_top 相机在线。",
        },
        current_observation={
            "observation_id": "obs-l5-05",
            "frame_id": "frm-l5-05",
            "camera_id": "world_top",
            "sim_time": 1.0,
            "rgb_image_data_url": img_base_init,
        },
        vlm_semantic_observation=_sem(
            obs_id="obs-l5-05",
            frame_id="frm-l5-05",
            camera_id="world_top",
            relation="cube visible on table from world_top camera while overhead camera is offline",
            support="table supported",
            visible=["workspace table and cube"], occluded=[],
            gaps=["cube not yet localized; overhead camera offline"],
            suggested=["call observe_workspace with camera_name='world_top' or 'scan_top'"],
            summary="Overhead camera temporarily unavailable; world_top and scan_top remain online.",
        ),
        acceptable_decisions=[
            DecisionRuleSpec(
                decision_kinds=["EXECUTE_STEP"],
                skill_ids=["observe_workspace"],
                parameter_rules={"camera_name": ["world_top", "scan_top", "inspection_top"]},
                note="Adapt camera_name parameter to available online top camera.",
            ),
            DecisionRuleSpec(decision_kinds=["SAFE_STOP"], note="Conservative stop if preferring operator intervention."),
        ],
        forbidden_decisions=[
            DecisionRuleSpec(
                decision_kinds=["EXECUTE_STEP"],
                skill_ids=["observe_workspace"],
                parameter_rules={"camera_name": ["overhead", None]},
                note="Must not retry offline overhead camera.",
            ),
            DecisionRuleSpec(decision_kinds=["EXECUTE_STEP"], skill_ids=["place_and_release", "regrasp_cube", "reorient_cube", "observe_visible_faces"], note="cube_localized=False."),
            DecisionRuleSpec(decision_kinds=["COMPLETE_MISSION"], note="Not localized."),
        ],
        expected_behavior="Adapt observe_workspace parameter to an online camera ('world_top'|'scan_top'|'inspection_top') instead of retrying offline 'overhead'.",
        oracle_source="E5 parameter adaptation under temporary sensor unavailability",
        provenance={"case_alias": "E5"},
    ))

    cases.append(_make_case(
        case_id="L5_06_E6_SHIFTED_CUBE_RELOCALIZE_ONLY",
        dimension=CapabilityDimension.L5_GENERALIZATION,
        difficulty="medium",
        source_type=BenchmarkSourceType.REAL_REPLAY if sl_x005_fail else BenchmarkSourceType.COUNTERFACTUAL_TEST,
        initial_state={
            "simulation_initialized": True,
            "cube_localized": False,
            "scan_attempted": False,
            "cube_released_on_table": False,
            "cube_held_in_gripper": False,
            "all_54_facelets_observed": False,
            "perturbation": {"dx_m": 0.05, "dy_m": 0.0},
        },
        cv_state={
            "cube_localized": False,
            "observed_facelets": all_unknown_facelets,
            "observed_count": 0,
            "unknown_count": 54,
            "unknown_facelet_indices": list(range(54)),
            "observation_conflicts": [],
            "previous_stale_center_m": [0.1015, -0.1358, 0.6692],
        },
        observation_history=[],
        failure_feedback={
            "skill_id": "place_and_release",
            "success": False,
            "failure_code": "POSE_STALE_AFTER_SHIFT",
            "result_summary": "初始魔方位置发生 +5 cm 偏移，需重新通过顶部 RGB-D 定位（禁止直接修改底层控制量）。",
        },
        current_observation={
            "observation_id": "obs-l5-06",
            "frame_id": "frm-l5-06",
            "camera_id": "overhead",
            "sim_time": 0.9,
            "rgb_image_data_url": img_x005,
        },
        vlm_semantic_observation=_sem(
            obs_id="obs-l5-06",
            frame_id="frm-l5-06",
            relation="cube visibly shifted rightward (+X) on workspace table",
            support="table supported",
            visible=["cube at shifted table position"], occluded=["bottom"],
            gaps=["new 3D pose must be estimated via RGB-D"],
            suggested=["observe_workspace to re-localize shifted cube"],
            summary="Cube position shifted +5 cm along table; re-localization via observe_workspace required.",
        ),
        acceptable_decisions=[
            DecisionRuleSpec(decision_kinds=["EXECUTE_STEP"], skill_ids=["observe_workspace"], note="Re-localize shifted cube via RGB-D."),
        ],
        forbidden_decisions=[
            DecisionRuleSpec(decision_kinds=["EXECUTE_STEP"], skill_ids=["place_and_release", "regrasp_cube", "reorient_cube", "observe_visible_faces"], note="cube_localized=False; must re-localize rather than blind grasp/motion."),
            DecisionRuleSpec(decision_kinds=["COMPLETE_MISSION"], note="Not localized."),
        ],
        expected_behavior="Invoke observe_workspace to re-localize shifted cube using RGB-D without bypassing perception.",
        oracle_source="E6 initial pose shift re-localization rule",
        provenance={
            "case_alias": "E6",
            "source_bundle_run_id": sl_x005_fail["run_id"] if sl_x005_fail else None,
            "m4c_bundle_loaded": sl_x005_fail is not None,
        },
    ))

    return cases


def build_closed_loop_scenarios() -> list[dict[str, Any]]:
    """Representative real MuJoCo closed-loop evaluation scenarios (Section XIV)."""
    return [
        {
            "scenario_id": "CL_01_NORMAL_INSPECT_SEED0",
            "title": "正常六面主动扫描 (Seed 0)",
            "mission_type": MissionType.INSPECT_CUBE.value,
            "seed": 0,
            "perturbation": None,
            "setup_phase": "none",
            "expected_outcome": "COMPLETED",
            "expected_capability_block": False,
            "max_decision_rounds": 16,
            "max_vlm_calls": 32,
        },
        {
            "scenario_id": "CL_02_PARTIAL_SCAN_45_OF_54",
            "title": "已完成 45/54 扫描的中间状态接续 (真实物理预置)",
            "mission_type": MissionType.INSPECT_CUBE.value,
            "seed": 0,
            "perturbation": None,
            "setup_phase": "real_released_45_of_54",
            "expected_outcome": "COMPLETED",
            "expected_capability_block": False,
            "max_decision_rounds": 12,
            "max_vlm_calls": 24,
        },
        {
            "scenario_id": "CL_03_LOCALIZATION_FAILURE_BLACKOUT",
            "title": "视觉传感器中断导致定位失败 (Blackout 负对照)",
            "mission_type": MissionType.INSPECT_CUBE.value,
            "seed": 0,
            "perturbation": {"dx_m": 0.05, "dy_m": 0.0, "dyaw_rad": 0.0, "vision_fault_mode": "blackout"},
            "setup_phase": "none",
            "expected_outcome": "SAFE_STOP_OR_PERCEPTION_FAILURE",
            "expected_capability_block": False,
            "max_decision_rounds": 4,
            "max_vlm_calls": 8,
        },
        {
            "scenario_id": "CL_04_PHYSICAL_SKILL_FAILURE_SHIFT_X005",
            "title": "+5 cm 偏移重抓基座碰撞 (物理 Skill 故障归因)",
            "mission_type": MissionType.INSPECT_CUBE.value,
            "seed": 0,
            "perturbation": {"dx_m": 0.05, "dy_m": 0.0, "dyaw_rad": 0.0, "vision_fault_mode": None},
            "setup_phase": "none",
            "expected_outcome": "SKILL_FAILURE_ATTRIBUTED",
            "expected_capability_block": False,
            "max_decision_rounds": 14,
            "max_vlm_calls": 28,
        },
        {
            "scenario_id": "CL_05_UNSUPPORTED_SOLVE_CAPABILITY",
            "title": "完整求解遇到未建模物理转层 (能力边界阻塞)",
            "mission_type": MissionType.SOLVE_CUBE.value,
            "seed": 0,
            "perturbation": None,
            "setup_phase": "none",
            "expected_outcome": "BLOCKED_CAPABILITY",
            "expected_capability_block": True,
            "max_decision_rounds": 18,
            "max_vlm_calls": 36,
        },
    ]
