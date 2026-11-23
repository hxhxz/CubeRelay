"""Import REAL_REPLAY contexts from M4-C historical experiment ZIP bundles.

Enforces strict causal temporal cutoff (t <= cutoff_sim_time) and excludes
SIMULATOR_GROUND_TRUTH_AUDIT_ONLY (audit_only_poses.csv) from agent inputs.
"""

from __future__ import annotations

import base64
import io
import json
from pathlib import Path
from typing import Any
import zipfile

from PIL import Image


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


def _encode_png_bytes_as_jpeg_data_url(raw_png: bytes, *, quality: int = 84) -> str:
    img = Image.open(io.BytesIO(raw_png)).convert("RGB")
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=quality)
    b64 = base64.b64encode(buf.getvalue()).decode("ascii")
    return f"data:image/jpeg;base64,{b64}"


def extract_m4c_replay_slice(
    zip_path: str | Path,
    *,
    cutoff_sim_time: float,
    preferred_camera_id: str = "overhead",
) -> dict[str, Any]:
    """Slice an M4-C experiment bundle up to cutoff_sim_time without future or audit leakage."""
    zp = Path(zip_path).resolve()
    if not zp.exists():
        raise FileNotFoundError(f"M4-C bundle not found: {zp}")

    with zipfile.ZipFile(zp, mode="r") as zf:
        config = _read_zip_json(zf, "config.json", {})
        frames = _read_zip_jsonl(zf, "frames.jsonl")
        observations = _read_zip_jsonl(zf, "observations.jsonl")
        poses = _read_zip_jsonl(zf, "pose_estimates.jsonl")
        verifications = _read_zip_jsonl(zf, "contact_verifications.jsonl")
        skill_execs = _read_zip_json(zf, "skill_executions.json", [])

        eps = 1e-6
        past_frames = [
            f for f in frames
            if f.get("sim_time") is not None and float(f["sim_time"]) <= cutoff_sim_time + eps
        ]
        past_obs = [
            o for o in observations
            if o.get("sim_time") is not None and float(o["sim_time"]) <= cutoff_sim_time + eps
        ]
        past_poses = [
            p for p in poses
            if p.get("sim_time") is not None and float(p["sim_time"]) <= cutoff_sim_time + eps
        ]
        past_verifs = [
            v for v in verifications
            if v.get("sim_time") is not None and float(v["sim_time"]) <= cutoff_sim_time + eps
        ]
        past_execs = [
            ex for ex in skill_execs
            if ex.get("ended_sim_time") is not None and float(ex["ended_sim_time"]) <= cutoff_sim_time + eps
        ]

        # Select latest frame at or before cutoff matching preferred_camera_id (fallback any latest)
        cam_frames = [f for f in past_frames if f.get("camera_id") == preferred_camera_id]
        selected_frame = cam_frames[-1] if cam_frames else (past_frames[-1] if past_frames else None)
        rgb_data_url: str | None = None
        if selected_frame and selected_frame.get("rgb_path"):
            rel = str(selected_frame["rgb_path"])
            if rel in zf.namelist():
                rgb_data_url = _encode_png_bytes_as_jpeg_data_url(zf.read(rel))

    # Explicitly exclude audit_only_poses.csv and strip any audit keys
    sanitized_history = [
        {
            "observation_id": o.get("observation_id"),
            "frame_id": o.get("frame_id"),
            "camera_ids": o.get("camera_ids", []),
            "sim_time": o.get("sim_time"),
            "coverage": o.get("coverage"),
            "unknown_after": o.get("unknown_after"),
            "conflicts": o.get("conflicts", 0),
            "visual_summary": o.get("visual_summary", ""),
        }
        for o in past_obs
    ]

    latest_pose = past_poses[-1] if past_poses else None
    latest_verif = past_verifs[-1] if past_verifs else None
    latest_exec = past_execs[-1] if past_execs else None

    return {
        "source_bundle_zip": str(zp),
        "run_id": config.get("run_id"),
        "session_id": config.get("session_id"),
        "seed": config.get("seed", 0),
        "perturbation": dict(config.get("perturbation") or {}),
        "cutoff_sim_time": float(cutoff_sim_time),
        "selected_frame": selected_frame,
        "rgb_image_data_url": rgb_data_url,
        "observation_history": sanitized_history,
        "latest_pose_estimate": latest_pose,
        "latest_contact_verification": latest_verif,
        "latest_skill_execution": latest_exec,
        "counts": {
            "frames": len(past_frames),
            "observations": len(past_obs),
            "pose_estimates": len(past_poses),
            "contact_verifications": len(past_verifs),
            "skill_executions": len(past_execs),
        },
    }


def discover_m4c_bundles(bundles_dir: str | Path) -> dict[str, Path]:
    """Return mapping from condition prefix to M4-C ZIP bundle path if present."""
    root = Path(bundles_dir)
    if not root.exists():
        return {}
    mapping: dict[str, Path] = {}
    for zp in sorted(root.glob("*.zip")):
        name = zp.name
        if name.startswith("baseline_"):
            mapping["baseline"] = zp
        elif name.startswith("translate_x_005_"):
            mapping["translate_x_005"] = zp
        elif name.startswith("translate_x_010_"):
            mapping["translate_x_010"] = zp
        elif name.startswith("vision_missing_negative_control_"):
            mapping["vision_missing_negative_control"] = zp
    return mapping
