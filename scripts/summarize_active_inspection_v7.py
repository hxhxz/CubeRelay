#!/usr/bin/env python3
"""Add stage and observation metrics to saved active-inspection evaluations."""

from __future__ import annotations

import argparse
import json
from collections import Counter, defaultdict
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("paths", nargs="+", type=Path)
    args = parser.parse_args()
    for path in args.paths:
        report = json.loads(path.read_text(encoding="utf-8"))
        attempts: Counter[str] = Counter()
        successes: Counter[str] = Counter()
        observation_metrics: dict[str, dict[str, int]] = defaultdict(
            lambda: {"correct": 0, "incorrect": 0, "events": 0}
        )
        first_failures: Counter[str] = Counter()
        for run in report["runs"]:
            if run["first_failure_stage"] is None:
                run["first_failure_stage"] = "SCAN_INCOMPLETE_AFTER_MAX_CYCLES"
            first_failures[run["first_failure_stage"]] += 1
            for event in run["events"]:
                skill = event["skill"]
                attempts[skill] += 1
                successes[skill] += int(event["success"])
                if skill.startswith("observe_"):
                    observation_metrics[skill]["events"] += 1
                    observation_metrics[skill]["correct"] += event["correct_observed"]
                    observation_metrics[skill]["incorrect"] += event["incorrect_observed"]
        report["summary"]["stage_success"] = {
            skill: {
                "successes": successes[skill], "attempts": attempts[skill],
                "rate": successes[skill] / attempts[skill],
            }
            for skill in attempts
        }
        report["summary"]["observation_patch_metrics"] = dict(observation_metrics)
        report["summary"]["first_failure_stages"] = dict(first_failures)
        report["summary"]["regrasp_recovery_gain"] = (
            report["summary"]["regrasp_final_successes"]
            - report["summary"]["regrasp_first_candidate_successes"]
        )
        path.write_text(json.dumps(report, indent=2), encoding="utf-8")
        print(json.dumps({"path": str(path), **report["summary"]}, indent=2))


if __name__ == "__main__":
    main()
