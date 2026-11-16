# episode.mp4 grasp audit and replacement

## Audit result

The original `runs/embodied_v2_seed4/episode.mp4` was **Mock grasp evidence**. After
initial contact, `robot_grasp_weld` was enabled and a palm-contact suction fallback could
also enable it. Consequently, the video did not demonstrate force/friction retention.
Its reported 80% grasp metric is invalidated. Random initial placement still uses free-
joint `qpos`, which is allowed world generation and is never used after episode reset.

The old constrained face-turn fixture also changes rendered sticker colors only after a
hinge reaches its target. It remains labelled `SIMPLIFIED_PHYSICAL_FIXTURE`; it is not a
26-cubie physical turn.

## Replacement implementation

- `robot_grasp_weld` was removed from MJCF.
- No robot mocap body exists.
- No cube position or quaternion is assigned after reset.
- Two opposing pads close symmetrically and apply MuJoCo normal/contact/friction forces.
- A grasp passes only when bilateral contact fraction is at least 0.85, relative slip is
  at most 25 mm, and lift height is at least 60 mm.
- Wrist rotation uses a smooth trajectory. It does not call the cube engine or alter the
  54-facelet arrangement.
- The virtual-human weld is retained only as an explicitly labelled **Mock receiver**.

## Active observation

The physical sequence is `PLACE → RELEASE → OBSERVE → REGRASP → ROTATE`. Each visual
sticker stores color or `unknown`, confidence, source camera and frame id. Occluded cells
remain unknown until another pixel observation supplies evidence. Bottom observation is
attempted by pitch rotation followed by side placement; failure to regrasp or expose the
bottom remains a failed episode rather than a simulator-truth fallback.

## Known failure mode

Arbitrary continuous yaw can cause a cube corner to escape the parallel pads during
closure. These episodes are retained in evaluation output with contact/slip/lift values.
The current implementation intentionally reports failure instead of enabling a hidden
constraint. A production improvement should add visual yaw estimation and collision-
checked grasp-pose selection.

