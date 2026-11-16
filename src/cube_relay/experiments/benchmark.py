"""Fixed-plan versus actual-state replanning benchmark."""

from __future__ import annotations

import random
import time
from dataclasses import asdict, dataclass

from cube_relay.cube import CubeEngine, CubeSolver
from cube_relay.cube.state import LEGAL_MOVES


@dataclass(frozen=True, slots=True)
class BenchmarkResult:
    baseline: str
    task: str
    seed: int
    success: bool
    total_moves: int
    human_moves: int
    robot_moves: int
    replan_count: int
    mismatch_count: int
    recovery_success: bool
    runtime_ms: float

    def as_dict(self) -> dict[str, object]:
        return asdict(self)


def run_case(baseline: str, task: str, seed: int) -> BenchmarkResult:
    if baseline not in {"fixed-plan", "replan"} or task not in {"A", "B", "C"}:
        raise ValueError("unsupported baseline/task")
    engine, solver = CubeEngine(), CubeSolver()
    actual, _ = engine.scramble(seed, 12)
    plan = solver.solve(actual)
    rng = random.Random(seed + 10000)
    total = human = robot = replans = mismatches = 0
    injected = False
    started = time.perf_counter()
    while plan and total < 100 and not engine.is_solved(actual):
        if task == "B" and total == 3 and not injected:
            intervention = rng.choice(LEGAL_MOVES)
            actual = engine.apply_move(actual, intervention)
            total += 1
            human += 1
            mismatches += 1
            injected = True
            if baseline == "replan":
                plan = solver.solve(actual)
                replans += 1
        move = plan.pop(0)
        total += 1
        robot += 1
        if task == "C" and robot == 3 and not injected:
            injected = True  # no-op: actual is intentionally unchanged
            mismatches += 1
            if baseline == "replan":
                plan = solver.solve(actual)
                replans += 1
            continue
        actual = engine.apply_move(actual, move)
    success = engine.is_solved(actual)
    return BenchmarkResult(
        baseline, task, seed, success, total, human, robot, replans, mismatches,
        recovery_success=success if task != "A" else True,
        runtime_ms=(time.perf_counter() - started) * 1000,
    )


def task_matrix() -> list[tuple[str, int]]:
    return [("A", seed) for seed in range(20)] + [("B", seed) for seed in range(10)] + [
        ("C", seed) for seed in range(10)
    ]

