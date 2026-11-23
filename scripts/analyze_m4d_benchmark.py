#!/usr/bin/env python3
"""Analyze and summarize saved CubeRelay M4-D Benchmark results."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from cube_relay.benchmark import (
    BenchmarkExporter,
    BenchmarkRunResult,
    load_benchmark_run,
    verify_benchmark_zip_integrity,
)


def summarize_benchmark_payload(result: BenchmarkRunResult) -> dict[str, Any]:
    """Produce concise structured comparison summaries across real scorecards and ablations."""
    groups_summary: dict[str, Any] = {}
    for label, sc in result.real_scorecards.items():
        groups_summary[label] = {
            "source": sc.execution_source_label.value,
            "n": sc.sample_count,
            "metrics": {
                k: {
                    "value": m.value,
                    "num": m.numerator,
                    "den": m.denominator,
                    "ci95": [m.ci_95_low, m.ci_95_high],
                }
                for k, m in {
                    **sc.decision_metrics,
                    **sc.perception_metrics,
                    **sc.recovery_metrics,
                    **sc.closed_loop_metrics,
                }.items()
            },
            "dimensions": {
                d: {
                    "pass_rate": ds.pass_rate.value,
                    "passed": ds.passed_count,
                    "comparable": ds.pass_rate.denominator,
                    "incomparable": ds.incomparable_count,
                    "not_run": ds.not_run_count,
                    "attribution": ds.attribution_counts,
                }
                for d, ds in sc.per_dimension.items()
            },
            "attribution_totals": sc.failure_attribution_counts,
            "latency_ms": sc.latency_summary_ms,
            "tokens": sc.token_summary,
        }

    return {
        "benchmark_run_id": result.benchmark_run_id,
        "execution_mode": result.execution_mode,
        "contains_fake_provider": result.contains_fake_provider,
        "real_groups": groups_summary,
        "fake_validation_groups": list(result.fake_validation_scorecards.keys()),
        "vlm_ablation": result.vlm_ablation_summary,
        "guide_ablation": result.guide_ablation_summary,
        "closed_loop_episodes": [
            {
                "scenario_id": ep.scenario_id,
                "planner_group": ep.planner_group.value,
                "mission_status": ep.mission_status,
                "goal_achieved": ep.goal_achieved,
                "attribution": ep.failure_attribution.primary_category.value,
                "skills": ep.skills_executed,
                "wall_time_s": ep.wall_time_s,
                "sim_time_s": ep.sim_time_s,
            }
            for ep in result.closed_loop_episodes
        ],
        "incomparabilities": result.incomparabilities,
    }


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Analyze CubeRelay M4-D Benchmark outputs")
    parser.add_argument(
        "--input",
        type=Path,
        default=ROOT / "results" / "m4d_benchmark",
        help="Run directory, summary.json, or ZIP file.",
    )
    parser.add_argument("--verify-zip", type=Path, default=None, help="Optional ZIP path to audit SHA-256 and integrity.")
    parser.add_argument("--regenerate-report", action="store_true", help="Rewrite report.md and analysis_summary.json.")
    parser.add_argument("--json", action="store_true", help="Print full JSON analysis.")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    result = load_benchmark_run(args.input)
    analysis = summarize_benchmark_payload(result)

    if args.verify_zip:
        analysis["zip_verification"] = verify_benchmark_zip_integrity(args.verify_zip)

    if args.regenerate_report and Path(args.input).is_dir():
        out_dir = Path(args.input)
        (out_dir / "analysis_summary.json").write_text(
            json.dumps(analysis, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
        (out_dir / "report.md").write_text(
            BenchmarkExporter.build_markdown_report(result),
            encoding="utf-8",
        )

    if args.json:
        print(json.dumps(analysis, indent=2, ensure_ascii=False))
    else:
        print(BenchmarkExporter.build_markdown_report(result))
        if args.verify_zip:
            print("ZIP Verification:", json.dumps(analysis["zip_verification"], indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
