#!/usr/bin/env python3
"""Paired physical evaluation for sequential/NBV continuous inspection."""

from __future__ import annotations

import argparse
import json
from collections import Counter
from dataclasses import asdict
from pathlib import Path

import numpy as np

from cube_relay.embodied.active_inspection_v7 import ContinuousActiveInspector
from cube_relay.embodied.mujoco_v2 import MuJoCoEmbodiedBackend


DIFFICULT_SEEDS = (4, 5, 8, 9, 10, 12, 13, 15, 18, 21,
                   25, 31, 37, 42, 47, 56, 63, 72, 83, 95)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", choices=("sequential", "nbv", "difficult"), default="nbv")
    parser.add_argument("--episodes", type=int, default=None)
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--replays", type=Path, required=True)
    args = parser.parse_args()
    count = args.episodes or (20 if args.mode != "nbv" else 50)
    seeds = list(DIFFICULT_SEEDS[:count]) if args.mode == "difficult" else list(
        range(args.seed, args.seed + count)
    )
    planner_mode = "nbv" if args.mode in {"nbv", "difficult"} else "sequential"
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.replays.mkdir(parents=True, exist_ok=True)
    rows = []
    for seed in seeds:
        replay = args.replays / f"seed_{seed}.mp4"
        backend = MuJoCoEmbodiedBackend(width=320, height=240, video_path=replay)
        metadata = backend.reset_random(seed, 15)
        truth = str(metadata["truth_for_evaluation_only"])
        result = ContinuousActiveInspector(backend, planner_mode).run(seed, reset_scene=False)
        data = asdict(result)
        event_rows = []
        for event in data["events"]:
            correct = incorrect = observed = 0
            for item in event["detail"].get("visual_evidence", []):
                if item["color"] is None:
                    continue
                observed += 1
                truth_index = "URFDLB".index(item["face"]) * 9 + item["index"]
                if item["color"] == truth[truth_index]:
                    correct += 1
                else:
                    incorrect += 1
            event["correct_observed"] = correct
            event["incorrect_observed"] = incorrect
            event["detail"].pop("visual_evidence", None)
            event_rows.append(event)
        fused = data["evidence"]
        correct_54 = sum(
            item["color"] is not None
            and item["color"] == truth["URFDLB".index(item["face"]) * 9 + item["index"]]
            for item in fused
        )
        observed_54 = sum(item["color"] is not None for item in fused)
        data.update({
            "seed": seed, "mode": planner_mode, "events": event_rows,
            "correct_stickers_54": correct_54,
            "observed_stickers_54": observed_54,
            "unknown_stickers": 54 - observed_54,
            "sticker_accuracy_54": correct_54 / 54,
            "exact_54": result.reconstructed_facelets == truth,
            "replay": str(replay),
        })
        rows.append(data)
        backend.write_video()
        backend.renderer.close()
        print(json.dumps({"seed": seed, "success": result.success,
                          "first_failure": result.first_failure_stage,
                          "observed": observed_54, "correct": correct_54}))
    summary = {
        "mode": planner_mode, "episodes": len(rows),
        "complete_scan_rate": float(np.mean([row["unknown_stickers"] == 0 for row in rows])),
        "exact_54_rate": float(np.mean([row["exact_54"] for row in rows])),
        "legal_rate": float(np.mean([row["legal"] for row in rows])),
        "mean_correct_stickers_54": float(np.mean([row["correct_stickers_54"] for row in rows])),
        "mean_unknown": float(np.mean([row["unknown_stickers"] for row in rows])),
        "mean_conflicts": float(np.mean([
            row["events"][-1]["conflicts"] if row["events"] else 0 for row in rows
        ])),
        "mean_actions": float(np.mean([row["action_count"] for row in rows])),
        "regrasp_first_candidate_successes": sum(row["regrasp_first_candidate_successes"] for row in rows),
        "regrasp_final_successes": sum(row["regrasp_final_successes"] for row in rows),
        "first_failure_stages": dict(Counter(row["first_failure_stage"] for row in rows)),
    }
    args.output.write_text(json.dumps({"summary": summary, "runs": rows}, indent=2), encoding="utf-8")
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
