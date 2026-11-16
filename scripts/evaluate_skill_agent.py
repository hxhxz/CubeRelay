#!/usr/bin/env python3
"""Paired evaluation of three planners over the same deterministic Skills."""

from __future__ import annotations

import argparse
import json
import time
from collections import Counter
from pathlib import Path

import numpy as np

from cube_relay.embodied.skill_agent import (
    ConstrainedHeuristicVLMProvider,
    FixedPipelinePlanner,
    RuleBasedSkillPlanner,
    SkillBasedGraspAgent,
    VLMAgentPlanner,
)
from cube_relay.embodied.vlm import HeuristicSceneVLM


def planner_factory(name: str):
    if name == "fixed_pipeline":
        return FixedPipelinePlanner()
    if name == "rule_based_skill_planner":
        return RuleBasedSkillPlanner()
    if name == "vlm_agent_planner":
        # Explicit offline Mock: replace this provider with a hosted VLM adapter
        # without changing Skills or safety gates.
        return VLMAgentPlanner(ConstrainedHeuristicVLMProvider())
    raise ValueError(name)


def summarize(rows: list[dict[str, object]]) -> dict[str, object]:
    return {
        "episodes": len(rows),
        "first_attempt_success_rate": float(np.mean([
            bool(row["first_attempt_success"]) for row in rows
        ])),
        "final_success_rate": float(np.mean([bool(row["final_success"]) for row in rows])),
        "mean_attempts": float(np.mean([int(row["attempts"]) for row in rows])),
        "abnormal_push_rate": float(np.mean([bool(row["abnormal_push"]) for row in rows])),
        "mean_planner_calls": float(np.mean([
            float(row["decision_cost"]["planner_calls"]) for row in rows
        ])),
        "mean_vlm_calls": float(np.mean([
            float(row["decision_cost"]["vlm_calls"]) for row in rows
        ])),
        "mean_decision_ms": float(np.mean([
            float(row["decision_cost"]["decision_ms"]) for row in rows
        ])),
        "failure_codes": dict(Counter(
            code for row in rows if not row["final_success"]
            for code in row["failure_history"]
        )),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--episodes", type=int, default=100)
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--output", type=Path, default=Path("results/skill_agent_ablation.json"))
    args = parser.parse_args()

    from cube_relay.embodied.mujoco_v2 import MuJoCoEmbodiedBackend

    names = ("fixed_pipeline", "rule_based_skill_planner", "vlm_agent_planner")
    groups: dict[str, list[dict[str, object]]] = {}
    failures_path = args.output.with_name(args.output.stem + "_failures.jsonl")
    failures_path.parent.mkdir(parents=True, exist_ok=True)
    started = time.perf_counter()
    with failures_path.open("w", encoding="utf-8") as failures:
        for name in names:
            backend = MuJoCoEmbodiedBackend()
            rows: list[dict[str, object]] = []
            for offset in range(args.episodes):
                seed = args.seed + offset
                result = SkillBasedGraspAgent(
                    backend, HeuristicSceneVLM(), planner_factory(name)
                ).run(seed)
                row = result.model_dump(mode="json", exclude={"skill_logs", "contact_trace"})
                rows.append(row)
                if not result.final_success:
                    failures.write(json.dumps({
                        **row,
                        "skill_logs": [item.model_dump(mode="json") for item in result.skill_logs],
                        "contact_trace": result.contact_trace,
                    }) + "\n")
            groups[name] = rows
    report = {
        "paired_seeds": list(range(args.seed, args.seed + args.episodes)),
        "shared_skills": [
            "observe_cube", "plan_grasp", "approach_grasp", "verify_pose",
            "establish_grasp", "test_lift", "retreat",
        ],
        "vlm_planner_fidelity": "MOCK:constrained deterministic provider; replaceable adapter boundary",
        "safety_boundary": (
            "planners select only candidate index and bounded offsets; backend owns joints, "
            "collision/displacement stop, bilateral contact and lift gates"
        ),
        "summaries": {name: summarize(rows) for name, rows in groups.items()},
        "runs": groups,
        "failure_traces": str(failures_path),
        "elapsed_seconds": time.perf_counter() - started,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps({
        "summaries": report["summaries"],
        "elapsed_seconds": report["elapsed_seconds"],
        "failure_traces": str(failures_path),
    }, indent=2))


if __name__ == "__main__":
    main()
