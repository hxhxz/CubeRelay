#!/usr/bin/env python3
"""Record one replayable v7 physical active-scan episode."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

from evaluate_task_agent_v7 import load_local_env
from cube_relay.embodied.mujoco_v2 import MuJoCoEmbodiedBackend
from cube_relay.embodied.task_agent_v7 import EmbodiedTaskAgent, GeminiTaskPlanner, RuleTaskPlanner


def main() -> None:
    load_local_env()
    parser = argparse.ArgumentParser()
    parser.add_argument("--seed", type=int, default=1)
    parser.add_argument("--planner", choices=("gemini", "rule"), default="gemini")
    parser.add_argument("--output", type=Path, default=Path("runs/task_agent_v7_demo"))
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    backend = MuJoCoEmbodiedBackend(width=480, height=360, video_path=args.output / "episode.mp4")
    if args.planner == "gemini":
        planner = GeminiTaskPlanner(
            os.environ["CUBERELAY_VLM_ENDPOINT"], os.environ["CUBERELAY_VLM_MODEL"],
            os.environ["CUBERELAY_VLM_API_KEY"],
        )
    else:
        planner = RuleTaskPlanner()
    result = EmbodiedTaskAgent(backend, planner).run(args.seed)
    backend.write_video()
    (args.output / "episode.json").write_text(
        result.model_dump_json(indent=2), encoding="utf-8"
    )
    print(result.model_dump_json(indent=2, exclude={"sticker_evidence", "vlm_traces"}))


if __name__ == "__main__":
    main()
