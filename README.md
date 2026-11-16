# CubeRelay — human/robot Rubik's cube experiment platform

CubeRelay provides a deterministic 3×3 cube core, human/robot turn coordinator,
zero-build Web UI, observation confirmation, failure injection, plan repair,
reproducible baselines, trajectories, and an optional MuJoCo Embodied Simulation v2.
Facelets use `URFDLB`; each face is row-major when viewed from outside.

## Setup and test

```bash
python3 -m venv .venv
.venv/bin/pip install -e '.[dev]'
.venv/bin/pytest -q
```

## Web demo

```bash
.venv/bin/uvicorn cube_relay.api.main:app --app-dir src
```

Open `http://127.0.0.1:8000`. `sim` is an authoritative software simulator.
`dry_run` records requests but never marks them executed. `real` is disabled unless a
concrete driver and all safety gates are supplied.

## Demo

```bash
.venv/bin/python scripts/demo.py --scramble "R U R' U'"
```

The first solver call can be slower while the native module/tables are loaded.
`CubeSolver.warm_up()` exposes that cost separately from subsequent solves.

## Embodied experiment vertical slice

Run the dependency-light baseline with reproducible failures and interventions:

```bash
python scripts/evaluate.py --episodes 10 --failure-rate .15 --intervention-rate .08
python scripts/replay.py runs/episode_0000.jsonl
python scripts/benchmark.py --output results/
python scripts/demo_90s.py
```

Run Embodied Simulation v2 on Python 3.11-3.13 (MuJoCo 3.3.7 does not provide a
Python 3.14 wheel):

```bash
python -m pip install -e '.[dev,simulation]'
pytest -q tests/test_mujoco_integration.py
python scripts/evaluate.py --backend mujoco --episodes 1 --failure-rate 0
MUJOCO_GL=glfw python scripts/embodied_v2_demo.py --phase grasp --seed 4
MUJOCO_GL=glfw python scripts/evaluate_embodied_v2.py --episodes 20
MUJOCO_GL=glfw python scripts/evaluate_grasp_ablation.py --episodes 100 --seed 0
MUJOCO_GL=glfw python scripts/contact_level_debug.py --study e1 --episodes 30 --seed 0
MUJOCO_GL=glfw python scripts/evaluate_skill_agent.py --episodes 100 --seed 0
MUJOCO_GL=glfw python scripts/embodied_v2_demo.py \
  --phase grasp --seed 0 --output runs/embodied_v2_yaw_seed0
```

The v2 physics scene adds a randomly placed free rigid cube, 54 rendered stickers,
RGB-D localization, contact-gated grasp/lift, physical whole-cube wrist rotation and
reobservation. Face turns remain a measured constrained-hinge approximation, not a
26-cubie contact model. See [`docs/embodied_simulation_v2.md`](docs/embodied_simulation_v2.md)
for commands, fidelity labels and the remaining six-face occlusion gap. The random-yaw
grasp planner and paired 4×100 ablation are documented in
[`docs/grasp_yaw_ablation.md`](docs/grasp_yaw_ablation.md). The v6 failure-aware
planner is documented in `docs/failure_aware_skill_planning_v6_zh.md`.
CubeRelay v7 adds a task-level
`EmbodiedTaskAgent`; its current implementation status, source audit and honest
100-scene physical scan failure report are in
`docs/cuberelay_v7_audit_and_status_zh.md`.
The subsequent collision/inertia audit, contact telemetry, E1/E2/physics controls,
and final paired results are in
[`docs/contact_level_debugging.md`](docs/contact_level_debugging.md).
The safety-gated Skill API, Fixed/Rule/VLM Planner comparison and 3×100 paired
evaluation are documented in
[`docs/skill_based_embodied_agent.md`](docs/skill_based_embodied_agent.md).

Optional single-visible-face scanning requires `pip install -e '.[vision]'`. It uses
four supplied corners and six calibrated color samples. It cannot see hidden stickers;
all six faces must be scanned and the resulting state manually confirmed.

## Documentation

- [Experiment protocol](docs/experiment_protocol.md)
- [90-second demo](docs/demo_script.md)
- [ROS 2 / real robot boundary](docs/ros2_real_robot_integration.md)
- [Project report](docs/project_report.md)
- [Embodied Simulation v2](docs/embodied_simulation_v2.md)
- [Random-yaw grasp ablation](docs/grasp_yaw_ablation.md)
- [Contact-level grasp debugging](docs/contact_level_debugging.md)
- [Skill-Based Embodied Agent](docs/skill_based_embodied_agent.md)
- [基于技能的具身智能体架构（中文）](docs/skill_based_embodied_agent_zh.md)
- [Failure-Aware Skill Planning v6（中文）](docs/failure_aware_skill_planning_v6_zh.md)

Known limits: no trained/calibrated visual model, real robot driver, or hardware
validation is included. The MuJoCo cube is a six-face actuator approximation, not a
contact-rich interlocking-cubie manipulation model.
