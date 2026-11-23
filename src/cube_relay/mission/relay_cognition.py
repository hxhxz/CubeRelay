"""Passive cognitive analyzers, belief conservation, flip-cost modeling, and fast/slow contracts for M5 Agent Relay."""

from __future__ import annotations

from dataclasses import dataclass, field
from itertools import permutations
import json
import os
from pathlib import Path
import threading
import time
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from cube_relay.cube.moves import CubeEngine, LEGAL_MOVES
from cube_relay.cube.solver import CubeSolver
from cube_relay.cube.state import FACE_ORDER, SOLVED_FACELETS, inverse_move
from cube_relay.cube.validation import InvalidCubeState, validate_facelets
from .dual_model import (
    FakeStructuredModelClient,
    OpenAICompatibleStructuredClient,
    StructuredCall,
    StructuredModelClient,
)

DEFAULT_FLIP_COST_PROFILE_PATH = Path("results/m5a1_calibration/flip_cost_profile.json")
_OPPOSITE_FACE = {"U": "D", "D": "U", "F": "B", "B": "F", "R": "L", "L": "R"}

# Exact 3x3 chiral corner & edge sticker indices in Kociemba 54-char order (U,R,F,D,L,B * 9).
_CORNER_TRIPLES: tuple[tuple[int, int, int], ...] = (
    (8, 9, 20),   # URF
    (6, 18, 38),  # UFL
    (0, 36, 47),  # ULB
    (2, 45, 11),  # UBR
    (29, 26, 15), # DFR
    (27, 44, 24), # DLF
    (33, 53, 42), # DBL
    (35, 17, 51), # DRB
)

_EDGE_PAIRS: tuple[tuple[int, int], ...] = (
    (7, 19), (5, 10), (1, 46), (3, 37),
    (28, 25), (32, 16), (34, 52), (30, 43),
    (23, 12), (21, 41), (48, 14), (50, 39),
)


def _build_chiral_corner_map() -> dict[tuple[str, str], str]:
    mapping: dict[tuple[str, str], str] = {}
    for triple in _CORNER_TRIPLES:
        cols = tuple(SOLVED_FACELETS[idx] for idx in triple)
        for shift in range(3):
            a, b, c = cols[shift], cols[(shift + 1) % 3], cols[(shift + 2) % 3]
            mapping[(a, b)] = c
    return mapping


_CHIRAL_CORNER_PAIR_TO_THIRD = _build_chiral_corner_map()
_STANDARD_EDGES: tuple[frozenset[str], ...] = tuple(
    frozenset((SOLVED_FACELETS[a], SOLVED_FACELETS[b])) for a, b in _EDGE_PAIRS
)


class ExecutionContractSpec(BaseModel):
    """Structured monitoring contract issued by the slow Agent loop to the 50 Hz fast loop."""

    model_config = ConfigDict(extra="forbid")

    max_target_drift_m: float = Field(default=0.015, ge=0.002, le=0.08)
    interrupt_on_human_chat_command: bool = True
    mid_turn_recovery_mode: Literal["UNWIND_TO_ZERO", "ALIGN_NEAREST_DETENT"] = "UNWIND_TO_ZERO"
    abort_on_unexpected_flip: bool = False


class StaleResponseGuard:
    """Thread-safe epoch guard preventing stale in-flight slow LLM responses from executing after preemption."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._epoch: int = 0
        self.stale_responses_discarded: int = 0
        self.last_invalidation_reason: str | None = None

    @property
    def current_epoch(self) -> int:
        with self._lock:
            return self._epoch

    def issue_epoch(self) -> int:
        with self._lock:
            return self._epoch

    def invalidate(self, reason: str = "USER_PREEMPT") -> int:
        with self._lock:
            self._epoch += 1
            self.last_invalidation_reason = str(reason)
            return self._epoch

    def accept(self, epoch: int) -> bool:
        with self._lock:
            if int(epoch) != self._epoch:
                self.stale_responses_discarded += 1
                return False
            return True

    def reset(self) -> None:
        with self._lock:
            self._epoch = 0
            self.stale_responses_discarded = 0
            self.last_invalidation_reason = None

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            return {
                "current_epoch": self._epoch,
                "stale_responses_discarded": self.stale_responses_discarded,
                "last_invalidation_reason": self.last_invalidation_reason,
            }


@dataclass(frozen=True, slots=True)
class FlipCostProfile:
    """Embodied flip & regrasp cost summary anchored to M5-A.1 empirical calibration."""

    source_path: str
    schema_version: str
    cold_0_flip_mean_s: float
    cold_1_flip_mean_s: float
    cold_2_flip_mean_s: float
    cold_mixed_3_step_mean_s: float
    empirical_0_flip_success_rate: float
    empirical_1_flip_success_rate: float
    empirical_2_flip_success_rate: float
    mean_regrasps_by_flips: dict[int, float]
    marginal_time_s_by_flips: dict[int, float]

    @classmethod
    def from_file(cls, path: str | Path = DEFAULT_FLIP_COST_PROFILE_PATH) -> "FlipCostProfile":
        p = Path(path)
        raw: dict[str, Any] = {}
        if p.exists():
            raw = json.loads(p.read_text(encoding="utf-8"))
        t0 = dict(raw.get("0_flip") or {})
        t1 = dict(raw.get("1_flip") or {})
        t2 = dict(raw.get("2_flip") or {})
        tm = dict(raw.get("mixed_3_step_sequence") or {})

        m0 = float(t0.get("mean_sim_time_s", 32.98))
        m1 = float(t1.get("mean_sim_time_s", 34.45))
        m2 = float(t2.get("mean_sim_time_s", 42.36))
        mm = float(tm.get("mean_sim_time_s", 79.91))
        rg2 = float(t2.get("mean_regrasps", 1.0))

        # Deduct one-time episode reset/pick/scan cold-start (~28.5s) and scale empirical
        # flip + lay-down regrasp penalty cleanly for in-station continuous vs desktop flip work.
        marginal_0 = 4.5
        flip_step_delta = max(8.0, round((m1 - m0) + 8.0, 2))
        regrasp_delta = max(9.5, round((m2 - m1) + 3.0 * rg2, 2))
        marginal_1 = round(marginal_0 + flip_step_delta, 2)
        marginal_2 = round(marginal_1 + regrasp_delta, 2)

        return cls(
            source_path=str(p),
            schema_version=str(raw.get("schema_version", "cuberelay_m5a1_flip_cost_profile_v1")),
            cold_0_flip_mean_s=round(m0, 3),
            cold_1_flip_mean_s=round(m1, 3),
            cold_2_flip_mean_s=round(m2, 3),
            cold_mixed_3_step_mean_s=round(mm, 3),
            empirical_0_flip_success_rate=float(t0.get("empirical_success_rate", 0.95)),
            empirical_1_flip_success_rate=float(t1.get("empirical_success_rate", 1.0)),
            empirical_2_flip_success_rate=float(t2.get("empirical_success_rate", 0.95)),
            mean_regrasps_by_flips={
                0: float(t0.get("mean_regrasps", 0.0)),
                1: float(t1.get("mean_regrasps", 0.0)),
                2: rg2,
            },
            marginal_time_s_by_flips={
                0: marginal_0,
                1: marginal_1,
                2: marginal_2,
            },
        )

    def flips_for_move(self, move: str, *, top_face: str = "U", bottom_face: str | None = None) -> int:
        face = str(move).strip()[0]
        bottom = bottom_face or _OPPOSITE_FACE.get(top_face, "D")
        if face == top_face:
            return 0
        if face == bottom:
            return 2
        return 1

    def estimate_move_cost(self, move: str, *, top_face: str = "U", bottom_face: str | None = None) -> dict[str, Any]:
        flips = self.flips_for_move(move, top_face=top_face, bottom_face=bottom_face)
        regrasps = self.mean_regrasps_by_flips.get(flips, 0.0)
        return {
            "move": move,
            "target_face": move[0],
            "flips": flips,
            "marginal_sim_time_s": self.marginal_time_s_by_flips.get(flips, 14.0),
            "regrasps_expected": regrasps,
            "tier": "LOW_0_FLIP" if flips == 0 else ("MID_1_FLIP" if flips == 1 else "HIGH_2_FLIP_REGRASP"),
        }

    def to_agent_priors(self) -> dict[str, Any]:
        return {
            "source_path": self.source_path,
            "schema_version": self.schema_version,
            "marginal_sim_time_s": dict(self.marginal_time_s_by_flips),
            "expected_regrasps": dict(self.mean_regrasps_by_flips),
            "calibrated_cold_mean_sim_time_s": {
                "0_flip": self.cold_0_flip_mean_s,
                "1_flip": self.cold_1_flip_mean_s,
                "2_flip": self.cold_2_flip_mean_s,
                "mixed_3_step_sequence": self.cold_mixed_3_step_mean_s,
            },
            "empirical_success_rate": {
                "0_flip": self.empirical_0_flip_success_rate,
                "1_flip": self.empirical_1_flip_success_rate,
                "2_flip": self.empirical_2_flip_success_rate,
            },
        }


@dataclass(frozen=True, slots=True)
class BeliefConservationResult:
    """Result of deterministic cubie conservation & prior transition inference (Zero Action Leakage)."""

    deduced_54_unique: bool
    deduced_facelets: str
    ambiguous_facelet_count: int
    ambiguous_facelet_indices: list[int]
    candidate_count: int
    occluded_face: str | None
    inferred_human_moves: list[str]
    human_deviation_detected: bool
    state_changed_since_handover: bool
    reasoning_summary_zh: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "deduced_54_unique": self.deduced_54_unique,
            "deduced_facelets": self.deduced_facelets,
            "ambiguous_facelet_count": self.ambiguous_facelet_count,
            "ambiguous_facelet_indices": list(self.ambiguous_facelet_indices),
            "candidate_count": self.candidate_count,
            "occluded_face": self.occluded_face,
            "inferred_human_moves": list(self.inferred_human_moves),
            "human_deviation_detected": self.human_deviation_detected,
            "state_changed_since_handover": self.state_changed_since_handover,
            "reasoning_summary_zh": self.reasoning_summary_zh,
        }


class BeliefConservationAnalyzer:
    """Lock occluded facelets via exact 8-corner/12-edge conservation and infer visible human transitions."""

    def __init__(self) -> None:
        self._engine = CubeEngine()

    def _enumerate_conservation_candidates(self, partial: str) -> list[str]:
        if len(partial) != 54:
            return []
        if "?" not in partial:
            try:
                validate_facelets(partial, check_solvable=True)
                return [partial]
            except InvalidCubeState:
                return []

        arr = list(partial)
        seen_centers = {arr[f * 9 + 4] for f in range(6) if arr[f * 9 + 4] != "?"}
        missing_centers = [c for c in FACE_ORDER if c not in seen_centers]
        for f in range(6):
            if arr[f * 9 + 4] == "?" and len(missing_centers) == 1:
                arr[f * 9 + 4] = missing_centers[0]

        for triple in _CORNER_TRIPLES:
            vals = [arr[i] for i in triple]
            if vals.count("?") == 1:
                q_pos = vals.index("?")
                a = vals[(q_pos + 1) % 3]
                b = vals[(q_pos + 2) % 3]
                if (a, b) in _CHIRAL_CORNER_PAIR_TO_THIRD:
                    arr[triple[q_pos]] = _CHIRAL_CORNER_PAIR_TO_THIRD[(a, b)]

        rem_edges: list[tuple[int, int]] = []
        seen_edges: list[frozenset[str]] = []
        for a, b in _EDGE_PAIRS:
            ca, cb = arr[a], arr[b]
            if ca != "?" and cb != "?":
                seen_edges.append(frozenset((ca, cb)))
            elif ca == "?" and cb == "?":
                return []
            else:
                rem_edges.append((a, b))

        unused_edges = [edge for edge in _STANDARD_EDGES if edge not in seen_edges]
        if len(unused_edges) != len(rem_edges):
            return []

        candidates: list[str] = []
        seen_set: set[str] = set()
        for perm in permutations(unused_edges):
            cand = list(arr)
            ok = True
            for (a, b), edge_pair in zip(rem_edges, perm, strict=True):
                known_col = cand[a] if cand[a] != "?" else cand[b]
                unk_slot = b if cand[a] != "?" else a
                if known_col not in edge_pair:
                    ok = False
                    break
                cand[unk_slot] = next(iter(edge_pair - {known_col}))
            if not ok:
                continue
            cand_str = "".join(cand)
            if cand_str in seen_set:
                continue
            try:
                validate_facelets(cand_str, check_solvable=True)
            except InvalidCubeState:
                continue
            seen_set.add(cand_str)
            candidates.append(cand_str)
        return candidates

    def _infer_moves_from_prior(self, prev_54: str, target_54: str) -> list[str]:
        if prev_54 == target_54:
            return []
        for m1 in LEGAL_MOVES:
            s1 = self._engine.apply_move(prev_54, m1)
            if s1 == target_54:
                return [m1]
        for m1 in LEGAL_MOVES:
            s1 = self._engine.apply_move(prev_54, m1)
            for m2 in LEGAL_MOVES:
                if m2[0] == m1[0]:
                    continue
                if self._engine.apply_move(s1, m2) == target_54:
                    return [m1, m2]
        return []

    @staticmethod
    def _matches_partial(full_54: str, partial_54: str) -> bool:
        return all(p == "?" or p == f for p, f in zip(partial_54, full_54, strict=True))

    def _infer_moves_from_partial(self, prev_54: str, partial_54: str) -> list[str]:
        if self._matches_partial(prev_54, partial_54):
            return []
        for m1 in LEGAL_MOVES:
            s1 = self._engine.apply_move(prev_54, m1)
            if self._matches_partial(s1, partial_54):
                return [m1]
        return []

    def analyze(
        self,
        observed_partial_54: str,
        *,
        previous_belief_54: str | None = None,
        last_suggested_moves: list[str] | tuple[str, ...] | None = None,
    ) -> BeliefConservationResult:
        """Analyze 5-face rapid scan against cubie conservation & robot's own prior belief (never human truth)."""
        occluded_counts = {
            FACE_ORDER[f]: observed_partial_54[f * 9 : (f + 1) * 9].count("?")
            for f in range(6)
        }
        occ_face = max(occluded_counts, key=occluded_counts.get)
        if occluded_counts[occ_face] == 0:
            occ_face = None

        candidates = self._enumerate_conservation_candidates(observed_partial_54)
        unique = len(candidates) == 1

        if candidates:
            deduced_chars: list[str] = []
            ambiguous_indices: list[int] = []
            for idx in range(54):
                vals = {c[idx] for c in candidates}
                if len(vals) == 1:
                    deduced_chars.append(next(iter(vals)))
                else:
                    deduced_chars.append("?")
                    ambiguous_indices.append(idx)
            deduced_facelets = "".join(deduced_chars)
        else:
            deduced_facelets = observed_partial_54
            ambiguous_indices = [i for i, ch in enumerate(observed_partial_54) if ch == "?"]

        inferred_moves: list[str] = []
        state_changed = bool(previous_belief_54 and previous_belief_54 != deduced_facelets)
        deviation = False

        if previous_belief_54 and len(previous_belief_54) == 54:
            if unique:
                inferred_moves = self._infer_moves_from_prior(previous_belief_54, candidates[0])
                state_changed = candidates[0] != previous_belief_54
            else:
                inferred_moves = self._infer_moves_from_partial(previous_belief_54, observed_partial_54)
                state_changed = not self._matches_partial(previous_belief_54, observed_partial_54)

            if last_suggested_moves:
                prefixes: list[tuple[str, ...]] = [
                    tuple(last_suggested_moves[:k]) for k in range(1, len(last_suggested_moves) + 1)
                ]
                expected_states = [
                    self._engine.apply_moves(previous_belief_54, pref) for pref in prefixes
                ]
                if unique:
                    if state_changed and candidates[0] not in expected_states:
                        deviation = True
                elif state_changed and not any(self._matches_partial(es, observed_partial_54) for es in expected_states):
                    deviation = True
            elif inferred_moves and not last_suggested_moves:
                # No suggested moves yet human rotated cube
                deviation = False

        if "?" not in observed_partial_54 and unique:
            summary = "已直接全视角观测 54/54 贴片，状态唯一确认。"
        elif unique:
            inf_txt = f"（视觉反推人类动作: {' '.join(inferred_moves)}）" if inferred_moves else (
                "（桌面状态与交接前一致，无新增动作）" if not state_changed else "（复杂多步后仍由块守恒唯一锁定）"
            )
            summary = (
                f"5 面桌面快瞄结合 8 角块/12 棱块色守恒唯一锁定全部 54 格（底面 {occ_face or 'D'} 9 格均已数学锁定，0 歧义）{inf_txt}，可省去 25s 翻面重扫。"
            )
        elif len(candidates) > 1:
            summary = (
                f"5 面桌面快瞄后仍存在 {len(candidates)} 个满足群论守恒的合法底面候选，"
                f"共 {len(ambiguous_indices)} 格存在真歧义（索引 {ambiguous_indices}），需权衡翻面重扫 (scan_occluded_bottom_face) 或开口询问人类。"
            )
        else:
            summary = (
                f"桌面快瞄观测存在 {len(ambiguous_indices)} 格未知且无法通过单面守恒锁定，"
                "建议执行完整主动扫描 (scan_occluded_bottom_face) 或按需唤醒 VLM 诊断。"
            )

        return BeliefConservationResult(
            deduced_54_unique=unique,
            deduced_facelets=deduced_facelets,
            ambiguous_facelet_count=len(ambiguous_indices),
            ambiguous_facelet_indices=ambiguous_indices,
            candidate_count=len(candidates),
            occluded_face=occ_face,
            inferred_human_moves=inferred_moves,
            human_deviation_detected=deviation,
            state_changed_since_handover=state_changed,
            reasoning_summary_zh=summary,
        )


def compute_candidate_solve_paths(
    current_54: str,
    *,
    top_face: str = "U",
    bottom_face: str | None = None,
    flip_profile: FlipCostProfile | None = None,
    inferred_human_moves: list[str] | tuple[str, ...] | None = None,
    state_history: list[str] | tuple[str, ...] | None = None,
) -> dict[str, Any]:
    """Read-only solver & embodied marginal cost summary for AgentPlanningProvider (never executes actions)."""
    validate_facelets(current_54, check_solvable=True)
    profile = flip_profile or FlipCostProfile.from_file()
    solver = CubeSolver()
    eng = CubeEngine()

    if current_54 == SOLVED_FACELETS:
        return {
            "is_solved": True,
            "primary_kociemba_solution": [],
            "remaining_optimal_steps": 0,
            "alternative_non_undo_solution": None,
            "undo_conflict_risk": False,
            "undo_target_move": None,
            "primary_move_costs": [],
            "alternative_move_costs": [],
            "next_high_cost_2flip_move": None,
        }

    primary = solver.solve(current_54)
    inferred = list(inferred_human_moves or ())
    history_set = set(state_history or ())

    inv_last = inverse_move(inferred[-1]) if inferred and inferred[-1] in LEGAL_MOVES else None
    first_next_state = eng.apply_move(current_54, primary[0])
    repeats_history = first_next_state in history_set
    undoes_human = bool(inv_last is not None and primary[0] == inv_last)
    undo_conflict_risk = bool(undoes_human or repeats_history)

    alternative: list[str] | None = None
    if undo_conflict_risk:
        forbidden_face = inv_last[0] if inv_last else primary[0][0]
        # 1-move lookahead avoiding direct undo face & already-visited ping-pong states
        best_alt: list[str] | None = None
        for m1 in LEGAL_MOVES:
            if m1[0] == forbidden_face:
                continue
            s1 = eng.apply_move(current_54, m1)
            if s1 in history_set:
                continue
            sub = solver.solve(s1)
            if sub and sub[0][0] == m1[0]:
                continue
            cand = [m1, *sub]
            if best_alt is None or len(cand) < len(best_alt):
                best_alt = cand
                if len(best_alt) <= len(primary) + 1:
                    break
        alternative = best_alt

    primary_costs = [
        profile.estimate_move_cost(mv, top_face=top_face, bottom_face=bottom_face)
        for mv in primary[:6]
    ]
    alt_costs = (
        [
            profile.estimate_move_cost(mv, top_face=top_face, bottom_face=bottom_face)
            for mv in alternative[:6]
        ]
        if alternative
        else []
    )
    high_2flip = next((item["move"] for item in primary_costs if item["flips"] == 2), None)

    return {
        "is_solved": False,
        "primary_kociemba_solution": primary,
        "remaining_optimal_steps": len(primary),
        "alternative_non_undo_solution": alternative,
        "undo_conflict_risk": undo_conflict_risk,
        "undo_target_move": inv_last if undoes_human else (primary[0] if repeats_history else None),
        "primary_move_costs": primary_costs,
        "alternative_move_costs": alt_costs,
        "next_high_cost_2flip_move": high_2flip,
    }


SpeechActType = Literal[
    "EMERGENCY_STOP",
    "PAUSE_AND_HANDOVER",
    "YIELD_TURN_TO_ROBOT",
    "RETAIN_HUMAN_TURN",
    "UPDATE_PREFERENCE_ONLY",
    "ANSWER_CLARIFICATION",
    "QUESTION_OR_COMMENT",
]

DeviationIntentType = Literal["ACCIDENTAL_UNDO", "INTENTIONAL_KEEP", "NONE"]

# Minimal <2ms reflex channel for pure single-word hardware e-stop commands ONLY.
REFLEX_ESTOP_EXACT_TOKENS: frozenset[str] = frozenset({"停", "急停", "stop", "halt"})


class _HumanUtteranceSemanticsLLMOutput(BaseModel):
    """Strict structured JSON schema returned by the LLM semantic router."""

    model_config = ConfigDict(extra="forbid")

    speech_act: SpeechActType
    requires_immediate_motion_interrupt: bool
    should_wake_robot_from_human_turn: bool
    persistent_constraints_to_add: list[str] = Field(default_factory=list)
    constraints_to_clear: list[str] = Field(default_factory=list)
    deviation_intent: DeviationIntentType = "NONE"
    rationale_zh: str = ""
    confidence: float = Field(default=0.85, ge=0.0, le=1.0)


class HumanUtteranceSemantics(_HumanUtteranceSemanticsLLMOutput):
    """Interpreted HRI utterance semantics enriched with provenance and latency metadata."""

    provenance: str = "LLM_ROUTER"
    latency_ms: float = 0.0
    model_name: str | None = None
    provider_name: str | None = None
    error_code: str | None = None


class HRIDialogueInterpreter:
    """Real LLM-backed semantic intent router for human-robot Rubik's cube relay dialogue.

    Replaces hardcoded keyword/substring matching with structured LLM understanding while
    preserving a <2ms zero-latency hardware e-stop reflex for exact single-word halt tokens.
    """

    def __init__(self, client: StructuredModelClient | None = None) -> None:
        if client is not None:
            self.client: StructuredModelClient = client
        else:
            chosen = OpenAICompatibleStructuredClient("PERCEPTION")
            if not chosen.is_configured():
                chosen = OpenAICompatibleStructuredClient("HRI")
            if not chosen.is_configured():
                chosen = OpenAICompatibleStructuredClient("AGENT")
                chosen.model = os.getenv("CUBERELAY_PERCEPTION_MODEL", "").strip() or "gemini-3.5-flash-lite"
            chosen.model = os.getenv("CUBERELAY_ROUTER_MODEL", "").strip() or chosen.model
            chosen.thinking_budget = 0
            chosen.reasoning_effort = "none"
            chosen.token_budget = 256
            chosen.temperature = 0.0
            chosen.timeout_seconds = min(float(chosen.timeout_seconds), 20.0)
            self.client = chosen
        self.latest_trace: StructuredCall | None = None

    @staticmethod
    def is_reflex_estop(text: str) -> bool:
        return str(text or "").strip().lower() in REFLEX_ESTOP_EXACT_TOKENS

    def _build_prompt(
        self,
        *,
        utterance: str,
        relay_phase: str,
        robot_running: bool,
        clarification_pending: bool,
        current_action: str | None,
        recent_dialog: list[dict[str, Any]],
        active_constraints: list[str],
    ) -> str:
        compact_history = [
            {
                "role": str(item.get("role", "")),
                "text": str(item.get("text", "")),
                **({"topic": item["topic"]} if item.get("topic") else {}),
            }
            for item in recent_dialog[-3:]
        ]
        schema = _HumanUtteranceSemanticsLLMOutput.model_json_schema()
        schema["properties"].pop("rationale_zh")
        payload = {
            "utterance": utterance,
            "state": {
                "relay_phase": relay_phase,
                "robot_running": bool(robot_running),
                "clarification_pending": bool(clarification_pending),
                "current_action": current_action,
                "active_constraints": list(active_constraints),
                "recent_dialog_last_3": compact_history,
            },
            "rules": [
                "Understand true semantics, negation, and colloquial Chinese/English expressions—never rely on naive keyword presence.",
                "Negation / retain turn: e.g. '先别继续解，让我自己先转两步看看' means human wants to KEEP their turn -> speech_act='RETAIN_HUMAN_TURN', should_wake_robot_from_human_turn=false.",
                "Colloquial handover: e.g. '这几个块太绕了我搞不定，剩下的看你的啦', '交给你吧', '你继续' -> speech_act='YIELD_TURN_TO_ROBOT', should_wake_robot_from_human_turn=true.",
                "Mid-motion preference/praise/comment: when robot_running=true, if the human praises, comments, asks a question, or states a FUTURE turn division preference (e.g. '干得漂亮，待会儿底面 D 动作留给我拧就行'), set speech_act='UPDATE_PREFERENCE_ONLY' (or 'QUESTION_OR_COMMENT') and requires_immediate_motion_interrupt=false! NEVER interrupt robot motion unless the human explicitly asks to stop/halt/pause the current motion right now or cancel/change the currently executing move.",
                "Compound interrupt + persistent constraint: e.g. '停一下，后面底面 D 全归你拧' -> speech_act='PAUSE_AND_HANDOVER', requires_immediate_motion_interrupt=true, should_wake_robot_from_human_turn=false, AND extract ONLY the persistent collaboration preference into persistent_constraints_to_add (e.g. ['后续底面 D 动作全部由机器人执行']) WITHOUT transient pause words like '停一下'.",
                "Clarification / deviation: if clarification_pending=true and the utterance answers the robot's question, set speech_act='ANSWER_CLARIFICATION', should_wake_robot_from_human_turn=true. Set deviation_intent='ACCIDENTAL_UNDO' if human says they slipped/want undo, 'INTENTIONAL_KEEP' if they intentionally changed route / want to keep their move, else 'NONE'.",
                "Constraint removal: if the human revokes a prior constraint in active_constraints, include the exact matching string(s) from active_constraints in constraints_to_clear.",
            ],
            "response_schema": schema,
        }
        return (
            "You are CubeRelay's real-time HRI semantic intent router for human-robot collaborative Rubik's cube solving. "
            "Analyze the human utterance in context and output ONLY strictly valid JSON matching response_schema.\n"
            + json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
        )

    def _offline_fallback(
        self,
        *,
        utterance: str,
        clarification_pending: bool,
        latency_ms: float,
        error_code: str | None = None,
    ) -> HumanUtteranceSemantics:
        return HumanUtteranceSemantics(
            speech_act="ANSWER_CLARIFICATION" if clarification_pending else "QUESTION_OR_COMMENT",
            requires_immediate_motion_interrupt=False,
            should_wake_robot_from_human_turn=bool(clarification_pending),
            persistent_constraints_to_add=[utterance] if utterance else [],
            constraints_to_clear=[],
            deviation_intent="NONE",
            rationale_zh=(
                f"离线降级模式（{error_code or 'API_UNCONFIGURED'}），未执行语义路由，仅保守记录原始指令且不误触发急停。"
            ),
            confidence=0.0,
            provenance="OFFLINE_FALLBACK",
            latency_ms=round(latency_ms, 3),
            model_name=getattr(self.client, "model", None) or None,
            provider_name=getattr(self.client, "provider_name", None) or None,
            error_code=error_code or "CLIENT_UNCONFIGURED",
        )

    def interpret(
        self,
        utterance: str,
        *,
        relay_phase: str = "IDLE",
        robot_running: bool = False,
        clarification_pending: bool = False,
        current_action: str | None = None,
        recent_dialog: list[dict[str, Any]] | None = None,
        active_constraints: list[str] | None = None,
    ) -> HumanUtteranceSemantics:
        started = time.perf_counter()
        clean = str(utterance or "").strip()
        if not clean:
            raise ValueError("自然语言指令不能为空")

        # <2ms zero-latency reflex channel for pure single-word hardware e-stop ONLY
        if self.is_reflex_estop(clean):
            elapsed_ms = (time.perf_counter() - started) * 1000.0
            self.latest_trace = None
            return HumanUtteranceSemantics(
                speech_act="EMERGENCY_STOP",
                requires_immediate_motion_interrupt=True,
                should_wake_robot_from_human_turn=False,
                persistent_constraints_to_add=[],
                constraints_to_clear=[],
                deviation_intent="NONE",
                rationale_zh="命中纯单字硬件急停反射通道（<2ms），立即刹停并安全停泊。",
                confidence=1.0,
                provenance="REFLEX_ESTOP",
                latency_ms=round(elapsed_ms, 3),
                model_name="reflex_estop",
                provider_name="hardware_reflex",
            )

        if not self.client.is_configured():
            self.latest_trace = None
            return self._offline_fallback(
                utterance=clean,
                clarification_pending=clarification_pending,
                latency_ms=(time.perf_counter() - started) * 1000.0,
                error_code="CLIENT_UNCONFIGURED",
            )

        prompt = self._build_prompt(
            utterance=clean,
            relay_phase=relay_phase,
            robot_running=robot_running,
            clarification_pending=clarification_pending,
            current_action=current_action,
            recent_dialog=list(recent_dialog or []),
            active_constraints=list(active_constraints or []),
        )
        parsed, trace = self.client.generate(prompt, _HumanUtteranceSemanticsLLMOutput, None)
        self.latest_trace = trace
        if parsed is None:
            return self._offline_fallback(
                utterance=clean,
                clarification_pending=clarification_pending,
                latency_ms=float(trace.latency_ms if trace else (time.perf_counter() - started) * 1000.0),
                error_code=(trace.error_code if trace else "HRI_ROUTER_FAILED"),
            )

        is_fake = isinstance(self.client, FakeStructuredModelClient) or "fake" in str(
            getattr(self.client, "provider_name", "")
        ).lower()
        provenance = "FAKE_LLM_ROUTER" if is_fake else "LIVE_LLM_ROUTER"
        clean_add = [str(c).strip() for c in parsed.persistent_constraints_to_add if str(c).strip()]
        clean_clear = [str(c).strip() for c in parsed.constraints_to_clear if str(c).strip()]
        return HumanUtteranceSemantics(
            speech_act=parsed.speech_act,
            requires_immediate_motion_interrupt=bool(parsed.requires_immediate_motion_interrupt),
            should_wake_robot_from_human_turn=bool(parsed.should_wake_robot_from_human_turn),
            persistent_constraints_to_add=clean_add,
            constraints_to_clear=clean_clear,
            deviation_intent=parsed.deviation_intent,
            rationale_zh=parsed.rationale_zh.strip() or f"语义意图识别为 {parsed.speech_act}",
            confidence=float(parsed.confidence),
            provenance=provenance,
            latency_ms=round(float(trace.latency_ms), 2),
            model_name=getattr(self.client, "model", None) or None,
            provider_name=getattr(self.client, "provider_name", None) or None,
        )
