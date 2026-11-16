#!/usr/bin/env python3
"""Paired 2x2 ablation for position and yaw inputs to physical grasping.

Simulator pose is read only in this evaluator. Normal perception/control code
cannot access it. Every condition uses identical seeds and unchanged XML physics.
"""

from __future__ import annotations

import argparse
import json
import math
import time
from collections import Counter
from dataclasses import asdict
from pathlib import Path

import numpy as np

from cube_relay.embodied.perception_v2 import DeterministicCubeLocalizer


CONDITIONS = (
    ("gt_position+gt_yaw", True, True),
    ("gt_position+vision_yaw", True, False),
    ("vision_position+gt_yaw", False, True),
    ("vision_position+vision_yaw", False, False),
)


def json_default(value: object) -> object:
    if isinstance(value, np.generic):
        return value.item()
    raise TypeError(f"{type(value).__name__} is not JSON serializable")


def square_angle_error(first: float, second: float) -> float:
    period = math.pi / 2
    return abs((first - second + period / 2) % period - period / 2)


def classify_failure(reason: str | None, localized: bool, rotation_attempted: bool) -> str:
    if not localized:
        return "vision_localization_failed"
    if not reason:
        return "success" if rotation_attempted else "unknown"
    if "no IK" in reason:
        return "planning_rejected"
    if "bilateral" in reason:
        return "bilateral_contact_missing"
    if "trial lift" in reason:
        return "trial_lift_slip_or_contact_loss"
    if "full lift" in reason:
        return "full_lift_unstable"
    if "rotation" in reason:
        return "rotation_contact_loss_or_slip"
    return "other"


def summarize(rows: list[dict[str, object]]) -> dict[str, object]:
    localized = [row for row in rows if row["localized"]]
    def rate(key: str) -> float:
        return sum(bool(row[key]) for row in rows) / len(rows)
    return {
        "episodes": len(rows),
        "localization_rate": rate("localized"),
        "mean_input_position_error_m": float(np.mean(
            [row["input_position_error_m"] for row in localized]
        )),
        "p95_input_position_error_m": float(np.percentile(
            [row["input_position_error_m"] for row in localized], 95
        )),
        "mean_input_yaw_error_deg": float(np.degrees(np.mean(
            [row["input_yaw_error_rad"] for row in localized]
        ))),
        "p95_input_yaw_error_deg": float(np.degrees(np.percentile(
            [row["input_yaw_error_rad"] for row in localized], 95
        ))),
        "mean_vision_position_error_m": float(np.mean(
            [row["vision_position_error_m"] for row in localized]
        )),
        "mean_vision_yaw_error_deg": float(np.degrees(np.mean(
            [row["vision_yaw_error_rad"] for row in localized]
        ))),
        "left_contact_established_rate": rate("left_contact_established"),
        "right_contact_established_rate": rate("right_contact_established"),
        "mean_left_normal_force_n": float(np.mean([row["left_normal_force_n"] for row in rows])),
        "mean_right_normal_force_n": float(np.mean([row["right_normal_force_n"] for row in rows])),
        "mean_max_slip_m": float(np.mean([row["max_slip_m"] for row in rows])),
        "trial_lift_success_rate": rate("trial_lift_success"),
        "full_lift_success_rate": rate("full_lift_success"),
        "full_rotation_success_rate": rate("full_rotation_success"),
        "failure_types": dict(Counter(str(row["failure_type"]) for row in rows)),
        "contact_failure_classes": dict(Counter(
            str(row.get("contact_failure_class") or "success") for row in rows
        )),
    }


def run(
    episodes: int, start_seed: int, scramble_steps: int,
    failure_log: Path | None = None,
    pad_friction: float | None = None,
) -> dict[str, object]:
    from cube_relay.embodied.mujoco_v2 import MuJoCoEmbodiedBackend
    from cube_relay.embodied.v2_types import GraspControlConfig

    backend = MuJoCoEmbodiedBackend(
        grasp_config=GraspControlConfig(pad_sliding_friction=pad_friction)
    )
    localizer = DeterministicCubeLocalizer()
    groups: dict[str, list[dict[str, object]]] = {}
    started = time.perf_counter()
    failure_handle = None
    if failure_log is not None:
        failure_log.parent.mkdir(parents=True, exist_ok=True)
        failure_handle = failure_log.open("w", encoding="utf-8")
    for name, use_gt_position, use_gt_yaw in CONDITIONS:
        rows: list[dict[str, object]] = []
        for offset in range(episodes):
            seed = start_seed + offset
            backend.reset_random(seed, scramble_steps)
            frame = backend.capture_rgbd()
            detection = localizer.locate(frame)
            cube = backend._id(backend.mujoco.mjtObj.mjOBJ_BODY, "cube")
            truth_position = backend.data.xpos[cube].copy()
            rotation = backend.data.xmat[cube].reshape(3, 3)
            truth_yaw = math.atan2(float(rotation[1, 0]), float(rotation[0, 0]))
            if detection is None:
                rows.append({
                    "seed": seed, "localized": False, "input_position_error_m": None,
                    "input_yaw_error_rad": None, "vision_position_error_m": None,
                    "vision_yaw_error_rad": None, "left_contact_established": False,
                    "right_contact_established": False, "left_normal_force_n": 0.0,
                    "right_normal_force_n": 0.0, "max_slip_m": 0.0,
                    "trial_lift_success": False, "full_lift_success": False,
                    "full_rotation_success": False, "failure_type": "vision_localization_failed",
                })
                continue
            vision_position = np.asarray(detection.center_world_m)
            position = truth_position if use_gt_position else vision_position
            yaw = truth_yaw if use_gt_yaw else detection.yaw_radians
            grasped = backend.approach_grasp_lift(tuple(position), yaw)
            if grasped:
                backend.rotate_whole_cube_and_reobserve()
            telemetry = backend.last_grasp_telemetry
            contact_failure_class = (
                None if telemetry.full_rotation_success
                else backend.contact_failure_class or "rotation_contact_loss_or_slip"
            )
            row = {
                "seed": seed,
                "localized": True,
                "input_position_error_m": float(np.linalg.norm(position - truth_position)),
                "input_yaw_error_rad": square_angle_error(yaw, truth_yaw),
                "vision_position_error_m": float(np.linalg.norm(
                    vision_position - truth_position
                )),
                "vision_yaw_error_rad": square_angle_error(
                    detection.yaw_radians, truth_yaw
                ),
                "vision_position_m": vision_position.tolist(),
                "truth_position_m_evaluation_only": truth_position.tolist(),
                "vision_yaw_rad": detection.yaw_radians,
                "truth_yaw_rad_evaluation_only": truth_yaw,
                "selected_candidate": asdict(backend.last_selected_grasp_candidate)
                    if backend.last_selected_grasp_candidate else None,
                "left_contact_established": telemetry.left_contact_rate > 0,
                "right_contact_established": telemetry.right_contact_rate > 0,
                "left_contact_rate": telemetry.left_contact_rate,
                "right_contact_rate": telemetry.right_contact_rate,
                "left_normal_force_n": telemetry.left_normal_force_n,
                "right_normal_force_n": telemetry.right_normal_force_n,
                "max_slip_m": telemetry.max_relative_slip_m,
                "trial_lift_success": telemetry.trial_lift_success,
                "full_lift_success": telemetry.full_lift_success,
                "full_rotation_success": telemetry.full_rotation_success,
                "failure_reason": telemetry.failure_reason,
                "failure_type": classify_failure(
                    telemetry.failure_reason, True, telemetry.full_rotation_success
                ),
                "contact_failure_class": contact_failure_class,
                "phase_trace": telemetry.phase_trace,
                "final_contact_sample": backend.contact_debug_trace[-1]
                    if backend.contact_debug_trace else None,
            }
            rows.append(row)
            if failure_handle is not None and contact_failure_class is not None:
                failure_handle.write(json.dumps({
                    "condition": name,
                    "seed": seed,
                    "contact_failure_class": contact_failure_class,
                    "failure_reason": telemetry.failure_reason,
                    "trace": backend.contact_debug_trace,
                }, default=json_default) + "\n")
        groups[name] = rows
    if failure_handle is not None:
        failure_handle.close()
    return {
        "paired_seeds": list(range(start_seed, start_seed + episodes)),
        "physics": "unchanged simulation/cube_relay_v2.xml for all four conditions",
        "truth_boundary": (
            "GT position/yaw are evaluator-only interventions; normal camera, localizer, "
            "planner and controller never read simulator cube pose"
        ),
        "summaries": {name: summarize(rows) for name, rows in groups.items()},
        "runs": groups,
        "failure_trace_jsonl": str(failure_log) if failure_log else None,
        "elapsed_seconds": time.perf_counter() - started,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--episodes", type=int, default=100)
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--scramble-steps", type=int, default=15)
    parser.add_argument("--output", type=Path, default=Path("results/grasp_yaw_ablation.json"))
    parser.add_argument("--pad-friction", type=float)
    args = parser.parse_args()
    failure_log = args.output.with_name(args.output.stem + "_failures.jsonl")
    report = run(
        args.episodes, args.seed, args.scramble_steps, failure_log, args.pad_friction
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(report, indent=2, default=json_default), encoding="utf-8"
    )
    print(json.dumps(
        {"summaries": report["summaries"], "elapsed_seconds": report["elapsed_seconds"]},
        indent=2, default=json_default,
    ))


if __name__ == "__main__":
    main()
