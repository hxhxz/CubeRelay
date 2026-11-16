#!/usr/bin/env python3
"""Independent A/C acceptance for physical place/release/regrasp and held views."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np

from cube_relay.embodied.failure_aware_v6 import FailureAwareRulePlanner, FailureAwareSkillAgent
from cube_relay.embodied.mujoco_v2 import MuJoCoEmbodiedBackend
from cube_relay.embodied.vlm import HeuristicSceneVLM


def failure_seeds(path: Path) -> list[int]:
    return [int(json.loads(line)["seed"]) for line in path.read_text().splitlines() if line.strip()]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--failures", type=Path,
                        default=Path("results/task_agent_v7_rule_100_failures.jsonl"))
    parser.add_argument("--episodes", type=int, default=16)
    parser.add_argument("--output", type=Path,
                        default=Path("results/foundations_v7_a_c.jsonl"))
    parser.add_argument("--replays", type=Path,
                        default=Path("results/replays/foundations_v7"))
    args = parser.parse_args()
    seeds = failure_seeds(args.failures)[:args.episodes]
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.replays.mkdir(parents=True, exist_ok=True)
    with args.output.open("w", encoding="utf-8") as output:
        for seed in seeds:
            replay = args.replays / f"seed_{seed}.mp4"
            backend = MuJoCoEmbodiedBackend(width=320, height=240, video_path=replay)
            backend.reset_random(seed, 15)
            grasp = FailureAwareSkillAgent(
                backend, HeuristicSceneVLM(), FailureAwareRulePlanner()
            ).run(seed, 15, reset_scene=False)
            align = backend.task_align_scan_axes() if grasp.final_success else {"success": False}
            place = backend.task_place_release() if align["success"] else {"success": False}
            released = backend.task_observe_released() if place["success"] else []
            regrasp = backend.task_regrasp() if place["success"] else {"success": False}
            reorient = (
                backend.task_reorient("pitch", 1.5707963267948966)
                if regrasp["success"] else {"success": False}
            )
            held = backend.task_observe_held() if reorient["success"] else []
            row = {
                "seed": seed,
                "grasp_success": grasp.final_success,
                "align": align,
                "place": place,
                "released_observation_count": len(released),
                "regrasp": regrasp,
                "reorient": reorient,
                "held_observation_count": len(held),
                "held_observation_diagnostics": backend.last_observation_diagnostics,
                "replay": str(replay),
            }
            output.write(json.dumps(
                row, separators=(",", ":"),
                default=lambda value: value.item() if isinstance(value, np.generic) else str(value),
            ) + "\n")
            backend.write_video()
            backend.renderer.close()
            print(json.dumps({key: row[key] for key in (
                "seed", "grasp_success", "released_observation_count",
                "held_observation_count",
            )}))


if __name__ == "__main__":
    main()
