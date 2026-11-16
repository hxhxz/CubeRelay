#!/usr/bin/env python3
"""Automatic terminal form of the 90-second intervention/recovery demo."""

import json
import sys
from dataclasses import asdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from cube_relay.adapters.sim_robot import SimRobotAdapter  # noqa: E402
from cube_relay.agent import TurnCoordinator  # noqa: E402
from cube_relay.cube import CubeEngine, SOLVED_FACELETS  # noqa: E402

engine = CubeEngine()
initial = engine.apply_moves(SOLVED_FACELETS, "R U R' F2 D")
coordinator = TurnCoordinator(SimRobotAdapter(engine))
state = coordinator.start(initial)
unexpected = next(move for move in ("F", "R", "U") if move != state.planned_moves[0])
print(f"Human unexpected move: {unexpected}; recommended was {state.planned_moves[0]}")
coordinator.submit_human_move(unexpected)
while state.status == "running":
    if state.next_actor == "robot":
        coordinator.execute_robot_turn(plan_version=state.plan_version)
    else:
        coordinator.submit_human_move(state.planned_moves[0])
output = Path("runs/demo_90s.json")
output.parent.mkdir(exist_ok=True)
output.write_text(json.dumps({"session": state.model_dump(),
                              "events": [asdict(e) for e in coordinator.events]},
                             indent=2), encoding="utf-8")
print(f"status={state.status} plan_version={state.plan_version} events={len(coordinator.events)}")
print(f"trajectory={output}")

