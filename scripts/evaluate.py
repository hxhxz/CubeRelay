#!/usr/bin/env python3
"""Run baseline episodes with failures/interventions and emit trajectories/metrics."""

import argparse
import json
import sys
from dataclasses import asdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from cube_relay.cube import CubeEngine  # noqa: E402
from cube_relay.embodied.coordinator import BaselineCoordinator  # noqa: E402
from cube_relay.embodied.execution import (  # noqa: E402
    DeterministicTurnExecutor, FailureInjectingExecutor,
)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--episodes", type=int, default=10)
    parser.add_argument("--backend", choices=("deterministic", "mujoco"), default="deterministic")
    parser.add_argument("--failure-rate", type=float, default=0.1)
    parser.add_argument("--intervention-rate", type=float, default=0.05)
    parser.add_argument("--output", type=Path, default=Path("runs"))
    args = parser.parse_args()
    if args.backend == "mujoco":
        from cube_relay.embodied.mujoco_executor import MuJoCoTurnExecutor
        base = MuJoCoTurnExecutor()
    else:
        base = DeterministicTurnExecutor()
    engine = CubeEngine()
    summaries = []
    for seed in range(args.episodes):
        executor = FailureInjectingExecutor(base, args.failure_rate, seed)
        state, _ = engine.scramble(seed, 12)
        result = BaselineCoordinator(executor).run(
            state, seed=seed, intervention_probability=args.intervention_rate
        )
        path = args.output / f"episode_{seed:04d}.jsonl"
        result.trajectory.write_jsonl(path)
        summaries.append(asdict(result.metrics))
    args.output.mkdir(parents=True, exist_ok=True)
    (args.output / "metrics.json").write_text(json.dumps(summaries, indent=2), encoding="utf-8")
    solved = sum(item["solved"] for item in summaries)
    print(json.dumps({"episodes": args.episodes, "solved": solved,
                      "success_rate": solved / args.episodes}, indent=2))
    return 0 if solved == args.episodes else 1


if __name__ == "__main__":
    raise SystemExit(main())

