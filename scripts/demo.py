#!/usr/bin/env python3
"""Run the Week 1 scramble -> solve -> verify loop."""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from cube_relay.cube import CubeEngine, CubeSolver, SOLVED_FACELETS  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--scramble", required=True, help="space-separated standard moves")
    args = parser.parse_args()

    engine = CubeEngine()
    solver = CubeSolver()
    moves = args.scramble.split()
    scrambled = engine.apply_moves(SOLVED_FACELETS, moves)
    result = solver.solve_timed(scrambled)
    final = engine.apply_moves(scrambled, result.moves)

    print(f"initial:  {SOLVED_FACELETS}")
    print(f"scramble: {' '.join(moves)}")
    print(f"state:    {scrambled}")
    print(f"solution: {' '.join(result.moves)}")
    print(f"solve_ms: {result.elapsed_seconds * 1000:.3f}")
    print("SOLVED" if engine.is_solved(final) else "FAILED")
    return 0 if engine.is_solved(final) else 1


if __name__ == "__main__":
    raise SystemExit(main())

