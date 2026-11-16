"""Adapter around the mature Kociemba two-phase solver."""

from __future__ import annotations

import time
from dataclasses import dataclass

import kociemba

from .state import LEGAL_MOVES, SOLVED_FACELETS
from .validation import InvalidCubeState, validate_facelets


@dataclass(frozen=True, slots=True)
class SolveResult:
    moves: list[str]
    elapsed_seconds: float


class CubeSolver:
    def solve(self, facelets: str) -> list[str]:
        return self.solve_timed(facelets).moves

    def solve_timed(self, facelets: str) -> SolveResult:
        validate_facelets(facelets, check_solvable=False)
        if facelets == SOLVED_FACELETS:
            return SolveResult([], 0.0)
        started = time.perf_counter()
        try:
            raw = kociemba.solve(facelets)
        except (ValueError, RuntimeError) as exc:
            raise InvalidCubeState(f"cube is not physically solvable: {exc}") from exc
        moves = raw.split()
        unknown = set(moves) - set(LEGAL_MOVES)
        if unknown:
            raise RuntimeError(f"solver returned unsupported moves: {sorted(unknown)}")
        return SolveResult(moves, time.perf_counter() - started)

    def warm_up(self) -> float:
        started = time.perf_counter()
        kociemba.solve(SOLVED_FACELETS)
        return time.perf_counter() - started

