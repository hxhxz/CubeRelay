# CubeRelay Embodied Simulation v2

## Delivered vertical loop

`simulation/cube_relay_v2.xml` contains a free rigid cube at a seeded random table
position and yaw, 54 independently rendered sticker geoms, a Cartesian robot, two
physical fingers, RGB-D cameras and robot/human grasp constraints. The v2 demo does:

1. render RGB and metric depth;
2. use a replaceable VLM only for coarse cube visibility;
3. back-project segmented sticker pixels with calibrated intrinsics/extrinsics;
4. move physical robot joints to the estimated position;
5. require sustained bilateral pad contact, bounded relative slip and measured lift;
6. lift the free body, rotate the wrist joint and capture a new observation.

The perception localizer receives only `RGBDFrame`. It has no reference to `MjData`,
the logical cube string, geom ids or body position. Evaluation may read body position
after inference solely to calculate error, and labels that field as evaluation truth.

## State machine and replaceable VLM

`EmbodiedV2Controller` declares all requested nominal states and four explicit recovery
states. `OpenAICompatibleSceneVLM` works with cloud or vLLM OpenAI-compatible endpoints.
Its output is limited to coarse scene semantics. Deterministic code owns geometry,
sticker color fusion and Kociemba-backed legality checking.

## Fidelity table

| Component | Level | Current meaning |
| --- | --- | --- |
| Table, free cube, gravity/contact, arm/wrist/finger joints | **PHYSICS** | MuJoCo is stepped; pose changes come from dynamics and actuators |
| RGB-D localization | **REAL ALGORITHM / SIM SENSOR** | Uses rendered pixels, metric depth and camera calibration only |
| Grasp retention | **PHYSICS** | Parallel pads, normal force and friction only; no robot weld, mocap or post-reset cube pose assignment |
| Whole-cube rotation and reobservation | **PHYSICS** | Wrist joint moves the grasped free body and a new camera frame is rendered |
| 54-sticker fusion/legality | **REAL ALGORITHM** | Weighted visual observations + independent physical solvability check |
| Face turn | **SIMPLIFIED PHYSICAL FIXTURE** | Existing MuJoCo hinge must reach its angle before logical state/appearance commit; not 26 interlocking cubies |
| Human/robot handoff | **MOCK RECEIVER** | The virtual-human weld remains explicit Mock; robot grasp itself is friction-only |
| `MockEmbodiedBackend` | **MOCK** | Unit tests only; metrics identify it as Mock |

## Commands

Use Python 3.11–3.13 because MuJoCo 3.3.7 has no Python 3.14 wheel:

```bash
python3.13 -m venv .venv-sim
.venv-sim/bin/pip install -e '.[dev,simulation]'

# Minimum physical vertical loop + MP4 + metrics
MUJOCO_GL=glfw .venv-sim/bin/python scripts/embodied_v2_demo.py \
  --phase grasp --seed 4 --scramble-steps 15 --output runs/embodied_v2_seed4

# Random-scene physics evaluation
MUJOCO_GL=glfw .venv-sim/bin/python scripts/evaluate_embodied_v2.py \
  --episodes 20 --output results/embodied_v2.json

# Full regression, including MuJoCo
MUJOCO_GL=glfw .venv-sim/bin/python -m pytest -q
```

For a cloud/vLLM scene model, add `--vlm-endpoint URL --vlm-model MODEL`. The endpoint
must expose `/chat/completions` in OpenAI-compatible form.

## Remaining physical gap (not hidden by a mock)

The full six-face physical scan uses PLACE→RELEASE→OBSERVE→REGRASP→ROTATE, but some
random poses still fail regrasp or bottom exposure. The controller
therefore enters `RECOVERING_OBSERVATION` and then `ERROR` if a second pixel scan still
cannot produce all six legal faces. It does **not** fill missing stickers from simulator
truth. A production completion needs a collision-checked regrasp sequence or a physical
scan cradle, followed by random-pose six-face success evaluation.

Likewise, face turning is a measured constrained hinge approximation. It is not claimed
as a contact-rich 26-cubie Rubik's cube. Replacing it with a cubie/contact model or a
validated hardware turner is required before claiming high-fidelity manipulation.

See [`episode_grasp_audit.md`](episode_grasp_audit.md) for the invalidated weld-based
video, replacement acceptance criteria, active-observation evidence and failure modes.
