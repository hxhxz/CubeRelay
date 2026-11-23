"""Controlled position perturbation experiment runner for CubeRelay M4-C."""

from __future__ import annotations

from dataclasses import asdict, dataclass
import json
from pathlib import Path
from typing import Any

from .schema import utc_now_iso


@dataclass(frozen=True, slots=True)
class PerturbationCondition:
    """One controlled physical / visual experiment condition."""

    name: str
    dx_m: float = 0.0
    dy_m: float = 0.0
    dyaw_rad: float = 0.0
    vision_fault_mode: str | None = None
    description: str = ""

    def to_perturbation_dict(self) -> dict[str, Any]:
        return {
            "condition": self.name,
            "dx_m": float(self.dx_m),
            "dy_m": float(self.dy_m),
            "dyaw_rad": float(self.dyaw_rad),
            "vision_fault_mode": self.vision_fault_mode,
        }


PERTURBATION_CONDITIONS: dict[str, PerturbationCondition] = {
    "baseline": PerturbationCondition(
        name="baseline",
        dx_m=0.0,
        dy_m=0.0,
        dyaw_rad=0.0,
        vision_fault_mode=None,
        description="Baseline: original initial cube pose at requested seed",
    ),
    "translate_x_005": PerturbationCondition(
        name="translate_x_005",
        dx_m=0.05,
        dy_m=0.0,
        dyaw_rad=0.0,
        vision_fault_mode=None,
        description="Perturbation A: initial cube translated +0.05 m (+5 cm) along world X",
    ),
    "translate_x_010": PerturbationCondition(
        name="translate_x_010",
        dx_m=0.10,
        dy_m=0.0,
        dyaw_rad=0.0,
        vision_fault_mode=None,
        description="Perturbation B: initial cube translated +0.10 m (+10 cm) along world X",
    ),
    "vision_missing_negative_control": PerturbationCondition(
        name="vision_missing_negative_control",
        dx_m=0.05,
        dy_m=0.0,
        dyaw_rad=0.0,
        vision_fault_mode="blackout",
        description="Negative control: cube shifted +0.05 m while RGB-D stream is unavailable",
    ),
}


def run_perturbation_condition(
    condition: PerturbationCondition | str,
    *,
    seed: int = 0,
    mission_type: str = "INSPECT_CUBE",
    output_dir: str | Path,
    include_audit_ground_truth: bool = True,
    include_rgbd: bool = True,
    include_high_freq_trajectory: bool = True,
    trajectory_sample_hz: float = 50.0,
    width: int = 480,
    height: int = 320,
    scope: str = "full_mission",
) -> dict[str, Any]:
    """Run one condition inside an isolated SimulationSession and export its ZIP bundle."""
    from cube_relay.mission.session import SimulationSession

    cond = (
        PERTURBATION_CONDITIONS[condition]
        if isinstance(condition, str)
        else condition
    )
    out_root = Path(output_dir).resolve()
    runs_dir = out_root / "runs"
    bundles_dir = out_root / "bundles"
    runs_dir.mkdir(parents=True, exist_ok=True)
    bundles_dir.mkdir(parents=True, exist_ok=True)

    session = SimulationSession(
        seed=seed,
        width=width,
        height=height,
        use_dedicated_thread=False,
        experiments_dir=runs_dir,
        trajectory_sample_hz=trajectory_sample_hz,
        include_audit_ground_truth=include_audit_ground_truth,
    )
    try:
        snapshot = session.run_mission(
            mission_type,
            seed=seed,
            perturbation=cond.to_perturbation_dict(),
        )
        run_id = str(snapshot.get("run_id") or "")
        zip_path = bundles_dir / f"{cond.name}_{run_id}.zip"
        _, manifest = session.exporter.export_zip_bytes(
            run_id=run_id or None,
            session_snapshot=snapshot,
            scope=scope,
            include_rgbd=include_rgbd,
            include_high_freq_trajectory=include_high_freq_trajectory,
            include_audit_ground_truth=include_audit_ground_truth,
            out_path=zip_path,
        )
        mission = snapshot.get("mission") or {}
        return {
            "condition": cond.name,
            "description": cond.description,
            "perturbation": asdict(cond),
            "seed": int(seed),
            "mission_type": mission_type,
            "run_id": run_id,
            "session_id": snapshot.get("session_id"),
            "mission_status": mission.get("status"),
            "failure_reason": mission.get("failure_reason"),
            "result_summary": mission.get("result_summary"),
            "zip_path": str(zip_path),
            "zip_bytes": zip_path.stat().st_size,
            "counts": (snapshot.get("experiment_recording") or {}).get("counts", {}),
            "reference_integrity_ok": bool(
                (manifest.get("reference_integrity") or {}).get("ok", False)
            ),
        }
    finally:
        session.close()


def run_perturbation_suite(
    conditions: list[str] | tuple[str, ...] | None = None,
    *,
    seed: int = 0,
    mission_type: str = "INSPECT_CUBE",
    output_dir: str | Path,
    include_audit_ground_truth: bool = True,
    include_rgbd: bool = True,
    include_high_freq_trajectory: bool = True,
    trajectory_sample_hz: float = 50.0,
    width: int = 480,
    height: int = 320,
    scope: str = "full_mission",
) -> dict[str, Any]:
    """Run multiple controlled perturbation conditions sequentially in fresh sessions."""
    names = list(conditions or PERTURBATION_CONDITIONS.keys())
    unknown = [name for name in names if name not in PERTURBATION_CONDITIONS]
    if unknown:
        raise ValueError(
            f"Unknown condition(s): {unknown}; expected subset of {list(PERTURBATION_CONDITIONS)}"
        )

    out_root = Path(output_dir).resolve()
    out_root.mkdir(parents=True, exist_ok=True)
    results = [
        run_perturbation_condition(
            name,
            seed=seed,
            mission_type=mission_type,
            output_dir=out_root,
            include_audit_ground_truth=include_audit_ground_truth,
            include_rgbd=include_rgbd,
            include_high_freq_trajectory=include_high_freq_trajectory,
            trajectory_sample_hz=trajectory_sample_hz,
            width=width,
            height=height,
            scope=scope,
        )
        for name in names
    ]
    index = {
        "schema_version": "m4c.v1",
        "generated_utc": utc_now_iso(),
        "seed": int(seed),
        "mission_type": mission_type,
        "trajectory_sample_hz": float(trajectory_sample_hz),
        "include_audit_ground_truth": bool(include_audit_ground_truth),
        "conditions": names,
        "results": results,
    }
    (out_root / "experiment_index.json").write_text(
        json.dumps(index, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    return index
