#!/usr/bin/env python3
"""Run CubeRelay M4-D Task Agent Capability Benchmark (Layer A Replay + Layer B MuJoCo)."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import re
import sys
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from cube_relay.benchmark import (
    BenchmarkExporter,
    CapabilityDimension,
    ClosedLoopBenchmarkRunner,
    DecisionReplayRunner,
    PlannerGroup,
    PromptGuideMode,
    VLMAblationCondition,
    assemble_benchmark_run,
    build_closed_loop_scenarios,
    build_m4d_replay_cases,
    load_benchmark_run,
    verify_benchmark_zip_integrity,
)
from cube_relay.mission.dual_model import FakeStructuredModelClient
from cube_relay.mission.vlm_client import FakeGeminiVLMClient


def _build_default_fake_perception_factory():
    def _factory() -> FakeStructuredModelClient:
        def _handler(prompt: str, image_url: str | None) -> dict[str, Any]:
            obs_match = re.search(r"observation_id[\"':\s]+([A-Za-z0-9_\-]+)", prompt)
            frm_match = re.search(r"frame_id[\"':\s]+([A-Za-z0-9_\-]+)", prompt)
            cam_match = re.search(r"camera_id[\"':\s]+([A-Za-z0-9_\-]+)", prompt)
            return {
                "observation_id": obs_match.group(1) if obs_match else "obs-fake",
                "frame_id": frm_match.group(1) if frm_match else "frm-fake",
                "camera_id": cam_match.group(1) if cam_match else "overhead",
                "cube_visible": bool(image_url),
                "cube_relation_to_gripper": "on_table_released" if "released" in prompt else "unknown",
                "support_relation": "table_top",
                "visible_regions": ["top", "front"] if image_url else [],
                "occluded_regions": ["bottom_table_contact"] if image_url else ["workspace_blackout"],
                "information_gaps": ["bottom face hidden while resting on table"],
                "suggested_observations": ["observe_workspace"] if not image_url else ["regrasp_cube"],
                "visual_conflicts": [],
                "confidence": 0.65 if image_url else 0.15,
                "summary": "Offline fake VLM semantic summary for pipeline verification.",
            }
        return FakeStructuredModelClient("PERCEPTION", _handler, model="fake-vlm-validator")
    return _factory


def _build_default_fake_agent_factory():
    def _factory() -> FakeStructuredModelClient:
        def _handler(prompt: str, _image_url: str | None) -> dict[str, Any]:
            obs_match = re.search(r"(obs-[A-Za-z0-9_\-]+)", prompt)
            obs_id = obs_match.group(1) if obs_match else "obs-fake"
            # Minimal heuristic mock so offline_fake produces schema-valid Agent decisions
            if "unsupported" in prompt.lower() or "impossible" in prompt.lower() or "non_u_turn" in prompt.lower():
                return {
                    "selected_action": "CAPABILITY_BLOCKED",
                    "skill_id": None,
                    "parameters": {},
                    "reason_summary": "Fake offline agent mock: required capability unavailable.",
                    "evidence_observation_ids": [obs_id],
                    "expected_outcome": "capability_blocked",
                    "completion_condition": "report limitation",
                    "confidence": 0.85,
                    "need_replan": False,
                }
            if '"cube_localized": false' in prompt:
                return {
                    "selected_action": "observe_workspace",
                    "skill_id": "observe_workspace",
                    "parameters": {"camera_name": "overhead"},
                    "reason_summary": "Fake offline agent mock: cube not localized yet.",
                    "evidence_observation_ids": [obs_id],
                    "expected_outcome": "cube_localized",
                    "completion_condition": "cube localized",
                    "confidence": 0.8,
                    "need_replan": False,
                }
            return {
                "selected_action": "observe_visible_faces",
                "skill_id": "observe_visible_faces",
                "parameters": {"view_mode": "held"},
                "reason_summary": "Fake offline agent mock decision for pipeline schema verification.",
                "evidence_observation_ids": [obs_id],
                "expected_outcome": "updated facelets",
                "completion_condition": "54 facelets valid",
                "confidence": 0.75,
                "need_replan": False,
            }
        return FakeStructuredModelClient("AGENT", _handler, model="fake-agent-validator")
    return _factory


def _build_default_fake_single_factory():
    def _factory() -> FakeGeminiVLMClient:
        def _handler(prompt: str, _img: str | None, _has_img: bool) -> dict[str, Any]:
            return {
                "action": "observe_workspace",
                "parameters": {"camera_name": "overhead"},
                "reason_summary": "Fake single-model mock decision.",
                "expected_information_gain": "verify cube location",
                "confidence": 0.7,
            }
        return FakeGeminiVLMClient(model="fake-single-vlm-validator", handler=_handler)
    return _factory


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run CubeRelay M4-D Task Agent Capability Benchmark")
    parser.add_argument(
        "--mode",
        choices=["offline_fake", "online_real", "deterministic_only"],
        default="offline_fake",
        help="Execution mode (FAKE_PROVIDER outputs are strictly segregated from real scorecards).",
    )
    parser.add_argument(
        "--groups",
        default="DETERMINISTIC_BASELINE,LLM_AGENT_CV_ONLY,LLM_AGENT_CV_VLM,SINGLE_MODEL_BASELINE",
        help="Comma-separated PlannerGroup list for Layer A Replay.",
    )
    parser.add_argument(
        "--dimensions",
        default="",
        help="Optional comma-separated CapabilityDimension filter (default all L1-L5).",
    )
    parser.add_argument(
        "--cases",
        default="",
        help="Optional comma-separated case_id prefix/exact filter.",
    )
    parser.add_argument(
        "--guide-modes",
        default="GUIDE_MINIMAL",
        help="Comma-separated PromptGuideMode list (GUIDE_MINIMAL,GUIDE_FULL).",
    )
    parser.add_argument(
        "--run-guide-ablation",
        action="store_true",
        help="Additionally evaluate GUIDE_FULL vs GUIDE_MINIMAL when not already both in --guide-modes.",
    )
    parser.add_argument(
        "--run-vlm-ablation",
        action="store_true",
        help="Run 5-condition L3 VLM causal ablation (VLM_TRUE/ABSENT/SWAPPED/CONTRADICTORY/LOW_CONFIDENCE).",
    )
    parser.add_argument(
        "--vlm-ablation-guide-mode",
        choices=["GUIDE_MINIMAL", "GUIDE_FULL"],
        default="GUIDE_MINIMAL",
    )
    parser.add_argument("--repeats", type=int, default=1, help="Repeats per case for Layer A main matrix.")
    parser.add_argument("--vlm-ablation-repeats", type=int, default=1, help="Repeats per case for L3 VLM ablation.")
    parser.add_argument("--closed-loop", action="store_true", help="Run Layer B physical MuJoCo closed-loop scenarios.")
    parser.add_argument(
        "--closed-loop-scenarios",
        default="",
        help="Optional comma-separated CL scenario IDs (default all CL_01..CL_05).",
    )
    parser.add_argument(
        "--closed-loop-groups",
        default="DETERMINISTIC_BASELINE,LLM_AGENT_CV_ONLY,LLM_AGENT_CV_VLM",
        help="Comma-separated PlannerGroup list for Layer B MuJoCo closed loop.",
    )
    parser.add_argument("--closed-loop-width", type=int, default=480)
    parser.add_argument("--closed-loop-height", type=int, default=320)
    parser.add_argument(
        "--m4c-bundles-dir",
        type=Path,
        default=ROOT / "results" / "m4c_experiments" / "bundles",
    )
    parser.add_argument(
        "--m4a-frames-dir",
        type=Path,
        default=ROOT / "results" / "m4a_acceptance" / "frames",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=ROOT / "results" / "m4d_benchmark",
    )
    parser.add_argument(
        "--run-subdir",
        default="",
        help="Optional explicit run directory name under --output-dir (defaults to writing directly to --output-dir when empty unless --timestamped).",
    )
    parser.add_argument("--timestamped", action="store_true", help="Write under <output-dir>/<timestamp>.")
    parser.add_argument("--dry-run-count", type=int, default=0, help="Optional cap on replay cases.")
    parser.add_argument("--skip-replay", action="store_true", help="Skip main Layer A Decision Replay suite.")
    parser.add_argument(
        "--merge-from",
        type=Path,
        default=None,
        help="Optional existing summary.json or run dir to merge previous Layer A/B records into.",
    )
    parser.add_argument("--no-export-zip", action="store_true", help="Skip ZIP bundle generation.")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    all_cases = build_m4d_replay_cases(
        m4c_bundles_dir=args.m4c_bundles_dir,
        m4a_frames_dir=args.m4a_frames_dir,
    )

    selected_cases = list(all_cases)
    if args.dimensions.strip():
        allowed_dims = {CapabilityDimension(x.strip()) for x in args.dimensions.split(",") if x.strip()}
        selected_cases = [c for c in selected_cases if c.capability_dimension in allowed_dims]
    if args.cases.strip():
        prefixes = [x.strip() for x in args.cases.split(",") if x.strip()]
        selected_cases = [c for c in selected_cases if any(c.case_id == p or c.case_id.startswith(p) for p in prefixes)]
    if args.dry_run_count and args.dry_run_count > 0:
        selected_cases = selected_cases[: args.dry_run_count]

    groups = [PlannerGroup(x.strip()) for x in args.groups.split(",") if x.strip()]
    if args.mode == "deterministic_only":
        groups = [PlannerGroup.DETERMINISTIC_BASELINE]

    guide_modes = [PromptGuideMode(x.strip()) for x in args.guide_modes.split(",") if x.strip()]

    fake_p = _build_default_fake_perception_factory() if args.mode == "offline_fake" else None
    fake_a = _build_default_fake_agent_factory() if args.mode == "offline_fake" else None
    fake_s = _build_default_fake_single_factory() if args.mode == "offline_fake" else None

    replay_runner = DecisionReplayRunner(
        mode=args.mode,
        perception_client_factory=fake_p,
        agent_client_factory=fake_a,
        single_vlm_client_factory=fake_s,
    )

    def _log_progress(rec: Any, idx: int, total: int) -> None:
        cond = rec.vlm_ablation_condition.value if rec.vlm_ablation_condition else rec.guide_mode.value
        extra = ""
        if rec.model_call_status not in {"SUCCESS", "NOT_APPLICABLE", "INCOMPARABLE"}:
            extra = f" err={rec.reason_summary[:100]!r}"
        print(
            f"  [{idx}/{total}] {rec.planner_group.value} ({cond}) {rec.benchmark_case_id} "
            f"rep={rec.repeat_index} -> {rec.normalized_action} [{rec.oracle_result.verdict}] "
            f"status={rec.model_call_status} ({rec.latency_ms:.0f}ms){extra}",
            flush=True,
        )

    decision_records = []
    guide_ablation_records = []
    vlm_ablation_records = []
    closed_loop_episodes = []

    if args.merge_from is not None:
        prev = load_benchmark_run(args.merge_from)
        decision_records.extend(prev.decision_records)
        guide_ablation_records.extend(prev.guide_ablation_records)
        vlm_ablation_records.extend(prev.vlm_ablation_records)
        closed_loop_episodes.extend(prev.closed_loop_episodes)
        print(
            f"[M4-D] Loaded prior records from {args.merge_from}: "
            f"D={len(decision_records)}, VLM={len(vlm_ablation_records)}, GUIDE={len(guide_ablation_records)}, CL={len(closed_loop_episodes)}",
            flush=True,
        )

    if not args.skip_replay:
        print(
            f"[M4-D] Layer A Replay: mode={args.mode}, cases={len(selected_cases)}, "
            f"groups={[g.value for g in groups]}, guide_modes={[m.value for m in guide_modes]}, repeats={args.repeats}",
            flush=True,
        )
        decision_records.extend(
            replay_runner.run_suite(
                selected_cases,
                planner_groups=groups,
                guide_modes=guide_modes,
                repeats=args.repeats,
                on_progress=_log_progress,
            )
        )

    if args.run_guide_ablation and len(guide_modes) < 2 and args.mode != "deterministic_only":
        missing_mode = (
            PromptGuideMode.GUIDE_FULL
            if PromptGuideMode.GUIDE_FULL not in guide_modes
            else PromptGuideMode.GUIDE_MINIMAL
        )
        ab_groups = [g for g in groups if g != PlannerGroup.DETERMINISTIC_BASELINE]
        if ab_groups:
            print(
                f"[M4-D] Prompt Guide Ablation ({missing_mode.value}): cases={len(selected_cases)}, groups={[g.value for g in ab_groups]}",
                flush=True,
            )
            guide_ablation_records.extend(
                replay_runner.run_suite(
                    selected_cases,
                    planner_groups=ab_groups,
                    guide_modes=[missing_mode],
                    repeats=1,
                    on_progress=_log_progress,
                )
            )

    if args.run_vlm_ablation and args.mode != "deterministic_only":
        l3_cases = [c for c in all_cases if c.capability_dimension == CapabilityDimension.L3_PERCEPTION_GROUNDED_REASONING]
        if args.cases.strip():
            l3_cases = [c for c in l3_cases if c in selected_cases] or l3_cases
        print(
            f"[M4-D] L3 VLM Semantic Causal Ablation: cases={len(l3_cases)}, conditions={len(VLMAblationCondition)}, "
            f"repeats={args.vlm_ablation_repeats}",
            flush=True,
        )
        vlm_ablation_records.extend(
            replay_runner.run_vlm_ablation(
                l3_cases,
                guide_mode=PromptGuideMode(args.vlm_ablation_guide_mode),
                repeats=args.vlm_ablation_repeats,
                on_progress=_log_progress,
            )
        )

    out_dir = Path(args.output_dir).resolve()
    if args.run_subdir.strip():
        out_dir = out_dir / args.run_subdir.strip()
    elif args.timestamped:
        out_dir = out_dir / datetime.now(timezone.utc).strftime("run_%Y%m%d_%H%M%S")
    out_dir.mkdir(parents=True, exist_ok=True)

    if args.closed_loop:
        scenarios = build_closed_loop_scenarios()
        if args.closed_loop_scenarios.strip():
            allowed_cl = {x.strip() for x in args.closed_loop_scenarios.split(",") if x.strip()}
            scenarios = [s for s in scenarios if s["scenario_id"] in allowed_cl]
        cl_groups = [PlannerGroup(x.strip()) for x in args.closed_loop_groups.split(",") if x.strip()]
        if args.mode == "deterministic_only":
            cl_groups = [PlannerGroup.DETERMINISTIC_BASELINE]

        cl_runner = ClosedLoopBenchmarkRunner(
            mode=args.mode,
            output_dir=out_dir,
            width=args.closed_loop_width,
            height=args.closed_loop_height,
            perception_client_factory=fake_p,
            agent_client_factory=fake_a,
            single_vlm_client_factory=fake_s,
        )
        print(
            f"[M4-D] Layer B Closed-Loop MuJoCo: scenarios={[s['scenario_id'] for s in scenarios]}, "
            f"groups={[g.value for g in cl_groups]}",
            flush=True,
        )
        for scen in scenarios:
            for grp in cl_groups:
                print(f"  -> Running {scen['scenario_id']} with {grp.value}...", flush=True)
                ep = cl_runner.run_scenario(
                    scen,
                    planner_group=grp,
                    guide_mode=PromptGuideMode.GUIDE_MINIMAL,
                )
                closed_loop_episodes.append(ep)
                print(
                    f"     done: status={ep.mission_status}, goal={ep.goal_achieved}, "
                    f"attr={ep.failure_attribution.primary_category.value}, skills={ep.skills_executed}",
                    flush=True,
                )

    result = assemble_benchmark_run(
        decision_records=decision_records,
        vlm_ablation_records=vlm_ablation_records,
        guide_ablation_records=guide_ablation_records,
        closed_loop_episodes=closed_loop_episodes,
        execution_mode=args.mode,
    )
    written = BenchmarkExporter.write_run_directory(
        result,
        out_dir=out_dir,
        cases=all_cases,
        export_zip=not args.no_export_zip,
    )
    zip_check = verify_benchmark_zip_integrity(written["zip"]) if "zip" in written else None

    print(
        json.dumps(
            {
                "benchmark_run_id": result.benchmark_run_id,
                "execution_mode": result.execution_mode,
                "contains_fake_provider": result.contains_fake_provider,
                "decision_records": len(result.decision_records),
                "vlm_ablation_records": len(result.vlm_ablation_records),
                "guide_ablation_records": len(result.guide_ablation_records),
                "closed_loop_episodes": len(result.closed_loop_episodes),
                "real_scorecards": list(result.real_scorecards.keys()),
                "fake_validation_scorecards": list(result.fake_validation_scorecards.keys()),
                "output_dir": str(out_dir),
                "zip_path": str(written["zip"]) if "zip" in written else None,
                "zip_integrity_ok": bool(zip_check["ok"]) if zip_check else None,
            },
            indent=2,
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
