"""Small, deterministic facelet permutation engine for all 18 standard moves."""

from __future__ import annotations

import random
from collections.abc import Iterable

from .state import FACE_ORDER, LEGAL_MOVES, SOLVED_FACELETS
from .validation import InvalidCubeState, validate_facelets

Vector = tuple[int, int, int]
Sticker = tuple[Vector, Vector]


def _stickers() -> tuple[Sticker, ...]:
    result: list[Sticker] = []
    for face in FACE_ORDER:
        for row in range(3):
            for col in range(3):
                if face == "U":
                    item = ((col - 1, 1, row - 1), (0, 1, 0))
                elif face == "R":
                    item = ((1, 1 - row, 1 - col), (1, 0, 0))
                elif face == "F":
                    item = ((col - 1, 1 - row, 1), (0, 0, 1))
                elif face == "D":
                    item = ((col - 1, -1, 1 - row), (0, -1, 0))
                elif face == "L":
                    item = ((-1, 1 - row, col - 1), (-1, 0, 0))
                else:  # B
                    item = ((1 - col, 1 - row, -1), (0, 0, -1))
                result.append(item)
    return tuple(result)


STICKERS = _stickers()
STICKER_INDEX = {sticker: index for index, sticker in enumerate(STICKERS)}
NORMALS: dict[str, Vector] = {
    "U": (0, 1, 0), "R": (1, 0, 0), "F": (0, 0, 1),
    "D": (0, -1, 0), "L": (-1, 0, 0), "B": (0, 0, -1),
}


def _dot(left: Vector, right: Vector) -> int:
    return sum(a * b for a, b in zip(left, right, strict=True))


def _cross(left: Vector, right: Vector) -> Vector:
    return (
        left[1] * right[2] - left[2] * right[1],
        left[2] * right[0] - left[0] * right[2],
        left[0] * right[1] - left[1] * right[0],
    )


def _rotate_clockwise(vector: Vector, axis: Vector) -> Vector:
    """Rotate -90 degrees around an outward face normal."""
    parallel = tuple(axis[i] * _dot(axis, vector) for i in range(3))
    cross = _cross(axis, vector)
    return tuple(parallel[i] - cross[i] for i in range(3))  # type: ignore[return-value]


def _quarter_turn_permutation(face: str) -> tuple[int, ...]:
    axis = NORMALS[face]
    destinations: list[int] = []
    for position, normal in STICKERS:
        if _dot(position, axis) == 1:
            position = _rotate_clockwise(position, axis)
            normal = _rotate_clockwise(normal, axis)
        destinations.append(STICKER_INDEX[(position, normal)])
    return tuple(destinations)


QUARTER_TURNS = {face: _quarter_turn_permutation(face) for face in FACE_ORDER}


class CubeEngine:
    """Apply standard moves without maintaining hidden cubie state."""

    def apply_move(self, facelets: str, move: str) -> str:
        validate_facelets(facelets, check_solvable=False)
        if move not in LEGAL_MOVES:
            raise ValueError(f"illegal move {move!r}; expected one of {LEGAL_MOVES}")
        turns = 2 if move.endswith("2") else 3 if move.endswith("'") else 1
        state = facelets
        permutation = QUARTER_TURNS[move[0]]
        for _ in range(turns):
            updated = [""] * 54
            for source, destination in enumerate(permutation):
                updated[destination] = state[source]
            state = "".join(updated)
        return state

    def apply_moves(self, facelets: str, moves: Iterable[str] | str) -> str:
        if isinstance(moves, str):
            moves = moves.split()
        for move in moves:
            facelets = self.apply_move(facelets, move)
        return facelets

    def is_solved(self, facelets: str) -> bool:
        validate_facelets(facelets, check_solvable=False)
        return facelets == SOLVED_FACELETS

    def scramble(self, seed: int, n: int = 25) -> tuple[str, list[str]]:
        if n < 0:
            raise ValueError("scramble length cannot be negative")
        rng = random.Random(seed)
        moves: list[str] = []
        while len(moves) < n:
            move = rng.choice(LEGAL_MOVES)
            if moves and moves[-1][0] == move[0]:
                continue
            moves.append(move)
        return self.apply_moves(SOLVED_FACELETS, moves), moves

