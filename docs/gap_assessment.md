# Embodied Agent upgrade: repository gap assessment

Assessment date: 2026-11-12.

## Reused without reimplementation

- `CubeEngine`: deterministic 54-facelet permutations, seeded scrambles and 18 moves.
- `CubeSolver`: Kociemba adapter and normalized move notation.
- Existing 60 unit/regression tests and CLI solving demo.

## Gaps found

| Capability | Before upgrade | This vertical slice |
| --- | --- | --- |
| Independent validation | Functions coupled to solver import | `StateValidator` report contract; physical checker injected |
| Random validation | 20 solve seeds | 1,000 seeded valid-state validation/property cases |
| Physics | None | MuJoCo scene and joint-feedback turn executor |
| Robot interface | None | Protocol plus deterministic and MuJoCo implementations |
| Vision | None | Pixel-only camera contract and estimator boundary |
| Repair | None | Failure/intervention-aware baseline coordinator |
| Experiment data | None | JSONL events, replay verification and metrics |

## Truthfulness boundary

- **Real implementation:** move engine, solver, state validator, event/replay/metric pipeline,
  MuJoCo stepping and joint-position feedback when the simulation extra is installed.
- **Approximate model:** the MuJoCo cube uses six independently actuated face plates. It
  measures actuator/joint dynamics but does not model 26 interlocking cubies, grasping,
  contact-rich sticker motion, or a production arm end-effector.
- **Mock/test double:** `DeterministicTurnExecutor` and `MockVisionEstimator`. They are named
  explicitly and never selected by the MuJoCo backend.
- **Not implemented:** a trained/calibrated facelet detector and real robot SDK driver.
  Camera frames therefore have no facelet state unless an estimator is explicitly supplied.

