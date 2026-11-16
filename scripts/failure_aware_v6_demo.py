#!/usr/bin/env python3
"""Record one v6 failure-aware grasp episode."""

from __future__ import annotations

import argparse
from pathlib import Path

from cube_relay.embodied.failure_aware_v6 import (
    FailureAwareRulePlanner,
    FailureAwareSkillAgent,
    FixedBudgetPlanner,
)
from cube_relay.embodied.vlm import HeuristicSceneVLM


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--seed", type=int, required=True)
    parser.add_argument("--planner", choices=("fixed1", "fixed3", "rule3"), default="rule3")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    planners = {
        "fixed1": lambda: FixedBudgetPlanner(1),
        "fixed3": lambda: FixedBudgetPlanner(3),
        "rule3": FailureAwareRulePlanner,
    }
    from cube_relay.embodied.mujoco_v2 import MuJoCoEmbodiedBackend
    backend = MuJoCoEmbodiedBackend(video_path=args.output / "episode.mp4")
    result = FailureAwareSkillAgent(
        backend, HeuristicSceneVLM(), planners[args.planner]()
    ).run(args.seed)
    (args.output / "episode.json").write_text(
        result.model_dump_json(indent=2), encoding="utf-8"
    )
    backend.write_video()
    print(result.model_dump_json(
        indent=2, exclude={"skill_logs", "contact_trace", "vlm_call_traces"}
    ))


if __name__ == "__main__":
    main()
