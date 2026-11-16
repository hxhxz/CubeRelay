#!/usr/bin/env python3
"""Run the Week 3 fixed-seed benchmark and write JSON/CSV summaries."""

import argparse
import csv
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from cube_relay.experiments.benchmark import run_case, task_matrix  # noqa: E402

parser = argparse.ArgumentParser()
parser.add_argument("--output", type=Path, required=True)
args = parser.parse_args()
args.output.mkdir(parents=True, exist_ok=True)
rows = [run_case(baseline, task, seed).as_dict()
        for baseline in ("fixed-plan", "replan") for task, seed in task_matrix()]
(args.output / "results.json").write_text(json.dumps(rows, indent=2), encoding="utf-8")
with (args.output / "results.csv").open("w", newline="", encoding="utf-8") as handle:
    writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
    writer.writeheader(); writer.writerows(rows)
summary = {}
for baseline in ("fixed-plan", "replan"):
    for task in ("A", "B", "C"):
        selected = [row for row in rows if row["baseline"] == baseline and row["task"] == task]
        summary[f"{baseline}:{task}"] = {
            "cases": len(selected), "successes": sum(row["success"] for row in selected),
            "success_rate": sum(row["success"] for row in selected) / len(selected),
            "mean_runtime_ms": sum(row["runtime_ms"] for row in selected) / len(selected),
        }
(args.output / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
print(json.dumps(summary, indent=2))

