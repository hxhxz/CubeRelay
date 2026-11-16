from cube_relay.cube import CubeEngine
from cube_relay.embodied.coordinator import BaselineCoordinator
from cube_relay.embodied.execution import DeterministicTurnExecutor, FailureInjectingExecutor
from cube_relay.telemetry.trajectory import Trajectory


def test_closed_loop_repairs_failures_and_interventions(tmp_path) -> None:
    engine = CubeEngine()
    state, _ = engine.scramble(7, 12)
    executor = FailureInjectingExecutor(DeterministicTurnExecutor(), 0.2, 4)
    result = BaselineCoordinator(executor).run(
        state, seed=8, intervention_probability=0.12
    )
    assert result.solved
    assert result.metrics.failed_actions > 0
    assert result.metrics.interventions > 0
    assert result.metrics.replans == result.metrics.failed_actions + result.metrics.interventions
    path = tmp_path / "run.jsonl"
    result.trajectory.write_jsonl(path)
    replay = Trajectory.read_jsonl(path)
    replay.verify_chain()
    assert replay.events == result.trajectory.events

