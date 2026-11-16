from typing import Protocol

from cube_relay.models import MoveRequest, MoveResult


class RobotAdapter(Protocol):
    def execute_move(self, request: MoveRequest) -> MoveResult: ...
    def emergency_stop(self) -> None: ...

