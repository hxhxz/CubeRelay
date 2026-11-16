#!/usr/bin/env python3
"""Generate raw and summary evidence for Robot undoing Human moves."""

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from cube_relay.experiments.inverse_diagnostics import (  # noqa: E402
    random_scramble_cases, solved_perturbation_cases, summarize,
)

parser = argparse.ArgumentParser()
parser.add_argument("--samples", type=int, default=100)
parser.add_argument("--seed", type=int, default=20261112)
parser.add_argument("--output", type=Path, default=Path("results/inverse_diagnostics"))
args = parser.parse_args()
args.output.mkdir(parents=True, exist_ok=True)

solved = solved_perturbation_cases()
random_cases = random_scramble_cases(args.samples, args.seed)
all_records = solved + random_cases
with (args.output / "samples.jsonl").open("w", encoding="utf-8") as handle:
    for record in all_records:
        handle.write(json.dumps(record.as_dict(), sort_keys=True) + "\n")
report = {
    "seed": args.seed,
    "solved_state_perturbations": summarize(solved),
    "random_scrambles_15_to_20_moves": summarize(random_cases),
    "visualization_direction_contract": {
        "CW90": "face + empty suffix; CSS rotate(+90deg)",
        "CCW90": "face + apostrophe suffix; CSS rotate(-90deg)",
        "HALF_TURN": "face + 2 suffix; CSS rotate(180deg)",
        "facelet_rendering": "UI reads actual_state[face_index * 9 + sticker_index]",
    },
}
(args.output / "summary.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
print(json.dumps(report, indent=2))
