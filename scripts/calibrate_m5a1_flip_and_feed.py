#!/usr/bin/env python3
"""M5-A.1 20-seed physical stress calibration & Flip-and-Feed cost profiler.

Evaluates 0-Flip, 1-Flip (4 side faces), 2-Flip across seeds 0..19, plus
10 random seeds of 3-step cross-axis sequences combining 0/1/2-Flip transitions.
Exports `results/m5a1_calibration/flip_cost_profile.json`.
"""

from __future__ import annotations

import argparse
from collections import Counter
import json
import math
from pathlib import Path
import time
from typing import Any

import numpy as np

from cube_relay.cube import CubeEngine
from cube_relay.embodied.mujoco_v2 import MuJoCoEmbodiedBackend
from cube_relay.embodied.physical_cube_26 import extract_54_geom_facelets_state
from cube_relay.embodied.physical_u import physical_color_layout


def _summarize_bucket(records: list[dict[str, Any]]) -> dict[str, Any]:
    """Summarize calibration statistics for one flip-count bucket."""
    sample_count = len(records)
    successes = [r for r in records if r["success"]]
    success_count = len(successes)
    rate = round(success_count / sample_count, 4) if sample_count > 0 else 0.0
    sim_times = [float(r["sim_time_s"]) for r in successes]
    all_sim_times = [float(r["sim_time_s"]) for r in records]
    regrasps = [int(r.get("regrasps_executed", 0)) for r in successes]
    failures = Counter(str(r["failure_code"]) for r in records if not r["success"])
    return {
        "sample_count": sample_count,
        "success_count": success_count,
        "empirical_success_rate": rate,
        "mean_sim_time_s": round(float(np.mean(sim_times)), 4) if sim_times else 0.0,
        "p95_sim_time_s": round(float(np.percentile(sim_times, 95)), 4) if sim_times else 0.0,
        "all_trials_mean_sim_time_s": round(float(np.mean(all_sim_times)), 4) if all_sim_times else 0.0,
        "mean_regrasps": round(float(np.mean(regrasps)), 4) if regrasps else 0.0,
        "failure_breakdown": dict(failures),
        "failed_trials": [
            {
                "seed": r["seed"],
                "move": r.get("move") or r.get("sequence"),
                "failure_code": r["failure_code"],
                "failure_reason": r.get("failure_reason", ""),
                "sim_time_s": r["sim_time_s"],
            }
            for r in records
            if not r["success"]
        ],
    }


def _evaluate_single_move(
    backend: MuJoCoEmbodiedBackend,
    eng: CubeEngine,
    *,
    seed: int,
    move: str,
    expected_flips: int,
    scramble_steps: int = 6,
) -> dict[str, Any]:
    """Execute one physical turn on a freshly randomized tabletop cube and validate 54 facelets."""
    meta = backend.reset_random(seed=seed, scramble_steps=scramble_steps)
    init_state = str(meta["truth_for_evaluation_only"])
    geom_init = physical_color_layout(init_state)
    init_rgba = backend.model.geom_rgba.copy()
    t0 = float(backend.data.time)
    t_wall0 = time.perf_counter()

    res = backend.execute_physical_face_turn(move)
    sim_dt = round(float(backend.data.time) - t0, 4)
    wall_dt = round(time.perf_counter() - t_wall0, 3)

    exp_state = eng.apply_move(init_state, move)
    obs_state = extract_54_geom_facelets_state(backend.model, backend.data, backend.mujoco, geom_init)
    no_recolor = bool(np.array_equal(init_rgba, backend.model.geom_rgba))

    ok = bool(res.get("success"))
    failure_code = res.get("failure_code")
    failure_reason = str(res.get("failure_reason") or "")
    angle_err = float(res["angle_error_deg"]) if res.get("angle_error_deg") is not None else 999.0
    slice_err = (
        float(res["max_slice_misalignment_deg"])
        if res.get("max_slice_misalignment_deg") is not None
        else 999.0
    )

    if ok and not no_recolor:
        ok = False
        failure_code = "RUNTIME_RECOLOR_VIOLATION"
        failure_reason = "geom_rgba changed during execution"
    elif ok and not res.get("contact_driven"):
        ok = False
        failure_code = "NON_CONTACT_TURN"
        failure_reason = "turn was not contact-driven"
    elif ok and (angle_err >= 2.0 or slice_err >= 2.0):
        ok = False
        failure_code = "LATTICE_TOLERANCE_EXCEEDED"
        failure_reason = f"angle_err={angle_err:.3f} deg, slice_err={slice_err:.3f} deg"
    elif ok and obs_state != exp_state:
        ok = False
        failure_code = "GEOM_54_MISMATCH"
        failure_reason = f"expected={exp_state} observed={obs_state}"
    elif ok and int(res.get("flips_executed", -1)) != expected_flips:
        ok = False
        failure_code = "UNEXPECTED_FLIP_COUNT"
        failure_reason = (
            f"expected flips={expected_flips}, got {res.get('flips_executed')}"
        )

    return {
        "seed": seed,
        "move": move,
        "expected_flips": expected_flips,
        "flips_executed": int(res.get("flips_executed", 0)),
        "regrasps_executed": int(res.get("regrasps_executed", 0)),
        "success": ok,
        "failure_code": None if ok else str(failure_code or "TURN_FAILED"),
        "failure_reason": "" if ok else failure_reason,
        "sim_time_s": sim_dt,
        "wall_time_s": wall_dt,
        "angle_error_deg": round(angle_err, 3) if math.isfinite(angle_err) else None,
        "max_slice_misalignment_deg": round(slice_err, 3) if math.isfinite(slice_err) else None,
        "scramble": meta.get("scramble"),
        "orientation": res.get("orientation"),
    }


def _evaluate_mixed_sequence(
    backend: MuJoCoEmbodiedBackend,
    eng: CubeEngine,
    *,
    seed: int,
    side_face: str,
    scramble_steps: int = 6,
) -> dict[str, Any]:
    """Execute a 3-step continuous sequence covering 0-flip -> 1-flip -> 2-flip on one session."""
    meta = backend.reset_random(seed=seed, scramble_steps=scramble_steps)
    init_state = str(meta["truth_for_evaluation_only"])
    geom_init = physical_color_layout(init_state)
    init_rgba = backend.model.geom_rgba.copy()
    t0 = float(backend.data.time)
    t_wall0 = time.perf_counter()

    exp_state = init_state
    suffixes = ("", "'", "2")
    u_mv = "U" + suffixes[seed % 3]
    side_mv = side_face + suffixes[(seed + 1) % 3]

    executed_steps: list[dict[str, Any]] = []
    sequence_moves: list[str] = []
    ok = True
    failure_code: str | None = None
    failure_reason = ""
    total_regrasps = 0
    total_flips = 0

    for step_idx in range(3):
        if step_idx == 0:
            mv = u_mv
        elif step_idx == 1:
            mv = side_mv
        else:
            assert backend.orientation_tracker is not None
            bottom_face = backend.orientation_tracker.snapshot().bottom_face
            mv = bottom_face + suffixes[(seed + 2) % 3]
        sequence_moves.append(mv)
        res = backend.execute_physical_face_turn(mv)
        exp_state = eng.apply_move(exp_state, mv)
        obs_state = extract_54_geom_facelets_state(backend.model, backend.data, backend.mujoco, geom_init)
        total_regrasps += int(res.get("regrasps_executed", 0))
        total_flips += int(res.get("flips_executed", 0))

        step_ok = bool(res.get("success")) and np.array_equal(init_rgba, backend.model.geom_rgba) and obs_state == exp_state
        executed_steps.append(
            {
                "move": mv,
                "flips_executed": int(res.get("flips_executed", 0)),
                "regrasps_executed": int(res.get("regrasps_executed", 0)),
                "success": step_ok,
                "failure_code": res.get("failure_code"),
                "angle_error_deg": res.get("angle_error_deg"),
                "max_slice_misalignment_deg": res.get("max_slice_misalignment_deg"),
            }
        )
        if not step_ok:
            ok = False
            if not res.get("success"):
                failure_code = str(res.get("failure_code") or "MIXED_STEP_FAILED")
                failure_reason = f"step {step_idx} ({mv}): {res.get('failure_reason')}"
            elif obs_state != exp_state:
                failure_code = "GEOM_54_MISMATCH"
                failure_reason = f"step {step_idx} ({mv}): 54-cell mismatch"
            else:
                failure_code = "RUNTIME_RECOLOR_VIOLATION"
                failure_reason = f"step {step_idx} ({mv}): geom_rgba modified"
            break

    sim_dt = round(float(backend.data.time) - t0, 4)
    wall_dt = round(time.perf_counter() - t_wall0, 3)
    return {
        "seed": seed,
        "sequence": sequence_moves,
        "flips_executed": total_flips,
        "regrasps_executed": total_regrasps,
        "success": ok,
        "failure_code": failure_code,
        "failure_reason": failure_reason,
        "sim_time_s": sim_dt,
        "wall_time_s": wall_dt,
        "steps": executed_steps,
    }


def run_calibration(*, num_seeds: int = 20, mixed_seeds: int = 10, output_path: Path) -> dict[str, Any]:
    """Run all 0/1/2-Flip and mixed-sequence physical calibration trials and write JSON output."""
    eng = CubeEngine()
    zero_flip_moves = ("U", "U'", "U2")
    one_flip_moves = ("R", "F'", "L2", "B", "R'", "F2", "L", "B'", "R2", "F", "L'", "B2")
    two_flip_moves = ("D", "D'", "D2")
    side_faces = ("R", "F", "L", "B")

    zero_records: list[dict[str, Any]] = []
    one_records: list[dict[str, Any]] = []
    two_records: list[dict[str, Any]] = []
    mixed_records: list[dict[str, Any]] = []

    backend = MuJoCoEmbodiedBackend(full_26_cubie=True, width=320, height=240)
    try:
        for seed in range(num_seeds):
            z_rec = _evaluate_single_move(
                backend,
                eng,
                seed=seed,
                move=zero_flip_moves[seed % len(zero_flip_moves)],
                expected_flips=0,
            )
            zero_records.append(z_rec)
            print(f"[0-flip] seed={seed:2d} move={z_rec['move']:2s} ok={z_rec['success']} sim={z_rec['sim_time_s']}s code={z_rec['failure_code']}", flush=True)

            o_rec = _evaluate_single_move(
                backend,
                eng,
                seed=seed,
                move=one_flip_moves[seed % len(one_flip_moves)],
                expected_flips=1,
            )
            one_records.append(o_rec)
            print(f"[1-flip] seed={seed:2d} move={o_rec['move']:2s} ok={o_rec['success']} sim={o_rec['sim_time_s']}s code={o_rec['failure_code']}", flush=True)

            t_rec = _evaluate_single_move(
                backend,
                eng,
                seed=seed,
                move=two_flip_moves[seed % len(two_flip_moves)],
                expected_flips=2,
            )
            two_records.append(t_rec)
            print(f"[2-flip] seed={seed:2d} move={t_rec['move']:2s} ok={t_rec['success']} sim={t_rec['sim_time_s']}s code={t_rec['failure_code']}", flush=True)

        for seed in range(mixed_seeds):
            m_rec = _evaluate_mixed_sequence(
                backend,
                eng,
                seed=seed,
                side_face=side_faces[seed % len(side_faces)],
            )
            mixed_records.append(m_rec)
            print(f"[mixed3] seed={seed:2d} seq={m_rec['sequence']} ok={m_rec['success']} sim={m_rec['sim_time_s']}s code={m_rec['failure_code']}", flush=True)
    finally:
        backend.renderer.close()

    profile = {
        "schema_version": "cuberelay_m5a1_flip_cost_profile_v1",
        "generated_at_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "seed_range": f"0..{num_seeds - 1}",
        "mixed_seed_range": f"0..{mixed_seeds - 1}",
        "metrics_note": (
            "mean_sim_time_s, p95_sim_time_s, and mean_regrasps aggregate successful physical executions; "
            "all_trials_mean_sim_time_s is reported alongside failure_breakdown without omitting failed seeds."
        ),
        "0_flip": _summarize_bucket(zero_records),
        "1_flip": _summarize_bucket(one_records),
        "2_flip": _summarize_bucket(two_records),
        "mixed_3_step_sequence": _summarize_bucket(mixed_records),
        "trials": {
            "0_flip": zero_records,
            "1_flip": one_records,
            "2_flip": two_records,
            "mixed_3_step_sequence": mixed_records,
        },
    }

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(profile, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return profile


def main() -> None:
    parser = argparse.ArgumentParser(description="Run M5-A.1 20-seed Flip-and-Feed calibration")
    parser.add_argument("--seeds", type=int, default=20)
    parser.add_argument("--mixed-seeds", type=int, default=10)
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("results/m5a1_calibration/flip_cost_profile.json"),
    )
    args = parser.parse_args()
    profile = run_calibration(
        num_seeds=args.seeds,
        mixed_seeds=args.mixed_seeds,
        output_path=args.output,
    )
    for key in ("0_flip", "1_flip", "2_flip", "mixed_3_step_sequence"):
        b = profile[key]
        print(
            f"SUMMARY {key}: {b['success_count']}/{b['sample_count']} "
            f"({b['empirical_success_rate']*100:.1f}%), mean_sim={b['mean_sim_time_s']}s, "
            f"p95_sim={b['p95_sim_time_s']}s, mean_regrasps={b['mean_regrasps']}, "
            f"failures={b['failure_breakdown']}",
            flush=True,
        )


if __name__ == "__main__":
    main()
