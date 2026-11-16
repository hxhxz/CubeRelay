"""Model-independent VLA output contract."""

from typing import Literal

from pydantic import BaseModel, Field

Face = Literal["U", "R", "F", "D", "L", "B"]
Turn = Literal["CW90", "CCW90", "HALF_TURN"]
ControlMode = Literal[
    "human_face_vla_turn", "vla_discrete", "vla_continuous", "hierarchical"
]


class ActionIntent(BaseModel):
    face: Face | None
    turn: Turn
    confidence: float = Field(ge=0, le=1)
    source: str

    def standard_move(self, selected_face: Face | None = None) -> str:
        face = selected_face if self.face is None else self.face
        if face is None:
            raise ValueError("an autonomous action requires a face")
        suffix = {"CW90": "", "CCW90": "'", "HALF_TURN": "2"}[self.turn]
        return face + suffix
