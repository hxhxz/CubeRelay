#!/usr/bin/env python3
"""Reproducible M4-A runner: Gemini VLM-in-the-Loop, Visual Ablations, and Deterministic Baseline."""

from __future__ import annotations

import argparse
import base64
import json
import sys
import time
from pathlib import Path
from typing import Any

from cube_relay.embodied.failure_aware_v6 import FailureAwareRulePlanner, FailureAwareSkillAgent
from cube_relay.embodied.vlm import HeuristicSceneVLM
from cube_relay.mission import (
    DeterministicMissionPlanner,
    FakeGeminiVLMClient,
    GeminiMissionPlanner,
    MissionState,
    MissionStatus,
    MissionType,
    SimulationSession,
    SkillRegistry,
    VLMInspectionLimits,
)

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUT_DIR = ROOT / "results" / "m4a_acceptance"


def _save_data_url_jpeg(data_url: str | None, out_path: Path) -> dict[str, Any] | None:
    if not data_url or "," not in data_url:
        return None
    _, b64 = data_url.split(",", 1)
    raw = base64.b64decode(b64)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_bytes(raw)
    return {"path": str(out_path.relative_to(ROOT)), "bytes": len(raw)}


def _compact_snapshot(snapshot: dict[str, Any]) -> dict[str, Any]:
    compacted = json.loads(json.dumps(snapshot, ensure_ascii=False))
    for key in ("main_frame_url", "wrist_rgb_url", "wrist_depth_url"):
        val = compacted.get(key)
        if isinstance(val, str):
            compacted[key] = f"<data_url len={len(val)}>"
    agent = compacted.get("agent_state")
    if isinstance(agent, dict) and isinstance(agent.get("current_observation_image_url"), str):
        val = agent["current_observation_image_url"]
        agent["current_observation_image_url"] = f"<data_url len={len(val)}>"
    for ev in compacted.get("trace_events", []):
        ev_d = ev.get("evidence")
        if isinstance(ev_d, dict) and isinstance(ev_d.get("frame_images"), list):
            for img in ev_d["frame_images"]:
                if isinstance(img, dict) and isinstance(img.get("image_url"), str):
                    img["image_url"] = f"<data_url len={len(img['image_url'])}>"
    return compacted


def _extract_vlm_metrics(snapshot: dict[str, Any], planner: Any) -> dict[str, Any]:
    timing = snapshot.get("timing_metrics") or {}
    skill_execs = snapshot.get("skill_executions") or []
    physical_actions = sum(
        1
        for ex in skill_execs
        if ex.get("skill_id") in {"place_and_release", "regrasp_cube", "reorient_cube", "active_six_face_scan", "execute_physical_u_turn"}
    )
    observe_count = sum(
        1
        for ev in snapshot.get("trace_events", [])
        if ev.get("event_type") == "perception"
    )
    obs_ref = snapshot.get("last_observation_ref") or {}
    call_traces = []
    for idx, tr in enumerate(getattr(planner, "call_traces", []), start=1):
        call_traces.append({
            "call_index": idx,
            "provider": tr.provider,
            "model": tr.model,
            "latency_ms": tr.latency_ms,
            "input_tokens": tr.input_tokens,
            "output_tokens": tr.output_tokens,
            "image_included": tr.image_included,
            "image_sha256": tr.image_sha256,
            "parsed_output": tr.parsed_output.model_dump(mode="json") if tr.parsed_output else None,
            "error_code": tr.error_code,
            "error": tr.error,
        })
    return {
        "seed": snapshot.get("seed"),
        "mission_type": snapshot.get("mission", {}).get("mission_type"),
        "status": snapshot.get("mission", {}).get("status"),
        "failure_reason": snapshot.get("mission", {}).get("failure_reason"),
        "blocked_move": snapshot.get("mission", {}).get("blocked_move"),
        "observed_count": obs_ref.get("observed_count", 0),
        "unknown_count": obs_ref.get("unknown_count", 54),
        "conflict_count": obs_ref.get("conflict_count", 0),
        "validation_status": snapshot.get("cube_validation_status"),
        "reconstructed_facelets": obs_ref.get("reconstructed_facelets"),
        "skills_executed": [ex.get("skill_id") for ex in skill_execs],
        "physical_action_count": physical_actions,
        "observation_count": observe_count,
        "sim_time": snapshot.get("sim_time"),
        "skill_duration_sim_s": timing.get("skill_duration_sim_s"),
        "total_execution_wall_s": timing.get("total_execution_wall_s"),
        "vlm_calls": timing.get("vlm_calls", 0),
        "model_latency_ms": timing.get("model_latency_ms", 0.0),
        "input_tokens": timing.get("input_tokens", 0),
        "output_tokens": timing.get("output_tokens", 0),
        "fallback_triggered": snapshot.get("agent_state", {}).get("fallback_triggered", False),
        "llm_connected": snapshot.get("agent_state", {}).get("llm_connected", False),
        "llm_model": snapshot.get("agent_state", {}).get("llm_model"),
        "call_traces": call_traces,
    }


def run_vlm_closed_loop_suite(out_dir: Path, *, seed: int = 0, model: str | None = None) -> dict[str, Any]:
    frames_dir = out_dir / "frames"
    frames_dir.mkdir(parents=True, exist_ok=True)
    results: dict[str, Any] = {}

    for mission_type, filename in (
        (MissionType.INSPECT_CUBE, f"vlm_inspect_cube_seed{seed}.json"),
        (MissionType.VERIFY_PHYSICAL_U_TURN, f"vlm_verify_u_turn_seed{seed}.json"),
        (MissionType.SOLVE_CUBE, f"vlm_solve_cube_seed{seed}.json"),
    ):
        planner = GeminiMissionPlanner(model=model, limits=VLMInspectionLimits(max_decision_rounds=18, max_vlm_calls=18))
        if not planner.client.is_configured():
            raise RuntimeError("Gemini VLM client is not configured (.env / CUBERELAY_VLM_API_KEY missing)")
        sess = SimulationSession(seed=seed, width=480, height=320, planner=planner)
        try:
            snap = sess.run_mission(mission_type, seed=seed)
            metrics = _extract_vlm_metrics(snap, planner)
            # Capture initial / final observation image files from decision events & traces
            saved_frames: list[dict[str, Any]] = []
            if mission_type == MissionType.INSPECT_CUBE:
                saved = _save_data_url_jpeg(
                    snap.get("agent_state", {}).get("current_observation_image_url"),
                    frames_dir / f"vlm_inspect_final_overhead_seed{seed}.jpg",
                )
                if saved:
                    saved_frames.append({"stage": "final_vlm_input", **saved})
            elif mission_type == MissionType.VERIFY_PHYSICAL_U_TURN:
                saved = _save_data_url_jpeg(
                    snap.get("main_frame_url"),
                    frames_dir / f"vlm_post_u_turn_main_seed{seed}.jpg",
                )
                if saved:
                    saved_frames.append({"stage": "post_u_turn_main", **saved})
            metrics["saved_frames"] = saved_frames
            (out_dir / filename).write_text(
                json.dumps({"metrics": metrics, "snapshot": _compact_snapshot(snap)}, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            results[mission_type.value] = metrics
        finally:
            sess.close()

    # Controlled direct capability block test (when model/request asks for unsupported move U')
    fake_block_client = FakeGeminiVLMClient(
        model=model or "gemini-protocol-capability-check",
        responses=[{
            "action": "execute_physical_u_turn",
            "parameters": {"move": "U'"},
            "reason_summary": "Attempt inverse U' physical turn (should be rejected by SkillRegistry)",
            "expected_information_gain": "Verify Safety Gate blocks unsupported U' move",
            "confidence": 0.9,
        }],
    )
    block_planner = GeminiMissionPlanner(client=fake_block_client)
    sess_blk = SimulationSession(seed=seed, width=320, height=240, planner=block_planner)
    try:
        snap_blk = sess_blk.run_mission(MissionType.SOLVE_CUBE, seed=seed)
        blk_summary = {
            "status": snap_blk["mission"]["status"],
            "blocked_move": snap_blk["mission"]["blocked_move"],
            "blocked_reason": snap_blk["mission"]["blocked_reason"],
            "decision_events": [
                ev for ev in snap_blk["decision_events"] if ev["event_type"] == "CAPABILITY_BLOCKED"
            ],
        }
        (out_dir / "vlm_unsupported_move_blocked.json").write_text(
            json.dumps(blk_summary, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        results["DIRECT_UNSUPPORTED_MOVE_BLOCK"] = blk_summary
    finally:
        sess_blk.close()

    return results


def run_visual_ablation_suite(
    out_dir: Path,
    *,
    seed: int = 0,
    model: str | None = None,
    repeats: int = 2,
) -> dict[str, Any]:
    frames_dir = out_dir / "frames"
    frames_dir.mkdir(parents=True, exist_ok=True)

    sess = SimulationSession(seed=seed, width=480, height=320)
    try:
        b = sess._backend
        FailureAwareSkillAgent(b, HeuristicSceneVLM(), FailureAwareRulePlanner()).run(seed, 15, reset_scene=False)
        b.task_align_scan_axes()
        b.task_place_release()
        obs_s1 = sess.build_agent_observation(camera_id="overhead")
        s1_file = _save_data_url_jpeg(obs_s1.rgb_image_data_url, frames_dir / f"ablation_s1_released_table_seed{seed}.jpg")

        b.task_regrasp()
        obs_s2 = sess.build_agent_observation(camera_id="overhead")
        s2_file = _save_data_url_jpeg(obs_s2.rgb_image_data_url, frames_dir / f"ablation_s2_held_gripper_seed{seed}.jpg")
    finally:
        sess.close()

    reg = SkillRegistry()
    msn = MissionState(
        mission_id=f"msn-ablation-seed{seed}",
        session_id=f"ABLATION-SEED{seed}",
        mission_type=MissionType.INSPECT_CUBE,
        user_goal="Visual dependency controlled ablation",
        success_criteria="Select valid action matching visual physical state",
        status=MissionStatus.OBSERVING,
        created_at="00:00:00",
    )

    real_state_s1 = {"simulation_initialized": True, "cube_localized": True, "cube_released_on_table": True, "cube_held_in_gripper": False}
    real_state_s2 = {"simulation_initialized": True, "cube_localized": True, "cube_released_on_table": False, "cube_held_in_gripper": True}
    # Permissive prompt-evaluation state so we can inspect what the VLM picks in counterfactuals,
    # then validate the VLM choice separately against real_state_s1 / real_state_s2 via SkillRegistry!
    permissive_state = {"simulation_initialized": True, "cube_localized": True, "cube_released_on_table": True, "cube_held_in_gripper": True}

    conditions = [
        ("ExpA_Real_S1_Released", "vision_only_minimal", obs_s1, None, real_state_s1, "regrasp_cube"),
        ("ExpA_Real_S2_Held", "vision_only_minimal", obs_s2, None, real_state_s2, "reorient_cube"),
        ("ExpB_NoImage_S1", "no_image", obs_s1, None, real_state_s1, "regrasp_cube"),
        ("ExpB_NoImage_S2", "no_image", obs_s2, None, real_state_s2, "reorient_cube"),
        ("ExpC_Replaced_S1WithHeldImg", "replaced_image", obs_s1, obs_s2.rgb_image_data_url, real_state_s1, "regrasp_cube"),
        ("ExpC_Replaced_S2WithReleasedImg", "replaced_image", obs_s2, obs_s1.rgb_image_data_url, real_state_s2, "reorient_cube"),
    ]

    rows: list[dict[str, Any]] = []
    for cond_name, ctx_mode, obs, repl_url, true_scene_state, true_expected_action in conditions:
        trial_records: list[dict[str, Any]] = []
        for rep in range(1, repeats + 1):
            p = GeminiMissionPlanner(model=model, context_mode=ctx_mode, replacement_image_data_url=repl_url)
            plan = p.create_plan(msn, reg, plan_id=f"plan-{cond_name}-{rep}")
            action = p.select_next_action(msn, plan, reg, permissive_state, None, agent_observation=obs)
            # Check chosen action against the TRUE physical preconditions via SkillRegistry!
            chosen_skill = action.skill_id or action.decision_kind
            if chosen_skill in {s.skill_id for s in reg.list_skills()}:
                gate_ok, missing = reg.check_preconditions(chosen_skill, true_scene_state)
                param_ok, param_err = reg.validate_parameters(chosen_skill, action.parameters)
            else:
                gate_ok, missing, param_ok, param_err = False, ["non_skill_action"], True, None
            trace = p.call_traces[-1] if p.call_traces else None
            trial_records.append({
                "repeat": rep,
                "selected_action": chosen_skill,
                "parameters": action.parameters,
                "rationale_summary": action.rationale_summary,
                "confidence": action.confidence,
                "matches_true_state_action": chosen_skill == true_expected_action,
                "safety_gate_against_true_state": {
                    "passed": gate_ok and param_ok,
                    "missing_preconditions": missing,
                    "param_error": param_err,
                },
                "latency_ms": trace.latency_ms if trace else None,
                "input_tokens": trace.input_tokens if trace else None,
                "output_tokens": trace.output_tokens if trace else None,
                "image_included": trace.image_included if trace else None,
                "image_sha256": trace.image_sha256 if trace else None,
            })
        rows.append({
            "condition": cond_name,
            "context_mode": ctx_mode,
            "observation_id": obs.observation_id,
            "frame_id": obs.frame_id,
            "true_expected_action": true_expected_action,
            "repeats": trial_records,
        })

    ablation_report = {
        "seed": seed,
        "camera_id": "overhead",
        "saved_frames": {"s1_released": s1_file, "s2_held": s2_file},
        "conditions": rows,
    }
    (out_dir / f"visual_ablation_seed{seed}.json").write_text(
        json.dumps(ablation_report, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return ablation_report


def run_baseline_comparison(
    out_dir: Path,
    *,
    seeds: list[int],
    model: str | None = None,
) -> dict[str, Any]:
    det_runs: list[dict[str, Any]] = []
    vlm_runs: list[dict[str, Any]] = []

    for s in seeds:
        det_planner = DeterministicMissionPlanner()
        sess_det = SimulationSession(seed=s, width=480, height=320, planner=det_planner)
        try:
            t0 = time.perf_counter()
            snap_det = sess_det.run_mission(MissionType.INSPECT_CUBE, seed=s)
            wall_det = round(time.perf_counter() - t0, 4)
            m_det = _extract_vlm_metrics(snap_det, det_planner)
            m_det["total_execution_wall_s"] = wall_det
            det_runs.append(m_det)
        finally:
            sess_det.close()

        vlm_planner = GeminiMissionPlanner(model=model, limits=VLMInspectionLimits(max_decision_rounds=18, max_vlm_calls=18))
        sess_vlm = SimulationSession(seed=s, width=480, height=320, planner=vlm_planner)
        try:
            snap_vlm = sess_vlm.run_mission(MissionType.INSPECT_CUBE, seed=s)
            m_vlm = _extract_vlm_metrics(snap_vlm, vlm_planner)
            vlm_runs.append(m_vlm)
        finally:
            sess_vlm.close()

    def _agg(rows: list[dict[str, Any]]) -> dict[str, Any]:
        n = max(1, len(rows))
        return {
            "episodes": len(rows),
            "success_rate": sum(1 for r in rows if r["status"] == "COMPLETED") / n,
            "mean_observed_count": sum(r["observed_count"] for r in rows) / n,
            "mean_physical_actions": sum(r["physical_action_count"] for r in rows) / n,
            "mean_observations": sum(r["observation_count"] for r in rows) / n,
            "mean_sim_time_s": round(sum(float(r["sim_time"] or 0.0) for r in rows) / n, 3),
            "mean_wall_time_s": round(sum(float(r["total_execution_wall_s"] or 0.0) for r in rows) / n, 3),
            "total_vlm_calls": sum(r["vlm_calls"] for r in rows),
            "total_input_tokens": sum(r["input_tokens"] for r in rows),
            "total_output_tokens": sum(r["output_tokens"] for r in rows),
            "mean_vlm_latency_ms": round(sum(float(r["model_latency_ms"] or 0.0) for r in rows) / n, 2),
            "failures": sum(1 for r in rows if r["status"] != "COMPLETED"),
        }

    comparison = {
        "seeds": seeds,
        "deterministic_baseline": {"summary": _agg(det_runs), "runs": det_runs},
        "gemini_vlm_agent": {"summary": _agg(vlm_runs), "runs": vlm_runs},
    }
    (out_dir / "baseline_vs_vlm_comparison.json").write_text(
        json.dumps(comparison, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return comparison


def main() -> int:
    parser = argparse.ArgumentParser(description="Run CubeRelay M4-A Gemini VLM-in-the-Loop Experiments.")
    parser.add_argument("--mode", choices=("all", "vlm_closed_loop", "ablation", "baseline"), default="all")
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--seeds", default="0,1,2")
    parser.add_argument("--model", default=None)
    parser.add_argument("--ablation-repeats", type=int, default=2)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUT_DIR)
    args = parser.parse_args()

    args.output_dir = args.output_dir.resolve()
    args.output_dir.mkdir(parents=True, exist_ok=True)
    summary: dict[str, Any] = {"ok": True, "seed": args.seed, "mode": args.mode}

    if args.mode in ("all", "vlm_closed_loop"):
        summary["vlm_closed_loop"] = run_vlm_closed_loop_suite(args.output_dir, seed=args.seed, model=args.model)
    if args.mode in ("all", "ablation"):
        summary["visual_ablation"] = run_visual_ablation_suite(
            args.output_dir, seed=args.seed, model=args.model, repeats=args.ablation_repeats
        )
    if args.mode in ("all", "baseline"):
        seeds = [int(s.strip()) for s in args.seeds.split(",") if s.strip()]
        summary["baseline_comparison"] = run_baseline_comparison(args.output_dir, seeds=seeds, model=args.model)

    (args.output_dir / "summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
