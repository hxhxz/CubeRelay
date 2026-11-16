#!/usr/bin/env python3
"""Run and record one Skill-Based Embodied Agent grasp episode."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from cube_relay.embodied.skill_agent import (
    ConstrainedHeuristicVLMProvider,
    FixedPipelinePlanner,
    RuleBasedSkillPlanner,
    SkillBasedGraspAgent,
    VLMAgentPlanner,
)
from cube_relay.embodied.vlm import HeuristicSceneVLM


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--seed", type=int, default=1)
    parser.add_argument(
        "--planner", choices=("fixed", "rule", "vlm"), default="rule"
    )
    parser.add_argument("--output", type=Path, default=Path("runs/skill_agent_demo"))
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    planners = {
        "fixed": FixedPipelinePlanner,
        "rule": RuleBasedSkillPlanner,
        "vlm": lambda: VLMAgentPlanner(ConstrainedHeuristicVLMProvider()),
    }
    from cube_relay.embodied.mujoco_v2 import MuJoCoEmbodiedBackend
    backend = MuJoCoEmbodiedBackend(video_path=args.output / "episode.mp4")
    result = SkillBasedGraspAgent(
        backend, HeuristicSceneVLM(), planners[args.planner]()
    ).run(args.seed)
    (args.output / "episode.json").write_text(
        result.model_dump_json(indent=2), encoding="utf-8"
    )
    backend.write_video()
    print(result.model_dump_json(indent=2, exclude={"skill_logs", "contact_trace"}))


if __name__ == "__main__":
    main()
