import pytest

from cube_relay.cube import CubeEngine, CubeSolver, InvalidCubeState, SOLVED_FACELETS
from cube_relay.cube.validation import validate_facelets


ENGINE = CubeEngine()
SOLVER = CubeSolver()


@pytest.mark.parametrize("seed", range(20))
def test_twenty_seeded_scrambles_solve(seed: int) -> None:
    scrambled, _ = ENGINE.scramble(seed, n=25)
    solution = SOLVER.solve(scrambled)
    assert solution
    assert ENGINE.apply_moves(scrambled, solution) == SOLVED_FACELETS


def test_solved_cube_needs_no_moves() -> None:
    assert SOLVER.solve(SOLVED_FACELETS) == []


@pytest.mark.parametrize(
    "facelets, message",
    [
        ("U" * 53, "54 characters"),
        (SOLVED_FACELETS[:-1] + "X", "unknown facelet"),
        ("U" * 54, "occur 9 times"),
    ],
)
def test_rejects_malformed_states(facelets: str, message: str) -> None:
    with pytest.raises(InvalidCubeState, match=message):
        SOLVER.solve(facelets)


def test_rejects_wrong_centers() -> None:
    state = list(SOLVED_FACELETS)
    state[4], state[13] = state[13], state[4]
    with pytest.raises(InvalidCubeState, match="centers"):
        validate_facelets("".join(state))


def test_rejects_impossible_single_flipped_edge() -> None:
    state = list(SOLVED_FACELETS)
    state[7], state[19] = state[19], state[7]
    with pytest.raises(InvalidCubeState, match="not physically solvable"):
        SOLVER.solve("".join(state))


def test_timing_is_reported() -> None:
    scrambled, _ = ENGINE.scramble(100, n=10)
    result = SOLVER.solve_timed(scrambled)
    assert result.elapsed_seconds >= 0
    assert ENGINE.is_solved(ENGINE.apply_moves(scrambled, result.moves))
