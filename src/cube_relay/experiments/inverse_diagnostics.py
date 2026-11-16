"""Offline diagnostics for Human move followed by Robot solver selection."""

from __future__ import annotations

import random
from dataclasses import asdict, dataclass

from cube_relay.adapters.sim_robot import SimRobotAdapter
from cube_relay.agent import TurnCoordinator
from cube_relay.cube import CubeEngine, CubeSolver, SOLVED_FACELETS, inverse_move
from cube_relay.cube.state import LEGAL_MOVES


@dataclass(frozen=True, slots=True)
class DiagnosticRecord:
    case_type: str
    seed: int
    scramble_length: int
    scramble_moves: list[str]
    initial_cube_state: str
    state_before_human: str
    human_move: str
    state_after_human: str
    solver_input_state: str
    solver_solution: list[str]
    robot_selected_move: str
    robot_selection_reason: str
    is_inverse_of_human_move: bool
    state_after_robot: str
    solver_received_post_human_state: bool
    robot_transition_matches_engine: bool

    def as_dict(self) -> dict[str, object]:
        return asdict(self)


def solved_perturbation_cases() -> list[DiagnosticRecord]:
    engine, solver = CubeEngine(), CubeSolver()
    records = []
    for index, human_move in enumerate(LEGAL_MOVES):
        state_after_human = engine.apply_move(SOLVED_FACELETS, human_move)
        solution = solver.solve(state_after_human)
        robot_move = solution[0]
        state_after_robot = engine.apply_move(state_after_human, robot_move)
        records.append(DiagnosticRecord(
            case_type="solved_plus_one_human_move", seed=index, scramble_length=0,
            scramble_moves=[], initial_cube_state=SOLVED_FACELETS,
            state_before_human=SOLVED_FACELETS, human_move=human_move,
            state_after_human=state_after_human, solver_input_state=state_after_human,
            solver_solution=solution, robot_selected_move=robot_move,
            robot_selection_reason="first_move_of_solver_solution_after_physical_perturbation",
            is_inverse_of_human_move=robot_move == inverse_move(human_move),
            state_after_robot=state_after_robot, solver_received_post_human_state=True,
            robot_transition_matches_engine=(
                state_after_robot == engine.apply_move(state_after_human, robot_move)
            ),
        ))
    return records


def random_scramble_cases(count: int = 100, seed: int = 20261112) -> list[DiagnosticRecord]:
    engine = CubeEngine()
    rng = random.Random(seed)
    records: list[DiagnosticRecord] = []
    for case_seed in range(count):
        length = rng.randint(15, 20)
        initial, scramble_moves = engine.scramble(case_seed, length)
        coordinator = TurnCoordinator(
            SimRobotAdapter(engine), engine=engine, collaboration_mode="free_collaboration"
        )
        state = coordinator.start(initial)
        candidates = [move for move in LEGAL_MOVES if move != state.planned_moves[0]]
        rng.shuffle(candidates)
        human_move = next(
            move for move in candidates
            if not engine.is_solved(engine.apply_move(initial, move))
        )
        coordinator.submit_human_move(human_move)
        coordinator.execute_robot_turn(plan_version=state.plan_version)
        event = next(event for event in coordinator.events if event.kind == "TURN_DIAGNOSTIC")
        detail = event.detail
        record = DiagnosticRecord(
            case_type="random_scramble_unexpected_human_move", seed=case_seed,
            scramble_length=length, scramble_moves=scramble_moves,
            initial_cube_state=str(detail["initial_cube_state"]),
            state_before_human=str(detail["state_before_human"]),
            human_move=str(detail["human_move"]),
            state_after_human=str(detail["state_after_human"]),
            solver_input_state=str(detail["solver_input_state"]),
            solver_solution=list(detail["solver_solution"]),
            robot_selected_move=str(detail["robot_selected_move"]),
            robot_selection_reason=str(detail["robot_selection_reason"]),
            is_inverse_of_human_move=bool(detail["is_inverse_of_human_move"]),
            state_after_robot=str(detail["state_after_robot"]),
            solver_received_post_human_state=(
                detail["solver_input_state"] == detail["state_after_human"]
            ),
            robot_transition_matches_engine=(
                detail["state_after_robot"] == engine.apply_move(
                    str(detail["state_after_human"]), str(detail["robot_selected_move"])
                )
            ),
        )
        records.append(record)
    return records


def summarize(records: list[DiagnosticRecord]) -> dict[str, object]:
    total = len(records)
    inverse_count = sum(record.is_inverse_of_human_move for record in records)
    return {
        "samples": total,
        "robot_first_move_is_inverse_count": inverse_count,
        "robot_first_move_is_inverse_ratio": inverse_count / total if total else 0.0,
        "solver_received_post_human_state_count": sum(
            record.solver_received_post_human_state for record in records
        ),
        "state_transition_matches_engine_count": sum(
            record.robot_transition_matches_engine for record in records
        ),
    }
