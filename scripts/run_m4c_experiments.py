#!/usr/bin/env python3
"""Run repeatable M4-C position-perturbation & negative-control experiments."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from cube_relay.experiment.analyzer import analyze_zip_bundles
from cube_relay.experiment.perturbation import (
    PERTURBATION_CONDITIONS,
    run_perturbation_suite,
)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Run CubeRelay M4-C position perturbation & visual fault experiments."
    )
    parser.add_argument(
        "--conditions",
        nargs="+",
        default=list(PERTURBATION_CONDITIONS.keys()),
        choices=list(PERTURBATION_CONDITIONS.keys()),
        help="Perturbation conditions to run sequentially in isolated MuJoCo sessions.",
    )
    parser.add_argument("--seed", type=int, default=0, help="Shared MuJoCo scramble seed.")
    parser.add_argument(
        "--mission-type",
        default="INSPECT_CUBE",
        choices=["INSPECT_CUBE", "VERIFY_PHYSICAL_U_TURN", "SOLVE_CUBE"],
        help="Mission type executed per condition.",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=ROOT / "results" / "m4c_experiments",
        help="Destination directory for runs, ZIP bundles, and optional analysis.",
    )
    parser.add_argument("--sample-hz", type=float, default=50.0, help="Robot trajectory sample rate (Hz).")
    parser.add_argument("--no-rgbd", action="store_true", help="Exclude raw PNG/NPY RGB-D frames from exported ZIPs.")
    parser.add_argument(
        "--no-audit-gt",
        action="store_true",
        help="Disable simulator audit-only ground-truth pose recording.",
    )
    parser.add_argument(
        "--analyze",
        action="store_true",
        help="Also run automated causal analysis & plot generation on exported ZIPs.",
    )
    args = parser.parse_args()

    index = run_perturbation_suite(
        args.conditions,
        seed=args.seed,
        mission_type=args.mission_type,
        output_dir=args.output_dir,
        include_audit_ground_truth=not args.no_audit_gt,
        include_rgbd=not args.no_rgbd,
        include_high_freq_trajectory=True,
        trajectory_sample_hz=args.sample_hz,
    )
    print(json.dumps(index, indent=2, ensure_ascii=False))
    if args.analyze:
        zips = [item["zip_path"] for item in index["results"]]
        summary = analyze_zip_bundles(zips, output_dir=args.output_dir / "analysis")
        print(json.dumps({"analysis_report": summary["report_path"], "x_deltas": summary["x_deltas"]}, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
