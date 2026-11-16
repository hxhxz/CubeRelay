"""Shared cube notation and immutable facelet state helpers."""

from dataclasses import dataclass

FACE_ORDER = "URFDLB"
SOLVED_FACELETS = "".join(face * 9 for face in FACE_ORDER)
BASE_MOVES = tuple(FACE_ORDER)
LEGAL_MOVES = tuple(
    f"{face}{suffix}" for face in BASE_MOVES for suffix in ("", "'", "2")
)


def inverse_move(move: str) -> str:
    """Return the standard inverse notation without changing cube state."""
    if move not in LEGAL_MOVES:
        raise ValueError(f"illegal move: {move}")
    if move.endswith("2"):
        return move
    return move[0] if move.endswith("'") else move + "'"


@dataclass(frozen=True, slots=True)
class CubeState:
    """A 54-character cube state in fixed U, R, F, D, L, B order."""

    facelets: str = SOLVED_FACELETS

    def __str__(self) -> str:
        return self.facelets
