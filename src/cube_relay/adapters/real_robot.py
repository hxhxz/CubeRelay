"""Default-deny boundary for future real hardware drivers."""

from cube_relay.models import MoveRequest, MoveResult


class RealRobotUnavailableError(RuntimeError):
    pass


class DisabledRealRobotAdapter:
    def __init__(self, *, driver_configured: bool = False, human_enabled: bool = False,
                 emergency_stop_ready: bool = False, workspace_clear: bool = False) -> None:
        if not all((driver_configured, human_enabled, emergency_stop_ready, workspace_clear)):
            raise RealRobotUnavailableError(
                "real mode disabled: driver, human enable, emergency stop, and workspace check required"
            )

    def execute_move(self, request: MoveRequest) -> MoveResult:
        raise RealRobotUnavailableError("no concrete real robot driver is installed")

    def emergency_stop(self) -> None:
        return None

