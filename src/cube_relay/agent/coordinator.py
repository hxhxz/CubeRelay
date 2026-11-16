"""Human/robot turn state machine with actual-state plan repair."""

from __future__ import annotations

from dataclasses import dataclass
from uuid import uuid4

from cube_relay.adapters.base import RobotAdapter
from cube_relay.adapters.observation import ManualObservationAdapter
from cube_relay.cube import CubeEngine, CubeSolver
from cube_relay.cube.state import inverse_move
from cube_relay.cube.state import LEGAL_MOVES
from cube_relay.models import CubeObservation, MoveRequest, SessionState


@dataclass(frozen=True, slots=True)
class CoordinatorEvent:
    sequence: int
    kind: str
    actual_state: str
    move: str | None
    plan_version: int
    detail: dict[str, object]


class TurnCoordinator:
    def __init__(self, robot: RobotAdapter, robot_mode: str = "sim",
                 engine: CubeEngine | None = None, solver: CubeSolver | None = None,
                 control_mode: str = "hierarchical",
                 policy_backend: str = "kociemba_baseline",
                 collaboration_mode: str = "guided_shared_plan") -> None:
        self.robot = robot
        self.robot_mode = robot_mode
        self.engine = engine or CubeEngine()
        self.solver = solver or CubeSolver()
        self.control_mode = control_mode
        self.policy_backend = policy_backend
        self.collaboration_mode = collaboration_mode
        self.manual = ManualObservationAdapter()
        self.state: SessionState | None = None
        self.events: list[CoordinatorEvent] = []
        self.initial_cube_state: str | None = None
        self.plan_input_state: str | None = None
        self.plan_solution: list[str] = []
        self.last_human_diagnostic: dict[str, object] | None = None
        self.state_visit_counts: dict[str, int] = {}
        self.pending_confirmation: dict[str, object] | None = None
        self._allow_inverse_once = False
        self._skip_repeat_pause_once = False

    def _emit(self, kind: str, move: str | None = None, **detail: object) -> None:
        assert self.state is not None
        self.events.append(CoordinatorEvent(len(self.events) + 1, kind,
                           self.state.actual_state, move, self.state.plan_version, detail))

    def start(self, facelets: str) -> SessionState:
        plan = self.solver.solve(facelets)
        self.initial_cube_state = facelets
        self.plan_input_state = facelets
        self.plan_solution = plan.copy()
        solved = self.engine.is_solved(facelets)
        self.state = SessionState(
            session_id=str(uuid4()), actual_state=facelets, planned_moves=plan,
            next_actor="human", plan_version=1, status="solved" if solved else "running",
            robot_mode=self.robot_mode, message="ready", machine_status="idle",
            control_mode=self.control_mode, policy_backend=self.policy_backend,
            collaboration_mode=self.collaboration_mode,
        )
        self._emit("SESSION_STARTED", initial_cube_state=facelets,
                   solver_input_state=facelets, solver_solution=plan.copy())
        self.state_visit_counts = {facelets: 1}
        return self.state

    def _set_confirmation(self, reason: str, *, pending_move: str | None = None,
                          **detail: object) -> None:
        state = self._require_active()
        self.pending_confirmation = {"reason": reason, "pending_move": pending_move, **detail}
        state.status = "paused"
        state.confirmation_required = True
        state.confirmation_reason = reason
        state.pending_robot_move = pending_move
        state.message = reason

    def _clear_confirmation(self) -> None:
        assert self.state is not None
        self.pending_confirmation = None
        self.state.confirmation_required = False
        self.state.confirmation_reason = None
        self.state.pending_robot_move = None
        self.state.message = "ready"

    def _record_state_visit(self, source: str, move: str) -> bool:
        assert self.state is not None
        current = self.state.actual_state
        count = self.state_visit_counts.get(current, 0) + 1
        self.state_visit_counts[current] = count
        if count > 1:
            self._emit("REPEATED_STATE", move, source=source, visit_count=count,
                       repeated_state=current)
            return True
        return False

    def _alternate_plan_avoiding(self, forbidden_move: str) -> list[str]:
        """Find a valid plan whose first move is not the declined inverse."""
        state = self._require_active()
        candidates: list[list[str]] = []
        for candidate in LEGAL_MOVES:
            if candidate == forbidden_move:
                continue
            after = self.engine.apply_move(state.actual_state, candidate)
            candidates.append([candidate, *self.solver.solve(after)])
        return min(candidates, key=len)

    def _require_active(self) -> SessionState:
        if self.state is None:
            raise RuntimeError("session has not started")
        if self.state.status == "solved":
            raise RuntimeError("session already solved")
        return self.state

    def _replan(self, reason: str) -> None:
        state = self._require_active()
        state.machine_status = "planning"
        solver_input_state = state.actual_state
        self._emit("PLANNING_STARTED", reason=reason, policy_backend=state.policy_backend,
                   solver_input_state=solver_input_state)
        state.planned_moves = self.solver.solve(solver_input_state)
        self.plan_input_state = solver_input_state
        self.plan_solution = state.planned_moves.copy()
        state.plan_version += 1
        state.machine_status = "ready" if state.next_actor == "robot" else "idle"
        self._emit("PLANNING_FINISHED", reason=reason,
                   planned_move_count=len(state.planned_moves),
                   solver_input_state=solver_input_state,
                   solver_solution=state.planned_moves.copy())
        self._emit("PLAN_REPAIRED", reason=reason)

    def submit_human_move(self, move: str) -> SessionState:
        state = self._require_active()
        if state.status != "running" or state.next_actor != "human":
            raise RuntimeError("not the human turn")
        recommended = state.planned_moves[0] if state.planned_moves else None
        state_before_human = state.actual_state
        state.actual_state = self.engine.apply_move(state.actual_state, move)
        state_after_human = state.actual_state
        unexpected = move != recommended
        self.last_human_diagnostic = {
            "initial_cube_state": self.initial_cube_state,
            "state_before_human": state_before_human,
            "human_move": move,
            "state_after_human": state_after_human,
            "recommended_move": recommended,
            "unexpected": unexpected,
        }
        self._emit("HUMAN_MOVE", move, recommended=recommended,
                   unexpected=unexpected, initial_cube_state=self.initial_cube_state,
                   state_before_human=state_before_human,
                   human_move=move, state_after_human=state_after_human)
        repeated_after_human = self._record_state_visit("human", move)
        if self.engine.is_solved(state.actual_state):
            state.status = "solved"
            state.planned_moves = []
            self._emit("SOLVED")
            return state
        if move == recommended:
            state.planned_moves = state.planned_moves[1:]
        else:
            self._replan("unexpected_human_move")
        state.next_actor = "robot"
        state.machine_status = "ready"
        if repeated_after_human:
            self._set_confirmation("REPEATED_STATE", repeated_state=state.actual_state,
                                   resume_actor="robot")
        return state

    def execute_robot_turn(self, *, plan_version: int | None = None) -> SessionState:
        state = self._require_active()
        if state.status != "running" or state.next_actor != "robot":
            raise RuntimeError("not the robot turn")
        if plan_version is not None and plan_version != state.plan_version:
            raise RuntimeError("stale plan version")
        move = state.planned_moves[0]
        before = state.actual_state
        human = self.last_human_diagnostic or {}
        human_move = human.get("human_move")
        is_direct_inverse = isinstance(human_move, str) and move == inverse_move(human_move)
        if human.get("unexpected") and is_direct_inverse:
            selection_reason = "solver_replan_first_move_is_inverse_of_unexpected_human_move"
        elif human.get("unexpected"):
            selection_reason = "first_move_of_solver_replan_after_unexpected_human_move"
        else:
            selection_reason = "next_move_from_existing_plan_after_recommended_human_move"
        self._emit(
            "ROBOT_MOVE_SELECTED", move,
            robot_selected_move=move,
            robot_selection_reason=selection_reason,
            is_inverse_of_human_move=is_direct_inverse,
            solver_input_state=self.plan_input_state,
            solver_solution=self.plan_solution.copy(),
        )
        undo_conflict = bool(human.get("unexpected") and is_direct_inverse and
                             self.engine.apply_move(before, move) == human.get("state_before_human"))
        if undo_conflict:
            self._emit(
                "UNDO_CONFLICT", move,
                human_move=human_move,
                robot_move=move,
                pre_human_state=human.get("state_before_human"),
                resulting_state=human.get("state_before_human"),
                collaboration_mode=state.collaboration_mode,
                requires_confirmation=(state.collaboration_mode == "guided_shared_plan"),
            )
            if state.collaboration_mode == "guided_shared_plan" and not self._allow_inverse_once:
                self._set_confirmation(
                    "UNDO_CONFLICT", pending_move=move, human_move=human_move,
                    state_before_human=human.get("state_before_human"),
                )
                return state
        self._allow_inverse_once = False
        expected_after = self.engine.apply_move(before, move)
        state.machine_status = "executing"
        self._emit("ROBOT_EXECUTION_STARTED", move)
        result = self.robot.execute_move(MoveRequest(
            actor="robot", move=move, expected_before=before, plan_version=state.plan_version
        ))
        if result.observed_after is None:
            state.machine_status = "failed"
            state.status = "paused"
            state.message = result.error or "execution unconfirmed"
            self._emit("ROBOT_MOVE_FAILED", move, backend=result.backend, error=result.error)
            return state
        state.actual_state = result.observed_after
        diagnostic = {
            "initial_cube_state": self.initial_cube_state,
            "state_before_human": human.get("state_before_human"),
            "human_move": human_move,
            "state_after_human": human.get("state_after_human"),
            "solver_input_state": self.plan_input_state,
            "solver_solution": self.plan_solution.copy(),
            "robot_selected_move": move,
            "robot_selection_reason": selection_reason,
            "is_inverse_of_human_move": is_direct_inverse,
            "state_after_robot": result.observed_after,
        }
        self._emit("TURN_DIAGNOSTIC", move, **diagnostic)
        state.machine_status = "verifying"
        self._emit("ROBOT_VERIFYING", move, backend=result.backend)
        self._emit("ROBOT_MOVE", move, backend=result.backend, success=result.success)
        if result.observed_after != expected_after:
            self._emit("STATE_MISMATCH", move, expected=expected_after,
                       observed=result.observed_after, error=result.error)
            self._replan("robot_execution_mismatch")
        else:
            state.planned_moves = state.planned_moves[1:]
        repeated = self._record_state_visit("robot", move)
        if self.engine.is_solved(state.actual_state):
            state.status = "solved"
            state.machine_status = "idle"
            state.planned_moves = []
            self._emit("SOLVED")
        else:
            state.next_actor = "human"
            state.machine_status = "idle"
            if repeated and not self._skip_repeat_pause_once:
                self._set_confirmation("REPEATED_STATE", repeated_state=state.actual_state)
        self._skip_repeat_pause_once = False
        return state

    def resolve_confirmation(self, decision: str) -> SessionState:
        if self.state is None or not self.state.confirmation_required or self.pending_confirmation is None:
            raise RuntimeError("no confirmation is pending")
        state = self.state
        reason = str(self.pending_confirmation["reason"])
        pending_move = self.pending_confirmation.get("pending_move")
        if reason == "UNDO_CONFLICT":
            if decision == "allow_inverse":
                self._clear_confirmation()
                state.status = "running"
                state.next_actor = "robot"
                self._allow_inverse_once = True
                self._skip_repeat_pause_once = True
                self._emit("USER_CONFIRMED_UNDO", str(pending_move), decision=decision)
                return self.execute_robot_turn(plan_version=state.plan_version)
            if decision == "keep_human_move":
                assert isinstance(pending_move, str)
                alternate = self._alternate_plan_avoiding(pending_move)
                self._clear_confirmation()
                state.status = "running"
                state.next_actor = "robot"
                state.planned_moves = alternate
                state.plan_version += 1
                self.plan_input_state = state.actual_state
                self.plan_solution = alternate.copy()
                state.machine_status = "ready"
                self._emit("USER_REJECTED_UNDO", decision=decision,
                           avoided_move=pending_move, alternate_solution=alternate.copy())
                self._emit("PLAN_REPAIRED", reason="user_kept_human_move")
                return state
            raise ValueError("UNDO_CONFLICT decision must be allow_inverse or keep_human_move")
        if reason == "REPEATED_STATE":
            if decision != "continue":
                raise ValueError("REPEATED_STATE decision must be continue")
            resume_actor = str(self.pending_confirmation.get("resume_actor", "human"))
            self._clear_confirmation()
            state.status = "running"
            state.next_actor = resume_actor
            self._emit("USER_CONFIRMED_REPEAT", decision=decision)
            return state
        raise RuntimeError(f"unknown confirmation reason: {reason}")

    def override_observation(self, observation: CubeObservation) -> SessionState:
        state = self._require_active()
        report = self.manual.validate(observation)
        if not report.valid:
            state.status = "paused"
            state.message = report.error or "INVALID_OBSERVATION"
            kind = report.error if report.error in {"LOW_CONFIDENCE", "MANUAL_CONFIRMATION_REQUIRED"} else "INVALID_OBSERVATION"
            self._emit(kind, error=report.error, source=observation.source)
            if kind in {"LOW_CONFIDENCE", "INVALID_OBSERVATION"}:
                self._emit("RETRY_SCAN", source=observation.source)
            return state
        state.actual_state = observation.facelets
        state.status = "running"
        state.message = "observation confirmed"
        self._emit("MANUAL_CONFIRMATION", source=observation.source,
                   confidence=observation.confidence)
        if self.engine.is_solved(state.actual_state):
            state.status = "solved"
            state.planned_moves = []
            self._emit("SOLVED")
        else:
            self._replan("confirmed_observation")
        return state
