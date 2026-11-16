#!/usr/bin/env python3
"""Paired Failure-Aware Skill Planning v6 evaluation."""

from __future__ import annotations

import argparse
import json
import os
import time
from collections import Counter
from pathlib import Path

import numpy as np

from cube_relay.embodied.failure_aware_v6 import (
    FailureAwareRulePlanner,
    FailureAwareSkillAgent,
    FixedBudgetPlanner,
    OpenAICompatibleFailureAwareVLM,
    RealVLMFailureAwarePlanner,
)
from cube_relay.embodied.vlm import HeuristicSceneVLM


def load_local_env(path: Path = Path(".env")) -> None:
    """Load a local ignored env file without overriding the process environment."""
    if not path.is_file():
        return
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        name, value = line.split("=", 1)
        name = name.strip()
        value = value.strip().strip('"').strip("'")
        if name and name not in os.environ:
            os.environ[name] = value


def summarize(rows: list[dict[str, object]]) -> dict[str, object]:
    first = float(np.mean([bool(row["first_attempt_success"]) for row in rows]))
    final = float(np.mean([bool(row["final_success"]) for row in rows]))
    return {
        "episodes": len(rows),
        "first_attempt_success_rate": first,
        "final_success_rate": final,
        "recovery_gain": final - first,
        "recovery_success_rate": float(np.mean([
            bool(row["recovery_success"]) for row in rows
        ])),
        "mean_attempts": float(np.mean([int(row["attempts"]) for row in rows])),
        "abnormal_push_rate": float(np.mean([
            bool(row["abnormal_push"]) for row in rows
        ])),
        "mean_repeated_attempts": float(np.mean([
            int(row["repeated_attempt_count"]) for row in rows
        ])),
        "episodes_with_repeated_attempt_rate": float(np.mean([
            int(row["repeated_attempt_count"]) > 0 for row in rows
        ])),
        "mean_inference_ms": float(np.mean([
            float(row["decision_cost"]["decision_ms"]) for row in rows
        ])),
        "mean_vlm_calls": float(np.mean([
            float(row["decision_cost"]["vlm_calls"]) for row in rows
        ])),
        "total_input_tokens": int(sum(
            float(row["decision_cost"]["input_tokens"]) for row in rows
        )),
        "total_output_tokens": int(sum(
            float(row["decision_cost"]["output_tokens"]) for row in rows
        )),
        "total_cost_usd": float(sum(
            float(row["decision_cost"]["cost_usd"]) for row in rows
        )),
        "terminal_failure_codes": dict(Counter(
            row["failure_history"][-1]
            for row in rows if not row["final_success"] and row["failure_history"]
        )),
    }


def main() -> None:
    load_local_env()
    parser = argparse.ArgumentParser()
    parser.add_argument("--episodes", type=int, default=100)
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument(
        "--output", type=Path, default=Path("results/failure_aware_v6_ablation.json")
    )
    parser.add_argument("--real-vlm-endpoint", default=os.getenv("CUBERELAY_VLM_ENDPOINT", ""))
    parser.add_argument("--real-vlm-model", default=os.getenv("CUBERELAY_VLM_MODEL", ""))
    parser.add_argument("--api-key-env", default="CUBERELAY_VLM_API_KEY")
    parser.add_argument(
        "--input-cost-per-million", type=float,
        default=(float(os.environ["CUBERELAY_VLM_INPUT_COST_PER_MILLION"])
                 if os.getenv("CUBERELAY_VLM_INPUT_COST_PER_MILLION") else None),
    )
    parser.add_argument(
        "--output-cost-per-million", type=float,
        default=(float(os.environ["CUBERELAY_VLM_OUTPUT_COST_PER_MILLION"])
                 if os.getenv("CUBERELAY_VLM_OUTPUT_COST_PER_MILLION") else None),
    )
    args = parser.parse_args()

    api_key = os.getenv(args.api_key_env, "")
    real_configured = bool(args.real_vlm_endpoint and args.real_vlm_model and api_key)
    from cube_relay.embodied.mujoco_v2 import MuJoCoEmbodiedBackend

    factories = {
        "fixed_1": lambda: FixedBudgetPlanner(1),
        "fixed_3": lambda: FixedBudgetPlanner(3),
        "rule_based_3": FailureAwareRulePlanner,
    }
    if real_configured:
        factories["real_vlm_3"] = lambda: RealVLMFailureAwarePlanner(
            OpenAICompatibleFailureAwareVLM(
                endpoint=args.real_vlm_endpoint,
                model=args.real_vlm_model,
                api_key=api_key,
                input_cost_per_million=args.input_cost_per_million,
                output_cost_per_million=args.output_cost_per_million,
            )
        )

    groups: dict[str, list[dict[str, object]]] = {}
    failures_path = args.output.with_name(args.output.stem + "_failures.jsonl")
    calls_path = args.output.with_name(args.output.stem + "_vlm_calls.jsonl")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    started = time.perf_counter()
    with failures_path.open("w", encoding="utf-8") as failure_file, calls_path.open(
        "w", encoding="utf-8"
    ) as calls_file:
        for name, factory in factories.items():
            backend = MuJoCoEmbodiedBackend()
            rows: list[dict[str, object]] = []
            for offset in range(args.episodes):
                result = FailureAwareSkillAgent(
                    backend, HeuristicSceneVLM(), factory()
                ).run(args.seed + offset)
                row = result.model_dump(
                    mode="json",
                    exclude={"skill_logs", "contact_trace", "vlm_call_traces"},
                )
                rows.append(row)
                for trace in result.vlm_call_traces:
                    calls_file.write(json.dumps({
                        "planner": name, "seed": result.seed,
                        **trace.model_dump(mode="json"),
                    }) + "\n")
                if not result.final_success:
                    failure_file.write(json.dumps({
                        **row,
                        "skill_logs": [x.model_dump(mode="json") for x in result.skill_logs],
                        "contact_trace": result.contact_trace,
                        "vlm_call_traces": [
                            x.model_dump(mode="json") for x in result.vlm_call_traces
                        ],
                    }) + "\n")
            groups[name] = rows

    summaries = {name: summarize(rows) for name, rows in groups.items()}
    pricing_configured = (
        args.input_cost_per_million is not None
        and args.output_cost_per_million is not None
    )
    if "real_vlm_3" in summaries and not pricing_configured:
        summaries["real_vlm_3"]["total_cost_usd"] = None
    fixed_1 = summaries["fixed_1"]["final_success_rate"]
    fixed_3 = summaries["fixed_3"]["final_success_rate"]
    rule = summaries["rule_based_3"]["final_success_rate"]
    attribution = {
        "fixed_retry_gain_fixed3_minus_fixed1": fixed_3 - fixed_1,
        "adaptive_rule_gain_rule3_minus_fixed3": rule - fixed_3,
        "total_rule_gain_rule3_minus_fixed1": rule - fixed_1,
    }
    report = {
        "version": "Failure-Aware Skill Planning v6",
        "paired_seeds": list(range(args.seed, args.seed + args.episodes)),
        "max_attempts": {
            "fixed_1": 1, "fixed_3": 3, "rule_based_3": 3, "real_vlm_3": 3,
        },
        "real_vlm": {
            "status": "evaluated" if real_configured else "not_run_missing_configuration",
            "model": args.real_vlm_model or None,
            "endpoint_configured": bool(args.real_vlm_endpoint),
            "api_key_present": bool(api_key),
            "mock_substitution_used": False,
            "pricing_configured": pricing_configured,
            "input_cost_per_million": args.input_cost_per_million,
            "output_cost_per_million": args.output_cost_per_million,
        },
        "summaries": summaries,
        "attribution": attribution,
        "runs": groups,
        "failure_traces": str(failures_path),
        "vlm_call_traces": str(calls_path),
        "elapsed_seconds": time.perf_counter() - started,
    }
    args.output.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps({
        "summaries": summaries,
        "attribution": attribution,
        "real_vlm": report["real_vlm"],
        "elapsed_seconds": report["elapsed_seconds"],
    }, indent=2))


if __name__ == "__main__":
    main()
