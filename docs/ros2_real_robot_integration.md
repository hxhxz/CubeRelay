# ROS 2 / real robot integration boundary

Real mode is default-disabled. The repository contains no configured vendor driver
and therefore sends no hardware command.

## Required physical primitives

Implement a concrete `RobotAdapter` using actions/services equivalent to:

1. `reorient_cube(target_face)` — establish the requested face in the fixture frame.
2. `rotate_face(face, radians, speed_limit)` — execute one supported face turn.
3. `confirm_observation()` — obtain a camera scan or explicit operator confirmation.
4. `emergency_stop()` — independent, immediately available stop path.

Map `U/R/F/D/L/B` through a calibrated cube frame, fixture frame, robot base frame,
tool-center point, and camera frame. Record calibration version with each trajectory.
Never update `actual_state` from a successful action return alone: a physical driver
must provide an independent observation or operator confirmation.

## Enable sequence

- Load an explicit robot/SDK configuration and verify model/serial number.
- Home at low speed with an empty fixture.
- Verify hardware emergency stop and software stop.
- Validate workspace exclusion and require a held/explicit human enable.
- Check fixture occupancy, cube pose and tool calibration.
- Advertise only empirically validated moves; return `UNSUPPORTED_MOVE` otherwise.

The first hardware milestone is one fixture-constrained 90-degree face turn, not all
18 moves. Humans and the arm must not enter the shared workspace simultaneously.
Any low-confidence/missing observation pauses execution. ROS 2/MoveIt planning is an
adapter concern and must not be imported into the deterministic coordinator.

## Feedback contract

Return requested move, controller result, measured joint/tool error, safety state and
an observation reference. Timeouts, collisions, no-op motion and mismatched face
turns are failures. Preserve actual state, emit mismatch, stop, observe, then replan.

