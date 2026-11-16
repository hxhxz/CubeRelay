"""End-to-end M3-D Mission acceptance runner on real MuJoCo backend (seed=0)."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

from cube_relay.mission import MissionStatus, MissionType, SimulationSession

ROOT = Path(__file__).resolve().parents[1]
OUT_DIR = ROOT / "results" / "m3d_acceptance"


def _compact_snapshot_for_report(snapshot: dict[str, Any]) -> dict[str, Any]:
    """Strip multi-KB base64 images into metadata while preserving all mission/agent/event fields."""
    compacted = dict(snapshot)
    for key in ("main_frame_url", "wrist_rgb_url", "wrist_depth_url"):
        val = compacted.get(key)
        if isinstance(val, str):
            compacted[f"{key}_prefix"] = val[:40]
            compacted[f"{key}_len"] = len(val)
            compacted[key] = f"<data_url len={len(val)}>"
    return compacted


def run_acceptance(seed: int = 0) -> dict[str, Any]:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    session = SimulationSession(seed=seed, width=480, height=320, use_dedicated_thread=False)

    reports: dict[str, Any] = {}
    try:
        # 1) INSPECT_CUBE
        snap_inspect = session.run_mission(MissionType.INSPECT_CUBE, seed=seed)
        assert snap_inspect["mission"]["status"] == MissionStatus.COMPLETED.value
        inspect_skills = [ex["skill_id"] for ex in snap_inspect["skill_executions"]]
        assert "execute_physical_u_turn" not in inspect_skills, f"INSPECT_CUBE unexpectedly ran U turn: {inspect_skills}"
        assert snap_inspect["frame_source"] == "REAL_MUJOCO_RENDERER"
        assert snap_inspect["agent_state"]["llm_connected"] is False
        assert snap_inspect["agent_state"]["planner_mode"] == "DETERMINISTIC_PLANNER"

        (OUT_DIR / "inspect_cube_snapshot.json").write_text(
            json.dumps(_compact_snapshot_for_report(snap_inspect), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        reports["INSPECT_CUBE"] = {
            "status": snap_inspect["mission"]["status"],
            "sim_time": snap_inspect["sim_time"],
            "skills_executed": inspect_skills,
            "plan_steps": [s["skill_id"] for s in snap_inspect["plan"]["steps"]],
            "observed_count": snap_inspect["last_observation_ref"]["observed_count"],
            "unknown_count": snap_inspect["last_observation_ref"]["unknown_count"],
            "decision_event_count": len(snap_inspect["decision_events"]),
            "result_summary": snap_inspect["mission"]["result_summary"],
        }

        # 2) VERIFY_PHYSICAL_U_TURN
        snap_u = session.run_mission(MissionType.VERIFY_PHYSICAL_U_TURN, seed=seed)
        assert snap_u["mission"]["status"] == MissionStatus.COMPLETED.value
        pv = snap_u["physical_verification"] or {}
        assert pv.get("affected_21_verified") is True, f"Expected 21/21 verification, got: {pv}"
        assert pv.get("no_recolor") is True
        assert pv.get("logical_state_unchanged") is True
        assert pv.get("same_model_and_data") is True
        assert pv.get("active_equalities") == []
        assert float(pv.get("actual_angle_deg", 0.0)) > 85.0
        assert float(pv.get("min_base_contact_n", 0.0)) > 0.5
        assert float(pv.get("min_turn_contact_n", 0.0)) > 0.5

        (OUT_DIR / "verify_physical_u_turn_snapshot.json").write_text(
            json.dumps(_compact_snapshot_for_report(snap_u), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        reports["VERIFY_PHYSICAL_U_TURN"] = {
            "status": snap_u["mission"]["status"],
            "sim_time": snap_u["sim_time"],
            "skills_executed": [ex["skill_id"] for ex in snap_u["skill_executions"]],
            "plan_steps": [s["skill_id"] for s in snap_u["plan"]["steps"]],
            "physical_verification": pv,
            "decision_event_count": len(snap_u["decision_events"]),
            "result_summary": snap_u["mission"]["result_summary"],
        }

        # 3) SOLVE_CUBE
        snap_solve = session.run_mission(MissionType.SOLVE_CUBE, seed=seed)
        assert snap_solve["mission"]["status"] == MissionStatus.BLOCKED_CAPABILITY.value, (
            f"Expected BLOCKED_CAPABILITY, got {snap_solve['mission']['status']}"
        )
        event_types = [ev["event_type"] for ev in snap_solve["decision_events"]]
        assert "CAPABILITY_BLOCKED" in event_types, f"Missing CAPABILITY_BLOCKED in {event_types}"
        solve_skills = [ex["skill_id"] for ex in snap_solve["skill_executions"]]
        assert "compute_symbolic_plan" in solve_skills
        assert "execute_physical_u_turn" not in solve_skills, (
            f"SOLVE_CUBE should not execute U turn when solution starts with unsupported move/audit block: {solve_skills}"
        )

        (OUT_DIR / "solve_cube_snapshot.json").write_text(
            json.dumps(_compact_snapshot_for_report(snap_solve), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        reports["SOLVE_CUBE"] = {
            "status": snap_solve["mission"]["status"],
            "sim_time": snap_solve["sim_time"],
            "skills_executed": solve_skills,
            "plan_steps": [
                {"skill_id": s["skill_id"], "status": s["status"], "title": s["title"]}
                for s in snap_solve["plan"]["steps"]
            ],
            "blocked_reason": snap_solve["mission"]["blocked_reason"],
            "decision_event_count": len(snap_solve["decision_events"]),
            "capability_blocked_events": [
                ev for ev in snap_solve["decision_events"] if ev["event_type"] == "CAPABILITY_BLOCKED"
            ],
            "result_summary": snap_solve["mission"]["result_summary"],
        }

        summary = {
            "ok": True,
            "seed": seed,
            "capabilities": snap_solve["capabilities"],
            "missions": reports,
        }
        (OUT_DIR / "summary.json").write_text(
            json.dumps(summary, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        return summary
    finally:
        session.close()


def main() -> int:
    summary = run_acceptance(seed=0)
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
