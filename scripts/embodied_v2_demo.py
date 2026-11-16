#!/usr/bin/env python3
"""Run the CubeRelay Embodied Simulation v2 physics demo."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from cube_relay.embodied.perception_v2 import DeterministicCubeLocalizer
from cube_relay.embodied.v2_controller import EmbodiedV2Controller, write_v2_artifacts
from cube_relay.embodied.vlm import HeuristicSceneVLM, OpenAICompatibleSceneVLM


def arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--phase", choices=("grasp", "full"), default="grasp")
    parser.add_argument("--seed", type=int, default=7)
    parser.add_argument("--scramble-steps", type=int, default=15)
    parser.add_argument("--output", type=Path, default=Path("runs/embodied_v2"))
    parser.add_argument("--vlm-endpoint")
    parser.add_argument("--vlm-model", default="local-model")
    parser.add_argument("--vlm-api-key", default="")
    return parser.parse_args()


def main() -> None:
    args = arguments()
    from cube_relay.embodied.mujoco_v2 import MuJoCoEmbodiedBackend

    args.output.mkdir(parents=True, exist_ok=True)
    backend = MuJoCoEmbodiedBackend(video_path=args.output / "episode.mp4")
    vlm = (
        OpenAICompatibleSceneVLM(args.vlm_endpoint, args.vlm_model, args.vlm_api_key)
        if args.vlm_endpoint else HeuristicSceneVLM()
    )
    if args.phase == "grasp":
        metadata = backend.reset_random(args.seed, args.scramble_steps)
        before = backend.capture_rgbd()
        backend.frames.append(before.rgb)
        semantics = vlm.understand(before.rgb)
        detection = DeterministicCubeLocalizer().locate(before) if semantics.cube_visible else None
        if detection is None:
            raise SystemExit("cube was not localized from RGB-D pixels")
        grasped = backend.approach_grasp_lift(
            detection.center_world_m, detection.yaw_radians
        )
        if grasped:
            backend.rotate_whole_cube_and_reobserve()
        video = backend.write_video()
        contact_trace = args.output / "contact_trace.json"
        contact_trace.write_text(
            json.dumps(backend.contact_debug_trace, indent=2), encoding="utf-8"
        )
        report = {
            "phase": "minimum_physics_vertical_loop",
            "seed": args.seed,
            "scramble": metadata["scramble"],
            "cube_detection": {
                "center_world_m": detection.center_world_m,
                "yaw_radians": detection.yaw_radians,
                "yaw_confidence": detection.yaw_confidence,
                "confidence": detection.confidence,
                "source": detection.source,
            },
            "grasp_candidates": [
                {
                    "wrist_yaw_radians": item.wrist_yaw_radians,
                    "face_pair": item.face_pair,
                    "ik_feasible": item.ik_feasible,
                    "collision_free": item.collision_free,
                    "contact_geometry_score": item.contact_geometry_score,
                    "motion_cost": item.motion_cost,
                    "rejection_reason": item.rejection_reason,
                }
                for item in backend.last_grasp_candidates
            ],
            "grasp_verified": grasped,
            "contact_failure_class": backend.contact_failure_class,
            "grasp_telemetry": {
                "bilateral_contact_fraction": backend.last_grasp_telemetry.bilateral_contact_fraction,
                "max_relative_slip_m": backend.last_grasp_telemetry.max_relative_slip_m,
                "lift_height_m": backend.last_grasp_telemetry.lift_height_m,
                "rotation_success": backend.last_grasp_telemetry.success,
                "left_contact_rate": backend.last_grasp_telemetry.left_contact_rate,
                "right_contact_rate": backend.last_grasp_telemetry.right_contact_rate,
                "left_normal_force_n": backend.last_grasp_telemetry.left_normal_force_n,
                "right_normal_force_n": backend.last_grasp_telemetry.right_normal_force_n,
                "trial_lift_success": backend.last_grasp_telemetry.trial_lift_success,
                "full_lift_success": backend.last_grasp_telemetry.full_lift_success,
                "full_rotation_success": backend.last_grasp_telemetry.full_rotation_success,
                "phase_trace": backend.last_grasp_telemetry.phase_trace,
                "failure_reason": backend.last_grasp_telemetry.failure_reason,
            },
            "whole_cube_rotation": "physical wrist joint",
            "reobserved": grasped,
            "contact_trace": str(contact_trace),
            "video": str(video) if video else None,
            "implementation_level": backend.implementation_level,
            "audit": "robot grasp uses no weld, mocap, or direct pose assignment after reset",
        }
        (args.output / "grasp_metrics.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
        print(json.dumps(report, indent=2))
        return

    controller = EmbodiedV2Controller(backend, vlm)
    result = controller.run(seed=args.seed, scramble_steps=args.scramble_steps)
    write_v2_artifacts(result, args.output)
    backend.write_video()
    print(json.dumps({"solved": result.solved, "terminal": result.terminal_state.value}, indent=2))


if __name__ == "__main__":
    main()
