"""FastAPI application for the human/robot relay demo."""

from __future__ import annotations

import asyncio
from dataclasses import asdict
import hmac
import os
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from cube_relay.adapters.dryrun_robot import DryRunRobotAdapter
from cube_relay.adapters.real_robot import DisabledRealRobotAdapter, RealRobotUnavailableError
from cube_relay.adapters.sim_robot import SimRobotAdapter
from cube_relay.agent import TurnCoordinator
from cube_relay.cube import CubeEngine, SOLVED_FACELETS
from cube_relay.benchmark import (
    BenchmarkExporter,
    build_m4d_replay_cases,
    discover_benchmark_runs,
    load_benchmark_run,
)
from cube_relay.benchmark.exporter import _sanitize_benchmark_payload
from cube_relay.experiment import ArtifactExporter, validate_run_id
from cube_relay.models import CubeObservation, SessionState

ROOT = Path(__file__).resolve().parents[3]
WEB = ROOT / "web"
WEB_CONSOLE = WEB / "console"
WEB_CONSOLE.mkdir(parents=True, exist_ok=True)
app = FastAPI(title="CubeRelay", version="0.4.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["GET", "POST"],
    allow_headers=["Content-Type"],
)
sessions: dict[str, TurnCoordinator] = {}
_m3d_session: Any = None
_m3d_default_seed: int = 0
_m3d_default_full_26_cubie: bool = os.getenv("CUBERELAY_M3D_FULL_26_CUBIE", "1").strip().lower() not in {
    "0",
    "false",
    "no",
}


class CreateSessionRequest(BaseModel):
    facelets: str | None = None
    scramble: str | None = None
    robot_mode: str = "sim"
    control_mode: str = "hierarchical"
    policy_backend: str = "kociemba_baseline"
    collaboration_mode: str = "guided_shared_plan"


class HumanMoveBody(BaseModel):
    move: str


class RobotTurnBody(BaseModel):
    plan_version: int | None = None


class ConfirmationBody(BaseModel):
    decision: str


class M3DExportRequest(BaseModel):
    run_id: str | None = None
    scope: str = "full_mission"
    include_rgbd: bool = True
    include_high_freq_trajectory: bool = True
    include_audit_ground_truth: bool = False


def _coordinator(session_id: str) -> TurnCoordinator:
    if session_id not in sessions:
        raise HTTPException(404, "session not found")
    return sessions[session_id]


def _call(action):
    try:
        return action()
    except (ValueError, RuntimeError) as exc:
        raise HTTPException(409, str(exc)) from exc


@app.post("/session", response_model=SessionState)
def create_session(body: CreateSessionRequest) -> SessionState:
    engine = CubeEngine()
    facelets = body.facelets or SOLVED_FACELETS
    if body.scramble:
        facelets = engine.apply_moves(SOLVED_FACELETS, body.scramble)
    if body.robot_mode == "sim":
        robot = SimRobotAdapter(engine)
    elif body.robot_mode == "dry_run":
        robot = DryRunRobotAdapter()
    elif body.robot_mode == "real":
        try:
            robot = DisabledRealRobotAdapter()
        except RealRobotUnavailableError as exc:
            raise HTTPException(503, str(exc)) from exc
    else:
        raise HTTPException(422, "robot_mode must be sim, dry_run, or real")
    allowed_modes = {"human_face_vla_turn", "vla_discrete", "vla_continuous", "hierarchical"}
    if body.control_mode not in allowed_modes:
        raise HTTPException(422, "unsupported control_mode")
    if body.policy_backend != "kociemba_baseline":
        raise HTTPException(503, "requested VLA policy backend is not installed")
    if body.collaboration_mode not in {"guided_shared_plan", "free_collaboration"}:
        raise HTTPException(422, "unsupported collaboration_mode")
    coordinator = TurnCoordinator(
        robot, body.robot_mode, engine=engine, control_mode=body.control_mode,
        policy_backend=body.policy_backend, collaboration_mode=body.collaboration_mode,
    )
    state = _call(lambda: coordinator.start(facelets))
    sessions[state.session_id] = coordinator
    return state


@app.get("/session/{session_id}", response_model=SessionState)
def get_session(session_id: str) -> SessionState:
    coordinator = _coordinator(session_id)
    assert coordinator.state is not None
    return coordinator.state


@app.post("/session/{session_id}/human-move", response_model=SessionState)
def human_move(session_id: str, body: HumanMoveBody) -> SessionState:
    return _call(lambda: _coordinator(session_id).submit_human_move(body.move))


@app.post("/session/{session_id}/robot-turn", response_model=SessionState)
def robot_turn(session_id: str, body: RobotTurnBody | None = None) -> SessionState:
    version = body.plan_version if body else None
    return _call(lambda: _coordinator(session_id).execute_robot_turn(plan_version=version))


@app.post("/session/{session_id}/confirm", response_model=SessionState)
def confirm(session_id: str, body: ConfirmationBody) -> SessionState:
    return _call(lambda: _coordinator(session_id).resolve_confirmation(body.decision))


@app.post("/session/{session_id}/observe", response_model=SessionState)
def observe(session_id: str, observation: CubeObservation) -> SessionState:
    return _call(lambda: _coordinator(session_id).override_observation(observation))


@app.get("/session/{session_id}/events")
def events(session_id: str) -> list[dict[str, object]]:
    return [asdict(event) for event in _coordinator(session_id).events]


@app.get("/session/{session_id}/events/export")
def export_events(session_id: str) -> dict[str, object]:
    coordinator = _coordinator(session_id)
    assert coordinator.state is not None
    return {"session": coordinator.state.model_dump(),
            "events": [asdict(event) for event in coordinator.events]}


@app.get("/")
def index():
    return FileResponse(WEB / "index.html")


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "service": "cube-relay"}


@app.get("/style.css")
def standalone_style():
    return FileResponse(WEB / "style.css", media_type="text/css")


@app.get("/app.js")
def standalone_script():
    return FileResponse(WEB / "app.js", media_type="application/javascript")


@app.get("/clarity.css")
def clarity_style():
    return FileResponse(WEB / "clarity.css", media_type="text/css")


# ============================================================================
# M3-D Mission Orchestration, Skill Registry, Decision Events & Live Session
# ============================================================================


def configure_m3d_session(
    session: Any = None,
    *,
    default_seed: int = 0,
    full_26_cubie: bool | None = None,
) -> None:
    global _m3d_session, _m3d_default_seed, _m3d_default_full_26_cubie
    _m3d_default_seed = int(default_seed)
    if full_26_cubie is not None:
        _m3d_default_full_26_cubie = bool(full_26_cubie)
    if session is not None:
        _m3d_session = session
        if (
            full_26_cubie is not None
            and hasattr(session, "reconfigure_full_26_cubie")
            and getattr(session, "full_26_cubie", None) != bool(full_26_cubie)
        ):
            session.reconfigure_full_26_cubie(bool(full_26_cubie))


def get_m3d_session() -> Any:
    global _m3d_session
    if _m3d_session is None:
        from cube_relay.mission.session import SimulationSession

        _m3d_session = SimulationSession(
            seed=_m3d_default_seed,
            use_dedicated_thread=True,
            full_26_cubie=_m3d_default_full_26_cubie,
        )
    return _m3d_session


def _resolve_mission_type(cmd: dict[str, Any]) -> str | None:
    if "mission_type" in cmd and cmd["mission_type"]:
        return str(cmd["mission_type"])
    task = cmd.get("task")
    if task == "single_u_turn":
        return "VERIFY_PHYSICAL_U_TURN"
    if task in {"INSPECT_CUBE", "VERIFY_PHYSICAL_U_TURN", "SOLVE_CUBE", "RELAY_SOLVE_CUBE"}:
        return str(task)
    return None


def _authorize_real_vlm(cmd: dict[str, Any]) -> None:
    """Gate real VLM activation without exposing or persisting the configured password."""
    configured = os.getenv("CUBERELAY_VLM_ENABLE_PASSWORD", "")
    supplied = cmd.get("enable_password")
    if not configured:
        raise HTTPException(
            503,
            "REAL_VLM_PASSWORD_NOT_CONFIGURED: set CUBERELAY_VLM_ENABLE_PASSWORD on the server",
        )
    if not isinstance(supplied, str) or not hmac.compare_digest(supplied, configured):
        raise HTTPException(403, "REAL_VLM_PASSWORD_INVALID: password verification failed")


def _dispatch_m3d_command(session: Any, cmd: dict[str, Any]) -> dict[str, Any]:
    ctype = str(cmd.get("type", "")).upper()
    if ctype == "GET_STATE":
        return {"ok": True, "snapshot": session.get_snapshot()}
    if ctype == "SELECT_MISSION":
        mtype = _resolve_mission_type(cmd) or "INSPECT_CUBE"
        sel_kwargs: dict[str, Any] = {}
        if "scramble_steps" in cmd and cmd["scramble_steps"] is not None:
            sel_kwargs["scramble_steps"] = cmd["scramble_steps"]
        snap = session.select_mission(mtype, **sel_kwargs)
        return {"ok": True, "snapshot": snap}
    if ctype == "SET_SCRAMBLE_STEPS":
        if "scramble_steps" not in cmd or cmd["scramble_steps"] is None:
            raise ValueError("SET_SCRAMBLE_STEPS requires scramble_steps")
        snap = session.set_scramble_steps(cmd["scramble_steps"])
        return {"ok": True, "snapshot": snap}
    if ctype == "SET_PLANNER_MODE":
        pmode = str(cmd.get("planner_mode", "DETERMINISTIC_PLANNER"))
        if pmode == "LLM_AGENT":
            _authorize_real_vlm(cmd)
        model = cmd.get("model")
        context_mode = str(cmd.get("context_mode", "vision_plus_structured_state"))
        kwargs: dict[str, Any] = {"model": model, "context_mode": context_mode}
        if "use_vlm_perception" in cmd:
            kwargs["use_vlm_perception"] = bool(cmd["use_vlm_perception"])
        if "guide_mode" in cmd and cmd["guide_mode"] is not None:
            kwargs["guide_mode"] = str(cmd["guide_mode"])
        snap = session.set_planner_mode(pmode, **kwargs)
        return {"ok": True, "snapshot": snap}
    if ctype in {"START_MISSION", "START_TASK"}:
        mtype = _resolve_mission_type(cmd) or session.selected_mission_type.value
        seed = cmd.get("seed")
        start_kwargs: dict[str, Any] = {
            "seed": int(seed) if seed is not None else None,
        }
        if "full_26_cubie" in cmd and cmd["full_26_cubie"] is not None:
            start_kwargs["full_26_cubie"] = bool(cmd["full_26_cubie"])
        if "scramble_steps" in cmd and cmd["scramble_steps"] is not None:
            start_kwargs["scramble_steps"] = cmd["scramble_steps"]
        if "scramble_moves" in cmd and cmd["scramble_moves"] is not None:
            start_kwargs["scramble_moves"] = list(cmd["scramble_moves"])
        ack = session.start_mission_async(mtype, **start_kwargs)
        return {"ok": ack.get("accepted", True), "ack": ack, "snapshot": session.get_snapshot()}
    if ctype in {"STOP_MISSION", "STOP_TASK"}:
        snap = session.stop_mission()
        return {"ok": True, "snapshot": snap}
    if ctype == "URGENT_INTERRUPT":
        snap = session.urgent_interrupt(str(cmd.get("reason") or "UI紧急中断指令"))
        return {"ok": True, "snapshot": snap}
    if ctype == "RESET_SCENE":
        seed = cmd.get("seed")
        mtype = _resolve_mission_type(cmd)
        reset_kwargs: dict[str, Any] = {
            "seed": int(seed) if seed is not None else None,
            "mission_type": mtype,
        }
        if "full_26_cubie" in cmd and cmd["full_26_cubie"] is not None:
            reset_kwargs["full_26_cubie"] = bool(cmd["full_26_cubie"])
        if "scramble_steps" in cmd and cmd["scramble_steps"] is not None:
            reset_kwargs["scramble_steps"] = cmd["scramble_steps"]
        if "scramble_moves" in cmd and cmd["scramble_moves"] is not None:
            reset_kwargs["scramble_moves"] = list(cmd["scramble_moves"])
        snap = session.reset_scene(**reset_kwargs)
        return {"ok": True, "snapshot": snap}
    if ctype == "HUMAN_APPLY_MOVE":
        if "move" not in cmd or not cmd["move"]:
            raise ValueError("HUMAN_APPLY_MOVE requires move")
        snap = session.human_apply_move(str(cmd["move"]))
        return {"ok": True, "snapshot": snap}
    if ctype == "HUMAN_UNDO_MOVE":
        snap = session.human_undo_move()
        return {"ok": True, "snapshot": snap}
    if ctype == "HUMAN_PERTURB_POSE":
        snap = session.human_perturb_pose(
            dx_m=float(cmd.get("dx_m", 0.0)),
            dy_m=float(cmd.get("dy_m", 0.0)),
            dyaw_deg=float(cmd.get("dyaw_deg", 0.0)),
        )
        return {"ok": True, "snapshot": snap}
    if ctype == "SET_TURN_QUOTA":
        return {"ok": True, "snapshot": session.set_turn_quota(cmd.get("quota", 3))}
    if ctype == "HUMAN_SEND_CHAT":
        text = cmd.get("text") if cmd.get("text") is not None else cmd.get("message")
        auto_res = cmd.get("auto_resume")
        snap = session.human_send_chat(
            str(text or ""),
            auto_resume=None if auto_res is None else bool(auto_res),
        )
        return {"ok": True, "snapshot": snap}
    if ctype == "HUMAN_FINISH_TURN":
        note = cmd.get("note")
        if getattr(session, "use_dedicated_thread", False) and hasattr(session, "human_finish_turn_async"):
            ack = session.human_finish_turn_async(note=note)
            snap = ack.get("snapshot", session.get_snapshot()) if isinstance(ack, dict) else session.get_snapshot()
            return {"ok": ack.get("accepted", True) if isinstance(ack, dict) else True, "ack": ack, "snapshot": snap}
        snap = session.human_finish_turn(note=note)
        return {"ok": True, "snapshot": snap}
    if ctype in {"CONFIGURE_SESSION", "SET_FULL_26_CUBIE"}:
        if "full_26_cubie" not in cmd or cmd["full_26_cubie"] is None:
            raise ValueError(f"{ctype} requires boolean full_26_cubie")
        target_full = bool(cmd["full_26_cubie"])
        seed = cmd.get("seed")
        mtype = _resolve_mission_type(cmd)
        if hasattr(session, "reconfigure_full_26_cubie") and seed is None and mtype is None:
            snap = session.reconfigure_full_26_cubie(target_full)
        else:
            snap = session.reset_scene(
                seed=int(seed) if seed is not None else None,
                mission_type=mtype,
                full_26_cubie=target_full,
            )
        return {"ok": True, "snapshot": snap}
    if ctype == "SET_CAMERA_PRESET":
        snap = session.set_camera_preset(str(cmd.get("camera", "overview")))
        return {"ok": True, "snapshot": snap}
    if ctype == "CAMERA_ORBIT":
        snap = session.orbit_camera(
            float(cmd.get("delta_azimuth", 0.0)),
            float(cmd.get("delta_elevation", 0.0)),
        )
        return {"ok": True, "snapshot": snap}
    if ctype == "CAMERA_ZOOM":
        snap = session.zoom_camera(float(cmd.get("delta_distance", 0.0)))
        return {"ok": True, "snapshot": snap}
    if ctype == "SET_RENDER_FLAGS":
        flags = cmd.get("flags") or {}
        snap = session.set_render_flags(dict(flags))
        return {"ok": True, "snapshot": snap}
    raise HTTPException(400, f"unsupported m3d command type: {ctype}")


@app.get("/api/m3d/state")
def m3d_state() -> dict[str, Any]:
    return get_m3d_session().get_snapshot()


@app.get("/api/m3d/capabilities")
def m3d_capabilities() -> dict[str, Any]:
    return get_m3d_session().get_capabilities()


@app.get("/api/m3d/events")
def m3d_events() -> list[dict[str, Any]]:
    return get_m3d_session().get_events()


@app.post("/api/m3d/command")
def m3d_command(cmd: dict[str, Any]) -> dict[str, Any]:
    session = get_m3d_session()
    try:
        return _dispatch_m3d_command(session, cmd)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(409, str(exc)) from exc


class M3DConfigureRequest(BaseModel):
    seed: int | None = None
    full_26_cubie: bool | None = None
    mission_type: str | None = None


@app.post("/api/m3d/configure")
def m3d_configure(req: M3DConfigureRequest) -> dict[str, Any]:
    global _m3d_default_seed, _m3d_default_full_26_cubie
    if req.seed is not None:
        _m3d_default_seed = int(req.seed)
    if req.full_26_cubie is not None:
        _m3d_default_full_26_cubie = bool(req.full_26_cubie)
    session = get_m3d_session()
    if req.seed is not None or req.mission_type is not None or req.full_26_cubie is not None:
        kwargs: dict[str, Any] = {}
        if req.full_26_cubie is not None:
            kwargs["full_26_cubie"] = bool(req.full_26_cubie)
        snap = session.reset_scene(
            seed=int(req.seed) if req.seed is not None else None,
            mission_type=req.mission_type,
            **kwargs,
        )
    else:
        snap = session.get_snapshot()
    return {"ok": True, "snapshot": snap}


def _exporter_for_session(session: Any) -> ArtifactExporter:
    exp = getattr(session, "exporter", None)
    if isinstance(exp, ArtifactExporter):
        return exp
    return ArtifactExporter(getattr(session, "experiment_recorder", None))


@app.get("/api/m3d/runs")
def m3d_list_runs() -> dict[str, Any]:
    session = get_m3d_session()
    snap = session.get_snapshot()
    exporter = _exporter_for_session(session)
    return {
        "current_run_id": snap.get("run_id"),
        "recording": snap.get("experiment_recording") or {},
        "runs": exporter.list_runs(),
    }


@app.get("/api/m3d/export/manifest")
def m3d_export_manifest(run_id: str | None = None) -> dict[str, Any]:
    session = get_m3d_session()
    snap = session.get_snapshot()
    exporter = _exporter_for_session(session)
    if run_id is not None:
        try:
            validate_run_id(run_id)
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from exc
    use_snap = snap if (run_id is None or run_id == snap.get("run_id")) else None
    try:
        return exporter.export_manifest_info(session_snapshot=use_snap, run_id=run_id)
    except FileNotFoundError as exc:
        raise HTTPException(404, str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc


def _run_m3d_export(
    *,
    run_id: str | None,
    scope: str,
    include_rgbd: bool,
    include_high_freq_trajectory: bool,
    include_audit_ground_truth: bool,
) -> Response:
    session = get_m3d_session()
    snap = session.get_snapshot()
    exporter = _exporter_for_session(session)
    if run_id is not None:
        try:
            validate_run_id(run_id)
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from exc
    use_snap = snap if (run_id is None or run_id == snap.get("run_id")) else None
    try:
        zip_bytes, manifest = exporter.export_zip_bytes(
            run_id=run_id,
            session_snapshot=use_snap,
            scope=scope,
            include_rgbd=include_rgbd,
            include_high_freq_trajectory=include_high_freq_trajectory,
            include_audit_ground_truth=include_audit_ground_truth,
        )
    except PermissionError as exc:
        raise HTTPException(403, str(exc)) from exc
    except FileNotFoundError as exc:
        raise HTTPException(404, str(exc)) from exc
    except ValueError as exc:
        msg = str(exc)
        status = 422 if "scope" in msg.lower() else 400
        raise HTTPException(status, msg) from exc
    resolved_run_id = str(manifest.get("run_id") or "cuberelay-export")
    safe_name = f"cuberelay_{resolved_run_id}_{scope}.zip"
    return Response(
        content=zip_bytes,
        media_type="application/zip",
        headers={
            "Content-Disposition": f'attachment; filename="{safe_name}"',
            "X-CubeRelay-Run-Id": resolved_run_id,
            "X-CubeRelay-Export-Scope": scope,
        },
    )


@app.get("/api/m3d/export")
def m3d_export_get(
    run_id: str | None = None,
    scope: str = "full_mission",
    include_rgbd: bool = True,
    include_high_freq_trajectory: bool = True,
    include_audit_ground_truth: bool = False,
) -> Response:
    return _run_m3d_export(
        run_id=run_id,
        scope=scope,
        include_rgbd=include_rgbd,
        include_high_freq_trajectory=include_high_freq_trajectory,
        include_audit_ground_truth=include_audit_ground_truth,
    )


@app.post("/api/m3d/export")
def m3d_export_post(req: M3DExportRequest) -> Response:
    return _run_m3d_export(
        run_id=req.run_id,
        scope=req.scope,
        include_rgbd=req.include_rgbd,
        include_high_freq_trajectory=req.include_high_freq_trajectory,
        include_audit_ground_truth=req.include_audit_ground_truth,
    )


def _m4d_benchmark_root() -> Path:
    custom = os.getenv("CUBERELAY_M4D_BENCHMARK_DIR", "").strip()
    return Path(custom).resolve() if custom else (ROOT / "results" / "m4d_benchmark")


@app.get("/api/m4d/benchmark/runs")
def m4d_benchmark_runs() -> dict[str, Any]:
    root = _m4d_benchmark_root()
    runs = discover_benchmark_runs(root)
    return {
        "status": "OK" if runs else "NOT_RUN",
        "root_dir": str(root),
        "runs": runs,
    }


@app.get("/api/m4d/benchmark/cases")
def m4d_benchmark_cases() -> dict[str, Any]:
    cases = build_m4d_replay_cases()
    items = [
        {
            "case_id": c.case_id,
            "benchmark_version": c.benchmark_version,
            "capability_dimension": c.capability_dimension.value,
            "difficulty": c.difficulty,
            "source_type": c.source_type.value,
            "mission_type": c.mission.get("mission_type"),
            "user_goal": c.mission.get("user_goal"),
            "expected_behavior": c.expected_behavior,
            "oracle_source": c.oracle_source,
            "disabled_skills": list(c.disabled_skills),
            "removed_skills": list(c.removed_skills),
            "seed": c.seed,
        }
        for c in cases
    ]
    return {"total": len(items), "cases": items}


@app.get("/api/m4d/benchmark/latest")
def m4d_benchmark_latest(run_id: str | None = None) -> dict[str, Any]:
    root = _m4d_benchmark_root()
    runs = discover_benchmark_runs(root)
    if not runs:
        return {
            "status": "NOT_RUN",
            "available_runs": [],
            "result": None,
        }
    target = None
    if run_id:
        clean_id = validate_run_id(run_id)
        for r in runs:
            if r.get("benchmark_run_id") == clean_id:
                target = r
                break
        if target is None:
            raise HTTPException(404, f"Benchmark run {run_id!r} not found")
    else:
        target = runs[0]

    loaded = load_benchmark_run(target["summary_path"])
    payload = _sanitize_benchmark_payload(loaded.model_dump(mode="json"))
    if loaded.contains_fake_provider and not loaded.real_scorecards:
        source_badge = "FAKE_PROVIDER"
    elif loaded.contains_fake_provider:
        source_badge = "MIXED_REAL_AND_FAKE"
    elif loaded.execution_mode == "deterministic_only":
        source_badge = "DETERMINISTIC_RULE"
    else:
        source_badge = "REAL_ONLINE_MODEL"
    return {
        "status": "OK",
        "source_badge": source_badge,
        "available_runs": runs,
        "result": payload,
    }


@app.get("/api/m4d/benchmark/export")
def m4d_benchmark_export(run_id: str | None = None) -> Response:
    root = _m4d_benchmark_root()
    runs = discover_benchmark_runs(root)
    if not runs:
        raise HTTPException(404, "No M4-D benchmark run available for export")
    target = runs[0]
    if run_id:
        clean_id = validate_run_id(run_id)
        matched = [r for r in runs if r.get("benchmark_run_id") == clean_id]
        if not matched:
            raise HTTPException(404, f"Benchmark run {run_id!r} not found")
        target = matched[0]
    loaded = load_benchmark_run(target["summary_path"])
    zip_bytes, _ = BenchmarkExporter.export_zip_bytes(loaded)
    filename = f"cuberelay_m4d_{loaded.benchmark_run_id}.zip"
    return Response(
        content=zip_bytes,
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@app.websocket("/ws/session")
async def ws_session(websocket: WebSocket) -> None:
    await websocket.accept()
    session = get_m3d_session()
    loop = asyncio.get_running_loop()
    queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue(maxsize=16)

    def _on_update(snapshot: dict[str, Any]) -> None:
        def _push() -> None:
            if queue.full():
                try:
                    queue.get_nowait()
                except asyncio.QueueEmpty:
                    pass
            queue.put_nowait(snapshot)

        loop.call_soon_threadsafe(_push)

    session.subscribe(_on_update)
    await websocket.send_json({"type": "STATE_UPDATE", "payload": session.get_snapshot()})

    async def _sender() -> None:
        while True:
            snap = await queue.get()
            await websocket.send_json({"type": "STATE_UPDATE", "payload": snap})

    sender_task = asyncio.create_task(_sender())
    try:
        while True:
            msg = await websocket.receive_json()
            if isinstance(msg, dict):
                try:
                    result = _dispatch_m3d_command(session, msg)
                except HTTPException as exc:
                    await websocket.send_json({
                        "type": "COMMAND_RESULT",
                        "ok": False,
                        "status": exc.status_code,
                        "error": str(exc.detail),
                    })
                    continue
                except (ValueError, RuntimeError) as exc:
                    await websocket.send_json({
                        "type": "COMMAND_RESULT",
                        "ok": False,
                        "status": 422 if isinstance(exc, ValueError) else 409,
                        "error": str(exc),
                    })
                    continue
                await websocket.send_json({"type": "STATE_UPDATE", "payload": result["snapshot"]})
    except WebSocketDisconnect:
        pass
    except Exception:
        pass
    finally:
        session.unsubscribe(_on_update)
        sender_task.cancel()


@app.get("/console")
def console_index():
    index_path = WEB_CONSOLE / "index.html"
    if not index_path.exists():
        raise HTTPException(404, "console bundle not built yet")
    return FileResponse(index_path)


app.mount("/console-assets", StaticFiles(directory=WEB_CONSOLE), name="console-assets")
app.mount("/static", StaticFiles(directory=WEB), name="static")
