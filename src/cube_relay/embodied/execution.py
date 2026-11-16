"""Physical-action contracts and explicit test doubles."""

from __future__ import annotations

import random
import time
from dataclasses import dataclass
from typing import Protocol

from cube_relay.cube.state import LEGAL_MOVES


@dataclass(frozen=True, slots=True)
class ActionRequest:
    move: str
    expected_before: str
    plan_version: int


@dataclass(frozen=True, slots=True)
class ActionFeedback:
    success: bool
    move: str
    duration_seconds: float
    position_error_radians: float | None
    backend: str
    detail: str = ""


class TurnExecutor(Protocol):
    def execute(self, request: ActionRequest) -> ActionFeedback: ...
    def emergency_stop(self) -> None: ...


class DeterministicTurnExecutor:
    """MOCK: exact, zero-dynamics executor used only for unit tests/baselines."""

    def __init__(self) -> None:
        self.stopped = False

    def execute(self, request: ActionRequest) -> ActionFeedback:
        if request.move not in LEGAL_MOVES:
            raise ValueError(f"illegal move: {request.move}")
        if self.stopped:
            return ActionFeedback(False, request.move, 0.0, None, "mock", "emergency stop")
        return ActionFeedback(True, request.move, 0.0, 0.0, "mock", "exact test double")

    def emergency_stop(self) -> None:
        self.stopped = True


class FailureInjectingExecutor:
    """Reproducibly inject execution failures around another executor."""

    def __init__(self, wrapped: TurnExecutor, probability: float, seed: int) -> None:
        if not 0 <= probability <= 1:
            raise ValueError("failure probability must be in [0, 1]")
        self.wrapped = wrapped
        self.probability = probability
        self.rng = random.Random(seed)

    def execute(self, request: ActionRequest) -> ActionFeedback:
        if self.rng.random() < self.probability:
            started = time.perf_counter()
            return ActionFeedback(
                False, request.move, time.perf_counter() - started, None,
                "injected", "synthetic failure before actuation",
            )
        return self.wrapped.execute(request)

    def emergency_stop(self) -> None:
        self.wrapped.emergency_stop()

