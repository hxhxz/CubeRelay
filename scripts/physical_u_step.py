"""Single-seed one-scene U contact experiment. No post-reset state writes."""
import argparse
import json
from dataclasses import asdict
from pathlib import Path
import numpy as np
from PIL import Image, ImageDraw
from cube_relay.embodied.mujoco_v2 import MuJoCoEmbodiedBackend
from cube_relay.embodied.active_inspection_v7 import ContinuousActiveInspector
from cube_relay.embodied.physical_u import ContactUTurn, build_u_scene
from cube_relay.embodied.visual_turn_loop import compare_observations
from cube_relay.cube import CubeEngine


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--seed", type=int, default=0)
    p.add_argument("--output", type=Path, default=Path("results/physical_u_seed0"))
    p.add_argument("--video-timing", choices=["legacy","sim_time"], default="sim_time")
    args = p.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    b = MuJoCoEmbodiedBackend(physical_u=True, width=320, height=240,
                             video_path=args.output/"episode.mp4", video_timing=args.video_timing)
    report = {"seed": args.seed, "single_scene": True, "status": "NOT_STARTED"}
    capture = b.capture_rgbd
    epoch = "before"
    count = 0
    captures = []
    def record(*a, **kw):
        nonlocal count
        frame = capture(*a, **kw)
        name = f"{epoch}_{count:04d}_{frame.camera_name}"
        Image.fromarray(frame.rgb).save(args.output/(name+".png"))
        np.savez_compressed(args.output/(name+".npz"), depth=frame.depth_m,
                            camera_to_world=frame.calibration.camera_to_world,
                            intrinsics=[frame.calibration.fx,frame.calibration.fy,
                                        frame.calibration.cx,frame.calibration.cy])
        captures.append({"file":name,"epoch":epoch,"camera":frame.camera_name,
                         "simulation_time":frame.timestamp_seconds})
        count += 1
        return frame
    b.capture_rgbd = record
    executor = ContactUTurn(b)
    try:
        b.reset_random(args.seed, 15)
        (args.output/"scene.xml").write_text(build_u_scene(b.model_path))
        rgba = b.model.geom_rgba.copy()
        logical = b._appearance_state  # Integrity sentinel ONLY; not planning input.
        def forbidden(*a, **kw):
            raise AssertionError("Post-initialization software recolor / symbolic execution is forbidden")
        b._set_sticker_colors = forbidden
        b.engine.apply_move = forbidden
        b.reset_random = forbidden
        identities = (id(b.model), id(b.data))
        report["simulation_start_time"] = float(b.data.time)
        scan = ContinuousActiveInspector(b, "sequential").run(args.seed, reset_scene=False)
        report["scan"] = asdict(scan)
        print("scan", scan.success, scan.first_failure_stage, flush=True)
        if scan.success:
            report["expected"] = CubeEngine().apply_move(scan.reconstructed_facelets, "U")
            result = executor.dock_and_turn()
            report["execution"] = result
            print("execution", result, flush=True)
            epoch = "after"
            if result["success"]:
                observations = b.task_observe_released(3000)
                report["comparison"] = compare_observations(report["expected"], observations)
                comparison = report["comparison"]
                affected = list(range(9)) + ["URFDLB".index(face)*9+i for face in "RFLB" for i in range(3)]
                observed = comparison["observed_state"]
                missing = [i for i in affected if observed[i] == "?"]
                mismatch = [i for i in affected if observed[i] not in ("?", report["expected"][i])]
                report["affected_verification"] = {"indices": affected, "unknown": missing,
                    "mismatches": mismatch, "observed_count": len(affected)-len(missing),
                    "success": not missing and not mismatch and not comparison["conflicts"] and not comparison["differences"]}
                report["status"] = "AFFECTED_21_VERIFIED" if report["affected_verification"]["success"] else comparison["status"]
            else:
                report["status"] = "PHYSICAL_EXECUTION_FAILED"
        else:
            report["status"] = "INITIAL_SCAN_FAILED"
        report["no_recolor"] = bool(np.array_equal(rgba, b.model.geom_rgba))
        report["logical_state_unchanged"] = logical == b._appearance_state
        report["same_model_and_data"] = identities == (id(b.model), id(b.data))
        report["active_equalities"] = np.flatnonzero(b.data.eq_active).tolist()
        report["simulation_end_time"] = float(b.data.time)
        if "comparison" in report:
            canvas = Image.new("RGB", (660,300), "#cccccc")
            draw = ImageDraw.Draw(canvas)
            colors = dict(U="white",R="red",F="green",D="yellow",L="orange",B="blue")
            for row, (label,state) in enumerate([("before",scan.reconstructed_facelets),
                    ("predicted",report["expected"]),("observed",report["comparison"]["observed_state"])]):
                draw.text((5,row*100+35),label,fill="black")
                for i,color in enumerate(state):
                    face,cell=divmod(i,9)
                    x,y=100+face*90+cell%3*24,row*100+20+cell//3*24
                    draw.rectangle((x,y,x+22,y+22),fill=colors.get(color,"#666666"),outline="black")
                    draw.text((x+4,y+4),color,fill="black")
                    draw.text((100+face*90,row*100+3),"URFDLB"[face],fill="black")
            canvas.save(args.output/"facelets.png")
    finally:
        report["captures"] = captures
        report["trace"] = executor.trace
        (args.output/"report.json").write_text(json.dumps(report, indent=2,
            default=lambda x: x.tolist() if isinstance(x,np.ndarray) else x.item()))
        b.write_video()
        b.renderer.close()
    print(report["status"], flush=True)


if __name__ == "__main__":
    main()
