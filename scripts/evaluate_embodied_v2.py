#!/usr/bin/env python3
"""Evaluate the minimum real-physics v2 vertical loop over random scenes."""

from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

import numpy as np

from cube_relay.embodied.perception_v2 import DeterministicCubeLocalizer
from cube_relay.embodied.vlm import HeuristicSceneVLM


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--episodes", type=int, default=20)
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--scramble-steps", type=int, default=15)
    parser.add_argument("--output", type=Path, default=Path("results/embodied_v2.json"))
    args = parser.parse_args()

    from cube_relay.embodied.mujoco_v2 import MuJoCoEmbodiedBackend

    backend = MuJoCoEmbodiedBackend()
    localizer = DeterministicCubeLocalizer()
    vlm = HeuristicSceneVLM()
    episodes: list[dict[str, object]] = []
    started = time.perf_counter()
    for offset in range(args.episodes):
        seed = args.seed + offset
        backend.reset_random(seed, args.scramble_steps)
        frame = backend.capture_rgbd()
        semantics = vlm.understand(frame.rgb)
        detection = localizer.locate(frame) if semantics.cube_visible else None
        cube_body = backend._id(backend.mujoco.mjtObj.mjOBJ_BODY, "cube")
        truth = backend.data.xpos[cube_body].copy()  # evaluator only; never passed to perception
        localization_error = None
        grasped = False
        stable_rotation = False
        if detection is not None:
            localization_error = float(np.linalg.norm(np.asarray(detection.center_world_m) - truth))
            grasped = backend.approach_grasp_lift(
                detection.center_world_m, detection.yaw_radians
            )
            if grasped:
                backend.rotate_whole_cube_and_reobserve()
                stable_rotation = backend.last_grasp_telemetry.success
        episodes.append({
            "seed": seed,
            "localized": detection is not None,
            "localization_error_m_evaluation_truth": localization_error,
            "grasp_lift_rotate_reobserve_success": grasped,
            "stable_rotation_success": stable_rotation,
            "grasp_telemetry": {
                "contact_fraction": backend.last_grasp_telemetry.bilateral_contact_fraction,
                "max_slip_m": backend.last_grasp_telemetry.max_relative_slip_m,
                "lift_height_m": backend.last_grasp_telemetry.lift_height_m,
                "failure_reason": backend.last_grasp_telemetry.failure_reason,
                "yaw_radians": detection.yaw_radians if detection else None,
                "yaw_confidence": detection.yaw_confidence if detection else None,
                "left_contact_rate": backend.last_grasp_telemetry.left_contact_rate,
                "right_contact_rate": backend.last_grasp_telemetry.right_contact_rate,
                "left_normal_force_n": backend.last_grasp_telemetry.left_normal_force_n,
                "right_normal_force_n": backend.last_grasp_telemetry.right_normal_force_n,
                "trial_lift_success": backend.last_grasp_telemetry.trial_lift_success,
                "full_rotation_success": backend.last_grasp_telemetry.full_rotation_success,
                "phase_trace": backend.last_grasp_telemetry.phase_trace,
            },
        })
    errors = [row["localization_error_m_evaluation_truth"] for row in episodes if row["localized"]]
    report = {
        "implementation_level": backend.implementation_level,
        "episodes": args.episodes,
        "localization_success_rate": sum(bool(row["localized"]) for row in episodes) / args.episodes,
        "grasp_loop_success_rate": sum(bool(row["grasp_lift_rotate_reobserve_success"]) for row in episodes) / args.episodes,
        "stable_rotation_success_rate": sum(bool(row["stable_rotation_success"]) for row in episodes) / args.episodes,
        "mean_localization_error_m": float(np.mean(errors)) if errors else None,
        "p95_localization_error_m": float(np.percentile(errors, 95)) if errors else None,
        "elapsed_seconds": time.perf_counter() - started,
        "truth_boundary": "cube body position is read only here for scoring, never by perception/control",
        "runs": episodes,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps({key: value for key, value in report.items() if key != "runs"}, indent=2))


if __name__ == "__main__":
    main()
