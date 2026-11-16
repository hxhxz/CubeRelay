"""Authoritative software simulator with reproducible execution faults."""

from __future__ import annotations

from collections import deque
from typing import Literal

from cube_relay.cube import CubeEngine
from cube_relay.models import MoveRequest, MoveResult

Fault = Literal["no-op"] | str


class SimRobotAdapter:
    def __init__(self, engine: CubeEngine | None = None, faults: list[Fault] | None = None) -> None:
        self.engine = engine or CubeEngine()
        self.faults = deque(faults or [])
        self.stopped = False

    def execute_move(self, request: MoveRequest) -> MoveResult:
        if self.stopped:
            return MoveResult(success=False, move=request.move, observed_after=None,
                              error="emergency stop", backend="sim")
        fault = self.faults.popleft() if self.faults else None
        actual_move = request.move
        if fault == "no-op":
            observed = request.expected_before
        elif fault:
            actual_move = fault
            try:
                observed = self.engine.apply_move(request.expected_before, actual_move)
            except ValueError as exc:
                return MoveResult(success=False, move=request.move, observed_after=None,
                                  error=str(exc), backend="sim")
        else:
            observed = self.engine.apply_move(request.expected_before, request.move)
        return MoveResult(success=True, move=request.move, observed_after=observed,
                          error=None if not fault else f"injected:{fault}", backend="sim")

    def emergency_stop(self) -> None:
        self.stopped = True

