import random

from cube_relay.cube import CubeEngine
from cube_relay.cube.validation import StateValidator, validate_facelets


def test_one_thousand_random_valid_states() -> None:
    engine = CubeEngine()
    rng = random.Random(20261112)
    for case in range(1000):
        state, moves = engine.scramble(rng.randrange(2**32), n=rng.randint(0, 40))
        assert validate_facelets(state, check_solvable=True) == state, case
        inverse = [move if move.endswith("2") else move[0] if move.endswith("'") else move + "'"
                   for move in reversed(moves)]
        assert engine.is_solved(engine.apply_moves(state, inverse)), case


def test_validator_returns_structured_report_without_planning() -> None:
    report = StateValidator().validate("bad", check_solvable=False)
    assert not report.valid
    assert not report.physical_solvability_checked
    assert "54 characters" in report.error
