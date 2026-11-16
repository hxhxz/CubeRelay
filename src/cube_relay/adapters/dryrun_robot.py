"""Safe dry-run adapter: records intent and never claims physical execution."""

from cube_relay.models import MoveRequest, MoveResult


class DryRunRobotAdapter:
    def __init__(self, safety_mode: str = "disabled-output") -> None:
        self.safety_mode = safety_mode
        self.requests: list[dict[str, object]] = []
        self.stopped = False

    def execute_move(self, request: MoveRequest) -> MoveResult:
        record = {
            "move": request.move,
            "expected_before": request.expected_before,
            "plan_version": request.plan_version,
            "safety_mode": self.safety_mode,
        }
        self.requests.append(record)
        return MoveResult(
            success=False, move=request.move, observed_after=None,
            error="DRY_RUN_ONLY: no physical command sent; confirmation required",
            backend="dry_run",
        )

    def emergency_stop(self) -> None:
        self.stopped = True

