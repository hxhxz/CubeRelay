"""Comprehensive M4-C tests covering causal audit, exporter, GT boundary, perturbation, and regressions."""

from __future__ import annotations

import ast
import csv
import hashlib
import io
import json
import math
import os
from pathlib import Path
import sys
import zipfile

from fastapi.testclient import TestClient
import numpy as np
import pytest

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from cube_relay.api import main as api_main
from cube_relay.embodied.perception_v2 import DeterministicCubeLocalizer
from cube_relay.embodied.skill_agent import (
    ObserveCubeInput,
    PlanGraspInput,
    SkillBasedGraspAgent,
    SkillRuntime,
)
from cube_relay.embodied.v2_types import CameraCalibration, RGBDFrame
from cube_relay.embodied.vlm import HeuristicSceneVLM
from cube_relay.experiment import (
    ArtifactExporter,
    ExperimentRecorder,
    QualityStatus,
    TruthAccessBoundary,
    TruthAccessCategory,
    TruthAccessViolation,
    analyze_zip_bundles,
    load_zip_bundle,
    run_perturbation_suite,
)
from cube_relay.mission.events import DecisionEventLog, DecisionEventType, TraceEventLog, TraceEventType
from cube_relay.mission.models import MissionState, MissionStatus, MissionType, PlanState, PlanStep, PlanStepStatus
from cube_relay.mission.session import SimulationSession

_SKIP_GL = os.environ.get("CUBERELAY_SKIP_GL_TESTS") == "1"


def _make_calibrated_cube_rgbd(
    *,
    center_world_m: tuple[float, float, float] = (0.10, -0.12, 0.61),
    width: int = 160,
    height: int = 120,
    cam_pos: tuple[float, float, float] = (0.10, -0.12, 1.41),
) -> RGBDFrame:
    """Create a synthetic calibrated top-down RGB-D frame containing a colored cube top."""
    fx = fy = 220.0
    cx = width / 2.0
    cy = height / 2.0
    # Camera looking straight down (-Z world) -> CV +X=world +X, CV +Y=world -Y, CV +Z=world -Z
    c2w = np.eye(4, dtype=float)
    c2w[:3, :3] = np.diag([1.0, -1.0, -1.0])
    c2w[:3, 3] = np.array(cam_pos, dtype=float)

    rgb = np.full((height, width, 3), 210, dtype=np.uint8)
    depth = np.full((height, width), cam_pos[2] - 0.55, dtype=np.float32)  # table at z=0.55

    # Cube half-size ~ 0.056 m -> top surface at z = center_world_m[2] + 0.056
    z_top = center_world_m[2] + 0.057
    half = 0.057
    xs = np.linspace(center_world_m[0] - half, center_world_m[0] + half, 91)
    ys = np.linspace(center_world_m[1] - half, center_world_m[1] + half, 91)
    w2c = np.linalg.inv(c2w)
    for xw in xs:
        for yw in ys:
            p_cam = w2c @ np.array([xw, yw, z_top, 1.0])
            zc = float(p_cam[2])
            if zc <= 0.1:
                continue
            u = int(round(fx * p_cam[0] / zc + cx))
            v = int(round(fy * p_cam[1] / zc + cy))
            if 0 <= u < width and 0 <= v < height:
                rgb[v, u] = (20, 185, 70)  # vivid saturated green sticker
                depth[v, u] = np.float32(zc)

    cal = CameraCalibration(fx=fx, fy=fy, cx=cx, cy=cy, camera_to_world=c2w)
    return RGBDFrame(rgb=rgb, depth_m=depth, calibration=cal, camera_name="overhead", timestamp_seconds=1.25, frame_id="frm-synth-01")


def _build_complete_synthetic_run(base_dir: Path, *, secret_value: str = "AIzaTestSecretKey9876543210") -> tuple[ExperimentRecorder, str]:
    rec = ExperimentRecorder(base_dir=base_dir)
    run = rec.start_run(
        session_id="LIVE-SEED0-TEST01",
        seed=0,
        mission_type="INSPECT_CUBE",
        planner_mode="DETERMINISTIC_PLANNER",
        perturbation={"condition": "baseline", "dx_m": 0.0, "api_key": secret_value},
    )
    frame = _make_calibrated_cube_rgbd(center_world_m=(0.095, -0.125, 0.61))
    det, diag = DeterministicCubeLocalizer().locate_with_diagnostics(frame)
    assert det is not None

    run.poses.record_camera_frame(
        frame_id=frame.frame_id or "frm-synth-01",
        camera_id="overhead",
        rgb=frame.rgb,
        depth_m=frame.depth_m,
        fx=frame.calibration.fx,
        fy=frame.calibration.fy,
        cx=frame.calibration.cx,
        cy=frame.calibration.cy,
        camera_to_world=frame.calibration.camera_to_world,
        sim_time=1.25,
        rgb_sim_time=1.25,
        depth_sim_time=1.25,
        mission_id="msn-test1",
        skill_execution_id="exec-001",
        observation_id="obs-001",
    )
    pose = run.poses.record_pose_estimate(
        frame_id=frame.frame_id or "frm-synth-01",
        camera_id="overhead",
        sim_time=1.25,
        diagnostics=diag,
        mission_id="msn-test1",
        skill_execution_id="exec-001",
        observation_id="obs-001",
    )
    grasp = run.grasp_targets.record_grasp_target(
        pose_estimate=pose,
        sim_time=1.30,
        mission_id="msn-test1",
        skill_execution_id="exec-002",
        object_center_world_m=list(det.center_world_m),
        object_yaw_rad=float(det.yaw_radians),
        approach_offset_local_xy_m=[0.0, 0.0],
        world_offset_xy_m=[0.0, 0.0],
        target_end_effector_pose={"x_m": det.center_world_m[0], "y_m": det.center_world_m[1], "z_m": 0.665, "yaw_rad": 0.0},
        target_gripper_width_m=0.056,
        pregrasp_gap_m=0.095,
        actual_end_effector_pose_at_plan={"position_world_m": [0.0, 0.0, 0.85]},
        ik_status="FEASIBLE",
        reachability_status="REACHABLE",
        collision_check_status="CLEAR",
    )
    traj_id = run.trajectories.begin_trajectory(
        grasp_target_id=grasp.grasp_target_id,
        skill_execution_id="exec-002",
        ee_target={"x_m": det.center_world_m[0], "y_m": det.center_world_m[1], "z_m": 0.665, "yaw_rad": 0.0},
        phase="APPROACH",
    )
    run.trajectories.record_command(
        sim_time=1.32,
        phase="APPROACH",
        ctrl={"robot_x_ctrl": det.center_world_m[0], "robot_y_ctrl": det.center_world_m[1], "robot_z_ctrl": -0.35},
        cartesian_target=(det.center_world_m[0], det.center_world_m[1], -0.35),
    )
    row = {
        "trajectory_id": traj_id,
        "grasp_target_id": grasp.grasp_target_id,
        "skill_execution_id": "exec-002",
        "run_id": run.config.run_id,
        "sim_time": 1.35,
        "monotonic_wall_time": 100.1,
        "utc_timestamp": "2026-11-16T00:00:00Z",
        "controller_phase": "SLOW_CLOSE",
        "joint_robot_x": det.center_world_m[0] - 0.001,
        "joint_robot_y": det.center_world_m[1],
        "joint_robot_z": -0.35,
        "joint_wrist_yaw": 0.0,
        "joint_wrist_pitch": 0.0,
        "joint_left_finger": 0.015,
        "joint_right_finger": 0.015,
        "vel_robot_x": 0.0,
        "vel_robot_y": 0.0,
        "vel_robot_z": 0.0,
        "vel_wrist_yaw": 0.0,
        "vel_wrist_pitch": 0.0,
        "ctrl_robot_x": det.center_world_m[0],
        "ctrl_robot_y": det.center_world_m[1],
        "ctrl_robot_z": -0.35,
        "ctrl_wrist_yaw": 0.0,
        "ctrl_wrist_pitch": 0.0,
        "ctrl_left_finger": 0.074,
        "ctrl_right_finger": 0.074,
        "ee_target_x_m": det.center_world_m[0],
        "ee_target_y_m": det.center_world_m[1],
        "ee_target_z_m": 0.665,
        "ee_target_yaw_rad": 0.0,
        "ee_actual_x_m": round(det.center_world_m[0] - 0.001, 6),
        "ee_actual_y_m": round(det.center_world_m[1] + 0.001, 6),
        "ee_actual_z_m": 0.664,
        "ee_actual_yaw_rad": 0.0,
        "ee_actual_pitch_rad": 0.0,
        "gripper_inner_gap_m": 0.057,
        "coordinate_frame": "world",
        "units": "m,rad,s",
        "source_kind": "ROBOT_PROPRIOCEPTION",
        "quality_status": "VALID",
    }
    run.trajectories.robot_states.append(row)
    from cube_relay.experiment.recorder import ROBOT_STATE_FIELDS
    run.writer.enqueue_csv("robot_states.csv", ROBOT_STATE_FIELDS, row)
    run.grasp_targets.update_actual_contact_pose(
        grasp.grasp_target_id,
        {"position_world_m": [row["ee_actual_x_m"], row["ee_actual_y_m"], row["ee_actual_z_m"]]},
    )

    cv_id = run.contacts.begin_verification()
    phases = [
        ("APPROACH", 1.31, 0, 0, 0.0, 0.0, 0.000),
        ("SLOW_CLOSE", 1.35, 1, 1, 14.2, 14.0, 0.001),
        ("STABLE_HOLD", 1.45, 2, 2, 18.5, 18.2, 0.002),
        ("FULL_LIFT", 1.65, 2, 2, 19.1, 18.8, 0.004),
        ("REORIENT", 1.85, 2, 2, 17.8, 17.6, 0.007),
    ]
    for ph, st, lc, rc, lf, rf, slip in phases:
        run.contacts.record_sample(
            {
                "time_s": st,
                "phase": ph,
                "left_contact_count": lc,
                "right_contact_count": rc,
                "left_normal_force_n": lf,
                "right_normal_force_n": rf,
                "jaw_inner_gap_m": 0.056,
                "relative_cube_position_gripper_m": [0.0, 0.0, 0.0],
                "relative_slip_from_bilateral_contact_m": slip,
                "unexpected_gripper_contacts": [],
            },
            trajectory_id=traj_id,
            grasp_target_id=grasp.grasp_target_id,
            skill_execution_id="exec-002",
            contact_verification_id=cv_id,
        )
    run.contacts.finalize_verification(
        skill_name="initial_grasp",
        sim_time=1.90,
        trajectory_id=traj_id,
        grasp_target_id=grasp.grasp_target_id,
        pose_estimate_id=pose.pose_estimate_id,
        skill_execution_id="exec-002",
        bilateral_contact_fraction=0.96,
        left_contact_fraction=0.98,
        right_contact_fraction=0.97,
        left_normal_force_n=17.4,
        right_normal_force_n=17.1,
        relative_slip_m=0.007,
        gripper_width_m=0.056,
        lift_height_m=0.14,
        object_motion_relative_to_gripper_m=[0.0, 0.0, 0.0],
        object_followed_end_effector=True,
        unintended_contacts=[],
        verification_thresholds={"min_bilateral_contact_fraction": 0.80, "max_relative_slip_m": 0.03},
        verification_result=True,
        failure_reason=None,
        contact_verification_id=cv_id,
    )
    obs = {"observation_id": "obs-001", "frame_id": frame.frame_id, "sim_time": 1.25}
    run.events.record_observation(obs)
    run.events.record_decision_event({
        "event_id": "ev-001",
        "mission_id": "msn-test1",
        "observation_id": "obs-001",
        "skill_execution_id": "exec-001",
        "feedback_observation_id": "obs-001",
    })
    run.set_skill_executions([
        {"execution_id": "exec-001", "skill_id": "observe_workspace", "status": "VERIFIED", "elapsed_sec": 0.05},
        {"execution_id": "exec-002", "skill_id": "place_and_release", "status": "VERIFIED", "elapsed_sec": 0.65},
    ])
    snap = {
        "session_id": "LIVE-SEED0-TEST01",
        "run_id": run.config.run_id,
        "seed": 0,
        "sim_time": 1.90,
        "frame_source": "REAL_MUJOCO_RENDERER",
        "authorization": "Bearer TopSecretTokenValue",
        "mission": {"mission_id": "msn-test1", "mission_type": "INSPECT_CUBE", "status": "COMPLETED"},
        "timing_metrics": {"sim_time": 1.90, "skill_duration_sim_s": 0.70, "total_execution_wall_s": 1.2},
    }
    run.set_snapshot(snap)
    run.finalize(status="FINALIZED")
    return rec, run.config.run_id


# ---------------------------------------------------------------------------
# Section XIII Tests 1-17 (Non-GL Deterministic + Unit + API + Security + Audit)
# ---------------------------------------------------------------------------


def test_01_02_03_export_api_manifest_sha256_integrity_and_security(tmp_path: Path) -> None:
    """Tests #1, #2, #3: Export API ZIP, manifest SHA-256, secret redaction, path traversal."""
    rec, run_id = _build_complete_synthetic_run(tmp_path / "exp")
    exporter = ArtifactExporter(rec)

    class _StubSession:
        def __init__(self) -> None:
            self.experiment_recorder = rec
            self.exporter = exporter
            self.enable_password = "super_secret_password"

        def get_snapshot(self) -> dict[str, object]:
            return rec.get_run(run_id).session_snapshot  # type: ignore[union-attr]

    prev_session = api_main._m3d_session
    api_main.configure_m3d_session(_StubSession())
    try:
        client = TestClient(api_main.app)
        runs_resp = client.get("/api/m3d/runs")
        assert runs_resp.status_code == 200
        assert runs_resp.json()["current_run_id"] == run_id

        man_resp = client.get("/api/m3d/export/manifest")
        assert man_resp.status_code == 200
        assert man_resp.json()["exportable"] is True
        assert man_resp.json()["available_datasets"]["rgbd_frames"] is True

        # Reject path traversal
        bad_resp = client.get("/api/m3d/export", params={"run_id": "../secret"})
        assert bad_resp.status_code == 400

        # Export full mission via POST & causal chain via GET
        post_resp = client.post("/api/m3d/export", json={"run_id": run_id, "scope": "full_mission"})
        assert post_resp.status_code == 200
        assert post_resp.headers["content-type"] == "application/zip"

        causal_resp = client.get("/api/m3d/export", params={"run_id": run_id, "scope": "grasp_causal_chain"})
        assert causal_resp.status_code == 200

        with zipfile.ZipFile(io.BytesIO(post_resp.content)) as zf:
            names = set(zf.namelist())
            for req in (
                "manifest.json",
                "config.json",
                "session_snapshot.json",
                "decision_events.jsonl",
                "skill_executions.json",
                "observations.jsonl",
                "frames.jsonl",
                "camera_calibration.json",
                "pose_estimates.jsonl",
                "grasp_targets.jsonl",
                "trajectory_commands.csv",
                "robot_states.csv",
                "contact_samples.csv",
                "contact_verifications.jsonl",
                "metrics.json",
                "report.md",
            ):
                assert req in names, f"Missing {req} in exported ZIP"

            manifest = json.loads(zf.read("manifest.json").decode("utf-8"))
            assert manifest["reference_integrity"]["ok"] is True
            assert manifest["seed"] == 0
            assert manifest["run_id"] == run_id

            # Verify every SHA-256 and byte length in manifest
            for item in manifest["files"]:
                raw = zf.read(item["path"])
                assert len(raw) == item["size_bytes"]
                assert hashlib.sha256(raw).hexdigest() == item["sha256"]

            # Secret redaction check
            bundle_dump = "\n".join(
                zf.read(n).decode("utf-8", errors="replace")
                for n in names
                if n.endswith((".json", ".jsonl", ".csv", ".md"))
            )
            assert "AIzaTestSecretKey9876543210" not in bundle_dump
            assert "TopSecretTokenValue" not in bundle_dump
    finally:
        api_main.configure_m3d_session(prev_session)


def test_04_05_rgbd_alignment_and_metric_depth_recovery(tmp_path: Path) -> None:
    """Tests #4 & #5: RGB/Depth sim_time synchronization and lossless float32 .npy depth recovery."""
    rec, run_id = _build_complete_synthetic_run(tmp_path / "exp")
    exporter = ArtifactExporter(rec)
    zip_bytes, _ = exporter.export_zip_bytes(run_id=run_id)
    with zipfile.ZipFile(io.BytesIO(zip_bytes)) as zf:
        frames = [json.loads(line) for line in zf.read("frames.jsonl").decode("utf-8").splitlines() if line.strip()]
        assert len(frames) == 1
        f = frames[0]
        assert f["rgb_sim_time"] == f["sim_time"]
        assert f["depth_sim_time"] == f["sim_time"]
        assert f["rgb_depth_sim_time_delta_s"] == 0.0
        rgb_bytes = zf.read(f["rgb_path"])
        depth_bytes = zf.read(f["depth_path"])
        depth_arr = np.load(io.BytesIO(depth_bytes), allow_pickle=False)
        assert depth_arr.dtype == np.float32
        assert depth_arr.shape == (f["height"], f["width"])
        assert len(rgb_bytes) > 100
        # Camera at z=1.41, cube top at 0.61+0.057=0.667 -> depth = 0.743 m; table = 0.86 m
        assert float(np.min(depth_arr)) == pytest.approx(1.41 - (0.61 + 0.057), abs=1e-4)
        assert float(np.max(depth_arr)) == pytest.approx(1.41 - 0.55, abs=1e-4)


def test_06_07_08_09_causal_chain_from_rgbd_to_contact_windows(tmp_path: Path) -> None:
    """Tests #6, #7, #8, #9: Frame -> Pose -> Grasp Target -> Trajectory -> Contact Phase Windows."""
    rec, run_id = _build_complete_synthetic_run(tmp_path / "exp")
    zip_path = tmp_path / "bundle.zip"
    ArtifactExporter(rec).export_zip_bytes(run_id=run_id, out_path=zip_path)
    bundle = load_zip_bundle(zip_path)

    assert len(bundle["pose_estimates"]) == 1
    pose = bundle["pose_estimates"][0]
    assert pose["frame_id"] == bundle["frames"][0]["frame_id"]
    assert pose["camera_id"] == "overhead"
    assert pose["source_kind"] == "VISUAL_POSE_ESTIMATE"
    # Recovered world center X/Y within 12 mm (at fx=220, 1px ~ 3.4 mm) of true synthetic placement (0.095, -0.125)
    est = pose["estimated_center_world_m"]
    assert abs(est[0] - 0.095) < 0.012
    assert abs(est[1] - (-0.125)) < 0.012

    grasp = bundle["grasp_targets"][0]
    assert grasp["pose_estimate_id"] == pose["pose_estimate_id"]
    assert grasp["pose_version"] == pose["pose_version"]
    # Three distinct poses must be preserved (Pose Estimate vs Grasp Target vs Actual EE)
    assert grasp["object_center_world_m"] != [
        grasp["target_end_effector_pose"]["x_m"],
        grasp["target_end_effector_pose"]["y_m"],
        grasp["target_end_effector_pose"]["z_m"],
    ]
    assert grasp["actual_end_effector_pose_at_contact"]["position_world_m"] != [
        grasp["target_end_effector_pose"]["x_m"],
        grasp["target_end_effector_pose"]["y_m"],
        grasp["target_end_effector_pose"]["z_m"],
    ]

    rs = bundle["robot_states"]
    assert rs[0]["grasp_target_id"] == grasp["grasp_target_id"]

    cv = bundle["contact_verifications"][0]
    assert cv["trajectory_id"] == rs[0]["trajectory_id"]
    assert cv["grasp_target_id"] == grasp["grasp_target_id"]
    for win in ("Approach", "Initial Contact", "Grasp Closure", "Lift / Hold", "Reorientation"):
        assert win in cv["phase_windows"]
        assert cv["phase_windows"][win]["sample_count"] >= 1
    assert cv["phase_windows"]["Approach"]["bilateral_contact_fraction"] == 0.0
    assert cv["phase_windows"]["Lift / Hold"]["bilateral_contact_fraction"] == 1.0

    # Verify offline causal analyzer generates metrics, report, and all 6 PNG charts
    analysis = analyze_zip_bundles([zip_path], output_dir=tmp_path / "analysis")
    assert Path(analysis["report_path"]).exists()
    assert len(analysis["plots"]) == 6
    for plot_p in analysis["plots"].values():
        assert Path(plot_p).exists() and Path(plot_p).stat().st_size > 1024


def test_10_regrasp_zero_contact_gate_regression_and_timeline_fixes() -> None:
    """Test #10 (+ Anomalies #1, #4, #5): regrasp bilateral_contact=0 must NEVER be VERIFIED; timeline immutable."""
    from cube_relay.embodied.mujoco_v2 import MuJoCoEmbodiedBackend
    from cube_relay.embodied.v2_types import GraspControlConfig, GraspTelemetry

    # Reproduce exact Anomaly #1: action sequence succeeds geometrically, but last_grasp_telemetry has bilateral=0
    fake = object.__new__(MuJoCoEmbodiedBackend)
    fake.grasp_config = GraspControlConfig()
    fake.last_grasp_telemetry = GraspTelemetry(False, 0.0, 0.0, 0.0, 0.0, "not attempted")
    fake.contact_failure_class = None
    fake.contact_debug_trace = []
    fake.experiment_run = None
    fake._active_contact_verification_id = None
    fake.last_selected_grasp_candidate = type(
        "Cand", (), {"wrist_yaw_radians": 0.0, "face_pair": "local_y_faces"}
    )()
    fake.last_grasp_candidates = ()
    fake.task_align_scan_axes = lambda: {
        "success": True,
        "bilateral_contact_fraction": 0.99,
        "left_contact_fraction": 1.0,
        "right_contact_fraction": 0.99,
        "left_normal_force_n": 18.0,
        "right_normal_force_n": 18.0,
        "max_relative_slip_m": 0.002,
    }
    fake.refresh_visual_world_state = lambda *a, **kw: {"success": True}
    # Simulate _regrasp_from_pixels returning True without updating last_grasp_telemetry -> STILL bilateral=0!
    fake._regrasp_from_pixels = lambda *a, **kw: True

    res = MuJoCoEmbodiedBackend.task_regrasp(fake, exclude_face_pairs={"local_x_faces"})
    assert res["contact_verification_passed"] is False
    assert res["success"] is False
    assert res["bilateral_contact_fraction"] == 0.0
    assert res["failure_code"] == "REGRASP_CONTACT_VERIFICATION_FAILED"

    # Also verify Timeline immutability (Anomaly #4): earlier events must keep their own stage_id!
    sess = object.__new__(SimulationSession)
    sess.event_log = DecisionEventLog()
    sess.trace_log = TraceEventLog()
    sess._timeline_events = []
    sess._recorded_observations = []
    sess._current_run = None
    sess.session_id = "LIVE-TEST"
    sess.mission = MissionState(
        mission_id="msn-1",
        session_id="LIVE-TEST",
        mission_type=MissionType.INSPECT_CUBE,
        user_goal="test",
        success_criteria="test",
        status=MissionStatus.EXECUTING,
        created_at="00:00:00",
    )
    sess.plan = PlanState(
        plan_id="plan-1",
        mission_id="msn-1",
        mission_type=MissionType.INSPECT_CUBE,
        planner_name="DeterministicMissionPlanner",
        rationale_summary="test",
        created_at="00:00:00",
        updated_at="00:00:00",
        steps=[
            PlanStep(step_id="step-1", index=1, title="S1", skill_id="observe_workspace", description="d", status=PlanStepStatus.RUNNING),
            PlanStep(step_id="step-2", index=2, title="S2", skill_id="place_and_release", description="d", status=PlanStepStatus.PENDING),
        ],
    )
    sess._sim_time = lambda: 1.0
    sess._read_telemetry = lambda: {"layerTurnAngleDeg": 0.0, "contactForceN": 0.0, "gripperWidthMm": 80.0, "gripperState": "OPEN"}
    sess.planner = type("P", (), {"mode": type("M", (), {"value": "DETERMINISTIC_PLANNER"})(), "llm_model": None})()
    ev1 = sess._record_decision(
        event_type=DecisionEventType.SKILL_COMPLETED,
        source="SkillExecutor",
        summary="done s1",
        rationale="r1",
        status="VERIFIED",
        skill_id="observe_workspace",
    )
    assert ev1 is not None
    sess.plan.steps[0].status = PlanStepStatus.VERIFIED
    sess.plan.steps[1].status = PlanStepStatus.RUNNING
    sess._sim_time = lambda: 5.0
    sess._record_decision(
        event_type=DecisionEventType.SKILL_COMPLETED,
        source="SkillExecutor",
        summary="done s2",
        rationale="r2",
        status="VERIFIED",
        skill_id="place_and_release",
    )
    assert sess._timeline_events[0]["stage_id"] == "step-1"
    assert sess._timeline_events[1]["stage_id"] == "step-2"


def test_13_non_gl_reachability_block_and_no_forced_success(tmp_path: Path) -> None:
    """Test #13 (unit): Out-of-workspace cube recorded as UNREACHABLE/BLOCKED, never forced to grasp."""
    from cube_relay.embodied.mujoco_v2 import MuJoCoEmbodiedBackend
    from cube_relay.embodied.v2_types import GraspControlConfig

    frame = _make_calibrated_cube_rgbd(center_world_m=(0.75, -0.10, 0.61), cam_pos=(0.75, -0.10, 1.41))
    rec = ExperimentRecorder(base_dir=tmp_path / "exp")
    run = rec.start_run(session_id="LIVE-TEST", seed=0)

    class _MockBackend:
        def __init__(self) -> None:
            self.experiment_run = run
            self.truth_boundary = TruthAccessBoundary()
            self.grasp_config = GraspControlConfig()
            self.data = type("D", (), {"time": 0.5, "qpos": np.zeros(20)})()
            self.model = type("M", (), {"jnt_qposadr": [0] * 20})()

        def _id(self, kind: object, name: str) -> int:
            return 0

        def _joint(self, name: str) -> int:
            return 0

        _wrapped_angle_distance = staticmethod(MuJoCoEmbodiedBackend._wrapped_angle_distance)

        def capture_rgbd(self, camera_name: str = "overhead") -> RGBDFrame:
            return frame

        def generate_grasp_candidates(self, target_xyz: tuple[float, float, float], cube_yaw: float):
            return MuJoCoEmbodiedBackend.generate_grasp_candidates(self, target_xyz, cube_yaw)

    rt = SkillRuntime(_MockBackend(), HeuristicSceneVLM())
    obs_out = rt.observe_cube(ObserveCubeInput())
    assert obs_out.success is True
    plan_out = rt.plan_grasp(PlanGraspInput(detection=obs_out.detection))
    assert plan_out.success is False
    assert all(not c.ik_feasible for c in plan_out.candidates)
    run.flush()
    assert len(run.grasp_targets.grasp_targets) == 1
    assert run.grasp_targets.grasp_targets[0].reachability_status == "UNREACHABLE"
    assert run.grasp_targets.grasp_targets[0].quality_status == QualityStatus.UNREACHABLE


def test_14_15_truth_boundary_ast_runtime_leakage_and_vision_blackout_negative_control(tmp_path: Path) -> None:
    """Section XII & Tests #14, #15: Hard GT leakage guards, vision blackout refusal, cache invalidation."""
    # (a) AST audit: perception_v2.py must not reference mujoco qpos/xpos/xmat or _true_cube_pose
    p_src = (ROOT / "src" / "cube_relay" / "embodied" / "perception_v2.py").read_text(encoding="utf-8")
    tree = ast.parse(p_src)
    forbidden_attrs = {"xpos", "xquat", "xmat", "qpos", "geom_xpos", "cvel", "_true_cube_pose"}
    found_forbidden = [
        node.attr for node in ast.walk(tree) if isinstance(node, ast.Attribute) and node.attr in forbidden_attrs
    ]
    assert found_forbidden == [], f"perception_v2 references simulator truth attributes: {found_forbidden}"

    # (b) Runtime boundary enforcement: assert_cube_truth_allowed raises inside RUNTIME_LOCALIZATION_FORBIDDEN
    boundary = TruthAccessBoundary()
    with boundary.scope(TruthAccessCategory.RUNTIME_LOCALIZATION_FORBIDDEN, "test_perception"):
        with pytest.raises(TruthAccessViolation):
            boundary.assert_cube_truth_allowed("data.xpos[cube]")

    # (c) Negative control with hidden MuJoCo cube shift + sensor blackout -> must NOT use GT or stale cache
    good_frame = _make_calibrated_cube_rgbd(center_world_m=(0.08, -0.10, 0.61), cam_pos=(0.08, -0.10, 1.41))
    blackout_frame = RGBDFrame(
        rgb=np.zeros((120, 160, 3), dtype=np.uint8),
        depth_m=np.full((120, 160), np.nan, dtype=np.float32),
        calibration=good_frame.calibration,
        camera_name="overhead",
        timestamp_seconds=2.0,
        frame_id="frm-blackout",
    )
    rec = ExperimentRecorder(base_dir=tmp_path / "exp")
    run = rec.start_run(session_id="LIVE-NEG", seed=0, perturbation={"dx_m": 0.05, "vision_fault_mode": "blackout"})

    class _TrapBackend:
        def __init__(self) -> None:
            self.experiment_run = run
            self.truth_boundary = TruthAccessBoundary()
            self.data = type("D", (), {"time": 1.0})()
            self.use_blackout = False

        @property
        def hidden_cube_gt(self) -> tuple[float, float, float]:
            self.truth_boundary.assert_cube_truth_allowed("hidden_cube_gt")
            return (0.145, -0.125, 0.61)

        def capture_rgbd(self, camera_name: str = "overhead") -> RGBDFrame:
            self.truth_boundary.assert_cube_truth_allowed  # never called
            return blackout_frame if self.use_blackout else good_frame

        def generate_grasp_candidates(self, target_xyz, cube_yaw):
            raise AssertionError("generate_grasp_candidates must never be reached when vision fails")

    backend = _TrapBackend()
    rt = SkillRuntime(backend, HeuristicSceneVLM())
    # First succeed cleanly
    first_obs = rt.observe_cube(ObserveCubeInput())
    assert first_obs.success is True
    assert rt.state.detection is not None
    stale_det = first_obs.detection
    # Now switch sensor to blackout (simulating vision outage while cube physically moved)
    backend.use_blackout = True
    backend.data.time = 2.0
    fail_out = rt.observe_cube(ObserveCubeInput())
    assert fail_out.success is False
    # Stale cache MUST be cleared and planning MUST refuse even if given stale detection!
    assert rt.state.observed is False
    assert rt.state.detection is None
    assert rt.state.candidates == ()
    plan_out = rt.plan_grasp(PlanGraspInput(detection=stale_det))
    assert plan_out.success is False
    assert len(run.grasp_targets.grasp_targets) == 0


def test_16_17_legacy_snapshot_no_forged_samples_and_sample_mode_blocked(tmp_path: Path) -> None:
    """Tests #16 & #17: Legacy snapshots never forge trajectories; SAMPLE mode strictly blocked."""
    exporter = ArtifactExporter(ExperimentRecorder(base_dir=tmp_path / "exp"))

    legacy_snapshot = {
        "session_id": "LEGACY-001",
        "seed": 3,
        "sim_time": 12.5,
        "frame_source": "REAL_MUJOCO_RENDERER",
        "decision_events": [
            {"event_id": "ev-legacy-1", "sim_time": 4.2, "wall_time": "2026-11-15T10:00:00Z", "event_type": "SKILL_COMPLETED"}
        ],
        "trace_events": [],
        "observations": [],
        "skill_executions": [],
    }
    zip_bytes, manifest = exporter.export_zip_bytes(session_snapshot=legacy_snapshot, scope="full_mission")
    with zipfile.ZipFile(io.BytesIO(zip_bytes)) as zf:
        assert "robot_states.csv" not in zf.namelist()
        assert "contact_samples.csv" not in zf.namelist()
        markers = manifest["missing_data_markers"]
        assert markers["robot_states"] == "NO_TRAJECTORY_RECORDED"
        assert markers["pose_estimates"] == "NO_POSE_ESTIMATES_RECORDED"
        evs = [json.loads(l) for l in zf.read("decision_events.jsonl").decode("utf-8").splitlines() if l.strip()]
        assert evs[0]["wall_time"] == "2026-11-15T10:00:00Z"

    # SAMPLE mode must be rejected by both Exporter and API
    sample_snap = {"session_id": "SYNTHETIC-SAMPLE-001", "frame_source": "SYNTHETIC_SAMPLE"}
    with pytest.raises(PermissionError, match="SAMPLE_MODE_FORBIDDEN"):
        exporter.export_zip_bytes(session_snapshot=sample_snap)

    exp_recorder = exporter.recorder
    exp_exporter = exporter

    class _SampleSession:
        experiment_recorder = exp_recorder
        exporter = exp_exporter

        def get_snapshot(self) -> dict[str, object]:
            return dict(sample_snap)

    prev = api_main._m3d_session
    api_main.configure_m3d_session(_SampleSession())
    try:
        client = TestClient(api_main.app)
        assert client.get("/api/m3d/export/manifest").json()["exportable"] is False
        resp = client.post("/api/m3d/export", json={"scope": "full_mission"})
        assert resp.status_code == 403
        assert "SAMPLE_MODE_FORBIDDEN" in resp.text
    finally:
        api_main.configure_m3d_session(prev)


# ---------------------------------------------------------------------------
# Real MuJoCo GL Perturbation & Full Closed-Loop Tests (#11-#15 + Analyzer)
# ---------------------------------------------------------------------------


@pytest.mark.skipif(_SKIP_GL, reason="GL tests disabled")
def test_mujoco_real_causal_suite_baseline_plus5cm_plus10cm_negcontrol(tmp_path: Path) -> None:
    """Real MuJoCo verification of Tests #4-#15 + Section XI automated causal analysis & 6 plots."""
    index = run_perturbation_suite(
        ["baseline", "translate_x_005", "translate_x_010", "vision_missing_negative_control"],
        seed=0,
        mission_type="INSPECT_CUBE",
        output_dir=tmp_path / "m4c_real",
        trajectory_sample_hz=50.0,
        width=320,
        height=240,
    )
    results_by_name = {r["condition"]: r for r in index["results"]}
    assert results_by_name["baseline"]["mission_status"] == "COMPLETED"
    assert results_by_name["vision_missing_negative_control"]["mission_status"] == "FAILED"

    summary = analyze_zip_bundles(
        [r["zip_path"] for r in index["results"]],
        output_dir=tmp_path / "m4c_real" / "analysis",
    )
    deltas = {d["condition"]: d for d in summary["x_deltas"]}
    metrics = {m["condition"]: m for m in summary["metrics"]}

    # Baseline verified real contacts & recoverable float32 depth
    assert metrics["baseline"]["bilateral_contact_passed_count"] >= 2
    assert metrics["baseline"]["data_source_compliant"] is True

    # +5 cm causal chain: GT dX, RGB-D Est dX, Grasp Target dX, Actual EE dX respond to +0.05 m shift
    d5 = deltas["translate_x_005"]
    m5 = metrics["translate_x_005"]
    assert d5["delta_x_ground_truth_m"] == pytest.approx(0.05, abs=0.005)
    assert d5["delta_x_rgbd_estimate_m"] == pytest.approx(0.05, abs=0.015)
    assert d5["delta_x_grasp_target_m"] == pytest.approx(0.05, abs=0.015)
    assert d5["delta_x_actual_end_effector_m"] == pytest.approx(0.05, abs=0.025)
    assert m5["initial_grasp_verification"] is not None
    assert m5["initial_grasp_verification"]["verification_result"] is True
    assert m5["initial_grasp_verification"]["bilateral_contact_fraction"] >= 0.80
    assert m5["data_source_compliant"] is True

    # +10 cm: RGB-D & grasp target must track +0.10 m; execution either completes or fails truthfully
    d10 = deltas["translate_x_010"]
    m10 = metrics["translate_x_010"]
    assert d10["delta_x_ground_truth_m"] == pytest.approx(0.10, abs=0.005)
    assert d10["delta_x_rgbd_estimate_m"] == pytest.approx(0.10, abs=0.015)
    assert d10["delta_x_grasp_target_m"] == pytest.approx(0.10, abs=0.015)
    assert d10["delta_x_actual_end_effector_m"] >= 0.08
    assert (
        m10["mission_status"] == "COMPLETED"
        or m10["grasp_reachability_status"] in {"UNREACHABLE", "COLLISION_BLOCKED"}
        or m10["failure_reason"] is not None
    )

    # Negative control must produce zero valid pose estimates & zero grasp targets
    assert metrics["vision_missing_negative_control"]["grasp_target_id"] is None
    assert metrics["vision_missing_negative_control"]["negative_control_clean"] is True
    assert metrics["vision_missing_negative_control"]["data_source_compliant"] is True

    # All 6 analysis plots generated
    for plot_path in summary["plots"].values():
        assert Path(plot_path).exists() and Path(plot_path).stat().st_size > 1024


@pytest.mark.skipif(_SKIP_GL, reason="GL tests disabled")
def test_mujoco_real_regrasp_negative_control_and_cache_isolation(tmp_path: Path) -> None:
    """Real MuJoCo check: fresh session has clean pose cache & SkillBasedGraspAgent refuses blackout."""
    from cube_relay.embodied.mujoco_v2 import MuJoCoEmbodiedBackend

    backend = MuJoCoEmbodiedBackend(physical_u=True, width=320, height=240)
    try:
        backend.reset_with_perturbation(0, 15, dx_m=0.05)
        rt = SkillRuntime(backend, HeuristicSceneVLM())
        first_obs = rt.observe_cube(ObserveCubeInput())
        assert first_obs.detection is not None
        stale_det = first_obs.detection

        # Reset must wipe pose caches cleanly
        backend.reset_with_perturbation(0, 15, dx_m=0.0, vision_fault_mode="blackout")
        assert backend.last_grasp_candidates == ()
        assert backend.last_selected_grasp_candidate is None
        assert backend.visual_world_state is None
        assert backend._world_state_revision == 0

        # Blackout observation must fail & never plan grasp from hidden MuJoCo cube qpos
        out = rt.observe_cube(ObserveCubeInput())
        assert out.success is False
        assert rt.state.detection is None
        plan_out = rt.plan_grasp(PlanGraspInput(detection=stale_det))
        assert plan_out.success is False
    finally:
        backend.renderer.close()
