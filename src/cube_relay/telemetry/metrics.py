"""Episode metrics derived only from trajectory events."""

from dataclasses import dataclass

from .trajectory import Trajectory


@dataclass(frozen=True, slots=True)
class EpisodeMetrics:
    solved: bool
    attempted_actions: int
    successful_actions: int
    failed_actions: int
    interventions: int
    replans: int
    mean_action_seconds: float


def compute_metrics(trajectory: Trajectory, solved: bool) -> EpisodeMetrics:
    actions = [event for event in trajectory.events if event.kind == "ACTION_RESULT"]
    durations = [float(event.payload.get("duration_seconds", 0.0)) for event in actions]
    successes = sum(bool(event.payload.get("success")) for event in actions)
    return EpisodeMetrics(
        solved=solved,
        attempted_actions=len(actions),
        successful_actions=successes,
        failed_actions=len(actions) - successes,
        interventions=sum(event.kind == "HUMAN_INTERVENTION" for event in trajectory.events),
        replans=sum(event.kind == "PLAN_REPAIRED" for event in trajectory.events),
        mean_action_seconds=sum(durations) / len(durations) if durations else 0.0,
    )

