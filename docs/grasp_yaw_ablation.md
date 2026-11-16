# Random-yaw physical grasp upgrade and paired ablation

> Historical yaw-stage report. Its physical model still contained a palm
> collision overlap and unintended sticker mass. Use
> [`contact_level_debugging.md`](contact_level_debugging.md) for corrected-model
> results and the current production configuration.

## Outcome

The normal CubeRelay grasp path now estimates square yaw from RGB-D image
outline edges/corners, transforms those pixels through camera calibration into
world coordinates, plans both opposing-face grasps, aligns the wrist, and runs
a verified physical execution sequence:

`PREGRASP → ALIGN → APPROACH → SLOW_CLOSE → BILATERAL_CONTACT → TRIAL_LIFT → STABILITY_CHECK → FULL_LIFT → ROTATE`

No robot weld, mocap body, cube pose assignment, or logical-state attachment is
used after reset. Insufficient sustained bilateral contact, excessive relative
motion, or contact loss stops execution and records a failure reason.

The full vision-position + vision-yaw 90-degree rotation rate is **51/100**,
up from the previously reported fixed-wrist result of **6/20 (30%)**. This is an
improvement, not a claim that physical grasping is solved; 49/100 scenes still
fail safely.

## Implementation

- `DeterministicCubeLocalizer` selects the top visible cube surface, extracts a
  monotonic convex hull, and fits a minimum-area rectangle over physical contour
  edge angles. It deliberately does not use a square's degenerate PCA principal
  axis. Yaw is represented modulo 90 degrees because the square outline cannot
  identify a labelled face direction.
- Camera RGB-D points are transformed by the calibrated 4×4 camera-to-world
  matrix before yaw fitting.
- The planner produces two wrist-yaw candidates separated by 90 degrees. Each
  records Cartesian reachability, conservative table/palm clearance, opposing
  face alignment score, current-wrist motion cost, and rejection reason.
- MuJoCo solved contacts provide independent left/right contact state and normal
  force. Closure is symmetric and slow, and stops only after sustained bilateral
  force. Trial lift compensates for stage gravity sag and uses the same 3 cm
  retention limit as rotation.
- Every episode records input/vision pose error, contact rates, normal forces,
  relative motion, trial/full-lift/full-rotation results, phase trace and failure
  type.

## Paired 4×100 ablation

```bash
MUJOCO_GL=glfw python scripts/evaluate_grasp_ablation.py \
  --episodes 100 --seed 0 --output results/grasp_yaw_ablation.json
```

All four groups use seeds 0–99, the same scramble count, model, mass, friction,
contact solver and controller. GT pose is read only by this evaluator and is
never exposed to normal perception or control.

| Input condition | Position error mean / P95 | Yaw error mean / P95 | L/R contact established | Trial lift | Full lift | 90° rotation |
|---|---:|---:|---:|---:|---:|---:|
| GT position + GT yaw | 0 / 0 cm | 0° / 0° | 82% / 71% | 43% | 43% | 43% |
| GT position + visual yaw | 0 / 0 cm | 0.284° / 0.710° | 82% / 80% | 53% | 52% | 52% |
| Visual position + GT yaw | 1.772 / 2.438 cm | 0° / 0° | 84% / 73% | 49% | 49% | 48% |
| Visual position + visual yaw | 1.772 / 2.438 cm | 0.284° / 0.710° | 80% / 77% | 52% | 51% | **51%** |

For the all-visual condition, mean left/right solved normal force is
13.21/12.44 N and mean maximum relative motion is 1.26 cm. Failures are:

- 34 sustained bilateral-contact failures;
- 14 trial-lift contact-loss/excess-motion failures;
- 1 full-lift instability;
- 0 rotation-only failures among stable full lifts.

The paired result shows neither GT yaw nor GT position materially raises the
final rate. Visual yaw is already substantially more accurate than needed for
the 12 cm face geometry. The remaining bottleneck is contact acquisition and
compliant grasp control, not perception. Friction was therefore **not** raised.
The controller fixes in this change are limited to sustained contact
confirmation, corrected trial-lift clearance and a consistent safety threshold.

An intermediate pre-control diagnostic is retained at
`results/grasp_yaw_ablation_precontrol.json`. It demonstrated 1–3% completion
after face alignment because the old trial-lift command only unloaded the pads
without clearing the table. Continuing a diagnosed episode showed 100%
bilateral contact and only 0.43 mm additional motion during full lift, which led
to the height-command correction.

## Reproducible artifacts

- Final 400-scene report: `results/grasp_yaw_ablation.json`
- Pre-control diagnostic: `results/grasp_yaw_ablation_precontrol.json`
- Successful trajectory metrics: `runs/embodied_v2_yaw_seed0/grasp_metrics.json`
- Successful video: `runs/embodied_v2_yaw_seed0/episode.mp4`
- Full automated suite: `111 passed in 19.26s`

## Fidelity boundary

- **Physical MuJoCo:** free rigid cube, pad/core contact, friction, solved normal
  forces, gravity, joint motion, lift, slip and whole-cube wrist rotation.
- **Deterministic perception:** rendered RGB-D pixels and calibration only. It
  never reads cube qpos, body pose or logical cube state.
- **Approximate planning:** this Cartesian gantry has analytic joint-limit IK
  and conservative geometric table/palm clearance, not a general numerical IK
  solver or mesh collision planner.
- **Simplified physical model:** one rigid cube body and a constrained face-turn
  fixture rather than 26 independently contacting cubies.
- **Mock:** the virtual human receiver still uses the explicitly labelled human
  handover weld. It is not used for robot grasp evaluation.

## Remaining work

The next optimization should target contact acquisition, using compliant
force/impedance control and a second candidate retry after a clean release. The
paired data does not justify increasing friction or replacing visual pose with
GT. More realistic arm links, numerical IK, mesh collision checking and a cubie
contact model remain separate fidelity upgrades.
