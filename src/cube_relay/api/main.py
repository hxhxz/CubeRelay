"""FastAPI application for the human/robot relay demo."""

from __future__ import annotations

import asyncio
from dataclasses import asdict
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from cube_relay.adapters.dryrun_robot import DryRunRobotAdapter
from cube_relay.adapters.real_robot import DisabledRealRobotAdapter, RealRobotUnavailableError
from cube_relay.adapters.sim_robot import SimRobotAdapter
from cube_relay.agent import TurnCoordinator
from cube_relay.cube import CubeEngine, SOLVED_FACELETS
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


def configure_m3d_session(session: Any = None, *, default_seed: int = 0) -> None:
    global _m3d_session, _m3d_default_seed
    _m3d_default_seed = int(default_seed)
    if session is not None:
        _m3d_session = session


def get_m3d_session() -> Any:
    global _m3d_session
    if _m3d_session is None:
        from cube_relay.mission.session import SimulationSession

        _m3d_session = SimulationSession(
            seed=_m3d_default_seed,
            use_dedicated_thread=True,
        )
    return _m3d_session


def _resolve_mission_type(cmd: dict[str, Any]) -> str | None:
    if "mission_type" in cmd and cmd["mission_type"]:
        return str(cmd["mission_type"])
    task = cmd.get("task")
    if task == "single_u_turn":
        return "VERIFY_PHYSICAL_U_TURN"
    if task in {"INSPECT_CUBE", "VERIFY_PHYSICAL_U_TURN", "SOLVE_CUBE"}:
        return str(task)
    return None


def _dispatch_m3d_command(session: Any, cmd: dict[str, Any]) -> dict[str, Any]:
    ctype = str(cmd.get("type", "")).upper()
    if ctype == "GET_STATE":
        return {"ok": True, "snapshot": session.get_snapshot()}
    if ctype == "SELECT_MISSION":
        mtype = _resolve_mission_type(cmd) or "INSPECT_CUBE"
        snap = session.select_mission(mtype)
        return {"ok": True, "snapshot": snap}
    if ctype in {"START_MISSION", "START_TASK"}:
        mtype = _resolve_mission_type(cmd) or session.selected_mission_type.value
        seed = cmd.get("seed")
        ack = session.start_mission_async(
            mtype,
            seed=int(seed) if seed is not None else None,
        )
        return {"ok": ack.get("accepted", True), "ack": ack, "snapshot": session.get_snapshot()}
    if ctype in {"STOP_MISSION", "STOP_TASK"}:
        snap = session.stop_mission()
        return {"ok": True, "snapshot": snap}
    if ctype == "RESET_SCENE":
        seed = cmd.get("seed")
        mtype = _resolve_mission_type(cmd)
        snap = session.reset_scene(
            seed=int(seed) if seed is not None else None,
            mission_type=mtype,
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
                result = _dispatch_m3d_command(session, msg)
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
