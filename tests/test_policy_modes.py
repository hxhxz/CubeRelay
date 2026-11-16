import pytest

from cube_relay.policy import ActionIntent


@pytest.mark.parametrize(
    "turn, expected",
    [("CW90", "R"), ("CCW90", "R'"), ("HALF_TURN", "R2")],
)
def test_structured_vla_intent_maps_three_turns_to_standard_moves(turn, expected) -> None:
    intent = ActionIntent(face="R", turn=turn, confidence=.9, source="test")
    assert intent.standard_move() == expected


def test_human_selected_face_can_supply_missing_vla_face() -> None:
    intent = ActionIntent(face=None, turn="CCW90", confidence=.8, source="turn-only-vla")
    assert intent.standard_move("F") == "F'"
    with pytest.raises(ValueError, match="requires a face"):
        intent.standard_move()
