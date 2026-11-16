#!/usr/bin/env python3
"""Reproduce the supplied log and compare collaboration policy metrics."""

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from cube_relay.cube import CubeEngine  # noqa: E402
from cube_relay.experiments.collaboration_audit import aggregate, run_episode  # noqa: E402

parser = argparse.ArgumentParser()
parser.add_argument("--fixture", type=Path, default=Path("docs/cube-22c86967-d798-4c6b-8d04-8aa2eb3ce8a7.json"))
parser.add_argument("--samples", type=int, default=100)
parser.add_argument("--output", type=Path, default=Path("results/collaboration_audit"))
args = parser.parse_args()
data = json.loads(args.fixture.read_text(encoding="utf-8"))
events = {event["sequence"]: event for event in data["events"]}
fixture_initial = events[20]["actual_state"]

fixture_rows = [
    run_episode(fixture_initial, policy=policy, seed=0,
                forced_human_moves=["U'", "R"], random_interventions=0)
    for policy in ("before_unconditional", "after_guided")
]
engine = CubeEngine()
random_rows = {"before_unconditional": [], "after_guided": []}
for seed in range(args.samples):
    initial, _ = engine.scramble(seed, 15 + seed % 6)
    for policy in random_rows:
        random_rows[policy].append(run_episode(initial, policy=policy, seed=seed))

report = {
    "fixture": str(args.fixture),
    "fixture_event_20_start_with_human_moves_U_prime_R": {
        row.policy: row.as_dict() for row in fixture_rows
    },
    "random_scrambles_15_to_20_moves": {
        policy: aggregate(rows) for policy, rows in random_rows.items()
    },
    "definitions": {
        "before_unconditional": "execute solver_solution[0]; auto-confirm repeated-state pause for measurement",
        "after_guided": "on UNDO_CONFLICT choose keep_human_move alternate valid plan",
        "undo_rate": "actual robot moves returning exactly to state_before_human / all robot moves",
    },
}
args.output.mkdir(parents=True, exist_ok=True)
(args.output / "summary.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
with (args.output / "samples.jsonl").open("w", encoding="utf-8") as handle:
    for row in fixture_rows:
        handle.write(json.dumps({"group": "fixture", **row.as_dict()}) + "\n")
    for policy, rows in random_rows.items():
        for row in rows:
            handle.write(json.dumps({"group": "random", **row.as_dict()}) + "\n")
print(json.dumps(report, indent=2))
