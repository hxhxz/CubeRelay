#!/usr/bin/env python3
"""Replay a recorded contact-debug timeline without simulator truth injection."""

from __future__ import annotations

import argparse
import json
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("trace", type=Path)
    parser.add_argument("--seed", type=int, required=True)
    parser.add_argument("--condition")
    parser.add_argument("--config")
    args = parser.parse_args()
    match = None
    for line in args.trace.read_text(encoding="utf-8").splitlines():
        record = json.loads(line)
        if record.get("seed") != args.seed:
            continue
        if args.condition and record.get("condition") != args.condition:
            continue
        if args.config and record.get("config") != args.config:
            continue
        match = record
        break
    if match is None:
        raise SystemExit("matching failure trace was not found")
    print(json.dumps({key: value for key, value in match.items() if key != "trace"}, indent=2))
    previous_phase = None
    for sample in match["trace"]:
        phase = sample["phase"]
        if phase != previous_phase:
            print(f"\n[{phase}]")
            previous_phase = phase
        slip = sample.get("relative_slip_from_bilateral_contact_m")
        slip_text = "n/a" if slip is None else f"{1000 * slip:.1f}mm"
        print(
            f"t={sample['time_s']:.3f}s "
            f"contacts={sample['left_contact_count']}/{sample['right_contact_count']} "
            f"force={sample['left_normal_force_n']:.2f}/{sample['right_normal_force_n']:.2f}N "
            f"gap={1000 * sample['jaw_inner_gap_m']:.1f}mm "
            f"cube_disp={1000 * sample['cube_displacement_from_pregrasp_m']:.1f}mm "
            f"slip={slip_text}"
        )


if __name__ == "__main__":
    main()
