#!/usr/bin/env python3
"""Evaluate CubeRelay v7 active scan with fixed paired random scenes."""

from __future__ import annotations

import argparse
import json
import os
import time
from collections import Counter
from pathlib import Path

import numpy as np

from cube_relay.embodied.mujoco_v2 import MuJoCoEmbodiedBackend
from cube_relay.embodied.task_agent_v7 import (
    EmbodiedTaskAgent,
    FixedTaskPlanner,
    GeminiTaskPlanner,
    RuleTaskPlanner,
)


def load_local_env(path: Path = Path(".env")) -> None:
    if not path.exists():
        return
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


def main() -> None:
    load_local_env()
    parser = argparse.ArgumentParser()
    parser.add_argument("--episodes", type=int, default=100)
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--planner", choices=("gemini", "rule", "fixed"), default="gemini")
    parser.add_argument("--output", type=Path, default=Path("results/task_agent_v7_evaluation.json"))
    args = parser.parse_args()
    endpoint = os.getenv("CUBERELAY_VLM_ENDPOINT", "")
    model = os.getenv("CUBERELAY_VLM_MODEL", "")
    api_key = os.getenv("CUBERELAY_VLM_API_KEY", "")
    if args.planner == "gemini" and not (endpoint and model and api_key):
        raise SystemExit("Gemini planner requires CUBERELAY_VLM_ENDPOINT/MODEL/API_KEY")

    runs = []
    calls_path = args.output.with_name(args.output.stem + "_vlm_calls.jsonl")
    failures_path = args.output.with_name(args.output.stem + "_failures.jsonl")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    started = time.perf_counter()
    with calls_path.open("w", encoding="utf-8") as calls, failures_path.open("w", encoding="utf-8") as failures:
        for seed in range(args.seed, args.seed + args.episodes):
            backend = MuJoCoEmbodiedBackend(width=320, height=240)
            metadata = backend.reset_random(seed, 15)
            if args.planner == "gemini":
                planner = GeminiTaskPlanner(endpoint, model, api_key)
            elif args.planner == "rule":
                planner = RuleTaskPlanner()
            else:
                planner = FixedTaskPlanner()
            result = EmbodiedTaskAgent(backend, planner).run(seed, reset_scene=False)
            data = result.model_dump(mode="json", exclude={"events", "sticker_evidence", "vlm_traces"})
            truth = str(metadata["truth_for_evaluation_only"])
            reconstructed = result.reconstructed_facelets
            observed = [item.get("color") for item in result.sticker_evidence]
            compared = sum(color is not None for color in observed)
            correct = sum(
                color is not None and color == truth[index]
                for index, color in enumerate(observed)
            )
            data.update({
                "complete_scan": result.unknown_stickers == 0,
                "exact_reconstruction": reconstructed == truth,
                "sticker_accuracy_54": correct / 54,
                "observed_sticker_accuracy": correct / compared if compared else 0.0,
            })
            runs.append(data)
            for trace in result.vlm_traces:
                calls.write(json.dumps({"seed": seed, **trace.model_dump(mode="json")}) + "\n")
            if not result.success:
                failures.write(json.dumps({
                    **data,
                    "events": [item.model_dump(mode="json") for item in result.events],
                    "sticker_evidence": list(result.sticker_evidence),
                }) + "\n")
            backend.renderer.close()

    summary = {
        "planner": args.planner,
        "model": model if args.planner == "gemini" else None,
        "episodes": len(runs),
        "complete_scan_rate": float(np.mean([row["complete_scan"] for row in runs])),
        "legal_reconstruction_rate": float(np.mean([row["legal"] for row in runs])),
        "exact_54_rate": float(np.mean([row["exact_reconstruction"] for row in runs])),
        "mean_sticker_accuracy_54": float(np.mean([row["sticker_accuracy_54"] for row in runs])),
        "mean_observed_sticker_accuracy": float(np.mean([
            row["observed_sticker_accuracy"] for row in runs
        ])),
        "regrasp_success_rate": (
            sum(row["regrasp_successes"] for row in runs)
            / max(1, sum(row["regrasp_attempts"] for row in runs))
        ),
        "mean_actions": float(np.mean([row["action_count"] for row in runs])),
        "mean_elapsed_seconds": float(np.mean([row["elapsed_seconds"] for row in runs])),
        "total_vlm_calls": sum(row["vlm_calls"] for row in runs),
        "mean_vlm_latency_ms": float(np.mean([row["vlm_latency_ms"] for row in runs])),
        "total_input_tokens": sum(row["input_tokens"] for row in runs),
        "total_output_tokens": sum(row["output_tokens"] for row in runs),
        "failure_reasons": dict(Counter(row["failure_code"] for row in runs if row["failure_code"])),
        "elapsed_seconds": time.perf_counter() - started,
    }
    report = {"summary": summary, "runs": runs}
    args.output.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
