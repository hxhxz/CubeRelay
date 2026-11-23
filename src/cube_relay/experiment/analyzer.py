"""Automated offline causal analyzer and plotter for M4-C ZIP bundles."""

from __future__ import annotations

import csv
import io
import json
import math
import re
from pathlib import Path
from typing import Any
import zipfile

import numpy as np
from PIL import Image, ImageDraw, ImageFont


_SECRET_SCAN_RE = re.compile(r"(AIza[0-9A-Za-z_\-]{20,}|sk-[A-Za-z0-9]{16,}|Bearer\s+[A-Za-z0-9._\-]{8,})")
_PALETTE = {
    "baseline": (48, 214, 160),
    "translate_x_005": (84, 140, 255),
    "translate_x_010": (255, 191, 105),
    "vision_missing_negative_control": (255, 102, 123),
}


def _color_for(name: str, idx: int) -> tuple[int, int, int]:
    if name in _PALETTE:
        return _PALETTE[name]
    fallback = [(61, 232, 229), (192, 132, 252), (248, 113, 113), (52, 211, 153)]
    return fallback[idx % len(fallback)]


def _read_zip_json(zf: zipfile.ZipFile, name: str, default: Any = None) -> Any:
    if name not in zf.namelist():
        return default
    return json.loads(zf.read(name).decode("utf-8"))


def _read_zip_jsonl(zf: zipfile.ZipFile, name: str) -> list[dict[str, Any]]:
    if name not in zf.namelist():
        return []
    out: list[dict[str, Any]] = []
    for line in zf.read(name).decode("utf-8").splitlines():
        line = line.strip()
        if line:
            out.append(json.loads(line))
    return out


def _read_zip_csv(zf: zipfile.ZipFile, name: str) -> list[dict[str, str]]:
    if name not in zf.namelist():
        return []
    text = zf.read(name).decode("utf-8")
    return list(csv.DictReader(io.StringIO(text)))


def _float_or_none(val: Any) -> float | None:
    if val is None or val == "":
        return None
    try:
        out = float(val)
        return out if math.isfinite(out) else None
    except (TypeError, ValueError):
        return None


def _euclidean(a: list[float] | None, b: list[float] | None) -> float | None:
    if a is None or b is None or len(a) != len(b):
        return None
    return float(math.sqrt(sum((float(x) - float(y)) ** 2 for x, y in zip(a, b))))


def load_zip_bundle(zip_path: str | Path) -> dict[str, Any]:
    """Load an exported experiment ZIP package completely from disk."""
    zp = Path(zip_path).resolve()
    with zipfile.ZipFile(zp, mode="r") as zf:
        manifest = _read_zip_json(zf, "manifest.json", {})
        config = _read_zip_json(zf, "config.json", {})
        snapshot = _read_zip_json(zf, "session_snapshot.json", {})
        metrics = _read_zip_json(zf, "metrics.json", {})
        skill_executions = _read_zip_json(zf, "skill_executions.json", [])
        calibration = _read_zip_json(zf, "camera_calibration.json", {})
        frames = _read_zip_jsonl(zf, "frames.jsonl")
        poses = _read_zip_jsonl(zf, "pose_estimates.jsonl")
        grasp_targets = _read_zip_jsonl(zf, "grasp_targets.jsonl")
        verifications = _read_zip_jsonl(zf, "contact_verifications.jsonl")
        decisions = _read_zip_jsonl(zf, "decision_events.jsonl")
        traces = _read_zip_jsonl(zf, "trace_events.jsonl")
        observations = _read_zip_jsonl(zf, "observations.jsonl")
        robot_states = _read_zip_csv(zf, "robot_states.csv")
        traj_commands = _read_zip_csv(zf, "trajectory_commands.csv")
        contact_samples = _read_zip_csv(zf, "contact_samples.csv")
        audit_poses = _read_zip_csv(zf, "audit_only_poses.csv")

        secret_hits: list[str] = []
        for member in zf.namelist():
            if member.endswith((".json", ".jsonl", ".csv", ".md")):
                text = zf.read(member).decode("utf-8", errors="replace")
                if _SECRET_SCAN_RE.search(text):
                    secret_hits.append(member)

    return {
        "zip_path": str(zp),
        "manifest": manifest,
        "config": config,
        "snapshot": snapshot,
        "metrics": metrics,
        "skill_executions": skill_executions,
        "calibration": calibration,
        "frames": frames,
        "pose_estimates": poses,
        "grasp_targets": grasp_targets,
        "contact_verifications": verifications,
        "decision_events": decisions,
        "trace_events": traces,
        "observations": observations,
        "robot_states": robot_states,
        "trajectory_commands": traj_commands,
        "contact_samples": contact_samples,
        "audit_only_poses": audit_poses,
        "secret_hits": secret_hits,
    }


def extract_bundle_metrics(bundle: dict[str, Any], *, label: str | None = None) -> dict[str, Any]:
    """Extract all 12 Section-XI metrics from one loaded experiment ZIP bundle."""
    cfg = bundle["config"]
    snap = bundle["snapshot"]
    manifest = bundle["manifest"]
    pert = cfg.get("perturbation") or {}
    cond_name = label or str(pert.get("condition") or cfg.get("run_id") or Path(bundle["zip_path"]).stem)

    # 1. Ground truth initial position (audit-only)
    init_gt_row = next(
        (r for r in bundle["audit_only_poses"] if r.get("phase") == "INIT_SETTLED"),
        bundle["audit_only_poses"][0] if bundle["audit_only_poses"] else None,
    )
    gt_pos: list[float] | None = None
    if init_gt_row is not None:
        gt_pos = [
            float(init_gt_row["cube_gt_x_m"]),
            float(init_gt_row["cube_gt_y_m"]),
            float(init_gt_row["cube_gt_z_m"]),
        ]
    elif pert.get("perturbation_metadata") and pert["perturbation_metadata"].get("perturbed_pos"):
        gt_pos = [float(v) for v in pert["perturbation_metadata"]["perturbed_pos"]]

    # 2 & 3. RGB-D pose estimates: observe_workspace and pre-grasp observe_cube
    poses = bundle["pose_estimates"]
    valid_poses = [p for p in poses if p.get("quality_status") == "VALID" and p.get("estimated_center_world_m")]
    grasp_targets = bundle["grasp_targets"]
    first_grasp = grasp_targets[0] if grasp_targets else None
    grasp_pose = None
    if first_grasp is not None:
        grasp_pose = next(
            (p for p in poses if p.get("pose_estimate_id") == first_grasp.get("pose_estimate_id")),
            None,
        )
    workspace_pose = valid_poses[0] if valid_poses else (poses[0] if poses else None)
    primary_pose = grasp_pose or (valid_poses[0] if valid_poses else None)
    est_pos = (
        [float(v) for v in primary_pose["estimated_center_world_m"]]
        if primary_pose and primary_pose.get("estimated_center_world_m")
        else None
    )
    ws_est_pos = (
        [float(v) for v in workspace_pose["estimated_center_world_m"]]
        if workspace_pose and workspace_pose.get("estimated_center_world_m")
        else None
    )
    loc_err_3d = _euclidean(est_pos, gt_pos)
    loc_err_xy = _euclidean(est_pos[:2], gt_pos[:2]) if est_pos and gt_pos else None

    # 4 & 5 & 6. Grasp target vs actual EE pose & trajectory
    tgt_pose_dict = (first_grasp or {}).get("target_end_effector_pose") or {}
    if all(tgt_pose_dict.get(k) is not None for k in ("x_m", "y_m", "z_m")):
        tgt_xyz = [float(tgt_pose_dict["x_m"]), float(tgt_pose_dict["y_m"]), float(tgt_pose_dict["z_m"])]
    elif tgt_pose_dict.get("robot_x_ctrl") is not None and tgt_pose_dict.get("robot_y_ctrl") is not None:
        cz = tgt_pose_dict.get("contact_z_ctrl", -0.29)
        tgt_xyz = [
            float(tgt_pose_dict["robot_x_ctrl"]),
            float(tgt_pose_dict["robot_y_ctrl"]),
            round(1.09 + float(cz), 6),
        ]
    else:
        tgt_xyz = None
    contact_ee_dict = (first_grasp or {}).get("actual_end_effector_pose_at_contact") or {}
    actual_ee_at_contact = (
        [float(v) for v in contact_ee_dict["position_world_m"]]
        if contact_ee_dict.get("position_world_m")
        else None
    )
    grasp_traj_rows = (
        [r for r in bundle["robot_states"] if r.get("grasp_target_id") == first_grasp.get("grasp_target_id")]
        if first_grasp is not None
        else []
    )
    # Identify settled SLOW_CLOSE / BILATERAL_CONTACT / end-of-APPROACH EE pose
    actual_ee_close: list[float] | None = actual_ee_at_contact
    if actual_ee_close is None and grasp_traj_rows:
        close_rows = [r for r in grasp_traj_rows if r.get("controller_phase") in {"SLOW_CLOSE", "BILATERAL_CONTACT", "STABLE_HOLD"}]
        ref_row = close_rows[-1] if close_rows else grasp_traj_rows[-1]
        ax = _float_or_none(ref_row.get("ee_actual_x_m"))
        ay = _float_or_none(ref_row.get("ee_actual_y_m"))
        az = _float_or_none(ref_row.get("ee_actual_z_m"))
        if ax is not None and ay is not None and az is not None:
            actual_ee_close = [ax, ay, az]

    ee_target_vs_actual_xy = (
        _euclidean(tgt_xyz[:2], actual_ee_close[:2])
        if tgt_xyz and actual_ee_close
        else None
    )

    # 7 & 8. Slip and bilateral contact
    cvs = bundle["contact_verifications"]
    initial_cv = next((cv for cv in cvs if "initial" in str(cv.get("skill_name", "")).lower()), cvs[0] if cvs else None)
    regrasp_cv = next((cv for cv in cvs if "regrasp" in str(cv.get("skill_name", "")).lower()), None)
    slips = [float(cv["relative_slip_m"]) for cv in cvs if cv.get("relative_slip_m") is not None]
    bilat_rates = [float(cv["bilateral_contact_fraction"]) for cv in cvs if cv.get("bilateral_contact_fraction") is not None]
    passed_count = sum(1 for cv in cvs if cv.get("verification_result"))

    # 10. Visual freshness & frame sync
    frames_by_id = {f["frame_id"]: f for f in bundle["frames"] if f.get("frame_id")}
    pose_age_sim_s = _float_or_none((first_grasp or {}).get("pose_age_sim_s"))
    max_rgb_depth_delta = max(
        (float(f.get("rgb_depth_sim_time_delta_s") or 0.0) for f in bundle["frames"]),
        default=0.0,
    )
    frame_bound_ok = bool(primary_pose and primary_pose.get("frame_id") in frames_by_id)

    # 11. Data source compliance
    ref_ok = bool((manifest.get("reference_integrity") or {}).get("ok", False))
    source_kinds_poses = {p.get("source_kind") for p in poses}
    gt_leaked = (
        "SIMULATOR_GROUND_TRUTH_AUDIT_ONLY" in source_kinds_poses
        or bool(bundle["secret_hits"])
    )
    if pert.get("vision_fault_mode"):
        # Negative control MUST have zero valid poses and zero grasp targets
        neg_clean = (len(valid_poses) == 0 and len(grasp_targets) == 0)
    else:
        neg_clean = True

    # 12. Timing breakdown
    mission = snap.get("mission") or {}
    timing = snap.get("timing_metrics") or {}
    skills_timing = [
        {
            "execution_id": ex.get("execution_id"),
            "skill_id": ex.get("skill_id"),
            "status": ex.get("status"),
            "elapsed_sec": ex.get("elapsed_sec"),
        }
        for ex in bundle["skill_executions"]
    ]

    return {
        "condition": cond_name,
        "run_id": cfg.get("run_id"),
        "seed": cfg.get("seed"),
        "perturbation": pert,
        "vision_fault_mode": pert.get("vision_fault_mode"),
        # 1
        "initial_gt_pos_m": gt_pos,
        # 2
        "workspace_rgbd_est_pos_m": ws_est_pos,
        "grasp_rgbd_est_pos_m": est_pos,
        "pose_estimate_id": primary_pose.get("pose_estimate_id") if primary_pose else None,
        "pose_version": primary_pose.get("pose_version") if primary_pose else None,
        "pose_camera_id": primary_pose.get("camera_id") if primary_pose else None,
        "pose_frame_id": primary_pose.get("frame_id") if primary_pose else None,
        # 3
        "visual_localization_error_3d_m": round(loc_err_3d, 6) if loc_err_3d is not None else None,
        "visual_localization_error_xy_m": round(loc_err_xy, 6) if loc_err_xy is not None else None,
        # 4
        "grasp_target_id": first_grasp.get("grasp_target_id") if first_grasp else None,
        "grasp_target_ee_xyz_m": tgt_xyz,
        "grasp_target_object_center_m": first_grasp.get("object_center_world_m") if first_grasp else None,
        "grasp_reachability_status": first_grasp.get("reachability_status") if first_grasp else None,
        "grasp_collision_status": first_grasp.get("collision_check_status") if first_grasp else None,
        # 5
        "actual_ee_close_xyz_m": actual_ee_close,
        "ee_target_vs_actual_xy_error_m": round(ee_target_vs_actual_xy, 6) if ee_target_vs_actual_xy is not None else None,
        # 6
        "robot_state_sample_count": len(bundle["robot_states"]),
        "grasp_trajectory_id": grasp_traj_rows[0]["trajectory_id"] if grasp_traj_rows else None,
        # 7
        "max_relative_slip_m": round(max(slips), 6) if slips else None,
        "mean_relative_slip_m": round(sum(slips) / len(slips), 6) if slips else None,
        # 8
        "bilateral_contact_verification_count": len(cvs),
        "bilateral_contact_passed_count": passed_count,
        "mean_bilateral_contact_fraction": round(sum(bilat_rates) / len(bilat_rates), 6) if bilat_rates else None,
        "initial_grasp_verification": initial_cv,
        "regrasp_verification": regrasp_cv,
        # 9
        "mission_status": mission.get("status"),
        "failure_reason": mission.get("failure_reason"),
        "skill_execution_count": len(bundle["skill_executions"]),
        # 10
        "pose_age_sim_s": round(pose_age_sim_s, 6) if pose_age_sim_s is not None else None,
        "max_rgb_depth_sim_time_delta_s": round(max_rgb_depth_delta, 6),
        "frame_bound_ok": frame_bound_ok,
        # 11
        "reference_integrity_ok": ref_ok,
        "ground_truth_leakage_detected": gt_leaked,
        "negative_control_clean": neg_clean,
        "data_source_compliant": bool(ref_ok and not gt_leaked and neg_clean),
        # 12
        "sim_time_s": timing.get("sim_time"),
        "skill_duration_sim_s": timing.get("skill_duration_sim_s"),
        "total_execution_wall_s": timing.get("total_execution_wall_s"),
        "skills_timing": skills_timing,
    }


def _draw_canvas(title: str, subtitle: str, width: int = 1280, height: int = 760) -> tuple[Image.Image, ImageDraw.ImageDraw]:
    img = Image.new("RGB", (width, height), (11, 17, 29))
    draw = ImageDraw.Draw(img)
    draw.rectangle([16, 16, width - 16, height - 16], outline=(38, 52, 78), width=2)
    draw.text((36, 28), title, fill=(241, 245, 249), font_size=24)
    draw.text((36, 60), subtitle, fill=(148, 163, 184), font_size=15)
    return img, draw


def _map_xy(
    val_x: float,
    val_y: float,
    *,
    xmin: float,
    xmax: float,
    ymin: float,
    ymax: float,
    box: tuple[int, int, int, int],
) -> tuple[float, float]:
    x0, y0, x1, y1 = box
    dx = xmax - xmin or 1.0
    dy = ymax - ymin or 1.0
    px = x0 + (val_x - xmin) / dx * (x1 - x0)
    py = y1 - (val_y - ymin) / dy * (y1 - y0)
    return px, py


def _draw_axes_grid(
    draw: ImageDraw.ImageDraw,
    *,
    box: tuple[int, int, int, int],
    xmin: float,
    xmax: float,
    ymin: float,
    ymax: float,
    xlabel: str,
    ylabel: str,
    ticks: int = 4,
) -> None:
    x0, y0, x1, y1 = box
    draw.rectangle([x0, y0, x1, y1], fill=(16, 24, 39), outline=(51, 65, 85), width=2)
    for i in range(ticks + 1):
        frac = i / ticks
        gx = x0 + frac * (x1 - x0)
        gy = y1 - frac * (y1 - y0)
        draw.line([(gx, y0), (gx, y1)], fill=(28, 39, 59), width=1)
        draw.line([(x0, gy), (x1, gy)], fill=(28, 39, 59), width=1)
        xv = xmin + frac * (xmax - xmin)
        yv = ymin + frac * (ymax - ymin)
        draw.text((gx - 18, y1 + 6), f"{xv:.3f}", fill=(148, 163, 184), font_size=12)
        draw.text((max(20, x0 - 66), gy - 7), f"{yv:.3f}", fill=(148, 163, 184), font_size=12)
    draw.text(((x0 + x1) / 2 - 48, y1 + 42), xlabel, fill=(203, 213, 225), font_size=14)
    draw.text((x0, y0 - 22), ylabel, fill=(203, 213, 225), font_size=14)


def _draw_legend(draw: ImageDraw.ImageDraw, items: list[tuple[str, tuple[int, int, int]]], x: int, y: int) -> None:
    cy = y
    for label, col in items:
        draw.rectangle([x, cy + 3, x + 16, cy + 15], fill=col)
        draw.text((x + 24, cy), label, fill=(226, 232, 240), font_size=13)
        cy += 22


def _plot_3d_localization(metrics_list: list[dict[str, Any]], out_path: Path) -> None:
    img, draw = _draw_canvas(
        "M4-C Localization Comparison: Ground Truth vs RGB-D Estimate",
        "World XY plane (top-down, left) & X/Y/Z error magnitude (right)",
    )
    box_left = (95, 115, 650, 660)
    xs: list[float] = []
    ys: list[float] = []
    for m in metrics_list:
        for p in (m.get("initial_gt_pos_m"), m.get("grasp_rgbd_est_pos_m"), m.get("workspace_rgbd_est_pos_m")):
            if p:
                xs.append(float(p[0]))
                ys.append(float(p[1]))
    xmin, xmax = (min(xs) - 0.03, max(xs) + 0.03) if xs else (0.0, 0.3)
    ymin, ymax = (min(ys) - 0.03, max(ys) + 0.03) if ys else (-0.25, 0.05)
    _draw_axes_grid(draw, box=box_left, xmin=xmin, xmax=xmax, ymin=ymin, ymax=ymax, xlabel="World X (m)", ylabel="World Y (m)")

    legend: list[tuple[str, tuple[int, int, int]]] = []
    for idx, m in enumerate(metrics_list):
        col = _color_for(m["condition"], idx)
        legend.append((f"{m['condition']} ({m['mission_status']})", col))
        gt = m.get("initial_gt_pos_m")
        est = m.get("grasp_rgbd_est_pos_m") or m.get("workspace_rgbd_est_pos_m")
        if gt:
            gx, gy = _map_xy(gt[0], gt[1], xmin=xmin, xmax=xmax, ymin=ymin, ymax=ymax, box=box_left)
            draw.ellipse([gx - 8, gy - 8, gx + 8, gy + 8], outline=col, width=3)
            draw.text((gx + 10, gy - 14), f"GT({gt[0]:.3f})", fill=col, font_size=12)
        if est:
            ex, ey = _map_xy(est[0], est[1], xmin=xmin, xmax=xmax, ymin=ymin, ymax=ymax, box=box_left)
            draw.rectangle([ex - 6, ey - 6, ex + 6, ey + 6], fill=col)
            if gt:
                draw.line([(gx, gy), (ex, ey)], fill=col, width=2)
            draw.text((ex + 10, ey + 2), f"RGBD({est[0]:.3f})", fill=(241, 245, 249), font_size=12)

    box_right = (740, 145, 1220, 660)
    errs = [float(m["visual_localization_error_3d_m"] or 0.0) * 1000.0 for m in metrics_list]
    max_e = max(errs + [10.0]) * 1.25
    _draw_axes_grid(draw, box=box_right, xmin=0.0, xmax=float(len(metrics_list)), ymin=0.0, ymax=max_e, xlabel="Condition Index", ylabel="3D Error (mm)")
    bar_w = max(28, int((box_right[2] - box_right[0]) / max(1, len(metrics_list)) * 0.55))
    for idx, m in enumerate(metrics_list):
        col = _color_for(m["condition"], idx)
        cx = box_right[0] + (idx + 0.5) / max(1, len(metrics_list)) * (box_right[2] - box_right[0])
        err_mm = m["visual_localization_error_3d_m"]
        if err_mm is not None:
            top_y = _map_xy(0, err_mm * 1000.0, xmin=0, xmax=1, ymin=0, ymax=max_e, box=box_right)[1]
            draw.rectangle([cx - bar_w / 2, top_y, cx + bar_w / 2, box_right[3]], fill=col)
            draw.text((cx - 24, top_y - 18), f"{err_mm*1000.0:.1f}mm", fill=col, font_size=13)
        else:
            draw.text((cx - 34, box_right[3] - 32), "MISSING", fill=col, font_size=13)
        draw.text((cx - 38, box_right[3] + 24), m["condition"][:14], fill=(203, 213, 225), font_size=11)
    _draw_legend(draw, legend, 745, 26)
    img.save(out_path)


def _plot_grasp_target_comparison(deltas: list[dict[str, Any]], out_path: Path) -> None:
    img, draw = _draw_canvas(
        "M4-C Grasp Target & Perturbation Delta-X Comparison",
        "Comparing Delta X (relative to baseline): GT vs RGB-D Estimate vs Grasp Target vs Actual EE",
    )
    box = (110, 140, 1210, 650)
    vals = [
        float(d[k])
        for d in deltas
        for k in ("delta_x_ground_truth_m", "delta_x_rgbd_estimate_m", "delta_x_grasp_target_m", "delta_x_actual_end_effector_m")
        if d.get(k) is not None
    ]
    ymin = min(vals + [-0.01]) - 0.01
    ymax = max(vals + [0.12]) + 0.02
    _draw_axes_grid(draw, box=box, xmin=0.0, xmax=float(len(deltas)), ymin=ymin, ymax=ymax, xlabel="Condition", ylabel="Delta X vs Baseline (m)")

    series = [
        ("delta_x_ground_truth_m", "GT Cube dX", (148, 163, 184)),
        ("delta_x_rgbd_estimate_m", "RGB-D Est dX", (61, 232, 229)),
        ("delta_x_grasp_target_m", "Grasp Target dX", (84, 140, 255)),
        ("delta_x_actual_end_effector_m", "Actual EE dX", (48, 214, 160)),
    ]
    zero_y = _map_xy(0, 0.0, xmin=0, xmax=1, ymin=ymin, ymax=ymax, box=box)[1]
    draw.line([(box[0], zero_y), (box[2], zero_y)], fill=(100, 116, 139), width=1)

    group_w = (box[2] - box[0]) / max(1, len(deltas))
    bar_w = max(14, int(group_w * 0.16))
    for i, d in enumerate(deltas):
        gx = box[0] + (i + 0.5) * group_w
        for j, (key, _, col) in enumerate(series):
            val = d.get(key)
            bx = gx + (j - 1.5) * (bar_w + 4)
            if val is not None:
                ty = _map_xy(0, float(val), xmin=0, xmax=1, ymin=ymin, ymax=ymax, box=box)[1]
                draw.rectangle([bx - bar_w / 2, min(ty, zero_y), bx + bar_w / 2, max(ty, zero_y)], fill=col)
                draw.text((bx - 16, min(ty, zero_y) - 16), f"{float(val):+.3f}", fill=col, font_size=11)
            else:
                draw.text((bx - 12, zero_y - 16), "NA", fill=(255, 102, 123), font_size=11)
        draw.text((gx - 65, box[3] + 24), d["condition"], fill=(226, 232, 240), font_size=13)
    _draw_legend(draw, [(lbl, col) for _, lbl, col in series], 1030, 28)
    img.save(out_path)


def _plot_ee_trajectories(bundles: list[tuple[str, dict[str, Any]]], out_path: Path) -> None:
    img, draw = _draw_canvas(
        "M4-C End-Effector Actual Trajectory Comparison",
        "Executed ee_actual_x_m over sim_time (left) & top-down XY trajectory (right)",
    )
    box_xt = (95, 135, 650, 660)
    box_xy = (735, 135, 1220, 660)
    ts: list[float] = []
    xs: list[float] = []
    ys: list[float] = []
    for _, b in bundles:
        for r in b["robot_states"]:
            t = _float_or_none(r.get("sim_time"))
            x = _float_or_none(r.get("ee_actual_x_m"))
            y = _float_or_none(r.get("ee_actual_y_m"))
            if t is not None and x is not None and y is not None:
                ts.append(t)
                xs.append(x)
                ys.append(y)
    tmin, tmax = (min(ts), max(ts) + 0.1) if ts else (0.0, 10.0)
    xmin, xmax = (min(xs) - 0.03, max(xs) + 0.03) if xs else (-0.1, 0.3)
    ymin, ymax = (min(ys) - 0.03, max(ys) + 0.03) if ys else (-0.25, 0.05)

    _draw_axes_grid(draw, box=box_xt, xmin=tmin, xmax=tmax, ymin=xmin, ymax=xmax, xlabel="sim_time (s)", ylabel="ee_actual_x (m)")
    _draw_axes_grid(draw, box=box_xy, xmin=xmin, xmax=xmax, ymin=ymin, ymax=ymax, xlabel="ee_actual_x (m)", ylabel="ee_actual_y (m)")

    legend: list[tuple[str, tuple[int, int, int]]] = []
    for idx, (name, b) in enumerate(bundles):
        col = _color_for(name, idx)
        legend.append((name, col))
        pts_xt: list[tuple[float, float]] = []
        pts_xy: list[tuple[float, float]] = []
        rows = b["robot_states"]
        stride = max(1, len(rows) // 450)
        for r in rows[::stride]:
            t = _float_or_none(r.get("sim_time"))
            x = _float_or_none(r.get("ee_actual_x_m"))
            y = _float_or_none(r.get("ee_actual_y_m"))
            if t is not None and x is not None and y is not None:
                pts_xt.append(_map_xy(t, x, xmin=tmin, xmax=tmax, ymin=xmin, ymax=xmax, box=box_xt))
                pts_xy.append(_map_xy(x, y, xmin=xmin, xmax=xmax, ymin=ymin, ymax=ymax, box=box_xy))
        if len(pts_xt) >= 2:
            draw.line(pts_xt, fill=col, width=2)
            draw.line(pts_xy, fill=col, width=2)
    _draw_legend(draw, legend, 980, 26)
    img.save(out_path)


def _plot_contact_timeseries(
    bundles: list[tuple[str, dict[str, Any]]],
    *,
    mode: str,
    out_path: Path,
) -> None:
    is_force = (mode == "forces")
    title = (
        "M4-C Left & Right Finger Normal Force Time-Series"
        if is_force
        else "M4-C Cube-to-Gripper Relative Slip Time-Series"
    )
    subtitle = (
        "Solid = Left Normal Force (N), Dashed = Right Normal Force (N)"
        if is_force
        else "Maximum & instantaneous relative slip (m) vs 0.030 m limit"
    )
    img, draw = _draw_canvas(title, subtitle)
    box = (95, 135, 1210, 660)
    ts: list[float] = []
    vs: list[float] = []
    for _, b in bundles:
        for r in b["contact_samples"]:
            t = _float_or_none(r.get("sim_time"))
            if t is None:
                continue
            if is_force:
                lf = _float_or_none(r.get("left_normal_force_n")) or 0.0
                rf = _float_or_none(r.get("right_normal_force_n")) or 0.0
                vs.extend([lf, rf])
            else:
                vs.append(_float_or_none(r.get("relative_slip_m")) or 0.0)
            ts.append(t)
    tmin, tmax = (min(ts), max(ts) + 0.1) if ts else (0.0, 10.0)
    ymax = max(vs + ([5.0] if is_force else [0.035])) * 1.15
    _draw_axes_grid(
        draw,
        box=box,
        xmin=tmin,
        xmax=tmax,
        ymin=0.0,
        ymax=ymax,
        xlabel="sim_time (s)",
        ylabel="Force (N)" if is_force else "Relative Slip (m)",
    )
    if not is_force:
        lim_y = _map_xy(0, 0.03, xmin=0, xmax=1, ymin=0.0, ymax=ymax, box=box)[1]
        draw.line([(box[0], lim_y), (box[2], lim_y)], fill=(255, 102, 123), width=2)
        draw.text((box[0] + 10, lim_y - 18), "Slip Threshold = 0.030 m", fill=(255, 102, 123), font_size=12)

    legend: list[tuple[str, tuple[int, int, int]]] = []
    for idx, (name, b) in enumerate(bundles):
        col = _color_for(name, idx)
        legend.append((name, col))
        rows = b["contact_samples"]
        stride = max(1, len(rows) // 500)
        pts1: list[tuple[float, float]] = []
        pts2: list[tuple[float, float]] = []
        for r in rows[::stride]:
            t = _float_or_none(r.get("sim_time"))
            if t is None:
                continue
            if is_force:
                lf = _float_or_none(r.get("left_normal_force_n")) or 0.0
                rf = _float_or_none(r.get("right_normal_force_n")) or 0.0
                pts1.append(_map_xy(t, lf, xmin=tmin, xmax=tmax, ymin=0.0, ymax=ymax, box=box))
                pts2.append(_map_xy(t, rf, xmin=tmin, xmax=tmax, ymin=0.0, ymax=ymax, box=box))
            else:
                sl = _float_or_none(r.get("relative_slip_m")) or 0.0
                pts1.append(_map_xy(t, sl, xmin=tmin, xmax=tmax, ymin=0.0, ymax=ymax, box=box))
        if len(pts1) >= 2:
            draw.line(pts1, fill=col, width=2)
        if is_force and len(pts2) >= 2:
            for a, c in zip(pts2[::2], pts2[1::2]):
                draw.line([a, c], fill=col, width=2)
    _draw_legend(draw, legend, 980, 26)
    img.save(out_path)


def _plot_causal_diagram(metrics_list: list[dict[str, Any]], deltas: list[dict[str, Any]], out_path: Path) -> None:
    img, draw = _draw_canvas(
        "M4-C Visual Grasp Causal Chain Audit Diagram",
        "Camera Frame -> Pose Estimate -> Grasp Target -> Trajectory -> Contact Verification",
        width=1360,
        height=760,
    )
    delta_by_name = {d["condition"]: d for d in deltas}
    stages = [
        ("1. RGB-D Frame", lambda m, d: f"frm: {str(m.get('pose_frame_id') or 'NONE')}\ncam: {m.get('pose_camera_id') or 'overhead'}\ndt_sync: {m.get('max_rgb_depth_sim_time_delta_s')}s"),
        ("2. Pose Estimate", lambda m, d: f"id: {str(m.get('pose_estimate_id') or 'NONE')}\nest: {[round(v, 3) for v in m['grasp_rgbd_est_pos_m']] if m.get('grasp_rgbd_est_pos_m') else 'MISSING'}\ndX_est: {d.get('delta_x_rgbd_estimate_m')}"),
        ("3. Grasp Target", lambda m, d: f"id: {str(m.get('grasp_target_id') or 'NONE')}\nreach: {m.get('grasp_reachability_status') or 'BLOCKED'}\ndX_tgt: {d.get('delta_x_grasp_target_m')}"),
        ("4. Trajectory", lambda m, d: f"id: {str(m.get('grasp_trajectory_id') or 'NONE')}\nstates: {m.get('robot_state_sample_count')}\ndX_ee: {d.get('delta_x_actual_end_effector_m')}"),
        ("5. Contact Verif", lambda m, d: (
            f"status: {m.get('mission_status')}\n"
            f"bilat: {m.get('mean_bilateral_contact_fraction')}\n"
            f"slip: {str(m['max_relative_slip_m']) + 'm' if m.get('max_relative_slip_m') is not None else 'NONE'}"
        )),
    ]
    start_y = 120
    row_h = 142
    box_w = 215
    gap_x = 42
    for row_idx, m in enumerate(metrics_list):
        name = m["condition"]
        d = delta_by_name.get(name, {})
        col = _color_for(name, row_idx)
        y = start_y + row_idx * row_h
        draw.text((34, y - 4), f"{name} (GT dX={d.get('delta_x_ground_truth_m')}, compliant={m.get('data_source_compliant')})", fill=col, font_size=14)
        for st_idx, (st_title, fn) in enumerate(stages):
            x = 34 + st_idx * (box_w + gap_x)
            by = y + 20
            bh = 94
            draw.rectangle([x, by, x + box_w, by + bh], fill=(16, 24, 39), outline=col, width=2)
            draw.text((x + 10, by + 8), st_title, fill=col, font_size=13)
            draw.text((x + 10, by + 30), fn(m, d), fill=(226, 232, 240), font_size=11)
            if st_idx < len(stages) - 1:
                ax0 = x + box_w + 4
                ax1 = x + box_w + gap_x - 4
                ay = by + bh / 2
                draw.line([(ax0, ay), (ax1, ay)], fill=col, width=2)
                draw.polygon([(ax1, ay), (ax1 - 8, ay - 5), (ax1 - 8, ay + 5)], fill=col)
    img.save(out_path)


def analyze_zip_bundles(
    zip_paths: list[str | Path],
    *,
    output_dir: str | Path,
    baseline_name: str = "baseline",
    x_delta_tolerance_m: float = 0.025,
) -> dict[str, Any]:
    """Compare exported ZIP bundles, compute all 12 metrics & X-deltas, draw 6 plots, write report."""
    out_root = Path(output_dir).resolve()
    plots_dir = out_root / "plots"
    plots_dir.mkdir(parents=True, exist_ok=True)

    loaded: list[tuple[str, dict[str, Any]]] = []
    metrics_list: list[dict[str, Any]] = []
    for idx, zp in enumerate(zip_paths):
        b = load_zip_bundle(zp)
        pert = b["config"].get("perturbation") or {}
        name = str(pert.get("condition") or b["config"].get("run_id") or f"run_{idx}")
        loaded.append((name, b))
        metrics_list.append(extract_bundle_metrics(b, label=name))

    base = next((m for m in metrics_list if m["condition"] == baseline_name), metrics_list[0] if metrics_list else None)
    base_gt = base.get("initial_gt_pos_m") if base else None
    base_est = base.get("grasp_rgbd_est_pos_m") if base else None
    base_tgt = base.get("grasp_target_ee_xyz_m") if base else None
    base_ee = base.get("actual_ee_close_xyz_m") if base else None

    deltas: list[dict[str, Any]] = []
    for m in metrics_list:
        gt = m.get("initial_gt_pos_m")
        est = m.get("grasp_rgbd_est_pos_m")
        tgt = m.get("grasp_target_ee_xyz_m")
        ee = m.get("actual_ee_close_xyz_m")
        dx_gt = round(gt[0] - base_gt[0], 6) if (gt and base_gt) else None
        dx_est = round(est[0] - base_est[0], 6) if (est and base_est) else None
        dx_tgt = round(tgt[0] - base_tgt[0], 6) if (tgt and base_tgt) else None
        dx_ee = round(ee[0] - base_ee[0], 6) if (ee and base_ee) else None

        tracking_ok: bool | None = None
        if m.get("vision_fault_mode"):
            tracking_ok = bool(dx_est is None and dx_tgt is None and dx_ee is None and m.get("negative_control_clean"))
        elif dx_gt is not None and dx_est is not None and dx_tgt is not None and dx_ee is not None:
            tracking_ok = bool(
                abs(dx_est - dx_gt) <= x_delta_tolerance_m
                and abs(dx_tgt - dx_est) <= x_delta_tolerance_m
                and abs(dx_ee - dx_tgt) <= x_delta_tolerance_m
            )
        deltas.append({
            "condition": m["condition"],
            "delta_x_ground_truth_m": dx_gt,
            "delta_x_rgbd_estimate_m": dx_est,
            "delta_x_grasp_target_m": dx_tgt,
            "delta_x_actual_end_effector_m": dx_ee,
            "tracking_within_tolerance": tracking_ok,
            "tolerance_m": x_delta_tolerance_m,
        })

    plot_files = {
        "localization_3d": plots_dir / "01_3d_localization_comparison.png",
        "grasp_target": plots_dir / "02_grasp_target_comparison.png",
        "ee_trajectory": plots_dir / "03_end_effector_trajectory_comparison.png",
        "contact_forces": plots_dir / "04_contact_forces_timeseries.png",
        "relative_slip": plots_dir / "05_relative_slip_timeseries.png",
        "causal_diagram": plots_dir / "06_causal_chain_diagram.png",
    }
    _plot_3d_localization(metrics_list, plot_files["localization_3d"])
    _plot_grasp_target_comparison(deltas, plot_files["grasp_target"])
    _plot_ee_trajectories(loaded, plot_files["ee_trajectory"])
    _plot_contact_timeseries(loaded, mode="forces", out_path=plot_files["contact_forces"])
    _plot_contact_timeseries(loaded, mode="slip", out_path=plot_files["relative_slip"])
    _plot_causal_diagram(metrics_list, deltas, plot_files["causal_diagram"])

    report_md = _format_analysis_report(metrics_list, deltas, plot_files)
    (out_root / "causal_analysis_report.md").write_text(report_md, encoding="utf-8")

    summary = {
        "metrics": metrics_list,
        "x_deltas": deltas,
        "plots": {k: str(v) for k, v in plot_files.items()},
        "report_path": str(out_root / "causal_analysis_report.md"),
    }
    (out_root / "causal_analysis_metrics.json").write_text(
        json.dumps(summary, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    return summary


def _format_analysis_report(
    metrics_list: list[dict[str, Any]],
    deltas: list[dict[str, Any]],
    plot_files: dict[str, Path],
) -> str:
    lines = [
        "# CubeRelay M4-C 自动化因果分析报告",
        "",
        "## 一、X 轴位置扰动因果传导对比",
        "",
        "| Condition | Delta X GT (m) | Delta X RGB-D Est (m) | Delta X Grasp Target (m) | Delta X Actual EE (m) | 因果跟踪符合容差 |",
        "| --- | ---: | ---: | ---: | ---: | :---: |",
    ]
    for d in deltas:
        lines.append(
            f"| `{d['condition']}` | {d['delta_x_ground_truth_m']} | {d['delta_x_rgbd_estimate_m']} | "
            f"{d['delta_x_grasp_target_m']} | {d['delta_x_actual_end_effector_m']} | {d['tracking_within_tolerance']} |"
        )
    lines.extend([
        "",
        "## 二、全量 12 项指标对比",
        "",
        "| Condition | Status | RGB-D Err 3D (m) | EE Target/Actual Err XY (m) | Max Slip (m) | Mean Bilat Contact | Pose Age (s) | Compliant | Wall (s) | Sim (s) |",
        "| --- | --- | ---: | ---: | ---: | ---: | ---: | :---: | ---: | ---: |",
    ])
    for m in metrics_list:
        lines.append(
            f"| `{m['condition']}` | `{m['mission_status']}` ({m['failure_reason'] or 'OK'}) | "
            f"{m['visual_localization_error_3d_m']} | {m['ee_target_vs_actual_xy_error_m']} | "
            f"{m['max_relative_slip_m']} | {m['mean_bilateral_contact_fraction']} | "
            f"{m['pose_age_sim_s']} | {m['data_source_compliant']} | "
            f"{m['total_execution_wall_s']} | {m['sim_time_s']} |"
        )
    lines.extend(["", "## 三、生成图表清单", ""])
    for k, p in plot_files.items():
        lines.append(f"- `{k}`: `{p}`")
    return "\n".join(lines) + "\n"
