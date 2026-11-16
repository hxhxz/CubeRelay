# MuJoCo contact-level grasp debugging

## Result

The robot grasp remains a free-body MuJoCo contact simulation: there is no robot
grasp weld, mocap attachment, or runtime assignment of the cube pose. The final
controller executes:

`PREGRASP → ALIGN → APPROACH → SLOW_CLOSE → BILATERAL_CONTACT → STABLE_HOLD → TRIAL_LIFT → STABILITY_CHECK → FULL_LIFT → ROTATE`

Every phase records left/right contact points, normals and solved normal force,
contact distance, cube and gripper pose, jaw gap, cube displacement and relative
slip. A failed contact check stops the motion and assigns a contact-level failure
class.

On paired seeds 0–99, the final full-vision path completes 59/100 physical
90-degree rotations. This is an increase from the supplied 51/100 baseline, but
41 scenes still fail safely; this is not a solved grasping system.

## Root causes found in the model audit

Two physical-model defects had to be corrected before controller comparisons
were valid:

1. The old palm box extended down into the side-grasp envelope. At approach it
   could hit the cube top and move the cube before finger closure. The palm is now
   above that envelope.
2. The 54 visual sticker geoms inherited density and raised the simulated cube
   mass from the intended 0.085 kg to 0.209848 kg. They now have zero density and
   remain visual-only; the measured cube body mass is 0.085 kg.

The audited model uses a 2 ms timestep, implicit-fast integrator, elliptic contact
cone, 12 cm cube, 15 cm × 2.4 cm × 12 cm opposing pads, finger joint range
0–75 mm, pad `solref=.004 1`, finger `kp=500`, and an explicit ±8 N actuator
force limit. Production pad sliding friction is 10.

Earlier result files without `mass_fixed` are retained for diagnosis only and
must not be compared with the final runs.

## Paired control experiments

E1 held GT position/yaw fixed and varied only contact geometry over 30 paired
seeds. The decisive results were:

| Geometry | 90° rotation |
|---|---:|
| z=-0.29 m, no tangent offset | 56.7% |
| z=-0.31 m | 3.3% |
| z=-0.27 m | 3.3% |
| tangent offset -10 mm | 53.3% |
| tangent offset +10 mm | **63.3%** |
| pregrasp gap 180 mm | 56.7% |
| pregrasp gap 150 mm | 30.0% |

E2 fixed the selected geometry and varied controller settings over the same 30
seeds:

| Controller | Rotation | Mean max slip |
|---|---:|---:|
| kp=500, unlimited force | 63.3% | 2.19 mm |
| close 0.75 s | 56.7% | 2.88 mm |
| close 3.0 s | 63.3% | 2.05 mm |
| kp=250 | 50.0% | 1.29 mm |
| kp=750 | 66.7% | 10.47 mm |
| kp=500, ±8 N | **63.3%** | **1.13 mm** |
| kp=500, ±15 N | 56.7% | 4.50 mm |

The 8 N cap was selected because it preserved completion while halving slip. The
small kp=750 gain included a numerical-instability failure and much higher slip.

With GT geometry over 100 paired seeds, friction 2 reached 70% and friction 10
reached 64%. A second full-vision paired control reversed that ordering: friction
10 reached 59%, versus 56% for friction 2. Production therefore keeps friction
10 because full vision is the actual deployment path; both results are reported
to avoid hiding this perception/contact interaction.

## Final 4×100 ablation

All conditions use seeds 0–99 and identical physical/controller parameters.
Simulator truth is available only to the evaluator for the two GT conditions and
scoring; the normal visual pipeline receives rendered RGB-D and calibration.

| Input | Position error mean / P95 | Yaw error mean / P95 | L/R contact | Trial lift | Full lift | 90° rotation |
|---|---:|---:|---:|---:|---:|---:|
| GT position + GT yaw | 0 / 0 cm | 0° / 0° | 74% / 77% | 64% | 64% | 64% |
| GT position + visual yaw | 0 / 0 cm | 0.287° / 0.833° | 67% / 81% | 61% | 61% | 61% |
| Visual position + GT yaw | 1.878 / 2.580 cm | 0° / 0° | 68% / 74% | 56% | 54% | 54% |
| Visual position + visual yaw | 1.878 / 2.580 cm | 0.287° / 0.833° | 67% / 78% | 60% | 59% | **59%** |

Full-vision failures are 21 single-side contacts that push the object, 17
geometric misalignments, one bilateral contact not sustained, one trial-lift
slip/contact loss and one contact numerical instability. Rotation introduces no
additional failures after a stable full lift in this run. The data supports the
user's instruction to stop prioritizing yaw: yaw error is below one degree at
P95, while position/contact acquisition dominates.

## Reproduce and inspect

```bash
MUJOCO_GL=glfw python scripts/contact_level_debug.py --study e1 --episodes 30 --seed 0
MUJOCO_GL=glfw python scripts/contact_level_debug.py --study e2 --episodes 30 --seed 0
MUJOCO_GL=glfw python scripts/contact_level_debug.py --study physics --episodes 100 --seed 0
MUJOCO_GL=glfw python scripts/evaluate_grasp_ablation.py \
  --episodes 100 --seed 0 --pad-friction 10 \
  --output results/contact_debug_final_ablation_friction10.json
python scripts/replay_contact_trace.py \
  results/contact_debug_final_ablation_friction10_failures.jsonl --seed 9 \
  --condition vision_position+vision_yaw
```

Primary artifacts:

- `results/contact_debug_e1_mass_fixed.json`
- `results/contact_debug_e2_mass_fixed.json`
- `results/contact_debug_physics_mass_fixed_100.json`
- `results/contact_debug_final_ablation_friction10.json`
- matching `*_failures.jsonl` files with complete failed-run traces
- `runs/contact_debug_final_success_seed1/`
- `runs/contact_debug_final_failure_seed9/`

## Fidelity boundary and remaining issue

- **Physical simulation:** free rigid cube, collision, friction, solved force,
  gravity, joints, lift, slip and wrist rotation.
- **Deterministic visual perception:** RGB-D and calibrated transforms only; no
  cube qpos/body pose is used by the normal localizer.
- **Approximation:** Cartesian gantry and box collision geometry, rather than a
  general articulated arm with mesh IK/collision planning.
- **Mock:** the separately labelled virtual-human receiver weld remains a handover
  mock and is not used by robot grasp evaluation.

The next high-value change is contact-aware lateral retry/compliant centering
after a clean release. It should target the 38/41 full-vision failures attributable
to initial geometry or one-sided pushing, without increasing force or hiding
failures with attachment.
