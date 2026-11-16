#!/usr/bin/env python3
"""Verify and print a recorded JSONL trajectory."""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from cube_relay.telemetry.trajectory import Trajectory  # noqa: E402

parser = argparse.ArgumentParser()
parser.add_argument("trajectory", type=Path)
args = parser.parse_args()
trajectory = Trajectory.read_jsonl(args.trajectory)
trajectory.verify_chain()
for event in trajectory.events:
    print(f"{event.step:03d} {event.kind:20s} {event.move or '-':3s} v{event.plan_version}")
print(f"verified {len(trajectory.events)} events")

