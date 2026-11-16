"""Run a single existing constrained-hinge step after a complete v8 scan."""
import argparse
import json
from dataclasses import asdict
from pathlib import Path

import numpy as np
import imageio.v2 as imageio
from PIL import Image, ImageDraw
from cube_relay.cube import CubeEngine, LEGAL_MOVES

from cube_relay.embodied.active_inspection_v7 import ContinuousActiveInspector
from cube_relay.embodied.mujoco_v2 import MuJoCoEmbodiedBackend
from cube_relay.embodied.visual_turn_loop import plan_visual_state, compare_observations


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--move", choices=LEGAL_MOVES, help="Explicit regression action; default is solver first move")
    parser.add_argument("--output", type=Path, default=Path("results/visual_turn_seed0"))
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    backend = MuJoCoEmbodiedBackend(width=320, height=240,
                                   video_path=args.output / "episode.mp4")
    captures = []
    original = backend.capture_rgbd
    epoch = "before"

    def capture(*a, **kw):
        frame = original(*a, **kw)
        name = f"{epoch}_{len(captures):04d}_{frame.camera_name}"
        Image.fromarray(frame.rgb).save(args.output / f"{name}.png")
        np.savez_compressed(args.output / f"{name}.npz", depth_m=frame.depth_m,
                            camera_to_world=frame.calibration.camera_to_world,
                            intrinsics=[frame.calibration.fx, frame.calibration.fy,
                                        frame.calibration.cx, frame.calibration.cy])
        captures.append(name)
        return frame

    backend.capture_rgbd = capture
    hinge_renderer = backend.mujoco.Renderer(backend._turner.model, height=240, width=320)
    hinge_frames = []

    def hinge_frame(model, data):
        hinge_renderer.update_scene(data, camera="overhead")
        hinge_frames.append(hinge_renderer.render().copy())

    backend._turner.frame_callback = hinge_frame
    backend._turner.require_scene_safety = True
    report = {"seed": args.seed,
              "model": "separate constrained hinge + feedback-gated appearance update; NOT 26-cubie",
              "contact_physics_verified": False,
              "limitation": "Existing hinge plates have collision disabled; no physical robot-to-fixture docking",
              "acceptance_passed": False}
    report["acceptance_definition"] = "Full contact-driven turn is not verified by this separate, collision-disabled plate model; simplified_loop_passed reports the supported scope."
    try:
        backend.reset_random(args.seed, 15)  # Deliberately discard truth metadata.
        scan = ContinuousActiveInspector(backend, "sequential").run(args.seed, reset_scene=False)
        report["scan"] = asdict(scan)
        if not scan.success:
            report["status"] = "INITIAL_SCAN_FAILED"
        else:
            plan = plan_visual_state(scan.reconstructed_facelets)
            report["plan"] = plan
            selected = args.move or (plan["solution"][0] if plan["solution"] else None)
            report["action_source"] = "regression_override" if args.move else "solver_first_move"
            if selected:
                report["selected_move"] = selected
                plan["predicted_next"] = CubeEngine().apply_move(plan["input_state"], selected)
            if not plan["solution"]:
                report["status"] = "ALREADY_SOLVED"
            else:
                feedback = backend.execute_physical_turn(selected)
                report["execution"] = asdict(feedback)
                report["joint_trace"] = backend._turner.last_trace
                epoch = "after"
                if feedback.success:
                    # Bounded reobservation only. Missing faces remain unknown;
                    # no old evidence or symbolic predictions fill them.
                    observations = backend.task_observe_held(1000)
                    report["comparison"] = compare_observations(plan["predicted_next"], observations)
                    report["post_turn_stages"] = [{"stage": "held", "comparison": report["comparison"]}]
                    if report["comparison"]["status"] == "UNVERIFIED_INSUFFICIENT_EVIDENCE":
                        # Reuse the existing monitored rigid rotation to bring
                        # the wrist upright before its table placement Skill.
                        joint = backend._joint("wrist_pitch_joint")
                        pitch = float(backend.data.qpos[backend.model.jnt_qposadr[joint]])
                        upright = backend.task_reorient("pitch", -pitch)
                        report["post_turn_stages"].append({"stage": "return_upright", "feedback": upright})
                        placed = backend.task_place_release() if upright.get("success") else {
                            "success": False, "failure_code": "RETURN_UPRIGHT_FAILED"}
                        report["post_turn_stages"].append({"stage": "place_release", "feedback": placed})
                        if placed.get("success"):
                            observations.extend(backend.task_observe_released(1010))
                            report["comparison"] = compare_observations(plan["predicted_next"], observations)
                            report["post_turn_stages"].append({"stage": "released", "comparison": report["comparison"]})
                    report["status"] = report["comparison"]["status"]
                else:
                    report["status"] = "JOINT_EXECUTION_FAILED"
                    capture("overhead")
    finally:
        report["simplified_loop_passed"] = report.get("status") == "VISUALLY_VERIFIED"
        if "plan" in report:
            colors = dict(U="white", R="red", F="green", D="yellow", L="orange", B="blue")
            canvas = Image.new("RGB", (660, 300), "#cccccc")
            draw = ImageDraw.Draw(canvas)
            states = [("before", report["plan"]["input_state"]),
                      ("predicted", report["plan"]["predicted_next"]),
                      ("observed", report.get("comparison", {}).get("observed_state", "?"*54))]
            for row, (label, state) in enumerate(states):
                draw.text((5, row*100+35), label, fill="black")
                for index, color in enumerate(state):
                    face, cell = divmod(index, 9)
                    x = 100 + face*90 + (cell%3)*24
                    y = row*100 + 20 + (cell//3)*24
                    draw.rectangle((x, y, x+22, y+22), fill=colors.get(color, "#666666"), outline="black")
                    draw.text((x+4, y+4), color, fill="black")
                    draw.text((100+face*90, row*100+3), "URFDLB"[face], fill="black")
            canvas.save(args.output / "facelets.png")
        report["captures"] = captures
        (args.output / "report.json").write_text(json.dumps(report, indent=2,
            default=lambda value: value.tolist() if isinstance(value, np.ndarray) else value.item()))
        backend.write_video()
        if hinge_frames:
            # Slow replay with endpoint holds; timestamps in joint_trace are
            # the authoritative simulation clock, not video playback time.
            imageio.mimsave(args.output / "hinge.mp4",
                           [hinge_frames[0]] * 10 + hinge_frames + [hinge_frames[-1]] * 10, fps=10)
        hinge_renderer.close()
        backend.renderer.close()
    print(json.dumps({"status": report.get("status"), "acceptance_passed": False,
                      "unknown": report.get("comparison", {}).get("unknown")}, default=str))


if __name__ == "__main__":
    main()
