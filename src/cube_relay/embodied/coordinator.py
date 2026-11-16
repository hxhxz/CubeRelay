"""Closed-loop solver baseline with execution feedback and plan repair."""

from __future__ import annotations

import random
from dataclasses import dataclass

from cube_relay.cube import CubeEngine, CubeSolver
from cube_relay.cube.state import LEGAL_MOVES
from cube_relay.telemetry.metrics import EpisodeMetrics, compute_metrics
from cube_relay.telemetry.trajectory import Event, Trajectory

from .execution import ActionRequest, TurnExecutor


@dataclass(frozen=True, slots=True)
class EpisodeResult:
    final_state: str
    solved: bool
    metrics: EpisodeMetrics
    trajectory: Trajectory


class BaselineCoordinator:
    """Deterministic baseline: solve actual state, execute, verify feedback, repair."""

    def __init__(self, executor: TurnExecutor, engine: CubeEngine | None = None,
                 solver: CubeSolver | None = None) -> None:
        self.executor = executor
        self.engine = engine or CubeEngine()
        self.solver = solver or CubeSolver()

    def run(self, initial_state: str, *, seed: int = 0,
            intervention_probability: float = 0.0, max_attempts: int = 200) -> EpisodeResult:
        rng = random.Random(seed)
        actual = initial_state
        plan = self.solver.solve(actual)
        plan_version = 1
        trajectory = Trajectory()
        step = 0

        while not self.engine.is_solved(actual) and step < max_attempts:
            if rng.random() < intervention_probability:
                move = rng.choice(LEGAL_MOVES)
                before = actual
                actual = self.engine.apply_move(actual, move)
                step += 1
                trajectory.append(Event(step, "HUMAN_INTERVENTION", before, actual, move,
                                        plan_version, {"source": "confirmed_simulated_human"}))
                plan_version += 1
                plan = self.solver.solve(actual)
                trajectory.append(Event(step, "PLAN_REPAIRED", actual, actual, None,
                                        plan_version, {"reason": "human_intervention"}))

            if not plan:
                plan = self.solver.solve(actual)
            move = plan[0]
            before = actual
            feedback = self.executor.execute(ActionRequest(move, before, plan_version))
            step += 1
            if feedback.success:
                actual = self.engine.apply_move(actual, move)
                plan = plan[1:]
            else:
                plan_version += 1
                plan = self.solver.solve(actual)
            trajectory.append(Event(
                step, "ACTION_RESULT", before, actual, move, plan_version,
                {"success": feedback.success, "backend": feedback.backend,
                 "duration_seconds": feedback.duration_seconds,
                 "position_error_radians": feedback.position_error_radians,
                 "detail": feedback.detail},
            ))
            if not feedback.success:
                trajectory.append(Event(step, "PLAN_REPAIRED", actual, actual, None,
                                        plan_version, {"reason": "execution_failure"}))

        solved = self.engine.is_solved(actual)
        trajectory.verify_chain()
        return EpisodeResult(actual, solved, compute_metrics(trajectory, solved), trajectory)

