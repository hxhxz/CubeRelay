#!/usr/bin/env python3
"""Analyze exported CubeRelay M4-C experiment ZIP bundles and plot causal graphs."""

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


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Analyze CubeRelay M4-C ZIP bundles (no runtime MuJoCo dependency)."
    )
    parser.add_argument(
        "zips",
        nargs="*",
        type=Path,
        help="Exported experiment ZIP paths (or omit and pass --index).",
    )
    parser.add_argument(
        "--index",
        type=Path,
        default=None,
        help="Optional experiment_index.json path emitted by run_m4c_experiments.py.",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=ROOT / "results" / "m4c_experiments" / "analysis",
        help="Directory for plots, metrics JSON, and causal_analysis_report.md.",
    )
    parser.add_argument(
        "--baseline",
        default="baseline",
        help="Condition name treated as the baseline reference for Delta-X computation.",
    )
    args = parser.parse_args()

    zip_paths = list(args.zips)
    if args.index is not None:
        idx = json.loads(args.index.read_text(encoding="utf-8"))
        zip_paths.extend(Path(item["zip_path"]) for item in idx.get("results", []))
    if not zip_paths:
        parser.error("Provide one or more ZIP paths or --index experiment_index.json")

    summary = analyze_zip_bundles(
        zip_paths,
        output_dir=args.output_dir,
        baseline_name=args.baseline,
    )
    print(json.dumps({
        "report_path": summary["report_path"],
        "plots": summary["plots"],
        "x_deltas": summary["x_deltas"],
    }, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
