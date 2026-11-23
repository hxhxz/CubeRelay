"""Controlled ZIP artifact exporter for CubeRelay M4-C experiment packages."""

from __future__ import annotations

import hashlib
import io
import json
import zipfile
from pathlib import Path
from typing import Any

from .recorder import (
    DEFAULT_EXPERIMENTS_DIR,
    ExperimentRecorder,
    ExperimentRun,
    _current_git_commit,
    redact_secrets,
    validate_run_id,
)
from .schema import SCHEMA_VERSION, DataSourceKind, utc_now_iso

ALLOWED_SCOPES = {"full_mission", "grasp_causal_chain", "events_only"}


def _source_kind_for_archive_path(rel_path: str) -> str:
    if rel_path.endswith("_rgb.png"):
        return DataSourceKind.SENSOR_RGB.value
    if rel_path.endswith("_depth.npy"):
        return DataSourceKind.SENSOR_DEPTH.value
    if rel_path == "camera_calibration.json":
        return DataSourceKind.CALIBRATION.value
    if rel_path == "pose_estimates.jsonl":
        return DataSourceKind.VISUAL_POSE_ESTIMATE.value
    if rel_path in {"robot_states.csv", "contact_samples.csv", "contact_verifications.jsonl"}:
        return DataSourceKind.ROBOT_PROPRIOCEPTION.value
    if rel_path in {"trajectory_commands.csv", "grasp_targets.jsonl"}:
        return DataSourceKind.CONTROLLER_STATE.value
    if rel_path == "audit_only_poses.csv":
        return DataSourceKind.SIMULATOR_GROUND_TRUTH_AUDIT_ONLY.value
    if rel_path == "config.json":
        return DataSourceKind.FIXED_CONFIG.value
    return DataSourceKind.CONTROLLER_STATE.value


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    rows: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line:
            rows.append(json.loads(line))
    return rows


def _filter_grasp_causal_frames(
    frames: list[dict[str, Any]],
    poses: list[dict[str, Any]],
) -> set[str]:
    return {str(p["frame_id"]) for p in poses if p.get("frame_id")}


def verify_reference_integrity(
    *,
    frames: list[dict[str, Any]],
    poses: list[dict[str, Any]],
    grasp_targets: list[dict[str, Any]],
    contact_verifications: list[dict[str, Any]],
    robot_states_traj_ids: set[str],
    observations: list[dict[str, Any]],
    decision_events: list[dict[str, Any]],
    skill_executions: list[dict[str, Any]],
) -> dict[str, Any]:
    """Audit all causal foreign-key references across the bundle."""
    frame_ids = {str(f["frame_id"]) for f in frames if f.get("frame_id")}
    obs_ids = {str(o["observation_id"]) for o in observations if o.get("observation_id")}
    pose_ids = {str(p["pose_estimate_id"]) for p in poses if p.get("pose_estimate_id")}
    grasp_ids = {str(g["grasp_target_id"]) for g in grasp_targets if g.get("grasp_target_id")}
    exec_ids = {str(e["execution_id"]) for e in skill_executions if e.get("execution_id")}

    broken: list[dict[str, str]] = []
    for p in poses:
        fid = p.get("frame_id")
        if fid and frame_ids and str(fid) not in frame_ids:
            broken.append({"table": "pose_estimates", "id": str(p.get("pose_estimate_id")), "missing_ref": f"frame:{fid}"})
    for g in grasp_targets:
        pid = g.get("pose_estimate_id")
        if pid and pid != "MISSING_POSE_ESTIMATE" and str(pid) not in pose_ids:
            broken.append({"table": "grasp_targets", "id": str(g.get("grasp_target_id")), "missing_ref": f"pose:{pid}"})
    for cv in contact_verifications:
        gid = cv.get("grasp_target_id")
        tid = cv.get("trajectory_id")
        eid = cv.get("skill_execution_id")
        if gid and str(gid) not in grasp_ids:
            broken.append({"table": "contact_verifications", "id": str(cv.get("contact_verification_id")), "missing_ref": f"grasp:{gid}"})
        if tid and robot_states_traj_ids and str(tid) not in robot_states_traj_ids:
            broken.append({"table": "contact_verifications", "id": str(cv.get("contact_verification_id")), "missing_ref": f"trajectory:{tid}"})
        if eid and exec_ids and str(eid) not in exec_ids:
            broken.append({"table": "contact_verifications", "id": str(cv.get("contact_verification_id")), "missing_ref": f"exec:{eid}"})
    for ev in decision_events:
        fb = ev.get("feedback_observation_id")
        if fb and obs_ids and str(fb) not in obs_ids:
            broken.append({"table": "decision_events", "id": str(ev.get("event_id")), "missing_ref": f"feedback_obs:{fb}"})

    return {
        "ok": len(broken) == 0,
        "broken_references": broken,
        "counts": {
            "frames": len(frame_ids),
            "observations": len(obs_ids),
            "pose_estimates": len(pose_ids),
            "grasp_targets": len(grasp_ids),
            "contact_verifications": len(contact_verifications),
            "trajectories": len(robot_states_traj_ids),
            "skill_executions": len(exec_ids),
        },
    }


class ArtifactExporter:
    """Builds verifiable, self-contained ZIP archives from recorded runs or snapshots."""

    def __init__(
        self,
        recorder: ExperimentRecorder | None = None,
        *,
        base_dir: str | Path | None = None,
        max_export_bytes: int = 512 * 1024 * 1024,
    ) -> None:
        self.recorder = recorder
        self.base_dir = Path(base_dir or (recorder.base_dir if recorder else DEFAULT_EXPERIMENTS_DIR)).resolve()
        self.max_export_bytes = int(max_export_bytes)

    def _resolve_run_dir(self, run_id: str) -> Path:
        validate_run_id(run_id)
        if self.recorder is not None:
            run = self.recorder.get_run(run_id)
            if run is not None:
                run.flush()
                return run.run_dir
            return self.recorder.resolve_run_dir(run_id)
        target = (self.base_dir / run_id).resolve()
        if self.base_dir not in target.parents or not target.exists():
            raise FileNotFoundError(f"Experiment run {run_id!r} not found")
        return target

    def export_manifest_info(self, *, session_snapshot: dict[str, Any] | None = None, run_id: str | None = None) -> dict[str, Any]:
        """Return export readiness and available dataset inventory without side effects."""
        if session_snapshot and session_snapshot.get("frame_source") == "SYNTHETIC_SAMPLE":
            return {
                "exportable": False,
                "reason": "SAMPLE_MODE_FORBIDDEN",
                "run_id": None,
                "recording_status": "SAMPLE_BLOCKED",
                "available_datasets": {},
                "historical_runs": self.list_runs(),
            }
        target_run_id = run_id or (session_snapshot.get("run_id") if session_snapshot else None)
        run_dir: Path | None = None
        summary: dict[str, Any] = {}
        if target_run_id:
            try:
                run_dir = self._resolve_run_dir(str(target_run_id))
                sf = run_dir / "run_summary.json"
                if sf.exists():
                    summary = json.loads(sf.read_text(encoding="utf-8"))
            except FileNotFoundError:
                run_dir = None

        available = {
            "session_snapshot": bool(session_snapshot or (run_dir and (run_dir / "session_snapshot.json").exists())),
            "decision_events": bool(run_dir and (run_dir / "decision_events.jsonl").exists()) or bool(session_snapshot and session_snapshot.get("decision_events")),
            "trace_events": bool(run_dir and (run_dir / "trace_events.jsonl").exists()) or bool(session_snapshot and session_snapshot.get("trace_events")),
            "rgbd_frames": bool(run_dir and (run_dir / "frames.jsonl").exists()),
            "pose_estimates": bool(run_dir and (run_dir / "pose_estimates.jsonl").exists()),
            "grasp_targets": bool(run_dir and (run_dir / "grasp_targets.jsonl").exists()),
            "trajectory": bool(run_dir and (run_dir / "robot_states.csv").exists()),
            "contact_samples": bool(run_dir and (run_dir / "contact_samples.csv").exists()),
            "contact_verifications": bool(run_dir and (run_dir / "contact_verifications.jsonl").exists()),
            "audit_only_poses": bool(run_dir and (run_dir / "audit_only_poses.csv").exists()),
        }
        return {
            "exportable": bool(available["session_snapshot"] or run_dir),
            "run_id": target_run_id,
            "session_id": summary.get("session_id") or (session_snapshot.get("session_id") if session_snapshot else None),
            "recording_status": summary.get("recording_status") or (
                session_snapshot.get("experiment_recording", {}).get("status") if session_snapshot else "IDLE"
            ),
            "counts": summary.get("counts") or {},
            "available_datasets": available,
            "scopes": sorted(ALLOWED_SCOPES),
            "historical_runs": self.list_runs(),
        }

    def list_runs(self) -> list[dict[str, Any]]:
        if self.recorder is not None:
            return self.recorder.list_runs()
        if not self.base_dir.exists():
            return []
        runs: list[dict[str, Any]] = []
        for child in sorted(self.base_dir.iterdir(), key=lambda p: p.stat().st_mtime, reverse=True):
            if not child.is_dir():
                continue
            sf = child / "run_summary.json"
            if sf.exists():
                try:
                    runs.append(json.loads(sf.read_text(encoding="utf-8")))
                    continue
                except Exception:
                    pass
            runs.append({"run_id": child.name, "recording_status": "DISK_ONLY", "run_dir": str(child)})
        return runs

    def export_zip_bytes(
        self,
        *,
        run_id: str | None = None,
        session_snapshot: dict[str, Any] | None = None,
        scope: str = "full_mission",
        include_rgbd: bool = True,
        include_high_freq_trajectory: bool = True,
        include_audit_ground_truth: bool = False,
        out_path: str | Path | None = None,
    ) -> tuple[bytes, dict[str, Any]]:
        if scope not in ALLOWED_SCOPES:
            raise ValueError(f"Unsupported export scope {scope!r}; expected one of {sorted(ALLOWED_SCOPES)}")

        if session_snapshot is not None:
            fs = str(session_snapshot.get("frame_source") or "")
            sid = str(session_snapshot.get("session_id") or "")
            if fs == "SYNTHETIC_SAMPLE" or sid.startswith("SYNTHETIC-SAMPLE"):
                raise PermissionError("SAMPLE_MODE_FORBIDDEN: SYNTHETIC_SAMPLE cannot be exported as physical experiment data")

        target_run_id = run_id or (str(session_snapshot.get("run_id")) if session_snapshot and session_snapshot.get("run_id") else None)
        run_dir: Path | None = None
        if target_run_id:
            validate_run_id(target_run_id)
            try:
                run_dir = self._resolve_run_dir(target_run_id)
            except FileNotFoundError:
                if session_snapshot is None:
                    raise
                run_dir = None

        if run_dir is None and session_snapshot is None:
            raise FileNotFoundError("Neither a valid run_id on disk nor a session_snapshot was provided")

        if self.recorder is not None and target_run_id:
            active = self.recorder.get_run(target_run_id)
            if active is not None:
                active.flush()

        # Load snapshot
        snapshot: dict[str, Any] = {}
        if run_dir and (run_dir / "session_snapshot.json").exists():
            snapshot = json.loads((run_dir / "session_snapshot.json").read_text(encoding="utf-8"))
        if session_snapshot is not None:
            snapshot = dict(session_snapshot)
        snapshot = redact_secrets(snapshot)
        if str(snapshot.get("frame_source") or "") == "SYNTHETIC_SAMPLE" or str(snapshot.get("session_id") or "").startswith("SYNTHETIC-SAMPLE"):
            raise PermissionError("SAMPLE_MODE_FORBIDDEN: SYNTHETIC_SAMPLE cannot be exported as physical experiment data")

        # Load config
        config: dict[str, Any] = {}
        if run_dir and (run_dir / "config.json").exists():
            config = json.loads((run_dir / "config.json").read_text(encoding="utf-8"))
        else:
            config = {
                "schema_version": SCHEMA_VERSION,
                "run_id": target_run_id or f"legacy-{snapshot.get('session_id', 'unknown')}",
                "session_id": snapshot.get("session_id", "unknown"),
                "seed": snapshot.get("seed", 0),
                "mission_type": (snapshot.get("mission") or {}).get("mission_type", snapshot.get("selected_mission_type", "UNKNOWN")),
                "planner_mode": (snapshot.get("agent_state") or {}).get("planner_mode", "UNKNOWN"),
                "git_commit": _current_git_commit(),
                "legacy_snapshot_only": True,
                "created_utc": utc_now_iso(),
            }
        config = redact_secrets(config)

        # Load event & causal records
        decision_events = (
            _read_jsonl(run_dir / "decision_events.jsonl")
            if run_dir and (run_dir / "decision_events.jsonl").exists()
            else list(snapshot.get("decision_events") or [])
        )
        trace_events = (
            _read_jsonl(run_dir / "trace_events.jsonl")
            if run_dir and (run_dir / "trace_events.jsonl").exists()
            else list(snapshot.get("trace_events") or [])
        )
        skill_executions = (
            json.loads((run_dir / "skill_executions.json").read_text(encoding="utf-8"))
            if run_dir and (run_dir / "skill_executions.json").exists()
            else list(snapshot.get("skill_executions") or [])
        )
        observations = (
            _read_jsonl(run_dir / "observations.jsonl")
            if run_dir and (run_dir / "observations.jsonl").exists()
            else list(snapshot.get("observations") or [])
        )
        frames = _read_jsonl(run_dir / "frames.jsonl") if run_dir else []
        pose_estimates = _read_jsonl(run_dir / "pose_estimates.jsonl") if run_dir else []
        grasp_targets = _read_jsonl(run_dir / "grasp_targets.jsonl") if run_dir else []
        contact_verifications = _read_jsonl(run_dir / "contact_verifications.jsonl") if run_dir else []
        calibrations: dict[str, Any] = {}
        if run_dir and (run_dir / "camera_calibration.json").exists():
            calibrations = json.loads((run_dir / "camera_calibration.json").read_text(encoding="utf-8"))

        # Scope filtering for grasp_causal_chain
        if scope == "grasp_causal_chain":
            grasp_skill_ids = {"observe_workspace", "place_and_release", "regrasp_cube", "reorient_cube", "observe_cube", "plan_grasp", "approach_grasp", "verify_pose", "establish_grasp", "test_lift"}
            skill_executions = [ex for ex in skill_executions if ex.get("skill_id") in grasp_skill_ids]
            relevant_exec_ids = {str(ex.get("execution_id")) for ex in skill_executions}
            decision_events = [
                ev for ev in decision_events
                if ev.get("skill_id") in grasp_skill_ids or ev.get("skill_execution_id") in relevant_exec_ids
            ]
            causal_frame_ids = _filter_grasp_causal_frames(frames, pose_estimates)
            if causal_frame_ids:
                frames = [f for f in frames if str(f.get("frame_id")) in causal_frame_ids]

        # Track missing datasets honestly (never fabricate!)
        missing_markers: dict[str, str] = {}
        if not frames:
            missing_markers["frames"] = "NO_RGBD_FRAMES_RECORDED"
        if not pose_estimates:
            missing_markers["pose_estimates"] = "NO_POSE_ESTIMATES_RECORDED"
        if not grasp_targets:
            missing_markers["grasp_targets"] = "NO_GRASP_TARGETS_RECORDED"
        if not (run_dir and (run_dir / "robot_states.csv").exists()):
            missing_markers["robot_states"] = "NO_TRAJECTORY_RECORDED"
        if not (run_dir and (run_dir / "trajectory_commands.csv").exists()):
            missing_markers["trajectory_commands"] = "NO_TRAJECTORY_COMMANDS_RECORDED"
        if not (run_dir and (run_dir / "contact_samples.csv").exists()):
            missing_markers["contact_samples"] = "NO_CONTACT_SAMPLES_RECORDED"
        if not contact_verifications:
            missing_markers["contact_verifications"] = "NO_CONTACT_VERIFICATIONS_RECORDED"

        # Parse trajectory_ids present in robot_states.csv for referential integrity audit
        robot_traj_ids: set[str] = set()
        if run_dir and (run_dir / "robot_states.csv").exists():
            import csv as _csv

            with (run_dir / "robot_states.csv").open("r", encoding="utf-8", newline="") as fh:
                reader = _csv.DictReader(fh)
                for row in reader:
                    tid = row.get("trajectory_id")
                    if tid:
                        robot_traj_ids.add(tid)

        ref_integrity = verify_reference_integrity(
            frames=frames,
            poses=pose_estimates,
            grasp_targets=grasp_targets,
            contact_verifications=contact_verifications,
            robot_states_traj_ids=robot_traj_ids,
            observations=observations,
            decision_events=decision_events,
            skill_executions=skill_executions,
        )

        # Build metrics.json
        metrics_payload: dict[str, Any] = {}
        if run_dir and (run_dir / "metrics.json").exists():
            metrics_payload = json.loads((run_dir / "metrics.json").read_text(encoding="utf-8"))
        metrics_payload = redact_secrets({
            **metrics_payload,
            "schema_version": SCHEMA_VERSION,
            "run_id": config.get("run_id"),
            "session_id": config.get("session_id"),
            "seed": config.get("seed"),
            "scope": scope,
            "mission_status": (snapshot.get("mission") or {}).get("status"),
            "timing_metrics": snapshot.get("timing_metrics"),
            "reference_integrity": ref_integrity,
            "missing_data_markers": missing_markers,
            "pose_estimates_count": len(pose_estimates),
            "grasp_targets_count": len(grasp_targets),
            "contact_verifications": [cv for cv in contact_verifications],
        })

        # Build report.md
        report_md = self._build_markdown_report(
            config=config,
            snapshot=snapshot,
            pose_estimates=pose_estimates,
            grasp_targets=grasp_targets,
            contact_verifications=contact_verifications,
            ref_integrity=ref_integrity,
            missing_markers=missing_markers,
        )

        # Assemble entries in memory and verify size cap
        entries: dict[str, bytes] = {}
        entries["config.json"] = json.dumps(config, indent=2, ensure_ascii=False).encode("utf-8")
        entries["session_snapshot.json"] = json.dumps(snapshot, indent=2, ensure_ascii=False).encode("utf-8")
        entries["decision_events.jsonl"] = (
            "".join(json.dumps(redact_secrets(ev), ensure_ascii=False) + "\n" for ev in decision_events).encode("utf-8")
        )
        entries["trace_events.jsonl"] = (
            "".join(json.dumps(redact_secrets(ev), ensure_ascii=False) + "\n" for ev in trace_events).encode("utf-8")
        )
        entries["skill_executions.json"] = json.dumps(redact_secrets(skill_executions), indent=2, ensure_ascii=False).encode("utf-8")
        entries["observations.jsonl"] = (
            "".join(json.dumps(redact_secrets(obs), ensure_ascii=False) + "\n" for obs in observations).encode("utf-8")
        )
        raw_evidence_bundles = list(snapshot.get("evidence_bundles") or [])
        if raw_evidence_bundles:
            entries["evidence_bundles.jsonl"] = (
                "".join(json.dumps(redact_secrets(eb), ensure_ascii=False) + "\n" for eb in raw_evidence_bundles).encode("utf-8")
            )
        entries["metrics.json"] = json.dumps(metrics_payload, indent=2, ensure_ascii=False).encode("utf-8")
        entries["report.md"] = report_md.encode("utf-8")

        if scope != "events_only":
            entries["camera_calibration.json"] = json.dumps(calibrations or {"schema_version": SCHEMA_VERSION, "calibrations": {}, "missing": True}, indent=2, ensure_ascii=False).encode("utf-8")
            entries["pose_estimates.jsonl"] = (
                "".join(json.dumps(redact_secrets(p), ensure_ascii=False) + "\n" for p in pose_estimates).encode("utf-8")
            )
            entries["grasp_targets.jsonl"] = (
                "".join(json.dumps(redact_secrets(g), ensure_ascii=False) + "\n" for g in grasp_targets).encode("utf-8")
            )
            entries["contact_verifications.jsonl"] = (
                "".join(json.dumps(redact_secrets(c), ensure_ascii=False) + "\n" for c in contact_verifications).encode("utf-8")
            )

            if include_rgbd and run_dir is not None:
                entries["frames.jsonl"] = (
                    "".join(json.dumps(redact_secrets(f), ensure_ascii=False) + "\n" for f in frames).encode("utf-8")
                )
                for f in frames:
                    for key in ("rgb_path", "depth_path"):
                        rel = f.get(key)
                        if not rel:
                            continue
                        src = (run_dir / str(rel)).resolve()
                        if run_dir.resolve() not in src.parents:
                            raise ValueError(f"Unsafe frame path: {rel}")
                        if src.exists():
                            entries[str(rel)] = src.read_bytes()

            if include_high_freq_trajectory and run_dir is not None:
                for csv_name in ("trajectory_commands.csv", "robot_states.csv", "contact_samples.csv"):
                    src = run_dir / csv_name
                    if src.exists():
                        entries[csv_name] = src.read_bytes()

            if include_audit_ground_truth and run_dir is not None:
                audit_src = run_dir / "audit_only_poses.csv"
                if audit_src.exists():
                    entries["audit_only_poses.csv"] = audit_src.read_bytes()
                else:
                    missing_markers["audit_only_poses"] = "NO_AUDIT_POSES_RECORDED"

        total_bytes = sum(len(v) for v in entries.values())
        if total_bytes > self.max_export_bytes:
            raise ValueError(f"Export exceeds max allowed size ({total_bytes} > {self.max_export_bytes} bytes)")

        manifest_files = []
        for rel_path in sorted(entries):
            raw = entries[rel_path]
            manifest_files.append({
                "path": rel_path,
                "size_bytes": len(raw),
                "sha256": hashlib.sha256(raw).hexdigest(),
                "source_kind": _source_kind_for_archive_path(rel_path),
            })

        manifest = {
            "schema_version": SCHEMA_VERSION,
            "exporter_version": "1.0.0",
            "run_id": config.get("run_id"),
            "session_id": config.get("session_id"),
            "mission_id": (snapshot.get("mission") or {}).get("mission_id"),
            "scope": scope,
            "generated_utc": utc_now_iso(),
            "git_commit": config.get("git_commit") or _current_git_commit(),
            "seed": config.get("seed"),
            "scene_config": {
                "scene_xml_path": config.get("scene_xml_path"),
                "perturbation": config.get("perturbation", {}),
                "grasp_config": config.get("grasp_config", {}),
            },
            "export_options": {
                "include_rgbd": include_rgbd,
                "include_high_freq_trajectory": include_high_freq_trajectory,
                "include_audit_ground_truth": include_audit_ground_truth,
            },
            "missing_data_markers": missing_markers,
            "reference_integrity": ref_integrity,
            "files": manifest_files,
        }
        manifest_bytes = json.dumps(manifest, indent=2, ensure_ascii=False).encode("utf-8")
        entries["manifest.json"] = manifest_bytes

        buf = io.BytesIO()
        with zipfile.ZipFile(buf, mode="w", compression=zipfile.ZIP_DEFLATED) as zf:
            for rel_path in sorted(entries):
                zf.writestr(rel_path, entries[rel_path])
        zip_bytes = buf.getvalue()
        if out_path is not None:
            dest = Path(out_path)
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_bytes(zip_bytes)
        return zip_bytes, manifest

    @staticmethod
    def _build_markdown_report(
        *,
        config: dict[str, Any],
        snapshot: dict[str, Any],
        pose_estimates: list[dict[str, Any]],
        grasp_targets: list[dict[str, Any]],
        contact_verifications: list[dict[str, Any]],
        ref_integrity: dict[str, Any],
        missing_markers: dict[str, str],
    ) -> str:
        mission = snapshot.get("mission") or {}
        lines = [
            f"# CubeRelay Experiment Bundle Report — `{config.get('run_id')}`",
            "",
            f"- **Session ID**: `{config.get('session_id')}`",
            f"- **Seed**: `{config.get('seed')}`",
            f"- **Mission**: `{mission.get('mission_type', config.get('mission_type'))}` (`{mission.get('status', 'UNKNOWN')}`)",
            f"- **Git Commit**: `{config.get('git_commit')}`",
            f"- **Perturbation**: `{json.dumps(config.get('perturbation', {}), ensure_ascii=False)}`",
            f"- **Reference Integrity**: `{'PASS' if ref_integrity.get('ok') else 'FAIL'}`",
            "",
            "## Pose Estimates",
        ]
        if not pose_estimates:
            lines.append("- *Missing (`NO_POSE_ESTIMATES_RECORDED`)*")
        else:
            for p in pose_estimates:
                lines.append(
                    f"- `{p.get('pose_estimate_id')}` (v{p.get('pose_version')}) frame=`{p.get('frame_id')}` cam=`{p.get('camera_id')}` "
                    f"sim_t=`{p.get('sim_time')}` center=`{p.get('estimated_center_world_m')}` yaw=`{p.get('estimated_yaw_rad')}` "
                    f"status=`{p.get('quality_status')}`"
                )
        lines.extend(["", "## Grasp Targets"])
        if not grasp_targets:
            lines.append("- *Missing (`NO_GRASP_TARGETS_RECORDED`)*")
        else:
            for g in grasp_targets:
                lines.append(
                    f"- `{g.get('grasp_target_id')}` ← pose=`{g.get('pose_estimate_id')}` "
                    f"obj=`{g.get('object_center_world_m')}` target_ee=`{g.get('target_end_effector_pose')}` "
                    f"ik=`{g.get('ik_status')}` collision=`{g.get('collision_check_status')}`"
                )
        lines.extend(["", "## Contact Verifications"])
        if not contact_verifications:
            lines.append("- *Missing (`NO_CONTACT_VERIFICATIONS_RECORDED`)*")
        else:
            for cv in contact_verifications:
                lines.append(
                    f"- `{cv.get('contact_verification_id')}` skill=`{cv.get('skill_name')}` traj=`{cv.get('trajectory_id')}` "
                    f"bilateral=`{cv.get('bilateral_contact_fraction')}` slip=`{cv.get('relative_slip_m')}` "
                    f"L/R_N=`{cv.get('left_normal_force_n')}/{cv.get('right_normal_force_n')}` "
                    f"passed=`{cv.get('verification_result')}`"
                )
        if missing_markers:
            lines.extend(["", "## Missing Data Markers"])
            for k, v in missing_markers.items():
                lines.append(f"- `{k}`: `{v}`")
        return "\n".join(lines) + "\n"
