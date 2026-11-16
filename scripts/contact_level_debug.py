#!/usr/bin/env python3
"""Contact-level paired experiments for the MuJoCo parallel-jaw grasp."""

from __future__ import annotations

import argparse
import json
import math
import time
from collections import Counter
from dataclasses import asdict, replace
from pathlib import Path

import numpy as np

from cube_relay.embodied.v2_types import GraspControlConfig


def e1_configs() -> dict[str, GraspControlConfig]:
    # Historical pre-debug baseline, intentionally without force limiting.
    base = GraspControlConfig(
        contact_z_ctrl=-.29, finger_force_limit_n=None, pad_sliding_friction=10
    )
    return {
        "baseline": base,
        "height_low_-0.31": replace(base, contact_z_ctrl=-.31),
        "height_high_-0.27": replace(base, contact_z_ctrl=-.27),
        "height_high_-0.26": replace(base, contact_z_ctrl=-.26),
        "height_high_-0.25": replace(base, contact_z_ctrl=-.25),
        "closure_offset_-10mm": replace(base, approach_offset_local_xy_m=(0, -.01)),
        "closure_offset_+10mm": replace(base, approach_offset_local_xy_m=(0, .01)),
        "tangent_offset_-10mm": replace(base, approach_offset_local_xy_m=(-.01, 0)),
        "tangent_offset_+10mm": replace(base, approach_offset_local_xy_m=(.01, 0)),
        "pregrasp_gap_180mm": replace(base, pregrasp_gap_m=.18),
        "pregrasp_gap_150mm": replace(base, pregrasp_gap_m=.15),
    }


def e2_configs(base: GraspControlConfig | None = None) -> dict[str, GraspControlConfig]:
    # E1 winner after removing palm/cube top collision.
    base = base or GraspControlConfig(
        contact_z_ctrl=-.29,
        approach_offset_local_xy_m=(.01, 0),
        finger_force_limit_n=None,
        pad_sliding_friction=10,
    )
    return {
        "baseline": base,
        "close_fast_0.75s": replace(base, close_duration_seconds=.75),
        "close_slow_3.0s": replace(base, close_duration_seconds=3.0),
        "finger_kp_250": replace(base, finger_kp=250),
        "finger_kp_750": replace(base, finger_kp=750),
        "hold_short_0.05s": replace(base, stable_hold_seconds=.05),
        "hold_long_0.30s": replace(base, stable_hold_seconds=.30),
        "force_limit_8N": replace(base, finger_force_limit_n=8),
        "force_limit_15N": replace(base, finger_force_limit_n=15),
        "force_limit_25N": replace(base, finger_force_limit_n=25),
        "kp750_force_limit_15N": replace(
            base, finger_kp=750, finger_force_limit_n=15
        ),
        "kp750_force_limit_25N": replace(
            base, finger_kp=750, finger_force_limit_n=25
        ),
    }


def physics_configs(base: GraspControlConfig | None = None) -> dict[str, GraspControlConfig]:
    # E1 geometry plus the E2 force candidate; physics study confirms whether
    # changing friction/contact softness adds value.
    base = base or GraspControlConfig(
        contact_z_ctrl=-.29,
        approach_offset_local_xy_m=(.01, 0),
        finger_force_limit_n=8,
        pad_sliding_friction=10,
    )
    return {
        "baseline": base,
        "pad_friction_2": replace(base, pad_sliding_friction=2),
        "pad_friction_5": replace(base, pad_sliding_friction=5),
        "pad_friction_15": replace(base, pad_sliding_friction=15),
        "contact_soft_0.008": replace(base, contact_solref_timeconst=.008),
        "contact_stiff_0.002": replace(base, contact_solref_timeconst=.002),
    }


def model_audit(backend: object) -> dict[str, object]:
    model = backend.model
    mujoco = backend.mujoco
    def geom(name: str) -> int:
        return backend._id(mujoco.mjtObj.mjOBJ_GEOM, name)
    def joint(name: str) -> int:
        return backend._id(mujoco.mjtObj.mjOBJ_JOINT, name)
    def actuator(name: str) -> int:
        return backend._id(mujoco.mjtObj.mjOBJ_ACTUATOR, name)
    return {
        "timestep_s": float(model.opt.timestep),
        "integrator": int(model.opt.integrator),
        "cone": int(model.opt.cone),
        "cube_half_size_m": model.geom_size[geom("cube_core")].tolist(),
        "cube_mass_kg": float(model.body_mass[backend._id(mujoco.mjtObj.mjOBJ_BODY, "cube")]),
        "pad_half_size_m": model.geom_size[geom("left_finger_pad")].tolist(),
        "pad_friction": model.geom_friction[geom("left_finger_pad")].tolist(),
        "cube_friction": model.geom_friction[geom("cube_core")].tolist(),
        "pad_solref": model.geom_solref[geom("left_finger_pad")].tolist(),
        "pad_solimp": model.geom_solimp[geom("left_finger_pad")].tolist(),
        "left_joint_range_m": model.jnt_range[joint("left_finger_joint")].tolist(),
        "right_joint_range_m": model.jnt_range[joint("right_finger_joint")].tolist(),
        "left_actuator_gain": model.actuator_gainprm[actuator("left_finger_ctrl")].tolist(),
        "left_actuator_bias": model.actuator_biasprm[actuator("left_finger_ctrl")].tolist(),
        "left_actuator_force_limited": bool(
            model.actuator_forcelimited[actuator("left_finger_ctrl")]
        ),
        "left_actuator_force_range_n": model.actuator_forcerange[
            actuator("left_finger_ctrl")
        ].tolist(),
        "truth_boundary": "cube body pose is read only by this evaluator for GT control/scoring",
    }


def summarize(rows: list[dict[str, object]]) -> dict[str, object]:
    return {
        "episodes": len(rows),
        "bilateral_confirm_rate": sum(bool(row["bilateral_confirmed"]) for row in rows) / len(rows),
        "trial_lift_rate": sum(bool(row["trial_lift_success"]) for row in rows) / len(rows),
        "full_lift_rate": sum(bool(row["full_lift_success"]) for row in rows) / len(rows),
        "rotation_rate": sum(bool(row["full_rotation_success"]) for row in rows) / len(rows),
        "mean_left_force_n": float(np.mean([row["left_normal_force_n"] for row in rows])),
        "mean_right_force_n": float(np.mean([row["right_normal_force_n"] for row in rows])),
        "mean_max_slip_m": float(np.mean([row["max_relative_slip_m"] for row in rows])),
        "failure_classes": dict(Counter(str(row["failure_class"]) for row in rows)),
    }


def run_study(
    configs: dict[str, GraspControlConfig], episodes: int, start_seed: int,
    failure_log: Path,
) -> dict[str, object]:
    from cube_relay.embodied.mujoco_v2 import MuJoCoEmbodiedBackend

    groups: dict[str, list[dict[str, object]]] = {}
    failure_log.parent.mkdir(parents=True, exist_ok=True)
    failure_handle = failure_log.open("w", encoding="utf-8")
    audit: dict[str, object] | None = None
    started = time.perf_counter()
    try:
        for config_name, config in configs.items():
            backend = MuJoCoEmbodiedBackend(grasp_config=config)
            if audit is None:
                audit = model_audit(backend)
            rows: list[dict[str, object]] = []
            for offset in range(episodes):
                seed = start_seed + offset
                backend.reset_random(seed, 15)
                cube = backend._id(backend.mujoco.mjtObj.mjOBJ_BODY, "cube")
                truth_position = backend.data.xpos[cube].copy()
                rotation = backend.data.xmat[cube].reshape(3, 3)
                truth_yaw = math.atan2(float(rotation[1, 0]), float(rotation[0, 0]))
                grasped = backend.approach_grasp_lift(tuple(truth_position), truth_yaw)
                if grasped:
                    backend.rotate_whole_cube_and_reobserve()
                telemetry = backend.last_grasp_telemetry
                failure_class = (
                    None if telemetry.full_rotation_success
                    else backend.contact_failure_class or "rotation_contact_loss_or_slip"
                )
                row = {
                    "config": config_name,
                    "seed": seed,
                    "bilateral_confirmed": "BILATERAL_CONTACT" in telemetry.phase_trace,
                    "trial_lift_success": telemetry.trial_lift_success,
                    "full_lift_success": telemetry.full_lift_success,
                    "full_rotation_success": telemetry.full_rotation_success,
                    "left_contact_rate": telemetry.left_contact_rate,
                    "right_contact_rate": telemetry.right_contact_rate,
                    "left_normal_force_n": telemetry.left_normal_force_n,
                    "right_normal_force_n": telemetry.right_normal_force_n,
                    "max_relative_slip_m": telemetry.max_relative_slip_m,
                    "lift_height_m": telemetry.lift_height_m,
                    "failure_reason": telemetry.failure_reason,
                    "failure_class": failure_class or "success",
                    "phase_trace": telemetry.phase_trace,
                    "final_contact_sample": backend.contact_debug_trace[-1]
                        if backend.contact_debug_trace else None,
                }
                rows.append(row)
                if failure_class is not None:
                    failure_handle.write(json.dumps({
                        "config": config_name,
                        "config_values": asdict(config),
                        "seed": seed,
                        "failure_class": failure_class,
                        "failure_reason": telemetry.failure_reason,
                        "trace": backend.contact_debug_trace,
                    }, default=json_default) + "\n")
            groups[config_name] = rows
    finally:
        failure_handle.close()
    summaries = {name: summarize(rows) for name, rows in groups.items()}
    best = max(summaries, key=lambda name: (
        summaries[name]["rotation_rate"], summaries[name]["bilateral_confirm_rate"]
    ))
    return {
        "paired_seeds": list(range(start_seed, start_seed + episodes)),
        "configs": {name: asdict(config) for name, config in configs.items()},
        "model_audit": audit,
        "summaries": summaries,
        "best_config": best,
        "failure_trace_jsonl": str(failure_log),
        "runs": groups,
        "elapsed_seconds": time.perf_counter() - started,
    }


def json_default(value: object) -> object:
    if isinstance(value, np.generic):
        return value.item()
    if isinstance(value, tuple):
        return list(value)
    raise TypeError(f"{type(value).__name__} is not JSON serializable")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--study", choices=("e1", "e2", "physics"), required=True)
    parser.add_argument("--episodes", type=int, default=30)
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    configs = {
        "e1": e1_configs,
        "e2": e2_configs,
        "physics": physics_configs,
    }[args.study]()
    output = args.output or Path(f"results/contact_debug_{args.study}.json")
    failure_log = output.with_name(output.stem + "_failures.jsonl")
    report = run_study(configs, args.episodes, args.seed, failure_log)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2, default=json_default), encoding="utf-8")
    print(json.dumps({
        "study": args.study,
        "best_config": report["best_config"],
        "summaries": report["summaries"],
        "elapsed_seconds": report["elapsed_seconds"],
    }, indent=2, default=json_default))


if __name__ == "__main__":
    main()
