import pytest

from cube_relay.cube import CubeEngine, LEGAL_MOVES, SOLVED_FACELETS


ENGINE = CubeEngine()


def inverse(move: str) -> str:
    if move.endswith("2"):
        return move
    return move[0] if move.endswith("'") else move + "'"


@pytest.mark.parametrize("move", LEGAL_MOVES)
def test_all_18_moves_have_working_inverse(move: str) -> None:
    moved = ENGINE.apply_move(SOLVED_FACELETS, move)
    assert moved != SOLVED_FACELETS
    assert ENGINE.apply_move(moved, inverse(move)) == SOLVED_FACELETS


@pytest.mark.parametrize("face", "URFDLB")
def test_four_quarter_turns_restore_state(face: str) -> None:
    assert ENGINE.apply_moves(SOLVED_FACELETS, [face] * 4) == SOLVED_FACELETS


@pytest.mark.parametrize("face", "URFDLB")
def test_half_turn_matches_two_quarter_turns(face: str) -> None:
    assert ENGINE.apply_move(SOLVED_FACELETS, face + "2") == ENGINE.apply_moves(
        SOLVED_FACELETS, [face, face]
    )


def test_known_sexy_move_is_not_solved() -> None:
    state = ENGINE.apply_moves(SOLVED_FACELETS, "R U R' U'")
    assert not ENGINE.is_solved(state)
    assert ENGINE.apply_moves(state, "U R U' R'") == SOLVED_FACELETS


def test_scramble_is_deterministic_and_avoids_same_face_twice() -> None:
    state1, moves1 = ENGINE.scramble(seed=42, n=30)
    state2, moves2 = ENGINE.scramble(seed=42, n=30)
    assert state1 == state2
    assert moves1 == moves2
    assert all(left[0] != right[0] for left, right in zip(moves1, moves1[1:]))


def test_rejects_unknown_move() -> None:
    with pytest.raises(ValueError, match="illegal move"):
        ENGINE.apply_move(SOLVED_FACELETS, "X")

