"""Before/after evaluation for undo-conflict collaboration planning."""

from __future__ import annotations

import random
from dataclasses import asdict, dataclass

from cube_relay.adapters.sim_robot import SimRobotAdapter
from cube_relay.agent import TurnCoordinator
from cube_relay.cube import CubeEngine
from cube_relay.cube.state import LEGAL_MOVES


@dataclass(frozen=True, slots=True)
class CollaborationMetrics:
    policy: str
    seed: int
    success: bool
    undo_count: int
    robot_move_count: int
    undo_rate: float
    repeated_state_count: int
    replan_count: int
    total_steps: int

    def as_dict(self) -> dict[str, object]:
        return asdict(self)


def _metrics(coordinator: TurnCoordinator, policy: str, seed: int) -> CollaborationMetrics:
    events = coordinator.events
    diagnostics = [event for event in events if event.kind == "TURN_DIAGNOSTIC"]
    undos = sum(
        bool(event.detail.get("is_inverse_of_human_move")) and
        event.detail.get("state_after_robot") == event.detail.get("state_before_human")
        for event in diagnostics
    )
    robot_moves = sum(event.kind == "ROBOT_MOVE" for event in events)
    steps = sum(event.kind in {"HUMAN_MOVE", "ROBOT_MOVE"} for event in events)
    assert coordinator.state is not None
    return CollaborationMetrics(
        policy=policy, seed=seed, success=coordinator.state.status == "solved",
        undo_count=undos, robot_move_count=robot_moves,
        undo_rate=undos / robot_moves if robot_moves else 0.0,
        repeated_state_count=sum(event.kind == "REPEATED_STATE" for event in events),
        replan_count=sum(event.kind == "PLAN_REPAIRED" for event in events),
        total_steps=steps,
    )


def run_episode(initial_state: str, *, policy: str, seed: int,
                forced_human_moves: list[str] | None = None,
                random_interventions: int = 2, max_actions: int = 300) -> CollaborationMetrics:
    """Evaluate prior unconditional execution vs Guided keep-human resolution."""
    if policy not in {"before_unconditional", "after_guided"}:
        raise ValueError("unsupported audit policy")
    engine = CubeEngine()
    mode = "free_collaboration" if policy == "before_unconditional" else "guided_shared_plan"
    coordinator = TurnCoordinator(
        SimRobotAdapter(engine), engine=engine, collaboration_mode=mode
    )
    state = coordinator.start(initial_state)
    rng = random.Random(seed + 50000)
    forced = list(forced_human_moves or [])
    interventions_left = random_interventions if forced_human_moves is None else 0

    while state.status != "solved" and _metrics(coordinator, policy, seed).total_steps < max_actions:
        if state.confirmation_required:
            if state.confirmation_reason == "UNDO_CONFLICT":
                decision = "allow_inverse" if policy == "before_unconditional" else "keep_human_move"
            else:
                decision = "continue"
            coordinator.resolve_confirmation(decision)
            continue
        if state.next_actor == "human":
            if forced:
                move = forced.pop(0)
            elif interventions_left:
                candidates = [move for move in LEGAL_MOVES
                              if move != state.planned_moves[0]
                              and not engine.is_solved(engine.apply_move(state.actual_state, move))]
                move = rng.choice(candidates)
                interventions_left -= 1
            else:
                move = state.planned_moves[0]
            coordinator.submit_human_move(move)
        else:
            coordinator.execute_robot_turn(plan_version=state.plan_version)
    return _metrics(coordinator, policy, seed)


def aggregate(rows: list[CollaborationMetrics]) -> dict[str, object]:
    count = len(rows)
    robot_moves = sum(row.robot_move_count for row in rows)
    undos = sum(row.undo_count for row in rows)
    return {
        "episodes": count,
        "successes": sum(row.success for row in rows),
        "success_rate": sum(row.success for row in rows) / count if count else 0.0,
        "undo_count": undos,
        "robot_move_count": robot_moves,
        "undo_rate": undos / robot_moves if robot_moves else 0.0,
        "repeated_state_count": sum(row.repeated_state_count for row in rows),
        "replan_count": sum(row.replan_count for row in rows),
        "total_steps": sum(row.total_steps for row in rows),
    }

