"""Framework-independent public data contracts."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

Actor = Literal["human", "robot"]


class CubeObservation(BaseModel):
    facelets: str
    source: Literal["sim", "manual", "camera"]
    confidence: float = Field(ge=0, le=1)
    timestamp: str
    confirmed: bool = False


class MoveRequest(BaseModel):
    actor: Actor
    move: str
    expected_before: str
    plan_version: int


class MoveResult(BaseModel):
    success: bool
    move: str
    observed_after: str | None
    error: str | None = None
    backend: str


class SessionState(BaseModel):
    session_id: str
    actual_state: str
    planned_moves: list[str]
    next_actor: Actor
    plan_version: int
    status: Literal["idle", "running", "paused", "solved", "error"]
    robot_mode: Literal["sim", "dry_run", "real"]
    machine_status: Literal["idle", "planning", "ready", "executing", "verifying", "failed"] = "idle"
    control_mode: Literal[
        "human_face_vla_turn", "vla_discrete", "vla_continuous", "hierarchical"
    ] = "hierarchical"
    policy_backend: str = "kociemba_baseline"
    collaboration_mode: Literal["guided_shared_plan", "free_collaboration"] = "guided_shared_plan"
    confirmation_required: bool = False
    confirmation_reason: str | None = None
    pending_robot_move: str | None = None
    message: str = ""
