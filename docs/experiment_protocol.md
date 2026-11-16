# CubeRelay experiment protocol

## Reproducibility

Run `python scripts/benchmark.py --output results/`. Scrambles, interventions and
fault positions are fixed by integer seed. Runtime is measured wall-clock and is the
only field expected to vary across machines.

## Tasks and baselines

- A: 20 seeds, no disturbance.
- B: 10 seeds, a seeded legal human move at step three.
- C: 10 seeds, the third robot action is a no-op.
- `fixed-plan`: consumes only the initial Kociemba plan.
- `replan`: discards the old plan and solves from confirmed actual state on mismatch.

Each baseline runs all 40 cases. Expected sanity check: both solve A; replanning
recovers B/C while fixed-plan normally does not. This comparison evaluates recovery,
not a new cube-solving algorithm.

## Metrics

`success`, `total_moves`, `human_moves`, `robot_moves`, `replan_count`,
`mismatch_count`, `recovery_success`, and `runtime_ms` are written per case to CSV
and JSON. Summary JSON contains success counts/rates and mean runtime.

## Observation policy

Manual and camera observations require physical-solvability validation, confidence
at least 0.8, and explicit human confirmation. A single camera view is only a
nine-sticker face scan. Six separately scanned faces are needed before a complete
state can even be proposed; that proposal still requires confirmation. Simulator
state is never passed into the visual estimator.

## Interpretation limits

Deterministic simulation success is not physical success. MuJoCo results measure an
approximate face-plate actuator, not grasp/reorientation of an interlocking cube.
No real-hardware success rate is reported without hardware logs and observations.

