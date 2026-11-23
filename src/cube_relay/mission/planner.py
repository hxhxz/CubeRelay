"""Deterministic, Single-Model Baseline, and Decoupled Dual-Model Task Planners implementing DecisionPolicy."""

from __future__ import annotations

from dataclasses import dataclass, field, replace
import json
from typing import Any, Protocol
import uuid

from pydantic import BaseModel, ConfigDict, Field

from cube_relay.cube.state import LEGAL_MOVES

from .events import now_wall_time
from .models import (
    AgentObservation,
    MissionState,
    MissionType,
    ObservationReference,
    PlanState,
    PlanStep,
    PlanStepStatus,
    PlannerMode,
)
from .skill_registry import SkillRegistry
from .vlm_client import FakeGeminiVLMClient, VLMCallResult, _EnvLoadedGeminiClient
from .dual_model import DualModelDecisionClient

MISSION_SPECS: dict[MissionType, dict[str, str]] = {
    MissionType.INSPECT_CUBE: {
        "title": "六面扫描",
        "user_goal": "主动感知并扫描魔方全部六个面，融合 54 格贴片状态并校验合法性（不执行物理转面）。",
        "success_criteria": "54 格贴片观测完整（unknown=0）、零冲突且通过拓扑可解性校验；严禁调用物理转层动作。",
    },
    MissionType.VERIFY_PHYSICAL_U_TURN: {
        "title": "U 层物理转动验证",
        "user_goal": "验证机器人能否将魔方搬运至旋转工位，并通过实体接触驱动 U 层顺时针转动 90°（M3-B 基线）。",
        "success_criteria": "实测层转角误差 < 0.03 rad、上下双侧夹爪接触连续且转后 21 个受影响贴片视觉复核一致。",
    },
    MissionType.SOLVE_CUBE: {
        "title": "魔方完整求解",
        "user_goal": "获取当前魔方状态、计算 Kociemba 求解序列，并严格核查物理执行能力边界。",
        "success_criteria": "完成状态合法性校验与符号求解；若序列包含当前未建模物理转层（如 R/F/L/B/D/U'/U2），明确触发 CAPABILITY_BLOCKED。",
    },
    MissionType.RELAY_SOLVE_CUBE: {
        "title": "Agent 人机接力协同复原",
        "user_goal": "由 Gemini Agent 自主权衡 1s 桌面快瞄守恒推导 vs 25s 翻底面扫描、翻面边际物理代价与人类自然语言约束，联合人类物理完成 100% 复原。",
        "success_criteria": "经独立全六面视觉扫描确认 54/54 完全复原（SOLVED_FACELETS）、0 unknown、0 conflict，且严格满足零贴片改色与零动作/位姿真值泄漏。",
    },
}


@dataclass(frozen=True, slots=True)
class SelectedAction:
    """Output of a Planner / VLM decision step, decoupled from Skill execution."""

    decision_kind: str  # EXECUTE_STEP | REQUEST_REPLAN | BLOCK_CAPABILITY | COMPLETE_MISSION | FAIL_MISSION
    step_id: str | None
    skill_id: str | None
    parameters: dict[str, Any]
    rationale_summary: str
    input_reference: str | None = None
    blocked_move: str | None = None
    blocked_moves: tuple[str, ...] = ()
    blocked_reason: str | None = None
    expected_information_gain: str | None = None
    confidence: float | None = None
    validation_result: str = "PASSED"
    model_latency_ms: float | None = None
    token_usage: dict[str, Any] | None = None
    raw_vlm_action: str | None = None
    action_candidates: tuple[str, ...] = ()
    failure_code: str | None = None
    fallback_used: bool = False
    evidence_references: tuple[str, ...] = ()
    need_replan: bool = False
    decision_id: str | None = field(default_factory=lambda: f"dec-{uuid.uuid4().hex[:12]}")
    evidence_bundle_id: str | None = None
    request_id: str | None = None
    prompt_sha256: str | None = None
    perception_provenance: dict[str, Any] = field(default_factory=dict)
    evidence_conflicts: tuple[str, ...] = ()
    evidence_validity: dict[str, Any] = field(default_factory=dict)
    semantic_provided_to_agent: bool | None = None


class VLMInspectionLimits(BaseModel):
    """Deterministic safety & budget caps enforced by execution layer (never trusted to VLM)."""

    model_config = ConfigDict(extra="forbid")

    max_decision_rounds: int = Field(default=16, ge=1)
    max_observe_calls: int = Field(default=8, ge=1)
    max_reorient_calls: int = Field(default=5, ge=1)
    max_sim_time_sec: float = Field(default=150.0, gt=0.0)
    max_vlm_calls: int = Field(default=16, ge=1)
    allow_deterministic_fallback: bool = False
    allow_cv_only_on_vlm_failure: bool = False


class DecisionPolicy(Protocol):
    """Pluggable policy interface allowing DeterministicMissionPlanner or Gemini VLM Agent."""

    name: str
    mode: PlannerMode
    llm_connected: bool
    llm_model: str | None

    def status_label(self) -> str: ...

    def create_plan(
        self,
        mission: MissionState,
        registry: SkillRegistry,
        *,
        plan_id: str,
    ) -> PlanState: ...

    def select_next_action(
        self,
        mission: MissionState,
        plan: PlanState,
        registry: SkillRegistry,
        scene_state: dict[str, Any],
        latest_observation: ObservationReference | None,
        *,
        agent_observation: AgentObservation | None = None,
    ) -> SelectedAction: ...


class DeterministicMissionPlanner:
    """Auditable deterministic task orchestrator decoupled from physical Skills."""

    name = "DeterministicMissionPlanner"
    mode = PlannerMode.DETERMINISTIC_PLANNER
    llm_connected = False
    llm_model = None

    def status_label(self) -> str:
        return "当前由确定性任务规划器执行，LLM Agent 尚未接入"

    def create_plan(
        self,
        mission: MissionState,
        registry: SkillRegistry,
        *,
        plan_id: str,
    ) -> PlanState:
        now = now_wall_time()
        if mission.mission_type == MissionType.INSPECT_CUBE:
            blueprint = [
                ("observe_workspace", "工作站观察与定位", {"camera_name": "overhead"}),
                ("active_six_face_scan", "六面主动扫描", {"mode": "sequential"}),
                ("validate_cube_state", "54 格合法性校验", {}),
            ]
            rationale = (
                "任务目标为六面扫描（INSPECT_CUBE）：仅规划感知、主动多视角扫描与合法性校验 3 个阶段，"
                "不生成任何物理转面步骤。"
            )
        elif mission.mission_type == MissionType.VERIFY_PHYSICAL_U_TURN:
            turn_skill = "execute_physical_face_turn" if registry.physical_full_cube else "execute_physical_u_turn"
            blueprint = [
                ("observe_workspace", "工作站观察与定位", {"camera_name": "overhead"}),
                ("active_six_face_scan", "六面主动扫描", {"mode": "sequential"}),
                ("validate_cube_state", "54 格合法性校验", {}),
                ("compute_symbolic_plan", "计算 U 转动符号期望", {"target_mode": "single_u_expectation"}),
                (turn_skill, "接触驱动 U 层物理转动", {"move": "U"}),
                ("verify_post_turn_state", "转后独立相机视觉复核", {}),
            ]
            rationale = (
                "任务目标为 U 层物理转动验证（VERIFY_PHYSICAL_U_TURN）：规划扫描、校验、U 期望计算、"
                "接触式 U 层转动与转后独立相机复核 6 个阶段。"
            )
        elif mission.mission_type == MissionType.RELAY_SOLVE_CUBE:
            blueprint = [
                ("observe_workspace", "工作站观察与定位", {"camera_name": "overhead"}),
                ("scan_occluded_bottom_face", "完整六面扫描建信", {}),
            ]
            rationale = (
                "任务目标为 Agent 全自主人机接力复原（RELAY_SOLVE_CUBE）："
                "初始占位预览包含定位与建信，运行中将由 Gemini Agent 完全自主选择"
                "桌面快瞄推导、抓起翻扫、按需唤醒 VLM、契约化物理转面、桌面交接或澄清询问。"
            )
        else:  # MissionType.SOLVE_CUBE
            blueprint = [
                ("observe_workspace", "工作站观察与定位", {"camera_name": "overhead"}),
                ("active_six_face_scan", "六面主动扫描", {"mode": "sequential"}),
                ("validate_cube_state", "54 格合法性校验", {}),
                ("compute_symbolic_plan", "Kociemba 符号求解", {"target_mode": "solve"}),
                ("check_physical_capability", "物理能力边界核查", {}),
            ]
            rationale = (
                "任务目标为魔方完整求解（SOLVE_CUBE）：先完成观察、校验与符号求解，"
                "再逐动作检查物理执行能力；发现未支持转层时将阻断执行并报告 CAPABILITY_BLOCKED。"
            )

        steps: list[PlanStep] = []
        for idx, (skill_id, title, params) in enumerate(blueprint, start=1):
            desc = registry.get(skill_id)
            steps.append(
                PlanStep(
                    step_id=f"{plan_id}-s{idx}",
                    index=idx,
                    title=title,
                    skill_id=skill_id,
                    description=desc.description if desc else skill_id,
                    status=PlanStepStatus.PENDING,
                    implemented=bool(desc.implemented) if desc else False,
                    parameters=dict(params),
                )
            )
        return PlanState(
            plan_id=plan_id,
            mission_id=mission.mission_id,
            mission_type=mission.mission_type,
            planner_name=self.name,
            planner_mode=self.mode,
            created_at=now,
            updated_at=now,
            current_step_id=steps[0].step_id if steps else None,
            steps=steps,
            rationale_summary=rationale,
        )

    def select_next_action(
        self,
        mission: MissionState,
        plan: PlanState,
        registry: SkillRegistry,
        scene_state: dict[str, Any],
        latest_observation: ObservationReference | None,
        *,
        agent_observation: AgentObservation | None = None,
    ) -> SelectedAction:
        obs_ref = latest_observation.observation_id if latest_observation else None
        pending = [step for step in plan.steps if step.status == PlanStepStatus.PENDING]
        if not pending:
            return SelectedAction(
                decision_kind="COMPLETE_MISSION",
                step_id=None,
                skill_id=None,
                parameters={},
                rationale_summary="当前计划所有步骤均已验证完成，任务达到成功标准。",
                input_reference=obs_ref,
            )

        next_step = pending[0]
        param_ok, param_err = registry.validate_parameters(next_step.skill_id, next_step.parameters)
        if not param_ok:
            return SelectedAction(
                decision_kind="BLOCK_CAPABILITY",
                step_id=next_step.step_id,
                skill_id=next_step.skill_id,
                parameters=next_step.parameters,
                rationale_summary=f"参数或能力校验失败：{param_err}",
                input_reference=obs_ref,
                blocked_reason=param_err,
            )

        pre_ok, missing = registry.check_preconditions(next_step.skill_id, scene_state)
        if not pre_ok:
            reason = f"Skill [{next_step.skill_id}] 缺少前置条件：{', '.join(missing)}"
            return SelectedAction(
                decision_kind="BLOCK_CAPABILITY",
                step_id=next_step.step_id,
                skill_id=next_step.skill_id,
                parameters=next_step.parameters,
                rationale_summary=reason,
                input_reference=obs_ref,
                blocked_reason=reason,
            )

        # Extra physical boundary check before executing physical U or full-cube face turn
        if next_step.skill_id in {"execute_physical_u_turn", "execute_physical_face_turn"}:
            move = str(next_step.parameters.get("move", "U"))
            cap = registry.can_execute_physical_move(move, scene_state)
            if not cap.supported:
                return SelectedAction(
                    decision_kind="BLOCK_CAPABILITY",
                    step_id=next_step.step_id,
                    skill_id=next_step.skill_id,
                    parameters=next_step.parameters,
                    rationale_summary=cap.unsupported_reason or "物理能力校验未通过",
                    input_reference=obs_ref,
                    blocked_move=move,
                    blocked_moves=(move,),
                    blocked_reason=cap.unsupported_reason,
                )

        # Build explicit rationale grounded in real state & observation
        if next_step.skill_id == "observe_workspace":
            rationale = "工作站尚未获取当前相机帧与魔方定位信息，因此首先执行顶部 RGB-D 观测与三维定位。"
        elif next_step.skill_id == "active_six_face_scan":
            center_txt = (
                f"定位中心 {tuple(round(v, 3) for v in latest_observation.cube_center_world_m)}"
                if latest_observation and latest_observation.cube_center_world_m
                else "已完成工作站观测"
            )
            rationale = f"{center_txt}，当前未知贴片仍为 {latest_observation.unknown_count if latest_observation else 54}/54，选择执行六面主动扫描。"
        elif next_step.skill_id == "validate_cube_state":
            obs_count = latest_observation.observed_count if latest_observation else 0
            rationale = f"扫描后已采集 {obs_count}/54 贴片，选择执行独立合法性与 Kociemba 群论校验以确认状态完整可信。"
        elif next_step.skill_id == "compute_symbolic_plan":
            if mission.mission_type == MissionType.VERIFY_PHYSICAL_U_TURN:
                rationale = "魔方 54 格状态已校验合法，基于实测状态计算单步 U 顺时针旋转后的符号期望用于后续视觉复核（不修改物理场景）。"
            else:
                rationale = "魔方 54 格状态已校验合法，调用 Kociemba 符号求解器生成完整还原动作序列，供后续物理能力逐项核查。"
        elif next_step.skill_id == "check_physical_capability":
            sol = scene_state.get("symbolic_solution") or []
            rationale = (
                f"符号求解生成 {len(sol)} 步动作序列 {sol[:6]}{'...' if len(sol) > 6 else ''}，"
                "逐动作对照 SkillRegistry 核查 MuJoCo 当前物理模型是否具备执行能力。"
            )
        elif next_step.skill_id == "execute_physical_u_turn":
            rationale = (
                "能力校验确认：当前场景已启用 physical_u 接触模型、已完成 54 格扫描且 U 旋转工位可用，"
                "选择调用 ContactUTurn 执行真实接触式 U 层顺时针 +90° 转动。"
            )
        elif next_step.skill_id == "execute_physical_face_turn":
            mv = str(next_step.parameters.get("move", "U"))
            est_flips = registry.estimate_move_flips(mv, scene_state)
            rationale = (
                f"能力校验确认：26-cubie 全六面物理模型已就绪，执行 {mv} 物理转面"
                f"（预计翻面 {est_flips} 次后由单顶层夹具纯接触驱动）。"
            )
        elif next_step.skill_id == "verify_post_turn_state":
            rationale = "物理 U 层转角与接触记录已达标，机械臂与夹具退避后执行独立相机复核，验证受影响 21 格贴片是否与期望一致。"
        else:
            rationale = f"按当前计划选择执行步骤 {next_step.index}: {next_step.title} ({next_step.skill_id})。"

        return SelectedAction(
            decision_kind="EXECUTE_STEP",
            step_id=next_step.step_id,
            skill_id=next_step.skill_id,
            parameters=dict(next_step.parameters),
            rationale_summary=rationale,
            input_reference=obs_ref,
        )


_HIGH_LEVEL_PROTOCOL_ACTIONS = (
    "OBSERVE",
    "REORIENT",
    "REGRASP",
    "CONTINUE_TASK",
    "FINISH",
    "SAFE_STOP",
    "CAPABILITY_BLOCKED",
    "REQUEST_REPLAN",
    "REQUEST_MORE_INFORMATION",
    "STOP",
)

_MINIMAL_ABLATION_SKILLS = (
    "observe_visible_faces",
    "regrasp_cube",
    "reorient_cube",
    "finish_inspection",
)


class _SafetyGatedPolicyBase:
    """Shared deterministic prompt-context & SkillRegistry Safety Gate for LLM/VLM policies.

    Both the isolated single-model baseline (`GeminiMissionPlanner`) and the decoupled
    dual-model mainline (`LLMAgentDecisionPolicy`) inherit this deterministic gate as
    sibling peers rather than having M4-B subclass M4-A.
    """

    name = "_SafetyGatedPolicyBase"
    mode = PlannerMode.LLM_AGENT
    architecture_role = "SHARED_GATE_BASE"

    def _init_shared_state(
        self,
        *,
        limits: VLMInspectionLimits | None = None,
        context_mode: str = "vision_plus_structured_state",
        replacement_image_data_url: str | None = None,
        guide_mode: str = "GUIDE_FULL",
    ) -> None:
        if guide_mode not in {"GUIDE_FULL", "GUIDE_MINIMAL"}:
            raise ValueError(f"Unsupported guide_mode {guide_mode!r}; expected GUIDE_FULL or GUIDE_MINIMAL")
        self.limits = limits or VLMInspectionLimits()
        self.context_mode = context_mode
        self.replacement_image_data_url = replacement_image_data_url
        self.guide_mode = guide_mode
        self.call_traces: list[VLMCallResult] = []
        self._step_counter = 0

    def _prompt_header_instruction(self) -> str:
        return (
            "You are CubeRelay's task-level planning policy. Choose exactly one next action based on "
            "observable state and policy evidence. Never fabricate stickers, poses, or bypass preconditions. "
            "Output strictly valid JSON matching response_schema.\n"
        )

    def _plan_rationale_summary(self) -> str:
        return f"由 {self.name} ({getattr(self, 'llm_model', None) or 'unconfigured'}) 决定动作边界。"

    def create_plan(
        self,
        mission: MissionState,
        registry: SkillRegistry,
        *,
        plan_id: str,
    ) -> PlanState:
        now = now_wall_time()
        self._step_counter = 0
        return PlanState(
            plan_id=plan_id,
            mission_id=mission.mission_id,
            mission_type=mission.mission_type,
            planner_name=self.name,
            planner_mode=self.mode,
            created_at=now,
            updated_at=now,
            current_step_id=None,
            steps=[],
            rationale_summary=self._plan_rationale_summary(),
        )

    def _allowed_skill_ids(self, mission: MissionState, registry: SkillRegistry) -> list[str]:
        if self.context_mode in {"vision_only_minimal", "no_image", "replaced_image"}:
            return [sid for sid in _MINIMAL_ABLATION_SKILLS if registry.get(sid) is not None]
        if mission.mission_type == MissionType.RELAY_SOLVE_CUBE and self.guide_mode == "GUIDE_MINIMAL":
            relay_skills = (
                "observe_workspace",
                "observe_tabletop_rapid",
                "scan_occluded_bottom_face",
                "request_vlm_scene_semantics",
                "commit_physical_moves",
                "recover_preempted_turn_slice",
                "handover_to_human",
                "ask_human_clarification",
                "verify_solved_cube_independent",
            )
            return [
                sid
                for sid in relay_skills
                if (desc := registry.get(sid)) is not None and desc.implemented
            ]
        allowed: list[str] = []
        for desc in registry.list_skills():
            # Mode B: exclude composite black-box active_six_face_scan so VLM drives granular steps.
            if desc.skill_id == "active_six_face_scan":
                continue
            if not desc.implemented:
                continue
            if mission.mission_type == MissionType.INSPECT_CUBE and desc.skill_id in {
                "compute_symbolic_plan",
                "check_physical_capability",
                "execute_physical_u_turn",
                "execute_physical_face_turn",
                "recover_preempted_turn_slice",
                "verify_post_turn_state",
            }:
                continue
            if mission.mission_type == MissionType.VERIFY_PHYSICAL_U_TURN and desc.skill_id in {
                "check_physical_capability",
                "recover_preempted_turn_slice",
            }:
                continue
            allowed.append(desc.skill_id)
        return allowed

    def _build_prompt(
        self,
        mission: MissionState,
        registry: SkillRegistry,
        scene_state: dict[str, Any],
        agent_observation: AgentObservation,
        allowed_skill_ids: list[str],
    ) -> str:
        if self.context_mode in {"vision_only_minimal", "no_image", "replaced_image"}:
            # Strict information-leakage prevention: omit held/released flags, missing facelets, and skill results.
            candidates = [
                {
                    "action": sid,
                    "description": registry.get(sid).description if registry.get(sid) else sid,
                    "parameters": registry.get(sid).supported_parameters if registry.get(sid) else {},
                }
                for sid in allowed_skill_ids
            ]
            minimal_payload = {
                "mission_type": mission.mission_type.value,
                "task": (
                    "Inspect the current camera image carefully. Decide the single best next action to "
                    "continue inspecting the Rubik's cube without leaking or guessing hidden stickers. "
                    "Rules based purely on what you visually observe in the camera frame: "
                    "(1) If you see the cube sitting released on the table with the gripper retracted/away and not holding it, choose 'regrasp_cube' so the robot can pick it up and flip it to expose the bottom face. "
                    "(2) If you see the cube held between the gripper fingers in the air, choose 'reorient_cube' with {\"axis\":\"pitch\",\"degrees\":-90} to rotate it and reveal the occluded face. "
                    "(3) Only choose 'observe_visible_faces' if you need an initial or refreshed face reading, or 'finish_inspection' if all 6 faces are already fully observed."
                ),
                "allowed_actions": [*allowed_skill_ids, "REQUEST_MORE_INFORMATION", "STOP"],
                "action_descriptions": candidates,
                "response_schema": {
                    "action": "one string from allowed_actions",
                    "parameters": "dict (e.g. {\"axis\":\"pitch\",\"degrees\":-90} for reorient_cube, else {})",
                    "reason_summary": "concise factual explanation grounded in visual evidence",
                    "expected_information_gain": "what new information this step yields",
                    "confidence": "float in [0.0, 1.0]",
                },
            }
            return (
                "You are CubeRelay's embodied multimodal VLM planner. "
                "Output strictly valid JSON matching response_schema.\n"
                + json.dumps(minimal_payload, ensure_ascii=False, separators=(",", ":"))
            )

        # vision_plus_structured_state mode: structured observation & exact preconditions without ground truth.
        skill_specs: list[dict[str, Any]] = []
        for sid in allowed_skill_ids:
            desc = registry.get(sid)
            if desc is None:
                continue
            supported_parameters = dict(desc.supported_parameters)
            if sid == "reorient_cube" and not scene_state.get("all_54_facelets_observed", False):
                # The independently accepted inspection maneuver is the same pitch -90 path used
                # by ContinuousActiveInspector.  Yaw remains registered for general manipulation,
                # but must not be advertised as a safe way to expose the final hidden face.
                supported_parameters = {
                    "axis": "Literal['pitch']",
                    "degrees": "Literal[-90]",
                }
            pre_ok, missing = registry.check_preconditions(sid, scene_state)
            skill_specs.append({
                "skill_id": sid,
                "description": desc.description,
                "supported_parameters": supported_parameters,
                "preconditions_met": pre_ok,
                "missing_preconditions": missing,
            })

        face_names = ("U", "R", "F", "D", "L", "B")
        unknown_by_face = {face: 0 for face in face_names}
        for idx in agent_observation.unknown_facelet_indices:
            if 0 <= idx < 54:
                unknown_by_face[face_names[idx // 9]] += 1

        observable_state = {
            "cube_localized": bool(scene_state.get("cube_localized", False)),
            "cube_released_on_table": bool(scene_state.get("cube_released_on_table", False)),
            "cube_held_in_gripper": bool(scene_state.get("cube_held_in_gripper", False)),
            "scan_attempted": bool(scene_state.get("scan_attempted", False)),
            "observed_count": agent_observation.observed_count,
            "unknown_count": len(agent_observation.unknown_facelet_indices),
            "unknown_facelet_indices": list(agent_observation.unknown_facelet_indices),
            "unknown_by_face": unknown_by_face,
            "conflict_count": len(agent_observation.observation_conflicts),
            "observation_conflicts": list(agent_observation.observation_conflicts),
            "all_54_facelets_observed": bool(scene_state.get("all_54_facelets_observed", False)),
            "finish_inspection_done": bool(scene_state.get("finish_inspection_done", False)),
            "cube_state_validated": bool(scene_state.get("cube_state_validated", False)),
            "symbolic_plan_available": bool(scene_state.get("symbolic_plan_available", False)),
            "symbolic_solution": list(scene_state.get("symbolic_solution") or []),
            "capability_checked": bool(scene_state.get("capability_checked", False)),
            "physical_u_turn_executed": bool(scene_state.get("physical_u_turn_executed", False)),
            "post_turn_verified": bool(scene_state.get("post_turn_verified", False)),
            "u_turns_completed": int(scene_state.get("u_turns_completed", 0)),
            "turn_station_available": bool(scene_state.get("turn_station_available", True)),
            "physical_u_scene_enabled": bool(scene_state.get("physical_u_scene_enabled", True)),
        }

        if self.guide_mode == "GUIDE_MINIMAL":
            if mission.mission_type == MissionType.RELAY_SOLVE_CUBE:
                mission_guide = (
                    "Goal (RELAY_SOLVE_CUBE): Cooperate physically with the human to solve the Rubik's cube 100% under strict Zero Action/Pose Leakage. "
                    "You are completely autonomous—choose the single best next skill or protocol action based strictly on relay_cognitive_context, observable_state, available_skills (preconditions_met=true), failure_feedback, and physical_capability_boundary. "
                    "Core principles: "
                    "(1) Information Economics: When unknown_count==54 and previous_belief_54_known==false, run observe_workspace then scan_occluded_bottom_face. After any human turn (needs_rescan==true), prefer 1s zero-contact observe_tabletop_rapid first: if deduced_54_unique==true, skip scan_occluded_bottom_face to save ~25s; if ambiguous_facelet_count>0, weigh scan_occluded_bottom_face (~25s) vs ask_human_clarification. Call request_vlm_scene_semantics on CV failure/conflict/uncertainty. "
                    "(2) Dynamic Task Allocation: Human natural-language constraints in hri_context ALWAYS override default cost heuristics (e.g., if human refuses bottom moves or asks robot to solve/handover, obey immediately). Otherwise prefer committing 1..3 lower-cost moves via commit_physical_moves(moves, contract) and calling handover_to_human(message_zh, suggested_moves, delegation_reason_zh) before costly 2-Flip (~25s + regrasp) moves. "
                    "(3) Intent & Anti-Undo: If human_deviation_detected and undo_conflict_risk are true, check hri_context.human_dialog_history first: if human already clarified intent (keep route vs undo slip), act immediately using alternative_non_undo_solution or undo move; if human gave no explanation, call ask_human_clarification instead of blindly undoing (avoid R/R' ping-pong). "
                    "(4) Safety, Interrupts & Verification: When issuing commit_physical_moves, attach ExecutionContractSpec with interrupt_on_human_chat_command=true and mid_turn_recovery_mode='UNWIND_TO_ZERO' (preferred reversible safe-stop mode unless human explicitly asks to complete/snap forward). If the human interrupts or says pause/stop ('停', '暂停', '先别解', '等一下', urgent_interrupt), NEVER choose SAFE_STOP/STOP or abort the mission—first align lattice via recover_preempted_turn_slice if is_lattice_aligned is false, then immediately call handover_to_human so the robot parks safely on the table and pauses in WAITING_FOR_HUMAN_TURN for the human to operate or say '继续'. When is_solved is true and not post_solve_independent_verified, call verify_solved_cube_independent before FINISH."
                )
            else:
                mission_guide = (
                    f"Goal ({mission.mission_type.value}): {mission.user_goal} "
                    f"Success criteria: {mission.success_criteria} "
                    "Select the single best next skill or protocol action based strictly on current observable_state, "
                    "observation_history, failure_feedback, camera_status, available_skills (preconditions_met=true), "
                    "and physical_capability_boundary. Do not follow a fixed sequence when initial state, task goals, "
                    "or failures require skipping completed steps, re-observing, recovering, or selecting SAFE_STOP / "
                    "CAPABILITY_BLOCKED."
                )
            protocol_actions = (
                ["FINISH", "CAPABILITY_BLOCKED", "REQUEST_REPLAN"]
                if mission.mission_type == MissionType.RELAY_SOLVE_CUBE
                else ["FINISH", "SAFE_STOP", "CAPABILITY_BLOCKED", "REQUEST_REPLAN"]
            )
        else:
            inspection_guide = (
                "Required safe inspection phase: observe_workspace -> place_and_release -> "
                "observe_visible_faces({'view_mode':'released'}). If unknown_count remains greater than zero, "
                "choose regrasp_cube exactly once while the cube is released; after regrasp, choose "
                "reorient_cube({'axis':'pitch','degrees':-90}) exactly once while held; then choose "
                "observe_visible_faces({'view_mode':'held'}). Do not use yaw for the hidden-face scan, do not "
                "place_and_release again, and do not repeat an observation from an unchanged pose because those "
                "actions cannot reveal the remaining face. When unknown_count is zero: finish_inspection -> "
                "validate_cube_state."
            )
            if mission.mission_type == MissionType.INSPECT_CUBE:
                mission_guide = (
                    "Goal: Complete 54-sticker inspection and validate solvability WITHOUT any physical face turns. "
                    + inspection_guide
                    + " Then FINISH."
                )
            elif mission.mission_type == MissionType.VERIFY_PHYSICAL_U_TURN:
                mission_guide = (
                    "Goal: Inspect all 54 stickers, compute single U turn expectation, execute physical U turn, and verify post-turn 21 cells. "
                    + inspection_guide
                    + " After validate_cube_state: compute_symbolic_plan({'target_mode':'single_u_expectation'}) -> "
                    "execute_physical_u_turn({'move':'U'}) -> verify_post_turn_state -> FINISH."
                )
            else:
                mission_guide = (
                    "Goal: Inspect all 54 stickers, validate state, compute full symbolic Kociemba solve plan, and audit physical capability. "
                    + inspection_guide
                    + " After validate_cube_state: compute_symbolic_plan({'target_mode':'solve'}) -> "
                    "check_physical_capability -> FINISH (note: check_physical_capability will block if moves outside ['U'] are needed)."
                )
            protocol_actions = ["FINISH", "STOP"]

        context_payload = {
            "mission_type": mission.mission_type.value,
            "user_goal": mission.user_goal,
            "success_criteria": mission.success_criteria,
            "mission_guide": mission_guide,
            "prompt_meta": {
                "prompt_version": f"m4d.{self.guide_mode.lower()}",
                "guide_mode": self.guide_mode,
            },
            "observation_metadata": {
                "observation_id": agent_observation.observation_id,
                "frame_id": agent_observation.frame_id,
                "camera_id": agent_observation.camera_id,
                "sim_time": agent_observation.sim_time,
                "latest_skill_result": agent_observation.latest_skill_result,
            },
            "observation_history": list(scene_state.get("observation_history") or []),
            "camera_status": dict(scene_state.get("camera_status") or {}),
            "failure_feedback": scene_state.get("failure_feedback") or agent_observation.latest_skill_result,
            "observable_state": observable_state,
            "physical_capability_boundary": registry.snapshot().physical_limitations_summary,
            "available_skills": skill_specs,
            "protocol_actions": protocol_actions,
            "response_schema": {
                "action": "skill_id from available_skills (with preconditions_met=true) or protocol_actions",
                "parameters": "dict matching supported_parameters (use {} if none)",
                "reason_summary": "concise summary citing observed state and evidence",
                "expected_information_gain": "expected effect or information gain",
                "confidence": "float 0..1",
            },
        }
        if mission.mission_type == MissionType.RELAY_SOLVE_CUBE and scene_state.get("relay_cognitive_context"):
            context_payload["relay_cognitive_context"] = dict(scene_state["relay_cognitive_context"])
        return (
            self._prompt_header_instruction()
            + json.dumps(context_payload, ensure_ascii=False, separators=(",", ":"))
        )

    def _map_action_name(
        self,
        raw_action: str,
        params: dict[str, Any],
        mission: MissionState,
        scene_state: dict[str, Any],
    ) -> tuple[str, dict[str, Any]]:
        action = raw_action.strip()
        p = dict(params or {})

        if action == "OBSERVE" or action == "REQUEST_MORE_INFORMATION":
            if not scene_state.get("cube_localized", False):
                return "observe_workspace", {"camera_name": p.get("camera_name", "overhead")}
            return "observe_visible_faces", {"view_mode": p.get("view_mode", "auto")}

        if action == "REGRASP":
            return "regrasp_cube", {}

        if action == "REORIENT":
            axis = p.get("axis", "pitch")
            deg = p.get("degrees", -90 if axis == "pitch" else 90)
            return "reorient_cube", {"axis": axis, "degrees": deg}

        if action == "CONTINUE_TASK":
            if not scene_state.get("cube_localized", False):
                return "observe_workspace", {"camera_name": "overhead"}
            if not scene_state.get("scan_attempted", False):
                return "place_and_release", {}
            if not scene_state.get("all_54_facelets_observed", False):
                if scene_state.get("cube_held_in_gripper", False):
                    return "reorient_cube", {"axis": "pitch", "degrees": -90}
                if scene_state.get("cube_released_on_table", False):
                    return "regrasp_cube", {}
                return "observe_visible_faces", {"view_mode": "auto"}
            if not scene_state.get("finish_inspection_done", False):
                return "finish_inspection", {}
            if not scene_state.get("cube_state_validated", False):
                return "validate_cube_state", {}
            if mission.mission_type == MissionType.INSPECT_CUBE:
                return "FINISH", {}
            if not scene_state.get("symbolic_plan_available", False):
                mode = "single_u_expectation" if mission.mission_type == MissionType.VERIFY_PHYSICAL_U_TURN else "solve"
                return "compute_symbolic_plan", {"target_mode": mode}
            if mission.mission_type == MissionType.SOLVE_CUBE:
                if not scene_state.get("capability_checked", False):
                    return "check_physical_capability", {}
                sol = list(scene_state.get("symbolic_solution") or [])
                executed = list(scene_state.get("executed_physical_moves") or [])
                if scene_state.get("full_26_cubie_scene_enabled", False) and len(executed) < len(sol):
                    return "execute_physical_face_turn", {"move": str(sol[len(executed)])}
                if len(executed) > 0 and not scene_state.get("post_turn_verified", False):
                    return "verify_post_turn_state", {}
                if scene_state.get("full_26_cubie_scene_enabled", False):
                    return "FINISH", {}
                return "check_physical_capability", {}
            if scene_state.get("full_26_cubie_scene_enabled", False):
                if not scene_state.get("physical_face_turn_executed", False):
                    return "execute_physical_face_turn", {"move": "U"}
                if not scene_state.get("post_turn_verified", False):
                    return "verify_post_turn_state", {}
                return "FINISH", {}
            if not scene_state.get("physical_u_turn_executed", False):
                return "execute_physical_u_turn", {"move": "U"}
            if not scene_state.get("post_turn_verified", False):
                return "verify_post_turn_state", {}
            return "FINISH", {}

        if mission.mission_type == MissionType.RELAY_SOLVE_CUBE and action in {"STOP", "SAFE_STOP"}:
            if not scene_state.get("is_lattice_aligned", True):
                return "recover_preempted_turn_slice", {"mode": "UNWIND_TO_ZERO"}
            return "handover_to_human", {
                "message_zh": "已响应您的暂停/打断指令，魔方已安全停放桌面等待您的操作，或随时发送「你继续」。",
                "suggested_moves": [],
                "delegation_reason_zh": "响应人类中途打断，安全停泊于桌面等待恢复接力。",
            }

        if action == "compute_symbolic_plan" and "target_mode" not in p:
            p["target_mode"] = (
                "single_u_expectation"
                if mission.mission_type == MissionType.VERIFY_PHYSICAL_U_TURN
                else "solve"
            )
        if action == "execute_physical_u_turn" and "move" not in p:
            p["move"] = "U"
        if action == "reorient_cube":
            if "axis" not in p:
                p["axis"] = "pitch"
            if "degrees" not in p:
                p["degrees"] = -90 if p["axis"] == "pitch" else 90
        if action == "commit_physical_moves":
            if "contract" not in p or p["contract"] is None:
                p["contract"] = {
                    "max_target_drift_m": 0.015,
                    "interrupt_on_human_chat_command": True,
                    "mid_turn_recovery_mode": "UNWIND_TO_ZERO",
                    "abort_on_unexpected_flip": False,
                }
            if isinstance(p.get("moves"), list):
                p["moves"] = [str(m).strip() for m in p["moves"]]
        if action == "handover_to_human":
            p.setdefault("message_zh", "魔方已安全放回桌面，请按需操作并交回。")
            p.setdefault("suggested_moves", [])
            if isinstance(p.get("suggested_moves"), list):
                p["suggested_moves"] = [str(m).strip() for m in p["suggested_moves"]][:3]
            p.setdefault("delegation_reason_zh", "综合具身代价与当前协作成交策略移交桌面。")
        if action == "ask_human_clarification":
            p.setdefault("options", ["保留当前状态继续求解", "请撤回刚才这一步", "抓起翻转完整扫描底面"])
            p.setdefault("clarification_topic", "INTENT_DEVIATION")
        if action == "recover_preempted_turn_slice" and "mode" not in p:
            p["mode"] = "UNWIND_TO_ZERO"
        return action, p

    def _mission_ready_to_finish(self, mission: MissionState, scene_state: dict[str, Any]) -> tuple[bool, str | None]:
        if mission.mission_type == MissionType.RELAY_SOLVE_CUBE:
            if not scene_state.get("is_solved", False):
                return False, "RELAY_SOLVE_CUBE 尚未达成 54/54 复原状态"
            if not scene_state.get("post_solve_independent_verified", False):
                return False, "RELAY_SOLVE_CUBE 尚未完成全六面独立视觉复核 (verify_solved_cube_independent)"
            return True, None
        if mission.mission_type == MissionType.INSPECT_CUBE:
            if scene_state.get("custom_completion_requirement") == "cube_localized":
                if not scene_state.get("cube_localized", False):
                    return False, "自定义定位任务尚未完成三维定位 (cube_localized)"
                return True, None
            if not scene_state.get("cube_state_validated", False):
                return False, "INSPECT_CUBE 尚未完成 54 格合法性校验 (validate_cube_state)"
            return True, None
        if mission.mission_type == MissionType.VERIFY_PHYSICAL_U_TURN:
            if not scene_state.get("post_turn_verified", False):
                return False, "VERIFY_PHYSICAL_U_TURN 尚未完成转后 21 格视觉复核 (verify_post_turn_state)"
            return True, None
        # SOLVE_CUBE
        if not scene_state.get("symbolic_plan_available", False):
            return False, "SOLVE_CUBE 尚未完成符号求解 (compute_symbolic_plan)"
        sol = scene_state.get("symbolic_solution") or []
        if len(sol) > 0 and not scene_state.get("capability_checked", False):
            return False, "SOLVE_CUBE 尚未完成物理能力核查 (check_physical_capability)"
        if scene_state.get("full_26_cubie_scene_enabled", False) and len(sol) > 0:
            executed = list(scene_state.get("executed_physical_moves") or [])
            if len(executed) < len(sol):
                return False, f"SOLVE_CUBE 尚余 {len(sol) - len(executed)}/{len(sol)} 步物理转面未执行"
            if not scene_state.get("post_turn_verified", False):
                return False, "SOLVE_CUBE 尚未完成全六面独立相机复核 (verify_post_turn_state)"
        return True, None

    def _deterministic_fallback_step(
        self,
        mission: MissionState,
        plan: PlanState,
        registry: SkillRegistry,
        scene_state: dict[str, Any],
        latest_observation: ObservationReference | None,
        *,
        error_code: str,
        error_detail: str,
    ) -> SelectedAction:
        action, params = self._map_action_name("CONTINUE_TASK", {}, mission, scene_state)
        obs_ref = latest_observation.observation_id if latest_observation else None
        if action == "FINISH":
            return SelectedAction(
                decision_kind="COMPLETE_MISSION",
                step_id=None,
                skill_id=None,
                parameters={},
                rationale_summary=f"VLM 异常 ({error_code}) 触发确定性 Fallback：任务条件已满足。",
                input_reference=obs_ref,
                validation_result=f"FALLBACK_USED:{error_code}",
                failure_code=error_code,
                fallback_used=True,
            )
        self._step_counter += 1
        return SelectedAction(
            decision_kind="EXECUTE_STEP",
            step_id=f"{plan.plan_id}-d{self._step_counter}",
            skill_id=action,
            parameters=params,
            rationale_summary=f"VLM 异常 ({error_code}: {error_detail})，显式记录并回退至确定性下一步 [{action}]。",
            input_reference=obs_ref,
            validation_result=f"FALLBACK_USED:{error_code}",
            failure_code=error_code,
            fallback_used=True,
        )

    def _pre_decision_checks(
        self,
        mission: MissionState,
        registry: SkillRegistry,
        scene_state: dict[str, Any],
        latest_observation: ObservationReference | None,
        agent_observation: AgentObservation | None,
    ) -> tuple[str | None, list[str], tuple[str, ...], SelectedAction | None]:
        obs_ref = (
            agent_observation.observation_id
            if agent_observation is not None
            else (latest_observation.observation_id if latest_observation else None)
        )
        allowed_skill_ids = self._allowed_skill_ids(mission, registry)
        candidates = tuple([*allowed_skill_ids, *_HIGH_LEVEL_PROTOCOL_ACTIONS])

        if agent_observation is None:
            return obs_ref, allowed_skill_ids, candidates, SelectedAction(
                decision_kind="FAIL_MISSION",
                step_id=None,
                skill_id=None,
                parameters={},
                rationale_summary="相机或状态观测缺失：未能生成有效 AgentObservation。",
                input_reference=obs_ref,
                validation_result="REJECTED:CAMERA_FRAME_MISSING",
                action_candidates=candidates,
                failure_code="CAMERA_FRAME_MISSING",
            )

        latest_sim_time = scene_state.get("latest_sim_time")
        if latest_sim_time is not None and agent_observation.sim_time + 1e-6 < float(latest_sim_time):
            return obs_ref, allowed_skill_ids, candidates, SelectedAction(
                decision_kind="FAIL_MISSION",
                step_id=None,
                skill_id=None,
                parameters={},
                rationale_summary=(
                    f"观测帧过期：obs.sim_time={agent_observation.sim_time:.3f}s < "
                    f"current_sim_time={float(latest_sim_time):.3f}s。"
                ),
                input_reference=obs_ref,
                validation_result="REJECTED:STALE_OBSERVATION",
                action_candidates=candidates,
                failure_code="STALE_OBSERVATION",
            )
        return obs_ref, allowed_skill_ids, candidates, None

    def _resolve_image_url(self, agent_observation: AgentObservation) -> str | None:
        return (
            self.replacement_image_data_url
            if self.context_mode == "replaced_image" and self.replacement_image_data_url
            else agent_observation.rgb_image_data_url
        )

    @staticmethod
    def _attach_call_trace_metadata(selected: SelectedAction, call_res: VLMCallResult) -> SelectedAction:
        return replace(
            selected,
            evidence_bundle_id=selected.evidence_bundle_id or call_res.evidence_bundle_id,
            request_id=selected.request_id or call_res.request_id,
            prompt_sha256=selected.prompt_sha256 or call_res.prompt_sha256,
            perception_provenance=(
                dict(selected.perception_provenance)
                if selected.perception_provenance
                else dict(call_res.perception_provenance)
            ),
            evidence_conflicts=(
                selected.evidence_conflicts
                if selected.evidence_conflicts
                else tuple(call_res.evidence_conflicts)
            ),
            evidence_validity=(
                dict(selected.evidence_validity)
                if selected.evidence_validity
                else dict(call_res.evidence_validity)
            ),
            semantic_provided_to_agent=(
                selected.semantic_provided_to_agent
                if selected.semantic_provided_to_agent is not None
                else call_res.semantic_provided_to_agent
            ),
        )

    def _validate_and_gate_call(
        self,
        call_res: VLMCallResult,
        *,
        mission: MissionState,
        plan: PlanState,
        registry: SkillRegistry,
        scene_state: dict[str, Any],
        latest_observation: ObservationReference | None,
        obs_ref: str | None,
        allowed_skill_ids: list[str],
        candidates: tuple[str, ...],
        evidence_refs: tuple[str, ...],
        need_replan: bool,
    ) -> SelectedAction:
        token_usage = None
        if (
            call_res.input_tokens is not None
            or call_res.output_tokens is not None
            or call_res.reasoning_tokens is not None
        ):
            token_usage = {
                "input_tokens": call_res.input_tokens or 0,
                "output_tokens": call_res.output_tokens or 0,
                "reasoning_tokens": call_res.reasoning_tokens,
            }

        if call_res.error_code is not None or call_res.parsed_output is None:
            err_code = call_res.error_code or "VLM_CALL_FAILED"
            err_msg = call_res.error or "Model decision response invalid"
            if self.limits.allow_deterministic_fallback:
                fb = self._deterministic_fallback_step(
                    mission, plan, registry, scene_state, latest_observation,
                    error_code=err_code, error_detail=err_msg,
                )
                return self._attach_call_trace_metadata(fb, call_res)
            return self._attach_call_trace_metadata(SelectedAction(
                decision_kind="FAIL_MISSION",
                step_id=None,
                skill_id=None,
                parameters={},
                rationale_summary=f"VLM 决策失败 ({err_code})：{err_msg}",
                input_reference=obs_ref,
                validation_result=f"FAILED:{err_code}",
                model_latency_ms=call_res.latency_ms,
                token_usage=token_usage,
                action_candidates=candidates,
                failure_code=err_code,
            ), call_res)

        selected = self._gate_parsed_output(
            call_res,
            mission=mission,
            plan=plan,
            registry=registry,
            scene_state=scene_state,
            obs_ref=obs_ref,
            allowed_skill_ids=allowed_skill_ids,
            candidates=candidates,
            evidence_refs=evidence_refs,
            need_replan=need_replan,
            token_usage=token_usage,
        )
        return self._attach_call_trace_metadata(selected, call_res)

    def _gate_parsed_output(
        self,
        call_res: VLMCallResult,
        *,
        mission: MissionState,
        plan: PlanState,
        registry: SkillRegistry,
        scene_state: dict[str, Any],
        obs_ref: str | None,
        allowed_skill_ids: list[str],
        candidates: tuple[str, ...],
        evidence_refs: tuple[str, ...],
        need_replan: bool,
        token_usage: dict[str, Any] | None,
    ) -> SelectedAction:

        decision = call_res.parsed_output
        raw_action = decision.action.strip()

        # Explicit physical move request outside allowed single clockwise U turn -> CAPABILITY_BLOCKED
        if raw_action in LEGAL_MOVES:
            cap = registry.can_execute_physical_move(raw_action, scene_state)
            if not cap.supported:
                return SelectedAction(
                    decision_kind="BLOCK_CAPABILITY",
                    step_id=None,
                    skill_id="execute_physical_non_u_turn",
                    parameters={"move": raw_action},
                    rationale_summary=cap.unsupported_reason or f"物理动作 {raw_action} 不受支持",
                    input_reference=obs_ref,
                    blocked_move=raw_action,
                    blocked_moves=(raw_action,),
                    blocked_reason=cap.unsupported_reason,
                    expected_information_gain=decision.expected_information_gain,
                    confidence=decision.confidence,
                    validation_result="CAPABILITY_BLOCKED",
                    model_latency_ms=call_res.latency_ms,
                    token_usage=token_usage,
                    raw_vlm_action=raw_action,
                    action_candidates=candidates,
                    failure_code="CAPABILITY_UNSUPPORTED",
                )
        if raw_action == "execute_physical_non_u_turn":
            move = str(decision.parameters.get("move", "R"))
            cap = registry.can_execute_physical_move(move if move != "U" else "R", scene_state)
            return SelectedAction(
                decision_kind="BLOCK_CAPABILITY",
                step_id=None,
                skill_id="execute_physical_non_u_turn",
                parameters=dict(decision.parameters),
                rationale_summary=cap.unsupported_reason or "非 U 单向转层能力尚未在 MuJoCo 建模",
                input_reference=obs_ref,
                blocked_move=move,
                blocked_moves=(move,),
                blocked_reason=cap.unsupported_reason,
                expected_information_gain=decision.expected_information_gain,
                confidence=decision.confidence,
                validation_result="CAPABILITY_BLOCKED",
                model_latency_ms=call_res.latency_ms,
                token_usage=token_usage,
                raw_vlm_action=raw_action,
                action_candidates=candidates,
                failure_code="CAPABILITY_UNSUPPORTED",
            )

        mapped_action, mapped_params = self._map_action_name(raw_action, decision.parameters, mission, scene_state)

        if (
            mapped_action == "reorient_cube"
            and not scene_state.get("all_54_facelets_observed", False)
            and (
                mapped_params.get("axis") != "pitch"
                or float(mapped_params.get("degrees", 0.0)) != -90.0
            )
        ):
            return SelectedAction(
                decision_kind="FAIL_MISSION",
                step_id=None,
                skill_id=mapped_action,
                parameters=mapped_params,
                rationale_summary=(
                    "Safety Gate 拒绝未验收的扫描重定位参数：隐藏面扫描仅允许 "
                    "reorient_cube(axis='pitch', degrees=-90)。"
                ),
                input_reference=obs_ref,
                expected_information_gain=decision.expected_information_gain,
                confidence=decision.confidence,
                validation_result="REJECTED:INSPECTION_REORIENT_UNSUPPORTED",
                model_latency_ms=call_res.latency_ms,
                token_usage=token_usage,
                raw_vlm_action=raw_action,
                action_candidates=candidates,
                failure_code="PARAMETER_OUT_OF_BOUNDS",
            )

        if mapped_action in {"STOP", "SAFE_STOP"}:
            return SelectedAction(
                decision_kind="FAIL_MISSION",
                step_id=None,
                skill_id=None,
                parameters={},
                rationale_summary=f"VLM 主动请求停止：{decision.reason_summary}",
                input_reference=obs_ref,
                expected_information_gain=decision.expected_information_gain,
                confidence=decision.confidence,
                validation_result="STOP_REQUESTED",
                model_latency_ms=call_res.latency_ms,
                token_usage=token_usage,
                raw_vlm_action=raw_action,
                action_candidates=candidates,
                failure_code="VLM_REQUESTED_STOP",
                evidence_references=evidence_refs,
                need_replan=need_replan,
            )

        if mapped_action == "CAPABILITY_BLOCKED":
            return SelectedAction(
                decision_kind="BLOCK_CAPABILITY",
                step_id=None,
                skill_id=None,
                parameters=mapped_params,
                rationale_summary=decision.reason_summary,
                input_reference=obs_ref,
                blocked_reason=decision.reason_summary,
                expected_information_gain=decision.expected_information_gain,
                confidence=decision.confidence,
                validation_result="CAPABILITY_BLOCKED",
                model_latency_ms=call_res.latency_ms,
                token_usage=token_usage,
                raw_vlm_action=raw_action,
                action_candidates=candidates,
                failure_code="CAPABILITY_UNSUPPORTED",
                evidence_references=evidence_refs,
                need_replan=need_replan,
            )

        if mapped_action == "REQUEST_REPLAN":
            return SelectedAction(
                decision_kind="REQUEST_REPLAN",
                step_id=None,
                skill_id=None,
                parameters=mapped_params,
                rationale_summary=decision.reason_summary,
                input_reference=obs_ref,
                expected_information_gain=decision.expected_information_gain,
                confidence=decision.confidence,
                validation_result="REPLAN_REQUESTED",
                model_latency_ms=call_res.latency_ms,
                token_usage=token_usage,
                raw_vlm_action=raw_action,
                action_candidates=candidates,
                evidence_references=evidence_refs,
                need_replan=True,
            )

        if mapped_action == "FINISH":
            ready, not_ready_reason = self._mission_ready_to_finish(mission, scene_state)
            if not ready:
                return SelectedAction(
                    decision_kind="FAIL_MISSION",
                    step_id=None,
                    skill_id=None,
                    parameters={},
                    rationale_summary=f"Safety Gate 拒绝过早结束任务：{not_ready_reason}",
                    input_reference=obs_ref,
                    expected_information_gain=decision.expected_information_gain,
                    confidence=decision.confidence,
                    validation_result=f"REJECTED:PREMATURE_FINISH:{not_ready_reason}",
                    model_latency_ms=call_res.latency_ms,
                    token_usage=token_usage,
                    raw_vlm_action=raw_action,
                    action_candidates=candidates,
                    failure_code="PREMATURE_FINISH",
                    evidence_references=evidence_refs,
                    need_replan=need_replan,
                )
            return SelectedAction(
                decision_kind="COMPLETE_MISSION",
                step_id=None,
                skill_id=None,
                parameters={},
                rationale_summary=decision.reason_summary,
                input_reference=obs_ref,
                expected_information_gain=decision.expected_information_gain,
                confidence=decision.confidence,
                validation_result="PASSED",
                model_latency_ms=call_res.latency_ms,
                token_usage=token_usage,
                raw_vlm_action=raw_action,
                action_candidates=candidates,
                evidence_references=evidence_refs,
                need_replan=need_replan,
            )

        # Strict allow-list check against SkillRegistry-derived skills
        if mapped_action not in allowed_skill_ids:
            reason = f"Safety Gate 拒绝未授权动作：{raw_action!r} (映射 {mapped_action!r}) 不在当前允许列表 {allowed_skill_ids}"
            return SelectedAction(
                decision_kind="FAIL_MISSION",
                step_id=None,
                skill_id=mapped_action,
                parameters=mapped_params,
                rationale_summary=reason,
                input_reference=obs_ref,
                expected_information_gain=decision.expected_information_gain,
                confidence=decision.confidence,
                validation_result=f"REJECTED:DISALLOWED_ACTION:{raw_action}",
                model_latency_ms=call_res.latency_ms,
                token_usage=token_usage,
                raw_vlm_action=raw_action,
                action_candidates=candidates,
                failure_code="DISALLOWED_ACTION",
            )

        param_ok, param_err = registry.validate_parameters(mapped_action, mapped_params)
        if not param_ok:
            if mapped_action in {"execute_physical_u_turn", "execute_physical_face_turn"}:
                move = str(mapped_params.get("move", ""))
                cap = registry.can_execute_physical_move(move or "U'", scene_state)
                return SelectedAction(
                    decision_kind="BLOCK_CAPABILITY",
                    step_id=None,
                    skill_id=mapped_action,
                    parameters=mapped_params,
                    rationale_summary=param_err or cap.unsupported_reason or "不支持的物理转层参数",
                    input_reference=obs_ref,
                    blocked_move=move or None,
                    blocked_moves=(move,) if move else (),
                    blocked_reason=param_err or cap.unsupported_reason,
                    expected_information_gain=decision.expected_information_gain,
                    confidence=decision.confidence,
                    validation_result=f"CAPABILITY_BLOCKED:{param_err}",
                    model_latency_ms=call_res.latency_ms,
                    token_usage=token_usage,
                    raw_vlm_action=raw_action,
                    action_candidates=candidates,
                    failure_code="CAPABILITY_UNSUPPORTED",
                )
            return SelectedAction(
                decision_kind="FAIL_MISSION",
                step_id=None,
                skill_id=mapped_action,
                parameters=mapped_params,
                rationale_summary=f"Safety Gate 拒绝非法参数：{param_err}",
                input_reference=obs_ref,
                expected_information_gain=decision.expected_information_gain,
                confidence=decision.confidence,
                validation_result=f"REJECTED:PARAMETER_OUT_OF_BOUNDS:{param_err}",
                model_latency_ms=call_res.latency_ms,
                token_usage=token_usage,
                raw_vlm_action=raw_action,
                action_candidates=candidates,
                failure_code="PARAMETER_OUT_OF_BOUNDS",
            )

        pre_ok, missing = registry.check_preconditions(mapped_action, scene_state)
        if not pre_ok:
            reason = f"Safety Gate 拒绝 [{mapped_action}]：缺少前置条件 {', '.join(missing)}"
            if mapped_action in {"execute_physical_u_turn", "execute_physical_face_turn"}:
                return SelectedAction(
                    decision_kind="BLOCK_CAPABILITY",
                    step_id=None,
                    skill_id=mapped_action,
                    parameters=mapped_params,
                    rationale_summary=reason,
                    input_reference=obs_ref,
                    blocked_move=str(mapped_params.get("move", "U")),
                    blocked_moves=(str(mapped_params.get("move", "U")),),
                    blocked_reason=reason,
                    expected_information_gain=decision.expected_information_gain,
                    confidence=decision.confidence,
                    validation_result=f"CAPABILITY_BLOCKED:MISSING_PRECONDITIONS:{missing}",
                    model_latency_ms=call_res.latency_ms,
                    token_usage=token_usage,
                    raw_vlm_action=raw_action,
                    action_candidates=candidates,
                    failure_code="PRECONDITION_MISSING",
                )
            return SelectedAction(
                decision_kind="FAIL_MISSION",
                step_id=None,
                skill_id=mapped_action,
                parameters=mapped_params,
                rationale_summary=reason,
                input_reference=obs_ref,
                expected_information_gain=decision.expected_information_gain,
                confidence=decision.confidence,
                validation_result=f"REJECTED:MISSING_PRECONDITIONS:{missing}",
                model_latency_ms=call_res.latency_ms,
                token_usage=token_usage,
                raw_vlm_action=raw_action,
                action_candidates=candidates,
                failure_code="PRECONDITION_MISSING",
            )

        if mapped_action in {"execute_physical_u_turn", "execute_physical_face_turn"}:
            move = str(mapped_params.get("move", "U"))
            cap = registry.can_execute_physical_move(move, scene_state)
            if not cap.supported:
                return SelectedAction(
                    decision_kind="BLOCK_CAPABILITY",
                    step_id=None,
                    skill_id=mapped_action,
                    parameters=mapped_params,
                    rationale_summary=cap.unsupported_reason or "物理能力校验未通过",
                    input_reference=obs_ref,
                    blocked_move=move,
                    blocked_moves=(move,),
                    blocked_reason=cap.unsupported_reason,
                    expected_information_gain=decision.expected_information_gain,
                    confidence=decision.confidence,
                    validation_result=f"CAPABILITY_BLOCKED:{cap.unsupported_reason}",
                    model_latency_ms=call_res.latency_ms,
                    token_usage=token_usage,
                    raw_vlm_action=raw_action,
                    action_candidates=candidates,
                    failure_code="CAPABILITY_UNSUPPORTED",
                )

        self._step_counter += 1
        return SelectedAction(
            decision_kind="EXECUTE_STEP",
            step_id=f"{plan.plan_id}-v{self._step_counter}",
            skill_id=mapped_action,
            parameters=mapped_params,
            rationale_summary=decision.reason_summary,
            input_reference=obs_ref,
            expected_information_gain=decision.expected_information_gain,
            confidence=decision.confidence,
            validation_result="PASSED",
            model_latency_ms=call_res.latency_ms,
            token_usage=token_usage,
            raw_vlm_action=raw_action,
            action_candidates=candidates,
            evidence_references=evidence_refs,
            need_replan=need_replan,
        )


class GeminiMissionPlanner(_SafetyGatedPolicyBase):
    """BENCHMARK_BASELINE (M4-A): Isolated single-model multimodal VLM baseline.

    Strictly preserved as a standalone research baseline; never nested or invoked
    inside `LLMAgentDecisionPolicy` or `SimulationSession` dual-model mainline.
    """

    name = "GeminiMissionPlanner"
    mode = PlannerMode.LLM_AGENT
    architecture_role = "BENCHMARK_BASELINE"

    def __init__(
        self,
        *,
        client: _EnvLoadedGeminiClient | FakeGeminiVLMClient | None = None,
        model: str | None = None,
        limits: VLMInspectionLimits | None = None,
        context_mode: str = "vision_plus_structured_state",
        replacement_image_data_url: str | None = None,
        guide_mode: str = "GUIDE_FULL",
    ) -> None:
        self._init_shared_state(
            limits=limits,
            context_mode=context_mode,
            replacement_image_data_url=replacement_image_data_url,
            guide_mode=guide_mode,
        )
        if client is not None:
            self.client: _EnvLoadedGeminiClient | FakeGeminiVLMClient = client
            if model is not None:
                self.client.model = model
        else:
            self.client = _EnvLoadedGeminiClient(model=model)

    def _prompt_header_instruction(self) -> str:
        return (
            "You are CubeRelay's embodied multimodal VLM planner. Choose exactly one next action based on the "
            "live MuJoCo camera image and observable state. Never fabricate stickers, poses, or bypass preconditions. "
            "Output strictly valid JSON matching response_schema.\n"
        )

    def _plan_rationale_summary(self) -> str:
        return (
            f"由 {self.name} ({self.llm_model or 'unconfigured'}) 基于实时 MuJoCo RGB 图像与 "
            f"SkillRegistry 边界动态决定每一步动作。"
        )

    @property
    def llm_connected(self) -> bool:
        """True only after a real Gemini client has succeeded with a valid response."""
        return isinstance(self.client, _EnvLoadedGeminiClient) and bool(self.client.has_completed_valid_call)

    @property
    def llm_model(self) -> str | None:
        return self.client.model or None

    @property
    def model_provider(self) -> str:
        return self.client.provider_name

    def status_label(self) -> str:
        if self.llm_connected:
            return f"Gemini VLM 已连接并完成有效在线决策 ({self.llm_model})"
        if isinstance(self.client, FakeGeminiVLMClient):
            return f"离线协议客户端 ({self.llm_model}) · 未连接在线 Gemini API"
        if not self.client.is_configured():
            return "Gemini API 未配置，无法连接在线模型"
        return f"Gemini VLM 已就绪（待首次在线调用验证连接：{self.llm_model}）"

    def select_next_action(
        self,
        mission: MissionState,
        plan: PlanState,
        registry: SkillRegistry,
        scene_state: dict[str, Any],
        latest_observation: ObservationReference | None,
        *,
        agent_observation: AgentObservation | None = None,
    ) -> SelectedAction:
        obs_ref, allowed_skill_ids, candidates, fail_action = self._pre_decision_checks(
            mission, registry, scene_state, latest_observation, agent_observation
        )
        if fail_action is not None or agent_observation is None:
            return fail_action  # type: ignore[return-value]

        include_image = self.context_mode != "no_image"
        image_url = self._resolve_image_url(agent_observation)
        if include_image and not image_url:
            return SelectedAction(
                decision_kind="FAIL_MISSION",
                step_id=None,
                skill_id=None,
                parameters={},
                rationale_summary="实时 RGB 图像数据为空，拒绝进行无图像视觉决策。",
                input_reference=obs_ref,
                validation_result="REJECTED:CAMERA_FRAME_MISSING",
                action_candidates=candidates,
                failure_code="CAMERA_FRAME_MISSING",
            )

        prompt = self._build_prompt(mission, registry, scene_state, agent_observation, allowed_skill_ids)
        call_res = self.client.generate_decision(prompt, image_url, include_image=include_image)
        self.call_traces.append(call_res)
        return self._validate_and_gate_call(
            call_res,
            mission=mission,
            plan=plan,
            registry=registry,
            scene_state=scene_state,
            latest_observation=latest_observation,
            obs_ref=obs_ref,
            allowed_skill_ids=allowed_skill_ids,
            candidates=candidates,
            evidence_refs=(obs_ref,) if obs_ref else (),
            need_replan=False,
        )


class LLMAgentDecisionPolicy(_SafetyGatedPolicyBase):
    """ACTIVE_MAINLINE (M4-B/M4-E): Decoupled dual-model policy (Model A VLM + Model B Agent).

    Does NOT inherit from `GeminiMissionPlanner` (M4-A single-model baseline). Supports
    explicit `CV_ONLY` operation (`use_vlm_perception=False`, `semantic=None`) as well as
    `CV_VLM` and evidence-validated fallback via `PerceptionEvidenceBundle` & `EvidenceValidator`.
    """

    name = "LLMAgentDecisionPolicy"
    mode = PlannerMode.LLM_AGENT
    architecture_role = "ACTIVE_MAINLINE"

    def __init__(
        self,
        *,
        client: DualModelDecisionClient | None = None,
        limits: VLMInspectionLimits | None = None,
        context_mode: str = "vision_plus_structured_state",
        guide_mode: str = "GUIDE_FULL",
        use_vlm_perception: bool | None = None,
    ) -> None:
        resolved_limits = limits or VLMInspectionLimits(max_vlm_calls=32)
        self._init_shared_state(
            limits=resolved_limits,
            context_mode=context_mode,
            guide_mode=guide_mode,
        )
        if client is not None:
            if use_vlm_perception is not None:
                client.use_vlm_perception = bool(use_vlm_perception)
                client.model = (
                    f"perception={client.perception.client.model};agent={client.agent.client.model}"
                    if client.use_vlm_perception
                    else f"perception=NONE;agent={client.agent.client.model}"
                )
            self.client = client
        else:
            effective_vlm = True if use_vlm_perception is None else bool(use_vlm_perception)
            self.client = DualModelDecisionClient(
                use_vlm_perception=effective_vlm,
                allow_cv_only_on_vlm_failure=resolved_limits.allow_cv_only_on_vlm_failure,
            )

    @property
    def use_vlm_perception(self) -> bool:
        return bool(self.client.use_vlm_perception)

    @use_vlm_perception.setter
    def use_vlm_perception(self, value: bool) -> None:
        self.client.use_vlm_perception = bool(value)
        self.client.model = (
            f"perception={self.client.perception.client.model};agent={self.client.agent.client.model}"
            if self.client.use_vlm_perception
            else f"perception=NONE;agent={self.client.agent.client.model}"
        )

    def _prompt_header_instruction(self) -> str:
        return (
            "You are CubeRelay's decoupled task-level planning context for AgentPlanningProvider "
            "(the planner receives structured CV state, evidence validity metadata, and optional VLM semantic "
            "descriptions, never raw image pixels). Choose exactly one next action based on observable state "
            "and verified evidence. Never fabricate stickers, poses, or bypass preconditions. "
            "Output strictly valid JSON matching response_schema.\n"
        )

    def _plan_rationale_summary(self) -> str:
        mode_tag = "CV+VLM" if self.use_vlm_perception else "CV_ONLY"
        return (
            f"由 {self.name} [{mode_tag}] ({self.llm_model or 'unconfigured'}) 基于确定性 CV 状态、"
            f"PerceptionEvidenceBundle 与 SkillRegistry 边界动态决定每一步动作。"
        )

    @property
    def llm_connected(self) -> bool:
        return bool(self.client.has_completed_valid_call)

    @property
    def llm_model(self) -> str | None:
        return self.client.model or None

    @property
    def model_provider(self) -> str:
        return (
            "independent_vlm_perception+llm_agent"
            if self.use_vlm_perception
            else "cv_only+llm_agent"
        )

    @property
    def perception_provider(self):
        return self.client.perception

    @property
    def agent_provider(self):
        return self.client.agent

    def status_label(self) -> str:
        if not self.use_vlm_perception:
            if self.llm_connected:
                return f"CV_ONLY 独立 Agent 闭环已连接 ({self.llm_model}) · VLM 语义感知已关闭"
            if not self.client.is_configured():
                return "CV_ONLY 模式未配置：需要 AGENT endpoint/model/key"
            return f"CV_ONLY 模式已配置，等待首次有效 Agent 规划 ({self.llm_model})"
        if self.llm_connected:
            return f"双模型闭环已连接 ({self.llm_model})"
        if not self.client.is_configured():
            return "双模型未配置：需要独立 PERCEPTION 与 AGENT endpoint/model/key"
        return f"双模型已配置，等待首次有效感知与规划 ({self.llm_model})"

    def select_next_action(
        self,
        mission: MissionState,
        plan: PlanState,
        registry: SkillRegistry,
        scene_state: dict[str, Any],
        latest_observation: ObservationReference | None,
        *,
        agent_observation: AgentObservation | None = None,
    ) -> SelectedAction:
        hri = scene_state.get("relay_cognitive_context", {}).get("hri_context", {})
        if mission.mission_type == MissionType.RELAY_SOLVE_CUBE and hri.get("paused_by_interrupt"):
            skill, params = self._map_action_name("SAFE_STOP", {}, mission, scene_state)
            valid, error = registry.validate_parameters(skill, params)
            ready, missing = registry.check_preconditions(skill, scene_state)
            reason = error if not valid else ", ".join(missing)
            self._step_counter += 1
            return SelectedAction(
                decision_kind="EXECUTE_STEP" if valid and ready else "BLOCK_CAPABILITY",
                step_id=f"{plan.plan_id}-v{self._step_counter}",
                skill_id=skill,
                parameters=params,
                input_reference=latest_observation.observation_id if latest_observation else None,
                rationale_summary="执行已确认的人类暂停，先确保晶格对齐，再安全停泊交接。",
                blocked_reason=reason or None,
                validation_result="PASSED" if valid and ready else "REJECTED",
            )

        obs_ref, allowed_skill_ids, candidates, fail_action = self._pre_decision_checks(
            mission, registry, scene_state, latest_observation, agent_observation
        )
        if fail_action is not None or agent_observation is None:
            return fail_action  # type: ignore[return-value]

        orig_use_vlm = bool(self.client.use_vlm_perception)
        orig_model = self.client.model
        step_use_vlm = orig_use_vlm
        if mission.mission_type == MissionType.RELAY_SOLVE_CUBE:
            step_use_vlm = bool(scene_state.get("vlm_awakening_requested", False)) and bool(
                orig_use_vlm or self.client.perception.client.is_configured() or self.client.injected_semantics is not None
            )

        include_image = (
            step_use_vlm
            and self.context_mode != "no_image"
            and self.client.injected_semantics is None
        )
        image_url = self._resolve_image_url(agent_observation)
        if include_image and not image_url and not self.limits.allow_cv_only_on_vlm_failure:
            return SelectedAction(
                decision_kind="FAIL_MISSION",
                step_id=None,
                skill_id=None,
                parameters={},
                rationale_summary="实时 RGB 图像数据为空，拒绝进行无图像视觉决策。",
                input_reference=obs_ref,
                validation_result="REJECTED:CAMERA_FRAME_MISSING",
                action_candidates=candidates,
                failure_code="CAMERA_FRAME_MISSING",
            )

        prompt = self._build_prompt(mission, registry, scene_state, agent_observation, allowed_skill_ids)
        try:
            if step_use_vlm != orig_use_vlm:
                self.client.use_vlm_perception = step_use_vlm
                self.client.model = (
                    f"perception={self.client.perception.client.model};agent={self.client.agent.client.model}"
                    if step_use_vlm
                    else f"perception=ON_DEMAND_DORMANT;agent={self.client.agent.client.model}"
                )
            call_res = self.client.decide_with_evidence(
                prompt=prompt,
                observation=agent_observation,
                observation_ref=latest_observation,
                scene_state=scene_state,
                rgb_data_url=image_url,
                include_image=(self.context_mode != "no_image"),
                allow_cv_only_on_vlm_failure=self.limits.allow_cv_only_on_vlm_failure,
            )
        finally:
            self.client.use_vlm_perception = orig_use_vlm
            self.client.model = orig_model
        self.call_traces.append(call_res)
        last_agent_dec = getattr(self.client, "last_agent_decision", None)
        evidence_refs = (
            tuple(str(item) for item in last_agent_dec.evidence_observation_ids)
            if last_agent_dec is not None
            else ((obs_ref,) if obs_ref else ())
        )
        need_replan = bool(getattr(last_agent_dec, "need_replan", False)) if last_agent_dec is not None else False
        return self._validate_and_gate_call(
            call_res,
            mission=mission,
            plan=plan,
            registry=registry,
            scene_state=scene_state,
            latest_observation=latest_observation,
            obs_ref=obs_ref,
            allowed_skill_ids=allowed_skill_ids,
            candidates=candidates,
            evidence_refs=evidence_refs,
            need_replan=need_replan,
        )
